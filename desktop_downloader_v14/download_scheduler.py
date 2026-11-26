"""Runs several downloads at once without starving the rest of the app.

Before this module, downloads shared one three-thread pool with everything else
(YouTube search, update checks, format inspection, MP3 conversion). Three long
downloads therefore froze all of those, and a paused download kept its thread,
so pausing three downloads blocked every new one.

The scheduler fixes both problems:

* It limits how many downloads are *actively running*, not how many exist.
* Queued downloads wait in a plain queue and use no thread.
* A paused download gives its slot to the next queued download and waits for a
  free slot again when it is resumed.
"""

from __future__ import annotations

import threading
from collections import deque
from concurrent.futures import Future
from typing import Any, Callable

DEFAULT_PARALLEL_DOWNLOADS = 3
MIN_PARALLEL_DOWNLOADS = 1
MAX_PARALLEL_DOWNLOADS = 10


def clamp_parallel_downloads(value: object, default: int = DEFAULT_PARALLEL_DOWNLOADS) -> int:
    """Return a valid parallel-download count from user or saved input."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(MIN_PARALLEL_DOWNLOADS, min(MAX_PARALLEL_DOWNLOADS, number))


class SlotGate:
    """Drop-in replacement for the ``threading.Event`` the download engine polls.

    The engine only calls ``is_set()`` and ``wait()``. While the user has the
    download paused, the gate hands its slot back; once the user resumes, it
    reports "set" only after a slot is available again.
    """

    def __init__(
        self,
        scheduler: "DownloadScheduler",
        job_id: str,
        user_event: threading.Event,
    ) -> None:
        self._scheduler = scheduler
        self._job_id = job_id
        self._user_event = user_event

    def is_set(self) -> bool:
        return self._scheduler._gate_is_set(self._job_id, self._user_event)

    def wait(self, timeout: float | None = None) -> bool:
        return self._scheduler._gate_wait(self._job_id, self._user_event, timeout)

    def set(self) -> None:
        self._user_event.set()

    def clear(self) -> None:
        self._user_event.clear()


_Entry = tuple[str, Future, Callable[..., Any], tuple, dict]


class DownloadScheduler:
    def __init__(self, max_parallel: object = DEFAULT_PARALLEL_DOWNLOADS) -> None:
        self._cond = threading.Condition()
        self._max = clamp_parallel_downloads(max_parallel)
        self._active: set[str] = set()
        self._live: set[str] = set()
        self._pending: deque[_Entry] = deque()
        self._resume_waiters: deque[str] = deque()
        self._closed = False

    # ----- public API -------------------------------------------------

    @property
    def max_parallel(self) -> int:
        with self._cond:
            return self._max

    @property
    def active_count(self) -> int:
        with self._cond:
            return len(self._active)

    @property
    def pending_count(self) -> int:
        with self._cond:
            return len(self._pending)

    def set_max_parallel(self, value: object) -> int:
        launch: list[_Entry] = []
        with self._cond:
            self._max = clamp_parallel_downloads(value, self._max)
            launch = self._pump_locked()
            self._cond.notify_all()
            result = self._max
        self._launch(launch)
        return result

    def gate(self, job_id: str, user_event: threading.Event) -> SlotGate:
        return SlotGate(self, job_id, user_event)

    def submit(self, job_id: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        """Queue ``fn``; it starts as soon as fewer than ``max_parallel`` are running."""
        future: Future = Future()
        with self._cond:
            if self._closed:
                raise RuntimeError("The download scheduler is shut down.")
            self._pending.append((job_id, future, fn, args, kwargs))
            launch = self._pump_locked()
        self._launch(launch)
        return future

    def shutdown(self) -> None:
        """Stop starting queued downloads. Running ones end through their cancel events."""
        with self._cond:
            self._closed = True
            pending = list(self._pending)
            self._pending.clear()
            self._cond.notify_all()
        for _, future, *_rest in pending:
            future.cancel()

    # ----- internals --------------------------------------------------

    def _pump_locked(self) -> list[_Entry]:
        """Grant free slots. Resumed downloads go first, then new ones in order."""
        launch: list[_Entry] = []
        granted = False
        while len(self._active) < self._max:
            if self._resume_waiters:
                self._active.add(self._resume_waiters.popleft())
                granted = True
                continue
            if not self._pending or self._closed:
                break
            entry = self._pending.popleft()
            self._active.add(entry[0])
            self._live.add(entry[0])
            launch.append(entry)
        if granted:
            self._cond.notify_all()
        return launch

    def _launch(self, entries: list[_Entry]) -> None:
        # Runs outside the lock because cancelling a future calls user callbacks.
        for job_id, future, fn, args, kwargs in entries:
            if not future.set_running_or_notify_cancel():
                with self._cond:
                    self._active.discard(job_id)
                    self._live.discard(job_id)
                    more = self._pump_locked()
                self._launch(more)
                continue
            threading.Thread(
                target=self._run,
                args=(job_id, future, fn, args, kwargs),
                name=f"download-{job_id}",
                daemon=True,
            ).start()

    def _run(
        self,
        job_id: str,
        future: Future,
        fn: Callable[..., Any],
        args: tuple,
        kwargs: dict,
    ) -> None:
        try:
            result = fn(*args, **kwargs)
        except BaseException as error:  # noqa: BLE001 - mirrors ThreadPoolExecutor
            self._finish(job_id)
            future.set_exception(error)
        else:
            # Free the slot before the future's done-callbacks run, so slow
            # post-processing (hashing, cloud upload) never blocks the next download.
            self._finish(job_id)
            future.set_result(result)

    def _finish(self, job_id: str) -> None:
        with self._cond:
            self._active.discard(job_id)
            self._live.discard(job_id)
            if job_id in self._resume_waiters:
                self._resume_waiters.remove(job_id)
            launch = self._pump_locked()
            self._cond.notify_all()
        self._launch(launch)

    def _gate_is_set(self, job_id: str, user_event: threading.Event) -> bool:
        launch: list[_Entry] = []
        with self._cond:
            if job_id not in self._live:
                return user_event.is_set()
            if not user_event.is_set():
                if job_id in self._resume_waiters:
                    self._resume_waiters.remove(job_id)
                if job_id in self._active:
                    self._active.discard(job_id)
                    launch = self._pump_locked()
                    self._cond.notify_all()
                result = False
            elif job_id in self._active:
                result = True
            else:
                if job_id not in self._resume_waiters:
                    self._resume_waiters.append(job_id)
                launch = self._pump_locked()
                result = job_id in self._active
        self._launch(launch)
        return result

    def _gate_wait(
        self,
        job_id: str,
        user_event: threading.Event,
        timeout: float | None,
    ) -> bool:
        if not user_event.is_set():
            user_event.wait(timeout)
            return self._gate_is_set(job_id, user_event)
        if self._gate_is_set(job_id, user_event):
            return True
        with self._cond:
            self._cond.wait_for(
                lambda: job_id in self._active or job_id not in self._live,
                timeout,
            )
        return self._gate_is_set(job_id, user_event)
