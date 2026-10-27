"""Business logic for asynchronous individual and compatibility checks.

The compatibility layer deliberately reuses the existing product analysis
(AnalysisService / Evaluation V2) and the deterministic shelf compatibility
engine. It does not introduce a second score engine or generate a fake score.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from . import compat_store
from .database import get_product_by_id, get_user_profile_updated_at
from .evaluation.snapshot import profile_fingerprint

logger = logging.getLogger(__name__)


class TaskContextChanged(RuntimeError):
    """The user's profile or the set composition changed while work was running."""


class TaskFailed(RuntimeError):
    """A user-facing task failure with a safe message."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def user_profile_changed(task: dict) -> bool:
    """Compare the profile timestamp captured with the task to the account state."""
    stored = str(task.get("profile_updated_at") or "")
    current = str(get_user_profile_updated_at(int(task["user_id"])) or "")
    return bool(stored and current and stored != current)


def _profile(task: dict) -> dict:
    raw = task.get("profile_json")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def compatibility_cost(product_count: int) -> int:
    """Central compatibility-set price table.

    1 -> 1, 2 -> 1, 3 -> 2, 4 -> 3, 5 -> 3, 6 -> 4, 7 -> 5, 8 -> 5,
    9 -> 6, 10 -> 7 ... The pattern continues for the allowed shelf size.
    """
    count = max(0, int(product_count))
    if count == 0:
        return 0
    return (2 * count + 1) // 3


def product_score(report) -> int | None:
    """Read the saved deterministic score, including older snapshots.

    Some historical snapshots were stored with ``total = null`` while their
    parameter values are complete.  In that case the engine's own documented
    arithmetic mean is used instead of turning the whole set into a null result.
    No value is invented: the fallback only averages included, numeric values
    that are already present in the saved snapshot.
    """
    snapshot = getattr(report, "snapshot", None) or {}
    total = snapshot.get("total")
    if total is not None:
        try:
            return int(round(float(total)))
        except (TypeError, ValueError):
            pass
    values: list[float] = []
    for row in snapshot.get("parameters") or []:
        if not isinstance(row, dict) or not row.get("included"):
            continue
        value = row.get("value")
        if value is None or isinstance(value, bool):
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return int(round(sum(values) / len(values)))


def charge_compatibility_set(*, user_id: int, task_id: int, cost: int) -> bool:
    """Charge the fixed set price once, using the existing balance service."""
    amount = max(0, int(cost))
    if amount == 0:
        return True
    try:
        from .database import change_balance

        balance = change_balance(
            int(user_id),
            -amount,
            "compatibility_check",
            "Проверка совместимости набора",
            idempotency_key=f"compatibility:{int(task_id)}",
        )
        return balance is not None
    except Exception:  # noqa: BLE001 - the worker must never publish a free report
        logger.exception("[COMPAT] compatibility charge failed")
        return False


def product_overall(report) -> dict:
    try:
        return dict((report.user_report() or {}).get("overall") or {})
    except Exception:
        return {}


def _analysis_service_from_app(app):
    from .evaluation.analysis import AnalysisService
    from .evaluation.rules import get_rules
    from .evaluation.runtime import analysis_limits_from_env

    store = getattr(app.state, "evaluation_store", None)
    if store is None:
        raise TaskFailed("Хранилище анализа временно недоступно.")
    return AnalysisService(
        store,
        provider=getattr(app.state, "evaluation_research_provider", None),
        fetcher=getattr(app.state, "evaluation_document_fetcher", None),
        search=getattr(app.state, "evaluation_source_search", None),
        rules=get_rules(getattr(app.state, "evaluation_rule_version", None)),
        method_version=getattr(
            app.state, "evaluation_method_version", "research-1.0.0-draft"
        ),
        allow_synthetic_evidence=bool(
            getattr(app.state, "evaluation_allow_synthetic_evidence", False)
        ),
        **analysis_limits_from_env(),
    )


def get_or_analyze_product(
    service,
    *,
    product_id: int,
    profile: dict,
    user_id: int,
    product_loader=None,
    require_score: bool = True,
):
    """Reuse a current saved report; otherwise run the existing analysis once.

    Individual checks are verdict-first: a valid saved user report does not need
    a numeric legacy score. Compatibility sets still require a numeric score to
    calculate pairwise compatibility, so the worker passes ``require_score``
    explicitly.
    """
    saved = service.saved_report(
        product_id=int(product_id), profile=profile, user_id=int(user_id)
    )
    if saved is not None and (not require_score or product_score(saved) is not None):
        return saved
    report = service.analyze_product(
        int(product_id),
        profile=profile,
        user_id=int(user_id),
        allow_research=True,
        product_loader=product_loader,
    )
    if require_score and product_score(report) is None:
        raise TaskFailed(
            "Не удалось получить числовую индивидуальную оценку продукта. "
            "Повторите проверку позже; отчёт по набору не сформирован."
        )
    return report



def charge_saved_report(*, user_id: int, report, profile: dict) -> None:
    """Reuse the existing idempotent evaluation billing path from the worker."""
    try:
        from .evaluation.api import _charge_evaluation

        _charge_evaluation(int(user_id), report, profile)
    except Exception:  # noqa: BLE001 - billing must not discard a completed result
        return


def _verdict(score: int) -> tuple[str, str]:
    if score >= 80:
        return "Отлично подходит", "good"
    if score >= 60:
        return "Хорошо подходит", "good"
    if score >= 40:
        return "Подходит частично", "neutral"
    if score >= 20:
        return "Слабо подходит", "warn"
    return "Не подходит", "bad"


def _text(value: Any) -> str:
    return str(value or "").strip()


def score_text(value: Any) -> str:
    """Format a numeric score without a floating ``.0`` suffix."""
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Russian plural form for a count used in user-facing report text."""
    number = abs(int(count)) % 100
    if 11 <= number <= 14:
        return many
    tail = number % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def build_compatibility_report(
    *,
    set_name: str,
    products: list[dict],
    reports: list[Any],
) -> dict:
    """Build user-facing sections from deterministic shelf results only."""
    from .shelf_compatibility import compute_shelf_compatibility

    entries = []
    missing_scores: list[str] = []
    for product, report in zip(products, reports):
        score = product_score(report)
        if score is None:
            missing_scores.append(_text(product.get("name")) or f"#{product.get('id')}")
        overall = product_overall(report)
        individual_verdict = _text(overall.get("verdict"))
        if not individual_verdict or "Недостаточно данных" in individual_verdict:
            individual_verdict = _verdict(score)[0] if score is not None else "Оценка недоступна"
        individual_tone = _text(overall.get("tone"))
        if not individual_tone:
            individual_tone = _verdict(score)[1] if score is not None else "neutral"
        entries.append(
            {
                "product_id": int(product.get("id") or 0),
                "name": _text(product.get("name")).replace("\n", " "),
                "brand": _text(product.get("brand")),
                "image": _text(
                    product.get("image_url")
                    or product.get("image")
                ),
                "score": score,
                "verdict": individual_verdict,
                "tone": individual_tone,
                "snapshot_id": _text(
                    (getattr(report, "snapshot", None) or {}).get("snapshot_id")
                ),
            }
        )
    if missing_scores:
        raise TaskFailed(
            "Не удалось получить индивидуальную оценку для: "
            + ", ".join(missing_scores)
            + ". Отчёт по набору не сформирован; повторите проверку."
        )

    result = compute_shelf_compatibility(
        [
            {**dict(product), "score": product_score(report)}
            for product, report in zip(products, reports)
        ]
    )
    score = result.get("score")
    if score is None:
        raise TaskFailed(
            "Не удалось рассчитать совместимость набора по актуальным индивидуальным "
            "результатам. Повторите проверку."
        )
    conflicts = list(result.get("conflicts") or [])
    duplicates = list(result.get("duplicate_actives") or [])
    irritation = list(result.get("irritation") or [])
    coverage = dict(result.get("coverage") or {})
    missing_steps = list(coverage.get("missing") or [])

    conflict_names = {
        _text(name) for item in conflicts for name in (item.get("products") or [])
    }
    keep = [
        {
            "title": entry["name"],
            "detail": (
                f"Индивидуальная проверка: {entry['score']}% — {entry['verdict']}."
                if entry["score"] is not None
                else f"Индивидуальная проверка: {entry['verdict']}."
            ),
        }
        for entry in entries
        if entry["name"] not in conflict_names
        and entry["score"] is not None
        and entry["score"] >= 40
    ]

    changes: list[dict] = []
    for item in conflicts:
        names = " + ".join(_text(name) for name in item.get("products") or [])
        changes.append(
            {
                "title": _text(item.get("label")) or "Сочетание требует изменения",
                "detail": (
                    f"{names}. Правило Aidermy отмечает потенциальное взаимодействие. "
                    "Разведите средства по времени применения или не используйте их "
                    "в одном шаге ухода; при сомнениях сократите частоту."
                ).strip(),
            }
        )
    for item in duplicates:
        active = _text(item.get("ingredient")) or "активный компонент"
        changes.append(
            {
                "title": f"Повтор компонента: {active}",
                "detail": (
                    f"Компонент встречается в {int(item.get('count') or 0)} средствах набора. "
                    "Проверьте, не дублируете ли одну и ту же задачу ухода."
                ),
            }
        )
    for item in irritation:
        active = _text(item.get("ingredient")) or "потенциально раздражающий компонент"
        changes.append(
            {
                "title": f"Нагрузка на кожу: {active}",
                "detail": (
                    f"Компонент встречается в {int(item.get('count') or 0)} средствах. "
                    "Рассмотрите чередование или снижение частоты, если кожа реагирует."
                ),
            }
        )

    cautions = []
    for entry in entries:
        if entry["score"] is not None and entry["score"] < 40 and entry["name"] not in conflict_names:
            cautions.append(
                {
                    "title": f"Индивидуальная оценка: {entry['name']}",
                    "detail": (
                        f"{entry['score']}% — {entry['verdict']}. "
                        "Рассмотрите средство отдельно от остальной схемы или обсудите "
                        "его применение с учётом вашей переносимости."
                    ),
                }
            )

    gap_steps = [
        step
        for step in missing_steps
        if step in {"Очищение", "Тонизация", "Сыворотки", "Увлажнение", "SPF"}
    ]
    gaps = [
        {
            "title": f"Нет этапа «{step}»",
            "detail": (
                "В выбранном наборе этот этап не представлен. Это наблюдение о составе "
                "набора; добавляйте средство только если оно действительно нужно вашему профилю."
            ),
        }
        for step in gap_steps
    ]

    why = []
    scored = [entry for entry in entries if entry["score"] is not None]
    if scored:
        why.append(
            {
                "title": "Индивидуальные оценки",
                "detail": ", ".join(
                    f"{entry['name']} — {entry['score']}%" for entry in scored
                ),
            }
        )
    if conflicts:
        why.append(
            {
                "title": "Проверенные сочетания",
                "detail": "; ".join(
                    _text(item.get("label")) for item in conflicts if item.get("label")
                ),
            }
        )
    if duplicates or irritation:
        why.append(
            {
                "title": "Нагрузка и повтор компонентов",
                "detail": (
                    f"Повторов активов: {len(duplicates)}; "
                    f"компонентов с повышенным вниманием: {len(irritation)}."
                ),
            }
        )
    why.append(
        {
            "title": "Источник расчёта",
            "detail": (
                "Использованы актуальные индивидуальные результаты Score Engine "
                "и детерминированные правила сочетаемости Aidermy."
            ),
        }
    )

    limitations: list[str] = []
    limitations.append(
        "Отчёт не является медицинской рекомендацией и не подтверждает отсутствие "
        "индивидуальной реакции кожи."
    )
    if not conflicts and not duplicates and not irritation:
        limitations.append(
            "По доступным правилам выраженных сочетаний не найдено; это не доказывает "
            "безопасность всех компонентов при любом режиме применения."
        )

    verdict, tone = _verdict(score)
    count = len(entries)
    base = result.get("base")
    summary_parts = [
        f"Набор из {count} {_plural(count, 'средства', 'средств', 'средств')}: "
        f"{score_text(score)}/100 — {verdict}."
    ]
    if isinstance(base, int):
        summary_parts.append(f"Средний индивидуальный балл — {base}%.")
    if conflicts:
        summary_parts.append(
            f"Правила Aidermy отмечают {len(conflicts)} "
            f"{_plural(len(conflicts), 'потенциальное сочетание', 'потенциальных сочетания', 'потенциальных сочетаний')}."
        )
    if duplicates:
        summary_parts.append(
            f"Повторяющихся активов — {len(duplicates)}."
        )
    if irritation:
        summary_parts.append(
            f"Компонентов, требующих повышенного внимания, — {len(irritation)}."
        )
    if gap_steps:
        summary_parts.append(
            "Не представлены этапы: " + ", ".join(gap_steps) + "."
        )
    if not conflicts and not irritation and not duplicates:
        summary_parts.append(
            "Выраженных конфликтов по доступным правилам не найдено."
        )
    summary_parts.append(
        "Ниже — что можно оставить, что стоит изменить и где нужна осторожность."
    )
    summary = " ".join(summary_parts)

    report = {
        "version": "compat-1",
        "set_name": set_name,
        "generated_at": _now(),
        "source": "deterministic",
        "score": score,
        "overall": {"verdict": verdict, "tone": tone, "summary": summary},
        "products": entries,
        "keep": keep,
        "changes": changes,
        "cautions": cautions,
        "gaps": gaps,
        "why": why,
        "limitations": limitations,
        "deterministic": {
            "base": result.get("base"),
            "conflicts": conflicts,
            "duplicate_actives": duplicates,
            "irritation": irritation,
            "coverage": coverage,
        },
    }
    # Do not render empty sections on the client.
    for key in ("keep", "changes", "cautions", "gaps", "why"):
        if not report[key]:
            report.pop(key)
    return report
