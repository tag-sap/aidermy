"""Business logic for asynchronous individual and compatibility checks.

The compatibility layer deliberately reuses the existing product analysis
(AnalysisService / Evaluation V2) and the deterministic shelf compatibility
engine. It does not introduce a second score engine or generate a fake score.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from . import compat_store
from .database import get_product_by_id, get_user_profile_updated_at
from .evaluation.snapshot import profile_fingerprint


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


def product_score(report) -> int | None:
    total = (getattr(report, "snapshot", None) or {}).get("total")
    try:
        return int(round(float(total))) if total is not None else None
    except (TypeError, ValueError):
        return None


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
):
    """Reuse a current saved report; otherwise run the existing analysis once."""
    saved = service.saved_report(
        product_id=int(product_id), profile=profile, user_id=int(user_id)
    )
    if saved is not None:
        return saved
    report = service.analyze_product(
        int(product_id),
        profile=profile,
        user_id=int(user_id),
        allow_research=True,
        product_loader=product_loader,
    )
    if not (
        getattr(report, "is_final", False)
        or getattr(getattr(report, "analysis", None), "is_final", False)
    ):
        raise TaskFailed(
            "Не удалось получить итоговый результат: в доступных данных есть пробелы."
        )
    return report



def charge_saved_report(*, user_id: int, report, profile: dict) -> None:
    """Reuse the existing idempotent evaluation billing path from the worker."""
    try:
        from .evaluation.api import _charge_evaluation

        _charge_evaluation(int(user_id), report, profile)
    except Exception:  # noqa: BLE001 - billing must not discard a completed result
        return


def _verdict(score: int | None) -> tuple[str, str]:
    if score is None:
        return "Недостаточно данных", "muted"
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


def build_compatibility_report(
    *,
    set_name: str,
    products: list[dict],
    reports: list[Any],
) -> dict:
    """Build user-facing sections from deterministic shelf results only."""
    from .shelf_compatibility import compute_shelf_compatibility

    entries = []
    for product, report in zip(products, reports):
        score = product_score(report)
        overall = product_overall(report)
        entries.append(
            {
                "product_id": int(product.get("id") or 0),
                "name": _text(product.get("name")).replace("\n", " "),
                "brand": _text(product.get("brand")),
                "score": score,
                "verdict": _text(overall.get("verdict")) or _verdict(score)[0],
                "tone": _text(overall.get("tone")) or _verdict(score)[1],
                "snapshot_id": _text(
                    (getattr(report, "snapshot", None) or {}).get("snapshot_id")
                ),
            }
        )

    result = compute_shelf_compatibility(
        [
            {**dict(product), "score": product_score(report)}
            for product, report in zip(products, reports)
        ]
    )
    score = result.get("score")
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

    cautions = [
        {
            "title": _text(item.get("label")) or "Потенциальное взаимодействие",
            "detail": (
                " ".join(_text(name) for name in item.get("products") or [])
                + " — обоснованное ограничение по действующим правилам Aidermy."
            ).strip(),
        }
        for item in conflicts
    ]
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

    gaps = [
        {
            "title": f"Нет этапа «{step}»",
            "detail": (
                "В выбранном наборе этот этап не представлен. Это наблюдение о составе "
                "набора; добавляйте средство только если оно действительно нужно вашему профилю."
            ),
        }
        for step in missing_steps
        if step in {"Очищение", "Тонизация", "Сыворотки", "Увлажнение", "SPF"}
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
    missing_scores = [entry["name"] for entry in entries if entry["score"] is None]
    if missing_scores:
        limitations.append(
            "Не для всех средств есть итоговая индивидуальная оценка: "
            + ", ".join(missing_scores)
            + "."
        )
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
    if score is None:
        summary = (
            "Для части средств не хватает итоговых данных, поэтому общий вывод "
            "ограничен. Сохранённые индивидуальные результаты не подменялись оценками."
        )
    elif conflicts or irritation or duplicates:
        summary = (
            f"В наборе есть {len(conflicts)} потенциальных сочетаний по правилам Aidermy. "
            "Ниже — что можно оставить, что стоит изменить и где нужна осторожность."
        )
    else:
        summary = (
            "По актуальным индивидуальным результатам и доступным правилам сочетаемости "
            "выраженных конфликтов не найдено. Учитывайте переносимость и режим применения."
        )

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
