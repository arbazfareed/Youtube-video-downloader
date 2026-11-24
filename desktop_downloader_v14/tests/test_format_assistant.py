import unittest

from format_assistant import preset_details
from download_engine import _video_format_selector


class SmartFormatPresetTests(unittest.TestCase):
    def test_presets_have_explanations(self):
        for key in ("best", "balanced", "small", "compatible", "fast"):
            name, detail = preset_details(key)
            self.assertTrue(name)
            self.assertTrue(detail)

    def test_size_preset_caps_at_720p(self):
        self.assertIn("height<=720", _video_format_selector("small"))

    def test_compatibility_preset_prefers_mp4(self):
        self.assertIn("ext=mp4", _video_format_selector("compatible"))

    def test_fast_preset_uses_single_format_fallback(self):
        self.assertNotIn("+bestaudio", _video_format_selector("fast"))


if __name__ == "__main__":
    unittest.main()
