import importlib.util
import unittest
from pathlib import Path

from launch import _requirement_names

APP_DIR = Path(__file__).resolve().parents[1]
REQUIREMENTS = APP_DIR / "requirements.txt"


class YtdlpExtrasTests(unittest.TestCase):
    def test_requirements_install_ytdlp_with_its_default_helpers(self):
        lines = [
            line.split("#", 1)[0].strip()
            for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        ]
        self.assertTrue(
            any(line.startswith("yt-dlp[") and "default" in line.split("]")[0] for line in lines),
            "yt-dlp must be installed with [default] so YouTube's JavaScript "
            "challenge solver (yt-dlp-ejs) and HLS decryption are available",
        )

    def test_requirements_enable_browser_impersonation_for_sites_that_need_it(self):
        # Bandcamp, Vimeo and many Cloudflare-protected sites fail with "no impersonate
        # target is available" unless curl-cffi is installed.
        line = next(
            entry.split("#", 1)[0].strip()
            for entry in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
            if entry.startswith("yt-dlp")
        )
        self.assertIn("curl-cffi", line)

    def test_launcher_still_reads_the_package_name_from_an_extras_line(self):
        self.assertIn("yt-dlp", _requirement_names(REQUIREMENTS))
        self.assertNotIn("yt-dlp[default]", _requirement_names(REQUIREMENTS))

    @unittest.skipUnless(
        importlib.util.find_spec("yt_dlp_ejs"),
        "run after installing requirements.txt",
    )
    def test_the_helpers_are_importable_when_requirements_are_installed(self):
        for module in ("yt_dlp_ejs", "Cryptodome", "mutagen", "websockets", "curl_cffi"):
            with self.subTest(module=module):
                self.assertIsNotNone(importlib.util.find_spec(module))


if __name__ == "__main__":
    unittest.main()
