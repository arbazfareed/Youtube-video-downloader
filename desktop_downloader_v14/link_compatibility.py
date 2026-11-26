from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

_DIRECT_EXTENSIONS = {".3gp", ".avi", ".flv", ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".opus", ".wav", ".webm", ".wmv", ".zip", ".rar", ".7z", ".pdf", ".jpg", ".jpeg", ".png", ".gif"}
_PLAYLIST_KEYS = {"list", "playlist", "album", "collection"}
_DRM_HOSTS = {"netflix.com": "Netflix (DRM-protected)", "primevideo.com": "Prime Video (DRM-protected)", "disneyplus.com": "Disney+ (DRM-protected)", "hulu.com": "Hulu (DRM-protected)", "tv.apple.com": "Apple TV+ (DRM-protected)", "max.com": "Max (DRM-protected)"}


@dataclass(frozen=True)
class LinkAnalysis:
    valid: bool
    host: str = ""
    kind: str = "unknown"
    extractor: str = ""
    playlist: bool = False
    drm_service: str = ""
    message: str = ""


_LINK_START = re.compile(r"(?:https?://|magnet:\?)", re.IGNORECASE)
# A web address pasted without "https://", such as "www.site.com/..." or "youtu.be/id".
_SCHEMELESS_LINK = re.compile(
    r"(?:www\.(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#]\S*)?"
    r"|(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?[/?#]\S*)",
    re.IGNORECASE,
)


def normalize_link_text(text: str) -> str:
    """Add https:// to a pasted web address that has no scheme; leave anything else alone."""
    value = (text or "").strip()
    if not value or _LINK_START.match(value):
        return value
    if _SCHEMELESS_LINK.fullmatch(value):
        return "https://" + value
    return value


def split_pasted_links(text: str) -> list[str]:
    """Return the links in pasted text when it holds two or more.

    Links may be separated by spaces or new lines. Text that mixes links with
    ordinary words returns an empty list, so a single odd link still reaches the
    normal validation message instead of being split apart.
    """
    tokens = (text or "").split()
    if len(tokens) < 2:
        return []
    links = [normalize_link_text(token) for token in tokens]
    return links if all(_LINK_START.match(link) for link in links) else []


def analyze_link(url: str) -> LinkAnalysis:
    """Classify a link offline; never requests or downloads the remote URL."""
    value = normalize_link_text(url)
    if re.search(r"\s", value):
        return LinkAnalysis(
            False,
            message=(
                "This text contains spaces or more than one link. Check one link at "
                "a time, or click Add download to queue several pasted links."
            ),
        )
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return LinkAnalysis(False, message="The URL is malformed.")
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        if value.lower().startswith("magnet:?"):
            return LinkAnalysis(True, kind="torrent/magnet", message="Torrent link; use the torrent source.")
        return LinkAnalysis(False, host=host, message="Enter a valid HTTP(S) URL or magnet URI.")

    query = {key.lower() for key in parse_qs(parsed.query)}
    playlist = bool(query & _PLAYLIST_KEYS) or any(marker in parsed.path.lower() for marker in ("/playlist", "/album/", "/sets/"))
    leaf = parsed.path.rsplit("/", 1)[-1]
    extension = "." + leaf.rsplit(".", 1)[-1].lower() if "." in leaf else ""
    drm = next((label for domain, label in _DRM_HOSTS.items() if host == domain or host.endswith("." + domain)), "")
    if drm:
        return LinkAnalysis(True, host, "protected streaming page", playlist=playlist, drm_service=drm, message="This service commonly uses DRM; use its official app for authorized offline viewing.")
    if extension in _DIRECT_EXTENSIONS:
        return LinkAnalysis(True, host, "direct file", playlist=playlist, message="Looks like a direct file URL. Auto source can usually handle it.")

    extractor_name = ""
    try:
        from yt_dlp.extractor import gen_extractors
        for extractor in gen_extractors():
            try:
                if extractor.suitable(value):
                    extractor_name = str(getattr(extractor, "IE_NAME", "") or extractor.__class__.__name__)
                    break
            except Exception:
                continue
    except Exception:
        pass
    if extractor_name:
        kind = "playlist/page" if playlist else "media page"
        return LinkAnalysis(True, host, kind, extractor_name, playlist, message=f"yt-dlp recognizes this page ({extractor_name}).")
    return LinkAnalysis(True, host, "generic web page", playlist=playlist, message="No extractor matched locally. It may still be a supported stream or plugin URL.")


def format_multi_link_summary(links: list[str], limit: int = 12) -> str:
    """Describe several pasted links without contacting any of them."""
    lines = [f"{len(links)} links detected. Click Add download to queue them all."]
    for index, link in enumerate(links[:limit], start=1):
        analysis = analyze_link(link)
        what = analysis.kind if analysis.valid else analysis.message
        lines.append(f"{index}. {analysis.host or link[:50]} - {what}")
    if len(links) > limit:
        lines.append(f"...and {len(links) - limit} more.")
    lines.append("")
    lines.append("This is a local compatibility hint, not a live availability check.")
    return "\n".join(lines)


def format_analysis(analysis: LinkAnalysis) -> str:
    if not analysis.valid:
        return analysis.message
    lines = [f"Host: {analysis.host or 'magnet link'}", f"Type: {analysis.kind}", f"Playlist: {'Yes' if analysis.playlist else 'Not detected'}"]
    if analysis.extractor:
        lines.append(f"Extractor: {analysis.extractor}")
    if analysis.drm_service:
        lines.append(f"Access limitation: {analysis.drm_service}")
    lines.extend(["", analysis.message, "This is a local compatibility hint, not a live availability check."])
    return "\n".join(lines)
