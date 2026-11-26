"""Regression tests for Smart VLC dashboard preview lifecycle."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app_media import MediaMixin


class SmartVlcPreviewLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.mixin = MediaMixin()
        self.mixin._preview_playback_after = "previous-timer"
        self.mixin._preview_vlc_player = MagicMock()
        self.mixin._preview_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=7, Error=8, Playing=3, Paused=4)
        )
        self.mixin._preview_vlc_player.get_state.return_value = 7
        self.mixin._stop_video_preview = MagicMock()
        self.mixin._schedule_video_preview_poll = MagicMock()

    def test_ended_preview_is_cleaned_up_and_polling_stops(self):
        self.mixin._poll_video_preview()

        self.mixin._stop_video_preview.assert_called_once_with()
        self.mixin._schedule_video_preview_poll.assert_not_called()
        self.assertIsNone(self.mixin._preview_playback_after)

    def test_playing_preview_continues_polling(self):
        self.mixin._preview_vlc_player.get_state.return_value = 3
        self.mixin.preview_video_placeholder = MagicMock()
        self.mixin.preview_player_duration = MagicMock()
        self.mixin.preview_player_current_time = MagicMock()
        self.mixin.preview_player_position = MagicMock()
        self.mixin._preview_duration_ms = 0
        self.mixin._preview_seeking = False
        self.mixin._preview_audio_refresh_ticks = 0
        self.mixin._draw_video_preview_timeline = MagicMock()
        self.mixin._refresh_video_preview_audio_tracks = MagicMock()
        self.mixin._refresh_video_preview_subtitle_tracks = MagicMock()
        self.mixin._format_in_app_time = lambda value: str(value)
        self.mixin._preview_vlc_player.get_length.return_value = 1000
        self.mixin._preview_vlc_player.get_time.return_value = 100
        self.mixin._preview_vlc_player.is_seekable.return_value = True

        self.mixin._poll_video_preview()

        self.mixin._stop_video_preview.assert_not_called()
        self.mixin._schedule_video_preview_poll.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
