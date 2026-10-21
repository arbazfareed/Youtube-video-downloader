from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from history_store import DownloadRecord


_TERMINAL_STATUSES = {"complete", "failed", "cancelled", "interrupted"}


@dataclass(frozen=True)
class DownloadStatistics:
    total_downloads: int
    completed: int
    failed: int
    cancelled: int
    interrupted: int
    active: int
    success_rate: float
    top_domains: tuple[tuple[str, int], ...]


def calculate_statistics(
    records: Iterable[DownloadRecord],
    *,
    top_limit: int = 5,
) -> DownloadStatistics:
    if top_limit < 0:
        raise ValueError("top_limit must be non-negative")

    records = tuple(records)
    statuses = Counter(record.status.casefold() for record in records)
    domains: Counter[str] = Counter()
    total_downloads = sum(statuses.values())
    for record in records:
        try:
            hostname = urlsplit(record.url).hostname
        except ValueError:
            hostname = None
        if hostname:
            domains[hostname.casefold()] += 1

    completed = statuses["complete"]
    failed = statuses["failed"]
    cancelled = statuses["cancelled"]
    interrupted = statuses["interrupted"]
    terminal = sum(statuses[status] for status in _TERMINAL_STATUSES)
    success_rate = completed / terminal * 100 if terminal else 0.0
    top_domains = tuple(
        sorted(domains.items(), key=lambda item: (-item[1], item[0]))[:top_limit]
    )
    return DownloadStatistics(
        total_downloads=total_downloads,
        completed=completed,
        failed=failed,
        cancelled=cancelled,
        interrupted=interrupted,
        active=total_downloads - terminal,
        success_rate=success_rate,
        top_domains=top_domains,
    )
