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

    def test_json_error_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "video.mp4"
            path.write_text('{"error":"access denied"}', encoding="utf-8")
            ok, message = inspect_download(path)
            self.assertFalse(ok)
            self.assertIn("JSON", message)

    def test_nonempty_media_bytes_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clip.mp4"
            path.write_bytes(bytes([0, 0, 0, 24]) + b"ftypmp42" + b"x" * 100)
            ok, message = inspect_download(path)
            self.assertTrue(ok)
            self.assertIn("passed", message)

    def test_playlist_folder_with_only_html_error_pages_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "playlist"
            folder.mkdir()
            (folder / "one.mp4").write_text("<html>blocked</html>", encoding="utf-8")
            (folder / "two.mp4").write_text("<html>login required</html>", encoding="utf-8")
            ok, message = inspect_download(folder)
            self.assertFalse(ok)
            self.assertIn("no valid completed files", message)
            self.assertIn("HTML error page", message)

    def test_playlist_folder_with_valid_media_and_error_file_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "playlist"
            folder.mkdir()
            (folder / "one.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 64)
            (folder / "two.mp4").write_text("<html>blocked</html>", encoding="utf-8")
            (folder / "unfinished.mp4.part").write_bytes(b"partial")
            ok, message = inspect_download(folder)
            self.assertTrue(ok)
            self.assertIn("1 valid file", message)
            self.assertIn("Skipped 1", message)

    def test_playlist_folder_with_only_empty_files_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "playlist"
            folder.mkdir()
            (folder / "empty.mp4").touch()
            (folder / "pending.mp4.part").write_bytes(b"partial")
            ok, message = inspect_download(folder)
            self.assertFalse(ok)
            self.assertIn("empty file", message)


if __name__ == "__main__":
    unittest.main()
