from __future__ import annotations

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


def analyze_link(url: str) -> LinkAnalysis:
    """Classify a link offline; never requests or downloads the remote URL."""
    value = (url or "").strip()
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
