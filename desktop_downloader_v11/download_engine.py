from __future__ import annotations

import email.message
import hashlib
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit

from bandwidth import GlobalBandwidthLimiter
from cookies import load_cookies
from plugins import emit as emit_plugin_event
from proxy import ProxyRotator
import requests
import yt_dlp
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor


ProgressCallback = Callable[[str, float | None, str], None]
DIRECT_CHUNK_SIZE = 1024 * 1024
FRAGMENT_WORKERS = {"balanced": 4, "fast": 8, "maximum": 16}
PARALLEL_MIN_SIZE = 4 * 1024 * 1024
PARALLEL_RETRIES = 5
DELTA_MANIFEST_HEADER = "X-Chunk-Hash-Manifest"
MAX_DELTA_CHUNK_SIZE = 64 * 1024 * 1024
DIRECT_FILE_EXTENSIONS = {
    ".7z", ".aac", ".avi", ".csv", ".doc", ".docx", ".flac", ".gif", ".gz",
    ".jpeg", ".jpg", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg", ".mpg",
    ".msi", ".ods", ".odt", ".ogg", ".pdf", ".png", ".ppt", ".pptx", ".rar",
    ".tar", ".txt", ".wav", ".webm", ".webp", ".wmv", ".xls", ".xlsx", ".zip",
}
FFMPEG_LANGUAGE_TAGS = {
    "ar": "ara",
    "de": "deu",
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "hi": "hin",
    "it": "ita",
    "ja": "jpn",
    "ko": "kor",
    "pt": "por",
    "ru": "rus",
    "zh": "zho",
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.IGNORECASE)
ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
TRANSIENT_NETWORK_ERRORS = (
    "failed to resolve",
    "getaddrinfo failed",
    "temporary failure in name resolution",
    "name or service not known",
    "network is unreachable",
    "connection reset",
    "connection aborted",
    "connection refused",
    "read timed out",
    "connect timeout",
    "timed out",
    "temporary failure",
)
ACTIVE_TARGETS: set[str] = set()
TARGET_LOCK = threading.Lock()
QUALITY_HEIGHTS = {
    "4320p": 4320,
    "2880p": 2880,
    "2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
    "240p": 240,
    "144p": 144,
}


class DownloadCancelled(Exception):
    pass


def _clean_terminal_text(value: object) -> str:
    text = ANSI_ESCAPE.sub("", str(value))
    return "".join(character for character in text if character in "\t\n\r" or ord(character) >= 32)


def _is_transient_network_error(error: Exception) -> bool:
    message = _clean_terminal_text(error).casefold()
    return any(phrase in message for phrase in TRANSIENT_NETWORK_ERRORS)


def _wait_for_network_retry(
    cancel_event: threading.Event,
    resume_event: threading.Event | None,
    delay: float,
) -> bool:
    deadline = time.monotonic() + delay
    while True:
        _wait_until_resumed(cancel_event, resume_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return True
        if cancel_event.wait(min(remaining, 0.25)):
            return False


def _check_cancelled(cancel_event: threading.Event) -> None:
    if cancel_event.is_set():
        raise DownloadCancelled("Download cancelled.")


def _wait_until_resumed(
    cancel_event: threading.Event,
    resume_event: threading.Event | None,
) -> None:
    while resume_event is not None and not resume_event.is_set():
        _check_cancelled(cancel_event)
        resume_event.wait(0.25)
    _check_cancelled(cancel_event)


def _fragment_workers(speed_mode: str) -> int:
    return FRAGMENT_WORKERS.get(speed_mode, FRAGMENT_WORKERS["fast"])


def _wait_for_retry(cancel_event: threading.Event, delay: int) -> bool:
    return cancel_event.wait(delay)


def _limit_chunk_rate(
    chunk_size: int,
    max_speed: int | None,
    cancel_event: threading.Event,
    resume_event: threading.Event | None,
) -> None:
    if max_speed is None or max_speed <= 0:
        return

    remaining = chunk_size / max_speed
    while remaining > 0:
        _wait_until_resumed(cancel_event, resume_event)
        wait_for = min(remaining, 0.25)
        started = time.monotonic()
        if cancel_event.wait(wait_for):
            raise DownloadCancelled("Download cancelled.")
        remaining -= min(wait_for, time.monotonic() - started)


def _ffmpeg_directory() -> Path | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return Path(executable).parent

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        for executable_path in package_root.glob("Gyan.FFmpeg.Shared*/*/bin/ffmpeg.exe"):
            if executable_path.is_file():
                return executable_path.parent
    return None


def _is_direct_file_url(url: str) -> bool:
    suffix = PurePosixPath(unquote(urlsplit(url).path)).suffix.lower()
    return suffix in DIRECT_FILE_EXTENSIONS


def _safe_filename(filename: str) -> str:
    filename = PurePosixPath(filename.replace("\\", "/")).name
    filename = INVALID_FILENAME_CHARS.sub("_", filename).strip(" .")
    if not filename:
        filename = "download"
    base_name, separator, extension = filename.partition(".")
    base_name = base_name.rstrip(" .")
    filename = f"{base_name}{separator}{extension}"
    if base_name.upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        filename = f"_{filename}"
    return filename[:180].rstrip(" .") or "download"


def _video_format_selector(quality: str) -> str:
    height = QUALITY_HEIGHTS.get(quality)
    if height is None:
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"


def _audio_language_format_ids(formats: list[dict]) -> list[tuple[str, str]]:
    tracks: dict[str, dict] = {}
    for media_format in formats:
        if media_format.get("vcodec") != "none" or media_format.get("acodec") in {
            None,
            "none",
        }:
            continue
        language_value = media_format.get("language")
        language = (
            language_value
            if isinstance(language_value, str) and language_value
            else "und"
        )
        format_id = media_format.get("format_id")
        if not isinstance(format_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", format_id):
            continue
        current = tracks.get(language)
        rank = (
            media_format.get("quality") or 0,
            media_format.get("source_preference") or 0,
            media_format.get("abr") or 0,
            media_format.get("tbr") or 0,
        )
        current_rank = (
            (current.get("quality") or 0),
            (current.get("source_preference") or 0),
            (current.get("abr") or 0),
            (current.get("tbr") or 0),
        ) if current else None
        if current_rank is None or rank > current_rank:
            tracks[language] = media_format
    return [
        (language, media_format["format_id"])
        for language, media_format in sorted(tracks.items())
    ]


def _all_audio_tracks_selector(downloader, quality: str):
    default_selector = downloader.build_format_selector(
        _video_format_selector(quality)
    )
    height = QUALITY_HEIGHTS.get(quality)
    video_selector = "bestvideo" if height is None else f"bestvideo[height<={height}]"
    fallback_selector = "best" if height is None else f"best[height<={height}]"

    def select_formats(context):
        tracks = _audio_language_format_ids(context["formats"])
        if len(tracks) < 2:
            downloader.params["merge_output_format"] = "mp4"
            return default_selector(context)
        downloader.params["merge_output_format"] = "mkv"
        tracks.sort(key=lambda item: (not item[0].lower().startswith("en"), item[0]))
        audio_selectors = "+".join(format_id for _, format_id in tracks)
        selector = downloader.build_format_selector(
            f"{video_selector}+{audio_selectors}/{fallback_selector}"
        )
        return selector(context)

    return select_formats


def _ffmpeg_language_tag(language: str) -> str:
    language_code = language.lower().replace("_", "-").split("-", 1)[0]
    return FFMPEG_LANGUAGE_TAGS.get(language_code, language_code)


class _AudioLanguageMetadataPP(FFmpegPostProcessor):
    def run(self, info: dict) -> tuple[list[str], dict]:
        requested_formats = info.get("requested_formats") or []
        languages = []
        for media_format in requested_formats:
            if media_format.get("acodec") in {None, "none"}:
                continue
            language = media_format.get("language")
            languages.append(language if isinstance(language, str) else None)
        filepath = info.get("filepath")
        if (
            len(languages) < 2
            or not filepath
            or Path(filepath).suffix.lower() != ".mkv"
        ):
            return [], info

        default_index = next(
            (
                index
                for index, language in enumerate(languages)
                if language and language.lower().startswith("en")
            ),
            0,
        )
        options = ["-map", "0", "-c", "copy"]
        for index, language in enumerate(languages):
            if language and language.lower() != "und":
                options.extend(
                    (
                        f"-metadata:s:a:{index}",
                        f"language={_ffmpeg_language_tag(language)}",
                    )
                )
            options.extend(
                (
                    f"-disposition:a:{index}",
                    "default" if index == default_index else "0",
                )
            )

        source = Path(filepath)
        temporary = source.with_name(f"{source.stem}.language-tags{source.suffix}")
        self.run_ffmpeg(str(source), str(temporary), options)
        os.replace(temporary, source)
        return [], info


def _progress_details(
    filename: str | None,
    downloaded: int | None,
    total: int | None,
    speed: float | None = None,
    eta: float | None = None,
) -> str:
    parts = [Path(filename).name] if filename else []
    if downloaded is not None:
        downloaded_mb = downloaded / (1024 * 1024)
        if total:
            parts.append(f"{downloaded_mb:.1f} / {total / (1024 * 1024):.1f} MB")
        else:
            parts.append(f"{downloaded_mb:.1f} MB downloaded")
    if speed is not None and speed > 0:
        speed_mb = speed / (1024 * 1024)
        parts.append(f"{speed_mb:.2f} MB/s" if speed_mb >= 1 else f"{speed / 1024:.0f} KB/s")
    if eta is not None and eta >= 0:
        seconds = int(eta)
        parts.append(f"ETA {seconds // 60}:{seconds % 60:02d}")
    return " | ".join(parts)


def _response_filename(response: requests.Response) -> str:
    disposition = response.headers.get("Content-Disposition", "")
    message = email.message.Message()
    message["Content-Disposition"] = disposition
    filename = message.get_filename()
    if filename:
        return _safe_filename(filename)

    path_name = PurePosixPath(unquote(urlsplit(response.url).path)).name
    return _safe_filename(path_name or "download")


def _delta_sync_existing_file(
    session: requests.Session,
    url: str,
    target: Path,
    total: int,
    manifest_url: str,
    cancel_event: threading.Event,
    resume_event: threading.Event | None,
    progress: ProgressCallback,
    max_speed: int | None,
    bandwidth_limiter: GlobalBandwidthLimiter | None,
    proxy_rotator: ProxyRotator,
    validator: str,
) -> str | None:
    if not target.is_file():
        return None

    target_key = _target_key(target)
    with TARGET_LOCK:
        if target_key in ACTIVE_TARGETS:
            return None
        ACTIVE_TARGETS.add(target_key)

    partial = target.with_name(target.name + ".delta.part")
    try:
        with session.get(
            manifest_url,
            timeout=(15, 60),
            allow_redirects=True,
            proxies=proxy_rotator.next_requests_proxy(),
        ) as response:
            response.raise_for_status()
            try:
                manifest = response.json()
            except ValueError as error:
                raise RuntimeError("The chunk-hash manifest is not valid JSON.") from error

        if not isinstance(manifest, dict):
            raise RuntimeError("The chunk-hash manifest must be a JSON object.")
        chunk_size = manifest.get("chunk_size")
        manifest_size = manifest.get("size")
        algorithm = manifest.get("algorithm")
        chunk_hashes = manifest.get("chunks")
        if (
            not isinstance(chunk_size, int)
            or isinstance(chunk_size, bool)
            or chunk_size <= 0
            or chunk_size > MAX_DELTA_CHUNK_SIZE
            or not isinstance(manifest_size, int)
            or isinstance(manifest_size, bool)
            or manifest_size != total
            or algorithm not in {"sha256", "sha512"}
            or not isinstance(chunk_hashes, list)
        ):
            raise RuntimeError("The chunk-hash manifest has invalid size, algorithm, or chunks.")

        chunk_count = (total + chunk_size - 1) // chunk_size
        digest_length = hashlib.new(algorithm).digest_size * 2
        if len(chunk_hashes) != chunk_count or any(
            not isinstance(chunk_hash, str)
            or len(chunk_hash) != digest_length
            or not re.fullmatch(r"[0-9a-fA-F]+", chunk_hash)
            for chunk_hash in chunk_hashes
        ):
            raise RuntimeError("The chunk-hash manifest contains invalid chunk hashes.")

        unchanged: set[int] = set()
        with target.open("rb") as existing:
            for index, expected_hash in enumerate(chunk_hashes):
                _wait_until_resumed(cancel_event, resume_event)
                local_chunk = existing.read(min(chunk_size, total - index * chunk_size))
                if hashlib.new(algorithm, local_chunk).hexdigest() == expected_hash.lower():
                    unchanged.add(index)
        changed_count = chunk_count - len(unchanged)
        completed_bytes = 0
        progress(
            "Synchronizing changed chunks",
            100.0 if total == 0 else 0.0,
            f"{target.name} | {changed_count} of {chunk_count} chunks need updating",
        )

        with target.open("rb") as existing, partial.open("wb") as output:
            for index, expected_hash in enumerate(chunk_hashes):
                _wait_until_resumed(cancel_event, resume_event)
                start = index * chunk_size
                length = min(chunk_size, total - start)
                local_chunk = existing.read(length)
                if index in unchanged:
                    chunk = local_chunk
                else:
                    end = start + length - 1
                    headers = {"Range": f"bytes={start}-{end}"}
                    if validator.startswith("etag:") and not validator[5:].lstrip().startswith("W/"):
                        headers["If-Match"] = validator[5:]
                    elif validator.startswith("last-modified:"):
                        headers["If-Unmodified-Since"] = validator[14:]
                    with session.get(
                        url,
                        headers=headers,
                        timeout=(15, 60),
                        allow_redirects=True,
                        proxies=proxy_rotator.next_requests_proxy(),
                    ) as response:
                        if response.status_code != 206:
                            raise RuntimeError(
                                "The server did not return the requested changed chunk."
                            )
                        match = CONTENT_RANGE.match(response.headers.get("Content-Range", ""))
                        if (
                            not match
                            or int(match.group(1)) != start
                            or int(match.group(2)) != end
                            or match.group(3) == "*"
                            or int(match.group(3)) != total
                        ):
                            raise RuntimeError("The server returned an invalid changed chunk range.")
                        chunk = response.content
                    if (
                        len(chunk) != length
                        or hashlib.new(algorithm, chunk).hexdigest() != expected_hash.lower()
                    ):
                        raise RuntimeError(
                            f"Changed chunk {index + 1} did not match its manifest hash."
                        )
                    _limit_chunk_rate(len(chunk), max_speed, cancel_event, resume_event)
                    if bandwidth_limiter and not bandwidth_limiter.acquire(
                        len(chunk), cancel_event, resume_event
                    ):
                        raise DownloadCancelled("Download cancelled.")
                output.write(chunk)
                completed_bytes += length
                percent = completed_bytes * 100 / total if total else 100.0
                progress(
                    "Synchronizing changed chunks",
                    percent,
                    f"{target.name} | {completed_bytes / (1024 * 1024):.1f} / "
                    f"{total / (1024 * 1024):.1f} MB",
                )

        _check_cancelled(cancel_event)
        os.replace(partial, target)
        progress("Download complete", 100.0, str(target))
        return str(target)
    except Exception as error:
        try:
            partial.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise RuntimeError(
                f"{error} (could not remove temporary delta file {partial}: {cleanup_error})"
            ) from error
        raise
    finally:
        _release_target(target)


def _target_key(target: Path) -> str:
    return str(target.resolve()).casefold()


def _claim_target(directory: Path, filename: str) -> Path:
    stem, suffix = Path(filename).stem, Path(filename).suffix
    with TARGET_LOCK:
        counter = 0
        while True:
            name = filename if counter == 0 else f"{stem} ({counter}){suffix}"
            candidate = directory / name
            key = _target_key(candidate)
            if not candidate.exists() and key not in ACTIVE_TARGETS:
                ACTIVE_TARGETS.add(key)
                return candidate
            counter += 1


def _release_target(target: Path | None) -> None:
    if target is None:
        return
    with TARGET_LOCK:
        ACTIVE_TARGETS.discard(_target_key(target))


def _final_target(target: Path) -> Path:
    with TARGET_LOCK:
        if not target.exists():
            return target

        ACTIVE_TARGETS.discard(_target_key(target))
        stem, suffix = target.stem, target.suffix
        counter = 1
        while True:
            candidate = target.with_name(f"{stem} ({counter}){suffix}")
            if (
                not candidate.exists()
                and not candidate.with_name(candidate.name + ".part").exists()
                and _target_key(candidate) not in ACTIVE_TARGETS
            ):
                ACTIVE_TARGETS.add(_target_key(candidate))
                return candidate
            counter += 1


def _parallel_metadata_path(target: Path) -> Path:
    return target.with_name(target.name + ".segments.json")


def _parallel_segment_path(target: Path, index: int) -> Path:
    return target.with_name(f"{target.name}.part.segment-{index:02d}")


def _parallel_range_download(
    url: str,
    target: Path,
    total: int,
    preferred_workers: int,
    validator: str,
    cancel_event: threading.Event,
    resume_event: threading.Event | None,
    progress: ProgressCallback,
    bandwidth_limiter: GlobalBandwidthLimiter | None = None,
    proxy_rotator: ProxyRotator | None = None,
    cookies=None,
) -> str:
    segment_target = target
    partial = target.with_name(target.name + ".part")
    metadata_path = _parallel_metadata_path(target)
    metadata: dict = {}
    try:
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metadata = {}

        expected = {
            "url": url,
            "total": total,
            "validator": validator,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            for path in target.parent.glob(f"{target.name}.part.segment-*"):
                path.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            metadata = {}

        if not metadata.get("segments"):
            worker_count = max(1, min(preferred_workers, total))
            segments = []
            for index in range(worker_count):
                start = total * index // worker_count
                end = total * (index + 1) // worker_count - 1
                segments.append({"index": index, "start": start, "end": end})
            metadata = {**expected, "segments": segments}
            temporary_metadata = metadata_path.with_name(metadata_path.name + ".tmp")
            temporary_metadata.write_text(json.dumps(metadata), encoding="utf-8")
            temporary_metadata.replace(metadata_path)

        segments = metadata["segments"]
        completed_bytes = 0
        progress_lock = threading.Lock()
        for segment in segments:
            segment_path = _parallel_segment_path(target, segment["index"])
            if segment_path.exists():
                completed_bytes += min(
                    segment_path.stat().st_size,
                    segment["end"] - segment["start"] + 1,
                )

        progress(
            "Downloading direct file (parallel ranges)",
            completed_bytes * 100 / total,
            _progress_details(str(target), completed_bytes, total),
        )

        def download_segment(segment: dict) -> None:
            start = segment["start"]
            end = segment["end"]
            expected_length = end - start + 1
            segment_path = _parallel_segment_path(target, segment["index"])
            for attempt in range(PARALLEL_RETRIES):
                _wait_until_resumed(cancel_event, resume_event)
                existing = segment_path.stat().st_size if segment_path.exists() else 0
                if existing > expected_length:
                    segment_path.unlink()
                    existing = 0
                if existing == expected_length:
                    return

                range_start = start + existing
                headers = {"Range": f"bytes={range_start}-{end}"}
                if validator:
                    if validator.startswith("etag:"):
                        headers["If-Range"] = validator[5:]
                    elif validator.startswith("last-modified:"):
                        headers["If-Range"] = validator[14:]

                try:
                    with requests.get(
                        url,
                        headers=headers,
                        stream=True,
                        timeout=(15, 60),
                        allow_redirects=True,
                        proxies=proxy_rotator.next_requests_proxy() if proxy_rotator else None,
                        cookies=cookies,
                    ) as response:
                        if response.status_code != 206:
                            raise RuntimeError(
                                "The server stopped honoring range requests during parallel download."
                            )
                        range_header = response.headers.get("Content-Range", "")
                        match = CONTENT_RANGE.match(range_header)
                        if (
                            not match
                            or int(match.group(1)) != range_start
                            or int(match.group(2)) != end
                            or match.group(3) == "*"
                            or int(match.group(3)) != total
                        ):
                            raise RuntimeError("The server returned an invalid range segment.")

                        mode = "ab" if existing else "wb"
                        with segment_path.open(mode) as output:
                            for chunk in response.iter_content(chunk_size=DIRECT_CHUNK_SIZE):
                                _wait_until_resumed(cancel_event, resume_event)
                                if not chunk:
                                    continue
                                if output.tell() + len(chunk) > expected_length:
                                    raise RuntimeError("The server sent more bytes than requested.")
                                if bandwidth_limiter and not bandwidth_limiter.acquire(
                                    len(chunk), cancel_event, resume_event
                                ):
                                    raise DownloadCancelled("Download cancelled.")
                                output.write(chunk)
                                with progress_lock:
                                    nonlocal_completed[0] += len(chunk)
                                    progress(
                                        "Downloading direct file (parallel ranges)",
                                        nonlocal_completed[0] * 100 / total,
                                        _progress_details(
                                            str(target), nonlocal_completed[0], total
                                        ),
                                    )

                    if segment_path.stat().st_size != expected_length:
                        raise requests.ConnectionError(
                            "The server closed before this range completed."
                        )
                    return
                except requests.RequestException:
                    if attempt + 1 >= PARALLEL_RETRIES:
                        raise
                    _wait_until_resumed(cancel_event, resume_event)
                    if cancel_event.wait(min(2**attempt, 8)):
                        raise DownloadCancelled("Download cancelled.")

        nonlocal_completed = [completed_bytes]
        with ThreadPoolExecutor(max_workers=len(segments)) as executor:
            futures = [executor.submit(download_segment, segment) for segment in segments]
            for future in as_completed(futures):
                future.result()

        _wait_until_resumed(cancel_event, resume_event)
        with partial.open("wb") as output:
            for segment in segments:
                segment_path = _parallel_segment_path(target, segment["index"])
                with segment_path.open("rb") as input_file:
                    shutil.copyfileobj(input_file, output, length=DIRECT_CHUNK_SIZE)
        if partial.stat().st_size != total:
            partial.unlink(missing_ok=True)
            raise RuntimeError("Parallel download did not produce the expected file size.")

        final_target = _final_target(target)
        target = final_target
        partial.replace(final_target)
        for segment in segments:
            _parallel_segment_path(segment_target, segment["index"]).unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        progress("Download complete", 100.0, str(final_target))
        return str(final_target)
    finally:
        _release_target(target)


def _download_direct(
    url: str,
    directory: Path,
    cancel_event: threading.Event,
    progress: ProgressCallback,
    resume_event: threading.Event | None = None,
    max_speed: int | None = None,
    speed_mode: str = "fast",
    bandwidth_limiter: GlobalBandwidthLimiter | None = None,
    proxy: str = "",
    browser_cookies: str = "none",
) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    cookie_jar = load_cookies(browser_cookies)
    session = requests.Session()
    if cookie_jar:
        session.cookies.update(cookie_jar)
    proxy_rotator = ProxyRotator(proxy)
    target: Path | None = None
    last_error: Exception | None = None
    suggested_name = PurePosixPath(unquote(urlsplit(url).path)).name
    if suggested_name:
        suggested_name = _safe_filename(suggested_name)
        suggested_target = directory / suggested_name
        suggested_partial = suggested_target.with_name(suggested_target.name + ".part")
        if not suggested_target.exists() and suggested_partial.exists():
            target = _claim_target(directory, suggested_name)

    try:
        parallel_enabled = (
            target is None
            and max_speed is None
            and not proxy_rotator.enabled
            and _fragment_workers(speed_mode) > 1
        )
        parallel_info: tuple[str, int, str] | None = None
        delta_info: tuple[Path, int, str, str] | None = None
        if target is None:
            try:
                with session.get(
                    url,
                    headers={"Range": "bytes=0-0"},
                    stream=True,
                    timeout=(15, 60),
                    allow_redirects=True,
                    proxies=proxy_rotator.current_requests_proxy(),
                ) as probe:
                    match = CONTENT_RANGE.match(probe.headers.get("Content-Range", ""))
                    if (
                        probe.status_code == 206
                        and match
                        and int(match.group(1)) == 0
                        and int(match.group(2)) == 0
                        and match.group(3) != "*"
                        and "text/html" not in probe.headers.get("Content-Type", "").lower()
                    ):
                        total = int(match.group(3))
                        candidate_name = _response_filename(probe)
                        candidate = directory / candidate_name
                        validator = (
                            "etag:" + probe.headers["ETag"]
                            if probe.headers.get("ETag")
                            else "last-modified:" + probe.headers["Last-Modified"]
                            if probe.headers.get("Last-Modified")
                            else ""
                        )
                        manifest_path = probe.headers.get(DELTA_MANIFEST_HEADER, "").strip()
                        if manifest_path and candidate.is_file():
                            delta_info = (
                                candidate,
                                total,
                                urljoin(probe.url, manifest_path),
                                validator,
                            )
                        metadata_path = _parallel_metadata_path(candidate)
                        partial = candidate.with_name(candidate.name + ".part")
                        if (
                            parallel_enabled
                            and total >= PARALLEL_MIN_SIZE
                            and validator
                            and (metadata_path.exists() or not partial.exists())
                        ):
                            parallel_info = (candidate_name, total, validator)
            except requests.RequestException:
                parallel_info = None
                delta_info = None

        if delta_info:
            delta_target, total, manifest_url, validator = delta_info
            delta_result = _delta_sync_existing_file(
                session,
                url,
                delta_target,
                total,
                manifest_url,
                cancel_event,
                resume_event,
                progress,
                max_speed,
                bandwidth_limiter,
                proxy_rotator,
                validator,
            )
            if delta_result:
                return delta_result

        if parallel_info:
            candidate_name, total, validator = parallel_info
            target = _claim_target(directory, candidate_name)
            return _parallel_range_download(
                url,
                target,
                total,
                _fragment_workers(speed_mode),
                validator,
                cancel_event,
                resume_event,
                progress,
                bandwidth_limiter,
                proxy_rotator,
                cookie_jar,
            )

        for attempt in range(10):
            _wait_until_resumed(cancel_event, resume_event)
            headers = {}
            partial = target.with_name(target.name + ".part") if target else None
            existing = partial.stat().st_size if partial and partial.exists() else 0
            if existing:
                headers["Range"] = f"bytes={existing}-"

            try:
                with session.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=(15, 60),
                    allow_redirects=True,
                    proxies=proxy_rotator.next_requests_proxy(),
                ) as response:
                    if response.status_code == 416 and partial and partial.exists():
                        content_range = response.headers.get("Content-Range", "")
                        match = re.fullmatch(r"bytes \*/(\d+)", content_range, re.IGNORECASE)
                        if match and int(match.group(1)) == existing:
                            target = _final_target(target)
                            partial.replace(target)
                            return str(target)
                    response.raise_for_status()

                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type:
                        raise ValueError(
                            "This link returned a web page, not a direct file. "
                            "Choose 'Supported site' if yt-dlp supports that site."
                        )

                    if target is None:
                        target = _claim_target(directory, _response_filename(response))
                        partial = target.with_name(target.name + ".part")

                    append = existing > 0 and response.status_code == 206
                    if append:
                        content_range = response.headers.get("Content-Range", "")
                        match = CONTENT_RANGE.match(content_range)
                        if not match or int(match.group(1)) != existing:
                            raise ValueError("The server returned an invalid range for resume.")
                    else:
                        existing = 0

                    content_length = response.headers.get("Content-Length")
                    total = existing + int(content_length) if content_length and content_length.isdigit() else None
                    downloaded = existing
                    progress(
                        "Downloading direct file",
                        0.0 if total else None,
                        _progress_details(str(target), downloaded, total),
                    )
                    mode = "ab" if append else "wb"
                    with partial.open(mode) as output:
                        for chunk in response.iter_content(chunk_size=DIRECT_CHUNK_SIZE):
                            _wait_until_resumed(cancel_event, resume_event)
                            if chunk:
                                _limit_chunk_rate(
                                    len(chunk),
                                    max_speed,
                                    cancel_event,
                                    resume_event,
                                )
                                if bandwidth_limiter and not bandwidth_limiter.acquire(
                                    len(chunk), cancel_event, resume_event
                                ):
                                    raise DownloadCancelled("Download cancelled.")
                                output.write(chunk)
                                downloaded += len(chunk)
                                percent = downloaded * 100 / total if total else None
                                progress(
                                    "Downloading direct file",
                                    percent,
                                    _progress_details(str(target), downloaded, total),
                                )

                    _check_cancelled(cancel_event)
                    target = _final_target(target)
                    partial.replace(target)
                    progress("Download complete", 100.0, str(target))
                    return str(target)
            except requests.RequestException as error:
                last_error = error
                if error.response is not None and 400 <= error.response.status_code < 500:
                    raise RuntimeError(f"Direct download was rejected: {error}") from error
                if attempt == 9:
                    break
                delay = min(2 ** attempt, 30)
                progress(
                    f"Connection lost - retry {attempt + 1}/10 in {delay}s",
                    None,
                    _progress_details(
                        str(target) if target else suggested_name,
                        partial.stat().st_size if partial and partial.exists() else 0,
                        None,
                    ),
                )
                if _wait_for_retry(cancel_event, delay):
                    raise DownloadCancelled("Download cancelled.") from error

        if last_error:
            raise RuntimeError(f"Direct download failed after 10 attempts: {last_error}") from last_error
        raise RuntimeError("Direct download failed.")
    finally:
        try:
            session.close()
        finally:
            _release_target(target)


def _download_with_ytdlp(
    url: str,
    directory: Path,
    mode: str,
    quality: str,
    playlist_scope: str,
    cancel_event: threading.Event,
    progress: ProgressCallback,
    speed_mode: str = "fast",
    resume_event: threading.Event | None = None,
    max_speed: int | None = None,
    bandwidth_limiter: GlobalBandwidthLimiter | None = None,
    proxy: str | None = None,
    browser_cookies: str = "none",
) -> str:
    ffmpeg_directory = _ffmpeg_directory()
    if mode == "mp3 audio" and ffmpeg_directory is None:
        raise RuntimeError(
            "MP3 conversion needs FFmpeg. Install FFmpeg and reopen the app; "
            "see README.md for instructions."
        )

    last_downloaded = [0]
    live_started_at: float | None = None

    def progress_hook(data: dict) -> None:
        nonlocal live_started_at
        _wait_until_resumed(cancel_event, resume_event)
        if data.get("status") == "downloading":
            downloaded = data.get("downloaded_bytes")
            if downloaded is not None:
                delta = max(0, downloaded - last_downloaded[0])
                last_downloaded[0] = downloaded
                if bandwidth_limiter and not bandwidth_limiter.acquire(
                    delta, cancel_event, resume_event
                ):
                    raise DownloadCancelled("Download cancelled.")
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = downloaded * 100 / total if downloaded and total else None
            info_dict = data.get("info_dict") or {}
            is_live = (
                info_dict.get("is_live") is True
                or info_dict.get("live_status") == "is_live"
            )
            if is_live:
                live_started_at = live_started_at or time.monotonic()
                elapsed = int(time.monotonic() - live_started_at)
                details = _progress_details(
                    data.get("filename"),
                    downloaded,
                    total,
                    data.get("speed"),
                )
                details = f"{details} | " if details else ""
                details += f"Recorded {elapsed // 60}:{elapsed % 60:02d}"
                progress("Recording live stream", None, details)
                return
            progress(
                "Downloading media",
                percent,
                _progress_details(
                    data.get("filename"),
                    downloaded,
                    total,
                    data.get("speed"),
                    data.get("eta"),
                ),
            )
        elif data.get("status") == "finished":
            progress(
                "Processing media",
                None,
                _progress_details(data.get("filename"), data.get("downloaded_bytes"), None),
            )

    options: dict = {
        "paths": {"home": str(directory)},
        "outtmpl": {
            "default": "%(playlist_title,playlist|Single Videos)s/%(playlist_index&{} - |)s"
            "%(title).200B [%(id)s].%(ext)s",
        },
        "noplaylist": playlist_scope == "single video",
        "continuedl": True,
        "overwrites": False,
        "retries": 20,
        "fragment_retries": 20,
        "extractor_retries": 5,
        "file_access_retries": 5,
        "socket_timeout": 60,
        "concurrent_fragment_downloads": _fragment_workers(speed_mode),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": False,
    }
    if proxy:
        options["proxy"] = proxy
    if browser_cookies.lower() not in {"", "none", "off"}:
        options["cookiesfrombrowser"] = (browser_cookies.lower(), None, None, None)
    if max_speed is not None and max_speed > 0:
        options["ratelimit"] = max_speed
    if ffmpeg_directory:
        options["ffmpeg_location"] = str(ffmpeg_directory)
    if mode == "mp3 audio":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    elif mode == "best audio":
        options["format"] = "bestaudio/best"
    else:
        options["format"] = _video_format_selector(quality)
        options["merge_output_format"] = "mp4"
        options["allow_multiple_audio_streams"] = True

    _wait_until_resumed(cancel_event, resume_event)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            if mode not in {"mp3 audio", "best audio"}:
                downloader.format_selector = _all_audio_tracks_selector(
                    downloader, quality
                )
                downloader.add_post_processor(_AudioLanguageMetadataPP(downloader))
            info = downloader.extract_info(url, download=True)
    except Exception as error:
        if cancel_event.is_set():
            raise DownloadCancelled("Download cancelled.") from error
        raise
    _check_cancelled(cancel_event)

    if not info:
        return str(directory)
    requested_downloads = info.get("requested_downloads") or []
    filepath = next(
        (item.get("filepath") for item in requested_downloads if item.get("filepath")),
        info.get("_filename"),
    )
    if not filepath:
        return str(directory.resolve())
    result_path = Path(filepath)
    if not result_path.is_absolute():
        result_path = directory / result_path
    return str(result_path.resolve())


def download_url(
    url: str,
    directory: Path,
    source: str,
    mode: str,
    quality: str,
    playlist_scope: str,
    cancel_event: threading.Event,
    progress: ProgressCallback,
    speed_mode: str = "fast",
    resume_event: threading.Event | None = None,
    max_speed: int | None = None,
    bandwidth_limiter: GlobalBandwidthLimiter | None = None,
    job_id: str = "",
    proxy: str = "",
    browser_cookies: str = "none",
) -> str:
    parsed = urlsplit(url)
    selected_source = source.lower()
    torrent_selected = selected_source in {"torrent/magnet", "torrent"}
    if torrent_selected or selected_source == "auto":
        from torrent_engine import download_torrent, is_torrent_url

        torrent_link = is_torrent_url(url)
    else:
        torrent_link = False
    if torrent_selected or (selected_source == "auto" and torrent_link):
        if not torrent_link:
            raise ValueError("Enter a magnet URI or a direct HTTP(S) .torrent link.")
        if proxy or browser_cookies.lower() not in {"", "none", "off"}:
            raise ValueError("Proxies and browser cookies are not supported for torrent links.")
    elif parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS URL.")

    def report(status: str, percent: float | None, details: str) -> None:
        if job_id:
            emit_plugin_event("on_progress", job_id, percent)
        progress(status, percent, _clean_terminal_text(details))

    try:
        if browser_cookies.lower() not in {"", "none", "off"} and browser_cookies.lower() not in {
            "chrome", "firefox", "edge", "brave"
        }:
            raise ValueError(f"Unsupported browser cookie source: {browser_cookies}")
        proxy_rotator = ProxyRotator(proxy)
        if job_id:
            emit_plugin_event("on_start", job_id, url)
        if torrent_selected or (selected_source == "auto" and torrent_link):
            result = download_torrent(
                url, directory, cancel_event, report, resume_event, max_speed,
                bandwidth_limiter,
            )
        network_attempt = 0
        while not (
            torrent_selected or (selected_source == "auto" and torrent_link)
        ):
            _wait_until_resumed(cancel_event, resume_event)
            try:
                if selected_source == "direct file" or (
                    selected_source == "auto"
                    and _is_direct_file_url(url)
                    and mode != "mp3 audio"
                ):
                    result = _download_direct(
                        url, directory, cancel_event, report, resume_event, max_speed,
                        speed_mode, bandwidth_limiter, proxy, browser_cookies,
                    )
                else:
                    result = ""
                    for attempt in range(max(proxy_rotator.count, 1)):
                        try:
                            result = _download_with_ytdlp(
                                url,
                                directory,
                                mode,
                                quality,
                                playlist_scope,
                                cancel_event,
                                report,
                                speed_mode,
                                resume_event,
                                max_speed,
                                bandwidth_limiter,
                                proxy_rotator.next_url(),
                                browser_cookies,
                            )
                            break
                        except DownloadCancelled:
                            raise
                        except Exception:
                            if attempt + 1 >= max(proxy_rotator.count, 1):
                                raise
                break
            except DownloadCancelled:
                raise
            except Exception as error:
                if cancel_event.is_set():
                    raise DownloadCancelled("Download cancelled.") from error
                if not _is_transient_network_error(error):
                    raise RuntimeError(_clean_terminal_text(error)) from error
                network_attempt += 1
                delay = min(5 * (2 ** min(network_attempt - 1, 4)), 60)
                detail = _clean_terminal_text(error)
                report(
                    "Waiting for connection",
                    None,
                    f"Network unavailable: {detail}. Retrying in {delay}s "
                    f"(attempt {network_attempt}).",
                )
                if not _wait_for_network_retry(cancel_event, resume_event, delay):
                    raise DownloadCancelled("Download cancelled while waiting for the network.")
        if job_id:
            replacement = emit_plugin_event("on_complete", job_id, result)
            if replacement is not None:
                result = str(replacement)
        return result
    except DownloadCancelled:
        if job_id:
            emit_plugin_event("on_cancel", job_id)
        raise
    except Exception as error:
        if job_id:
            emit_plugin_event("on_error", job_id, error)
        raise
