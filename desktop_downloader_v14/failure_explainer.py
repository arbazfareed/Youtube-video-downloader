from __future__ import annotations


def explain_failure(message: str) -> tuple[str, str]:
    """Map common downloader errors to a human explanation and next action."""
    text = (message or "").casefold()
    cases = (
        (("429", "too many requests", "rate limit"), "The website is temporarily limiting requests.", "Wait, reduce concurrency or speed, and retry later."),
        (("403", "forbidden", "bot", "sign in", "private", "members-only"), "The server refused this request or requires an authenticated session.", "Confirm access and select browser cookies only if you are signed in and authorized."),
        (("404", "not found", "removed", "unavailable"), "The media page or its stream is no longer available at this address.", "Open the link in a browser and check whether the media still exists."),
        ((("geo", "country", "region"),), "The provider may restrict this media by location.", "Use the provider's official access options; do not attempt to bypass legal or account restrictions."),
        (("unsupported url", "no suitable extractor", "not a valid url"), "The URL was not recognized as a supported media page.", "Try Auto source, update yt-dlp, or use Direct file only for a direct media URL."),
        (("ffmpeg", "postprocess", "merging formats"), "The downloaded streams could not be converted or merged.", "Install/update FFmpeg and retry; check that the selected format supports merging."),
        (("no space left", "disk full", "enospc"), "The destination drive ran out of free space.", "Free disk space or choose a destination with more room."),
        (("timed out", "connection reset", "network is unreachable", "temporary failure in name resolution"), "The network connection failed during transfer.", "Check your network and retry; resumable partial data may be reused."),
        (("empty playlist", "no entries", "playlist is empty"), "The playlist returned no downloadable entries.", "Check playlist visibility, selection indices, and whether its items are still available."),
        (("html", "webpage", "content-type text/html"), "The response appears to be a web page rather than media bytes.", "Use Supported site/Auto for extractor pages; direct file links must point to the actual media resource."),
    )
    for patterns, explanation, action in cases:
        if any(term in text for term in patterns):
            return explanation, action
    return (
        "The downloader could not map this error to a specific cause.",
        "Review the raw details, check the URL and destination, update yt-dlp, then retry. If it persists, attach a sanitized diagnostic report.",
    )
