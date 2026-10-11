from __future__ import annotations

import argparse
import re
import sys
import threading
from pathlib import Path

from requests.exceptions import RequestException
from yt_dlp.utils import DownloadError

from checksum import verify_checksum
from download_engine import DownloadCancelled, download_url


def _positive_rate(value: str) -> int:
    try:
        rate = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("cap must be a positive number of bytes per second") from error
    if rate <= 0:
        raise argparse.ArgumentTypeError("cap must be greater than zero")
    return rate


def _parse_checksum(value: str) -> tuple[str, str]:
    algorithm, digest = (value.split(":", 1) if ":" in value else ("", value))
    if not algorithm:
        algorithm = "md5" if len(digest) == 32 else "sha256"
    algorithm = algorithm.lower()
    expected_length = {"md5": 32, "sha256": 64}.get(algorithm)
    if expected_length is None or len(digest) != expected_length or not re.fullmatch(r"[0-9a-fA-F]+", digest):
        raise argparse.ArgumentTypeError("checksum must be md5:<32 hex digits> or sha256:<64 hex digits>")
    return algorithm, digest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a public file, supported media, or torrent link.")
    parser.add_argument("url", help="public HTTP(S) URL or magnet URI")
    parser.add_argument("-o", "--output", type=Path, default=Path("downloads"), help="destination folder")
    parser.add_argument(
        "--source",
        choices=("auto", "direct file", "supported site", "torrent/magnet"),
        default="auto",
    )
    parser.add_argument("--mode", choices=("video", "best audio", "mp3 audio"), default="video")
    parser.add_argument("--quality", default="1080p", help="maximum video height, such as 1080p or best")
    parser.add_argument("--speed", choices=("balanced", "fast", "maximum"), default="fast")
    parser.add_argument("--cap", type=_positive_rate, help="per-download byte-per-second cap")
    parser.add_argument("--proxy", default="", help="proxy URL(s), comma-separated for retries")
    parser.add_argument(
        "--cookies",
        choices=("none", "chrome", "firefox", "edge", "brave"),
        default="none",
        help="use cookies from an installed browser",
    )
    parser.add_argument("--checksum", type=_parse_checksum, help="expected digest: md5:<hex> or sha256:<hex>")
    parser.add_argument(
        "--playlist-scope",
        choices=("auto (from link)", "single video", "entire playlist"),
        default="auto (from link)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cancel_event = threading.Event()
    resume_event = threading.Event()
    resume_event.set()

    def report(status: str, percent: float | None, details: str) -> None:
        percent_text = "working" if percent is None else f"{percent:.1f}%"
        print(f"\r{status}: {percent_text} {details}", end="", file=sys.stderr, flush=True)

    try:
        args.output.expanduser().mkdir(parents=True, exist_ok=True)
        result = download_url(
            args.url,
            args.output.expanduser(),
            args.source,
            args.mode,
            args.quality.lower(),
            args.playlist_scope,
            cancel_event,
            report,
            args.speed,
            resume_event,
            args.cap,
            None,
            "cli",
            args.proxy,
            args.cookies,
        )
        print(file=sys.stderr)
        if args.checksum:
            output = Path(result)
            if not output.is_file():
                print("Checksum verification requires a single downloaded file.", file=sys.stderr)
                return 1
            algorithm, expected = args.checksum
            actual, matches = verify_checksum(output, algorithm, expected)
            if not matches:
                print(
                    f"Checksum mismatch: expected {expected}, calculated {actual}.",
                    file=sys.stderr,
                )
                return 1
            print(f"Verified {algorithm.upper()} checksum: {actual}", file=sys.stderr)
        print(result)
        return 0
    except (DownloadCancelled, KeyboardInterrupt):
        cancel_event.set()
        print("\nDownload cancelled.", file=sys.stderr)
        return 130
    except (OSError, RuntimeError, ValueError, RequestException, DownloadError) as error:
        print(f"\nDownload failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
