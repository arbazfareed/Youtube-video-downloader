from __future__ import annotations

from http.cookiejar import CookieJar

SUPPORTED_BROWSERS = {"chrome", "firefox", "edge", "brave"}


def load_cookies(browser_name: str | None) -> CookieJar | None:
    if not browser_name or browser_name.lower() in {"none", "off"}:
        return None
    browser = browser_name.lower()
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(f"Unsupported browser cookie source: {browser_name}")

    from yt_dlp.cookies import extract_cookies_from_browser

    return extract_cookies_from_browser(browser)
