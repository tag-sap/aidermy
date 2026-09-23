import unittest

from app.axes import (
    AXES,
    canonicalize_axis,
    canonicalize_effect,
    canonicalize_knowledge_map,
)


class AxesTests(unittest.TestCase):
    def test_six_axes(self):
        self.assertEqual(
            set(AXES),
            {"hydration", "barrier", "irritation", "sensitization", "sebum", "pigmentation"},
        )

    def test_direct_mapping(self):
        self.assertEqual(canonicalize_axis("hydration"), ("hydration", False))
        self.assertEqual(canonicalize_axis("barrier_support"), ("barrier", False))
        self.assertEqual(canonicalize_axis("irritation"), ("irritation", False))
        self.assertEqual(canonicalize_axis("irritation_risk"), ("irritation", False))
        self.assertEqual(canonicalize_axis("sensitization"), ("sensitization", False))

    def test_flip_mapping(self):
        # «успокаивающие»/«контроль»/«осветляющие» legacy-имена инвертируют направление
        self.assertEqual(canonicalize_axis("soothing"), ("irritation", True))
        self.assertEqual(canonicalize_axis("sensitivity"), ("irritation", True))
        self.assertEqual(canonicalize_axis("oil_control"), ("sebum", True))
        self.assertEqual(canonicalize_axis("brightening"), ("pigmentation", True))

    def test_non_axis_mapping(self):
        # Механизмы/формульные свойства — НЕ оси
        self.assertEqual(canonicalize_axis("comedogenicity"), (None, False))
        self.assertEqual(canonicalize_axis("exfoliation"), (None, False))
        self.assertEqual(canonicalize_axis("active_load"), (None, False))
        self.assertEqual(canonicalize_axis("unknown_thing"), (None, False))

    def test_effect_direction_flip(self):
        self.assertEqual(canonicalize_effect("brightening", "positive"), ("pigmentation", "negative"))
        self.assertEqual(canonicalize_effect("soothing", "positive"), ("irritation", "negative"))
        self.assertEqual(canonicalize_effect("barrier_support", "positive"), ("barrier", "positive"))
        self.assertEqual(canonicalize_effect("oil_control", "negative"), ("sebum", "positive"))

    def test_knowledge_map_canonicalization(self):
        km = {
            "niacinamide": {
                "barrier_support": {"direction": "positive", "strength": 0.8, "confidence": 0.9},
                "oil_control": {"direction": "positive", "strength": 0.7, "confidence": 0.8},
                "brightening": {"direction": "positive", "strength": 0.6, "confidence": 0.7},
                "comedogenicity": {"direction": "positive", "strength": 0.5, "confidence": 0.5},
            }
        }
        out = canonicalize_knowledge_map(km)
        n = out["niacinamide"]
        self.assertIn("barrier", n)
        self.assertIn("sebum", n)
        self.assertIn("pigmentation", n)
        self.assertNotIn("comedogenicity", n)  # не ось → отброшен
        self.assertEqual(n["barrier"]["direction"], "positive")
        self.assertEqual(n["sebum"]["direction"], "negative")       # oil_control flip
        self.assertEqual(n["pigmentation"]["direction"], "negative")  # brightening flip
        # трассировка исходного имени
        self.assertEqual(n["sebum"]["_legacy_property"], "oil_control")

    def test_case_insensitive_mapping(self):
        self.assertEqual(canonicalize_axis("Barrier_Support"), ("barrier", False))
        self.assertEqual(canonicalize_axis("OIL CONTROL"), ("sebum", True))


if __name__ == "__main__":
    unittest.main()
