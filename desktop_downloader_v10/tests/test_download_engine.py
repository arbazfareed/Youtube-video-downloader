import queue
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app import MAX_SPEEDS, DownloaderApp
from history_store import DownloadHistory
from download_engine import (
    ACTIVE_TARGETS,
    DownloadCancelled,
    TARGET_LOCK,
    _claim_target,
    _download_direct,
    _is_direct_file_url,
    _safe_filename,
    _video_format_selector,
    _download_with_ytdlp,
    _fragment_workers,
    download_url,
    _progress_details,
    _wait_until_resumed,
)
from torrent_engine import _find_aria2, download_torrent, is_torrent_url
import requests


class _FakeJobs:
    def __init__(self, statuses):
        self.rows = {job_id: {"status": status} for job_id, status in statuses.items()}

    def get_children(self):
        return tuple(self.rows)

    def set(self, job_id, column, value=None):
        if value is None:
            return self.rows[job_id][column]
        self.rows[job_id][column] = value

    def delete(self, job_id):
        del self.rows[job_id]

    def exists(self, job_id):
        return job_id in self.rows


class _FakeRoot:
    def after(self, *_args):
        return None


class _FakeStringVar:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _FakeHistory:
    def __init__(self):
        self.deleted = []

    def delete(self, record_id):
        self.deleted.append(record_id)


class _FakeResponse:
    status_code = 206
    headers = {
        "Content-Length": "3",
        "Content-Range": "bytes 3-5/6",
        "Content-Type": "application/octet-stream",
    }
    url = "https://example.org/archive.bin"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield b"def"


class _ParallelProbeResponse(_FakeResponse):
    status_code = 206
    headers = {
        "Content-Range": "bytes 0-0/6",
        "Content-Type": "application/octet-stream",
        "Content-Disposition": 'attachment; filename="archive.bin"',
        "ETag": '"stable"',
    }

    def iter_content(self, chunk_size):
        yield b"a"


class _RangeResponse(_FakeResponse):
    def __init__(self, payload, start, end, total):
        self.payload = payload
        self.status_code = 206
        self.headers = {"Content-Range": f"bytes {start}-{end}/{total}"}

    def iter_content(self, chunk_size):
        yield self.payload


class _FakeSession:
    def __init__(self):
        self.headers = None

    def get(self, _url, headers, **_kwargs):
        self.headers = headers
        return _FakeResponse()

    def close(self):
        return None


class _DisconnectingResponse(_FakeResponse):
    status_code = 200
    headers = {
        "Content-Length": "6",
        "Content-Type": "application/octet-stream",
    }

    def iter_content(self, chunk_size):
        yield b"abc"
        raise requests.ConnectionError("connection dropped")


class _RecordingSession(_FakeSession):
    def __init__(self, *responses):
        super().__init__()
        self.responses = list(responses)
        self.request_headers = []

    def get(self, _url, headers, **_kwargs):
        self.headers = headers
        self.request_headers.append(headers)
        return self.responses.pop(0)


class DownloadEngineTests(unittest.TestCase):
    def test_clear_finished_removes_only_terminal_rows(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.jobs = _FakeJobs({
            "1": "Complete",
            "2": "Failed",
            "3": "Cancelled",
            "4": "Downloading direct file",
            "5": "Queued",
        })
        app.history = _FakeHistory()
        app._download_paths = {job_id: Path(job_id) for job_id in app.jobs.get_children()}
        app.cancel_events = {job_id: threading.Event() for job_id in app.jobs.get_children()}
        app.pause_events = {job_id: threading.Event() for job_id in app.jobs.get_children()}
        app.progress_summary = _FakeStringVar()

        removed = app.clear_finished()

        self.assertEqual(removed, 3)
        self.assertEqual(set(app.jobs.get_children()), {"4", "5"})
        self.assertEqual(set(app._download_paths), {"4", "5"})
        self.assertEqual(set(app.cancel_events), {"4", "5"})
        self.assertEqual(set(app.pause_events), {"4", "5"})
        self.assertEqual(set(app.history.deleted), {1, 2, 3})
        self.assertEqual(app.progress_summary.value, "Removed 3 finished download(s) from the list")

    def test_download_history_persists_updates_and_marks_interrupted_jobs(self):
        with TemporaryDirectory() as folder:
            history = DownloadHistory(Path(folder) / "history.sqlite3")
            record_id = history.add("https://example.org/video", "Downloading", folder)
            history.update(record_id, "Downloading media", "42.0%", "video.mp4", folder)

            reloaded = DownloadHistory(Path(folder) / "history.sqlite3")
            reloaded.mark_unfinished_interrupted()
            record = reloaded.list_records()[0]

            self.assertEqual(record.id, record_id)
            self.assertEqual(record.url, "https://example.org/video")
            self.assertEqual(record.status, "Interrupted")
            self.assertEqual(record.progress, "42.0%")
            self.assertEqual(record.details, "video.mp4")

            reloaded.delete(record_id)
            self.assertEqual(reloaded.list_records(), [])

    def test_schedule_validation_requires_future_local_time(self):
        self.assertIsNone(DownloaderApp._parse_scheduled_start(""))
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD HH:MM"):
            DownloaderApp._parse_scheduled_start("tomorrow")
        scheduled = (datetime.now().astimezone() + timedelta(minutes=2)).strftime(
            "%Y-%m-%d %H:%M"
        )
        self.assertGreater(DownloaderApp._parse_scheduled_start(scheduled), time.time())

    def test_late_schedule_event_is_ignored_after_cancel_cleanup(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.events = queue.Queue()
        app.events.put(("start", "1"))
        app.schedule_timers = {}
        app.cancel_events = {}
        app.jobs = _FakeJobs({"1": "Cancelled"})
        app.root = _FakeRoot()

        app._process_events()

        self.assertEqual(app.jobs.set("1", "status"), "Cancelled")

    def test_bandwidth_cap_options_include_unlimited_and_expected_rates(self):
        self.assertIsNone(MAX_SPEEDS["Unlimited"])
        self.assertEqual(MAX_SPEEDS["256 KB/s"], 256 * 1024)
        self.assertEqual(MAX_SPEEDS["5 MB/s"], 5 * 1024 * 1024)

    def test_detects_direct_file_links(self):
        self.assertTrue(_is_direct_file_url("https://example.org/files/video.mp4?download=1"))
        self.assertTrue(_is_direct_file_url("https://example.org/archive.zip"))

    def test_does_not_treat_site_pages_as_direct_files(self):
        self.assertFalse(_is_direct_file_url("https://www.youtube.com/watch?v=example"))
        self.assertFalse(_is_direct_file_url("https://example.org/download?id=12"))

    def test_recognizes_magnet_uris_and_direct_torrent_urls(self):
        self.assertTrue(is_torrent_url("magnet:?xt=urn:btih:0123456789abcdef"))
        self.assertTrue(is_torrent_url("magnet:?xt=urn:btmh:1220abcdef"))
        self.assertTrue(is_torrent_url("https://example.org/files/archive.TORRENT?token=x"))
        self.assertFalse(is_torrent_url("magnet:?dn=missing-info-hash"))
        self.assertFalse(is_torrent_url("https://example.org/files/archive.zip"))
        self.assertFalse(is_torrent_url("https://example.org/download?id=123"))

    def test_auto_routes_torrent_links_to_aria2_engine(self):
        links = (
            "magnet:?xt=urn:btih:0123456789abcdef",
            "https://example.org/archive.torrent",
        )
        with patch("torrent_engine.download_torrent", return_value="saved") as downloader:
            for url in links:
                with self.subTest(url=url):
                    self.assertEqual(
                        download_url(
                            url,
                            Path("downloads"),
                            "auto",
                            "video",
                            "best",
                            "auto",
                            threading.Event(),
                            lambda _status, _percent, _details: None,
                            max_speed=512 * 1024,
                        ),
                        "saved",
                    )

        self.assertEqual(downloader.call_count, len(links))
        self.assertEqual(downloader.call_args.args[-1], 512 * 1024)

    def test_torrent_download_requires_aria2_with_install_hint(self):
        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "aria2c"):
                download_torrent(
                    "magnet:?xt=urn:btih:0123456789abcdef",
                    Path(folder),
                    threading.Event(),
                    lambda _status, _percent, _details: None,
                )

    def test_find_aria2_checks_winget_install_folder(self):
        with TemporaryDirectory() as folder:
            package = (
                Path(folder)
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "aria2.aria2_test"
                / "aria2-build"
            )
            package.mkdir(parents=True)
            executable = package / "aria2c.exe"
            executable.touch()
            with (
                patch("torrent_engine.shutil.which", return_value=None),
                patch("torrent_engine.sys.platform", "win32"),
                patch.dict("torrent_engine.os.environ", {"LOCALAPPDATA": folder}),
            ):
                self.assertEqual(_find_aria2(), str(executable))

    def test_aria2_torrent_download_reports_completion_and_rate_limit(self):
        process = Mock()
        process.poll.return_value = None
        completed_status = {
            "gid": "0123456789abcdef",
            "status": "complete",
            "totalLength": "6",
            "completedLength": "6",
            "downloadSpeed": "0",
            "uploadSpeed": "0",
            "files": [{"path": "downloads/archive.bin"}],
        }

        def rpc_call(_endpoint, _secret, method, *args):
            if method == "tellActive":
                return [{"gid": "0123456789abcdef", "infoHash": "abc"}]
            if method in {"tellWaiting", "tellStopped"}:
                return []
            if method == "tellStatus":
                return completed_status
            self.fail(f"Unexpected aria2 RPC method: {method}")

        progress = []
        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value="aria2c"),
            patch("torrent_engine.subprocess.Popen", return_value=process) as popen,
            patch("torrent_engine._rpc_call", side_effect=rpc_call),
            patch("torrent_engine._rpc_port", return_value=45678),
        ):
            result = download_torrent(
                "magnet:?xt=urn:btih:0123456789abcdef",
                Path(folder),
                threading.Event(),
                lambda *event: progress.append(event),
                max_speed=512 * 1024,
            )

        self.assertEqual(result, str(Path("downloads") / "archive.bin"))
        command = popen.call_args.args[0]
        self.assertIn("--max-download-limit=524288", command)
        self.assertIn("--seed-ratio=0.0", command)
        self.assertEqual(progress[-1][1], 100.0)
        process.terminate.assert_called_once()

    def test_common_public_video_site_links_route_to_ytdlp(self):
        urls = (
            "https://www.youtube.com/watch?v=example",
            "https://www.tiktok.com/@creator/video/1234567890",
            "https://www.facebook.com/watch/?v=1234567890",
            "https://www.instagram.com/reel/example/",
            "https://t.me/example/123",
        )
        with patch("download_engine._download_with_ytdlp", return_value="saved") as downloader:
            for url in urls:
                with self.subTest(url=url):
                    result = download_url(
                        url,
                        Path("downloads"),
                        "auto",
                        "video",
                        "best",
                        "auto",
                        threading.Event(),
                        lambda _status, _percent, _details: None,
                    )
                    self.assertEqual(result, "saved")

        self.assertEqual(downloader.call_count, len(urls))

    def test_installed_ytdlp_extractors_match_common_public_platform_urls(self):
        from yt_dlp.extractor import gen_extractors

        samples = {
            "youtube": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "TikTok": "https://www.tiktok.com/@scout2015/video/6718335390845095173",
            "facebook": "https://www.facebook.com/watch/?v=1234567890",
            "Instagram": "https://www.instagram.com/reel/C0ffee12345/",
            "telegram:embed": "https://t.me/example/123",
        }
        extractors = list(gen_extractors())
        for expected_name, url in samples.items():
            with self.subTest(platform=expected_name):
                self.assertTrue(
                    any(
                        extractor.IE_NAME == expected_name and extractor.suitable(url)
                        for extractor in extractors
                    )
                )

    def test_resolution_options_are_upper_limits(self):
        self.assertEqual(
            _video_format_selector("4320p"),
            "bestvideo[height<=4320]+bestaudio/best[height<=4320]",
        )
        self.assertEqual(
            _video_format_selector("144p"),
            "bestvideo[height<=144]+bestaudio/best[height<=144]",
        )
        self.assertEqual(_video_format_selector("best"), "bestvideo+bestaudio/best")

    def test_progress_details_show_filename_size_speed_and_eta(self):
        details = _progress_details(
            r"C:\Downloads\video.mp4",
            2 * 1024 * 1024,
            4 * 1024 * 1024,
            1024 * 1024,
            65,
        )
        self.assertEqual(details, "video.mp4 | 2.0 / 4.0 MB | 1.00 MB/s | ETA 1:05")

    def test_single_video_option_disables_playlist_download(self):
        with TemporaryDirectory() as folder, patch("download_engine.yt_dlp.YoutubeDL") as youtube_dl:
            downloader = youtube_dl.return_value.__enter__.return_value
            downloader.extract_info.return_value = {"_filename": "video.mp4"}

            _download_with_ytdlp(
                "https://example.org/video",
                Path(folder),
                "video",
                "1080p",
                "single video",
                threading.Event(),
                lambda _status, _percent, _details: None,
            )

            options = youtube_dl.call_args.args[0]
            self.assertTrue(options["noplaylist"])
            self.assertIn("height<=1080", options["format"])
            self.assertEqual(options["concurrent_fragment_downloads"], 8)

    def test_media_options_accept_source_audio_and_bandwidth_cap(self):
        with TemporaryDirectory() as folder, patch("download_engine.yt_dlp.YoutubeDL") as youtube_dl:
            downloader = youtube_dl.return_value.__enter__.return_value
            downloader.extract_info.return_value = {"_filename": "audio.webm"}

            _download_with_ytdlp(
                "https://example.org/audio",
                Path(folder),
                "best audio",
                "best",
                "single video",
                threading.Event(),
                lambda _status, _percent, _details: None,
                max_speed=1024 * 1024,
            )

            options = youtube_dl.call_args.args[0]
            self.assertEqual(options["format"], "bestaudio/best")
            self.assertEqual(options["ratelimit"], 1024 * 1024)
            self.assertNotIn("postprocessors", options)

    def test_entire_playlist_option_keeps_playlist_items(self):
        with TemporaryDirectory() as folder, patch("download_engine.yt_dlp.YoutubeDL") as youtube_dl:
            downloader = youtube_dl.return_value.__enter__.return_value
            downloader.extract_info.return_value = {"_filename": "playlist.mp4"}

            _download_with_ytdlp(
                "https://example.org/playlist",
                Path(folder),
                "video",
                "best",
                "entire playlist",
                threading.Event(),
                lambda _status, _percent, _details: None,
            )

            options = youtube_dl.call_args.args[0]
            self.assertFalse(options["noplaylist"])
            self.assertIn("playlist_title", options["outtmpl"]["default"])
            self.assertIn("playlist_index", options["outtmpl"]["default"])

    def test_speed_modes_map_to_fragment_worker_limits(self):
        self.assertEqual(_fragment_workers("balanced"), 4)
        self.assertEqual(_fragment_workers("fast"), 8)
        self.assertEqual(_fragment_workers("maximum"), 16)

    def test_media_cancellation_stays_distinct_from_download_failure(self):
        with TemporaryDirectory() as folder, patch("download_engine.yt_dlp.YoutubeDL") as youtube_dl:
            downloader = youtube_dl.return_value.__enter__.return_value
            cancel_event = threading.Event()

            def cancel_during_extract(*_args, **_kwargs):
                cancel_event.set()
                raise RuntimeError("yt-dlp stopped after cancellation")

            downloader.extract_info.side_effect = cancel_during_extract
            with self.assertRaises(DownloadCancelled):
                _download_with_ytdlp(
                    "https://example.org/video",
                    Path(folder),
                    "video",
                    "1080p",
                    "single video",
                    cancel_event,
                    lambda _status, _percent, _details: None,
                )

    def test_output_template_separates_playlist_and_single_video_paths(self):
        import yt_dlp

        template = (
            "%(playlist_title,playlist|Single Videos)s/"
            "%(playlist_index&{} - |)s%(title).200B [%(id)s].%(ext)s"
        )
        with yt_dlp.YoutubeDL({"quiet": True, "outtmpl": {"default": template}}) as ydl:
            single = {"title": "Example", "id": "abc", "ext": "mp4"}
            playlist = {
                "title": "Example",
                "id": "abc",
                "ext": "mp4",
                "playlist_title": "My List",
                "playlist_index": 2,
            }

            single_path = ydl.prepare_filename(single).replace("\\", "/")
            playlist_path = ydl.prepare_filename(playlist).replace("\\", "/")

        self.assertEqual(single_path, "Single Videos/Example [abc].mp4")
        self.assertEqual(playlist_path, "My List/2 - Example [abc].mp4")

    def test_sanitizes_windows_unsafe_names(self):
        self.assertEqual(_safe_filename(r"..\folder\bad:name?.mp4"), "bad_name_.mp4")
        self.assertEqual(_safe_filename("CON"), "_CON")

    def test_resumes_existing_partial_and_avoids_active_duplicate(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "archive.zip.part").write_bytes(b"partial")

            first = _claim_target(directory, "archive.zip")
            second = _claim_target(directory, "archive.zip")
            try:
                self.assertEqual(first.name, "archive.zip")
                self.assertEqual(second.name, "archive (1).zip")
            finally:
                with TARGET_LOCK:
                    ACTIVE_TARGETS.discard(str(first.resolve()).casefold())
                    ACTIVE_TARGETS.discard(str(second.resolve()).casefold())

    def test_resumes_direct_file_and_uses_original_filename(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "archive.bin.part").write_bytes(b"abc")
            session = _FakeSession()

            with patch("download_engine.requests.Session", return_value=session):
                result = _download_direct(
                    "https://example.org/archive.bin",
                    directory,
                    threading.Event(),
                    lambda _status, _percent, _details: None,
                )

            self.assertEqual(session.headers, {"Range": "bytes=3-"})
            self.assertEqual(Path(result).name, "archive.bin")
            self.assertEqual(Path(result).read_bytes(), b"abcdef")

    def test_direct_download_applies_selected_bandwidth_cap(self):
        with TemporaryDirectory() as folder:
            with (
                patch("download_engine.requests.Session", return_value=_FakeSession()),
                patch("download_engine._limit_chunk_rate") as limit_rate,
            ):
                _download_direct(
                    "https://example.org/archive.bin",
                    Path(folder),
                    threading.Event(),
                    lambda _status, _percent, _details: None,
                    max_speed=512 * 1024,
                )

            limit_rate.assert_called_once()
            self.assertEqual(limit_rate.call_args.args[0], 3)
            self.assertEqual(limit_rate.call_args.args[1], 512 * 1024)

    def test_parallel_direct_download_uses_multiple_ranges_and_assembles_file(self):
        data = b"abcdef"
        range_headers = []

        def ranged_get(_url, headers, **_kwargs):
            range_headers.append(headers)
            requested = headers["Range"].removeprefix("bytes=").split("-")
            start, end = map(int, requested)
            return _RangeResponse(data[start:end + 1], start, end, len(data))

        session = _FakeSession()
        session.get = lambda _url, headers, **_kwargs: _ParallelProbeResponse()
        with (
            TemporaryDirectory() as folder,
            patch("download_engine.PARALLEL_MIN_SIZE", 1),
            patch("download_engine.requests.Session", return_value=session),
            patch("download_engine.requests.get", side_effect=ranged_get),
        ):
            result = _download_direct(
                "https://example.org/archive.bin",
                Path(folder),
                threading.Event(),
                lambda _status, _percent, _details: None,
                speed_mode="fast",
            )

            self.assertEqual(Path(result).read_bytes(), data)
            self.assertEqual(Path(result).name, "archive.bin")
            self.assertEqual(len(range_headers), 6, repr(range_headers))
            self.assertTrue(all(header.get("If-Range") == '"stable"' for header in range_headers))
            self.assertEqual(list(Path(folder).glob("*.segment-*")), [])
            self.assertEqual(list(Path(folder).glob("*.segments.json")), [])

    def test_retries_connection_drop_and_resumes_partial_file(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            session = _RecordingSession(
                _ParallelProbeResponse(),
                _DisconnectingResponse(),
                _FakeResponse(),
            )
            with (
                patch("download_engine.requests.Session", return_value=session),
                patch("download_engine._wait_for_retry", return_value=False),
            ):
                result = _download_direct(
                    "https://example.org/archive.bin",
                    directory,
                    threading.Event(),
                    lambda _status, _percent, _details: None,
                )

            self.assertEqual(
                session.request_headers,
                [{"Range": "bytes=0-0"}, {}, {"Range": "bytes=3-"}],
            )
            self.assertEqual(Path(result).read_bytes(), b"abcdef")

    def test_pause_waits_for_resume_and_observes_cancellation(self):
        cancel_event = threading.Event()
        pause_event = threading.Event()
        completed = threading.Event()

        thread = threading.Thread(
            target=lambda: (_wait_until_resumed(cancel_event, pause_event), completed.set())
        )
        thread.start()
        time.sleep(0.05)
        self.assertFalse(completed.is_set())
        pause_event.set()
        thread.join(timeout=1)
        self.assertTrue(completed.is_set())

        pause_event.clear()
        cancel_event.set()
        with self.assertRaises(DownloadCancelled) as raised:
            _wait_until_resumed(cancel_event, pause_event)
        self.assertEqual(str(raised.exception), "Download cancelled.")


if __name__ == "__main__":
    unittest.main()
