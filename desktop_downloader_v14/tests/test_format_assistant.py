import unittest

from format_assistant import preset_details
from download_engine import _video_format_selector


class SmartFormatPresetTests(unittest.TestCase):
    def test_presets_have_explanations(self):
        for key in ("best", "balanced", "small", "compatible", "fast"):
            name, detail = preset_details(key)
            self.assertTrue(name)
            self.assertTrue(detail)

    def test_size_preset_caps_at_720p_without_unbounded_fallback(self):
        selector = _video_format_selector("small")
        self.assertIn("height<=720", selector)
        self.assertNotRegex(selector, r"/best(?:$|/)")

    def test_compatibility_preset_prefers_mp4_without_unbounded_fallback(self):
        selector = _video_format_selector("compatible")
        self.assertIn("ext=mp4", selector)
        self.assertNotRegex(selector, r"/best(?:$|/)")

    def test_fast_preset_uses_single_format_and_keeps_720p_cap(self):
        selector = _video_format_selector("fast")
        self.assertNotIn("+bestaudio", selector)
        self.assertIn("height<=720", selector)
        self.assertNotRegex(selector, r"/best(?:$|/)")


if __name__ == "__main__":
    unittest.main()
