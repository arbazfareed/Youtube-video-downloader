"""Smart Player keyboard: Up/Down volume, B = next audio track, V = subtitles on/off."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import app_media
from app_media import MediaMixin


class Var:
    def __init__(self, value=""):
        self.v = value

    def get(self):
        return self.v

    def set(self, value):
        self.v = value


class Root:
    def __init__(self):
        self.timers = []

    def after(self, _delay, callback):
        self.timers.append(callback)
        return len(self.timers)

    def after_cancel(self, _id):
        pass

    def run_timers(self):
        while self.timers:
            self.timers.pop(0)()


class FakeVlc:
    """Minimal libVLC player: tracks, volume and subtitles, applied like VLC does."""

    def __init__(self, audio=((1, b"Hindi"), (2, b"English"), (3, b"Urdu")), subs=((-1, b"Disable"), (5, b"English"))):
        self.audio, self.subs = list(audio), list(subs)
        self.active_audio, self.active_spu, self.volume = audio[0][0], -1, 50
        self.set_audio_calls, self.spu_calls = [], []
        self.lazy, self.pending_audio = False, None

    def audio_get_track_description(self): return self.audio
    def audio_get_track(self): return self.active_audio
    def audio_set_track(self, i):
        self.set_audio_calls.append(i)
        if self.lazy:
            self.pending_audio = i   # applied later, like real VLC
        else:
            self.active_audio = i
        return 0

    def apply_pending(self):
        if self.pending_audio is not None:
            self.active_audio, self.pending_audio = self.pending_audio, None
    def video_get_spu_description(self): return self.subs
    def video_get_spu(self): return self.active_spu
    def video_set_spu(self, i): self.spu_calls.append(i); self.active_spu = i; return 0
    def audio_set_volume(self, v): self.volume = v; return 0
    def audio_get_volume(self): return self.volume
    def is_playing(self): return True
    def is_seekable(self): return True
    def get_time(self): return 10000
    def get_length(self): return 100000
    def set_time(self, t): return 0


def make_inapp(vlc=None):
    app = MediaMixin()
    app.root = Root()
    app._t = lambda text: text
    window = object()
    app._in_app_player_window = window
    app._in_app_player = vlc or FakeVlc()
    app._in_app_volume_var = Var(50)
    app._in_app_volume_label = Var("50%")
    app._in_app_audio_track = Var("")
    app._in_app_subtitle_track = Var("Off")
    app._in_app_audio_button = MagicMock()
    app._in_app_cc_button = MagicMock()
    app._in_app_audio_tracks = {}
    app._in_app_subtitle_tracks = {}
    app._show_in_app_controls = MagicMock()
    app._set_in_app_player_status = MagicMock()
    app._refresh_in_app_subtitle_tracks()
    app._refresh_in_app_audio_tracks(force=True)
    return app, window


def key(window, name):
    return SimpleNamespace(keysym=name, widget=SimpleNamespace(winfo_toplevel=lambda: window))


class InAppPlayerKeys(unittest.TestCase):
    def test_up_down_change_volume_by_5_and_accumulate(self):
        app, w = make_inapp()
        for _ in range(3):
            self.assertEqual(app._handle_playback_arrow_key(key(w, "Up")), "break")
        self.assertEqual(app._in_app_player.volume, 65)
        app._handle_playback_arrow_key(key(w, "Down"))
        self.assertEqual(app._in_app_player.volume, 60)
        self.assertEqual(app._in_app_volume_label.get(), "60%")

    def test_volume_stops_at_0_and_100(self):
        app, w = make_inapp()
        for _ in range(30):
            app._handle_playback_arrow_key(key(w, "Up"))
        self.assertEqual(app._in_app_player.volume, 100)
        for _ in range(30):
            app._handle_playback_arrow_key(key(w, "Down"))
        self.assertEqual(app._in_app_player.volume, 0)

    def test_b_cycles_every_audio_track_and_wraps(self):
        app, w = make_inapp()
        seen = []
        for _ in range(4):
            self.assertEqual(app._handle_playback_arrow_key(key(w, "b")), "break")
            app.root.run_timers()
            seen.append(app._in_app_player.active_audio)
        self.assertEqual(seen, [2, 3, 1, 2])
        self.assertEqual(app._in_app_audio_track.get(), "English")

    def test_capital_b_works_too(self):
        app, w = make_inapp()
        app._handle_playback_arrow_key(key(w, "B"))
        app.root.run_timers()
        self.assertEqual(app._in_app_player.active_audio, 2)

    def test_fast_double_b_press_goes_two_tracks_not_one(self):
        vlc = FakeVlc()
        vlc.lazy = True
        app, w = make_inapp(vlc)
        app._handle_playback_arrow_key(key(w, "b"))   # VLC has not applied it yet
        app._handle_playback_arrow_key(key(w, "b"))
        vlc.apply_pending()
        app.root.run_timers()
        vlc.apply_pending()
        app.root.run_timers()
        self.assertEqual(vlc.set_audio_calls[:2], [2, 3])
        self.assertEqual(vlc.active_audio, 3)

    def test_b_with_one_audio_track_changes_nothing_and_says_so(self):
        app, w = make_inapp(FakeVlc(audio=((1, b"Only"),)))
        app._handle_playback_arrow_key(key(w, "b"))
        self.assertEqual(app._in_app_player.set_audio_calls, [])
        self.assertIn("Only one audio track", app._set_in_app_player_status.call_args[0][0])

    def test_v_turns_subtitles_on_then_off_then_on(self):
        app, w = make_inapp()
        app._handle_playback_arrow_key(key(w, "v"))
        self.assertEqual(app._in_app_player.active_spu, 5)
        app._handle_playback_arrow_key(key(w, "V"))
        self.assertEqual(app._in_app_player.active_spu, -1)
        app._handle_playback_arrow_key(key(w, "v"))
        self.assertEqual(app._in_app_player.active_spu, 5)

    def test_v_without_subtitles_is_harmless(self):
        app, w = make_inapp(FakeVlc(subs=((-1, b"Disable"),)))
        self.assertEqual(app._handle_playback_arrow_key(key(w, "v")), "break")
        self.assertEqual(app._in_app_player.spu_calls, [])

    def test_keys_outside_the_player_are_not_taken(self):
        # Typing "b" or "v" in the link box must stay normal typing.
        app, _ = make_inapp()
        other = object()
        for name in ("b", "v", "Up"):
            self.assertIsNone(app._handle_playback_arrow_key(key(other, name)))
        self.assertEqual(app._in_app_player.set_audio_calls, [])
        self.assertEqual(app._in_app_player.volume, 50)

    def test_other_letters_ignored(self):
        app, w = make_inapp()
        self.assertIsNone(app._handle_playback_arrow_key(key(w, "x")))


class PreviewPaneKeys(unittest.TestCase):
    def make(self):
        app = MediaMixin()
        app.root = Root()
        app._t = lambda text: text
        vlc = FakeVlc()
        app._preview_vlc_player = vlc
        app.preview_container = object()
        app.preview_player_volume = Var(50)
        app.preview_video_status = Var("")
        app._preview_audio_track = Var("")
        app.preview_audio_selector = MagicMock()
        app._preview_subtitle_track = Var("Off")
        app._preview_subtitle_tracks = {}
        app._preview_audio_tracks = {}
        app._refresh_video_preview_subtitle_tracks()
        app._refresh_video_preview_audio_tracks(force=True)
        return app, vlc

    def event(self, app, name):
        return SimpleNamespace(keysym=name, widget=app.preview_container)

    def test_preview_volume_audio_and_subtitles(self):
        app, vlc = self.make()
        app.root.winfo_toplevel = lambda: app.root
        ev = lambda n: SimpleNamespace(keysym=n, widget=SimpleNamespace(winfo_toplevel=lambda: app.root, master=app.preview_container))
        self.assertEqual(app._handle_playback_arrow_key(ev("Up")), "break")
        self.assertEqual(vlc.volume, 55)
        app._handle_playback_arrow_key(ev("Down")); app._handle_playback_arrow_key(ev("Down"))
        self.assertEqual(vlc.volume, 45)
        app._handle_playback_arrow_key(ev("b")); app.root.run_timers()
        self.assertEqual(vlc.active_audio, 2)
        app._handle_playback_arrow_key(ev("b")); app._handle_playback_arrow_key(ev("b")); app.root.run_timers()
        self.assertEqual(vlc.active_audio, 1)
        app._handle_playback_arrow_key(ev("v"))
        self.assertEqual(vlc.active_spu, 5)
        app._handle_playback_arrow_key(ev("v"))
        self.assertEqual(vlc.active_spu, -1)


class Wiring(unittest.TestCase):
    def test_keys_are_bound_everywhere_the_arrows_are(self):
        src = (BASE_DIR / "app_media.py").read_text(encoding="utf-8")
        ui = (BASE_DIR / "app_ui.py").read_text(encoding="utf-8")
        for seq in ("<KeyPress-b>", "<KeyPress-B>", "<KeyPress-v>", "<KeyPress-V>"):
            self.assertIn(seq, app_media._PLAYBACK_KEY_SEQUENCES)
            self.assertIn(f'"{seq}"', ui, f"{seq} not bound app-wide")
        self.assertGreaterEqual(src.count("in _PLAYBACK_KEY_SEQUENCES"), 4)


if __name__ == "__main__":
    unittest.main()
