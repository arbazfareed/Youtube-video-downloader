from __future__ import annotations

import queue
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from app import DownloaderApp
from bandwidth import GlobalBandwidthLimiter
from download_scheduler import DownloadScheduler, SlotGate


class _Variable:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class _Entry(_Variable):
    def delete(self, *_args: object) -> None:
        self.value = ""


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def make_app(max_parallel: int = 3) -> DownloaderApp:
    app = DownloaderApp.__new__(DownloaderApp)
    app.executor = ThreadPoolExecutor(max_workers=3)
    app.download_scheduler = DownloadScheduler(max_parallel)
    app.events = queue.Queue()
    app.bandwidth_limiter = GlobalBandwidthLimiter()
    app._progress_lock = threading.Lock()
    app._last_progress_update = {}
    app._job_finished = Mock()
    app._download_futures = {}
    app.cancel_events = {}
    app.resume_events = {}
    app.download_options = {}
    return app


def register_job(app: DownloaderApp, job_id: str) -> None:
    app.cancel_events[job_id] = threading.Event()
    app.resume_events[job_id] = threading.Event()
    app.resume_events[job_id].set()
    app.download_options[job_id] = {
        "url": f"https://example.org/{job_id}",
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


class ParallelDownloadWiringTests(unittest.TestCase):
    def setUp(self):
        self.app = make_app()
        self.release = threading.Event()
        self.running = set()
        self.peak = 0
        self.gates = {}
        self.lock = threading.Lock()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.release.set()
        for event in self.app.resume_events.values():
            event.set()
        for future in self.app._download_futures.values():
            if not future.cancelled():
                future.result(timeout=5)
        if self.app.download_scheduler is not None:
            self.app.download_scheduler.shutdown()
        self.app.executor.shutdown(wait=True, cancel_futures=True)

    def fake_download(self, url, *args, **_kwargs):
        name = url.rsplit("/", 1)[1]
        gate = args[8]  # resume event argument handed to the engine
        with self.lock:
            self.gates[name] = gate
            self.running.add(name)
            self.peak = max(self.peak, len(self.running))
        try:
            while not self.release.is_set():
                while not gate.is_set():
                    if self.release.is_set():
                        return "saved"
                    gate.wait(0.02)
                time.sleep(0.005)
            return "saved"
        finally:
            with self.lock:
                self.running.discard(name)

    def test_ten_downloads_run_three_at_a_time_and_all_finish(self):
        with patch("app_downloads.download_url", side_effect=self.fake_download):
            for index in range(10):
                register_job(self.app, str(index))
                self.app._submit_download(str(index))
            self.assertTrue(wait_until(lambda: len(self.running) == 3))
            time.sleep(0.1)
            self.assertEqual(self.peak, 3)
            self.release.set()
            for future in self.app._download_futures.values():
                self.assertEqual(future.result(timeout=5), "saved")
        self.assertEqual(self.peak, 3)

    def test_engine_receives_a_pause_gate_not_the_raw_event(self):
        with patch("app_downloads.download_url", side_effect=self.fake_download):
            register_job(self.app, "0")
            self.app._submit_download("0")
            self.assertTrue(wait_until(lambda: "0" in self.gates))
        self.assertIsInstance(self.gates["0"], SlotGate)

    def test_background_tasks_are_not_blocked_by_running_downloads(self):
        with patch("app_downloads.download_url", side_effect=self.fake_download):
            for index in range(3):
                register_job(self.app, str(index))
                self.app._submit_download(str(index))
            self.assertTrue(wait_until(lambda: len(self.running) == 3))
            # Stands in for a YouTube search, update check or MP3 conversion.
            self.assertEqual(self.app.executor.submit(lambda: "done").result(timeout=1), "done")

    def test_pausing_downloads_lets_new_ones_start(self):
        with patch("app_downloads.download_url", side_effect=self.fake_download):
            for index in range(3):
                register_job(self.app, str(index))
                self.app._submit_download(str(index))
            self.assertTrue(wait_until(lambda: len(self.running) == 3))
            for index in range(3):
                self.app.resume_events[str(index)].clear()  # user presses Pause
            register_job(self.app, "3")
            self.app._submit_download("3")
            self.assertTrue(
                wait_until(lambda: "3" in self.running),
                "a new download stayed queued while three others were paused",
            )

    def test_cancelling_a_queued_download_never_starts_it(self):
        with patch("app_downloads.download_url", side_effect=self.fake_download):
            for index in range(4):
                register_job(self.app, str(index))
                self.app._submit_download(str(index))
            self.assertTrue(wait_until(lambda: len(self.running) == 3))
            self.assertTrue(self.app._download_futures["3"].cancel())
            self.release.set()
            self.app._download_futures["0"].result(timeout=5)
            time.sleep(0.1)
        self.assertNotIn("3", self.gates)

    def test_without_a_scheduler_downloads_still_use_the_shared_pool(self):
        self.app.download_scheduler = None
        with patch("app_downloads.download_url", side_effect=lambda *a, **k: "saved"):
            register_job(self.app, "0")
            self.app._submit_download("0")
            self.assertEqual(self.app._download_futures["0"].result(timeout=3), "saved")


class PastedLinksAddDownloadTests(unittest.TestCase):
    def _app(self, text: str) -> DownloaderApp:
        app = DownloaderApp.__new__(DownloaderApp)
        app.url_entry = _Entry(text)
        app.link_feedback_var = _Variable()
        app._add_batch_urls = Mock(return_value=(2, 2))
        return app

    def test_several_pasted_links_are_queued_as_separate_downloads(self):
        app = self._app("https://youtu.be/AAAAAAAAAAA\nhttps://youtu.be/BBBBBBBBBBB")
        app.add_download()
        app._add_batch_urls.assert_called_once_with(
            ["https://youtu.be/AAAAAAAAAAA", "https://youtu.be/BBBBBBBBBBB"]
        )
        self.assertEqual(app.url_entry.get(), "")
        self.assertIn("Added 2 of 2", app.link_feedback_var.get())

    def test_a_single_link_does_not_go_through_the_batch_path(self):
        app = self._app("youtu.be/AAAAAAAAAAA")

        class Stop(Exception):
            pass

        app.destination = Mock()
        app.destination.get.side_effect = Stop
        with self.assertRaises(Stop):  # got past the multi-link check to the normal path
            app.add_download()
        app._add_batch_urls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
