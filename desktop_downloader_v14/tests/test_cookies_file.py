import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import download_engine
from cookies import cookie_source_error, load_cookies, normalize_cookie_source

HEADER = "# Netscape HTTP Cookie File\n"
LINE = ".example.com\tTRUE\t/\tFALSE\t4102444800\tSID\tabc123\n"


class CookieSourceTests(unittest.TestCase):
    def test_browser_names_are_lower_cased_and_none_variants_match(self):
        self.assertEqual(normalize_cookie_source("Firefox"), "firefox")
        for value in (None, "", "None", "OFF", "  none "):
            self.assertEqual(normalize_cookie_source(value), "none")

    def test_file_path_keeps_its_capital_letters(self):
        self.assertEqual(normalize_cookie_source("FILE:C:\\Users\\Ali\\Cookies.txt"),
                         "file:C:\\Users\\Ali\\Cookies.txt")

    def test_missing_file_and_unknown_browser_are_explained(self):
        self.assertIn("not found", cookie_source_error("file:/no/such/cookies.txt"))
        self.assertIn("Unsupported", cookie_source_error("netscape"))
        self.assertIsNone(cookie_source_error("none"))
        self.assertIsNone(cookie_source_error("Chrome"))

    def test_load_cookies_reads_a_netscape_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "My Cookies.txt"
            path.write_text(HEADER + LINE, encoding="utf-8")
            self.assertEqual(cookie_source_error(f"file:{path}"), None)
            jar = load_cookies(f"file:{path}")
            self.assertEqual([(c.name, c.value) for c in jar], [("SID", "abc123")])

    def test_load_cookies_with_missing_file_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            load_cookies("file:/nope/cookies.txt")


class EngineUsesFileTests(unittest.TestCase):
    def test_ytdlp_gets_cookiefile_not_browser(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Cookies.txt"
            path.write_text(HEADER + LINE, encoding="utf-8")
            captured = {}

            class Stop(Exception):
                pass

            def fake_ydl(options, *a, **k):
                captured.update(options)
                raise Stop()

            with patch.object(download_engine.yt_dlp, "YoutubeDL", fake_ydl):
                with self.assertRaises(Stop):
                    download_engine._download_with_ytdlp(
                        "https://example.com/watch?v=1", Path(d) / "out", "video", "best",
                        "single video", threading.Event(), lambda *a: None,
                        browser_cookies=f"file:{path}")
            self.assertTrue(captured, "yt-dlp was never created")
            self.assertEqual(captured.get("cookiefile"), str(path))
            self.assertNotIn("cookiesfrombrowser", captured)

    def test_bad_cookie_file_stops_the_download_with_a_clear_message(self):
        with self.assertRaisesRegex(ValueError, "cookies file was not found"):
            download_engine.download_url(
                "https://example.com/video.mp4", Path(tempfile.mkdtemp()), "auto", "video", "best",
                "single video", threading.Event(), lambda *a: None, "fast", None, None, None,
                "j", "", "file:/nope/cookies.txt")

    def test_bot_check_message_mentions_the_cookies_file_option(self):
        from app_events import EventsMixin
        text = EventsMixin._friendly_download_error("Sign in to confirm you're not a bot")
        self.assertIn("cookies.txt", text)


if __name__ == "__main__":
    unittest.main()
