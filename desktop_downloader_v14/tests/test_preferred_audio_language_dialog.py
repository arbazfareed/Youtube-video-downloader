from __future__ import annotations

import unittest

from app_media import _preferred_audio_language_matches


class PreferredAudioLanguageMatchingTests(unittest.TestCase):
    def test_hindi_matches_two_and_three_letter_language_codes(self):
        self.assertTrue(_preferred_audio_language_matches("Hindi only", "hi", ""))
        self.assertTrue(_preferred_audio_language_matches("Hindi only", "hin", ""))

    def test_english_matches_two_and_three_letter_language_codes(self):
        self.assertTrue(_preferred_audio_language_matches("English only", "en", ""))
        self.assertTrue(_preferred_audio_language_matches("English only", "eng", ""))

    def test_language_region_suffix_is_normalized(self):
        self.assertTrue(_preferred_audio_language_matches("English only", "en-US", ""))
        self.assertTrue(_preferred_audio_language_matches("Hindi only", "hi_IN", ""))

    def test_falls_back_to_track_title_when_language_tag_is_unknown(self):
        self.assertTrue(_preferred_audio_language_matches("English only", "und", "English commentary"))
        self.assertTrue(_preferred_audio_language_matches("Hindi only", "und", "Hindi audio"))

    def test_does_not_match_unrelated_track(self):
        self.assertFalse(_preferred_audio_language_matches("English only", "fr", "French"))
        self.assertFalse(_preferred_audio_language_matches("Hindi only", "en", "English"))

    def test_unknown_preference_does_not_force_a_track(self):
        self.assertFalse(_preferred_audio_language_matches("Japanese only", "ja", "Japanese"))


if __name__ == "__main__":
    unittest.main()
