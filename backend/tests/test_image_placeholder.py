import asyncio
import unittest

from app.compat_routes import product_image_placeholder, product_thumb


class ImagePlaceholderTests(unittest.TestCase):
    def test_invalid_thumb_path_returns_a_404_svg_placeholder(self):
        response = asyncio.run(product_thumb(path="../private/secret.png"))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.media_type.startswith("image/svg+xml"))
        self.assertEqual(response.headers["x-aidermy-image"], "placeholder")
        self.assertIn(b"<svg", response.body)

    def test_empty_thumb_path_returns_a_404_svg_placeholder(self):
        response = asyncio.run(product_thumb())
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"<svg", response.body)

    def test_explicit_placeholder_is_a_successful_image(self):
        response = asyncio.run(product_image_placeholder())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.media_type.startswith("image/svg+xml"))
        self.assertIn(b"<svg", response.body)


if __name__ == "__main__":
    unittest.main()
