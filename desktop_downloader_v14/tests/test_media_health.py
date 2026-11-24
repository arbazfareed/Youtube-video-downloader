import tempfile
import unittest
from pathlib import Path

from media_health import inspect_download


class MediaHealthTests(unittest.TestCase):
    def test_missing_output_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            ok, message = inspect_download(Path(temp) / "missing.mp4")
            self.assertFalse(ok)
            self.assertIn("not created", message)

    def test_empty_file_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.mp4"
            path.touch()
            ok, message = inspect_download(path)
            self.assertFalse(ok)
            self.assertIn("empty", message)

    def test_html_response_is_not_accepted_as_media(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "video.mp4"
            path.write_bytes(b"<!doctype html><html><body>Access denied</body></html>")
            ok, message = inspect_download(path)
            self.assertFalse(ok)
            self.assertIn("HTML", message)

    def test_nonempty_media_bytes_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clip.mp4"
            path.write_bytes(bytes([0, 0, 0, 24]) + b"ftypmp42" + b"x" * 100)
            ok, message = inspect_download(path)
            self.assertTrue(ok)
            self.assertIn("passed", message)


if __name__ == "__main__":
    unittest.main()
