import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.face_taxonomy import (
    FACE_TAXONOMY, MAIN_FACE_TAXONOMY, EXCLUDED_FACE_CATEGORIES,
    face_category_titles, main_face_category_titles,
)


class FaceTaxonomyExclusionTests(unittest.TestCase):
    def test_lips_excluded_from_main_taxonomy(self):
        self.assertIn("Уход за губами", EXCLUDED_FACE_CATEGORIES)
        self.assertNotIn("Уход за губами", main_face_category_titles())
        self.assertEqual(len(main_face_category_titles()), len(face_category_titles()) - 1)
        self.assertEqual(len(MAIN_FACE_TAXONOMY), 9)

    def test_main_is_subset_of_full(self):
        self.assertTrue(set(main_face_category_titles()).issubset(set(face_category_titles())))

    def test_catalog_query_excludes_lips(self):
        from app.postgres_catalog import _build_catalog_query
        select_sql, params, count_sql, count_params = _build_catalog_query()
        # базовый фильтр — IN по 9 основным категориям; губ среди параметров нет
        self.assertIn("catalog_category IN (", select_sql)
        self.assertNotIn("Уход за губами", params)


if __name__ == "__main__":
    unittest.main()
