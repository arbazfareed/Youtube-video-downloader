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
from checksum import verify_checksum
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
    _clean_terminal_text,
    _ffmpeg_directory,
    download_url,
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
FINISHED_STATUSES = {"Complete", "Failed", "Cancelled", "Interrupted"}
MEDIA_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".gif", ".jpeg", ".jpg", ".m4a", ".mkv",
    ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".png", ".wav",
    ".webm", ".webp", ".wmv",
}


def _convert_media_to_mp3(source: Path, destination: Path, ffmpeg_directory: Path) -> None:
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
        result = subprocess.run(
            [
                str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin",
                "-y", "-i", str(source), "-vn", "-codec:a", "libmp3lame",
                "-q:a", "2", str(temporary_path),
            ],
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
    'is_configured',
    'save_credentials',
    'select_upload_source',
    'upload_path',
    'SUPPORTED_BROWSERS',
    'convert_docx_to_pdf',
    'convert_pdf_to_docx',
    'DownloadCancelled',
    '_clean_terminal_text',
    '_ffmpeg_directory',
    'download_url',
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
    'FINISHED_STATUSES',
    'MEDIA_EXTENSIONS',
    '_convert_media_to_mp3',
]
