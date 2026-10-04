"""Regression: report context + semantic tags (positive/negative).

Проверяет, что deterministic breakdown, fragments и их sentiment корректно
формируются и проходят через grounding/round-trip без потери тегов.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import (
    _breakdown_text,
    _fragment_list,
    _ground_fragments,
)
from app.ai_summary import _validated_fragments


class BreakdownTextTests(unittest.TestCase):
    def test_axes_included(self):
        analysis = {
            "dimensions": {"hydration": 0.72, "irritation": 0.05},
            "priorities": {"hydration": 0.4, "irritation": 0.4},
        }
        text = _breakdown_text(analysis)
        self.assertIn("hydration", text)
        self.assertIn("irritation", text)
        self.assertIn("weight", text)

    def test_no_dims_graceful(self):
        self.assertIn("нет данных", _breakdown_text({}))


class FragmentListTests(unittest.TestCase):
    def test_dict_list_normalized(self):
        out = _fragment_list([{"text": "a", "sentiment": "positive"}, {"text": "b", "sentiment": "negative"}])
        self.assertEqual(out, [{"text": "a", "sentiment": "positive"}, {"text": "b", "sentiment": "negative"}])

    def test_plain_string_to_positive(self):
        out = _fragment_list("hello")
        self.assertEqual(out, [{"text": "hello", "sentiment": "positive"}])

    def test_invalid_sentiment_falls_back(self):
        out = _fragment_list([{"text": "x", "sentiment": "neutral"}])
        self.assertEqual(out[0]["sentiment"], "positive")


class ValidatedFragmentsTests(unittest.TestCase):
    def test_only_positive_negative(self):
        out = _validated_fragments({"fragments": [{"text": "ok", "sentiment": "positive"}]}, 50)
        self.assertEqual(out, [{"text": "ok", "sentiment": "positive"}])

    def test_invalid_sentiment_falls_back(self):
        out = _validated_fragments({"fragments": [{"text": "ok", "sentiment": "good"}]}, 80)
        self.assertEqual(out, [{"text": "ok", "sentiment": "positive"}])

    def test_empty_text_dropped(self):
        out = _validated_fragments({"fragments": [{"text": "  ", "sentiment": "positive"}]}, 50)
        self.assertEqual(out, [])


class GroundFragmentsTests(unittest.TestCase):
    def test_sentiment_preserved(self):
        allowed = {"glycerin"}
        out = _ground_fragments(
            [{"text": "Глицерин увлажняет.", "sentiment": "positive"}],
            allowed, False, deterministic=None,
        )
        self.assertEqual(out, [{"text": "Глицерин увлажняет.", "sentiment": "positive"}])

    def test_invalid_sentiment_normalized(self):
        out = _ground_fragments(
            [{"text": "ок", "sentiment": "weird"}], set(), False, deterministic=None
        )
        self.assertEqual(out[0]["sentiment"], "positive")


if __name__ == "__main__":
    unittest.main()
