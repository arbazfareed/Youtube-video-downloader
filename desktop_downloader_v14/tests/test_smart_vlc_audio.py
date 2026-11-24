import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure v14 folder is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app_media import MediaMixin


class _FakeTkVar:
    def __init__(self, value=""):
        self._val = value

    def get(self):
        return self._val

    def set(self, val):
        self._val = val


class _FakeRoot:
    def __init__(self):
        self.timers = {}
        self.counter = 0

    def after(self, delay, callback):
        self.counter += 1
        timer_id = f"timer_{self.counter}"
        self.timers[timer_id] = callback
        return timer_id

    def after_cancel(self, timer_id):
        if timer_id in self.timers:
            del self.timers[timer_id]


class _FakePlayer:
    def __init__(self, tracks=None, active_track=1, is_playing=True):
        self._tracks = tracks or [(1, b"Hindi"), (2, b"English")]
        self._active_track = active_track
        self._is_playing = is_playing
        self.set_track_calls = []
        self._time = 15000
        self.set_time_calls = []

    def audio_get_track_description(self):
        return self._tracks

    def audio_get_track(self):
        return self._active_track

    def audio_set_track(self, track_id):
        self.set_track_calls.append(track_id)
        return 0

    def is_playing(self):
        return self._is_playing

    def get_time(self):
        return self._time

    def set_time(self, pos):
        self.set_time_calls.append(pos)

    def is_seekable(self):
        return True


class SmartVlcAudioTrackTest(unittest.TestCase):
    def setUp(self):
        self.mixin = MediaMixin()
        self.mixin.root = _FakeRoot()
        self.mixin.language = _FakeTkVar("en")
        self.mixin._t = lambda text: text

    def test_apply_vlc_audio_track_immediate_single_call(self):
        player = _FakePlayer(active_track=1)
        self.mixin._in_app_player = player
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")

        # Select track 2 (English)
        self.mixin._choose_in_app_audio_track(2)

        # audio_set_track must have been called exactly once immediately
        self.assertEqual(player.set_track_calls, [2])
        # Switch state pending
        self.assertIsNotNone(self.mixin._in_app_audio_switch)
        self.assertEqual(self.mixin._in_app_audio_switch["target"], 2)

        # Player reports track 2 active now
        player._active_track = 2

        # Fire the scheduled verification timer
        timer_id = self.mixin._in_app_audio_switch["after"]
        self.assertIn(timer_id, self.mixin.root.timers)
        self.mixin.root.timers[timer_id]()

        # Target should now be cleared as switch is confirmed
        self.assertIsNone(self.mixin._in_app_audio_switch["target"])
        # No extra audio_set_track calls should have occurred during polling
        self.assertEqual(player.set_track_calls, [2])
        self.assertEqual(self.mixin._in_app_audio_track.get(), "English")

    def test_apply_vlc_audio_track_paused_state_does_not_spam(self):
        player = _FakePlayer(active_track=1, is_playing=False)
        self.mixin._in_app_player = player
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")

        # User chooses English while paused
        self.mixin._choose_in_app_audio_track(2)

        # Initial call made
        self.assertEqual(player.set_track_calls, [2])

        # Step runs while still paused
        timer_id = self.mixin._in_app_audio_switch["after"]
        self.mixin.root.timers[timer_id]()

        # Verify it didn't spam set_track and kept the target pending
        self.assertEqual(player.set_track_calls, [2])
        self.assertEqual(self.mixin._in_app_audio_switch["target"], 2)

    def test_toggle_playback_resumes_pending_audio_switch(self):
        player = _FakePlayer(active_track=1, is_playing=False)
        self.mixin._in_app_player = player
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")
        self.mixin._in_app_playback_button = MagicMock()

        # Track 2 is pending
        self.mixin._in_app_audio_switch = {"target": 2, "after": None}

        # Mock player.play to flip is_playing to True
        def mock_play():
            player._is_playing = True
            return 0
        player.play = mock_play
        player.pause = lambda: None

        self.mixin._toggle_in_app_playback()

        # Resuming must have triggered _choose_in_app_audio_track for target 2
        self.assertEqual(player.set_track_calls, [2])

    def test_refresh_in_app_audio_tracks_synchronizes_active_track(self):
        player = _FakePlayer(
            tracks=[(1, b"Hindi"), (2, b"English")],
            active_track=2,
        )
        self.mixin._in_app_player = player
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")

        # Force refresh
        self.mixin._refresh_in_app_audio_tracks(force=True)
        self.assertEqual(self.mixin._in_app_audio_track.get(), "English")

        # Subsequent refresh with force=False should still reflect active track
        player._active_track = 1
        self.mixin._refresh_in_app_audio_tracks(force=False)
        self.assertEqual(self.mixin._in_app_audio_track.get(), "Hindi")

    def test_in_app_settings_menu_lifecycle(self):
        player = _FakePlayer(tracks=[(1, b"Hindi"), (2, b"English")], active_track=1)
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")
        self.mixin._in_app_playback_rate = _FakeTkVar("1.0x")
        self.mixin._in_app_subtitle_track = _FakeTkVar("Off")
        self.mixin._end_in_app_control_interaction = MagicMock()

        fake_button = MagicMock()
        fake_button.winfo_rootx.return_value = 100
        fake_button.winfo_rooty.return_value = 200

        with patch("app_media.tk.Menu") as mock_menu_cls:
            mock_menu_instance = MagicMock()
            mock_menu_cls.return_value = mock_menu_instance
            mock_menu_instance.winfo_reqheight.return_value = 100

            self.mixin._show_in_app_settings_menu(fake_button)

            mock_menu_instance.tk_popup.assert_called_once()
            mock_menu_instance.grab_release.assert_called_once()
            mock_menu_instance.destroy.assert_called_once()
            self.mixin._end_in_app_control_interaction.assert_called_once()


    def test_replay_after_end_restarts_playback_polling(self):
        from types import SimpleNamespace

        ended, playing, error = object(), object(), object()
        current_state = {"value": ended}
        player = _FakePlayer(active_track=1, is_playing=False)
        player.get_state = lambda: current_state["value"]
        player.get_length = lambda: 60000
        player.play = lambda: setattr(player, "_is_playing", True) or 0
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=ended, Playing=playing, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_player_status = _FakeTkVar("")
        self.mixin._in_app_ab_loop = {"A": None, "B": None}
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()
        self.mixin._in_app_playback_after = "stale-fired-callback"

        self.mixin._poll_in_app_playback()
        self.assertIsNone(self.mixin._in_app_playback_after)
        self.assertEqual(self.mixin.root.timers, {})

        current_state["value"] = playing
        self.mixin._toggle_in_app_playback()
        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)


    def test_stop_cancels_playback_poll_timer(self):
        player = _FakePlayer(is_playing=True)
        player.stop = MagicMock()
        self.mixin._in_app_player = player
        self.mixin._in_app_playback_after = self.mixin.root.after(
            250, self.mixin._poll_in_app_playback
        )

        timer_id = self.mixin._in_app_playback_after
        self.assertIn(timer_id, self.mixin.root.timers)

        self.mixin._stop_in_app_player()

        player.stop.assert_called_once()
        self.assertNotIn(timer_id, self.mixin.root.timers)
        self.assertIsNone(self.mixin._in_app_playback_after)


    def test_snapshots_use_unique_paths_and_preserve_previous_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as folder:
            self.mixin.destination = _FakeTkVar(folder)
            self.mixin._in_app_player_window = MagicMock()
            self.mixin._set_in_app_player_status = MagicMock()
            player = MagicMock()

            def write_snapshot(_display, path, _width, _height):
                Path(path).write_bytes(b"snapshot")
                return 0

            player.video_take_snapshot.side_effect = write_snapshot
            self.mixin._in_app_player = player
            fixed_time = MagicMock()
            fixed_time.strftime.return_value = "20261124_210000_123456"

            with patch("app_media.datetime") as mock_datetime:
                mock_datetime.now.return_value = fixed_time
                self.mixin._take_in_app_snapshot()
                first = next(Path(folder, "Screenshots").glob("snapshot_*.png"))
                first.write_bytes(b"first saved image")

                self.mixin._take_in_app_snapshot()
                files = sorted(Path(folder, "Screenshots").glob("snapshot_*.png"))

            self.assertEqual(len(files), 2)
            self.assertEqual(first.read_bytes(), b"first saved image")
            self.assertEqual(player.video_take_snapshot.call_count, 2)


    def test_playback_start_failure_does_not_claim_playing_or_poll(self):
        player = _FakePlayer(is_playing=False)
        player.play = MagicMock(return_value=-1)
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()

        with patch("app_media.messagebox.showerror") as show_error:
            self.mixin._toggle_in_app_playback()

        player.play.assert_called_once_with()
        self.mixin._set_in_app_launcher_buttons.assert_called_once_with(False)
        self.mixin._in_app_playback_button.configure.assert_called_once_with(text="▶")
        self.assertIsNone(self.mixin._in_app_playback_after)
        self.assertEqual(self.mixin.root.timers, {})
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Could not start playback"
        )
        show_error.assert_called_once()



if __name__ == "__main__":
    unittest.main()
