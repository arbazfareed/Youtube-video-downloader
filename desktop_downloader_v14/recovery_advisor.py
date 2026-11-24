from __future__ import annotations


def recovery_advice(error: str) -> tuple[bool, str]:
    """Return (retryable, practical next step) for a failed v14 download."""
    text = (error or "").casefold()
    rules = (
        (("429", "too many requests", "rate limit", "http error 503", "service unavailable"),
         True, "The server is rate-limiting requests. Wait a few minutes, lower the speed/parallelism if available, then use Resume / retry selected."),
        (("timed out", "timeout", "connection reset", "connection aborted", "temporary failure", "network is unreachable", "dns"),
         True, "This looks like a temporary network failure. Check the connection and use Resume / retry selected; saved partial data may continue."),
        (("403", "forbidden", "sign in", "private video", "members-only"),
         False, "The host may require authorization. Select cookies from a browser where you are signed in, or confirm the link is public and accessible."),
        (("404", "not found", "removed", "unavailable", "video is unavailable"),
         False, "Check that the item still exists and the URL is correct. A removed or private item cannot be recovered by retrying."),
        (("unsupported url", "no suitable extractor", "not a valid url"),
         False, "Try Auto source or Direct file for a genuine file URL. If it is a web page, update yt-dlp and check whether the site is supported."),
        (("ffmpeg", "postprocessing", "conversion failed"),
         False, "Install or repair FFmpeg, restart the downloader, and retry. The original media should be retained when conversion fails."),
        (("no space left", "disk full", "not enough disk", "enospc"),
         False, "Free space on the destination drive or choose another folder before retrying."),
        (("checksum mismatch", "integrity check failed"),
         False, "The file failed verification. Keep the suspect file separate, download again, and verify against a trusted checksum."),
    )
    for patterns, retryable, advice in rules:
        if any(pattern in text for pattern in patterns):
            return retryable, advice
    return True, "Review the details below, check the destination and connection, then use Resume / retry selected. If it repeats, update yt-dlp and attach the sanitized diagnostic log."
