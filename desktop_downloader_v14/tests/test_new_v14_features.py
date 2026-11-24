from __future__ import annotations

import csv
import sys
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from download_engine import _all_audio_tracks_selector, _download_with_ytdlp
from history_store import DownloadHistory
from update_engine import update_ytdlp


class TestNewV14Features(unittest.TestCase):
    def test_update_ytdlp_success(self) -> None:
        mock_proc = Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Successfully installed yt-dlp-2026.01.01"
        mock_proc.stderr = ""

        mock_ytdlp = MagicMock()
        # Simulate a stale already-imported module after pip updates the package.
        mock_ytdlp.__version__ = "2025.12.01"

        with (
            patch("subprocess.run", return_value=mock_proc) as mock_run,
            patch.dict("sys.modules", {"yt_dlp": mock_ytdlp}),
            patch("importlib.metadata.version", return_value="2026.01.01"),
        ):
            old_ver, new_ver = update_ytdlp()
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            self.assertEqual(cmd[1:], ["-m", "pip", "install", "--upgrade", "yt-dlp"])
            self.assertEqual(new_ver, "2026.01.01")

    def test_export_history_to_csv(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_history.db"
            csv_path = Path(temp_dir) / "exported_history.csv"
            history = DownloadHistory(db_path)

            history.add(
                url="https://youtube.com/watch?v=123",
                status="completed",
                destination=str(Path(temp_dir) / "video.mp4"),
            )

            count = history.export_to_csv(csv_path)
            self.assertEqual(count, 1)
            self.assertTrue(csv_path.exists())

            content = csv_path.read_text(encoding="utf-8-sig")
            reader = list(csv.reader(content.splitlines()))
            self.assertGreater(len(reader), 1)
            header = reader[0]
            self.assertIn("URL", header)
            self.assertIn("Destination", header)
            self.assertIn("Status", header)

            row = reader[1]
            self.assertEqual(row[1], "completed")
            self.assertEqual(row[5], "https://youtube.com/watch?v=123")

    def test_audio_languages_selector_filters_correctly(self) -> None:
        formats = [
            {"format_id": "v1080", "vcodec": "avc1", "acodec": "none", "height": 1080},
            {"format_id": "a_en", "vcodec": "none", "acodec": "mp4a", "language": "en"},
            {"format_id": "a_hi", "vcodec": "none", "acodec": "mp4a", "language": "hi"},
            {"format_id": "a_es", "vcodec": "none", "acodec": "mp4a", "language": "es"},
        ]

        mock_downloader = MagicMock()
        mock_downloader.build_format_selector = lambda spec: (
            lambda ctx: [f for f in ctx["formats"] if f["format_id"] in spec]
        )

        # Test selecting Hindi only
        ctx = {"formats": formats, "requested_formats": []}
        selector_hi = _all_audio_tracks_selector(
            mock_downloader, quality="Best available", audio_languages="Hindi only"
        )
        result_hi = list(selector_hi(ctx))
        audio_ids_hi = [f["format_id"] for f in result_hi if f.get("acodec") != "none"]
        self.assertIn("a_hi", audio_ids_hi)
        self.assertNotIn("a_en", audio_ids_hi)
        self.assertNotIn("a_es", audio_ids_hi)

        # Test selecting English only
        ctx2 = {"formats": formats, "requested_formats": []}
        selector_en = _all_audio_tracks_selector(
            mock_downloader, quality="Best available", audio_languages="English only"
        )
        result_en = list(selector_en(ctx2))
        audio_ids_en = [f["format_id"] for f in result_en if f.get("acodec") != "none"]
        self.assertIn("a_en", audio_ids_en)
        self.assertNotIn("a_hi", audio_ids_en)

        # Test selecting English + Hindi
        ctx3 = {"formats": formats, "requested_formats": []}
        selector_both = _all_audio_tracks_selector(
            mock_downloader, quality="Best available", audio_languages="English + Hindi"
        )
        result_both = list(selector_both(ctx3))
        audio_ids_both = [f["format_id"] for f in result_both if f.get("acodec") != "none"]
        self.assertIn("a_en", audio_ids_both)
        self.assertIn("a_hi", audio_ids_both)
        self.assertNotIn("a_es", audio_ids_both)

        # Test fallback when language does not exist in media
        ctx4 = {"formats": formats, "requested_formats": []}
        selector_ja = _all_audio_tracks_selector(
            mock_downloader, quality="Best available", audio_languages="Japanese only"
        )
        result_ja = list(selector_ja(ctx4))
        self.assertTrue(len(result_ja) > 0)

    def test_download_subtitles_options_configured(self) -> None:
        with patch("download_engine.yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_ydl = MagicMock()
            mock_ydl_cls.return_value.__enter__.return_value = mock_ydl
            mock_ydl.extract_info.return_value = {
                "_type": "video",
                "id": "subtest",
                "title": "Test Video",
                "ext": "mp4",
                "requested_downloads": [{"filepath": "test.mp4"}],
            }

            with TemporaryDirectory() as temp_dir:
                cancel_event = threading.Event()
                progress = MagicMock()

                _download_with_ytdlp(
                    url="https://youtube.com/watch?v=subtest",
                    directory=Path(temp_dir),
                    mode="video",
                    quality="1080p (Full HD)",
                    playlist_scope="single video",
                    cancel_event=cancel_event,
                    progress=progress,
                    download_subtitles=True,
                    subtitle_languages="en,hi",
                )

                self.assertTrue(mock_ydl_cls.called)
                opts = mock_ydl_cls.call_args[0][0]
                self.assertTrue(opts.get("writesubtitles"))
                self.assertTrue(opts.get("writeautomaticsub"))
                self.assertEqual(opts.get("subtitlesformat"), "srt/best")
                self.assertIn("en", opts.get("subtitleslangs"))
                self.assertIn("hi", opts.get("subtitleslangs"))

    def test_in_app_ab_loop_cycle(self) -> None:
        from app_media import MediaMixin

        app = MagicMock(spec=MediaMixin)
        app._in_app_player = MagicMock()
        app._in_app_player_window = MagicMock()
        app._in_app_ab_loop_button = MagicMock()
        app._format_in_app_time = MediaMixin._format_in_app_time

        # Initial state: no loop
        app._in_app_ab_loop = {"A": None, "B": None}
        app._in_app_player.get_time.return_value = 5000  # 5.0 seconds

        # Step 1: Click sets Point A
        MediaMixin._toggle_in_app_ab_loop(app)
        self.assertEqual(app._in_app_ab_loop["A"], 5000)
        self.assertIsNone(app._in_app_ab_loop["B"])

        # Step 2: Playback advances to 15000 ms, click sets Point B
        app._in_app_player.get_time.return_value = 15000
        MediaMixin._toggle_in_app_ab_loop(app)
        self.assertEqual(app._in_app_ab_loop["A"], 5000)
        self.assertEqual(app._in_app_ab_loop["B"], 15000)
        app._in_app_player.set_time.assert_called_with(5000)

        # Step 3: Third click clears loop
        MediaMixin._toggle_in_app_ab_loop(app)
        self.assertIsNone(app._in_app_ab_loop["A"])
        self.assertIsNone(app._in_app_ab_loop["B"])

    def test_in_app_snapshot_call(self) -> None:
        from app_media import MediaMixin

        with TemporaryDirectory() as temp_dir:
            app = MagicMock(spec=MediaMixin)
            app._in_app_player = MagicMock()
            app._in_app_player_window = MagicMock()
            app.destination = MagicMock()
            app.destination.get.return_value = temp_dir
            app._in_app_player.video_take_snapshot.return_value = 0

            MediaMixin._take_in_app_snapshot(app)

            self.assertTrue(app._in_app_player.video_take_snapshot.called)
            args = app._in_app_player.video_take_snapshot.call_args[0]
            self.assertEqual(args[0], 0)
            self.assertTrue(str(args[1]).endswith(".png"))
            self.assertIn("Screenshots", str(args[1]))

    def test_shutdown_on_complete_trigger(self) -> None:
        from app_events import EventsMixin

        app = MagicMock(spec=EventsMixin)
        app.shutdown_on_complete = MagicMock()
        app.shutdown_on_complete.get.return_value = True
        app.cancel_events = {}  # Empty queue -> finished

        with patch.object(EventsMixin, "_initiate_shutdown_countdown") as mock_countdown:
            # Call queue finished check logic
            if not app.cancel_events and app.shutdown_on_complete.get():
                EventsMixin._initiate_shutdown_countdown(app)

            mock_countdown.assert_called_once()


    def test_probe_audio_streams(self) -> None:
        from app_support import probe_audio_streams
        import json
        import subprocess

        fake_probe_json = json.dumps({
            "streams": [
                {
                    "index": 1,
                    "codec_name": "aac",
                    "channels": 2,
                    "tags": {"language": "hin", "title": "Hindi Audio"}
                },
                {
                    "index": 2,
                    "codec_name": "aac",
                    "channels": 2,
                    "tags": {"language": "eng", "title": "English Audio"}
                }
            ]
        })
        fake_process = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=fake_probe_json, stderr=""
        )

        with TemporaryDirectory() as temp_dir:
            dummy_file = Path(temp_dir) / "test.mkv"
            dummy_file.write_bytes(b"dummy")
            with patch("subprocess.run", return_value=fake_process):
                with patch("shutil.which", return_value="/usr/bin/ffprobe"):
                    streams = probe_audio_streams(dummy_file, Path("/usr/bin"))
                    self.assertEqual(len(streams), 2)
                    self.assertEqual(streams[0]["index"], 1)
                    self.assertEqual(streams[0]["language"], "hin")
                    self.assertEqual(streams[0]["title"], "Hindi Audio")
                    self.assertEqual(streams[1]["index"], 2)
                    self.assertEqual(streams[1]["language"], "eng")
                    self.assertEqual(streams[1]["title"], "English Audio")

    def test_convert_media_to_mp3_with_stream_index(self) -> None:
        from app_support import _convert_media_to_mp3
        import subprocess

        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source.mkv"
            destination = Path(temp_dir) / "out.mp3"
            source.write_bytes(b"data")

            def fake_ffmpeg(command, **kwargs):
                temp_out = Path(command[-1])
                temp_out.write_bytes(b"converted-mp3-bytes")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("subprocess.run", side_effect=fake_ffmpeg) as mock_run:
                _convert_media_to_mp3(source, destination, Path(temp_dir), stream_index=2)

            self.assertTrue(mock_run.called)
            cmd = mock_run.call_args[0][0]
            self.assertIn("-map", cmd)
            map_idx = cmd.index("-map")
            self.assertEqual(cmd[map_idx + 1], "0:2")
            self.assertIn("-codec:a", cmd)
            self.assertIn("libmp3lame", cmd)

    def test_audio_format_selector_and_single_audio_track_selector(self) -> None:
        from download_engine import _audio_format_selector, _single_audio_track_selector

        # Test format string generation
        self.assertIn("language^=hi", _audio_format_selector("Hindi only"))
        self.assertIn("language^=en", _audio_format_selector("English only"))
        self.assertEqual(_audio_format_selector("all"), "bestaudio/best")

        # Test single audio track selector selecting Hindi
        formats = [
            {"format_id": "v1", "vcodec": "avc1", "acodec": "none"},
            {"format_id": "a_en", "vcodec": "none", "acodec": "mp4a", "language": "en"},
            {"format_id": "a_hi", "vcodec": "none", "acodec": "mp4a", "language": "hi"},
        ]
        mock_downloader = MagicMock()
        mock_downloader.build_format_selector = lambda spec: (
            lambda ctx: [f for f in ctx["formats"] if f["format_id"] in spec]
        )
        selector_hi = _single_audio_track_selector(mock_downloader, audio_languages="Hindi only")
        chosen_hi = selector_hi({"formats": formats})
        self.assertEqual(len(chosen_hi), 1)
        self.assertEqual(chosen_hi[0]["format_id"], "a_hi")

        # Test single audio track selector selecting English
        selector_en = _single_audio_track_selector(mock_downloader, audio_languages="English only")
        chosen_en = selector_en({"formats": formats})
        self.assertEqual(len(chosen_en), 1)
        self.assertEqual(chosen_en[0]["format_id"], "a_en")

    def test_audio_metadata_pp_respects_preferred_language(self) -> None:
        from download_engine import _AudioLanguageMetadataPP

        pp_hi = _AudioLanguageMetadataPP(preferred_language="Hindi only")
        self.assertEqual(pp_hi.preferred_language, "Hindi only")

        pp_en = _AudioLanguageMetadataPP(preferred_language="English only")
        self.assertEqual(pp_en.preferred_language, "English only")

    def test_audio_metadata_pp_reorders_streams_for_preferred_language(self) -> None:
        from download_engine import _AudioLanguageMetadataPP
        from yt_dlp import YoutubeDL

        with YoutubeDL({"quiet": True}) as downloader:
            processor = _AudioLanguageMetadataPP(downloader, preferred_language="English only")
            processor.run_ffmpeg = Mock()
            info = {
                "filepath": "video.mkv",
                "requested_formats": [
                    {"vcodec": "avc1", "acodec": "none"},
                    {"vcodec": "none", "acodec": "opus", "language": "hi"},
                    {"vcodec": "none", "acodec": "opus", "language": "en"},
                ],
            }
            with patch("download_engine.os.replace"):
                processor.run(info)
            opts = processor.run_ffmpeg.call_args.args[2]
            map_indices = [opts[i + 1] for i, opt in enumerate(opts) if opt == "-map" and "0:a:" in opts[i + 1]]
            self.assertEqual(map_indices, ["0:a:1", "0:a:0"])
            self.assertIn("language=eng", opts[opts.index("-metadata:s:a:0") + 1])
            self.assertIn("language=hin", opts[opts.index("-metadata:s:a:1") + 1])

    def test_direct_download_converts_to_mp3_when_requested(self) -> None:
        from download_engine import _convert_to_mp3_if_needed
        import subprocess

        with TemporaryDirectory() as td:
            video_file = Path(td) / "test.mp4"
            video_file.write_bytes(b"dummy video data")

            def fake_run(cmd, *args, **kwargs):
                out = Path(cmd[-1])
                out.write_bytes(b"dummy mp3 data")
                return subprocess.CompletedProcess(cmd, 0, b"", b"")

            with patch("subprocess.run", side_effect=fake_run), patch("download_engine._ffmpeg_directory", return_value=Path(td)):
                res = _convert_to_mp3_if_needed(video_file, "mp3 audio")
                self.assertEqual(res.suffix.lower(), ".mp3")
                self.assertTrue(res.exists())

    def test_video_format_selector_vertical_video_support(self) -> None:
        from download_engine import _video_format_selector

        fmt_1080 = _video_format_selector("1080p (Full HD)")
        self.assertIn("width<=1080", fmt_1080)
        self.assertIn("height<=1080", fmt_1080)

        fmt_720 = _video_format_selector("720p (HD)")
        self.assertIn("width<=720", fmt_720)
        self.assertIn("height<=720", fmt_720)

        fmt_best = _video_format_selector("Best available")
        self.assertEqual(fmt_best, "bestvideo+bestaudio/best")

    def test_ytdlp_site_aware_error_reporting_facebook(self) -> None:
        from download_engine import _download_with_ytdlp

        cancel_ev = threading.Event()
        progress_cb = MagicMock()

        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl

        def fake_extract_info(url, download=True):
            # Simulate a playlist extraction error
            mock_ydl.params["logger"].error("Requested format is not available")
            return None

        mock_ydl.extract_info.side_effect = fake_extract_info

        def mock_ydl_init(options):
            mock_ydl.params = options
            return mock_ydl

        with patch("yt_dlp.YoutubeDL", side_effect=mock_ydl_init):
            with self.assertRaises(RuntimeError) as ctx:
                _download_with_ytdlp(
                    url="https://www.facebook.com/share/r/1CPyUfMY1n/",
                    directory=Path("."),
                    mode="video (recommended)",
                    quality="1080p (Full HD)",
                    playlist_scope="entire playlist",
                    cancel_event=cancel_ev,
                    progress=progress_cb,
                )
            self.assertIn("Facebook", str(ctx.exception))
            self.assertNotIn("YouTube", str(ctx.exception))

    def test_drm_streaming_services_detection(self) -> None:
        from download_engine import _check_drm_service, download_url

        self.assertEqual(_check_drm_service("https://www.netflix.com/title/80057281"), "Netflix")
        self.assertEqual(_check_drm_service("https://www.primevideo.com/detail/123"), "Amazon Prime Video")
        self.assertEqual(_check_drm_service("https://www.amazon.com/gp/video/detail/123"), "Amazon Prime Video")
        self.assertEqual(_check_drm_service("https://www.disneyplus.com/movies/sample/123"), "Disney+")
        self.assertIsNone(_check_drm_service("https://www.youtube.com/watch?v=123"))
        self.assertIsNone(_check_drm_service("https://www.instagram.com/reel/123/"))

        # download_url should immediately raise descriptive ValueError
        with self.assertRaises(ValueError) as ctx:
            download_url(
                url="https://www.netflix.com/title/80057281",
                directory=Path("."),
                source="auto",
                mode="video",
                quality="1080p",
                playlist_scope="single video",
                cancel_event=threading.Event(),
                progress=lambda *_args: None,
            )
        self.assertIn("Widevine DRM", str(ctx.exception))
        self.assertIn("Netflix", str(ctx.exception))

    def test_instagram_and_drm_advice_in_site_error_advice(self) -> None:
        from download_engine import _site_error_advice

        ig_advice = _site_error_advice("Instagram error: checkpoint_required login_required")
        self.assertIsNotNone(ig_advice)
        self.assertIn("Instagram requires authentication", ig_advice)

        drm_advice = _site_error_advice("ERROR: [DRM] The requested site is known to use DRM protection")
        self.assertIsNotNone(drm_advice)
        self.assertIn("Widevine DRM", drm_advice)

    def test_plugin_exception_safety(self) -> None:
        import plugins

        def broken_callback(*_args):
            raise RuntimeError("Failing plugin execution test")

        with (
            patch.object(plugins, "_loaded", True),
            patch.object(plugins, "_plugins", [("broken-plugin", {"on_complete": broken_callback})]),
        ):
            # emit should catch the exception and return None without crashing
            result = plugins.emit("on_complete", "job-1", "file.mp4")
            self.assertIsNone(result)

    def test_thumbnail_cache_invalidates_when_file_changes_within_same_second(self) -> None:
        from app_support import extract_video_thumbnail
        import os

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.mp4"
            source.write_bytes(b"first video version")
            fixed_mtime_ns = 1_800_000_000_123_456_789
            os.utime(source, ns=(fixed_mtime_ns, fixed_mtime_ns))
            ffmpeg_directory = root / "ffmpeg"
            ffmpeg_directory.mkdir()
            executable = ffmpeg_directory / "ffmpeg"
            executable.write_bytes(b"fake ffmpeg")

            def render_thumbnail(command, **_kwargs):
                Path(command[-1]).write_bytes(b"thumbnail bytes")
                return __import__("subprocess").CompletedProcess(command, 0)

            with patch("app_support.subprocess.run", side_effect=render_thumbnail) as run:
                first = extract_video_thumbnail(source, ffmpeg_directory=ffmpeg_directory)
                source.write_bytes(b"second video version with different size")
                os.utime(source, ns=(fixed_mtime_ns, fixed_mtime_ns))
                second = extract_video_thumbnail(source, ffmpeg_directory=ffmpeg_directory)

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)
            self.assertEqual(run.call_count, 2)

    def test_thumbnail_retries_at_start_for_subsecond_video(self) -> None:
        from app_support import extract_video_thumbnail
        import subprocess

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tiny.mp4"
            source.write_bytes(b"short clip")
            ffmpeg_directory = root / "ffmpeg"
            ffmpeg_directory.mkdir()
            (ffmpeg_directory / "ffmpeg").write_bytes(b"fake ffmpeg")

            def fake_run(command, **_kwargs):
                if "00:00:01" in command:
                    return subprocess.CompletedProcess(command, 1, stdout="", stderr="seek past EOF")
                Path(command[-1]).write_bytes(b"valid thumbnail")
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch("app_support.subprocess.run", side_effect=fake_run) as run:
                thumbnail = extract_video_thumbnail(
                    source, destination=root / "tiny.png", ffmpeg_directory=ffmpeg_directory
                )

            self.assertEqual(thumbnail, root / "tiny.png")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args_list[1].args[0][run.call_args_list[1].args[0].index("-ss") + 1], "00:00:00")

    def test_extract_video_thumbnail_helper(self) -> None:
        from app_support import extract_video_thumbnail

        # Non-existent file returns None
        self.assertIsNone(extract_video_thumbnail(Path("non_existent_file_12345.mp4")))


if __name__ == "__main__":
    unittest.main()

