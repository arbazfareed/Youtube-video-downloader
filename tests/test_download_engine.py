import sys
import unittest
from pathlib import Path


APP_DIRECTORY = Path(__file__).resolve().parents[1] / "desktop_downloader"
sys.path.insert(0, str(APP_DIRECTORY))

from download_engine import _safe_filename


class DownloadEngineSmokeTests(unittest.TestCase):
    def test_windows_reserved_name_is_sanitized(self):
        self.assertEqual(_safe_filename("CON .txt"), "_CON.txt")


if __name__ == "__main__":
    unittest.main()
