"""Regression: категории — известная canonical-категория не превращается в «Другое»."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.shelf_service import resolve_shelf_cabinet


class CategoryPipelineTests(unittest.TestCase):
    def test_known_canonical_subcategory_not_other(self):
        # legacy category = Другое, но canonical subcategory = Сыворотки.
        cabinet, category = resolve_shelf_cabinet("Другое", "face", "Some Serum", "Сыворотки")
        self.assertEqual(category, "Сыворотки")

    def test_other_when_no_canonical(self):
        # legacy = Другое и subcategory не специфична -> остаётся Другое (настоящий fallback).
        cabinet, category = resolve_shelf_cabinet("Другое", "face", "Some Product", "Все товары категории")
        self.assertEqual(category, "Другое")

    def test_known_legacy_category_preserved(self):
        # Известная legacy-категория не затирается канонической.
        cabinet, category = resolve_shelf_cabinet("Кремы", "face", "Some Product", "Сыворотки")
        self.assertEqual(category, "Кремы")

    def test_empty_legacy_uses_canonical(self):
        cabinet, category = resolve_shelf_cabinet("", "face", "Some Toner", "Тонизирование")
        self.assertEqual(category, "Тонизирование")


if __name__ == "__main__":
    unittest.main()
