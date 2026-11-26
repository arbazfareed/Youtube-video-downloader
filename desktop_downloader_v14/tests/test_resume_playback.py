import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app_media import MediaMixin
from resume_positions import ResumeStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = ResumeStore(Path(self.dir.name) / "r.json")
        self.video = Path(self.dir.name) / "a.mp4"
        self.video.touch()

    def tearDown(self):
        self.dir.cleanup()

    def test_saves_and_returns_position(self):
        self.store.save(self.video, 65_000, 600_000)
        self.assertEqual(ResumeStore(self.store.path).get(self.video), 65_000)   # survives restart

    def test_start_and_end_of_video_are_not_remembered(self):
        self.store.save(self.video, 65_000, 600_000)
        self.store.save(self.video, 3_000, 600_000)
        self.assertIsNone(self.store.get(self.video))
        self.store.save(self.video, 65_000, 600_000)
        self.store.save(self.video, 595_000, 600_000)     # last 10 s = finished
        self.assertIsNone(self.store.get(self.video))

    def test_unknown_length_is_ignored(self):
        self.store.save(self.video, 65_000, 0)
        self.assertIsNone(self.store.get(self.video))

    def test_forget_and_independent_videos(self):
        other = Path(self.dir.name) / "b.mp4"; other.touch()
        self.store.save(self.video, 40_000, 600_000)
        self.store.save(other, 90_000, 600_000)
        self.store.forget(self.video)
        self.assertIsNone(self.store.get(self.video))
        self.assertEqual(self.store.get(other), 90_000)

    def test_corrupt_file_is_harmless(self):
        self.store.path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.store.get(self.video))
        self.store.save(self.video, 40_000, 600_000)
        self.assertEqual(self.store.get(self.video), 40_000)

    def test_old_entries_are_trimmed(self):
        for i in range(520):
            self.store.save(Path(self.dir.name) / f"v{i}.mp4", 40_000, 600_000)
        self.assertLessEqual(len(self.store._read()), 500)


class PlayerHookTests(unittest.TestCase):
    def make(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        app = MediaMixin()
        app._t = lambda text: text
        app._format_in_app_time = lambda ms: f"{ms // 60000:02d}:{ms // 1000 % 60:02d}"
        app._set_in_app_player_status = MagicMock()
        app._resume_positions = ResumeStore(Path(self.dir.name) / "r.json")
        app._in_app_media_path = Path(self.dir.name) / "m.mp4"
        app._in_app_media_path.touch()
        app._in_app_resume_pending = app._resume_lookup(app._in_app_media_path)
        return app

    def test_second_play_continues_from_saved_spot(self):
        app = self.make()
        app._resume_playback_tick(MagicMock(), 125_000, 600_000, True, False)  # watching, saves
        app._resume_save_now()
        app._in_app_resume_pending = app._resume_lookup(app._in_app_media_path)
        player = MagicMock(); player.set_time.return_value = 0
        app._resume_playback_tick(player, 0, 600_000, True, False)
        player.set_time.assert_called_once_with(125_000)
        self.assertIn("Continuing from 02:05", app._set_in_app_player_status.call_args[0][0])
        self.assertIsNone(app._in_app_resume_pending)

    def test_waits_until_seekable_and_does_not_overwrite_saved_spot(self):
        app = self.make()
        app._resume_positions.save(app._in_app_media_path, 80_000, 600_000)
        app._in_app_resume_pending = 80_000
        player = MagicMock()
        app._resume_playback_tick(player, 0, 0, False, False)     # VLC not ready
        player.set_time.assert_not_called()
        self.assertEqual(app._resume_positions.get(app._in_app_media_path), 80_000)
        app._resume_save_now()                                    # closed before it was ready
        self.assertEqual(app._resume_positions.get(app._in_app_media_path), 80_000)

    def test_finished_video_is_forgotten(self):
        app = self.make()
        app._resume_positions.save(app._in_app_media_path, 80_000, 600_000)
        app._in_app_resume_pending = None
        app._resume_playback_tick(MagicMock(), 600_000, 600_000, True, True)
        self.assertIsNone(app._resume_positions.get(app._in_app_media_path))

    def test_closing_saves_last_position(self):
        app = self.make()
        app._in_app_resume_pending = None
        app._resume_playback_tick(MagicMock(), 200_000, 600_000, True, False)
        app._resume_positions.forget(app._in_app_media_path)      # periodic save not needed
        app._in_app_last_time_ms, app._in_app_last_duration_ms = 215_000, 600_000
        app._resume_save_now()
        self.assertEqual(app._resume_positions.get(app._in_app_media_path), 215_000)

    def test_store_failure_never_breaks_playback(self):
        app = self.make()
        app._resume_positions = MagicMock()
        app._resume_positions.get.side_effect = OSError("disk")
        app._resume_positions.save.side_effect = OSError("disk")
        self.assertIsNone(app._resume_lookup(app._in_app_media_path))
        app._in_app_resume_pending = None
        app._resume_playback_tick(MagicMock(), 50_000, 600_000, True, False)
        app._resume_save_now()


if __name__ == "__main__":
    unittest.main()
