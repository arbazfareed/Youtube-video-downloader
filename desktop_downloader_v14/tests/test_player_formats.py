import unittest

from app_support import (
    AUDIO_MEDIA_EXTENSIONS,
    MEDIA_EXTENSIONS,
    PLAYABLE_MEDIA_EXTENSIONS,
    VIDEO_MEDIA_EXTENSIONS,
)
from download_engine import DIRECT_FILE_EXTENSIONS


class PlayerFormatTests(unittest.TestCase):
    def test_every_format_ytdlp_commonly_saves_can_be_played_from_history(self):
        saved_by_downloads = {
            ".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".3gp", ".ts", ".m4v",
            ".m4a", ".mp3", ".opus", ".ogg", ".aac", ".flac", ".wav", ".wma", ".mka",
        }
        self.assertEqual(saved_by_downloads - PLAYABLE_MEDIA_EXTENSIONS, set())

    def test_playable_is_exactly_video_plus_audio(self):
        self.assertEqual(PLAYABLE_MEDIA_EXTENSIONS, VIDEO_MEDIA_EXTENSIONS | AUDIO_MEDIA_EXTENSIONS)
        self.assertEqual(VIDEO_MEDIA_EXTENSIONS & AUDIO_MEDIA_EXTENSIONS, set())

    def test_history_media_filter_includes_everything_playable(self):
        self.assertTrue(PLAYABLE_MEDIA_EXTENSIONS <= MEDIA_EXTENSIONS)
        self.assertIn(".png", MEDIA_EXTENSIONS)

    def test_direct_links_to_playable_formats_are_treated_as_files(self):
        # Formats the player accepts must also download as plain files from direct links.
        missing = {e for e in PLAYABLE_MEDIA_EXTENSIONS if e not in DIRECT_FILE_EXTENSIONS}
        self.assertEqual(missing, set(), "playable formats missing from direct-file detection")


if __name__ == "__main__":
    unittest.main()
