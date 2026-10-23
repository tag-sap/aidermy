"""Questionnaire ↔ implementation parity and knowledge-reuse scenarios.

Nothing here touches the network: the questionnaire is read from the production
frontend source, research uses ``FakeResearchProvider`` only.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.evaluation import (
    PARAMETERS,
    FakeResearchProvider,
    ResearchService,
    assess,
    build_snapshot,
    candidate,
    evaluate,
    get_rules,
    ok,
    resolve_parameters,
    resolve_relevance,
    validate_registry,
)
from app.evaluation.contracts import RuleSet
from app.evaluation.service import DEFAULT_METHOD_VERSION, EvaluationService
from app.evaluation.store import InMemoryStore

DATA_TS = (
    Path(__file__).resolve().parents[2]
    / "figma-make-preview"
    / "src"
    / "data.ts"
)
PRODUCT = {"id": 11, "name": "Barrier Cream"}
HASH_A = "a" * 64
HASH_B = "b" * 64
COMPOSITION = {"composition_hash": HASH_A, "inci_raw": "Aqua, Glycerin, Ceramide NP",
               "source": "catalog", "verified_at": "2026-10-20"}

PAYLOAD = {
    "skin_type": "dry",
    "age": "25_35",
    "concerns": ["Сухость / обезвоженность"],
    "allergies": ["Отдушки"],
    "goals": ["hydration"],
    "structured": {
        "therapy": [{"id": "tretinoin", "active": True}],
        "procedures": [{"id": "recent_laser", "period": "<7"}],
    },
}
PAYLOAD_IDS = (
    "goal:hydration",
    "intolerance:fragrance_intolerance",
    "problem:dryness",
    "procedure:recent_laser@<7",
    "skin_type:dry",
    "therapy:tretinoin",
)


def _export_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for match in re.finditer(r"export const (\w+):[^=]+= \[", text):
        depth, index = 1, match.end()
        while index < len(text) and depth:
            if text[index] == "[":
                depth += 1
            elif text[index] == "]":
                depth -= 1
            index += 1
        blocks[match.group(1)] = text[match.end(): index - 1]
    return blocks


_OPTION_RE = re.compile(r'\{ id: "([^"]+)", label: "([^"]+)"([^}]*)\}')


def _options(block: str) -> list[tuple[str, str]]:
    items = []
    for match in _OPTION_RE.finditer(block):
        if "type:" in match.group(3):  # a branch question, not an answer option
            continue
        items.append((match.group(1), match.group(2)))
    return items


def _cards(block: str) -> list[tuple[str, str]]:
    return re.findall(r'\{ id: "([^"]+)", label: "([^"]+)", shortLabel:', block)


class QuestionnaireParityTests(unittest.TestCase):
    """The catalog must be exactly the questionnaire users fill in."""

    @classmethod
    def setUpClass(cls):
        if not DATA_TS.exists():  # pragma: no cover - repository layout guard
            raise unittest.SkipTest(f"production questionnaire not found: {DATA_TS}")
        cls.blocks = _export_blocks(DATA_TS.read_text(encoding="utf-8"))

    def test_skin_type_and_age_options_match(self):
        from app.evaluation.questionnaire import AGES, SKIN_TYPES

        self.assertEqual(
            _options(self.blocks["SKIN_TYPE_OPTIONS"]),
            [(item.id, item.label) for item in SKIN_TYPES.options],
        )
        self.assertEqual(
            _options(self.blocks["AGE_OPTIONS"]),
            [(item.id, item.label) for item in AGES.options],
        )

    def test_concern_cards_match(self):
        from app.evaluation.questionnaire import PROBLEMS

        self.assertEqual(
            _cards(self.blocks["CONCERN_CARDS"]),
            [(item.id, item.label) for item in PROBLEMS.options],
        )

    def test_therapy_options_match(self):
        from app.evaluation.questionnaire import THERAPIES

        expected = (
            _options(self.blocks["THERAPY_OPTIONS"])
            + _options(self.blocks["RETINOID_OPTIONS"])
            + _options(self.blocks["ACID_OPTIONS"])
        )
        self.assertEqual(
            sorted(expected), sorted((item.id, item.label) for item in THERAPIES.options)
        )

    def test_procedures_and_periods_match(self):
        from app.evaluation.questionnaire import PROCEDURES

        self.assertEqual(
            _options(self.blocks["PROCEDURE_OPTIONS"]),
            [(item.id, item.label) for item in PROCEDURES.options],
        )
        self.assertEqual(
            _options(self.blocks["PROCEDURE_PERIODS"]),
            [(item.id, item.label) for item in PROCEDURES.modifiers],
        )

    def test_intolerances_and_goals_match(self):
        from app.evaluation.questionnaire import GOALS, INTOLERANCES

        self.assertEqual(
            _options(self.blocks["INTOLERANCE_OPTIONS"]),
            [(item.id, item.label) for item in INTOLERANCES.options],
        )
        self.assertEqual(
            _options(self.blocks["GOALS_OPTIONS"]),
            [(item.id, item.label) for item in GOALS.options],
        )

    def test_age_is_the_only_unevaluated_section(self):
        from app.evaluation.questionnaire import SECTIONS

        self.assertEqual(
            [item.id for item in SECTIONS if not item.evaluated], ["age"]
        )

    def test_every_questionnaire_option_has_exactly_one_parameter(self):
        from app.evaluation.parameters import catalog_parameters

        validate_registry()
        ids = [item.id for item in catalog_parameters()]
        self.assertEqual(len(ids), len(set(ids)))
        for parameter in catalog_parameters():
            self.assertIn(parameter.section, {"skin_type", "problem", "therapy",
                                              "procedure", "intolerance", "goal"})
            self.assertTrue(parameter.question)
            self.assertTrue(parameter.definition)
            self.assertEqual(PARAMETERS[parameter.id].label, parameter.label)



def evidence_ok(parameter_id: str, strength: str = "moderate", score: int = 100):
    return ok(
        candidate(
            parameter_id=parameter_id,
            claim=f"{PARAMETERS[parameter_id].label}: подтверждённое свойство",
            quote=f"{parameter_id} confirmed property",
            source_text=f"Formula. {parameter_id} confirmed property. End.",
            strength=strength,
            confidence=1.0,
        ),
        score=score,
    )


class ProfileResolutionTests(unittest.TestCase):
    def test_production_payload_resolves_to_real_questionnaire_parameters(self):
        resolved = resolve_parameters(PAYLOAD)
        self.assertEqual(tuple(item.id for item in resolved.parameters), PAYLOAD_IDS)
        self.assertEqual(resolved.unresolved, ())

    def test_age_does_not_produce_a_parameter(self):
        sections = {item.section for item in resolve_parameters(PAYLOAD).parameters}
        self.assertNotIn("age", sections)

    def test_each_parameter_carries_its_own_question_and_definition(self):
        labels = {item.id: item.label for item in resolve_parameters(PAYLOAD).parameters}
        self.assertEqual(labels["problem:dryness"], "Проблема: «Сухость / обезвоженность»")
        self.assertEqual(labels["therapy:tretinoin"], "Лечение: «Третиноин»")
        self.assertEqual(
            labels["procedure:recent_laser@<7"],
            "Процедура: «Лазер», Последние 7 дней",
        )
        self.assertEqual(labels["goal:hydration"], "Цель: «Увлажнить кожу»")
        parameter = PARAMETERS["problem:dryness"]
        self.assertIn("задаче", parameter.question)
        self.assertIn("увлажнение", parameter.definition)


class KnowledgeReuseTests(unittest.TestCase):
    """The knowledge model is per (product, composition, parameter, method)."""

    def setUp(self):
        self.store = InMemoryStore()
        self.provider = FakeResearchProvider(
            default=lambda request: evidence_ok(request.parameter_id)
        )
        self.service = ResearchService(self.store, self.provider, allow_synthetic_evidence=True)

    def _run(self, profile=PAYLOAD, composition=COMPOSITION, **kwargs):
        return self.service.research_missing(
            product=PRODUCT, composition=composition, profile=profile, **kwargs
        )

    def _composition_id(self, composition_hash=HASH_A) -> int:
        return int(self.store.get_composition(PRODUCT["id"], composition_hash)["id"])

    def _evaluations(self, composition_hash=HASH_A) -> dict:
        return {
            item.parameter_id: item
            for item in self.store.current_evaluations(
                self._composition_id(composition_hash), DEFAULT_METHOD_VERSION
            )
        }

    def test_two_users_with_the_same_answer_share_one_explanation(self):
        self._run(worker_id="user-a")
        first = self._evaluations()
        calls = self.provider.call_count()

        self._run(worker_id="user-b")  # same parameter, composition and method
        second = self._evaluations()

        self.assertEqual(self.provider.call_count(), calls, "second user must not re-research")
        self.assertEqual(set(first), set(second))
        for parameter_id, evaluation in first.items():
            self.assertEqual(evaluation.value, second[parameter_id].value)
            self.assertEqual(evaluation.rationale, second[parameter_id].rationale)
            self.assertEqual(evaluation.evidence_ids, second[parameter_id].evidence_ids)

    def test_second_request_does_not_call_the_provider(self):
        self._run()
        calls = self.provider.call_count()
        report = self._run()
        self.assertEqual(report.researched, ())
        self.assertEqual(self.provider.call_count(), calls)

    def test_new_subparameter_creates_its_own_evaluation(self):
        self._run()
        before = self._evaluations()
        report = self._run(profile=dict(PAYLOAD, goals=["hydration", "brightening"]))
        after = self._evaluations()

        self.assertEqual(report.researched, ("goal:brightening",))
        self.assertEqual(self.provider.call_count("goal:brightening"), 1)
        for parameter_id, evaluation in before.items():
            self.assertEqual(after[parameter_id].value, evaluation.value)
        self.assertIn("goal:brightening", after)

    def test_composition_change_makes_old_evaluations_unusable(self):
        self._run()
        changed = dict(COMPOSITION, composition_hash=HASH_B)
        plan = self.service.plan(product=PRODUCT, composition=changed, profile=PAYLOAD)
        self.assertEqual(plan.needed, PAYLOAD_IDS)
        self.assertEqual(plan.stale, ())
        self._run(composition=changed)
        self.assertEqual(len(self._evaluations(HASH_B)), len(PAYLOAD_IDS))


    def test_method_version_change_triggers_new_research(self):
        self._run()
        newer = ResearchService(self.store, self.provider, method_version="research-2.0.0", allow_synthetic_evidence=True)
        report = newer.research_missing(
            product=PRODUCT, composition=COMPOSITION, profile=PAYLOAD
        )
        self.assertEqual(report.researched, PAYLOAD_IDS)
        self.assertEqual(
            len(self.store.current_evaluations(self._composition_id(), "research-2.0.0")),
            len(PAYLOAD_IDS),
        )
        # Old rows remain as history for the previous method version.
        self.assertEqual(len(self._evaluations()), len(PAYLOAD_IDS))

    def test_different_profiles_do_not_rewrite_shared_knowledge(self):
        self._run()
        before = self.store.evidence_for(self._composition_id(), "problem:dryness")
        calls = self.provider.call_count()

        other = {"skin_type": "oily", "concerns": ["Поры и жирность"], "goals": ["sebum"]}
        self._run(profile=other)

        self.assertEqual(self.provider.call_count(), calls + 3)
        self.assertEqual(
            self.store.evidence_for(self._composition_id(), "problem:dryness"), before
        )
        evaluations = self._evaluations()
        self.assertIn("problem:sebum_pores", evaluations)
        self.assertIn("skin_type:oily", evaluations)
        self.assertIn("goal:sebum", evaluations)


class SnapshotReuseTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.provider = FakeResearchProvider(
            default=lambda request: evidence_ok(request.parameter_id)
        )
        ResearchService(self.store, self.provider, allow_synthetic_evidence=True).research_missing(
            product=PRODUCT, composition=COMPOSITION, profile=PAYLOAD
        )

    def test_two_users_get_identical_results_from_one_knowledge_record(self):
        service = EvaluationService(self.store)
        first = service.build(
            product=PRODUCT, composition=COMPOSITION, profile=PAYLOAD, user_id=1
        )
        second = service.build(
            product=PRODUCT, composition=COMPOSITION, profile=PAYLOAD, user_id=2
        )

        self.assertEqual(
            [(item["parameter_id"], item["value"]) for item in first.snapshot["parameters"]],
            [(item["parameter_id"], item["value"]) for item in second.snapshot["parameters"]],
        )
        self.assertEqual(
            [item["reason"] for item in first.snapshot["parameters"]],
            [item["reason"] for item in second.snapshot["parameters"]],
        )
        self.assertEqual(first.snapshot["total"], second.snapshot["total"])
        self.assertIsNone(first.snapshot["verdict"])
        self.assertNotEqual(first.snapshot["snapshot_id"], second.snapshot["snapshot_id"])

    def test_snapshot_reports_unverified_composition_without_hiding_it(self):
        unverified = {"composition_hash": "c" * 64, "inci_raw": "Aqua"}
        built = EvaluationService(self.store).build(
            product=PRODUCT, composition=unverified, profile=PAYLOAD, user_id=1
        )
        self.assertEqual(built.snapshot["composition"]["status"], "unverified")
        self.assertTrue(
            any("Состав не подтверждён" in text for text in built.snapshot["limitations"])
        )


class CompositionVerificationTests(unittest.TestCase):
    def test_unverified_composition_is_never_researched(self):
        store = InMemoryStore()
        provider = FakeResearchProvider(
            default=lambda request: evidence_ok(request.parameter_id)
        )
        service = ResearchService(store, provider, allow_synthetic_evidence=True)
        unverified = {"composition_hash": HASH_A, "inci_raw": "Aqua"}

        report = service.research_missing(
            product=PRODUCT, composition=unverified, profile=PAYLOAD
        )
        self.assertTrue(report.blocked)
        self.assertEqual(report.researched, ())
        self.assertEqual(provider.call_count(), 0)
        self.assertEqual(store.job_count(), 0)
        record = store.get_composition(PRODUCT["id"], HASH_A)
        self.assertEqual(record["status"], "unverified")

    def test_verified_composition_can_be_researched(self):
        store = InMemoryStore()
        service = ResearchService(
            store,
            FakeResearchProvider(default=lambda request: evidence_ok(request.parameter_id)),
            allow_synthetic_evidence=True,
        )
        inci = "Aqua, Glycerin, Niacinamide"
        record = store.upsert_composition(
            {"product_id": PRODUCT["id"], "composition_hash": HASH_A, "inci_raw": inci}
        )
        store.verify_composition(record["id"], "2026-10-23T00:00:00+00:00", "manual-review")
        report = service.research_missing(
            product=PRODUCT,
            composition={"composition_hash": HASH_A, "inci_raw": inci},
            profile=PAYLOAD,
        )
        self.assertFalse(report.blocked)
        self.assertEqual(report.researched, PAYLOAD_IDS)

    def test_explicitly_verified_payload_is_active_immediately(self):
        store = InMemoryStore()
        record = store.upsert_composition(
            {"product_id": 1, "composition_hash": HASH_A, "verified_at": "2026-10-20"}
        )
        self.assertEqual(record["status"], "active")
        again = store.upsert_composition(
            {"product_id": 1, "composition_hash": HASH_A, "inci_raw": "Aqua"}
        )
        self.assertEqual(again["status"], "active", "verification must not be lost")


class AggregationInvariantTests(unittest.TestCase):
    def test_total_is_plain_arithmetic_mean_of_assessed_parameters(self):
        from app.evaluation import ParameterEvaluation

        profile = {"skin_type": "dry", "concerns": ["dryness"], "goals": ["hydration"]}
        evaluations = [
            ParameterEvaluation("goal:hydration", "assessed", value=100,
                                rationale="подтверждено источниками",
                                evidence_ids=("1",),
                                composition_hash=HASH_A, method_version="m"),
            ParameterEvaluation("problem:dryness", "assessed", value=50,
                                rationale="подтверждено источниками",
                                evidence_ids=("2",),
                                composition_hash=HASH_A, method_version="m"),
            ParameterEvaluation("skin_type:dry", "assessed", value=75,
                                rationale="подтверждено источниками",
                                evidence_ids=("3",),
                                composition_hash=HASH_A, method_version="m"),
        ]
        result = evaluate(profile, evaluations)
        self.assertAlmostEqual(result.total, (100 + 50 + 75) / 3, places=2)
        self.assertAlmostEqual(result.completeness, 1.0, places=6)
        self.assertIsNone(result.verdict, "verdict stays off until calibration")

    def test_insufficient_parameter_is_excluded_not_zeroed(self):
        from app.evaluation import ParameterEvaluation

        profile = {"skin_type": "dry", "concerns": ["dryness"]}
        evaluations = [
            ParameterEvaluation("problem:dryness", "assessed", value=100,
                                rationale="подтверждено источниками",
                                evidence_ids=("1",),
                                composition_hash=HASH_A, method_version="m"),
            ParameterEvaluation("skin_type:dry", "insufficient_evidence",
                                rationale="источников недостаточно",
                                composition_hash=HASH_A, method_version="m",
                                limitations=("источники противоречат",)),
        ]
        result = evaluate(profile, evaluations)
        self.assertEqual(result.total, 100)
        self.assertAlmostEqual(result.completeness, 0.5, places=6)
        self.assertTrue(
            any("источники противоречат" in text for text in result.limitations)
        )
        excluded = next(p for p in result.parameters if p.parameter_id == "skin_type:dry")
        self.assertIsNone(excluded.value)
        self.assertFalse(excluded.included)
        self.assertIsNone(excluded.value)


class ExplanationQualityTests(unittest.TestCase):
    def test_published_explanation_is_bound_to_the_parameter_and_evidence(self):
        store = InMemoryStore()
        provider = FakeResearchProvider(
            {
                "problem:dryness": ok(
                    candidate(
                        parameter_id="problem:dryness",
                        claim="Глицерин удерживает влагу в роговом слое",
                        quote="Glycerin helps keep the skin hydrated",
                        source_text="Formula: Aqua, Glycerin. Glycerin helps keep the skin hydrated.",
                        strength="strong",
                        confidence=1.0,
                    ),
                    score=75,
                    rationale="Источник подтверждает влагоудерживающее свойство состава.",
                )
            }
        )
        report = ResearchService(store, provider, allow_synthetic_evidence=True).research_missing(
            product=PRODUCT,
            composition=COMPOSITION,
            profile={"concerns": ["Сухость / обезвоженность"]},
        )
        self.assertEqual(report.researched, ("problem:dryness",))

        record = store.get_composition(PRODUCT["id"], HASH_A)
        evaluation = store.current_evaluations(
            record["id"], DEFAULT_METHOD_VERSION
        )[0]
        self.assertIn("Проблема: «Сухость / обезвоженность»", evaluation.rationale)
        self.assertIn("Соответствует ли состав задаче", evaluation.rationale)
        self.assertIn("Глицерин удерживает влагу", evaluation.rationale)
        self.assertIn("Glycerin helps keep the skin hydrated", evaluation.rationale)
        self.assertIn("Оценка 75/100", evaluation.rationale)
        self.assertNotIn("лечит", evaluation.rationale.lower())

    def test_fabricated_quote_never_reaches_the_score(self):
        store = InMemoryStore()
        provider = FakeResearchProvider(
            {
                "problem:dryness": ok(
                    candidate(
                        parameter_id="problem:dryness",
                        claim="Средство лечит сухость",
                        quote="clinically proven to cure dryness",
                        source_text="Formula: Aqua, Glycerin.",
                        strength="strong",
                        confidence=1.0,
                    ),
                    score=75,
                    rationale="Источник подтверждает свойство состава.",
                )
            }
        )
        report = ResearchService(store, provider, allow_synthetic_evidence=True).research_missing(
            product=PRODUCT,
            composition=COMPOSITION,
            profile={"concerns": ["Сухость / обезвоженность"]},
        )
        self.assertEqual(report.failed, ("problem:dryness",))

        record = store.get_composition(PRODUCT["id"], HASH_A)
        self.assertEqual(
            store.current_evaluations(record["id"], DEFAULT_METHOD_VERSION), []
        )
        result = evaluate({"concerns": ["Сухость / обезвоженность"]}, [])
        self.assertIsNone(result.total)
        self.assertIsNone(result.parameters[0].value)
        self.assertEqual(result.parameters[0].status, "pending")

        # The rejected candidate is kept for audit, with an explicit reason.
        rows = store.evidence_for(record["id"], "problem:dryness")
        self.assertEqual(rows[0]["verification"], "rejected")
        self.assertIn("не найдена", rows[0]["rejection_reason"])
