import threading
import time
import unittest

from download_scheduler import (
    DEFAULT_PARALLEL_DOWNLOADS,
    DownloadScheduler,
    clamp_parallel_downloads,
)


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Probe:
    """Tracks how many fake downloads run at once."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = set()
        self.peak = 0
        self.finished = []

    def enter(self, name):
        with self.lock:
            self.running.add(name)
            self.peak = max(self.peak, len(self.running))

    def leave(self, name):
        with self.lock:
            self.running.discard(name)
            self.finished.append(name)


def blocking_download(probe, name, release, gate=None):
    """Behaves like the engine: runs until released, polling the pause gate."""
    probe.enter(name)
    try:
        while not release.is_set():
            if gate is not None:
                while not gate.is_set():
                    if release.is_set():
                        return name
                    gate.wait(0.02)
            time.sleep(0.005)
        return name
    finally:
        probe.leave(name)


class ParallelLimitTests(unittest.TestCase):
    def test_default_and_clamping(self):
        self.assertEqual(DEFAULT_PARALLEL_DOWNLOADS, 3)
        self.assertEqual(clamp_parallel_downloads("5"), 5)
        self.assertEqual(clamp_parallel_downloads("0"), 1)
        self.assertEqual(clamp_parallel_downloads("99"), 10)
        self.assertEqual(clamp_parallel_downloads("abc"), 3)
        self.assertEqual(clamp_parallel_downloads(None, default=4), 4)

    def test_never_runs_more_than_the_limit_and_finishes_every_download(self):
        scheduler = DownloadScheduler(3)
        probe, release = Probe(), threading.Event()
        futures = [
            scheduler.submit(str(i), blocking_download, probe, str(i), release)
            for i in range(8)
        ]
        self.assertTrue(wait_until(lambda: len(probe.running) == 3))
        time.sleep(0.1)
        self.assertEqual(len(probe.running), 3)
        self.assertEqual(scheduler.pending_count, 5)
        release.set()
        for future in futures:
            future.result(timeout=5)
        self.assertEqual(probe.peak, 3)
        self.assertEqual(len(probe.finished), 8)
        self.assertEqual(scheduler.active_count, 0)

    def test_queued_downloads_start_in_order(self):
        scheduler = DownloadScheduler(1)
        order, release = [], threading.Event()

        def job(name):
            order.append(name)
            release.wait(5)

        futures = [scheduler.submit(str(i), job, str(i)) for i in range(4)]
        for _ in range(4):
            time.sleep(0.05)
            release.set()
        for future in futures:
            future.result(timeout=5)
        self.assertEqual(order, ["0", "1", "2", "3"])

    def test_raising_the_limit_starts_waiting_downloads_immediately(self):
        scheduler = DownloadScheduler(1)
        probe, release = Probe(), threading.Event()
        futures = [scheduler.submit(str(i), blocking_download, probe, str(i), release) for i in range(3)]
        self.assertTrue(wait_until(lambda: len(probe.running) == 1))
        scheduler.set_max_parallel(3)
        self.assertTrue(wait_until(lambda: len(probe.running) == 3))
        release.set()
        for future in futures:
            future.result(timeout=5)

    def test_errors_reach_the_future_and_free_the_slot(self):
        scheduler = DownloadScheduler(1)

        def fail():
            raise RuntimeError("boom")

        failing = scheduler.submit("a", fail)
        following = scheduler.submit("b", lambda: "ok")
        with self.assertRaises(RuntimeError):
            failing.result(timeout=5)
        self.assertEqual(following.result(timeout=5), "ok")

    def test_slot_is_free_before_done_callbacks_run(self):
        """Slow post-processing in a done-callback must not block the next download."""
        scheduler = DownloadScheduler(1)
        started_second = threading.Event()
        callback_release = threading.Event()
        first = scheduler.submit("a", lambda: "a")
        first.add_done_callback(lambda _f: callback_release.wait(5))
        scheduler.submit("b", started_second.set)
        self.assertTrue(started_second.wait(2), "second download waited for the first one's callback")
        callback_release.set()


class CancelAndShutdownTests(unittest.TestCase):
    def test_cancelling_a_queued_download_skips_it_and_keeps_counts_right(self):
        scheduler = DownloadScheduler(1)
        probe, release = Probe(), threading.Event()
        ran = []
        first = scheduler.submit("a", blocking_download, probe, "a", release)
        queued = scheduler.submit("b", lambda: ran.append("b"))
        last = scheduler.submit("c", lambda: ran.append("c"))
        self.assertTrue(wait_until(lambda: "a" in probe.running))
        self.assertTrue(queued.cancel())
        release.set()
        first.result(timeout=5)
        last.result(timeout=5)
        self.assertEqual(ran, ["c"])
        self.assertTrue(queued.cancelled())
        self.assertTrue(wait_until(lambda: scheduler.active_count == 0))

    def test_shutdown_cancels_queued_downloads_and_rejects_new_ones(self):
        scheduler = DownloadScheduler(1)
        probe, release = Probe(), threading.Event()
        scheduler.submit("a", blocking_download, probe, "a", release)
        queued = scheduler.submit("b", lambda: None)
        self.assertTrue(wait_until(lambda: "a" in probe.running))
        scheduler.shutdown()
        self.assertTrue(queued.cancelled())
        with self.assertRaises(RuntimeError):
            scheduler.submit("c", lambda: None)
        release.set()


class PauseTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = DownloadScheduler(3)
        self.probe = Probe()
        self.release = threading.Event()
        self.user_events = {}
        self.futures = {}

    def tearDown(self):
        self.release.set()
        for event in self.user_events.values():
            event.set()
        for future in self.futures.values():
            future.result(timeout=5)

    def start(self, name):
        user_event = threading.Event()
        user_event.set()
        self.user_events[name] = user_event
        gate = self.scheduler.gate(name, user_event)
        self.futures[name] = self.scheduler.submit(
            name, blocking_download, self.probe, name, self.release, gate
        )

    def test_pausing_three_downloads_lets_a_fourth_start(self):
        for name in "abc":
            self.start(name)
        self.assertTrue(wait_until(lambda: len(self.probe.running) == 3))
        for name in "abc":
            self.user_events[name].clear()  # the user presses Pause
        self.start("d")
        self.assertTrue(
            wait_until(lambda: "d" in self.probe.running),
            "a fourth download could not start while the others were paused",
        )
        self.assertEqual(self.scheduler.active_count, 1)

    def test_resumed_download_waits_for_a_free_slot(self):
        for name in "abc":
            self.start(name)
        self.assertTrue(wait_until(lambda: self.scheduler.active_count == 3))
        self.user_events["a"].clear()
        self.assertTrue(wait_until(lambda: self.scheduler.active_count == 2))
        self.start("d")
        self.assertTrue(wait_until(lambda: self.scheduler.active_count == 3))
        self.user_events["a"].set()  # resume while all three slots are taken
        time.sleep(0.3)
        self.assertEqual(self.scheduler.active_count, 3)
        gate_a = self.scheduler.gate("a", self.user_events["a"])
        self.assertFalse(gate_a.is_set(), "resumed download took a slot that did not exist")
        # The moment another download pauses, the resumed one continues.
        self.user_events["b"].clear()
        self.assertTrue(wait_until(gate_a.is_set))
        self.assertEqual(self.scheduler.active_count, 3)

    def test_pausing_and_resuming_never_exceeds_the_limit(self):
        for name in "abcdef":
            self.start(name)
        for _ in range(5):
            for name in "abc":
                self.user_events[name].clear()
            time.sleep(0.05)
            for name in "abc":
                self.user_events[name].set()
            time.sleep(0.05)
        self.assertLessEqual(self.probe.peak, 6)
        self.assertLessEqual(self.scheduler.active_count, 3)

    def test_gate_never_takes_a_slot_after_its_download_finished(self):
        user_event = threading.Event()
        user_event.set()
        gate = self.scheduler.gate("x", user_event)
        scheduler_future = self.scheduler.submit("x", lambda: None)
        scheduler_future.result(timeout=5)
        self.assertTrue(wait_until(lambda: self.scheduler.active_count == 0))
        self.assertTrue(gate.is_set())  # follows the user event only
        user_event.clear()
        self.assertFalse(gate.is_set())
        self.assertEqual(self.scheduler.active_count, 0)


if __name__ == "__main__":
    unittest.main()
