import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from download_engine import _download_with_ytdlp, resolve_saved_file


class ResolveSavedFileTests(unittest.TestCase):
    def test_finds_the_real_file_when_only_letter_case_differs(self):
        with TemporaryDirectory() as folder:
            actual = Path(folder) / "e2e tests [clip].mp4"
            actual.write_bytes(b"media")
            self.assertEqual(resolve_saved_file(Path(folder) / "E2E tests [clip].mp4"), actual)

    def test_keeps_an_existing_path_exactly_as_given(self):
        with TemporaryDirectory() as folder:
            real = Path(folder) / "Clip.mp4"
            real.write_bytes(b"media")
            self.assertEqual(resolve_saved_file(real), real)

    def test_missing_or_ambiguous_names_are_returned_unchanged(self):
        with TemporaryDirectory() as folder:
            missing = Path(folder) / "none.mp4"
            self.assertEqual(resolve_saved_file(missing), missing)
            (Path(folder) / "CLIP.mp4").write_bytes(b"1")
            (Path(folder) / "Clip.mp4").write_bytes(b"2")
            ambiguous = Path(folder) / "clip.mp4"
            self.assertEqual(resolve_saved_file(ambiguous), ambiguous)

    def test_a_folder_that_does_not_exist_is_not_an_error(self):
        missing = Path("/nonexistent-folder-for-test/clip.mp4")
        self.assertEqual(resolve_saved_file(missing), missing)


class YtdlpResultPathTests(unittest.TestCase):
    def test_the_returned_path_is_the_file_that_exists_on_disk(self):
        with TemporaryDirectory() as folder:
            saved = Path(folder) / "e2e tests [clip].mp4"
            saved.write_bytes(b"media")
            reported = str(Path(folder) / "E2E tests [clip].mp4")
            with patch("download_engine.yt_dlp.YoutubeDL") as youtube_dl:
                downloader = youtube_dl.return_value.__enter__.return_value
                downloader.extract_info.return_value = {
                    "requested_downloads": [{"filepath": reported}]
                }
                result = _download_with_ytdlp(
                    "https://example.org/video", Path(folder), "video", "best",
                    "single video", threading.Event(), lambda *_a: None,
                )
            self.assertEqual(Path(result), saved.resolve())
            self.assertTrue(Path(result).is_file())


if __name__ == "__main__":
    unittest.main()
