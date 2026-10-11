import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from PIL import Image

from image_engine import (
    convert_image,
    generate_sequence_urls,
    resize_image,
    scrape_image_urls,
    strip_exif,
)


class ImageEngineTests(unittest.TestCase):
    @patch("image_engine.requests.get")
    def test_scrapes_relative_lazy_loaded_srcset_and_og_images_once(self, get):
        response = Mock()
        response.text = """
            <img src="/a.jpg" data-src="/b.webp">
            <source srcset="/c.png 1x, /d.gif 2x">
            <meta property="og:image" content="/a.jpg">
            <img src="/not-an-image.html">
        """
        get.return_value = response
        self.assertEqual(
            scrape_image_urls("https://example.org/gallery"),
            [
                "https://example.org/a.jpg",
                "https://example.org/b.webp",
                "https://example.org/c.png",
                "https://example.org/d.gif",
            ],
        )
        get.assert_called_once()

    @patch("image_engine.requests.get")
    def test_gallery_scan_sends_custom_headers(self, get):
        get.return_value.text = '<img src="/photo.jpg">'

        self.assertEqual(
            scrape_image_urls(
                "https://example.org/gallery",
                headers={"X-Gallery-Key": "private-token"},
            ),
            ["https://example.org/photo.jpg"],
        )
        self.assertEqual(
            get.call_args.kwargs["headers"]["X-Gallery-Key"],
            "private-token",
        )

    def test_generates_padded_sequence_and_rejects_invalid_pattern(self):
        self.assertEqual(
            generate_sequence_urls("https://example.org/img_{:03d}.jpg", 1, 3),
            [
                "https://example.org/img_001.jpg",
                "https://example.org/img_002.jpg",
                "https://example.org/img_003.jpg",
            ],
        )
        with self.assertRaises(ValueError):
            generate_sequence_urls("https://example.org/image.jpg", 1, 2)
        with self.assertRaises(ValueError):
            generate_sequence_urls("https://example.org/{:d}.jpg", 1, 10001)

    def test_convert_transparent_image_to_jpeg_and_resize_image(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGBA", (80, 40), (255, 0, 0, 0)).save(source)
            converted = convert_image(source, "JPEG")
            resized = resize_image(source, 20, 20)
            with Image.open(converted) as image:
                self.assertEqual(image.mode, "RGB")
            with Image.open(resized) as image:
                self.assertLessEqual(image.width, 20)
                self.assertLessEqual(image.height, 20)

    def test_strip_exif_saves_metadata_free_copy_and_preserves_source(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "private.jpg"
            exif = Image.Exif()
            exif[0x010F] = "Camera Model"
            Image.new("RGB", (16, 12), "blue").save(source, exif=exif)
            stripped = strip_exif(source)
            with Image.open(source) as original:
                self.assertEqual(original.getexif().get(0x010F), "Camera Model")
            with Image.open(stripped) as clean:
                self.assertEqual(dict(clean.getexif()), {})
                self.assertEqual(clean.size, (16, 12))


if __name__ == "__main__":
    unittest.main()
