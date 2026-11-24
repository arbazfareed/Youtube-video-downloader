from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProxyEntry:
    country: str | None
    url: str


def parse_proxy_entries(value: str | None) -> tuple[ProxyEntry, ...]:
    if not value or not value.strip():
        return ()

    entries = []
    for candidate in value.split(","):
        raw = candidate.strip()
        country = None
        proxy = raw
        label, separator, remainder = raw.partition("=")
        if separator and re.fullmatch(r"[A-Za-z]{2}", label.strip()):
            country = label.strip().upper()
            proxy = remainder.strip()
        try:
            parsed = urlsplit(proxy)
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError as error:
            raise ValueError("Proxy entries must be valid HTTP(S) or SOCKS5 URLs.") from error
        if (
            parsed.scheme.lower() not in {"http", "https", "socks5", "socks5h"}
            or not parsed.hostname
            or not valid_port
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Proxy entries must use http://, https://, socks5://, or socks5h:// "
                "and include a host and optional port."
            )
        entries.append(ProxyEntry(country, proxy))
    return tuple(entries)


def parse_proxy_list(value: str | None) -> tuple[str, ...]:
    """Return proxy URLs, preserving the legacy public API."""
    return tuple(entry.url for entry in parse_proxy_entries(value))


class ProxyRotator:
    def __init__(self, value: str | None = None) -> None:
        self._entries = parse_proxy_entries(value)
        self._proxies = tuple(entry.url for entry in self._entries)
        self._index = 0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)

    @property
    def count(self) -> int:
        return len(self._proxies)

    def ordered_urls(self, allowed_countries: tuple[str, ...] | list[str] = ()) -> list[str]:
        """Rotate the pool and put country-tagged allowed exits first."""
        if not self._entries:
            return []
        allowed = {country.upper() for country in allowed_countries}
        with self._lock:
            start = self._index
            self._index = (self._index + 1) % len(self._entries)
            rotated = list(self._entries[start:]) + list(self._entries[:start])
        if not allowed:
            return [entry.url for entry in rotated]
        preferred = [entry.url for entry in rotated if entry.country in allowed]
        unlabelled = [entry.url for entry in rotated if entry.country is None]
        other_regions = [
            entry.url for entry in rotated
            if entry.country is not None and entry.country not in allowed
        ]
        return preferred + unlabelled + other_regions

    def next_requests_proxy(self) -> dict[str, str] | None:
        if not self._proxies:
            return None
        with self._lock:
            proxy = self._proxies[self._index]
            self._index = (self._index + 1) % len(self._proxies)
        return {"http": proxy, "https": proxy}

    def current_requests_proxy(self) -> dict[str, str] | None:
        if not self._proxies:
            return None
        with self._lock:
            proxy = self._proxies[self._index]
        return {"http": proxy, "https": proxy}

    def next_url(self) -> str | None:
        selected = self.next_requests_proxy()
        return selected["https"] if selected else None
