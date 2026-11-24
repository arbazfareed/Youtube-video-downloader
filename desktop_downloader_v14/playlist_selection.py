from __future__ import annotations

import re


def normalize_playlist_items(value: str) -> str:
    """Validate yt-dlp playlist index/range syntax and return a canonical form."""
    text = (value or "").strip().replace(" ", "")
    if not text:
        return ""
    parts = text.split(",")
    ranges = []
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
        ranges.append((start, end))

    # Canonicalize the union, not the raw input: overlapping or repeated
    # positions otherwise reach yt-dlp more than once and can duplicate files.
    ranges.sort()
    merged = []
    total = 0
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    total = sum(end - start + 1 for start, end in merged)
    if total > 10000:
        raise ValueError("Select no more than 10,000 playlist entries at once.")
    return ",".join(
        str(start) if start == end else f"{start}-{end}"
        for start, end in merged
    )
