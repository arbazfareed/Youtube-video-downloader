from __future__ import annotations

from pathlib import Path

_IGNORED_SUFFIXES = (".part", ".ytdl", ".tmp")


def _inspect_file(target: Path) -> tuple[bool, str]:
    """Check one completed file for empty or obvious server-error content."""
    try:
        size = target.stat().st_size
        if size <= 0:
            return False, "empty file"
        with target.open("rb") as stream:
            prefix = stream.read(4096).lstrip().lower()
    except OSError as error:
        return False, f"cannot read file ({error})"

    if prefix.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return False, "HTML error page"
    if prefix.startswith((b'{"error"', b'{"message"')):
        return False, "JSON error response"
    return True, f"{size:,} bytes"


def inspect_download(path: str | Path) -> tuple[bool, str]:
    """Reject missing, empty, or error-page outputs, including playlist folders."""
    target = Path(path)
    if not target.exists():
        return False, f"Expected output was not created: {target}"
    if target.is_dir():
        candidates = [
            item for item in target.rglob("*")
            if item.is_file() and not item.name.lower().endswith(_IGNORED_SUFFIXES)
        ]
        if not candidates:
            return False, "The downloader finished but the output folder contains no completed files."

        healthy: list[Path] = []
        rejected: list[tuple[Path, str]] = []
        for item in candidates:
            valid, reason = _inspect_file(item)
            (healthy if valid else rejected).append(item if valid else (item, reason))

        if not healthy:
            reasons = sorted({reason for _, reason in rejected})
            return False, (
                "The output folder contains no valid completed files. "
                f"Rejected {len(rejected)} file(s): {', '.join(reasons)}."
            )
        detail = f"Output folder health check passed ({len(healthy)} valid file(s))."
        if rejected:
            detail += f" Skipped {len(rejected)} empty/error file(s)."
        return True, detail

    if not target.is_file():
        return False, "The download output is not a regular file."
    valid, reason = _inspect_file(target)
    if not valid:
        if reason == "empty file":
            return False, "The downloaded file is empty (0 bytes)."
        if reason == "HTML error page":
            return False, "The server returned an HTML page instead of media bytes (often a sign-in, block, or expired-link page)."
        if reason == "JSON error response":
            return False, "The server returned a JSON error response instead of a media file."
        return False, f"Cannot validate the downloaded output: {reason}."
    return True, f"File health check passed ({reason})."
