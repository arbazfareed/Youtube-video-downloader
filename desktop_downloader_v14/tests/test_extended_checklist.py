from __future__ import annotations

import json
import queue
import threading
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from PIL import Image
import requests

from app import DownloaderApp
from bandwidth import GlobalBandwidthLimiter
from checksum import calculate_checksum, verify_checksum
from download_engine import (
    ACTIVE_TARGETS,
    DownloadCancelled,
    RetryPolicy,
    TARGET_LOCK,
    _download_direct,
    _parallel_metadata_path,
    _parallel_range_download,
    _parallel_segment_path,
    _replace_with_retry,
    _safe_filename,
)
from history_store import DownloadHistory
from image_engine import convert_image, resize_image, strip_exif
from torrent_engine import download_torrent


class _Jobs:
    def __init__(self, job_id: str = "job") -> None:
        self.rows = {
            job_id: {
                "status": "Queued",
                "progress": "—",
                "details": "Waiting",
                "location": "",
                "link": "",
            }
        }
        self.selected = (job_id,)

    def exists(self, job_id: str) -> bool:
        return job_id in self.rows

    def item(self, job_id: str, _option: str) -> tuple[str, str]:
        row = self.rows[job_id]
        return row["status"], row["progress"]

    def selection(self) -> tuple[str, ...]:
        return self.selected

    def set(self, job_id: str, column: str, value: str | None = None) -> str | None:
        if value is None:
            return self.rows[job_id][column]
        self.rows[job_id][column] = value
        return value


class _Variable:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _Entry:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def delete(self, *_args: object) -> None:
        self.value = ""

    def insert(self, _index: str, value: str) -> None:
        self.value = value


class CancellationChecklistTests(unittest.TestCase):
    def _app_for_cancel(self, future: Mock | None, timer: Mock | None = None):
        app = DownloaderApp.__new__(DownloaderApp)
        app.jobs = _Jobs()
        app.cancel_events = {"job": threading.Event()}
        app.resume_events = {"job": threading.Event()}
        app.resume_events["job"].clear()
        app.schedule_timers = {"job": timer} if timer else {}
        app._download_futures = {"job": future} if future else {}
        app.events = queue.Queue()
        return app

    def test_queued_job_is_cancelled_before_worker_starts(self) -> None:
        future = Mock()
        future.cancel.return_value = True
        app = self._app_for_cancel(future)

        app.cancel_selected()

        future.cancel.assert_called_once_with()
        self.assertTrue(app.cancel_events["job"].is_set())
        self.assertTrue(app.resume_events["job"].is_set())
        self.assertEqual(app.jobs.set("job", "status"), "Cancelling…")

        future.cancelled.return_value = True
        app._download_future_finished("job", future)
        self.assertEqual(
            app.events.get_nowait(),
            ("finished", "job", "Cancelled", "Cancelled before starting"),
        )

    def test_active_job_uses_cancel_event_without_blocking_the_ui(self) -> None:
        future = Mock()
        future.cancel.return_value = False
        app = self._app_for_cancel(future)

        app.cancel_selected()

        self.assertTrue(app.cancel_events["job"].is_set())
        future.cancel.assert_called_once_with()
        self.assertTrue(app.events.empty())

    def test_scheduled_job_cancels_timer_and_marks_job_cancelled(self) -> None:
        timer = Mock()
        app = self._app_for_cancel(None, timer)

        app.cancel_selected()

        timer.cancel.assert_called_once_with()
        self.assertTrue(app.cancel_events["job"].is_set())
        self.assertEqual(
            app.events.get_nowait(),
            ("finished", "job", "Cancelled", "Scheduled download cancelled"),
        )

    def test_parallel_merge_cancellation_closes_and_removes_partial_output(self) -> None:
        with TemporaryDirectory() as folder:
            target = Path(folder) / "payload.bin"
            segments = [
                {"index": 0, "start": 0, "end": 1},
                {"index": 1, "start": 2, "end": 3},
            ]
            _parallel_metadata_path(target).write_text(
                json.dumps(
                    {
                        "url": "https://example.org/payload.bin",
                        "total": 4,
                        "validator": 'etag:"v1"',
                        "segments": segments,
                    }
                ),
                encoding="utf-8",
            )
            _parallel_segment_path(target, 0).write_bytes(b"ab")
            _parallel_segment_path(target, 1).write_bytes(b"cd")
            cancel_event = threading.Event()
            calls = 0

            def cancel_during_merge(event, _resume_event):
                nonlocal calls
                calls += 1
                if calls == 5:
                    event.set()
                if event.is_set():
                    raise DownloadCancelled("Download cancelled.")

            with (
                patch("download_engine.DIRECT_CHUNK_SIZE", 1),
                patch(
                    "download_engine._wait_until_resumed",
                    side_effect=cancel_during_merge,
                ),
            ):
                with self.assertRaises(DownloadCancelled):
                    _parallel_range_download(
                        "https://example.org/payload.bin",
                        target,
                        4,
                        2,
                        'etag:"v1"',
                        cancel_event,
                        None,
                        lambda *_args: None,
                    )

            self.assertFalse(Path(f"{target}.part").exists())
            self.assertTrue(_parallel_segment_path(target, 0).exists())
            self.assertTrue(_parallel_segment_path(target, 1).exists())
            with TARGET_LOCK:
                self.assertNotIn(str(target.resolve()).casefold(), ACTIVE_TARGETS)

    def test_parallel_segment_with_external_appended_bytes_is_restarted(self) -> None:
        with TemporaryDirectory() as folder:
            target = Path(folder) / "payload.bin"
            segments = [
                {"index": 0, "start": 0, "end": 1},
                {"index": 1, "start": 2, "end": 3},
            ]
            _parallel_metadata_path(target).write_text(
                json.dumps(
                    {
                        "url": "https://example.org/payload.bin",
                        "total": 4,
                        "validator": 'etag:"v1"',
                        "segments": segments,
                    }
                ),
                encoding="utf-8",
            )
            _parallel_segment_path(target, 0).write_bytes(b"xyz")
            _parallel_segment_path(target, 1).write_bytes(b"cd")
            response = Mock()
            response.status_code = 206
            response.headers = {"Content-Range": "bytes 0-1/4"}
            response.iter_content.return_value = iter([b"ab"])
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)

            with patch("download_engine.requests.get", return_value=response) as get:
                result = _parallel_range_download(
                    "https://example.org/payload.bin",
                    target,
                    4,
                    2,
                    'etag:"v1"',
                    threading.Event(),
                    None,
                    lambda *_args: None,
                )

            self.assertEqual(Path(result).read_bytes(), b"abcd")
            self.assertEqual(
                get.call_args.kwargs["headers"]["Range"],
                "bytes=0-1",
            )
            self.assertFalse(_parallel_segment_path(target, 0).exists())

    def test_malformed_parallel_metadata_restarts_with_fresh_ranges(self) -> None:
        with TemporaryDirectory() as folder:
            target = Path(folder) / "payload.bin"
            _parallel_metadata_path(target).write_text("{broken", encoding="utf-8")
            _parallel_segment_path(target, 0).write_bytes(b"stale")
            _parallel_segment_path(target, 1).write_bytes(b"stale")

            class RangeResponse:
                status_code = 206

                def __init__(self, start: int, end: int) -> None:
                    self.headers = {"Content-Range": f"bytes {start}-{end}/4"}
                    self.payload = b"abcd"[start : end + 1]

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return None

                def iter_content(self, chunk_size: int):
                    yield self.payload

            def range_response(_url: str, *, headers: dict[str, str], **_kwargs):
                start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
                return RangeResponse(start, end)

            with patch("download_engine.requests.get", side_effect=range_response):
                result = _parallel_range_download(
                    "https://example.org/payload.bin",
                    target,
                    4,
                    2,
                    'etag:"v1"',
                    threading.Event(),
                    None,
                    lambda *_args: None,
                )

            self.assertEqual(Path(result).read_bytes(), b"abcd")
            self.assertFalse(_parallel_metadata_path(target).exists())
            self.assertFalse(_parallel_segment_path(target, 0).exists())
            self.assertFalse(_parallel_segment_path(target, 1).exists())


class PartialFileIntegrityChecklistTests(unittest.TestCase):
    def _assert_resume_range_rejected(
        self, content_range: str, expected_message: str
    ) -> None:
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            partial = directory / "file.bin.part"
            partial.write_bytes(b"known")
            response = Mock()
            response.status_code = 206
            response.headers = {
                "Content-Range": content_range,
                "Content-Length": "3",
                "Content-Type": "application/octet-stream",
            }
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.iter_content.return_value = iter([b"bad"])
            session = Mock()
            session.headers = {}
            session.get.return_value = response

            with (
                patch("download_engine.requests.Session", return_value=session),
                self.assertRaisesRegex(ValueError, expected_message),
            ):
                _download_direct(
                    "https://example.org/file.bin",
                    directory,
                    threading.Event(),
                    lambda *_args: None,
                    retry_policy=RetryPolicy(attempts=1, base_delay=0, max_delay=0),
                )

            self.assertEqual(partial.read_bytes(), b"known")
            self.assertFalse((directory / "file.bin").exists())
            self.assertEqual(
                session.get.call_args.kwargs["headers"]["Range"],
                "bytes=5-",
            )

    def test_resume_rejects_a_server_range_starting_at_the_wrong_offset(self) -> None:
        self._assert_resume_range_rejected(
            "bytes 6-8/10",
            "invalid range for resume",
        )

    def test_resume_rejects_a_short_range_instead_of_marking_it_complete(self) -> None:
        self._assert_resume_range_rejected(
            "bytes 5-7/10",
            "incomplete range for resume",
        )

    def test_oversized_partial_file_is_not_promoted_by_a_416_response(self) -> None:
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            partial = directory / "file.bin.part"
            partial.write_bytes(b"knownextra")
            response = Mock()
            response.status_code = 416
            response.headers = {"Content-Range": "bytes */5"}
            response.raise_for_status.side_effect = requests.HTTPError(
                "HTTP 416", response=response
            )
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            session = Mock()
            session.headers = {}
            session.get.return_value = response

            with (
                patch("download_engine.requests.Session", return_value=session),
                self.assertRaisesRegex(RuntimeError, "rejected"),
            ):
                _download_direct(
                    "https://example.org/file.bin",
                    directory,
                    threading.Event(),
                    lambda *_args: None,
                    retry_policy=RetryPolicy(attempts=1, base_delay=0, max_delay=0),
                )

            self.assertEqual(partial.read_bytes(), b"knownextra")
            self.assertFalse((directory / "file.bin").exists())


class BatchClipboardAndConcurrencyChecklistTests(unittest.TestCase):
    def test_batch_add_handles_one_hundred_links_and_restores_input_state(self) -> None:
        app = DownloaderApp.__new__(DownloaderApp)
        app.url_entry = _Entry("https://keep.example/")
        app.expected_checksum = _Variable("sha256:" + "a" * 64)
        app.jobs = Mock()
        app.jobs.get_children.side_effect = lambda: list(range(len(queued)))
        queued: list[str] = []

        def add_download() -> None:
            queued.append(app.url_entry.get())

        app.add_download = add_download
        candidates = [
            *(f"https://example.org/file-{index}.zip" for index in range(100)),
            "",
            "not a URL",
            "ftp://example.org/file.zip",
        ]

        added, valid = app._add_batch_urls(candidates)

        self.assertEqual((added, valid), (100, 100))
        self.assertEqual(len(set(queued)), 100)
        self.assertEqual(app.url_entry.get(), "https://keep.example/")
        self.assertEqual(app.expected_checksum.get(), "sha256:" + "a" * 64)

    def test_clipboard_disabled_skips_reads_and_keeps_poll_scheduled(self) -> None:
        app = DownloaderApp.__new__(DownloaderApp)
        app.clipboard_autofill = _Variable(False)
        app.root = Mock()

        app._watch_clipboard()

        app.root.clipboard_get.assert_not_called()
        app.root.after.assert_called_once_with(800, app._watch_clipboard)

    def test_clipboard_non_url_is_ignored_and_lock_errors_are_reported_then_retried(self) -> None:
        app = DownloaderApp.__new__(DownloaderApp)
        app.clipboard_autofill = _Variable(True)
        app._last_clipboard = ""
        app._last_autofilled_clipboard = ""
        app._last_clipboard_error = None
        app.url_entry = _Entry("https://manual.example/")
        app.root = Mock()
        app.progress_summary = _Variable()
        app.root.clipboard_get.return_value = "hello"

        app._watch_clipboard()

        self.assertEqual(app.url_entry.get(), "https://manual.example/")
        app.root.clipboard_get.side_effect = __import__("app_support").tk.TclError(
            "clipboard busy"
        )
        app._watch_clipboard()
        self.assertIn("Clipboard temporarily unavailable", app.progress_summary.get())
        self.assertEqual(app.root.after.call_count, 2)

        app.url_entry.delete(0, "end")
        app.root.clipboard_get.side_effect = None
        app.root.clipboard_get.return_value = "https://example.org/recovered"
        app._watch_clipboard()
        self.assertEqual(app.url_entry.get(), "https://example.org/recovered")
        self.assertIsNone(app._last_clipboard_error)

    def test_progress_event_rate_is_limited_to_twenty_per_second(self) -> None:
        app = DownloaderApp.__new__(DownloaderApp)
        app.events = queue.Queue()
        app._progress_lock = threading.Lock()
        app._last_progress_update = {}

        with patch("app_downloads.time.monotonic", side_effect=[i / 1000 for i in range(1000)]):
            for index in range(1000):
                app._emit_download_progress(
                    "job",
                    "Downloading",
                    float(index % 100),
                    f"{index} bytes",
                )

        self.assertLessEqual(app.events.qsize(), 21)
        while not app.events.empty():
            app.events.get_nowait()
        app._emit_download_progress("job", "Waiting for connection", None, "Retry")
        self.assertEqual(app.events.get_nowait()[2], "Waiting for connection")

    def test_worker_pool_runs_three_of_ten_downloads_concurrently(self) -> None:
        app = DownloaderApp.__new__(DownloaderApp)
        app.executor = ThreadPoolExecutor(max_workers=3)
        self.addCleanup(lambda: app.executor.shutdown(wait=True, cancel_futures=True))
        app.events = queue.Queue()
        app.bandwidth_limiter = GlobalBandwidthLimiter()
        app._progress_lock = threading.Lock()
        app._last_progress_update = {}
        app._job_finished = Mock()
        app._download_futures = {}
        app.cancel_events = {}
        app.resume_events = {}
        app.download_options = {}
        lock = threading.Lock()
        release = threading.Event()
        three_started = threading.Event()
        active = 0
        maximum_active = 0
        started = 0

        def fake_download(*_args: object, **_kwargs: object) -> str:
            nonlocal active, maximum_active, started
            with lock:
                active += 1
                started += 1
                maximum_active = max(maximum_active, active)
                if started >= 3:
                    three_started.set()
            if not release.wait(3):
                raise TimeoutError("test did not release worker")
            with lock:
                active -= 1
            return "saved"

        with patch("app_downloads.download_url", side_effect=fake_download):
            for index in range(10):
                job_id = str(index)
                app.cancel_events[job_id] = threading.Event()
                app.resume_events[job_id] = threading.Event()
                app.resume_events[job_id].set()
                app.download_options[job_id] = {
                    "url": f"https://example.org/{index}",
                    "destination": Path("."),
                    "source": "auto",
                    "mode": "video",
                    "quality": "best",
                    "playlist_scope": "auto",
                    "speed_mode": "fast",
                    "max_speed": None,
                    "proxy": "",
                    "browser_cookies": "none",
                }
                app._submit_download(job_id)

            self.assertTrue(three_started.wait(2))
            self.assertEqual(maximum_active, 3)
            self.assertEqual(sum(future.running() for future in app._download_futures.values()), 3)
            release.set()
            for future in app._download_futures.values():
                future.result(timeout=3)

        self.assertEqual(started, 10)
        self.assertEqual(maximum_active, 3)


class FilenameAndStorageChecklistTests(unittest.TestCase):
    def test_filenames_are_sanitized_and_length_limit_preserves_extension(self) -> None:
        self.assertEqual(_safe_filename('invalid<>:"|?*.zip'), "invalid_______.zip")
        self.assertEqual(_safe_filename("folder/name.zip"), "name.zip")
        self.assertEqual(_safe_filename("CON.txt"), "_CON.txt")
        self.assertEqual(_safe_filename("NUL.zip"), "_NUL.zip")
        self.assertEqual(_safe_filename("test.zip. "), "test.zip")

        safe = _safe_filename("a" * 240 + ".mp4")

        self.assertLessEqual(len(safe), 180)
        self.assertTrue(safe.endswith(".mp4"))
        self.assertEqual(_safe_filename("a" * 220 + ".tar.gz")[-7:], ".tar.gz")

    def test_long_unicode_destination_path_with_spaces_is_pathlib_safe(self) -> None:
        with TemporaryDirectory(prefix="downloader path with spaces ") as folder:
            directory = Path(folder) / ("測試" * 25) / "nested folder"
            directory.mkdir(parents=True)
            target = directory / _safe_filename("video name.mp4")
            target.write_bytes(b"content")

            self.assertEqual(target.read_bytes(), b"content")
            self.assertEqual(target.name, "video name.mp4")

    def test_file_assembly_retries_transient_antivirus_permission_errors(self) -> None:
        with TemporaryDirectory() as folder:
            source = Path(folder) / "output.part"
            destination = Path(folder) / "output.bin"
            source.write_bytes(b"complete")
            replace = Path.replace
            attempts = 0

            def locked_twice(path: Path, target: Path) -> Path:
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("file is temporarily locked")
                return replace(path, target)

            with patch.object(Path, "replace", locked_twice):
                _replace_with_retry(source, destination, threading.Event())

            self.assertEqual(attempts, 3)
            self.assertEqual(destination.read_bytes(), b"complete")
            self.assertFalse(source.exists())

    def test_file_assembly_surfaces_a_persistent_permission_error(self) -> None:
        with TemporaryDirectory() as folder:
            source = Path(folder) / "output.part"
            destination = Path(folder) / "output.bin"
            source.write_bytes(b"complete")

            with patch.object(
                Path,
                "replace",
                side_effect=PermissionError("file remains locked"),
            ):
                with self.assertRaisesRegex(PermissionError, "remains locked"):
                    _replace_with_retry(source, destination, threading.Event())


class BandwidthAndScheduleChecklistTests(unittest.TestCase):
    def test_zero_bandwidth_limit_is_safe_and_behaves_as_unlimited(self) -> None:
        limiter = GlobalBandwidthLimiter(1024)
        limiter.set_limit(0)

        self.assertTrue(limiter.acquire(1024 * 1024, threading.Event()))

    def test_raising_bandwidth_cap_releases_a_waiting_transfer(self) -> None:
        limiter = GlobalBandwidthLimiter(32)
        started = threading.Event()
        finished = threading.Event()
        result: list[bool] = []

        def acquire_bandwidth() -> None:
            started.set()
            result.append(limiter.acquire(128, threading.Event()))
            finished.set()

        worker = threading.Thread(target=acquire_bandwidth)
        worker.start()
        self.assertTrue(started.wait(1))
        limiter.set_limit(None)
        worker.join(timeout=1)

        self.assertTrue(finished.is_set())
        self.assertEqual(result, [True])

    def test_schedule_rejects_a_past_time(self) -> None:
        past = (datetime.now().astimezone() - timedelta(minutes=5)).strftime(
            "%Y-%m-%d %H:%M"
        )

        with self.assertRaisesRegex(ValueError, "future"):
            DownloaderApp._parse_scheduled_start(past)


class HistoryAndChecksumChecklistTests(unittest.TestCase):
    def test_concurrent_history_writes_and_sql_like_url_are_parameterized(self) -> None:
        with TemporaryDirectory() as folder:
            history = DownloadHistory(Path(folder) / "history.sqlite3")
            hostile_url = "https://example.org/file'; DROP TABLE downloads;--"

            def write_records(worker: int) -> list[int]:
                ids = []
                for index in range(10):
                    record_id = history.add(
                        f"https://example.org/{worker}/{index}",
                        "Complete",
                        folder,
                    )
                    history.update(
                        record_id,
                        "Complete",
                        "100%",
                        "saved",
                        folder,
                    )
                    ids.append(record_id)
                return ids

            with ThreadPoolExecutor(max_workers=5) as executor:
                all_ids = [
                    record_id
                    for group in executor.map(write_records, range(5))
                    for record_id in group
                ]
            hostile_id = history.add(hostile_url, "Complete", folder)
            history.update(hostile_id, "Complete", "100%", "saved", folder)

            records = history.list_records()
            self.assertEqual(len(all_ids), 50)
            self.assertEqual(len(records), 51)
            self.assertEqual(
                next(record.url for record in records if record.id == hostile_id),
                hostile_url,
            )

    def test_checksum_accepts_correct_md5_and_sha256_and_rejects_wrong_hash(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "payload.bin"
            path.write_bytes(b"checksum test")

            self.assertTrue(
                verify_checksum(path, "md5", "329999451b1de1a6a333fc24328d7c67")[1]
            )
            self.assertTrue(
                verify_checksum(
                    path,
                    "sha256",
                    "50743bc89b03b938f412094255c8e3cf1658b470dbc01d7db80a11dc39adfb9a",
                )[1]
            )
            self.assertFalse(verify_checksum(path, "md5", "0" * 32)[1])

    def test_checksum_reader_uses_bounded_chunks(self) -> None:
        reader = MagicMock()
        reader.__enter__.return_value = reader
        reader.read.side_effect = [b"a" * (1024 * 1024), b"b", b""]
        source = Mock()
        source.open.return_value = reader

        calculate_checksum(source, "sha256")

        self.assertEqual(
            reader.read.call_args_list,
            [unittest.mock.call(1024 * 1024)] * 3,
        )


class NotificationChecklistTests(unittest.TestCase):
    def test_notification_failure_is_reported_without_failing_completed_job(self) -> None:
        app = DownloaderApp.__new__(DownloaderApp)
        app.events = queue.Queue()
        app.events.put(("finished", "1", "Complete", "C:\\Downloads\\video.mp4"))
        app.jobs = _Jobs("1")
        app.jobs.rows["1"]["status"] = "Downloading"
        app.jobs.rows["1"]["location"] = ""
        app._refresh_job_style = Mock()
        app._apply_queue_filter = Mock()
        app._download_paths = {"1": Path("C:\\Downloads\\video.mp4")}
        app._job_destinations = {}
        app.verified_checksums = {}
        app.overall_progress = Mock()
        app.progress_summary = _Variable()
        app.root = Mock()
        app._persist_job = Mock()
        app.cancel_events = {"1": threading.Event()}
        app._download_futures = {}
        app.resume_events = {"1": threading.Event()}
        app.schedule_timers = {}
        app.download_options = {"1": {}}

        with (
            patch("app_events.notify", side_effect=OSError("toast unavailable")),
            patch("app_events.messagebox.showwarning") as showwarning,
        ):
            app._process_events()

        self.assertEqual(app.jobs.set("1", "status"), "Complete")
        self.assertIn("OS notification failed", app.progress_summary.get())
        showwarning.assert_called_once()


class TorrentProcessChecklistTests(unittest.TestCase):
    def test_cancelled_torrent_terminates_aria2_process(self) -> None:
        process = Mock()
        process.poll.return_value = None
        cancel_event = threading.Event()

        def progress(status, _percent, _details):
            if status == "Preparing torrent":
                cancel_event.set()

        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value="aria2c"),
            patch("torrent_engine.subprocess.Popen", return_value=process),
            patch("torrent_engine._rpc_port", return_value=45678),
        ):
            with self.assertRaises(DownloadCancelled):
                download_torrent(
                    "magnet:?xt=urn:btih:0123456789abcdef",
                    Path(folder),
                    cancel_event,
                    progress,
                )

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=3)

    def test_aria2_crash_is_reported_as_a_download_error(self) -> None:
        process = Mock()
        process.poll.return_value = 7
        process.returncode = 7

        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value="aria2c"),
            patch("torrent_engine.subprocess.Popen", return_value=process),
            patch("torrent_engine._rpc_port", return_value=45678),
        ):
            with self.assertRaisesRegex(RuntimeError, "exited with code 7"):
                download_torrent(
                    "magnet:?xt=urn:btih:0123456789abcdef",
                    Path(folder),
                    threading.Event(),
                    lambda *_args: None,
                )

        process.terminate.assert_not_called()

    def test_persistent_aria2_rpc_disconnect_fails_instead_of_polling_forever(self) -> None:
        process = Mock()
        process.poll.return_value = None

        with (
            TemporaryDirectory() as folder,
            patch("torrent_engine._find_aria2", return_value="aria2c"),
            patch("torrent_engine.subprocess.Popen", return_value=process),
            patch("torrent_engine._rpc_port", return_value=45678),
            patch(
                "torrent_engine._find_torrent_status",
                return_value={"gid": "gid", "infoHash": "hash"},
            ),
            patch(
                "torrent_engine._rpc_status",
                side_effect=urllib.error.URLError("RPC disconnected"),
            ),
            patch("torrent_engine.RPC_FAILURE_TIMEOUT", 0),
        ):
            with self.assertRaisesRegex(RuntimeError, "stopped responding"):
                download_torrent(
                    "magnet:?xt=urn:btih:0123456789abcdef",
                    Path(folder),
                    threading.Event(),
                    lambda *_args: None,
                )

        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=3)


class ImageSafetyChecklistTests(unittest.TestCase):
    def test_image_operations_translate_decompression_bomb_errors(self) -> None:
        operations = (
            lambda source: convert_image(source, "PNG"),
            lambda source: resize_image(source, 100, 100),
            strip_exif,
        )
        with TemporaryDirectory() as folder:
            source = Path(folder) / "large.png"
            source.write_bytes(b"not decoded because Pillow open is mocked")
            with patch(
                "PIL.Image.open",
                side_effect=Image.DecompressionBombError("too many pixels"),
            ):
                for operation in operations:
                    with self.subTest(operation=operation):
                        with self.assertRaisesRegex(ValueError, "safe processing limit"):
                            operation(source)

    def test_image_preview_reports_a_decompression_bomb(self) -> None:
        with TemporaryDirectory() as folder:
            source = Path(folder) / "large.png"
            source.write_bytes(b"mocked image")
            app = DownloaderApp.__new__(DownloaderApp)
            app.jobs = _Jobs()
            app._selected_output_path = Mock(return_value=source)
            app._download_paths = {}
            app.inspector_status = _Variable()
            app.preview_image_label = Mock()
            app.preview_details = Mock()
            app.current_thumbnail = None
            app.root = Mock()
            app._t = lambda text: text
            app._clear_thumbnail = Mock()

            with patch(
                "PIL.Image.open",
                side_effect=Image.DecompressionBombError("too many pixels"),
            ):
                app._show_selected_thumbnail()

        app._clear_thumbnail.assert_called_once()
        self.assertIn("safe preview limit", app._clear_thumbnail.call_args.args[0])

    def test_corrupt_image_raises_a_handled_image_error(self) -> None:
        with TemporaryDirectory() as folder:
            source = Path(folder) / "broken.png"
            source.write_bytes(b"broken image")

            with self.assertRaises(OSError):
                resize_image(source, 100, 100)


if __name__ == "__main__":
    unittest.main()
