"""Static contracts for URL preview and multi-image photo scanning.

The frontend is built with Vite and has no unit-test runner. These checks read
the real sources so a future refactor cannot silently reintroduce preview
verdicts for unchecked products or remove the camera/gallery/file paths.
"""
from __future__ import annotations

import unittest
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "figma-make-preview" / "src"
APP = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
PHOTO = (FRONTEND / "photo-scan.tsx").read_text(encoding="utf-8")
MAPPING = (FRONTEND / "mapping.ts").read_text(encoding="utf-8")
CSS = (FRONTEND / "index.css").read_text(encoding="utf-8")


class UrlPreviewContractTests(unittest.TestCase):
    def test_unchecked_product_has_no_placeholder_match(self):
        self.assertNotIn(": { score: null }", PHOTO)
        self.assertIn("match: check && score != null", PHOTO)

    def test_preview_requires_a_numeric_saved_score(self):
        self.assertIn("if (score == null) return undefined", MAPPING)
        self.assertIn("const match = score != null", MAPPING)
        self.assertIn('typeof product.match?.score === "number"', APP)

    def test_url_field_has_a_clear_action(self):
        self.assertIn("Очистить ссылку", APP)
        self.assertIn('setUrl("")', APP)
        self.assertIn("scan-link-input__clear", CSS)

    def test_url_import_does_not_auto_run_compatibility(self):
        self.assertIn("совместимость ещё не проверялась", APP)
        self.assertNotIn(
            "const checkRes = await api.checkWithIngredients({ product_name: n, skin_type: skinType, profile, ingredients: pageInci",
            APP,
        )


class PhotoScanContractTests(unittest.TestCase):
    def test_camera_gallery_and_files_share_one_image_list(self):
        self.assertIn("navigator.mediaDevices.getUserMedia", PHOTO)
        self.assertIn("MAX_IMAGES", PHOTO)
        self.assertIn("capturePhoto", PHOTO)
        self.assertIn('accept="image/*" multiple', PHOTO)
        self.assertIn("filesRef.current?.click()", PHOTO)
        self.assertIn("galleryRef.current?.click()", PHOTO)

    def test_all_selected_images_are_sent_to_existing_api(self):
        self.assertIn("front_image: images[0]", PHOTO)
        self.assertIn("back_images: images.slice(1)", PHOTO)
        self.assertIn("images.length >= 1", PHOTO)
        self.assertIn("Выбрать из галереи", PHOTO)
        self.assertIn("Выбрать файлы", PHOTO)

    def test_edited_new_card_is_checked_with_its_edited_inci(self):
        self.assertIn("ingredientsOverride", PHOTO)
        self.assertIn("checkWithIngredients", PHOTO)
        self.assertIn("ingredients.join(\", \")", PHOTO)
        self.assertIn("readOnly={isExistingDraft}", PHOTO)
        self.assertIn("placeholder=\"*заполните в этом поле\"", PHOTO)

    def test_camera_shutter_is_an_icon(self):
        self.assertIn("<CameraGlyph />", PHOTO)
        self.assertNotIn(">Снять</button>", PHOTO)
        self.assertIn(".camera-modal__foot", CSS)

    def test_camera_and_viewer_have_mobile_safe_styles(self):
        for marker in (
            ".camera-backdrop",
            ".camera-modal",
            ".camera-shutter",
            ".scan-viewer",
            "env(safe-area-inset-bottom, 0px)",
        ):
            self.assertIn(marker, CSS)


if __name__ == "__main__":
    unittest.main()
