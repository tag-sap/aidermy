import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import (  # noqa: E402
    ensure_user_product_images_table,
    save_user_product_image,
    get_user_product_image,
    get_user_product_images,
)

# Тестовые id вне диапазона реальных пользователей.
USER_A = 990001
USER_B = 990002


class UserProductImageBindingTests(unittest.TestCase):
    def setUp(self):
        ensure_user_product_images_table()
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        from app.database import get_connection, AIDERMY_DB

        conn = get_connection(AIDERMY_DB)
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM user_product_images WHERE user_id IN (?, ?)", (USER_A, USER_B)
        )
        conn.commit()
        conn.close()

    def test_roundtrip_and_user_isolation(self):
        slug = "manual-test-product-slug"
        save_user_product_image(USER_A, slug, "https://example.test/a.jpg")

        self.assertEqual(
            get_user_product_image(USER_A, slug), "https://example.test/a.jpg"
        )
        # Другой пользователь НЕ видит чужое изображение.
        self.assertEqual(get_user_product_image(USER_B, slug), "")
        self.assertEqual(get_user_product_images(USER_B), {})

    def test_replace_keeps_single_row(self):
        slug = "manual-test-product-slug"
        save_user_product_image(USER_A, slug, "https://example.test/old.jpg")
        save_user_product_image(USER_A, slug, "https://example.test/new.jpg")

        self.assertEqual(get_user_product_image(USER_A, slug), "https://example.test/new.jpg")
        self.assertEqual(len(get_user_product_images(USER_A)), 1)

    def test_empty_values_are_ignored(self):
        save_user_product_image(USER_A, "", "https://example.test/a.jpg")
        save_user_product_image(USER_A, "slug", "")
        self.assertEqual(get_user_product_images(USER_A), {})


if __name__ == "__main__":
    unittest.main()
