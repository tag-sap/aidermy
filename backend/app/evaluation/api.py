"""HTTP API for evaluation v2 (`/api/v1/evaluation`).

Registered in the real application by ``evaluation.runtime.configure_evaluation``
(called from ``app.main``). Endpoints:

  GET  /parameters                     public: registry + rule description
  GET  /health                         public: storage/schema/research readiness
  POST /preview                        pure calculation, nothing is stored
  POST /snapshots                      build & persist a snapshot (auth)
  GET  /snapshots/{id}                 read a snapshot (owner only)
  POST /analyze                        scan all parameters, no spend (auth)
  POST /analyze/research               scan + shared research (admin)
  POST /products/{id}/status           current gaps of a catalog product (auth)
  POST /products/{id}/analyze          analyze a catalog product, no spend (auth)
  POST /products/{id}/research         analyze + research a catalog product (admin)
  POST /research-jobs                  enqueue missing parameters (admin)

All analysis endpoints run the synchronous service in a worker thread: page
downloads, search and LLM calls must not block the event loop.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..auth import get_current_user, get_current_user_optional
from .analysis import AnalysisService, AnalysisUnavailable
from .contracts import SCORE_LEVEL_CRITERIA, STATUS_ASSESSED, ContractError, ParameterEvaluation
from .knowledge import ProductNotFound, KnowledgeUnavailable, load_product_knowledge
from .gaps import analysis_state, scan_parameters
from .engine import evaluate
from .parameters import PARAMETERS
from .questionnaire import QUESTIONNAIRE_SOURCE, QUESTIONNAIRE_VERSION, SECTIONS
from .rules import describe_rules, get_rules
from .service import DEFAULT_METHOD_VERSION, EvaluationService
from .store import COMPOSITION_ACTIVE, StoreError

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


class CompositionInput(BaseModel):
    composition_hash: str = Field(min_length=1)
    inci_raw: str = ""
    source: str = ""
    verified_at: str | None = None


class ProductInput(BaseModel):
    id: int
    name: str = ""


class EvaluationInput(BaseModel):
    parameter_id: str
    # Required on purpose: a caller must state the status of the result. There is
    # no default "assessed" — an evaluation is never born scored by omission.
    status: str
    value: float | None = None
    confidence: float | None = None
    evidence_ids: list[str] = []
    rationale: str = ""
    limitations: list[str] = []
    evaluated_at: str = ""
    valid_until: str | None = None


class PreviewRequest(BaseModel):
    profile: dict[str, Any] = {}
    composition: CompositionInput | None = None
    evaluations: list[EvaluationInput] = []


class SnapshotRequest(BaseModel):
    profile: dict[str, Any] = {}
    product: ProductInput
    composition: CompositionInput


class ResearchRequest(BaseModel):
    product_id: int
    composition_hash: str
    parameters: list[str] = []


class AnalyzeRequest(BaseModel):
    """Either ``product_id`` (load from the Aidermy catalog) or explicit fields."""

    product_id: int | None = None
    product: ProductInput | None = None
    composition: CompositionInput | None = None
    profile: dict[str, Any] = {}
    source_urls: list[str] = []
    verified_at: str | None = None
    # Admin-only explicit confirmation of a catalog INCI (never implied).
    verify_catalog_inci: bool = False


class ProductAnalysisRequest(BaseModel):
    """Profile + explicit options for the catalog-product endpoints."""

    profile: dict[str, Any] = {}
    source_urls: list[str] = []
    verified_at: str | None = None
    verify_catalog_inci: bool = True


def _store(request: Request):
    store = getattr(request.app.state, "evaluation_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="evaluation storage is not configured")
    return store


def _method_version(request: Request) -> str:
    return getattr(request.app.state, "evaluation_method_version", DEFAULT_METHOD_VERSION)


def _service(request: Request) -> EvaluationService:
    return EvaluationService(
        _store(request),
        rules=get_rules(getattr(request.app.state, "evaluation_rule_version", None)),
        method_version=_method_version(request),
    )


def _analysis_service(request: Request) -> AnalysisService:
    from .runtime import analysis_limits_from_env

    return AnalysisService(
        _store(request),
        provider=getattr(request.app.state, "evaluation_research_provider", None),
        fetcher=getattr(request.app.state, "evaluation_document_fetcher", None),
        search=getattr(request.app.state, "evaluation_source_search", None),
        rules=get_rules(getattr(request.app.state, "evaluation_rule_version", None)),
        method_version=_method_version(request),
        allow_synthetic_evidence=bool(
            getattr(request.app.state, "evaluation_allow_synthetic_evidence", False)
        ),
        **analysis_limits_from_env(),
    )


_admin_security = HTTPBasic(auto_error=False)


def require_admin(
    credentials: HTTPBasicCredentials | None = Depends(_admin_security),
    x_admin_authorization: str | None = Header(
        default=None, alias="X-Admin-Authorization"
    ),
) -> None:
    """Reuse the admin credentials check from the existing admin routes.

    FastAPI's ``HTTPBasic`` and ``OAuth2PasswordBearer`` both read the same
    ``Authorization`` header. An endpoint that needs a user JWT *and* admin
    credentials therefore cannot be called with a plain Basic header: it would
    replace the Bearer token. Admin clients may send the Basic value in
    ``X-Admin-Authorization`` instead, keeping ``Authorization: Bearer ...`` for
    the user. The standard ``Authorization: Basic ...`` form keeps working when
    the endpoint does not also require a user.
    """
    if credentials is None and x_admin_authorization:
        scheme, _, value = x_admin_authorization.partition(" ")
        if scheme.lower() == "basic" and value:
            try:
                decoded = base64.b64decode(value, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                decoded = ""
            username, separator, password = decoded.partition(":")
            if separator:
                credentials = HTTPBasicCredentials(username=username, password=password)
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )

    from ..admin_routes import verify_admin

    verify_admin(credentials)


@router.get("/parameters")
async def list_parameters() -> dict:
    rules = get_rules()
    return {
        "questionnaire": {
            "version": QUESTIONNAIRE_VERSION,
            "source": QUESTIONNAIRE_SOURCE,
            "sections": [
                {
                    "id": section.id,
                    "label": section.label,
                    "evaluated": section.evaluated,
                    "options": [
                        {"id": option.id, "label": option.label}
                        for option in section.options
                    ],
                    "modifiers": [
                        {"id": item.id, "label": item.label}
                        for item in section.modifiers
                    ],
                }
                for section in SECTIONS
            ],
        },
        "parameters": [parameter.as_dict() for parameter in PARAMETERS.values()],
        "statuses": {
            "assessed": "выставлен балл и объяснение по подтверждённым доказательствам",
            "not_applicable": "параметр неприменим к продукту (не влияет на среднее)",
            "insufficient_evidence": "параметр применим, доказательств недостаточно",
            "pending": "ещё не исследован",
        },
        "score_levels": list(get_rules().score_levels),
        "score_criteria": {
            str(level): criterion for level, criterion in SCORE_LEVEL_CRITERIA.items()
        },
        "rules": describe_rules(rules),
    }


def _require_verified_preview_evidence(
    item: EvaluationInput,
    *,
    composition_hash: str,
    store,
    user: dict | None,
) -> None:
    """An ``assessed`` preview must point at real, fetched, confirmed evidence.

    ``/preview`` is a public calculation endpoint, so it cannot invent scores:
    the caller has to be authenticated and reference evidence that already exists
    in the store for this composition and parameter.
    """
    if user is None:
        raise HTTPException(
            status_code=403, detail="assessed preview requires authentication"
        )
    if not composition_hash:
        raise HTTPException(
            status_code=422, detail="assessed preview requires composition_hash"
        )
    if store is None:
        raise HTTPException(
            status_code=503, detail="evaluation storage is not configured"
        )
    if not item.evidence_ids:
        raise HTTPException(
            status_code=422, detail="assessed preview requires evidence_ids"
        )
    for raw in item.evidence_ids:
        try:
            evidence_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"invalid evidence_id: {raw!r}"
            ) from exc
        record = store.evidence_ref(evidence_id)
        if record is None:
            raise HTTPException(
                status_code=422, detail=f"evidence {evidence_id} is not stored"
            )
        if record.get("verification") != "confirmed":
            raise HTTPException(
                status_code=422, detail=f"evidence {evidence_id} is not confirmed"
            )
        if record.get("provenance") != "fetched":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"evidence {evidence_id} is not fetched "
                    f"(provenance={record.get('provenance') or 'unknown'})"
                ),
            )
        if record.get("parameter_id") != item.parameter_id:
            raise HTTPException(
                status_code=422,
                detail=f"evidence {evidence_id} belongs to another parameter",
            )
        if str(record.get("composition_hash") or "") != composition_hash:
            raise HTTPException(
                status_code=422,
                detail=f"evidence {evidence_id} belongs to another composition",
            )


@router.post("/preview")
async def preview(
    payload: PreviewRequest,
    request: Request,
    user: dict | None = Depends(get_current_user_optional),
) -> dict:
    composition_hash = payload.composition.composition_hash if payload.composition else ""
    store = getattr(request.app.state, "evaluation_store", None)
    for item in payload.evaluations:
        if item.status == STATUS_ASSESSED:
            _require_verified_preview_evidence(
                item,
                composition_hash=composition_hash,
                store=store,
                user=user,
            )
    try:
        evaluations = [
            ParameterEvaluation(
                parameter_id=item.parameter_id,
                status=item.status,
                value=item.value,
                confidence=item.confidence,
                composition_hash=composition_hash or "preview",
                method_version=DEFAULT_METHOD_VERSION,
                evidence_ids=tuple(item.evidence_ids),
                rationale=item.rationale,
                limitations=tuple(item.limitations),
                evaluated_at=item.evaluated_at,
                valid_until=item.valid_until,
            )
            for item in payload.evaluations
        ]
        result = evaluate(payload.profile, evaluations)
    except ContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"result": result.as_dict()}


@router.post("/snapshots")
async def create_snapshot(
    payload: SnapshotRequest,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    service = _service(request)
    try:
        built = service.build(
            product=payload.product.model_dump(),
            composition=payload.composition.model_dump(),
            profile=payload.profile,
            user_id=int(user["id"]),
        )
    except StoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "snapshot": built.snapshot,
        "analysis": built.analysis.as_dict(),
        "pending_parameters": list(built.pending_parameters),
        "stale_parameters": list(built.stale_parameters),
        "reused": built.reused,
    }


@router.get("/snapshots/{snapshot_id}")
async def read_snapshot(
    snapshot_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    service = _service(request)
    try:
        snapshot = service.snapshot(snapshot_id)
    except StoreError as exc:
        message = str(exc)
        status = 409 if "integrity" in message else 404
        raise HTTPException(status_code=status, detail=message) from exc
    owner = snapshot.get("user_id")
    if owner is None or int(owner) != int(user["id"]):
        raise HTTPException(status_code=403, detail="snapshot belongs to another user")
    return {"snapshot": snapshot}


def _analyze_sync(
    payload: AnalyzeRequest,
    request: Request,
    user: dict,
    *,
    allow_research: bool,
) -> dict:
    """Blocking analysis (runs in a worker thread, never on the event loop)."""
    service = _analysis_service(request)
    product_loader = getattr(request.app.state, "evaluation_product_loader", None)
    try:
        if payload.product_id is not None:
            report = service.analyze_product(
                payload.product_id,
                profile=payload.profile,
                verified_at=payload.verified_at,
                extra_sources=tuple(payload.source_urls),
                allow_research=allow_research,
                user_id=int(user["id"]),
                product_loader=product_loader,
                verify_catalog_inci=payload.verify_catalog_inci and allow_research,
            )
        elif payload.product is not None and payload.composition is not None:
            report = service.analyze(
                product=payload.product.model_dump(),
                composition=payload.composition.model_dump(),
                profile=payload.profile,
                source_urls=tuple(payload.source_urls),
                allow_research=allow_research,
                user_id=int(user["id"]),
            )
        else:
            raise HTTPException(
                status_code=422, detail="provide product_id or product+composition"
            )
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnalysisUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except StoreError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.as_dict()


async def _run_analysis(
    payload: AnalyzeRequest,
    request: Request,
    user: dict,
    *,
    allow_research: bool,
) -> dict:
    return await run_in_threadpool(
        _analyze_sync, payload, request, user, allow_research=allow_research
    )


@router.post("/analyze")
async def analyze(
    payload: AnalyzeRequest,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Scan all parameters and assemble the report without spending on research."""
    return await _run_analysis(payload, request, user, allow_research=False)


@router.post("/analyze/research")
async def analyze_with_research(
    payload: AnalyzeRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    _admin: None = Depends(require_admin),
) -> dict:
    """Same, but research the gaps first (shared downloads, per-parameter results)."""
    return await _run_analysis(payload, request, user, allow_research=True)



@router.get("/health")
async def evaluation_health(request: Request) -> dict:
    """Readiness of the V2 wiring (booleans only, no secrets)."""
    from .runtime import evaluation_schema_status

    store = getattr(request.app.state, "evaluation_store", None)
    provider = getattr(request.app.state, "evaluation_research_provider", None)
    fetcher = getattr(request.app.state, "evaluation_document_fetcher", None)
    search = getattr(request.app.state, "evaluation_source_search", None)
    schema = await run_in_threadpool(evaluation_schema_status)
    return {
        "storage": {"configured": store is not None},
        "research": {
            "provider": getattr(provider, "name", None) or "missing",
            "fetcher": getattr(fetcher, "name", None) or "missing",
            "search": getattr(search, "name", None) or "missing",
        },
        "schema": schema,
    }


class _ProductStatusRequest(BaseModel):
    profile: dict[str, Any] = {}


def _product_status_sync(
    product_id: int, payload: _ProductStatusRequest, request: Request
) -> dict:
    store = _store(request)
    service = _service(request)
    loader = getattr(request.app.state, "evaluation_product_loader", None)
    try:
        knowledge = load_product_knowledge(product_id, product_loader=loader)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    record = service.ensure_composition(product_id, knowledge.composition)
    stored = store.current_evaluations(record["id"], _method_version(request))
    scan = scan_parameters(
        evaluations=stored,
        profile=payload.profile,
        composition_hash=str(record["composition_hash"]),
        method_version=_method_version(request),
    )
    blocked = str(record.get("status") or "") != COMPOSITION_ACTIVE
    state = analysis_state(scan=scan, blocked=blocked, extra_notes=knowledge.notes)
    return {
        "product": knowledge.product,
        "composition": {
            "composition_hash": record["composition_hash"],
            "source": record.get("source") or "",
            "verified_at": str(record.get("verified_at") or ""),
            "status": record.get("status") or "",
        },
        "analysis": state.as_dict(),
        "current": [item.as_dict() for item in scan.current],
        "source_urls": list(knowledge.source_urls),
    }


@router.post("/products/{product_id}/status")
async def product_status(
    product_id: int,
    payload: _ProductStatusRequest,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """What is already known and what is missing (no writes to research, no spend)."""
    return await run_in_threadpool(_product_status_sync, product_id, payload, request)


def _product_analysis_request(
    payload: ProductAnalysisRequest, product_id: int, *, verify_catalog_inci: bool
) -> AnalyzeRequest:
    return AnalyzeRequest(
        product_id=product_id,
        profile=payload.profile,
        source_urls=payload.source_urls,
        verified_at=payload.verified_at,
        verify_catalog_inci=verify_catalog_inci,
    )


@router.post("/products/{product_id}/analyze")
async def product_analyze(
    product_id: int,
    payload: ProductAnalysisRequest,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Analyze a catalog product: scan + report, no research spending."""
    body = _product_analysis_request(payload, product_id, verify_catalog_inci=False)
    return await _run_analysis(body, request, user, allow_research=False)


@router.post("/products/{product_id}/research")
async def product_research(
    product_id: int,
    payload: ProductAnalysisRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    _admin: None = Depends(require_admin),
) -> dict:
    """Analyze + research a catalog product (admin; shared downloads)."""
    body = _product_analysis_request(
        payload, product_id, verify_catalog_inci=bool(payload.verify_catalog_inci)
    )
    return await _run_analysis(body, request, user, allow_research=True)


@router.post("/research-jobs")
async def create_research_jobs(
    payload: ResearchRequest,
    request: Request,
    _admin: None = Depends(require_admin),
) -> dict:
    store = _store(request)
    record = store.get_composition(payload.product_id, payload.composition_hash)
    if record is None:
        raise HTTPException(status_code=404, detail="composition is not registered")
    if str(record.get("status") or "") != COMPOSITION_ACTIVE:
        raise HTTPException(
            status_code=409,
            detail=(
                "composition is not verified (status="
                f"{record.get('status') or 'unverified'}): verify the INCI before research"
            ),
        )
    service = _service(request)
    created = service.enqueue_research(record["id"], payload.parameters)
    return {"created": created, "composition_id": record["id"]}


def setup_evaluation_routes(
    app,
    *,
    store=None,
    method_version: str | None = None,
    rule_version: str | None = None,
    provider=None,
    fetcher=None,
    search=None,
    allow_synthetic_evidence: bool = False,
) -> None:
    """Register the router and attach the optional dependencies to app.state."""
    app.state.evaluation_store = store
    if method_version:
        app.state.evaluation_method_version = method_version
    if rule_version:
        app.state.evaluation_rule_version = rule_version
    app.state.evaluation_research_provider = provider
    app.state.evaluation_document_fetcher = fetcher
    app.state.evaluation_source_search = search
    app.state.evaluation_allow_synthetic_evidence = allow_synthetic_evidence
    app.include_router(router)
