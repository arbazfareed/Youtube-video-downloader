from __future__ import annotations

import re


def normalize_playlist_items(value: str) -> str:
    """Validate yt-dlp playlist index/range syntax and return a canonical form."""
    text = (value or "").strip().replace(" ", "")
    if not text:
        return ""
    parts = text.split(",")
    normalized = []
    total = 0
    for part in parts:
        if not part:
            raise ValueError("Playlist selection contains an empty item.")
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not match:
            raise ValueError("Use playlist positions such as 1,3,5-8.")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise ValueError("Playlist positions must be positive and ranges must ascend.")
        total += end - start + 1
        if total > 10000:
            raise ValueError("Select no more than 10,000 playlist entries at once.")
        normalized.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(normalized)
