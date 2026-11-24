import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import image_engine

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

    def test_conversion_and_resize_preserve_existing_generated_files(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "photo.png"
            Image.new("RGB", (40, 20), "blue").save(source)

            converted_path = Path(directory) / "photo_converted.jpg"
            converted_path.write_bytes(b"keep previous conversion")
            converted = convert_image(source, "JPEG")
            self.assertEqual(converted.name, "photo_converted (1).jpg")
            self.assertEqual(converted_path.read_bytes(), b"keep previous conversion")

            resized_path = Path(directory) / "photo_resized.png"
            resized_path.write_bytes(b"keep previous resize")
            resized = resize_image(source, 10, 10)
            self.assertEqual(resized.name, "photo_resized (1).png")
            self.assertEqual(resized_path.read_bytes(), b"keep previous resize")

    def test_generated_image_saves_do_not_overwrite_a_concurrent_file(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "race.png"
            Image.new("RGB", (12, 8), "green").save(source)
            real_link = os.link

            cases = [
                (lambda: convert_image(source, "JPEG"), "race_converted.jpg",
                 "race_converted (1).jpg"),
                (lambda: resize_image(source, 6, 4), "race_resized.png",
                 "race_resized (1).png"),
                (lambda: strip_exif(source), "race_no_exif.png",
                 "race_no_exif (1).png"),
            ]
            for operation, first_name, next_name in cases:
                first = Path(directory) / first_name
                competitor_created = False

                def race_once(temp_path, destination):
                    nonlocal competitor_created
                    # Simulate exactly one competing creation. Later candidates
                    # must be allowed to publish, or this mock loops forever.
                    if destination == first and not competitor_created:
                        competitor_created = True
                        destination.write_bytes(b"created by competing process")
                    return real_link(temp_path, destination)

                with patch("image_engine.os.link", side_effect=race_once):
                    result = operation()
                self.assertTrue(competitor_created)
                self.assertEqual(first.read_bytes(), b"created by competing process")
                self.assertEqual(result.name, next_name)
                self.assertTrue(result.is_file())
                self.assertNotEqual(result.read_bytes(), b"created by competing process")

    def test_resize_preserves_all_animated_gif_frames_and_timing(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "animated.gif"
            first = Image.new("RGBA", (30, 20), (255, 0, 0, 255))
            second = Image.new("RGBA", (30, 20), (0, 0, 255, 255))
            first.save(
                source,
                save_all=True,
                append_images=[second],
                duration=[120, 240],
                loop=4,
                disposal=2,
            )

            resized = resize_image(source, 12, 10)

            with Image.open(resized) as animation:
                self.assertEqual(animation.n_frames, 2)
                self.assertEqual(animation.info.get("loop"), 4)
                self.assertEqual(animation.info.get("duration"), 120)
                animation.seek(0)
                self.assertEqual(animation.size, (12, 8))
                first_pixel = animation.convert("RGB").getpixel((2, 2))
                animation.seek(1)
                self.assertEqual(animation.info.get("duration"), 240)
                self.assertEqual(animation.size, (12, 8))
                second_pixel = animation.convert("RGB").getpixel((2, 2))
                self.assertNotEqual(first_pixel, second_pixel)

    def test_resize_applies_exif_orientation_before_enforcing_bounds(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "portrait.jpg"
            exif = Image.Exif()
            exif[0x0112] = 6  # Stored 16x12, displayed as 12x16.
            Image.new("RGB", (16, 12), "blue").save(source, exif=exif)

            resized = resize_image(source, 20, 10)

            with Image.open(resized) as image:
                self.assertLessEqual(image.width, 20)
                self.assertLessEqual(image.height, 10)
                self.assertEqual(image.size, (7, 10))  # Pillow rounds 12 * 10 / 16 down.
                self.assertEqual(image.getexif().get(0x0112), None)

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

    def test_strip_exif_applies_orientation_before_removing_it(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "portrait.jpg"
            exif = Image.Exif()
            exif[0x0112] = 6
            Image.new("RGB", (16, 12), "blue").save(source, exif=exif)

            stripped = strip_exif(source)

            with Image.open(stripped) as clean:
                self.assertEqual(clean.size, (12, 16))
                self.assertEqual(dict(clean.getexif()), {})


if __name__ == "__main__":
    unittest.main()
