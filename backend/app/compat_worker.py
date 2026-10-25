"""Single durable worker for compatibility and individual background checks.

The worker is deliberately small: tasks live in the database, every loop claims
one task atomically, and a restarted process can pick up queued or stale work.
It reuses ``AnalysisService`` and never performs its own scoring.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from . import compat_store
from .compat_service import (
    TaskContextChanged,
    TaskFailed,
    _now,
    _analysis_service_from_app,
    _profile,
    build_compatibility_report,
    charge_saved_report,
    get_or_analyze_product,
    user_profile_changed,
)
from .database import get_product_by_id

logger = logging.getLogger(__name__)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (TaskFailed, TaskContextChanged)):
        return str(exc)
    return "Не удалось завершить проверку. Попробуйте ещё раз."


def _set_status(set_id: int | None, status: str, **fields: Any) -> None:
    if set_id is None:
        return
    current = compat_store.get_set_any(int(set_id))
    if not current or current.get("deleted_at"):
        return
    compat_store.update_set(set_id, status=status, updated_at=_now(), **fields)


def _notify(
    *,
    user_id: int,
    event_key: str,
    kind: str,
    title: str,
    body: str,
    target_type: str,
    target_id: int | None,
) -> None:
    compat_store.create_notification(
        user_id=user_id,
        event_key=event_key,
        kind=kind,
        title=title,
        body=body,
        target_type=target_type,
        target_id=target_id,
    )


class CompatWorker:
    def __init__(
        self,
        service_factory: Callable[[], Any],
        *,
        poll_interval: float = 1.0,
        max_attempts: int = 2,
    ) -> None:
        self._service_factory = service_factory
        self._poll_interval = max(0.2, float(poll_interval))
        self._max_attempts = max(1, int(max_attempts))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._loop, name="aidermy-compat-worker", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:  # noqa: BLE001 - the loop must survive one bad task
                logger.exception("[COMPAT] worker loop failed")
                worked = False
            self._stop.wait(0.1 if worked else self._poll_interval)

    def run_once(self) -> bool:
        """Claim and process one task. Exposed for deterministic tests."""
        compat_store.recover_stale_tasks()
        task = compat_store.claim_next_task()
        if not task:
            return False
        try:
            service = self._service_factory()
        except Exception as exc:  # noqa: BLE001
            self._fail(task, exc)
            return True
        try:
            if task.get("kind") == "individual":
                self._run_individual(task, service)
            elif task.get("kind") == "compatibility":
                self._run_compatibility(task, service)
            else:
                raise TaskFailed("Неизвестный тип фоновой проверки.")
        except Exception as exc:  # noqa: BLE001 - persist a safe user-facing error
            logger.exception("[COMPAT] task %s failed", task.get("id"))
            self._fail(task, exc)
        return True

    def _fail(self, task: dict, exc: Exception) -> None:
        task_id = int(task["id"])
        set_id = task.get("set_id")
        error = _safe_error(exc)
        attempts = int(task.get("attempts") or 0)
        if set_id is not None:
            current = compat_store.get_set_any(int(set_id))
            if not current or current.get("deleted_at"):
                compat_store.update_task(
                    task_id,
                    status="cancelled",
                    active_key=None,
                    updated_at=_now(),
                    finished_at=_now(),
                )
                return
        if attempts >= self._max_attempts and not isinstance(exc, TaskContextChanged):
            error = "Не удалось завершить проверку после нескольких попыток. Попробуйте ещё раз."
        if attempts < self._max_attempts and not isinstance(exc, (TaskContextChanged, TaskFailed)):
            compat_store.update_task(
                task_id,
                status="queued",
                error=error,
                updated_at=_now(),
                finished_at=None,
            )
            _set_status(set_id, "queued", error=error)
            return
        compat_store.update_task(
            task_id,
            status="failed",
            active_key=None,
            error=error,
            updated_at=_now(),
            finished_at=_now(),
        )
        _set_status(set_id, "failed", error=error)
        kind = str(task.get("kind") or "")
        if kind == "compatibility":
            _notify(
                user_id=int(task["user_id"]),
                event_key=f"compat:{int(set_id)}:{task_id}:failed",
                kind="compatibility_failed",
                title="Не удалось проверить совместимость",
                body=error,
                target_type="compatibility_set",
                target_id=int(set_id) if set_id else None,
            )
        elif kind == "individual":
            product_ids = task.get("product_ids") or []
            product_id = int(product_ids[0]) if product_ids else None
            _notify(
                user_id=int(task["user_id"]),
                event_key=f"individual:{user_id}:{task.get('context_key') or task_id}:failed",
                kind="individual_failed",
                title="Не удалось проверить продукт",
                body=error,
                target_type="product",
                target_id=product_id,
            )

    def _run_individual(self, task: dict, service) -> None:
        task_id = int(task["id"])
        user_id = int(task["user_id"])
        product_ids = task.get("product_ids") or []
        if not product_ids:
            raise TaskFailed("В задаче не указан продукт.")
        product_id = int(product_ids[0])
        product = get_product_by_id(product_id)
        if not product:
            raise TaskFailed("Продукт больше недоступен в каталоге.")
        if user_profile_changed(task):
            raise TaskContextChanged(
                "Профиль кожи изменился во время проверки. Запустите проверку заново, "
                "чтобы результат соответствовал актуальному профилю."
            )

        compat_store.update_task(
            task_id, status="running", updated_at=_now()
        )
        report = get_or_analyze_product(
            service,
            product_id=product_id,
            profile=_profile(task),
            user_id=user_id,
        )
        charge_saved_report(user_id=user_id, report=report, profile=_profile(task))
        if user_profile_changed(task):
            raise TaskContextChanged(
                "Профиль кожи изменился во время проверки. Результат не сохранён "
                "как актуальный; запустите проверку заново."
            )
        snapshot = getattr(report, "snapshot", None) or {}
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        compat_store.update_task(
            task_id,
            status="completed",
            active_key=None,
            result_snapshot_id=snapshot_id,
            updated_at=_now(),
            finished_at=_now(),
        )
        _notify(
            user_id=user_id,
            event_key=f"individual:{user_id}:{task.get('context_key') or task_id}:completed",
            kind="individual_completed",
            title="Продукт проверен. Отчёт готов",
            body="Можно открыть карточку продукта и посмотреть персональный результат.",
            target_type="product",
            target_id=product_id,
        )

    def _run_compatibility(self, task: dict, service) -> None:
        task_id = int(task["id"])
        user_id = int(task["user_id"])
        set_id = task.get("set_id")
        if set_id is None:
            raise TaskFailed("Набор для проверки не найден.")
        current_set = compat_store.get_set_any(int(set_id))
        if not current_set or current_set.get("deleted_at"):
            compat_store.update_task(
                task_id,
                status="cancelled",
                active_key=None,
                updated_at=_now(),
                finished_at=_now(),
            )
            return
        if user_profile_changed(task):
            raise TaskContextChanged(
                "Профиль кожи изменился во время проверки набора. Запустите проверку "
                "заново, чтобы отчёт соответствовал актуальному профилю."
            )

        product_ids = [int(pid) for pid in (current_set.get("product_ids") or [])]
        if len(product_ids) < 2 or len(set(product_ids)) != len(product_ids):
            raise TaskFailed("В наборе должно быть минимум два разных продукта.")
        profile = _profile(task)
        products: list[dict] = []
        reports: list[Any] = []

        compat_store.update_task(
            task_id, status="waiting_for_products", updated_at=_now()
        )
        _set_status(int(set_id), "waiting_for_products", error="")
        for product_id in product_ids:
            if user_profile_changed(task):
                raise TaskContextChanged(
                    "Профиль кожи изменился во время проверки набора. Результат "
                    "не сохранён как актуальный; запустите проверку заново."
                )
            current_set = compat_store.get_set_any(int(set_id))
            if not current_set or current_set.get("deleted_at"):
                compat_store.update_task(
                    task_id,
                    status="cancelled",
                    active_key=None,
                    updated_at=_now(),
                    finished_at=_now(),
                )
                return
            product = get_product_by_id(int(product_id))
            if not product:
                raise TaskFailed("Один из продуктов набора больше недоступен в каталоге.")
            report = get_or_analyze_product(
                service,
                product_id=int(product_id),
                profile=profile,
                user_id=user_id,
            )
            charge_saved_report(user_id=user_id, report=report, profile=profile)
            products.append(product)
            reports.append(report)

        compat_store.update_task(
            task_id, status="analyzing_compatibility", updated_at=_now()
        )
        _set_status(int(set_id), "analyzing_compatibility", error="")
        if user_profile_changed(task):
            raise TaskContextChanged(
                "Профиль кожи изменился во время проверки набора. Запустите проверку "
                "заново, чтобы отчёт соответствовал актуальному профилю."
            )
        current_set = compat_store.get_set_any(int(set_id))
        if not current_set or current_set.get("deleted_at"):
            compat_store.update_task(
                task_id,
                status="cancelled",
                active_key=None,
                updated_at=_now(),
                finished_at=_now(),
            )
            return
        if [int(pid) for pid in (current_set.get("product_ids") or [])] != product_ids:
            raise TaskContextChanged(
                "Состав набора изменился во время проверки. Запустите проверку заново."
            )

        report = build_compatibility_report(
            set_name=str(current_set.get("name") or ""),
            products=products,
            reports=reports,
        )
        compat_store.update_set(
            int(set_id),
            status="completed",
            report_json=report,
            checked_at=_now(),
            error="",
            updated_at=_now(),
        )
        compat_store.update_task(
            task_id,
            status="completed",
            active_key=None,
            updated_at=_now(),
            finished_at=_now(),
        )
        _notify(
            user_id=user_id,
            event_key=f"compat:{int(set_id)}:{task_id}:completed",
            kind="compatibility_completed",
            title="Совместимость проверена. Отчёт по набору готов",
            body="Откройте вкладку «Наборы», чтобы посмотреть рекомендации.",
            target_type="compatibility_set",
            target_id=int(set_id),
        )

        return True


def _service_factory_for_app(app):
    def factory():
        return _analysis_service_from_app(app)

    return factory


def ensure_worker(app) -> CompatWorker | None:
    """Start one worker per application process (idempotent)."""
    existing = getattr(app.state, "compat_worker", None)
    if existing is not None:
        return existing
    if str(os.getenv("AIDERMY_COMPAT_WORKER", "1")).strip().lower() in {
        "0", "false", "no", "off"
    }:
        return None
    worker = CompatWorker(_service_factory_for_app(app))
    app.state.compat_worker = worker
    worker.start()
    logger.info("[COMPAT] background worker started")
    return worker

