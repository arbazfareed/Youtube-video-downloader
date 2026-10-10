from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from download_engine import DownloadCancelled, ProgressCallback


RPC_START_TIMEOUT = 15.0
POLL_INTERVAL = 0.5
RPC_FIELDS = [
    "gid",
    "status",
    "infoHash",
    "totalLength",
    "completedLength",
    "downloadSpeed",
    "uploadSpeed",
    "files",
    "errorMessage",
]


def _find_aria2() -> str | None:
    executable = shutil.which("aria2c")
    if executable:
        return executable

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            package_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
            for candidate in package_root.glob("aria2.aria2*/*/aria2c.exe"):
                if candidate.is_file():
                    return str(candidate)
    return None


def is_torrent_url(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme.lower() == "magnet":
        return any(
            value.lower().startswith(("urn:btih:", "urn:btmh:"))
            for key, value in parse_qsl(parsed.query)
            if key.lower() == "xt"
        )
    return (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.hostname is not None
        and parsed.path.lower().endswith(".torrent")
    )


def _rpc_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _rpc_call(endpoint: str, secret: str, method: str, *arguments: object) -> object:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": "smart-downloader",
        "method": f"aria2.{method}",
        "params": [f"token:{secret}", *arguments],
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=4) as response:
        result = json.loads(response.read().decode("utf-8"))
    if "error" in result:
        error = result["error"]
        raise RuntimeError(f"aria2 RPC {method} failed: {error.get('message', error)}")
    return result.get("result")


def _aria2_process_error(process: subprocess.Popen[bytes], log_file) -> str:
    log_file.flush()
    log_file.seek(0)
    details = log_file.read().decode("utf-8", errors="replace").strip()
    return details or f"aria2c exited with code {process.returncode}."


def _find_torrent_status(
    endpoint: str,
    secret: str,
    is_magnet: bool,
) -> dict | None:
    active = _rpc_list(endpoint, secret, "tellActive", RPC_FIELDS)
    waiting = _rpc_list(endpoint, secret, "tellWaiting", 0, 1000, RPC_FIELDS)
    stopped = _rpc_list(endpoint, secret, "tellStopped", 0, 1000, RPC_FIELDS)
    entries = [*active, *waiting, *stopped]
    torrent_entries = [entry for entry in entries if entry.get("infoHash")]
    if torrent_entries:
        return torrent_entries[0]
    if is_magnet and entries:
        return entries[0]
    return None


def _rpc_list(
    endpoint: str,
    secret: str,
    method: str,
    *arguments: object,
) -> list[dict]:
    result = _rpc_call(endpoint, secret, method, *arguments)
    if not isinstance(result, list):
        raise RuntimeError(f"aria2 returned an invalid {method} response.")
    return result


def _rpc_status(endpoint: str, secret: str, gid: str) -> dict:
    result = _rpc_call(endpoint, secret, "tellStatus", gid, RPC_FIELDS)
    if not isinstance(result, dict):
        raise RuntimeError("aria2 returned an invalid torrent status response.")
    return result


def _format_details(status: dict) -> str:
    total = int(status.get("totalLength") or 0)
    completed = int(status.get("completedLength") or 0)
    speed = int(status.get("downloadSpeed") or 0)
    file_entries = status.get("files") or []
    filename = ""
    if file_entries:
        filename = Path(file_entries[0].get("path") or "").name
    parts = [filename] if filename else ["Torrent"]
    if total:
        parts.append(f"{completed / 1048576:.1f} / {total / 1048576:.1f} MB")
    if speed:
        parts.append(
            f"{speed / 1048576:.2f} MB/s"
            if speed >= 1048576
            else f"{speed / 1024:.0f} KB/s"
        )
    upload = int(status.get("uploadSpeed") or 0)
    if upload:
        parts.append(f"upload {upload / 1024:.0f} KB/s")
    return " | ".join(parts)


def download_torrent(
    url: str,
    directory: Path,
    cancel_event: threading.Event,
    progress: ProgressCallback,
    pause_event: threading.Event | None = None,
    max_speed: int | None = None,
) -> str:
    executable = _find_aria2()
    if executable is None:
        raise RuntimeError(
            "Torrent downloads need aria2c. Install aria2, restart Smart Downloader 10.0, "
            "and try again. See SETUP.md."
        )

    directory.mkdir(parents=True, exist_ok=True)
    port = _rpc_port()
    secret = secrets.token_urlsafe(24)
    endpoint = f"http://127.0.0.1:{port}/jsonrpc"
    command = [
        executable,
        "--enable-rpc=true",
        "--rpc-listen-all=false",
        "--rpc-listen-port",
        str(port),
        "--rpc-secret",
        secret,
        "--follow-torrent=true",
        "--seed-time=0",
        "--seed-ratio=0.0",
        "--max-tries=10",
        "--retry-wait=5",
        "--connect-timeout=15",
        "--timeout=60",
        "--summary-interval=0",
        "--console-log-level=warn",
        "--dir",
        str(directory.resolve()),
    ]
    if max_speed is not None:
        command.append(f"--max-download-limit={max_speed}")
    command.append(url)

    is_magnet = urlsplit(url).scheme.lower() == "magnet"
    process: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryFile(mode="w+b") as log_file:
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log_file,
                creationflags=creation_flags,
            )
            progress("Preparing torrent", 0.0, "Connecting to aria2")
            start_deadline = time.monotonic() + RPC_START_TIMEOUT
            paused = False
            gid: str | None = None
            latest_status: dict | None = None

            while True:
                if cancel_event.is_set():
                    raise DownloadCancelled("Torrent download cancelled.")
                if process.poll() is not None:
                    raise RuntimeError(_aria2_process_error(process, log_file))

                if time.monotonic() < start_deadline:
                    try:
                        found_status = _find_torrent_status(endpoint, secret, is_magnet)
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        found_status = None
                    if found_status is not None:
                        gid = str(found_status["gid"])
                        latest_status = found_status
                        break
                    time.sleep(POLL_INTERVAL)
                    continue

                if gid is None:
                    raise RuntimeError(
                        "aria2 did not start a torrent job. Check the .torrent link or magnet URI."
                    )

            while True:
                if cancel_event.is_set():
                    raise DownloadCancelled("Torrent download cancelled.")

                should_pause = pause_event is not None and not pause_event.is_set()
                if should_pause != paused:
                    method = "pause" if should_pause else "unpause"
                    _rpc_call(endpoint, secret, method, gid)
                    paused = should_pause

                try:
                    latest_status = _rpc_status(endpoint, secret, gid)
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    if process.poll() is not None:
                        raise RuntimeError(_aria2_process_error(process, log_file))
                    time.sleep(POLL_INTERVAL)
                    continue

                status_name = latest_status.get("status", "")
                if status_name == "error":
                    raise RuntimeError(
                        latest_status.get("errorMessage") or "aria2 torrent download failed."
                    )
                if status_name == "complete":
                    progress("Download complete", 100.0, _format_details(latest_status))
                    files = latest_status.get("files") or []
                    if files:
                        paths = [Path(entry["path"]) for entry in files if entry.get("path")]
                        if paths:
                            return str(paths[0] if len(paths) == 1 else directory.resolve())
                    return str(directory.resolve())

                total = int(latest_status.get("totalLength") or 0)
                completed = int(latest_status.get("completedLength") or 0)
                percent = completed * 100 / total if total else None
                label = "Paused" if paused else "Downloading torrent"
                progress(label, percent, _format_details(latest_status))
                time.sleep(POLL_INTERVAL)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
