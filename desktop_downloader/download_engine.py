from __future__ import annotations

import email.message
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urlsplit

import requests
import yt_dlp


ProgressCallback = Callable[[str, float | None, str], None]
DIRECT_CHUNK_SIZE = 1024 * 1024
FRAGMENT_WORKERS = {"balanced": 4, "fast": 8, "maximum": 16}
PARALLEL_MIN_SIZE = 4 * 1024 * 1024
PARALLEL_RETRIES = 5
DIRECT_FILE_EXTENSIONS = {
    ".7z", ".aac", ".avi", ".csv", ".doc", ".docx", ".flac", ".gif", ".gz",
    ".jpeg", ".jpg", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".mpeg", ".mpg",
    ".msi", ".ods", ".odt", ".ogg", ".pdf", ".png", ".ppt", ".pptx", ".rar",
    ".tar", ".txt", ".wav", ".webm", ".webp", ".wmv", ".xls", ".xlsx", ".zip",
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", re.IGNORECASE)
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


def _check_cancelled(cancel_event: threading.Event) -> None:
    if cancel_event.is_set():
        raise DownloadCancelled("Download cancelled.")


def _wait_until_resumed(
    cancel_event: threading.Event,
    pause_event: threading.Event | None,
) -> None:
    while pause_event is not None and not pause_event.is_set():
        _check_cancelled(cancel_event)
        pause_event.wait(0.25)
    _check_cancelled(cancel_event)


def _fragment_workers(speed_mode: str) -> int:
    return FRAGMENT_WORKERS.get(speed_mode, FRAGMENT_WORKERS["fast"])


def _wait_for_retry(cancel_event: threading.Event, delay: int) -> bool:
    return cancel_event.wait(delay)


def _limit_chunk_rate(
    chunk_size: int,
    max_speed: int | None,
    cancel_event: threading.Event,
    pause_event: threading.Event | None,
) -> None:
    if max_speed is None or max_speed <= 0:
        return

    remaining = chunk_size / max_speed
    while remaining > 0:
        _wait_until_resumed(cancel_event, pause_event)
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
    if filename.split(".", 1)[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        filename = f"_{filename}"
    return filename[:180]


def _video_format_selector(quality: str) -> str:
    height = QUALITY_HEIGHTS.get(quality)
    if height is None:
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"


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
    pause_event: threading.Event | None,
    progress: ProgressCallback,
) -> str:
    partial = target.with_name(target.name + ".part")
    metadata_path = _parallel_metadata_path(target)
    metadata: dict = {}
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
            completed_bytes += min(segment_path.stat().st_size, segment["end"] - segment["start"] + 1)

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
            _wait_until_resumed(cancel_event, pause_event)
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
                            _wait_until_resumed(cancel_event, pause_event)
                            if not chunk:
                                continue
                            if output.tell() + len(chunk) > expected_length:
                                raise RuntimeError("The server sent more bytes than requested.")
                            output.write(chunk)
                            with progress_lock:
                                nonlocal_completed[0] += len(chunk)
                                progress(
                                    "Downloading direct file (parallel ranges)",
                                    nonlocal_completed[0] * 100 / total,
                                    _progress_details(str(target), nonlocal_completed[0], total),
                                )

                if segment_path.stat().st_size != expected_length:
                    raise requests.ConnectionError("The server closed before this range completed.")
                return
            except requests.RequestException:
                if attempt + 1 >= PARALLEL_RETRIES:
                    raise
                _wait_until_resumed(cancel_event, pause_event)
                if cancel_event.wait(min(2**attempt, 8)):
                    raise DownloadCancelled("Download cancelled.")

    nonlocal_completed = [completed_bytes]
    with ThreadPoolExecutor(max_workers=len(segments)) as executor:
        futures = [executor.submit(download_segment, segment) for segment in segments]
        for future in as_completed(futures):
            future.result()

    _wait_until_resumed(cancel_event, pause_event)
    with partial.open("wb") as output:
        for segment in segments:
            segment_path = _parallel_segment_path(target, segment["index"])
            with segment_path.open("rb") as input_file:
                shutil.copyfileobj(input_file, output, length=DIRECT_CHUNK_SIZE)
    if partial.stat().st_size != total:
        partial.unlink(missing_ok=True)
        raise RuntimeError("Parallel download did not produce the expected file size.")

    final_target = _final_target(target)
    partial.replace(final_target)
    for segment in segments:
        _parallel_segment_path(target, segment["index"]).unlink(missing_ok=True)
    metadata_path.unlink(missing_ok=True)
    progress("Download complete", 100.0, str(final_target))
    return str(final_target)


def _download_direct(
    url: str,
    directory: Path,
    cancel_event: threading.Event,
    progress: ProgressCallback,
    pause_event: threading.Event | None = None,
    max_speed: int | None = None,
    speed_mode: str = "fast",
) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
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
        if target is None and max_speed is None and _fragment_workers(speed_mode) > 1:
            parallel_info: tuple[str, int, str] | None = None
            try:
                with session.get(
                    url,
                    headers={"Range": "bytes=0-0"},
                    stream=True,
                    timeout=(15, 60),
                    allow_redirects=True,
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
                        metadata_path = _parallel_metadata_path(candidate)
                        partial = candidate.with_name(candidate.name + ".part")
                        validator = (
                            "etag:" + probe.headers["ETag"]
                            if probe.headers.get("ETag")
                            else "last-modified:" + probe.headers["Last-Modified"]
                            if probe.headers.get("Last-Modified")
                            else ""
                        )
                        if (
                            total >= PARALLEL_MIN_SIZE
                            and validator
                            and (metadata_path.exists() or not partial.exists())
                        ):
                            parallel_info = (candidate_name, total, validator)
            except requests.RequestException:
                parallel_info = None

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
                    pause_event,
                    progress,
                )

        for attempt in range(10):
            _wait_until_resumed(cancel_event, pause_event)
            headers = {}
            partial = target.with_name(target.name + ".part") if target else None
            existing = partial.stat().st_size if partial and partial.exists() else 0
            if existing:
                headers["Range"] = f"bytes={existing}-"

            try:
                with session.get(
                    url, headers=headers, stream=True, timeout=(15, 60), allow_redirects=True
                ) as response:
                    if response.status_code == 416 and partial and partial.exists():
                        content_range = response.headers.get("Content-Range", "")
                        match = re.fullmatch(r"bytes \*/(\d+)", content_range, re.IGNORECASE)
                        if match and int(match.group(1)) == existing:
                            final_target = _final_target(target)
                            partial.replace(final_target)
                            target = final_target
                            return str(final_target)
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
                            _wait_until_resumed(cancel_event, pause_event)
                            if chunk:
                                output.write(chunk)
                                _limit_chunk_rate(
                                    len(chunk),
                                    max_speed,
                                    cancel_event,
                                    pause_event,
                                )
                                downloaded += len(chunk)
                                percent = downloaded * 100 / total if total else None
                                progress(
                                    "Downloading direct file",
                                    percent,
                                    _progress_details(str(target), downloaded, total),
                                )

                    _check_cancelled(cancel_event)
                    final_target = _final_target(target)
                    partial.replace(final_target)
                    target = final_target
                    progress("Download complete", 100.0, str(final_target))
                    return str(final_target)
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
        session.close()
        if target is not None:
            with TARGET_LOCK:
                ACTIVE_TARGETS.discard(_target_key(target))


def _download_with_ytdlp(
    url: str,
    directory: Path,
    mode: str,
    quality: str,
    playlist_scope: str,
    cancel_event: threading.Event,
    progress: ProgressCallback,
    speed_mode: str = "fast",
    pause_event: threading.Event | None = None,
    max_speed: int | None = None,
) -> str:
    ffmpeg_directory = _ffmpeg_directory()
    if mode == "mp3 audio" and ffmpeg_directory is None:
        raise RuntimeError(
            "MP3 conversion needs FFmpeg. Install FFmpeg and reopen the app; "
            "see desktop_downloader/README.md for instructions."
        )

    def progress_hook(data: dict) -> None:
        _wait_until_resumed(cancel_event, pause_event)
        if data.get("status") == "downloading":
            downloaded = data.get("downloaded_bytes")
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = downloaded * 100 / total if downloaded and total else None
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

    _wait_until_resumed(cancel_event, pause_event)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
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
    pause_event: threading.Event | None = None,
    max_speed: int | None = None,
) -> str:
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid HTTP or HTTPS URL.")

    selected_source = source.lower()
    if selected_source == "direct file" or (
        selected_source == "auto" and _is_direct_file_url(url) and mode != "mp3 audio"
    ):
        return _download_direct(
            url,
            directory,
            cancel_event,
            progress,
            pause_event,
            max_speed,
            speed_mode,
        )

    return _download_with_ytdlp(
        url,
        directory,
        mode,
        quality,
        playlist_scope,
        cancel_event,
        progress,
        speed_mode,
        pause_event,
        max_speed,
    )
