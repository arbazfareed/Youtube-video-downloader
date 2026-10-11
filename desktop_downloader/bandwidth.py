from __future__ import annotations

import threading
import time


class GlobalBandwidthLimiter:
    def __init__(self, limit: int | None = None) -> None:
        self._lock = threading.Lock()
        self._limit = limit
        self._capacity = min(limit, 64 * 1024) if limit else 0
        self._tokens = float(self._capacity)
        self._updated_at = time.monotonic()

    def set_limit(self, limit: int | None) -> None:
        with self._lock:
            self._limit = limit
            self._capacity = min(limit, 64 * 1024) if limit else 0
            self._tokens = min(self._tokens, float(self._capacity))
            self._updated_at = time.monotonic()

    def acquire(
        self,
        size: int,
        cancel_event: threading.Event,
        resume_event: threading.Event | None = None,
    ) -> bool:
        if size <= 0:
            return True

        remaining = size
        while remaining:
            if cancel_event.is_set():
                return False
            if resume_event is not None and not resume_event.is_set():
                resume_event.wait(0.1)
                continue
            with self._lock:
                limit = self._limit
                if limit is None or limit <= 0:
                    return True

                now = time.monotonic()
                self._tokens = min(
                    float(self._capacity),
                    self._tokens + (now - self._updated_at) * limit,
                )
                self._updated_at = now
                portion = min(remaining, max(1, limit // 10), self._capacity)
                if self._tokens >= portion:
                    self._tokens -= portion
                    remaining -= portion
                    continue
                wait = (portion - self._tokens) / limit
            cancel_event.wait(min(wait, 0.1))
        return not cancel_event.is_set()
