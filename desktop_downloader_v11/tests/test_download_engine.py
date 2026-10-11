import queue
import sqlite3
import threading
import time
from types import SimpleNamespace
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

from app import MAX_SPEEDS, DownloaderApp, normalize_url
from bandwidth import GlobalBandwidthLimiter
from checksum import verify_checksum
from history_store import DownloadHistory
from download_engine import (
    ACTIVE_TARGETS,
    DownloadCancelled,
    TARGET_LOCK,
    _claim_target,
    _download_direct,
    _is_direct_file_url,
    _release_target,
    _safe_filename,
    _video_format_selector,
    _audio_language_format_ids,
    _all_audio_tracks_selector,
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
        self.rows = {
            job_id: {"status": status, "location": "original", "link": ""}
            for job_id, status in statuses.items()
        }

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
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeEntry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value


class _FakeHistory:
    def __init__(self):
        self.hidden = []

    def set_hidden(self, record_id, hidden):
        self.hidden.append((record_id, hidden))


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
    def test_multilingual_video_selection_keeps_one_best_track_per_language(self):
        from yt_dlp import YoutubeDL

        formats = [
            {"format_id": "137", "ext": "mp4", "url": "https://media/video",
             "vcodec": "avc1", "acodec": "none", "height": 1080, "quality": 10},
            {"format_id": "140", "ext": "m4a", "url": "https://media/en-low",
             "vcodec": "none", "acodec": "mp4a", "language": "en", "abr": 128},
            {"format_id": "251", "ext": "webm", "url": "https://media/en",
             "vcodec": "none", "acodec": "opus", "language": "en", "abr": 160},
            {"format_id": "hi-audio", "ext": "webm", "url": "https://media/hi",
             "vcodec": "none", "acodec": "opus", "language": "hi", "abr": 128},
        ]
        self.assertEqual(
            _audio_language_format_ids(formats),
            [("en", "251"), ("hi", "hi-audio")],
        )

        with YoutubeDL({"quiet": True, "allow_multiple_audio_streams": True}) as ydl:
            selector = _all_audio_tracks_selector(ydl, "1080p")
            selected = list(selector({
                "formats": formats,
                "has_merged_format": False,
                "incomplete_formats": False,
            }))

        self.assertEqual(ydl.params["merge_output_format"], "mkv")
        self.assertEqual(
            [item["format_id"] for item in selected[0]["requested_formats"]],
            ["137", "251", "hi-audio"],
        )

    def test_clear_finished_hides_only_terminal_rows(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.jobs = _FakeJobs({
            "1": "Complete",
            "2": "Failed",
            "3": "Cancelled",
            "4": "Downloading direct file",
            "5": "Queued",
        })
        app._queue_job_ids = list(app.jobs.get_children())
        app._apply_queue_filter = Mock()
        app._queue_filter = "all"
        app.history = _FakeHistory()
        app._download_paths = {job_id: Path(job_id) for job_id in app.jobs.get_children()}
        app._job_destinations = {}
        app.download_options = {}
        app._resume_errors = {}
        app.cancel_events = {job_id: threading.Event() for job_id in app.jobs.get_children()}
        app.resume_events = {job_id: threading.Event() for job_id in app.jobs.get_children()}
        app.progress_summary = _FakeStringVar()
        app.show_hidden = _FakeStringVar()

        removed = app.clear_finished()

        self.assertEqual(removed, 3)
        self.assertEqual(set(app.jobs.get_children()), {"4", "5"})
        self.assertEqual(set(app._download_paths), {"4", "5"})
        self.assertEqual(set(app.cancel_events), {"4", "5"})
        self.assertEqual(set(app.resume_events), {"4", "5"})
        self.assertEqual(set(app.history.hidden), {(1, True), (2, True), (3, True)})
        self.assertIn("Hidden 3", app.progress_summary.value)

    def test_destination_changes_do_not_rewrite_finished_rows(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.jobs = _FakeJobs({
            "1": "Complete",
            "2": "Failed",
            "3": "Cancelled",
            "4": "Interrupted",
            "5": "Downloading",
            "6": "Queued",
            "7": "Scheduled",
        })
        app._queue_job_ids = list(app.jobs.get_children())
        app._download_paths = {
            job_id: Path(job_id) for job_id in app.jobs.get_children()
        }
        app.destination = _FakeStringVar("C:\\Downloads")

        app._update_destination_labels()

        for job_id in ("1", "2", "3", "4"):
            self.assertEqual(app.jobs.set(job_id, "location"), "original")
        self.assertEqual(app.jobs.set("5", "location"), "original")
        self.assertEqual(app.jobs.set("6", "location"), "C:\\Downloads")
        self.assertEqual(app.jobs.set("7", "location"), "C:\\Downloads")

    def test_resume_options_restore_saved_settings_without_persisting_proxy(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.proxy_list = _FakeStringVar("http://user:secret@proxy.example:8080")
        app.browser_cookies = _FakeStringVar("firefox")
        record = SimpleNamespace(
            url="https://example.org/video",
            destination="C:\\Downloads",
            options={
                "source": "auto",
                "mode": "audio",
                "quality": "best",
                "destination": "C:\\Downloads",
                "output_path": "C:\\Downloads\\video.mp4",
                "cloud_provider": "local",
            },
        )

        restored = app._options_for_record(record)
        persisted = DownloaderApp._persistent_job_options_values(
            {
                **restored,
                "destination": Path("C:\\Downloads"),
                "proxy": "http://user:secret@proxy.example:8080",
            },
            Path("C:\\Downloads\\video.mp4"),
        )

        self.assertEqual(restored["mode"], "audio")
        self.assertEqual(restored["destination"], Path("C:\\Downloads"))
        self.assertEqual(restored["proxy"], "http://user:secret@proxy.example:8080")
        self.assertEqual(restored["browser_cookies"], "firefox")
        self.assertNotIn("proxy", persisted)
        self.assertEqual(persisted["output_path"], "C:\\Downloads\\video.mp4")

    def test_download_history_persists_updates_and_marks_interrupted_jobs(self):
        with TemporaryDirectory() as folder:
            history = DownloadHistory(Path(folder) / "history.sqlite3")
            saved_options = {
                "mode": "audio",
                "quality": "best",
                "destination": folder,
                "output_path": str(Path(folder) / "video.mp4"),
            }
            record_id = history.add(
                "https://example.org/video",
                "Downloading",
                folder,
                saved_options,
            )
            history.update(record_id, "Downloading media", "42.0%", "video.mp4", folder)

            reloaded = DownloadHistory(Path(folder) / "history.sqlite3")
            reloaded.mark_unfinished_interrupted()
            record = reloaded.list_records()[0]

            self.assertEqual(record.id, record_id)
            self.assertEqual(record.url, "https://example.org/video")
            self.assertEqual(record.status, "Interrupted")
            self.assertEqual(record.progress, "42.0%")
            self.assertEqual(record.details, "video.mp4")
            self.assertEqual(record.options, saved_options)

            reloaded.set_hidden(record_id, True)
            self.assertEqual(reloaded.list_records(), [])
            hidden_record = reloaded.list_records(include_hidden=True)[0]
            self.assertTrue(hidden_record.hidden)
            reloaded.set_hidden(record_id, False)
            self.assertFalse(reloaded.list_records()[0].hidden)

    def test_history_finds_latest_completed_url_and_persists_settings(self):
        with TemporaryDirectory() as folder:
            database_path = Path(folder) / "history.sqlite3"
            history = DownloadHistory(database_path)
            history.add("HTTPS://Example.org:443/video#first", "Complete", folder)
            latest_id = history.add("https://example.org/video#latest", "Complete", folder)
            history.add("https://example.org/failed", "Failed", folder)
            history.set_setting("dark_mode", "1")

            reloaded = DownloadHistory(database_path)
            result = reloaded.find_by_url("https://EXAMPLE.org/video#another")

            self.assertIsNotNone(result)
            self.assertEqual(result.id, latest_id)
            self.assertEqual(result.status, "Complete")
            self.assertEqual(reloaded.get_setting("dark_mode"), "1")
            self.assertIsNone(reloaded.find_by_url("https://example.org/failed"))

    def test_settings_callbacks_persist_and_recommended_setup_is_simple(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.history = Mock()
        app.dark_mode = _FakeStringVar(True)
        app.warn_on_duplicates = _FakeStringVar(False)
        app.clipboard_autofill = _FakeStringVar(True)
        app._apply_theme = Mock()
        app.source = _FakeStringVar("Supported site")
        app.mode = _FakeStringVar("MP3 audio")
        app.quality = _FakeStringVar("720p (HD)")
        app.playlist_scope = _FakeStringVar("Single video")
        app.speed_mode = _FakeStringVar("Maximum")
        app.max_speed = _FakeStringVar("1 MB/s")
        app.progress_summary = _FakeStringVar()

        app._save_theme_preference()
        app._save_duplicate_preference()
        app._save_clipboard_preference()
        app._use_recommended_settings()

        self.assertEqual(
            app.history.set_setting.call_args_list,
            [
                call("dark_mode", "1"),
                call("warn_on_duplicates", "0"),
                call("clipboard_autofill", "1"),
            ],
        )
        app._apply_theme.assert_called_once()
        self.assertEqual(app.source.get(), "Auto")
        self.assertEqual(app.mode.get(), "Video")
        self.assertEqual(app.quality.get(), "1080p (Full HD)")
        self.assertEqual(app.playlist_scope.get(), "Auto (from link)")
        self.assertEqual(app.speed_mode.get(), "Balanced")
        self.assertEqual(app.max_speed.get(), "Unlimited")

    def test_completed_duplicate_prompts_before_adding_again(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.url_entry = _FakeStringVar("https://example.org/video")
        app.destination = _FakeStringVar("C:\\Downloads")
        app.source = _FakeStringVar("Auto")
        app.warn_on_duplicates = _FakeStringVar(True)
        app.history = Mock()
        app.history.find_by_url.return_value = object()
        app._has_pending_duplicate = Mock(return_value=False)

        with patch("app.messagebox.askyesno", return_value=False) as confirm:
            app.add_download()

        app.history.find_by_url.assert_called_once_with("https://example.org/video")
        confirm.assert_called_once()
        app.history.add.assert_not_called()

    def test_clipboard_watcher_fills_new_urls_without_overwriting_user_text(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.clipboard_autofill = _FakeStringVar(True)
        app._last_clipboard = ""
        app._last_autofilled_clipboard = ""
        app.url_entry = _FakeEntry()
        app.root = Mock()
        app.root.clipboard_get.return_value = " https://example.org/file "

        app._watch_clipboard()

        self.assertEqual(app.url_entry.get(), "https://example.org/file")
        app.root.after.assert_called_once_with(800, app._watch_clipboard)

        app.url_entry.delete(0, "end")
        app.url_entry.insert(0, "https://manually-entered.example/")
        app.root.clipboard_get.return_value = "https://example.org/another"
        app._watch_clipboard()

        self.assertEqual(app.url_entry.get(), "https://manually-entered.example/")

    def test_batch_add_queues_valid_links_and_restores_url_entry(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.url_entry = _FakeEntry("https://keep-this.example/")
        app.expected_checksum = _FakeStringVar("sha256:" + "a" * 64)
        app.jobs = _FakeJobs({})
        queued = []

        def add_download():
            self.assertEqual(app.expected_checksum.get(), "")
            url = app.url_entry.get()
            queued.append(url)
            app.jobs.rows[str(len(queued))] = {
                "status": "Queued",
                "location": "",
                "link": url,
            }

        app.add_download = add_download
        added, valid = app._add_batch_urls(
            [
                "https://example.org/one",
                "",
                "not a link",
                "https://[broken/",
                "http://example.org/two",
                "magnet:?xt=urn:btih:abc",
            ]
        )

        self.assertEqual((added, valid), (3, 3))
        self.assertEqual(
            queued,
            [
                "https://example.org/one",
                "http://example.org/two",
                "magnet:?xt=urn:btih:abc",
            ],
        )
        self.assertEqual(app.url_entry.get(), "https://keep-this.example/")
        self.assertEqual(app.expected_checksum.get(), "sha256:" + "a" * 64)

    def test_history_migrates_existing_database_for_hidden_records(self):
        with TemporaryDirectory() as folder:
            database_path = Path(folder) / "history.sqlite3"
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE downloads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        url TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress TEXT NOT NULL DEFAULT '—',
                        details TEXT NOT NULL DEFAULT '',
                        destination TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO downloads
                        (url, status, destination, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("https://example.org/video", "Complete", folder, "now", "now"),
                )
                connection.commit()

            history = DownloadHistory(database_path)

            self.assertFalse(history.list_records()[0].hidden)
            history.set_hidden(history.list_records()[0].id, True)
            self.assertEqual(history.list_records(), [])

    def test_url_normalization_ignores_host_case_default_port_and_fragment(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.org:443/video?id=1#part"),
            "https://example.org/video?id=1",
        )

    def test_duplicate_detection_ignores_completed_history(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.jobs = _FakeJobs({"1": "Queued", "2": "Complete"})
        app._queue_job_ids = list(app.jobs.get_children())
        app.jobs.set("1", "link", "https://example.org/video#first")
        app.jobs.set("2", "link", "https://example.org/video")

        self.assertTrue(app._has_pending_duplicate("HTTPS://EXAMPLE.ORG/video#second"))
        app.jobs.set("1", "status", "Complete")
        self.assertFalse(app._has_pending_duplicate("https://example.org/video"))

    def test_checksum_verification_checks_sha256(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "payload.bin"
            path.write_bytes(b"payload")
            actual, matches = verify_checksum(
                path,
                "sha256",
                "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5",
            )
            self.assertEqual(len(actual), 64)
            self.assertTrue(matches)
            self.assertFalse(verify_checksum(path, "md5", "0" * 32)[1])

    def test_checksum_entry_accepts_algorithm_prefix(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.checksum_algorithm = _FakeStringVar("SHA256")
        app.expected_checksum = _FakeStringVar("md5:" + "a" * 32)

        self.assertEqual(app._checksum_options(), ("md5", "a" * 32))

    def test_job_finish_verifies_checksum_and_marks_mismatch_failed(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "payload.bin"
            path.write_bytes(b"payload")
            app = DownloaderApp.__new__(DownloaderApp)
            app.events = queue.Queue()
            app.verified_checksums = {}
            app.download_options = {
                "good": {
                    "expected_checksum": (
                        "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"
                    ),
                    "checksum_algorithm": "sha256",
                },
                "bad": {
                    "expected_checksum": "0" * 64,
                    "checksum_algorithm": "sha256",
                },
            }
            successful_future = Mock()
            successful_future.result.return_value = str(path)
            failed_future = Mock()
            failed_future.result.return_value = str(path)

            app._job_finished("good", successful_future)
            app._job_finished("bad", failed_future)

            self.assertEqual(app.events.get_nowait(), ("finished", "good", "Complete", str(path)))
            failed_event = app.events.get_nowait()
            self.assertEqual(failed_event[:3], ("finished", "bad", "Failed"))
            self.assertIn("checksum mismatch", failed_event[3])
            self.assertEqual(app.verified_checksums["good"], (
                "sha256",
                "239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5",
            ))

    def test_completion_notification_names_the_downloaded_file(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.events = queue.Queue()
        app.events.put(
            ("finished", "1", "Complete", "C:\\Downloads\\video.mp4")
        )
        app.jobs = _FakeJobs({"1": "Downloading"})
        app._refresh_job_style = Mock()
        app._apply_queue_filter = Mock()
        app._download_paths = {"1": Path("C:\\Downloads\\video.mp4")}
        app.verified_checksums = {}
        app.overall_progress = Mock()
        app.progress_summary = _FakeStringVar()
        app.root = Mock()
        app._persist_job = Mock()
        app.cancel_events = {"1": threading.Event()}
        app.resume_events = {"1": threading.Event()}
        app.schedule_timers = {}
        app.download_options = {"1": {}}

        with patch("app.notify") as notify_download:
            app._process_events()

        notify_download.assert_called_once_with("Download complete", "video.mp4")

    def test_global_bandwidth_limiter_is_cancellable(self):
        cancel_event = threading.Event()
        limiter = GlobalBandwidthLimiter(1024)
        cancel_event.set()
        self.assertFalse(limiter.acquire(1024, cancel_event))

    def test_global_bandwidth_limiter_is_shared_between_jobs(self):
        cancel_event = threading.Event()
        limiter = GlobalBandwidthLimiter(8192)
        self.assertTrue(limiter.acquire(8192, cancel_event))
        started = time.monotonic()
        self.assertTrue(limiter.acquire(8192, cancel_event))
        self.assertGreaterEqual(time.monotonic() - started, 0.75)

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
        self.assertEqual(downloader.call_args.args[-2], 512 * 1024)

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
        self.assertEqual(_safe_filename("CON .txt"), "_CON.txt")
        self.assertEqual(_safe_filename("report.txt "), "report.txt")

    def test_releases_claimed_target_for_reuse(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            target = _claim_target(directory, "archive.zip")

            _release_target(target)
            next_target = _claim_target(directory, "archive.zip")

            try:
                self.assertEqual(target, next_target)
            finally:
                _release_target(next_target)

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

    def test_direct_download_limits_chunk_before_writing_it(self):
        with TemporaryDirectory() as folder:
            operations = []
            original_open = Path.open

            class RecordingOutput:
                def __init__(self, output):
                    self.output = output

                def __enter__(self):
                    self.output.__enter__()
                    return self

                def __exit__(self, *args):
                    return self.output.__exit__(*args)

                def __getattr__(self, name):
                    return getattr(self.output, name)

                def write(self, chunk):
                    operations.append("write")
                    return self.output.write(chunk)

            def tracked_open(path, *args, **kwargs):
                output = original_open(path, *args, **kwargs)
                if path.name.endswith(".part"):
                    return RecordingOutput(output)
                return output

            def record_rate_limit(*_args):
                operations.append("limit")

            with (
                patch("download_engine.requests.Session", return_value=_FakeSession()),
                patch("download_engine.Path.open", autospec=True, side_effect=tracked_open),
                patch("download_engine._limit_chunk_rate", side_effect=record_rate_limit),
            ):
                _download_direct(
                    "https://example.org/archive.bin",
                    Path(folder),
                    threading.Event(),
                    lambda _status, _percent, _details: None,
                    max_speed=512 * 1024,
                )

            self.assertEqual(operations, ["limit", "write"])

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
        resume_event = threading.Event()
        completed = threading.Event()

        thread = threading.Thread(
            target=lambda: (_wait_until_resumed(cancel_event, resume_event), completed.set())
        )
        thread.start()
        time.sleep(0.05)
        self.assertFalse(completed.is_set())
        resume_event.set()
        thread.join(timeout=1)
        self.assertTrue(completed.is_set())

        resume_event.clear()
        cancel_event.set()
        with self.assertRaises(DownloadCancelled) as raised:
            _wait_until_resumed(cancel_event, resume_event)
        self.assertEqual(str(raised.exception), "Download cancelled.")


if __name__ == "__main__":
    unittest.main()
