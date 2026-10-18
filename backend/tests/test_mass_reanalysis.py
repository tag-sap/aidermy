import os
import sys
import unittest
import importlib.util

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
SPEC = importlib.util.spec_from_file_location(
    "mass_reanalyze", os.path.join(SCRIPTS, "mass_reanalyze.py"))
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ParseResponseTests(unittest.TestCase):
    def test_valid_json_array(self):
        self.assertEqual(MOD.parse_response('[{"name": "x", "claims": []}]'),
                         [{"name": "x", "claims": []}])

    def test_markdown_fence(self):
        self.assertIsInstance(MOD.parse_response('```json\n[{"name":"x"}]\n```'), list)

    def test_invalid_json(self):
        self.assertIsNone(MOD.parse_response("not json at all"))

    def test_non_list(self):
        self.assertIsNone(MOD.parse_response('{"name": "x"}'))


class ValidateRecordTests(unittest.TestCase):
    def test_valid_record(self):
        rec = {"name": "glycerin", "claims": [
            {"axis": "hydration", "direction": "positive", "strength": 0.8,
             "confidence": 0.9, "evidence_type": "confirmed"}]}
        v = MOD.validate_record(rec)
        self.assertEqual(len(v["claims"]), 1)

    def test_unknown_axis_dropped(self):
        rec = {"name": "x", "claims": [
            {"axis": "madeup_axis", "direction": "positive", "strength": 0.5, "confidence": 0.5}]}
        v = MOD.validate_record(rec)
        self.assertEqual(v["claims"], [])

    def test_invalid_direction_dropped(self):
        rec = {"name": "x", "claims": [
            {"axis": "hydration", "direction": "sideways", "strength": 0.5, "confidence": 0.5}]}
        v = MOD.validate_record(rec)
        self.assertEqual(v["claims"], [])

    def test_out_of_range_strength_dropped(self):
        rec = {"name": "x", "claims": [
            {"axis": "hydration", "direction": "positive", "strength": 5.0, "confidence": 0.5}]}
        v = MOD.validate_record(rec)
        self.assertEqual(v["claims"], [])

    def test_missing_name(self):
        self.assertIsNone(MOD.validate_record({"claims": []}))


class DecideActionsTests(unittest.TestCase):
    def _ing(self, claims):
        return {"id": 1, "name": "x", "claims": claims}

    def _rec(self, claims):
        return {"claims": claims, "conflicts": [], "uncertainties": [], "recommendation": "keep"}

    def test_agrees_skip(self):
        ing = self._ing([{"property": "hydration", "direction": "positive",
                          "strength": 0.8, "confidence": 0.9, "source_type": "", "source_title": ""}])
        rec = self._rec([{"axis": "hydration", "direction": "positive", "strength": 0.8,
                          "confidence": 0.9, "evidence_type": "confirmed"}])
        actions = MOD.decide_actions(ing, rec)
        self.assertEqual(actions[0]["action"], "skip")

    def test_conflict_needs_review(self):
        ing = self._ing([{"property": "irritation", "direction": "positive",
                          "strength": 0.5, "confidence": 0.8, "source_type": "", "source_title": ""}])
        rec = self._rec([{"axis": "irritation", "direction": "negative", "strength": 0.5,
                          "confidence": 0.5, "evidence_type": "likely"}])
        actions = MOD.decide_actions(ing, rec)
        self.assertEqual(actions[0]["action"], "needs_review")

    def test_new_axis_add(self):
        ing = self._ing([])
        rec = self._rec([{"axis": "hydration", "direction": "positive", "strength": 0.7,
                          "confidence": 0.8, "evidence_type": "confirmed"}])
        actions = MOD.decide_actions(ing, rec)
        self.assertEqual(actions[0]["action"], "add")

    def test_low_confidence_skip(self):
        ing = self._ing([])
        rec = self._rec([{"axis": "hydration", "direction": "positive", "strength": 0.7,
                          "confidence": 0.3, "evidence_type": "confirmed"}])
        actions = MOD.decide_actions(ing, rec)
        self.assertEqual(actions[0]["action"], "skip")


if __name__ == "__main__":
    unittest.main()
