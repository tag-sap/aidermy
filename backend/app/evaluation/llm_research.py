"""Real research provider: LLM extraction over pages that were actually fetched.

The model never supplies page text. It receives the documents downloaded for this
composition (``ResearchRequest.documents``) and may only quote them; every quote is
re-validated against the stored text in ``evidence.validate_candidate``. The model
also chooses the score, but only within the agreed 0/25/50/75/100 scale, and the
deterministic layer may reject or downgrade the proposal.

Without fetched documents, or without an API key, the provider reports an honest
``source_unavailable`` / ``provider_error`` — it never invents a successful check.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable, Mapping, Sequence

from .documents import SourceDocument
from .evidence import EvidenceCandidate, Source
from .research import (
    APPLICABILITY,
    RESEARCH_INSUFFICIENT,
    RESEARCH_OK,
    RESEARCH_PROVIDER_ERROR,
    RESEARCH_SOURCE_UNAVAILABLE,
    AssessmentProposal,
    ResearchOutcome,
    ResearchRequest,
)

DEFAULT_MODELS = ("deepseek-chat", "deepseek-v4-flash", "deepseek-flash")
DEFAULT_API_URL = "https://api.deepseek.com/v1/chat/completions"

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты — исследователь состава косметики. Тебе дан список скачанных страниц "
    "источника. Ты обязан отвечать ТОЛЬКО по их тексту.\n"
    "Правила:\n"
    "1. Каждый вывод подтверждай дословной цитатой из текста страницы. Не пересказывай "
    "и не придумывай цитаты.\n"
    "2. Если в тексте нет ответа на вопрос — sufficient=false, score=null.\n"
    "3. score — одно из 0, 25, 50, 75, 100, только если sufficient=true.\n"
    "4. applicability=not_applicable допустима, только если продукт по тексту явно "
    "не предназначен для этого требования; приведи applicability_reason.\n"
    "5. Не используй медицинские утверждения («лечит», «безопасен», «гарантирует»).\n"
    "6. quote — один непрерывный дословный фрагмент текста ровно одной страницы. "
    "Нельзя ставить многоточия, склеивать разные фрагменты, пересказывать или менять слова. "
    "Если дословной цитаты нет — не добавляй этот evidence.\n"
    "Ответ — строго JSON без markdown:\n"
    '{"applicability":"applicable|not_applicable","applicability_reason":"...",'
    '"sufficient":true|false,"score":0|25|50|75|100|null,"rationale":"...",'
    '"limitations":["..."],"contradictions":["..."],"important_unknowns":["..."],'
    '"evidence":[{"url":"...","quote":"...","claim":"...",'
    '"direction":"supports|contradicts|neutral","strength":"weak|moderate|strong",'
    '"confidence":0.0}]}'
)


def _extract_json(text: str) -> dict | None:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _build_user_prompt(request: ResearchRequest, documents: Sequence[SourceDocument], max_chars: int) -> str:
    anchors = "\n".join(f"- {int(value)}: {text}" for value, text in request.scale_anchors)
    blocks = []
    for index, document in enumerate(documents, start=1):
        blocks.append(
            f"[{index}] url: {document.url}\n"
            f"title: {document.title or '(без заголовка)'}\n"
            f"text: {document.text[:max_chars]}"
        )
    return (
        f"Продукт: {request.product_name or request.product_id}\n"
        f"Состав (INCI): {', '.join(request.ingredients) or 'не указан'}\n\n"
        f"Параметр: {request.parameter_label}\n"
        f"Вопрос: {request.parameter_question or request.parameter_definition}\n"
        f"Определение: {request.parameter_definition}\n\n"
        f"Шкала:\n{anchors}\n\n"
        f"Скачанные страницы:\n\n" + "\n\n".join(blocks) + "\n\n"
        "Верни только JSON по схеме."
    )


class LlmResearchProvider:
    """DeepSeek (or any OpenAI-compatible) extraction over fetched documents."""

    name = "llm"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        models: Sequence[str] = DEFAULT_MODELS,
        timeout: float = 60.0,
        max_documents: int = 6,
        max_document_chars: int = 6000,
        price_per_1k_tokens: float = 0.0,
        post: Callable[[dict], Mapping] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
        self.api_url = api_url or os.getenv("DEEPSEEK_API_URL", DEFAULT_API_URL)
        self.models = tuple(models)
        self.timeout = timeout
        self.max_documents = max_documents
        self.max_document_chars = max_document_chars
        self.price_per_1k_tokens = price_per_1k_tokens
        self._post = post

    # -- transport -----------------------------------------------------------
    def _http_post(self, payload: dict) -> Mapping:
        import httpx

        response = httpx.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        return response.json()

    def _call(self, prompt: str) -> tuple[str, int, int]:
        if self._post is None and not self.api_key:
            raise RuntimeError("LLM не настроен: нет DEEPSEEK_API_KEY")
        last_error: Exception | None = None
        data: Mapping = {}
        for model in self.models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }
            try:
                data = self._post(payload) if self._post is not None else self._http_post(payload)
                break
            except Exception as exc:  # noqa: BLE001 - try the next configured model
                last_error = exc
                logger.warning("[EVAL LLM] model=%s failed: %s", model, exc)
        else:
            raise RuntimeError(f"модели недоступны: {last_error}")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"неожиданный ответ модели: {exc}") from exc
        usage = data.get("usage") or {}
        return (
            str(content),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )


    # -- contract ------------------------------------------------------------
    def research(self, request: ResearchRequest) -> ResearchOutcome:
        documents = tuple(request.documents)[: self.max_documents]
        if not documents:
            return ResearchOutcome(
                status=RESEARCH_SOURCE_UNAVAILABLE,
                error="нет загруженных источников: сначала нужно скачать страницы продукта",
                provider=self.name,
            )
        prompt = _build_user_prompt(request, documents, self.max_document_chars)
        try:
            content, tokens_in, tokens_out = self._call(prompt)
        except Exception as exc:  # noqa: BLE001 - provider failures are data
            return ResearchOutcome(
                status=RESEARCH_PROVIDER_ERROR, error=str(exc), provider=self.name
            )

        cost = round((tokens_in + tokens_out) / 1000 * self.price_per_1k_tokens, 6)
        parsed = _extract_json(content)
        if parsed is None:
            return ResearchOutcome(
                status=RESEARCH_PROVIDER_ERROR,
                error="модель вернула не JSON",
                provider=self.name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
            )

        applicability = str(parsed.get("applicability") or "applicable").strip()
        if applicability not in APPLICABILITY:
            return ResearchOutcome(
                status=RESEARCH_PROVIDER_ERROR,
                error=f"недопустимая применимость: {applicability!r}",
                provider=self.name,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost,
            )
        score_raw = parsed.get("score")
        score = int(score_raw) if isinstance(score_raw, (int, float)) else None
        rationale = str(parsed.get("rationale") or "").strip()

        by_url = {document.url: document for document in documents}
        candidates: list[EvidenceCandidate] = []
        refs: list[int] = []
        dropped: list[str] = []
        for item in parsed.get("evidence") or []:
            if not isinstance(item, Mapping):
                continue
            url = str(item.get("url") or "").strip()
            quote = str(item.get("quote") or "").strip()
            document = by_url.get(url)
            if document is None or not quote:
                dropped.append(url or "(без url)")
                continue
            try:
                candidate = EvidenceCandidate(
                    parameter_id=request.parameter_id,
                    claim=str(item.get("claim") or request.parameter_label).strip(),
                    quote=quote,
                    source=Source(
                        url=document.url,
                        title=document.title,
                        source_type="unknown",
                        retrieved_at=document.retrieved_at,
                        content_hash=document.content_hash,
                        provenance=document.provenance,
                    ),
                    source_text=document.text,
                    direction=str(item.get("direction") or "supports"),
                    strength=str(item.get("strength") or "moderate"),
                    confidence=float(item.get("confidence") or 0.6),
                    extraction_method="llm_quote_extraction_v1",
                )
            except Exception:  # noqa: BLE001 - a malformed item is not a crash
                dropped.append(url)
                continue
            refs.append(len(candidates))
            candidates.append(candidate)

        limitations = [
            str(text).strip()
            for text in parsed.get("limitations") or []
            if str(text).strip()
        ]
        if dropped:
            limitations.append(
                "Модель сослалась на страницы вне загруженного набора: "
                + ", ".join(sorted(set(dropped))[:5])
            )
        proposal = AssessmentProposal(
            parameter_id=request.parameter_id,
            applicability=applicability,
            applicability_reason=str(parsed.get("applicability_reason") or "").strip(),
            sufficient=bool(parsed.get("sufficient")),
            score=score,
            rationale=rationale,
            limitations=tuple(limitations),
            contradictions=tuple(
                str(text).strip()
                for text in parsed.get("contradictions") or []
                if str(text).strip()
            ),
            important_unknowns=tuple(
                str(text).strip()
                for text in parsed.get("important_unknowns") or []
                if str(text).strip()
            ),
            evidence_refs=tuple(refs),
        )
        status = RESEARCH_OK if candidates else RESEARCH_INSUFFICIENT
        return ResearchOutcome(
            status=status,
            candidates=tuple(candidates),
            proposal=proposal,
            provider=self.name,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )

