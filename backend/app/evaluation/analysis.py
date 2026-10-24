"""End-to-end analysis: product knowledge -> gaps -> shared research -> report.

This is the mechanic the product needs, in one place:

  1. load the product and its composition (optionally from the Aidermy catalog);
  2. scan EVERY questionnaire parameter and collect the full gap set;
  3. research the gaps together: discover pages with the project's search, fetch
     each page once, answer each parameter from the same documents, keep each
     parameter's own result;
  4. assemble the report and state honestly whether it is final.

The service never invents a score and never marks an unfinished or failed analysis
as a finished report: that decision belongs to ``gaps.analysis_state``.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .gaps import AnalysisState, analysis_state, scan_parameters
from .documents import MAX_DOCUMENTS_PER_SESSION
from .freshness import DEFAULT_REVIEW_AFTER_DAYS
from .inci import NOT_LISTED, PRESENT, UNVERIFIABLE, check_intolerance
from .knowledge import (
    KnowledgeUnavailable,
    ProductKnowledge,
    ProductNotFound,
    assess_composition,
    load_product_knowledge,
)
from .parameters import PARAMETERS, ingredient_parameter, resolve_parameters
from .primary_function import build_primary_function, public_primary_function
from .relevance import goal_scope, goal_scope_note
from .comedogenicity import assess_comedogenicity
from .comedo_dedupe import comedo_ingredient_names, scrub_comedo_fields
from .verdicts import VERDICT_ICON_BY_STATUS, verdict_band
from .research import ResearchProvider
from .snapshot import profile_fingerprint, verify_snapshot
from .timing import StageTimer
from .research_service import (
    DEFAULT_MAX_ATTEMPTS,
    ResearchPlan,
    ResearchRunReport,
    ResearchService,
)
from .rules import RuleSet, get_rules
from .service import DEFAULT_METHOD_VERSION, EvaluationService
from .store import COMPOSITION_ACTIVE, EvaluationStore
from .websearch import SourceSearch


logger = logging.getLogger(__name__)


class AnalysisUnavailable(RuntimeError):
    """The analysis cannot run (missing provider, catalog or composition)."""


_INTOLERANCE_LABELS = {
    PRESENT: "Обнаружен в составе",
    NOT_LISTED: "Не обнаружен в составе",
    UNVERIFIABLE: "Не удалось определить",
}
_INTOLERANCE_STATES = {
    PRESENT: "present",
    NOT_LISTED: "absent",
    UNVERIFIABLE: "unknown",
}


def _intolerance_status(parameter_id: str, composition: Mapping) -> dict | None:
    """Expose the authoritative INCI status without reinterpreting the score."""
    parameter = PARAMETERS.get(parameter_id)
    if parameter is None and parameter_id.startswith("intolerance:ingredient:"):
        name = parameter_id.split(":", 2)[2].replace("_", " ").strip()
        if not name:
            return None
        try:
            parameter = ingredient_parameter(name)
        except Exception:  # noqa: BLE001 - malformed legacy ids stay unknown
            return None
    if parameter is None or parameter.section != "intolerance":
        return None
    checked = check_intolerance(parameter, composition)
    if checked is None:
        return None
    return {
        "state": _INTOLERANCE_STATES.get(checked.status, "unknown"),
        "label": _INTOLERANCE_LABELS.get(checked.status, "Не удалось определить"),
        "status": checked.status,
        "reason": checked.reason,
        "matched": list(checked.matched),
    }


def _short_explanation(text: object) -> str:
    """Keep at most two complete sentences; never cut a word or sentence."""
    clean = " ".join(str(text or "").replace("\n", " ").split())
    if not clean:
        return ""
    # The stored rationale starts with the parameter label and the question;
    # show the concrete answer, not the question.
    question_end = clean.find("?")
    if 0 <= question_end < len(clean) - 1:
        after_question = clean[question_end + 1:].strip()
        if after_question:
            clean = after_question
    # Model rationales append scoring/audit material after the actual reason.
    for marker in ("Оценка ", "За требование:", "Без отношения", "Цитаты приведены"):
        cut = clean.find(marker)
        if cut > 0:
            clean = clean[:cut].rstrip(" ;,.")
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    generic_prefixes = (
        "Оценивается ",
        "Насколько ",
        "Подходит ли ",
        "Соответствует ли ",
        "Можно ли ",
    )
    concrete = [
        sentence for sentence in sentences
        if sentence.strip() and not sentence.lstrip().startswith(generic_prefixes)
    ]
    selected = concrete or sentences
    # One complete sentence is better than two very long ones. Never cut a
    # sentence in the middle to satisfy a character budget.
    result = " ".join(selected[:1] if len(selected[0]) > 180 else selected[:2]).strip()
    if len(result) > 300 and len(selected) > 1:
        result = selected[0].strip()
    if result and result[-1] not in ".!?":
        result += "."
    return result


def _evidence_explanation(evidence: Sequence[Mapping] | None, verdict: str) -> str:
    """Prefer the short stored claim over repeating a long model rationale."""
    if verdict not in {"positive", "negative"}:
        return ""
    wanted = "contradicts" if verdict == "negative" else "supports"
    rows = [
        row for row in (evidence or [])
        if str(row.get("verification") or "") == "confirmed"
        and (not wanted or str(row.get("direction") or "") == wanted)
    ]
    if not rows:
        return ""
    rows.sort(
        key=lambda row: (
            {"strong": 3, "moderate": 2, "weak": 1}.get(str(row.get("strength") or ""), 0),
            float(row.get("confidence") or 0),
        ),
        reverse=True,
    )
    return _short_explanation(rows[0].get("claim") or rows[0].get("quote"))


def _risk_kind(evidence: Sequence[Mapping] | None) -> str:
    """Classify confirmed evidence as a confirmed or probable risk.

    This is deliberately based on stored, verified evidence and the existing
    evaluation result, not on guessing from an ingredient name.
    """
    risk_level = 0
    risk_confidence = 0.0
    support_level = 0
    support_confidence = 0.0
    levels = {"weak": 1, "moderate": 2, "strong": 3}
    for row in evidence or []:
        if str(row.get("verification") or "") != "confirmed":
            continue
        try:
            confidence = float(row.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        level = levels.get(str(row.get("strength") or ""), 0)
        direction = str(row.get("direction") or "")
        if direction == "contradicts" and level > risk_level:
            risk_level, risk_confidence = level, confidence
        elif direction == "supports" and level > support_level:
            support_level, support_confidence = level, confidence
    if risk_level >= 3 and risk_confidence >= 0.7:
        return "confirmed"
    if risk_level == 2 and risk_confidence >= 0.7:
        if support_level >= 3 and support_confidence >= risk_confidence:
            return ""
        return "probable"
    # A weak but confirmed contradiction is enough to require attention, but
    # not enough to declare the product unsuitable. This distinction is what
    # the user-facing “С осторожностью” state exists for.
    if risk_level == 1 and risk_confidence >= 0.7:
        return "possible"
    return ""


# Intolerance rows answer a profile restriction. A confirmed presence is a
# real conflict; an absent ingredient in a complete INCI satisfies the user's
# “avoid this” restriction and is a positive result.
_CRITICAL_SECTIONS = {"skin_type", "problem", "therapy", "procedure", "intolerance"}
_VERDICT_ICONS = {
    "positive": VERDICT_ICON_BY_STATUS["positive"],
    "negative": VERDICT_ICON_BY_STATUS["negative"],
    "caution": VERDICT_ICON_BY_STATUS["caution"],
    "neutral": VERDICT_ICON_BY_STATUS["neutral"],
    "unknown": VERDICT_ICON_BY_STATUS["unknown"],
}


def _section(parameter_id: str) -> str:
    return parameter_id.split(":", 1)[0]


def _verdict_label(
    parameter_id: str,
    verdict: str,
    intolerance: Mapping | None = None,
    risk_kind: str = "",
    goal_scope: str = "",
) -> str:
    section = _section(parameter_id)
    if section == "intolerance" and intolerance is not None:
        return str(intolerance.get("label") or "Не удалось определить")
    if section == "therapy":
        return {
            "positive": "Совместимо с лечением",
            "caution": "Требует осторожности с лечением",
            "neutral": "Совместимость неясна",
            "negative": (
                "Скорее всего несовместим с лечением"
                if risk_kind == "probable"
                else "Конфликт с лечением"
            ),
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "procedure":
        return {
            "positive": "Можно использовать в этот период",
            "caution": "Нужна осторожность в этот период",
            "neutral": "Нужна осторожность",
            "negative": (
                "Скорее всего не рекомендуется в этот период"
                if risk_kind == "probable"
                else "Не рекомендуется в этот период"
            ),
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "goal":
        if verdict == "positive":
            return (
                "Поддерживает уход"
                if goal_scope == "supportive"
                else "Цель поддерживается"
            )
        if verdict == "neutral":
            return (
                "Не является самостоятельным средством"
                if goal_scope in {"not_intended", "supportive"}
                else "Цель не подтверждена"
            )
        return {
            "caution": "Возможна осторожность",
            "negative": "Есть риск в отношении цели",
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "skin_type":
        return {
            "positive": "Соответствует типу кожи",
            "caution": "Возможна осторожность",
            "neutral": "Смешанный результат",
            "negative": "Не соответствует типу кожи",
            "unknown": "Не удалось определить",
        }[verdict]
    if section == "problem":
        return {
            "positive": "Соответствует задаче",
            "caution": "Возможна осторожность",
            "neutral": "Смешанный результат",
            "negative": "Не соответствует задаче",
            "unknown": "Не удалось определить",
        }[verdict]
    return {
        "positive": "Подходит",
        "caution": "Возможна осторожность",
        "neutral": "Смешанный результат",
        "negative": "Не подходит",
        "unknown": "Не удалось определить",
    }[verdict]


def _item_verdict(
    parameter_id: str,
    score: object,
    intolerance: Mapping | None,
    evidence: Sequence[Mapping] | None = None,
) -> str:
    if intolerance is not None:
        # The profile asks the user to avoid an ingredient. A complete INCI
        # without it satisfies that restriction (positive); finding it is a
        # confirmed conflict (negative); an incomplete list stays unknown.
        state = str(intolerance.get("state") or "unknown")
        if state == "absent":
            return "positive"
        if state == "present":
            return "negative"
        return "unknown"
    try:
        value = float(score)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "unknown"
    section = _section(parameter_id)
    risk = _risk_kind(evidence)

    # Therapy and procedure are safety questions, not efficacy questions. A
    # mixed/low compatibility there deserves attention even when no strong
    # contradiction was confirmed; only a strong conflict is unsuitable.
    if section in {"therapy", "procedure"}:
        if risk == "confirmed" or value <= 0:
            return "negative"
        if risk in {"probable", "possible"} or value < 75:
            return "caution"
        return "positive"

    # Benefit questions: a low score may only mean that the product does not
    # treat the concern. It is not evidence of harm. If no confirmed negative
    # evidence exists, compatibility is positive; a real risk becomes a warning.
    if risk == "confirmed":
        return "negative"
    if risk in {"probable", "possible"}:
        return "caution"
    if value >= 75:
        return "positive"
    # A low benefit score without confirmed contradicting evidence is not a
    # safety warning. For goals it is specifically neutral: the product may be
    # useful in a routine, but its standalone effect on the goal is unproven.
    if section == "goal":
        return "neutral"
    if value >= 50:
        return "positive"
    return "neutral"


def _caution_copy(parameter_id: str, evidence: Sequence[Mapping] | None) -> tuple[str, str]:
    """Cause-aware risk and a non-prescriptive recommendation.

    The risk text is taken from confirmed evidence when possible; otherwise it
    states only the uncertainty that remains. The recommendation avoids dose,
    frequency and treatment schedules because those are not known from the INCI.
    """
    section = _section(parameter_id)
    risk = ""
    def evidence_rank(item: Mapping) -> tuple[int, float]:
        try:
            confidence = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return (
            {"strong": 3, "moderate": 2, "weak": 1}.get(str(item.get("strength") or ""), 0),
            confidence,
        )

    for row in sorted(evidence or [], key=evidence_rank, reverse=True):
        if str(row.get("verification") or "") != "confirmed":
            continue
        if str(row.get("direction") or "") != "contradicts":
            continue
        risk = _short_explanation(row.get("claim") or row.get("quote"))
        if risk:
            break
    if not risk:
        risk = {
            "therapy": "Возможна дополнительная нагрузка на кожу при сочетании с текущим лечением.",
            "procedure": "Возможна дополнительная нагрузка на кожу в период восстановления.",
            "skin_type": "Возможна дополнительная нагрузка на этот тип кожи.",
            "problem": "Возможна дополнительная нагрузка на кожу в рамках этой задачи.",
            "goal": "Возможна дополнительная нагрузка на кожу при достижении этой цели.",
        }.get(section, "Возможна дополнительная нагрузка на кожу.")
    recommendation = {
        "therapy": (
            "Обсудите сочетание с врачом, который назначил лечение, до начала "
            "совместного использования."
        ),
        "procedure": (
            "Обсудите использование с врачом, который проводил процедуру, "
            "до нанесения продукта."
        ),
        "goal": (
            "Не считайте продукт самостоятельным средством для этой цели; "
            "если он нужен в уходе, обсудите его роль с дерматологом."
        ),
        # No generic recommendation is invented for a benefit row when the
        # evidence does not support a concrete action. The cause and risk stay
        # visible instead.
        "skin_type": "",
        "problem": "",
    }.get(section, "")
    return risk, recommendation


def _quoted(label: str) -> str:
    match = re.search(r"«([^»]+)»", str(label or ""))
    return match.group(1).strip() if match else ""


def _display_text(
    parameter_id: str,
    label: str,
    verdict: str,
    *,
    intolerance: Mapping | None = None,
    risk_kind: str = "",
    goal_scope: str = "",
) -> str:
    """One short, concrete sentence for the compact verdict list."""
    section = _section(parameter_id)
    subject = _quoted(label)
    if verdict == "unknown":
        return f"Не удалось определить: {label or 'параметр'}."
    if section == "intolerance":
        name = subject or "Вещество"
        state = str((intolerance or {}).get("state") or "unknown")
        if state == "present":
            return f"{name} обнаружен в составе."
        if state == "absent":
            return f"{name} не обнаружен в составе."
        return f"{name}: не удалось определить наличие в составе."
    if section == "therapy":
        target = subject or "лечением"
        if verdict == "positive":
            return f"Можно использовать с лечением «{target}»."
        if verdict == "negative":
            if risk_kind == "probable":
                return f"Скорее всего несовместим с лечением «{target}»."
            return f"Не рекомендуется использовать с лечением «{target}»."
        if verdict == "caution":
            return f"С лечением «{target}» возможна осторожность."
        return f"Совместимость с лечением «{target}» неясна."
    if section == "procedure":
        target = subject or "процедурой"
        period = ""
        if subject and "»" in label:
            rest = label.split("»", 1)[1].strip(" ,")
            rest = re.sub(r"^Последние\s+", "первые ", rest, flags=re.I)
            if rest:
                period = f" ({rest[:1].lower() + rest[1:]})"
        if verdict == "positive":
            return f"Можно использовать после процедуры «{target}»{period}."
        if verdict == "negative":
            if risk_kind == "probable":
                return f"Скорее всего не рекомендуется использовать после процедуры «{target}»{period}."
            return f"Не рекомендуется использовать после процедуры «{target}»{period}."
        if verdict == "caution":
            return f"После процедуры «{target}»{period} возможна осторожность."
        return f"Нужна осторожность после процедуры «{target}»{period}."
    if section == "goal":
        target = subject or "цель"
        if verdict == "positive":
            if goal_scope == "supportive":
                return (
                    f"Может поддерживать уход в рамках цели «{target}», но не "
                    "заменяет средство для этой цели."
                )
            return f"Поддерживает цель «{target}»."
        if verdict == "negative":
            return f"Есть риск в отношении цели «{target}»."
        if verdict == "caution":
            return f"Возможна осторожность в отношении цели «{target}»."
        if goal_scope == "not_intended":
            return (
                f"Не является самостоятельным средством для цели «{target}»; "
                "это не риск."
            )
        if goal_scope == "supportive":
            return (
                f"Может поддерживать уход в рамках цели «{target}», но не является "
                "самостоятельным средством для её достижения; это не риск."
            )
        return f"Цель «{target}» не подтверждена; это не риск."
    if section == "problem":
        target = subject or "задача"
        if verdict == "positive":
            return f"Соответствует задаче «{target}»."
        if verdict == "negative":
            return f"Не соответствует задаче «{target}»."
        if verdict == "caution":
            return f"Возможна осторожность в отношении проблемы «{target}»."
        return f"Нейтрален в отношении проблемы «{target}»."
    if section == "skin_type":
        target = subject or "этого типа"
        if verdict == "positive":
            return f"Подходит для кожи типа «{target}»."
        if verdict == "negative":
            return f"Не подходит для кожи типа «{target}»."
        if verdict == "caution":
            return f"Возможна осторожность для кожи типа «{target}»."
        return f"Нейтрален для кожи типа «{target}»."
    if verdict == "positive":
        return f"{label or 'Параметр'} — подходит."
    if verdict == "negative":
        return f"{label or 'Параметр'} — не подходит."
    if verdict == "caution":
        return f"{label or 'Параметр'} — возможна осторожность."
    if verdict == "unknown":
        return f"Не удалось определить: {label or 'параметр'}."
    return f"{label or 'Параметр'} — нейтральный результат."


def _gap_label(parameter_id: str) -> str:
    parameter = PARAMETERS.get(parameter_id)
    if parameter is not None:
        return parameter.label
    if parameter_id.startswith("intolerance:ingredient:"):
        name = parameter_id.split(":", 2)[2].replace("_", " ").strip()
        if name:
            try:
                return ingredient_parameter(name).label
            except Exception:  # noqa: BLE001
                return name
    return "Параметр профиля"


def _overall_verdict(items: Sequence[Mapping], score: float | int | None = None) -> dict:
    """Aggregate conflicts by meaning, not by counting positive cards.

    ``score`` is an already calculated deterministic compatibility score, when
    one exists. Its thresholds are not recalculated here: ``verdict_band`` only
    maps the existing 0..19/20..39/40..59/60..79/80..100 bands to user text.
    Without a score, the semantic checklist outcome is mapped to the same five
    labels without inventing a percentage.
    """
    assessed = [
        item for item in items
        if item.get("verdict") in {"positive", "caution", "neutral", "negative"}
    ]
    unknown = sum(1 for item in items if item.get("verdict") == "unknown")
    positive = sum(1 for item in items if item.get("verdict") == "positive")
    caution = [item for item in items if item.get("verdict") == "caution"]
    neutral = sum(1 for item in items if item.get("verdict") == "neutral")
    negative = [item for item in items if item.get("verdict") == "negative"]
    critical = [
        item for item in negative
        if _section(str(item.get("parameter_id") or "")) in _CRITICAL_SECTIONS
    ]
    band = verdict_band(score)
    if critical:
        first = critical[0]
        verdict, tone, icon = "Не подходит", "bad", "dead"
        summary = f"Есть критичный конфликт: {first.get('label')}. {first.get('verdict_label')}."
    elif not assessed and unknown:
        verdict, tone, icon = "Недостаточно данных", "muted", "neutral"
        summary = "Нет подтверждённых данных; неизвестные результаты не считаются положительными."
    elif not assessed:
        verdict, tone, icon = "Недостаточно данных", "muted", "neutral"
        summary = "Для вашего профиля нет подтверждённых результатов."
    elif band is not None:
        verdict = str(band["label"])
        tone = str(band["tone"])
        icon = str(band["icon"])
        summary = "Оценка соответствия профилю кожи по подтверждённым данным."
    elif negative:
        verdict, tone, icon = "Слабо подходит", "warn", "alert"
        summary = "Есть подтверждённое предупреждение: продукт подходит не полностью."
    elif caution:
        first = caution[0]
        verdict, tone, icon = "Подходит частично", "neutral", "neutral"
        summary = f"Есть предупреждение: {first.get('label')} требует осторожности."
    elif unknown:
        verdict, tone, icon = "Подходит частично", "neutral", "neutral"
        summary = "Часть пунктов не проверена; это ограничивает вывод."
    elif neutral:
        if positive:
            verdict, tone, icon = "Хорошо подходит", "good", "happy"
            summary = (
                "Подтверждённых рисков нет; часть целей не подтверждена или "
                "не является назначением продукта."
            )
        else:
            verdict, tone, icon = "Подходит частично", "neutral", "neutral"
            summary = (
                "Подтверждённых рисков нет, но и положительных результатов "
                "по выбранным целям недостаточно."
            )
    else:
        verdict, tone, icon = "Отлично подходит", "good", "happy"
        summary = "Все проверенные пункты подтверждают совместимость."
    return {
        "verdict": verdict,
        "tone": tone,
        "icon": icon,
        "summary": summary,
        "positive": positive,
        "caution": len(caution),
        "neutral": neutral,
        "negative": len(negative),
        "unknown": unknown,
        "assessed": len(assessed),
    }


def _source_urls(items: Sequence[Mapping], primary: Mapping | None) -> list[str]:
    urls: list[str] = []

    def add(url: object) -> None:
        text = str(url or "").strip()
        if text.startswith(("http://", "https://")) and text not in urls:
            urls.append(text)

    for item in items:
        for row in item.get("evidence") or []:
            source = row.get("source") or {}
            add(source.get("url"))
    for row in (primary or {}).get("basis") or []:
        add(row.get("source"))
    return urls


@dataclass(frozen=True)
class AnalysisReport:
    product: dict
    composition: dict
    snapshot: dict
    analysis: AnalysisState
    research: ResearchRunReport | None = None
    plan: ResearchPlan | None = None
    knowledge: ProductKnowledge | None = None
    evidence: dict[str, list[dict]] = field(default_factory=dict)
    primary_function: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    # Raw questionnaire input is kept out of snapshots, but the compact user
    # projection needs its intolerance parameter ids to read the verified INCI.
    profile_input: Mapping | None = None
    # Kept last for backward-compatible positional construction.
    comedogenicity: dict = field(default_factory=dict)

    @property
    def is_final(self) -> bool:
        return self.analysis.is_final

    def user_report(self) -> dict:
        """The compact, non-technical result rendered in the product drawer.

        Internal statuses, provider errors, the historical average and
        source-quote audit material stay in ``snapshot``/``analysis``/``evidence``.
        This projection contains the overall verdict, the checklist with
        explicit neutral/unknown states, and one source list.
        """
        personal = []
        seen: set[str] = set()
        comedo = dict(self.comedogenicity or {})
        comedo_names = comedo_ingredient_names(comedo)
        product_context = dict(self.knowledge.product) if self.knowledge is not None else dict(self.product)
        for row in self.snapshot.get("parameters") or []:
            if (
                not row.get("included")
                or row.get("value") is None
                or str(row.get("status") or "") in {
                    "pending",
                    "not_applicable",
                    "insufficient_evidence",
                    "stale",
                }
            ):
                continue
            parameter_id = str(row.get("parameter_id") or "")
            evidence_rows = list(self.evidence.get(parameter_id) or [])
            intolerance = _intolerance_status(parameter_id, self.composition)
            risk_kind = _risk_kind(evidence_rows) if not intolerance else ""
            verdict = _item_verdict(
                parameter_id,
                row.get("value"),
                intolerance,
                evidence_rows,
            )
            scope = goal_scope(parameter_id, product_context)
            scope_note = goal_scope_note(scope, product_context)
            # A goal outside the product's function is not a user-facing
            # checklist item unless there is a confirmed risk. Do not fill the
            # report with tasks the product was never meant to solve.
            if (
                _section(parameter_id) == "goal"
                and scope == "not_intended"
                and not risk_kind
            ):
                continue
            # An unknown category is not allowed to turn an LLM score into a
            # positive claim either.
            if scope in {"not_intended", "unknown"} and verdict == "positive":
                verdict = "neutral"
            explanation = (
                _evidence_explanation(evidence_rows, verdict)
                or _short_explanation(row.get("reason") or row.get("summary"))
            )
            if scope == "not_intended" and verdict == "neutral" and scope_note:
                explanation = scope_note
            item = {
                "parameter_id": parameter_id,
                "label": str(row.get("label") or ""),
                "score": row.get("value"),
                "reason": explanation,
                "explanation": explanation,
                "evidence": evidence_rows,
                "section": _section(parameter_id),
                "verdict": verdict,
                "verdict_label": _verdict_label(
                    parameter_id,
                    verdict,
                    intolerance,
                    risk_kind,
                    goal_scope=scope,
                ),
                "display_text": _display_text(
                    parameter_id,
                    str(row.get("label") or ""),
                    verdict,
                    intolerance=intolerance,
                    risk_kind=risk_kind,
                    goal_scope=scope,
                ),
                "verdict_icon": _VERDICT_ICONS[verdict],
            }
            if scope and scope != "unknown":
                item["goal_scope"] = scope
                item["scope_note"] = scope_note
            if risk_kind:
                item["risk_kind"] = risk_kind
            if verdict == "caution":
                risk_text, recommendation = _caution_copy(parameter_id, evidence_rows)
                item["status_label"] = "С осторожностью"
                item["cause"] = explanation or _display_text(
                    parameter_id,
                    str(row.get("label") or ""),
                    "caution",
                    risk_kind=risk_kind,
                    goal_scope=scope,
                )
                item["risk"] = risk_text
                item["recommendation"] = recommendation
            if intolerance is not None:
                item["intolerance"] = intolerance
            personal.append(item)
            seen.add(parameter_id)

        # INCI questions are deterministic: use the already verified composition
        # even when an old snapshot has no LLM evaluation for that parameter.
        if self.profile_input:
            for parameter in resolve_parameters(self.profile_input).parameters:
                if parameter.section != "intolerance" or parameter.id in seen:
                    continue
                checked = check_intolerance(parameter, self.composition)
                if checked is None or not checked.verified:
                    continue
                intolerance = _intolerance_status(parameter.id, self.composition)
                verdict = _item_verdict(
                    parameter.id,
                    100.0 if checked.status == NOT_LISTED else 0.0,
                    intolerance,
                )
                explanation = _short_explanation(checked.reason)
                personal.append({
                    "parameter_id": parameter.id,
                    "label": parameter.label,
                    "score": 100.0 if checked.status == NOT_LISTED else 0.0,
                    "reason": explanation,
                    "explanation": explanation,
                    "evidence": [],
                    "section": "intolerance",
                    "verdict": verdict,
                    "verdict_label": _verdict_label(parameter.id, verdict, intolerance),
                    "display_text": _display_text(
                        parameter.id, parameter.label, verdict, intolerance=intolerance
                    ),
                    "verdict_icon": _VERDICT_ICONS[verdict],
                    "derived": True,
                    "intolerance": intolerance,
                })
                seen.add(parameter.id)

        # Unknown is not a positive result: show it explicitly with a neutral
        # dash, but never invent a score or a check.
        for gap in self.analysis.gaps:
            parameter_id = str(gap.parameter_id)
            if parameter_id in seen:
                continue
            personal.append({
                "parameter_id": parameter_id,
                "label": _gap_label(parameter_id),
                "score": None,
                "reason": gap.detail or "Нет подтверждённых данных для оценки.",
                "evidence": [],
                "section": _section(parameter_id),
                "verdict": "unknown",
                "verdict_label": "Не удалось определить",
                "display_text": _display_text(
                    parameter_id,
                    _gap_label(parameter_id),
                    "unknown",
                ),
                "verdict_icon": _VERDICT_ICONS["unknown"],
            })
            seen.add(parameter_id)

        verdict_order = {
            "positive": 0,
            "negative": 1,
            "caution": 2,
            "neutral": 3,
            "unknown": 4,
        }
        personal.sort(key=lambda row: verdict_order.get(str(row.get("verdict")), 9))
        # The dedicated comedogenicity block owns its ingredient names/ratings.
        # Remove only repeated comedogenicity clauses from other user-facing
        # fields; independent irritation/allergy/barrier risks remain intact.
        if comedo_names:
            for item in personal:
                scrub_comedo_fields(item, comedo_names)
        primary = public_primary_function(self.primary_function)
        primary["reason"] = _short_explanation(primary.get("reason"))
        if comedo_names:
            scrub_comedo_fields(primary, comedo_names, fields=("reason", "purpose"))
        name = " ".join(str(self.product.get("name") or "").replace("\n", " ").split())
        overall = _overall_verdict(personal, score=self.snapshot.get("total"))
        if comedo_names:
            overall["summary"] = str(
                scrub_comedo_fields(dict(overall), comedo_names, fields=("summary",)).get("summary") or ""
            )
        report = {
            "product_name": name,
            "primary_function": primary,
            "overall": overall,
            "personal_compatibility": personal,
            "sources": _source_urls(personal, primary),
        }
        # A product-level pseudo-status is never shown. The block exists only
        # when at least one ingredient has a confirmed rating in 1..5; low INCI
        # coverage does not hide that known evidence.
        has_flagged = bool(comedo.get("ingredients")) or bool(comedo.get("max_rating"))
        if comedo and comedo.get("applicable", True) and comedo.get("status") == "assessed" and has_flagged:
            report["comedogenicity"] = comedo
        return report

    def as_dict(self) -> dict:
        payload = {
            "product": dict(self.product),
            "composition": dict(self.composition),
            "composition_state": assess_composition(
                self.product,
                self.composition,
                status=str(self.composition.get("status") or ""),
            ).as_dict(),
            "snapshot": self.snapshot,
            "analysis": self.analysis.as_dict(),
            "evidence": self.evidence,
            "primary_function": self.primary_function,
            "comedogenicity": self.comedogenicity,
            "user_report": self.user_report(),
            "timings": self.timings,
        }
        if self.plan is not None:
            payload["plan"] = {
                "needed": list(self.plan.needed),
                "stale": list(self.plan.stale),
                "gaps": [gap.as_dict() for gap in self.plan.gaps],
                "blocked": self.plan.blocked,
                "notes": list(self.plan.notes),
            }
        if self.research is not None:
            payload["research"] = {
                "researched": list(self.research.researched),
                "insufficient": list(self.research.insufficient),
                "not_applicable": list(self.research.not_applicable),
                "failed": list(self.research.failed),
                "skipped": list(self.research.skipped),
                "exhausted": list(self.research.exhausted),
                "deferred": list(self.research.deferred),
                "documents_fetched": self.research.documents_fetched,
                "documents_reused": self.research.documents_reused,
                "cost_usd": self.research.cost_usd,
                "tokens_in": self.research.tokens_in,
                "tokens_out": self.research.tokens_out,
                "blocked": self.research.blocked,
                "notes": list(self.research.notes),
            }
        return payload


class AnalysisService:
    """Runs the full analysis mechanic for one product composition."""

    def __init__(
        self,
        store: EvaluationStore,
        *,
        provider: ResearchProvider | None = None,
        fetcher=None,
        search: SourceSearch | None = None,
        rules: RuleSet | None = None,
        method_version: str = DEFAULT_METHOD_VERSION,
        max_age_days: int | None = None,
        review_after_days: int | None = DEFAULT_REVIEW_AFTER_DAYS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        max_documents: int = MAX_DOCUMENTS_PER_SESSION,
        max_cost_per_job: float = 0.50,
        max_cost_per_run: float = 5.00,
        max_concurrency: int = 4,
        allow_synthetic_evidence: bool = False,
    ) -> None:
        self.store = store
        self.provider = provider
        self.fetcher = fetcher
        self.search = search
        self.rules = rules or get_rules()
        self.method_version = method_version
        self.max_age_days = max_age_days
        self.review_after_days = review_after_days
        self.max_attempts = max_attempts
        self.max_documents = max_documents
        self.max_cost_per_job = max_cost_per_job
        self.max_cost_per_run = max_cost_per_run
        self.max_concurrency = max(1, min(int(max_concurrency), 8))
        self.allow_synthetic_evidence = allow_synthetic_evidence
        self._evaluation = EvaluationService(
            store,
            rules=self.rules,
            method_version=method_version,
            max_age_days=max_age_days,
            review_after_days=review_after_days,
            # The user-facing analysis has a primary-function score and
            # independent personal parameters; it must not calculate a mean
            # across heterogeneous questionnaire parameters.
            aggregate=False,
        )

    # -- public API ----------------------------------------------------------
    def analyze(
        self,
        *,
        product: Mapping[str, Any],
        composition: Mapping[str, Any],
        profile: Mapping[str, Any] | None,
        source_urls: Sequence[str] = (),
        allow_research: bool = True,
        process: bool = True,
        user_id: int | None = None,
        now: datetime | None = None,
        knowledge: ProductKnowledge | None = None,
        timer: StageTimer | None = None,
    ) -> AnalysisReport:
        """Scan all parameters, research the gaps, and assemble an honest report."""
        product_id = product.get("id")
        if product_id is None:
            raise AnalysisUnavailable("product.id is required")
        timer = timer or StageTimer(product_id=int(product_id), allow_research=allow_research)

        with timer.stage("composition"):
            record = self._evaluation.ensure_composition(int(product_id), composition)
        # An existing record may have been registered earlier as unverified (e.g.
        # by /status). An explicit verification must upgrade it, otherwise the
        # analysed composition stays blocked forever.
        if composition.get("verified_at") and str(record.get("status") or "") != COMPOSITION_ACTIVE:
            record = self.store.verify_composition(
                int(record["id"]),
                str(composition["verified_at"]),
                str(composition.get("source") or ""),
            )
        composition_hash = str(record["composition_hash"])
        blocked = str(record.get("status") or "") != COMPOSITION_ACTIVE

        research: ResearchRunReport | None = None
        plan: ResearchPlan | None = None

        if not blocked:
            service = self._research_service()
            with timer.stage("plan"):
                plan = service.plan(
                    product=product,
                    composition=composition,
                    profile=profile,
                    now=now,
                    source_urls=source_urls,
                    composition_record=record,
                )
            blocked = plan.blocked
            if plan.needed and allow_research:
                if self.provider is None:
                    raise AnalysisUnavailable(
                        "провайдер исследования не настроен: анализ недостающих "
                        "параметров невозможен"
                    )
                with timer.stage("research"):
                    research = service.research_missing(
                        product=product,
                        composition=composition,
                        profile=profile,
                        process=process,
                        now=now,
                        source_urls=source_urls,
                        plan=plan,
                    )
                blocked = research.blocked or blocked

        with timer.stage("snapshot"):
            built = self._evaluation.build(
                product=product,
                composition=composition,
                profile=profile,
                now=now,
                user_id=user_id,
                research_summary=research.summary() if research is not None else None,
                blocked=blocked,
                composition_record=record,
                stored_evaluations=plan.current if plan is not None and research is None else None,
            )

        extra_notes = list(knowledge.notes) if knowledge is not None else []
        state = built.analysis
        if extra_notes:
            state = analysis_state(
                scan=built.scan,
                research=research.summary() if research is not None else None,
                blocked=blocked,
                extra_notes=extra_notes,
            )

        logger.info(
            "[EVALUATION] product=%s composition=%s status=%s final=%s assessed=%d "
            "gaps=%d failed=%d docs_fetched=%d docs_reused=%d research=%s",
            product_id,
            composition_hash[:12],
            state.status,
            state.is_final,
            len(state.assessed_parameters),
            len(state.gaps),
            len(state.failed_parameters),
            state.documents_fetched,
            state.documents_reused,
            bool(research),
        )
        if state.gaps:
            logger.info(
                "[EVALUATION] gaps: %s",
                ", ".join(f"{gap.parameter_id}:{gap.reason}" for gap in state.gaps),
            )

        parameter_ids = (*state.assessed_parameters, *state.not_applicable_parameters)
        with timer.stage("evidence"):
            if parameter_ids and hasattr(self.store, "evidence_for_many"):
                evidence_by_parameter = self.store.evidence_for_many(
                    int(record["id"]), parameter_ids
                )
                evidence_by_parameter = {
                    parameter_id: [
                        row
                        for row in rows
                        if str(row.get("verification") or "") == "confirmed"
                    ]
                    for parameter_id, rows in evidence_by_parameter.items()
                }
                evidence_by_parameter = {
                    parameter_id: rows
                    for parameter_id, rows in evidence_by_parameter.items()
                    if rows
                }
            else:
                evidence_by_parameter = {}
                for parameter_id in parameter_ids:
                    rows = self.store.evidence_for(int(record["id"]), parameter_id)
                    confirmed = [
                        row
                        for row in rows
                        if str(row.get("verification") or "") == "confirmed"
                    ]
                    if confirmed:
                        evidence_by_parameter[parameter_id] = confirmed

        with timer.stage("primary_function"):
            primary_function = build_primary_function(
                product,
                {**record, "inci_raw": record.get("inci_raw") or composition.get("inci_raw") or ""},
                composition_status=str(record.get("status") or ""),
            )
        timings = timer.log(
            logger,
            assessed=len(state.assessed_parameters),
            gaps=len(state.gaps),
            failed=len(state.failed_parameters),
            needed=len(plan.needed) if plan is not None else 0,
            researched=len(research.researched) if research is not None else 0,
        )
        return AnalysisReport(
            product={
                "id": int(product_id),
                "name": str(product.get("name") or ""),
            },
            composition={
                "composition_hash": composition_hash,
                "inci_raw": record.get("inci_raw") or "",
                "source": record.get("source") or "",
                "verified_at": str(record.get("verified_at") or ""),
                "status": record.get("status") or "",
            },
            snapshot=built.snapshot,
            analysis=state,
            research=research,
            plan=plan,
            knowledge=knowledge,
            evidence=evidence_by_parameter,
            primary_function=primary_function,
            comedogenicity=assess_comedogenicity(
                product,
                {**record, "inci_raw": record.get("inci_raw") or composition.get("inci_raw") or ""},
                composition_status=str(record.get("status") or ""),
            ),
            timings=timings,
            profile_input=profile,
        )


    def saved_report(
        self,
        *,
        product_id: int,
        profile: Mapping[str, Any] | None,
        user_id: int | None,
    ) -> AnalysisReport | None:
        """Read a complete, current snapshot without research or a new write.

        Reopening a product must not repeat the first analysis. This method only
        accepts a verified snapshot whose saved parameter values still match the
        current evaluations; stale/incomplete history falls back to ``None`` and
        the regular (reuse-first) analysis path remains available.
        """
        if user_id is None or not hasattr(self.store, "latest_snapshot"):
            return None
        try:
            # Saved-report reads do not need ingredient seed URLs; skip that
            # extra knowledge lookup on every drawer open.
            knowledge = load_product_knowledge(
                int(product_id), include_ingredient_sources=False
            )
            record = self.store.get_composition(
                int(product_id), knowledge.composition_hash
            )
        except (ProductNotFound, KnowledgeUnavailable):
            return None
        except Exception:  # noqa: BLE001 - a saved read must not break the drawer
            return None
        if record is None or str(record.get("status") or "") != COMPOSITION_ACTIVE:
            return None

        latest = self.store.latest_snapshot(
            product_id=int(product_id),
            composition_hash=str(record["composition_hash"]),
            user_id=int(user_id),
            profile_fingerprint=profile_fingerprint(profile),
        )
        if latest is None or not verify_snapshot(latest):
            return None
        # An older snapshot may be marked incomplete only because an INCI
        # parameter was not evaluated. Re-scan with the verified composition:
        # deterministic INCI answers close such gaps without a new analysis.
        stored = self.store.current_evaluations(
            int(record["id"]), self.method_version
        )
        scan = scan_parameters(
            evaluations=stored,
            profile=profile,
            composition_hash=str(record["composition_hash"]),
            method_version=self.method_version,
            composition=record,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
        )
        if scan.needed or scan.stale:
            return None
        current_values = {
            item.parameter_id: item.value
            for item in scan.current
            if item.status == "assessed" and item.value is not None
        }
        saved_values = {
            str(row.get("parameter_id") or ""): row.get("value")
            for row in latest.get("parameters") or []
            if row.get("included") and row.get("value") is not None
        }
        if set(current_values) != set(saved_values):
            return None
        for parameter_id, value in current_values.items():
            try:
                if abs(float(value) - float(saved_values[parameter_id])) > 1e-9:
                    return None
            except (TypeError, ValueError):
                return None

        parameter_ids = tuple(saved_values)
        evidence: dict[str, list[dict]] = {}
        if parameter_ids:
            try:
                rows = self.store.evidence_for_many(int(record["id"]), parameter_ids)
            except AttributeError:
                rows = {
                    parameter_id: self.store.evidence_for(
                        int(record["id"]), parameter_id
                    )
                    for parameter_id in parameter_ids
                }
            for parameter_id, items in rows.items():
                confirmed = [
                    row
                    for row in items
                    if str(row.get("verification") or "") == "confirmed"
                ]
                if confirmed:
                    evidence[parameter_id] = confirmed
        primary = build_primary_function(
            knowledge.product,
            {**record, "inci_raw": record.get("inci_raw") or ""},
            composition_status=str(record.get("status") or ""),
        )
        state = analysis_state(scan=scan, blocked=False)
        return AnalysisReport(
            product=knowledge.product,
            composition={
                "composition_hash": str(record["composition_hash"]),
                "inci_raw": record.get("inci_raw") or "",
                "source": record.get("source") or "",
                "verified_at": str(record.get("verified_at") or ""),
                "status": record.get("status") or "",
            },
            snapshot=latest,
            analysis=state,
            knowledge=knowledge,
            evidence=evidence,
            primary_function=primary,
            comedogenicity=assess_comedogenicity(
                knowledge.product,
                {**record, "inci_raw": record.get("inci_raw") or ""},
                composition_status=str(record.get("status") or ""),
            ),
            timings={"saved": True},
            profile_input=profile,
        )

    def analyze_product(
        self,
        product_id: int,
        *,
        profile: Mapping[str, Any] | None,
        verified_at: str | None = None,
        composition_source: str | None = None,
        extra_sources: Sequence[str] = (),
        allow_research: bool = True,
        process: bool = True,
        user_id: int | None = None,
        now: datetime | None = None,
        product_loader: Callable[[int], Mapping | None] | None = None,
        repository=None,
        verify_catalog_inci: bool = False,
    ) -> AnalysisReport:
        """Analyze an existing Aidermy product (catalog + INCI + known sources).

        ``verify_catalog_inci`` is an explicit (admin) decision to treat the
        catalog INCI as the confirmed formula. It is refused when the record has
        no reliable INCI or no source URL, and it is recorded with its basis.
        """
        timer = StageTimer(product_id=int(product_id), allow_research=allow_research)
        try:
            with timer.stage("knowledge"):
                knowledge = load_product_knowledge(
                    product_id,
                    product_loader=product_loader,
                    repository=repository,
                    verified_at=verified_at,
                    composition_source=composition_source,
                    extra_sources=extra_sources,
                )
        except ProductNotFound:
            raise
        except KnowledgeUnavailable as exc:
            raise AnalysisUnavailable(str(exc)) from exc

        notes = list(knowledge.notes)
        composition = dict(knowledge.composition)
        readiness = assess_composition(knowledge.product, composition)
        if readiness.auto_verify and not composition.get("verified_at"):
            stamp = (now or datetime.now(timezone.utc)).isoformat()
            composition["verified_at"] = stamp
            notes.append(
                f"{readiness.message} Проверка происхождения зафиксирована в {stamp}."
            )
        if verify_catalog_inci and not composition.get("verified_at"):
            source = str(composition.get("source") or "")
            if not knowledge.product.get("has_reliable_inci"):
                raise AnalysisUnavailable(
                    "состав продукта нельзя подтвердить автоматически: в каталоге нет "
                    "надёжного INCI (нужно минимум два ингредиента)"
                )
            if not source.startswith(("http://", "https://")):
                raise AnalysisUnavailable(
                    "состав продукта нельзя подтвердить автоматически: у карточки нет "
                    "ссылки-источника состава"
                )
            stamp = (now or datetime.now(timezone.utc)).isoformat()
            composition["verified_at"] = stamp
            notes.append(
                f"Состав подтверждён администратором по данным каталога Aidermy "
                f"(источник: {source}) в {stamp}."
            )
        knowledge = ProductKnowledge(
            product=dict(knowledge.product),
            composition=composition,
            source_urls=knowledge.source_urls,
            notes=tuple(notes),
        )
        return self.analyze(
            product=knowledge.product,
            composition=knowledge.composition,
            profile=profile,
            source_urls=knowledge.source_urls,
            allow_research=allow_research,
            process=process,
            user_id=user_id,
            now=now,
            knowledge=knowledge,
            timer=timer,
        )

    # -- internals -----------------------------------------------------------
    def _research_service(self) -> ResearchService:
        return ResearchService(
            self.store,
            self.provider,
            method_version=self.method_version,
            max_attempts=self.max_attempts,
            max_age_days=self.max_age_days,
            review_after_days=self.review_after_days,
            allow_synthetic_evidence=self.allow_synthetic_evidence,
            fetcher=self.fetcher,
            search=self.search,
            max_documents=self.max_documents,
            max_cost_per_job=self.max_cost_per_job,
            max_cost_per_run=self.max_cost_per_run,
            max_concurrency=self.max_concurrency,
        )

