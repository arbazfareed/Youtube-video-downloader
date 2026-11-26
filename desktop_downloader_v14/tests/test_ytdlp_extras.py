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
            any(line.startswith("yt-dlp[default]") for line in lines),
            "yt-dlp must be installed with [default] so YouTube's JavaScript "
            "challenge solver (yt-dlp-ejs) and HLS decryption are available",
        )

    def test_launcher_still_reads_the_package_name_from_an_extras_line(self):
        self.assertIn("yt-dlp", _requirement_names(REQUIREMENTS))
        self.assertNotIn("yt-dlp[default]", _requirement_names(REQUIREMENTS))

    @unittest.skipUnless(
        importlib.util.find_spec("yt_dlp_ejs"),
        "run after installing requirements.txt",
    )
    def test_the_helpers_are_importable_when_requirements_are_installed(self):
        for module in ("yt_dlp_ejs", "Cryptodome", "mutagen", "websockets"):
            with self.subTest(module=module):
                self.assertIsNotNone(importlib.util.find_spec(module))


if __name__ == "__main__":
    unittest.main()
