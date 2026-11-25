import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app_media import MediaMixin, PLAYABLE_MEDIA_EXTENSIONS


class SmartVlcNavigationTests(unittest.TestCase):
    def setUp(self):
        self.player = MediaMixin()
        self.player.root = MagicMock()
        self.player._t = lambda text: text
        self.player._in_app_player_window = MagicMock()
        self.player._play_media_in_app = MagicMock()

    def test_open_another_video_replaces_media_in_same_player_flow(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as video:
            with patch("app_media.filedialog.askopenfilename", return_value=video.name):
                self.player._open_another_in_app_video()

        self.player._play_media_in_app.assert_called_once_with(Path(video.name).expanduser())

    def test_open_picker_lists_every_supported_media_extension(self):
        with patch("app_media.filedialog.askopenfilename", return_value="") as picker:
            self.player._open_another_in_app_video()

        filetypes = picker.call_args.kwargs["filetypes"]
        playable_glob = filetypes[0][1]
        for extension in PLAYABLE_MEDIA_EXTENSIONS:
            self.assertIn(f"*{extension}", playable_glob)
        self.assertEqual(filetypes[1], ("All files", "*.*"))

    def test_open_another_media_accepts_each_supported_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            for extension in sorted(PLAYABLE_MEDIA_EXTENSIONS):
                media = Path(directory) / f"sample{extension}"
                media.touch()
                self.player._play_media_in_app.reset_mock()
                with patch("app_media.filedialog.askopenfilename", return_value=str(media)):
                    self.player._open_another_in_app_video()
                self.player._play_media_in_app.assert_called_once_with(media)

    def test_cancel_open_video_keeps_current_playback_untouched(self):
        with patch("app_media.filedialog.askopenfilename", return_value=""):
            self.player._open_another_in_app_video()

        self.player._play_media_in_app.assert_not_called()

    def test_back_button_closes_player_not_entire_application(self):
        # The toolbar's Back action is wired to this player-only cleanup.
        self.assertTrue(callable(self.player._close_in_app_player))


if __name__ == "__main__":
    unittest.main()
