"""HTTP API for evaluation v2 (`/api/v1/evaluation`).

The router is intentionally NOT registered in app/main.py yet. Registration is a
one-line call (`setup_evaluation_routes(app, store=...)`) after the migration and
staging checks are approved.

Contract:
  GET  /api/v1/evaluation/parameters        public: registry + rule description
  POST /api/v1/evaluation/preview           pure calculation, nothing is stored
  POST /api/v1/evaluation/snapshots         build & persist a snapshot (auth)
  GET  /api/v1/evaluation/snapshots/{id}    read a snapshot (owner only)
  POST /api/v1/evaluation/research-jobs     enqueue missing parameters (auth)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from ..auth import get_current_user, get_current_user_optional
from .contracts import ContractError, ParameterEvaluation
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
    status: str = "evaluated"
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


_admin_security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_admin_security)) -> None:
    """Reuse the admin credentials check from the existing admin routes."""
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
        "rules": describe_rules(rules),
    }


@router.post("/preview")
async def preview(
    payload: PreviewRequest,
    _user: dict | None = Depends(get_current_user_optional),
) -> dict:
    composition_hash = payload.composition.composition_hash if payload.composition else "preview"
    try:
        evaluations = [
            ParameterEvaluation(
                parameter_id=item.parameter_id,
                status=item.status,
                value=item.value,
                confidence=item.confidence,
                composition_hash=composition_hash,
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


def setup_evaluation_routes(app, *, store=None, method_version: str | None = None) -> None:
    """Register the router. Call only after the migration is approved."""
    if store is not None:
        app.state.evaluation_store = store
    if method_version:
        app.state.evaluation_method_version = method_version
    app.include_router(router)
