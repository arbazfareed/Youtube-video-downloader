"""Remember where each video stopped, so the Smart Player can continue from there."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

MIN_REMEMBER_MS = 10_000        # stopped in the first 10 s: just start from the beginning
END_MARGIN_MS = 10_000          # stopped in the last 10 s: counts as finished
MAX_ENTRIES = 500


def default_path() -> Path:
    root = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_DATA_HOME")
        or str(Path.home() / ".local" / "share")
    )
    return Path(root) / "SmartDownloader14" / "resume_positions.json"


class ResumeStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else default_path()
        self._lock = threading.Lock()

    @staticmethod
    def _key(media: Path | str) -> str:
        try:
            return str(Path(media).resolve())
        except OSError:
            return str(media)

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        if len(data) > MAX_ENTRIES:
            newest = sorted(data.items(), key=lambda item: item[1].get("saved", 0), reverse=True)
            data = dict(newest[:MAX_ENTRIES])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        os.replace(temporary, self.path)

    def get(self, media: Path | str) -> int | None:
        """Milliseconds to continue from, or None to start at the beginning."""
        entry = self._read().get(self._key(media))
        try:
            position = int(entry["position"])
        except (TypeError, KeyError, ValueError):
            return None
        return position if position >= MIN_REMEMBER_MS else None

    def forget(self, media: Path | str) -> None:
        with self._lock:
            data = self._read()
            if data.pop(self._key(media), None) is not None:
                self._write(data)

    def save(self, media: Path | str, position_ms: int, duration_ms: int) -> None:
        if duration_ms <= 0:      # live or unknown length: nothing sensible to resume
            return
        if position_ms < MIN_REMEMBER_MS or position_ms > duration_ms - END_MARGIN_MS:
            self.forget(media)
            return
        with self._lock:
            data = self._read()
            data[self._key(media)] = {
                "position": int(position_ms), "duration": int(duration_ms), "saved": time.time(),
            }
            self._write(data)
