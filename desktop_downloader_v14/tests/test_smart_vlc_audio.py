import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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


    def test_polling_recovers_after_transient_vlc_status_exception(self):
        from types import SimpleNamespace

        playing, ended, error = object(), object(), object()
        player = _FakePlayer(is_playing=True)
        player.get_state = MagicMock(side_effect=[RuntimeError("temporary VLC error"), playing])
        player.get_length = lambda: 60000
        player.get_time = lambda: 15000
        player.is_seekable = lambda: True
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Playing=playing, Ended=ended, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_player_status = _FakeTkVar("")
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()

        self.mixin._poll_in_app_playback()

        retry_id = self.mixin._in_app_playback_after
        self.assertIsNotNone(retry_id)
        self.assertIn(retry_id, self.mixin.root.timers)
        self.assertEqual(
            self.mixin._in_app_player_status.get(),
            "Playback status temporarily unavailable",
        )

        self.mixin.root.timers[retry_id]()

        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)
        self.assertEqual(self.mixin._in_app_current_time.get(), "00:15")
        self.assertEqual(self.mixin._in_app_duration.get(), "01:00")

    def test_polling_recovers_after_seekability_query_exception(self):
        from types import SimpleNamespace

        playing, ended, error = object(), object(), object()
        player = _FakePlayer(is_playing=True)
        player.get_state = lambda: playing
        player.get_length = lambda: 60000
        player.get_time = lambda: 15000
        player.is_seekable = MagicMock(
            side_effect=[RuntimeError("temporary seekability error"), True]
        )
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Playing=playing, Ended=ended, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_player_status = _FakeTkVar("")
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()

        self.mixin._poll_in_app_playback()

        retry_id = self.mixin._in_app_playback_after
        self.assertIsNotNone(retry_id)
        self.assertIn(retry_id, self.mixin.root.timers)
        self.assertEqual(
            self.mixin._in_app_player_status.get(),
            "Playback seek status temporarily unavailable",
        )

        self.mixin.root.timers[retry_id]()

        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)
        self.assertEqual(self.mixin._in_app_position_var.get(), 25)
        self.assertEqual(self.mixin._in_app_current_time.get(), "00:15")

    def test_polling_recovers_after_track_refresh_exception(self):
        from types import SimpleNamespace

        playing, ended, error = object(), object(), object()
        player = _FakePlayer(is_playing=True)
        player.get_state = lambda: playing
        player.get_length = lambda: 60000
        player.get_time = lambda: 15000
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Playing=playing, Ended=ended, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_player_status = _FakeTkVar("")
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._in_app_audio_refresh_ticks = 3
        self.mixin._refresh_in_app_audio_tracks = MagicMock(
            side_effect=[RuntimeError("temporary track query error"), None]
        )
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()

        self.mixin._poll_in_app_playback()

        retry_id = self.mixin._in_app_playback_after
        self.assertIsNotNone(retry_id)
        self.assertIn(retry_id, self.mixin.root.timers)
        self.assertEqual(
            self.mixin._in_app_player_status.get(),
            "Playback track information temporarily unavailable",
        )
        self.assertEqual(self.mixin._in_app_position_var.get(), 25)

        # The polling interval is also the refresh cadence; make the next
        # retry land on a refresh tick to verify the transient error recovers.
        self.mixin._in_app_audio_refresh_ticks = 3
        self.mixin.root.timers[retry_id]()

        self.assertEqual(self.mixin._refresh_in_app_audio_tracks.call_count, 2)
        self.mixin._refresh_in_app_subtitle_tracks.assert_called_once()
        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)

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
        self.assertIsNone(getattr(self.mixin, "_in_app_playback_after", None))
        self.assertEqual(self.mixin.root.timers, {})

        current_state["value"] = playing
        self.mixin._toggle_in_app_playback()
        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)


    def test_ab_loop_restart_play_exception_resets_ui_and_polling(self):
        from types import SimpleNamespace

        ended, playing, error = object(), object(), object()
        player = _FakePlayer(active_track=1, is_playing=False)
        player.get_state = lambda: ended
        player.get_length = lambda: 60000
        player.play = MagicMock(side_effect=RuntimeError("VLC play error"))
        self.mixin._in_app_player = player
        window = MagicMock()
        self.mixin._in_app_player_window = window
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=ended, Playing=playing, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_player_status = _FakeTkVar("")
        self.mixin._in_app_ab_loop = {"A": 10000, "B": 20000}
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()

        with patch("app_media.messagebox.showerror") as show_error:
            self.mixin._poll_in_app_playback()

        player.play.assert_called_once()
        self.assertIsNone(getattr(self.mixin, "_in_app_playback_after", None))
        self.assertEqual(self.mixin.root.timers, {})
        self.mixin._in_app_playback_button.configure.assert_called_once_with(text="▶")
        self.mixin._set_in_app_launcher_buttons.assert_called_once_with(False)
        self.assertEqual(self.mixin._in_app_player_status.get(), "Could not restart playback")
        show_error.assert_called_once()
        self.assertEqual(self.mixin._in_app_ab_loop, {"A": 10000, "B": 20000})

    def test_ab_loop_restart_failure_resets_playback_ui_and_polling(self):
        from types import SimpleNamespace

        ended, playing, error = object(), object(), object()
        player = _FakePlayer(active_track=1, is_playing=False)
        player.get_state = lambda: ended
        player.get_length = lambda: 60000
        player.play = MagicMock(return_value=-1)
        self.mixin._in_app_player = player
        window = MagicMock()
        self.mixin._in_app_player_window = window
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=ended, Playing=playing, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_player_status = _FakeTkVar("")
        self.mixin._in_app_ab_loop = {"A": 10000, "B": 20000}
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()

        with patch("app_media.messagebox.showerror") as show_error:
            self.mixin._poll_in_app_playback()

        player.play.assert_called_once()
        self.assertIsNone(getattr(self.mixin, "_in_app_playback_after", None))
        self.assertEqual(self.mixin.root.timers, {})
        self.mixin._in_app_playback_button.configure.assert_called_once_with(text="▶")
        self.mixin._set_in_app_launcher_buttons.assert_called_once_with(False)
        self.assertEqual(
            self.mixin._in_app_player_status.get(), "Could not restart playback"
        )
        show_error.assert_called_once()

    def test_ab_loop_restart_seek_failure_clears_loop_and_continues_polling(self):
        from types import SimpleNamespace

        ended, playing, error = object(), object(), object()
        player = _FakePlayer(is_playing=False)
        player.get_state = lambda: ended
        player.get_length = lambda: 60000
        player.set_time = MagicMock(return_value=-1)
        player.play = MagicMock(return_value=0)
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
        self.mixin._in_app_ab_loop = {"A": 10000, "B": 20000}
        self.mixin._in_app_ab_loop_button = MagicMock()
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()

        self.mixin._poll_in_app_playback()

        player.play.assert_called_once()
        player.set_time.assert_called_once_with(10000)
        self.assertEqual(self.mixin._in_app_ab_loop, {"A": None, "B": None})
        self.mixin._in_app_ab_loop_button.configure.assert_called_once_with(
            text="A-B", foreground="#FFFFFF"
        )
        self.assertEqual(
            self.mixin._in_app_player_status.get(),
            "A-B loop restart seek failed; loop cleared",
        )
        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)

    def test_timeline_seek_failure_restores_actual_position(self):
        player = _FakePlayer(is_playing=True)
        player.get_length = lambda: 60000
        player._time = 15000
        player.set_time = MagicMock(return_value=-1)
        self.mixin._in_app_player = player
        self.mixin._in_app_seeking = True
        self.mixin._in_app_duration_ms = 60000
        self.mixin._in_app_position_var = _FakeTkVar(40)
        self.mixin._in_app_current_time = _FakeTkVar("00:24")
        self.mixin._in_app_timeline = MagicMock()
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()

        self.mixin._seek_in_app_player()

        player.set_time.assert_called_once_with(24000)
        self.assertEqual(self.mixin._in_app_position_var.get(), 25)
        self.assertEqual(self.mixin._in_app_current_time.get(), "00:15")
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Could not seek to selected position"
        )
        self.assertFalse(self.mixin._in_app_seeking)

    def test_timeline_seek_exception_restores_position_and_cleans_drag_state(self):
        player = _FakePlayer(is_playing=True)
        player.get_length = lambda: 60000
        player._time = 15000
        player.set_time = MagicMock(side_effect=RuntimeError("VLC seek exception"))
        self.mixin._in_app_player = player
        self.mixin._in_app_seeking = True
        self.mixin._in_app_control_interaction = True
        self.mixin._in_app_position_var = _FakeTkVar(40)
        self.mixin._in_app_current_time = _FakeTkVar("00:24")
        self.mixin._in_app_timeline = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()

        self.mixin._seek_in_app_player()

        player.set_time.assert_called_once_with(24000)
        self.assertEqual(self.mixin._in_app_position_var.get(), 25)
        self.assertEqual(self.mixin._in_app_current_time.get(), "00:15")
        self.assertFalse(self.mixin._in_app_seeking)
        self.assertFalse(self.mixin._in_app_control_interaction)
        self.mixin._draw_in_app_timeline.assert_called_once()
        self.mixin._show_in_app_controls.assert_called_once()
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Could not seek to selected position"
        )

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


    def test_stop_restores_audio_selector_to_active_track(self):
        player = _FakePlayer(active_track=1, is_playing=True)
        player.stop = MagicMock()
        self.mixin._in_app_player = player
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._in_app_audio_switch = {"target": 2, "after": None}

        # The selector shows the requested track while VLC still has Hindi active.
        self.mixin._refresh_in_app_audio_tracks(force=False)
        self.assertEqual(self.mixin._in_app_audio_track.get(), "English")

        self.mixin._stop_in_app_player()

        self.assertEqual(self.mixin._in_app_audio_track.get(), "Hindi")
        self.assertIsNone(self.mixin._in_app_audio_switch)
        player.stop.assert_called_once()


    def test_stop_cancels_pending_audio_switch_and_allows_new_selection(self):
        player = _FakePlayer(is_playing=True)
        player.stop = MagicMock()
        self.mixin._in_app_player = player
        self.mixin._in_app_audio_track = _FakeTkVar("Hindi")
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()
        self.mixin._in_app_playback_button = MagicMock()

        pending_timer = self.mixin.root.after(250, lambda: self.fail(
            "A stopped audio-switch callback must not run"
        ))
        self.mixin._in_app_audio_switch = {"target": 2, "after": pending_timer}

        self.mixin._stop_in_app_player()

        player.stop.assert_called_once()
        self.assertNotIn(pending_timer, self.mixin.root.timers)
        self.assertIsNone(self.mixin._in_app_audio_switch)

        # A fresh selection after Stop must create a new, independent request.
        self.mixin._choose_in_app_audio_track(1)
        self.assertEqual(player.set_track_calls, [1])
        self.assertEqual(self.mixin._in_app_audio_switch["target"], 1)
        self.assertIsNotNone(self.mixin._in_app_audio_switch["after"])


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


    def test_playback_start_exception_does_not_escape_or_claim_playing(self):
        player = _FakePlayer(is_playing=False)
        player.play = MagicMock(side_effect=RuntimeError("native VLC start error"))
        self.mixin._in_app_player = player
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()

        self.mixin._toggle_in_app_playback()

        player.play.assert_called_once_with()
        self.mixin._set_in_app_launcher_buttons.assert_not_called()
        self.mixin._in_app_playback_button.configure.assert_not_called()
        self.assertIsNone(getattr(self.mixin, "_in_app_playback_after", None))
        self.assertEqual(self.mixin.root.timers, {})
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Playback command failed"
        )
        self.mixin._show_in_app_controls.assert_called_once()

    def test_pause_exception_preserves_existing_playback_poll(self):
        player = _FakePlayer(is_playing=True)
        player.pause = MagicMock(side_effect=RuntimeError("native VLC pause error"))
        self.mixin._in_app_player = player
        self.mixin._in_app_playback_button = MagicMock()
        self.mixin._set_in_app_launcher_buttons = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()
        self.mixin._show_in_app_controls = MagicMock()
        timer_id = self.mixin.root.after(250, self.mixin._poll_in_app_playback)
        self.mixin._in_app_playback_after = timer_id

        self.mixin._toggle_in_app_playback()

        player.pause.assert_called_once_with()
        self.mixin._set_in_app_launcher_buttons.assert_not_called()
        self.mixin._in_app_playback_button.configure.assert_not_called()
        self.assertEqual(self.mixin._in_app_playback_after, timer_id)
        self.assertIn(timer_id, self.mixin.root.timers)
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Playback command failed"
        )
        self.mixin._show_in_app_controls.assert_called_once()

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
        self.assertIsNone(getattr(self.mixin, "_in_app_playback_after", None))
        self.assertEqual(self.mixin.root.timers, {})
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Could not start playback"
        )
        show_error.assert_called_once()



    def test_ab_loop_rejects_non_seekable_media(self):
        player = _FakePlayer(is_playing=True)
        player.is_seekable = lambda: False
        player.set_time = MagicMock()
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_ab_loop = {"A": None, "B": None}
        self.mixin._in_app_ab_loop_button = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()

        self.mixin._toggle_in_app_ab_loop()

        self.assertEqual(self.mixin._in_app_ab_loop, {"A": None, "B": None})
        player.set_time.assert_not_called()
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "A-B loop is unavailable for non-seekable media."
        )

    def test_ab_loop_default_endpoint_is_clamped_to_media_duration(self):
        player = _FakePlayer(is_playing=True)
        player.get_length = lambda: 60000
        player.set_time = MagicMock()
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_ab_loop = {"A": 59000, "B": None}
        self.mixin._in_app_ab_loop_button = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()

        self.mixin._toggle_in_app_ab_loop()

        self.assertEqual(self.mixin._in_app_ab_loop, {"A": 59000, "B": 60000})
        player.set_time.assert_called_once_with(59000)

    def test_ab_loop_rejects_a_point_at_media_end(self):
        player = _FakePlayer(is_playing=True)
        player.get_length = lambda: 60000
        player.set_time = MagicMock()
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_ab_loop = {"A": 60000, "B": None}
        self.mixin._in_app_ab_loop_button = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()

        self.mixin._toggle_in_app_ab_loop()

        self.assertEqual(self.mixin._in_app_ab_loop, {"A": 60000, "B": None})
        player.set_time.assert_not_called()
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Loop point B must be after A; move A earlier."
        )



    def test_ab_loop_clears_when_initial_seek_fails(self):
        player = _FakePlayer(is_playing=True)
        player.get_length = lambda: 60000
        player.set_time = MagicMock(return_value=-1)
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_ab_loop = {"A": 10000, "B": None}
        button = MagicMock()
        self.mixin._in_app_ab_loop_button = button
        self.mixin._set_in_app_player_status = MagicMock()

        self.mixin._toggle_in_app_ab_loop()

        self.assertEqual(self.mixin._in_app_ab_loop, {"A": None, "B": None})
        self.assertEqual(button.configure.call_args, call(text="A-B", foreground="#FFFFFF"))
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "Could not seek to loop point; A-B loop cleared"
        )

    def test_ab_loop_clears_when_boundary_seek_raises(self):
        from types import SimpleNamespace

        ended, playing, error = object(), object(), object()
        player = _FakePlayer(is_playing=True)
        player.get_state = lambda: playing
        player.get_length = lambda: 60000
        player._time = 25000
        player.set_time = MagicMock(side_effect=RuntimeError("VLC seek error"))
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=ended, Playing=playing, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_ab_loop = {"A": 10000, "B": 20000}
        self.mixin._in_app_ab_loop_button = MagicMock()
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()

        self.mixin._poll_in_app_playback()

        player.set_time.assert_called_once_with(10000)
        self.assertEqual(self.mixin._in_app_ab_loop, {"A": None, "B": None})
        self.assertEqual(self.mixin._in_app_current_time.get(), "00:25")
        self.mixin._in_app_ab_loop_button.configure.assert_called_once_with(
            text="A-B", foreground="#FFFFFF"
        )
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "A-B loop seek failed; loop cleared"
        )
        self.assertIsNotNone(self.mixin._in_app_playback_after)
        self.assertIn(self.mixin._in_app_playback_after, self.mixin.root.timers)

    def test_ab_loop_clears_when_boundary_seek_fails(self):
        from types import SimpleNamespace

        ended, playing, error = object(), object(), object()
        player = _FakePlayer(is_playing=True)
        player.get_state = lambda: playing
        player.get_length = lambda: 60000
        player._time = 25000
        player.set_time = MagicMock(return_value=-1)
        self.mixin._in_app_player = player
        self.mixin._in_app_player_window = MagicMock()
        self.mixin._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=ended, Playing=playing, Error=error)
        )
        self.mixin._in_app_duration = _FakeTkVar("")
        self.mixin._in_app_current_time = _FakeTkVar("")
        self.mixin._in_app_position_var = _FakeTkVar(0)
        self.mixin._in_app_seeking = False
        self.mixin._in_app_ab_loop = {"A": 10000, "B": 20000}
        button = MagicMock()
        self.mixin._in_app_ab_loop_button = button
        self.mixin._draw_in_app_timeline = MagicMock()
        self.mixin._refresh_in_app_audio_tracks = MagicMock()
        self.mixin._refresh_in_app_subtitle_tracks = MagicMock()
        self.mixin._set_in_app_player_status = MagicMock()

        self.mixin._poll_in_app_playback()

        self.assertEqual(self.mixin._in_app_ab_loop, {"A": None, "B": None})
        self.assertEqual(self.mixin._in_app_current_time.get(), "00:25")
        button.configure.assert_called_once_with(text="A-B", foreground="#FFFFFF")
        self.mixin._set_in_app_player_status.assert_called_once_with(
            "A-B loop seek failed; loop cleared"
        )
        self.assertIsNotNone(self.mixin._in_app_playback_after)


    def test_control_hide_schedule_survives_is_playing_exception(self):
        player = _FakePlayer(is_playing=True)
        player.is_playing = MagicMock(side_effect=RuntimeError("VLC status error"))
        self.mixin._in_app_player = player
        self.mixin._in_app_controls_after = None
        self.mixin._cancel_in_app_controls_hide = MagicMock()

        self.mixin._schedule_in_app_controls_hide()

        self.assertIsNone(self.mixin._in_app_controls_after)
        self.assertEqual(self.mixin.root.timers, {})

    def test_control_hide_callback_restores_controls_after_is_playing_exception(self):
        player = _FakePlayer(is_playing=True)
        player.is_playing = MagicMock(side_effect=RuntimeError("VLC status error"))
        self.mixin._in_app_player = player
        self.mixin._in_app_controls_after = "expired-timer"
        self.mixin._show_in_app_controls = MagicMock()
        self.mixin._start_in_app_controls_fade = MagicMock()

        self.mixin._hide_in_app_controls()

        self.assertIsNone(self.mixin._in_app_controls_after)
        self.mixin._show_in_app_controls.assert_called_once()
        self.mixin._start_in_app_controls_fade.assert_not_called()


    def test_video_preview_poll_retries_after_native_status_exception(self):
        from types import SimpleNamespace

        player = MagicMock()
        player.get_state.side_effect = RuntimeError("temporary VLC status error")
        self.mixin._preview_vlc_player = player
        self.mixin._preview_vlc = SimpleNamespace(
            State=SimpleNamespace(Error=object(), Playing=object(), Paused=object())
        )
        self.mixin._schedule_video_preview_poll = MediaMixin._schedule_video_preview_poll.__get__(
            self.mixin, MediaMixin
        )

        self.mixin._poll_video_preview()

        retry_id = self.mixin._preview_playback_after
        self.assertIsNotNone(retry_id)
        self.assertEqual(len(self.mixin.root.timers), 1)
        self.assertIn(retry_id, self.mixin.root.timers)

        # The transient failure clears; the next callback updates and schedules
        # the following poll, proving the preview loop remains alive.
        player.get_state.side_effect = None
        player.get_state.return_value = self.mixin._preview_vlc.State.Playing
        player.get_length.return_value = 60000
        player.get_time.return_value = 15000
        player.is_seekable.return_value = True
        self.mixin.preview_video_placeholder = MagicMock()
        self.mixin.preview_player_duration = _FakeTkVar("")
        self.mixin.preview_player_current_time = _FakeTkVar("")
        self.mixin.preview_player_position = _FakeTkVar(0)
        self.mixin._preview_seeking = False
        self.mixin._preview_audio_refresh_ticks = 1
        self.mixin._draw_video_preview_timeline = MagicMock()

        self.mixin.root.timers[retry_id]()

        self.assertEqual(self.mixin.preview_player_current_time.get(), "00:15")
        self.assertEqual(self.mixin.preview_player_position.get(), 25)
        self.assertIsNotNone(self.mixin._preview_playback_after)
        self.assertIn(self.mixin._preview_playback_after, self.mixin.root.timers)



    def test_video_preview_seek_exception_releases_drag_state(self):
        player = MagicMock()
        player.get_length.return_value = 60000
        player.is_seekable.return_value = True
        player.set_time.side_effect = RuntimeError("temporary VLC seek error")
        self.mixin._preview_vlc_player = player
        self.mixin._preview_seeking = True
        self.mixin._preview_duration_ms = 60000
        self.mixin.preview_player_position = _FakeTkVar(40)
        self.mixin.preview_player_timeline = MagicMock()
        self.mixin._draw_video_preview_timeline = MagicMock()

        self.mixin._seek_video_preview()

        player.set_time.assert_called_once_with(24000)
        self.assertFalse(self.mixin._preview_seeking)
        self.mixin._draw_video_preview_timeline.assert_called_once()



if __name__ == "__main__":
    unittest.main()
