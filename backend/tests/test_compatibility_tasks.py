import os
import tempfile
import unittest
from unittest.mock import patch

from app import compat_store
from app.compat_service import (
    build_compatibility_report,
    charge_compatibility_set,
    compatibility_cost,
)
from app.compat_worker import CompatWorker


class _Analysis:
    is_final = True


class _Report:
    def __init__(self, score: int = 70):
        self.analysis = _Analysis()
        self.snapshot = {"snapshot_id": f"s{score}", "total": score}

    def user_report(self):
        return {"overall": {"verdict": "Хорошо подходит", "tone": "good"}}


class _Service:
    def __init__(self):
        self.calls = []

    def saved_report(self, **kwargs):
        return None

    def analyze_product(self, product_id, **kwargs):
        self.calls.append(int(product_id))
        return _Report(70)


class CompatibilityTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp.close()
        self.addCleanup(lambda: os.path.exists(self.temp.name) and os.unlink(self.temp.name))
        self.patches = [
            patch.object(compat_store, "AIDERMY_DB", self.temp.name),
            patch.object(compat_store, "_SCHEMA_READY", False),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.charge_patch = patch(
            "app.compat_worker.charge_compatibility_set", return_value=True
        )
        self.charge_patch.start()
        self.addCleanup(self.charge_patch.stop)
        compat_store.ensure_schema()

    def _product(self, product_id):
        return {
            "id": product_id,
            "name": f"Product {product_id}",
            "brand": "Brand",
            "ingredients": "Aqua, Glycerin",
            "category": "Увлажнение",
        }

    def _set_and_task(self, product_ids=(1, 2)):
        set_row = compat_store.create_set(
            user_id=1,
            name="Набор",
            product_ids=list(product_ids),
            profile={"skin_type": "dry"},
            profile_updated_at="2026-01-01",
            context_key="ctx",
        )
        task = compat_store.create_task(
            user_id=1,
            kind="compatibility",
            product_ids=list(product_ids),
            profile={"skin_type": "dry"},
            profile_updated_at="2026-01-01",
            context_key="ctx",
            set_id=set_row["id"],
            active_key="active",
        )
        return set_row, task

    def test_task_and_set_are_durable_and_notifications_are_idempotent(self):
        set_row, task = self._set_and_task()
        self.assertEqual(task["status"], "queued")
        self.assertEqual(compat_store.find_task_by_context(1, "compatibility", "ctx")["id"], task["id"])
        self.assertEqual(compat_store.find_active_task_by_key("active")["id"], task["id"])

        first = compat_store.create_notification(
            user_id=1, event_key="e", kind="compatibility_completed",
            title="Готово", body="Отчёт", target_type="compatibility_set",
            target_id=set_row["id"],
        )
        second = compat_store.create_notification(
            user_id=1, event_key="e", kind="compatibility_completed",
            title="Готово", body="Отчёт", target_type="compatibility_set",
            target_id=set_row["id"],
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(compat_store.list_notifications(1)), 1)


    def test_worker_waits_for_individual_reports_then_saves_set_report(self):
        set_row, task = self._set_and_task()
        service = _Service()
        worker = CompatWorker(lambda: service)
        with patch("app.compat_worker.get_product_by_id", side_effect=self._product), \
                patch("app.compat_worker.user_profile_changed", return_value=False):
            self.assertTrue(worker.run_once())

        saved = compat_store.get_set(1, set_row["id"])
        self.assertEqual(saved["status"], "completed")
        report = compat_store._load(saved["report_json"], {})
        self.assertEqual(report["source"], "deterministic")
        self.assertEqual(len(report["products"]), 2)
        self.assertEqual(service.calls, [1, 2])
        self.assertEqual(compat_store.get_task(1, task["id"])["status"], "completed")
        notifications = compat_store.list_notifications(1)
        self.assertEqual(len(notifications), 1)
        self.assertIn("70/100", notifications[0]["body"])
        self.assertIn("Набор из 2", notifications[0]["body"])

    def test_individual_failure_does_not_start_compatibility_report(self):
        set_row, task = self._set_and_task()
        service = _Service()
        with patch("app.compat_worker.get_product_by_id", side_effect=self._product), \
                patch("app.compat_worker.user_profile_changed", return_value=False), \
                patch.object(service, "analyze_product", side_effect=RuntimeError("provider down")):
            self.assertTrue(CompatWorker(lambda: service, max_attempts=1).run_once())
        saved = compat_store.get_set(1, set_row["id"])
        self.assertEqual(saved["status"], "failed")
        self.assertIsNone(saved["report_json"])
        self.assertIn("Не удалось", compat_store.get_task(1, task["id"])["error"])

    def test_deleted_set_cancels_task_and_never_reappears(self):
        set_row, task = self._set_and_task()
        self.assertTrue(compat_store.soft_delete_set(1, set_row["id"]))
        self.assertIsNone(compat_store.get_set(1, set_row["id"]))
        self.assertEqual(compat_store.get_task(1, task["id"])["status"], "cancelled")
        service = _Service()
        with patch("app.compat_worker.get_product_by_id", side_effect=self._product):
            self.assertFalse(CompatWorker(lambda: service).run_once())
        self.assertEqual(service.calls, [])

    def test_profile_change_fails_task_instead_of_publishing_old_result(self):
        set_row, task = self._set_and_task()
        service = _Service()
        with patch("app.compat_worker.get_product_by_id", side_effect=self._product), \
                patch("app.compat_worker.user_profile_changed", return_value=True):
            self.assertTrue(CompatWorker(lambda: service).run_once())
        saved = compat_store.get_set(1, set_row["id"])
        self.assertEqual(saved["status"], "failed")
        self.assertIn("Профиль", saved["error"])
        self.assertIn("Профиль", compat_store.get_task(1, task["id"])["error"])
        self.assertEqual(service.calls, [])

    def test_worker_waits_for_an_existing_individual_task_without_duplicate(self):
        set_row, task = self._set_and_task()
        individual = compat_store.create_task(
            user_id=1,
            kind="individual",
            product_ids=[1],
            profile={"skin_type": "dry"},
            profile_updated_at="2026-01-01",
            context_key="individual-ctx",
            active_key="individual-active",
        )

        class WaitingService(_Service):
            def __init__(self):
                super().__init__()
                self.ready = {}

            def saved_report(self, **kwargs):
                return self.ready.get(int(kwargs["product_id"]))

            def analyze_product(self, product_id, **kwargs):
                self.calls.append(int(product_id))
                report = _Report(70)
                self.ready[int(product_id)] = report
                return report

        service = WaitingService()
        worker = CompatWorker(lambda: service)
        with patch("app.compat_worker.get_product_by_id", side_effect=self._product), \
                patch("app.compat_worker.user_profile_changed", return_value=False):
            self.assertTrue(worker.run_once())

        self.assertEqual(compat_store.get_task(1, individual["id"])["status"], "completed")
        self.assertEqual(compat_store.get_task(1, task["id"])["status"], "completed")
        self.assertEqual(service.calls, [1, 2])

    def test_individual_task_notifies_with_the_exact_product_target(self):
        individual = compat_store.create_task(
            user_id=1,
            kind="individual",
            product_ids=[7],
            profile={"skin_type": "dry"},
            profile_updated_at="2026-01-01",
            context_key="individual-notify",
            active_key="individual-notify-active",
        )
        service = _Service()
        with patch("app.compat_worker.get_product_by_id", side_effect=self._product), \
                patch("app.compat_worker.user_profile_changed", return_value=False), \
                patch("app.compat_worker.charge_saved_report", return_value=None):
            self.assertTrue(CompatWorker(lambda: service).run_once(kind="individual"))

        task = compat_store.get_task(1, individual["id"])
        self.assertEqual(task["status"], "completed")
        notifications = compat_store.list_notifications(1)
        self.assertEqual(len(notifications), 1)
        note = notifications[0]
        self.assertEqual(note["kind"], "individual_completed")
        self.assertEqual(note["target_type"], "product")
        self.assertEqual(note["target_id"], 7)
        self.assertEqual(note["title"], "Продукт проверен. Отчёт готов")
        self.assertIn("Product 7", note["body"])
        self.assertIn("70/100", note["body"])

    def test_numeric_partial_report_is_usable_without_waiting_for_every_gap(self):
        from app.compat_service import get_or_analyze_product

        class PartialReport(_Report):
            def __init__(self):
                super().__init__(70)
                self.analysis = type("PartialAnalysis", (), {"is_final": False})()

        class PartialService(_Service):
            def analyze_product(self, product_id, **kwargs):
                return PartialReport()

        result = get_or_analyze_product(
            PartialService(),
            product_id=7,
            profile={"skin_type": "dry"},
            user_id=1,
        )
        self.assertIsInstance(result, PartialReport)
        self.assertEqual(result.snapshot["total"], 70)

    def test_individual_verdict_report_does_not_require_a_numeric_score(self):
        from app.compat_service import TaskFailed, get_or_analyze_product

        class VerdictReport(_Report):
            def __init__(self):
                self.analysis = type("Analysis", (), {"is_final": False})()
                self.snapshot = {"snapshot_id": "verdict-only", "total": None, "parameters": []}

        class VerdictService(_Service):
            def analyze_product(self, product_id, **kwargs):
                return VerdictReport()

        report = get_or_analyze_product(
            VerdictService(),
            product_id=7,
            profile={"skin_type": "dry"},
            user_id=1,
            require_score=False,
        )
        self.assertIsInstance(report, VerdictReport)
        with self.assertRaises(TaskFailed):
            get_or_analyze_product(
                VerdictService(),
                product_id=7,
                profile={"skin_type": "dry"},
                user_id=1,
                require_score=True,
            )


    def test_report_has_no_empty_sections_and_marks_data_limits(self):
        report = build_compatibility_report(
            set_name="Набор",
            products=[self._product(1), self._product(2)],
            reports=[_Report(70), _Report(70)],
        )
        self.assertEqual(report["score"], 70)
        self.assertTrue(report["products"])
        self.assertIn("limitations", report)
        for key in ("keep", "changes", "cautions", "gaps", "why"):
            if key in report:
                self.assertTrue(report[key])
        self.assertNotIn("Недостаточно данных", str(report["overall"]))
        self.assertIn("Набор из 2 средств", report["overall"]["summary"])
        self.assertIn("70/100", report["overall"]["summary"])
        self.assertIn("Средний индивидуальный балл", report["overall"]["summary"])

    def test_legacy_snapshot_score_falls_back_to_included_parameter_values(self):
        class LegacyReport(_Report):
            def __init__(self):
                self.analysis = _Analysis()
                self.snapshot = {
                    "snapshot_id": "legacy",
                    "total": None,
                    "parameters": [
                        {"included": True, "value": 50.0},
                        {"included": True, "value": 75.0},
                        {"included": False, "value": 0.0},
                    ],
                }

        report = build_compatibility_report(
            set_name="Набор",
            products=[self._product(1), self._product(2)],
            reports=[LegacyReport(), LegacyReport()],
        )
        self.assertEqual(report["score"], 62)
        self.assertTrue(all(item["score"] == 62 for item in report["products"]))
        self.assertTrue(all(item["image"] == "" for item in report["products"]))

    def test_compatibility_cost_matches_the_required_table(self):
        expected = [1, 1, 2, 3, 3, 4, 5, 5, 6, 7]
        self.assertEqual(
            [compatibility_cost(count) for count in range(1, 11)],
            expected,
        )

    def test_compatibility_charge_is_idempotent_by_task_id(self):
        with patch("app.database.change_balance", return_value=9) as change:
            self.assertTrue(charge_compatibility_set(user_id=1, task_id=42, cost=1))
        self.assertEqual(change.call_args.kwargs["idempotency_key"], "compatibility:42")
        self.assertEqual(change.call_args.args[:2], (1, -1))

    def test_compatibility_charge_reports_insufficient_balance(self):
        with patch("app.database.change_balance", return_value=None):
            self.assertFalse(charge_compatibility_set(user_id=1, task_id=42, cost=1))


if __name__ == "__main__":
    unittest.main()
