"""Guard: Evaluation V2 must stay registered in the real application.

The full app cannot be imported in every environment (it needs the production
public schema), so this test checks the wiring statically and exercises the
router through a minimal app in the other test modules.
"""
from __future__ import annotations

import ast
import pathlib
import unittest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MAIN = BACKEND / "app" / "main.py"
RUNTIME = BACKEND / "app" / "evaluation" / "runtime.py"


def _calls(tree: ast.AST, name: str) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            found.append(node)
        elif isinstance(func, ast.Attribute) and func.attr == name:
            found.append(node)
    return found


class AppWiringTests(unittest.TestCase):
    def test_main_registers_evaluation_v2(self):
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        self.assertTrue(
            _calls(tree, "configure_evaluation"),
            "app.main must call evaluation.runtime.configure_evaluation(app)",
        )

    def test_main_checks_schema_without_applying_migrations(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn("evaluation_schema_status", source)
        for forbidden in ("apply_evaluation_migrations", "run_migrations", "psql"):
            self.assertNotIn(forbidden, source)

    def test_runtime_readiness_covers_every_required_table(self):
        from app.evaluation.runtime import REQUIRED_TABLES

        self.assertIn("source_documents", REQUIRED_TABLES)
        self.assertIn("parameter_evaluations", REQUIRED_TABLES)

    def test_router_is_registered_by_runtime(self):
        runtime = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("setup_evaluation_routes", runtime)
        self.assertIn("build_store_from_env", runtime)


class MigrationDiscoveryTests(unittest.TestCase):
    def test_finds_migrations_in_both_layouts_and_dedupes(self):
        import importlib.util
        import tempfile

        script = BACKEND / "scripts" / "apply_evaluation_migrations.py"
        spec = importlib.util.spec_from_file_location("apply_eval_migrations", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            first = root / "migrations"
            second = root / "sql"
            first.mkdir()
            second.mkdir()
            (first / "20261023_evaluation_v2.sql").write_text("select 1")
            (second / "20261023_evaluation_v2.sql").write_text("select 1")
            (second / "20261024_evaluation_v2_statuses.sql").write_text("select 2")
            module.MIGRATION_DIRS = (first, second)
            names = [path.name for path in module.migration_files()]
            self.assertEqual(
                names,
                [
                    "20261023_evaluation_v2.sql",
                    "20261024_evaluation_v2_statuses.sql",
                ],
            )


if __name__ == "__main__":
    unittest.main()
