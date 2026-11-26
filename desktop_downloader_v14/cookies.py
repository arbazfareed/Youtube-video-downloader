from __future__ import annotations

from http.cookiejar import CookieJar, MozillaCookieJar
from pathlib import Path

SUPPORTED_BROWSERS = {"chrome", "firefox", "edge", "brave"}
# A cookies.txt file (Netscape format, exported from a browser) is stored in the same
# setting as "file:<path>". It is the reliable choice when reading a browser directly
# fails, which is common for Chrome, Edge and Brave on Windows.
FILE_PREFIX = "file:"


def is_cookie_file(value: str | None) -> bool:
    return bool(value) and str(value).strip().casefold().startswith(FILE_PREFIX)


def cookie_file_path(value: str) -> str:
    return str(value).strip()[len(FILE_PREFIX):].strip()


def normalize_cookie_source(value: str | None) -> str:
    """"none", a lower-case browser name, or "file:<path>" (path keeps its case)."""
    text = (value or "").strip()
    if not text or text.casefold() in {"none", "off"}:
        return "none"
    if is_cookie_file(text):
        return FILE_PREFIX + cookie_file_path(text)
    return text.lower()


def cookie_source_error(value: str | None) -> str | None:
    """A plain-language problem with the setting, or None when it is usable."""
    source = normalize_cookie_source(value)
    if source == "none" or source in SUPPORTED_BROWSERS:
        return None
    if is_cookie_file(source):
        path = Path(cookie_file_path(source)).expanduser()
        if not path.is_file():
            return f"The cookies file was not found: {path}"
        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError as error:
            return f"The cookies file cannot be read: {error}"
        return None
    return f"Unsupported browser cookie source: {value}"


def load_cookies(browser_name: str | None) -> CookieJar | None:
    source = normalize_cookie_source(browser_name)
    if source == "none":
        return None
    if is_cookie_file(source):
        error = cookie_source_error(source)
        if error:
            raise ValueError(error)
        jar = MozillaCookieJar(str(Path(cookie_file_path(source)).expanduser()))
        jar.load(ignore_discard=True, ignore_expires=True)
        return jar
    if source not in SUPPORTED_BROWSERS:
        raise ValueError(f"Unsupported browser cookie source: {browser_name}")

    from yt_dlp.cookies import extract_cookies_from_browser

    return extract_cookies_from_browser(source)
