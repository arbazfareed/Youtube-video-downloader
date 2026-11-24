from __future__ import annotations

from pathlib import Path


def inspect_download(path: str | Path) -> tuple[bool, str]:
    """Reject missing/empty outputs and common HTML error pages masquerading as media."""
    target = Path(path)
    if not target.exists():
        return False, f"Expected output was not created: {target}"
    if target.is_dir():
        candidates = [
            item for item in target.rglob("*")
            if item.is_file()
            and not item.name.lower().endswith((".part", ".ytdl", ".tmp"))
        ]
        if not candidates:
            return False, "The downloader finished but the output folder contains no completed files."
        empty = [item for item in candidates if item.stat().st_size == 0]
        if len(empty) == len(candidates):
            return False, "The output folder contains only empty files."
        return True, f"Output folder contains {len(candidates)} file(s)."
    if not target.is_file():
        return False, "The download output is not a regular file."
    if target.stat().st_size <= 0:
        return False, "The downloaded file is empty (0 bytes)."
    try:
        with target.open("rb") as stream:
            prefix = stream.read(4096).lstrip().lower()
    except OSError as error:
        return False, f"Cannot read the downloaded output: {error}"
    if prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return False, "The server returned an HTML page instead of media bytes (often a sign-in, block, or expired-link page)."
    if prefix.startswith(b'{"error"') or prefix.startswith(b'{"message"'):
        return False, "The server returned a JSON error response instead of a media file."
    return True, f"File health check passed ({target.stat().st_size:,} bytes)."
