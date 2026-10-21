from __future__ import annotations

import threading
from urllib.parse import urlsplit


def parse_proxy_list(value: str | None) -> tuple[str, ...]:
    if not value or not value.strip():
        return ()

    proxies = []
    for candidate in value.split(","):
        proxy = candidate.strip()
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
        proxies.append(proxy)
    return tuple(proxies)


class ProxyRotator:
    def __init__(self, value: str | None = None) -> None:
        self._proxies = parse_proxy_list(value)
        self._index = 0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._proxies)

    @property
    def count(self) -> int:
        return len(self._proxies)

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
