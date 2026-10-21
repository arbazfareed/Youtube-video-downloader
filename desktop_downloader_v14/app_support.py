from __future__ import annotations

import queue
import os
import re
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import hashlib
import json
import webbrowser
import tkinter as tk
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib.parse import urlsplit

from requests.exceptions import RequestException

from bandwidth import GlobalBandwidthLimiter
from checksum import calculate_checksum, verify_checksum
from cloud_storage import (
    is_configured,
    save_credentials,
    select_upload_source,
    upload_path,
)
from cookies import SUPPORTED_BROWSERS
from document_engine import convert_docx_to_pdf, convert_pdf_to_docx
from download_engine import (
    DownloadCancelled,
    RetryPolicy,
    _clean_terminal_text,
    _ffmpeg_directory,
    download_url,
    parse_custom_headers,
)
from extract import extract_archive
from history_store import DownloadHistory, normalize_url
from image_engine import (
    convert_image,
    generate_sequence_urls,
    resize_image,
    scrape_image_urls,
    strip_exif,
)
from notifications import notify
from plugins import load_plugins
from proxy import parse_proxy_list
from torrent_engine import is_torrent_url
from zip_archive import create_zip_archive
from diagnostics import diagnostics_path, export_diagnostics, record_diagnostic
from localization import LANGUAGES, translate
from update_engine import (
    APP_VERSION,
    NoPublishedReleaseError,
    UpdateError,
    check_for_update,
    download_verified_update,
    update_ytdlp,
)


MAX_SPEEDS = {
    "Unlimited": None,
    "256 KB/s": 256 * 1024,
    "512 KB/s": 512 * 1024,
    "1 MB/s": 1024 * 1024,
    "2 MB/s": 2 * 1024 * 1024,
    "5 MB/s": 5 * 1024 * 1024,
}
PLAYABLE_MEDIA_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".ogg", ".wav", ".webm", ".wmv",
}
VIDEO_MEDIA_EXTENSIONS = {
    ".avi", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".webm", ".wmv",
}
AUDIO_MEDIA_EXTENSIONS = {
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav",
}
FINISHED_STATUSES = {"Complete", "Failed", "Cancelled", "Interrupted"}
MEDIA_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".gif", ".jpeg", ".jpg", ".m4a", ".mkv",
    ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".png", ".wav",
    ".webm", ".webp", ".wmv",
}


def probe_audio_streams(source: Path, ffmpeg_directory: Path | None = None) -> list[dict]:
    if ffmpeg_directory is None:
        ffmpeg_directory = _ffmpeg_directory()
    ffprobe_executable = None
    if ffmpeg_directory:
        candidate = ffmpeg_directory / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if candidate.is_file():
            ffprobe_executable = candidate
    if not ffprobe_executable:
        which_probe = shutil.which("ffprobe")
        if which_probe:
            ffprobe_executable = Path(which_probe)
    
    if not ffprobe_executable or not Path(source).is_file():
        return []

    try:
        result = subprocess.run(
            [
                str(ffprobe_executable),
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=index,codec_name,channels:stream_tags=language,title",
                "-of", "json",
                str(source),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        parsed = []
        for s in streams:
            idx = s.get("index")
            if idx is None:
                continue
            tags = s.get("tags") or {}
            lang = tags.get("language") or "und"
            title = tags.get("title") or ""
            codec = s.get("codec_name") or ""
            channels = s.get("channels") or 2
            parsed.append({
                "index": int(idx),
                "language": str(lang),
                "title": str(title),
                "codec": str(codec),
                "channels": int(channels),
            })
        return parsed
    except Exception:
        return []


def extract_video_thumbnail(
    source: Path,
    destination: Path | None = None,
    ffmpeg_directory: Path | None = None,
) -> Path | None:
    source = Path(source)
    if not source.is_file():
        return None
    if ffmpeg_directory is None:
        ffmpeg_directory = _ffmpeg_directory()
    ffmpeg = None
    if ffmpeg_directory:
        candidate = ffmpeg_directory / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if candidate.is_file():
            ffmpeg = candidate
    if not ffmpeg:
        which = shutil.which("ffmpeg")
        if which:
            ffmpeg = Path(which)
    if not ffmpeg:
        return None
    if destination is None:
        thumb_dir = Path(tempfile.gettempdir()) / "smart_downloader_thumbs"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        try:
            mtime = int(source.stat().st_mtime)
        except OSError:
            mtime = 0
        dest_name = f"{hashlib.md5(f'{source}_{mtime}'.encode()).hexdigest()[:16]}.png"
        destination = thumb_dir / dest_name
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    try:
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-y", "-ss", "00:00:01", "-i", str(source),
            "-vframes", "1", "-vf", "scale=320:-1", str(destination),
        ]
        res = subprocess.run(cmd, capture_output=True, check=False, timeout=8)
        if res.returncode == 0 and destination.is_file() and destination.stat().st_size > 0:
            return destination
    except Exception:
        pass
    return None


def _convert_media_to_mp3(
    source: Path,
    destination: Path,
    ffmpeg_directory: Path,
    stream_index: int | str | None = None,
) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.stem}.",
            suffix=".mp3",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        temporary_path.unlink()
        ffmpeg = ffmpeg_directory / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        cmd = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-y", "-i", str(source),
        ]
        if stream_index is not None:
            map_spec = str(stream_index) if ":" in str(stream_index) else f"0:{stream_index}"
            cmd.extend(["-map", map_spec])
        cmd.extend([
            "-vn", "-codec:a", "libmp3lame",
            "-q:a", "2", str(temporary_path),
        ])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            error = result.stderr.strip() or f"FFmpeg exited with status {result.returncode}."
            raise RuntimeError(f"MP3 conversion failed: {error}")
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

__all__ = [
    'queue',
    'os',
    're',
    'sqlite3',
    'shutil',
    'subprocess',
    'sys',
    'tempfile',
    'threading',
    'time',
    'hashlib',
    'json',
    'webbrowser',
    'tk',
    'Callable',
    'Future',
    'ThreadPoolExecutor',
    'datetime',
    'Path',
    'filedialog',
    'messagebox',
    'simpledialog',
    'ttk',
    'urlsplit',
    'RequestException',
    'GlobalBandwidthLimiter',
    'verify_checksum',
    'calculate_checksum',
    'diagnostics_path',
    'export_diagnostics',
    'record_diagnostic',
    'LANGUAGES',
    'translate',
    'UpdateError',
    'check_for_update',
    'download_verified_update',
    'APP_VERSION',
    'NoPublishedReleaseError',
    'is_configured',
    'save_credentials',
    'select_upload_source',
    'upload_path',
    'SUPPORTED_BROWSERS',
    'convert_docx_to_pdf',
    'convert_pdf_to_docx',
    'DownloadCancelled',
    'RetryPolicy',
    '_clean_terminal_text',
    '_ffmpeg_directory',
    'download_url',
    'parse_custom_headers',
    'extract_archive',
    'DownloadHistory',
    'normalize_url',
    'convert_image',
    'generate_sequence_urls',
    'resize_image',
    'scrape_image_urls',
    'strip_exif',
    'create_zip_archive',
    'notify',
    'load_plugins',
    'parse_proxy_list',
    'is_torrent_url',
    'MAX_SPEEDS',
    'PLAYABLE_MEDIA_EXTENSIONS',
    'VIDEO_MEDIA_EXTENSIONS',
    'AUDIO_MEDIA_EXTENSIONS',
    'FINISHED_STATUSES',
    'MEDIA_EXTENSIONS',
    '_convert_media_to_mp3',
    'probe_audio_streams',
    'extract_video_thumbnail',
]
