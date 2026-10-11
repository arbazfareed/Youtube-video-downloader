from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


_LOCK = threading.Lock()
_MAX_BYTES = 1_000_000
_MAX_BACKUPS = 3


def diagnostics_path() -> Path:
    data_root = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_DATA_HOME")
        or str(Path.home() / ".local" / "share")
    )
    return Path(data_root) / "SmartDownloader12" / "diagnostics.jsonl"


def record_diagnostic(
    enabled: bool,
    component: str,
    error: BaseException,
    path: Path | None = None,
) -> bool:
    if not enabled:
        return False
    target = path or diagnostics_path()
    event = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "component": component[:80],
        "error_type": type(error).__name__[:120],
    }
    encoded = json.dumps(event, ensure_ascii=True) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if target.exists() and target.stat().st_size + len(encoded.encode("utf-8")) > _MAX_BYTES:
            for backup_index in range(_MAX_BACKUPS, 0, -1):
                source = target.with_suffix(f".jsonl.{backup_index - 1}") if backup_index > 1 else target
                destination = target.with_suffix(f".jsonl.{backup_index}")
                if source.exists():
                    if backup_index == _MAX_BACKUPS:
                        destination.unlink(missing_ok=True)
                    source.replace(destination)
        with target.open("a", encoding="utf-8") as output:
            output.write(encoded)
    return True


def export_diagnostics(destination: Path, source: Path | None = None) -> Path:
    diagnostic_file = source or diagnostics_path()
    backups = [
        diagnostic_file.with_suffix(f".jsonl.{index}")
        for index in range(_MAX_BACKUPS, 0, -1)
    ]
    sources = [path for path in (*backups, diagnostic_file) if path.is_file()]
    if not sources:
        raise FileNotFoundError("No local diagnostic events have been recorded.")
    destination = destination.expanduser()
    if destination.resolve() in {path.resolve() for path in sources}:
        raise ValueError("Choose a different file for the diagnostic export.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        for path in sources:
            with path.open("rb") as source_file:
                while chunk := source_file.read(64 * 1024):
                    output.write(chunk)
    return destination
