"""Download real videos with the app's own engine and report what worked.

Run by the "v14 live site check" GitHub workflow (nothing is downloaded to the
user's computer), or by hand:

    python live_check.py                       # built-in list of public test videos
    python live_check.py URL [URL ...]         # your own links
    LIVE_CHECK_URLS="name|mode|url[|timeout seconds]" python live_check.py

Each job uses the same download engine, three-at-a-time scheduler, history
database and media health check as the app. Every finished file is probed with
ffprobe so "Complete" means a playable file with the expected streams.

Exit code: 1 only if a *required* check fails. Sites such as YouTube can refuse
datacenter addresses, so they are reported but never fail the run by themselves.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from download_engine import RetryPolicy, download_url
from download_scheduler import DownloadScheduler
from history_store import DownloadHistory
from media_health import inspect_download


@dataclass
class Check:
    name: str
    mode: str
    url: str
    required: bool = False   # a failure here fails the whole run
    expect_video: bool = True
    timeout: int = 150       # seconds before the check is cancelled and reported


DEFAULT_CHECKS = [
    # Plain files: no site can block these, so they must always work.
    Check("Direct MP4 (MDN flower, CC0)", "video",
          "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", True),
    Check("Direct MP4 (w3schools sample)", "video",
          "https://www.w3schools.com/html/mov_bbb.mp4", True),
    Check("Direct MP4 as MP3 audio", "mp3 audio",
          "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4", True,
          expect_video=False),
    # Real video sites: informational, the site may refuse a cloud address.
    Check("YouTube: Me at the zoo", "video", "https://www.youtube.com/watch?v=jNQXAC9IVRw"),
    Check("YouTube: yt-dlp test clip", "video", "https://www.youtube.com/watch?v=BaW_jenozKc"),
    Check("YouTube audio as MP3", "mp3 audio", "https://www.youtube.com/watch?v=BaW_jenozKc",
          expect_video=False),
    Check("Vimeo test video", "video", "https://vimeo.com/56015672"),
    # Small public items from other sites (taken from yt-dlp's own extractor tests).
    Check("Bandcamp test song (audio)", "video",
          "http://youtube-dl.bandcamp.com/track/youtube-dl-test-song", expect_video=False),
    Check("PeerTube test video", "video",
          "https://peertube2.cpy.re/w/122d093a-1ede-43bd-bd34-59d2931ffc5e"),
]


def parse_checks(argv: list[str]) -> list[Check]:
    if argv:
        return [Check(url, "video", url) for url in argv]
    raw = os.environ.get("LIVE_CHECK_URLS", "").strip()
    if not raw:
        return list(DEFAULT_CHECKS)
    checks = []
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) in (3, 4) and parts[2]:
            limit = int(parts[3]) if len(parts) == 4 and parts[3].isdigit() else 150
            checks.append(Check(parts[0], parts[1], parts[2], required=True,
                                expect_video=parts[1].lower() == "video", timeout=limit))
        elif line.strip().startswith("http"):
            checks.append(Check(line.strip(), "video", line.strip()))
    return checks


def probe_streams(path: Path) -> tuple[set[str], float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.is_file():
        return set(), 0.0
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "stream=codec_type:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        data = json.loads(result.stdout or "{}")
        kinds = {stream["codec_type"] for stream in data.get("streams", [])}
        return kinds, float(data.get("format", {}).get("duration") or 0)
    except (ValueError, KeyError):
        return set(), 0.0


def _resolve_case_insensitive_output(saved: str | Path, search_root: Path) -> Path:
    """Resolve filename casing differences reported by remote extractors."""
    expected = Path(saved)
    if expected.is_file() or not expected.parent.is_dir():
        return expected
    try:
        matches = [
            item for item in expected.parent.iterdir()
            if item.is_file() and item.name.casefold() == expected.name.casefold()
        ]
    except OSError:
        return expected
    return matches[0] if len(matches) == 1 else expected


def run_check(check: Check, index: int, history: DownloadHistory, folder: Path,
              scheduler: DownloadScheduler) -> dict:
    history_id = history.add(check.url, "Queued", str(folder))
    job_id = str(history_id)
    user_event = threading.Event()
    user_event.set()
    gate = scheduler.gate(job_id, user_event)
    started = time.monotonic()

    def job() -> dict:
        outcome = {"check": check, "status": "Failed", "detail": "", "seconds": 0.0}
        cancel_event = threading.Event()
        timed_out = threading.Event()

        def give_up() -> None:
            timed_out.set()
            cancel_event.set()

        timer = threading.Timer(check.timeout, give_up)
        timer.daemon = True
        timer.start()
        print(f"START  {check.name} ({check.mode})", flush=True)
        try:
            saved = download_url(
                check.url, folder / f"{index:02d}", "auto", check.mode, "720p",
                "single video", cancel_event, lambda *_a: None, "fast", gate,
                None, None, job_id, "", "none",
                retry_policy=RetryPolicy(3, 1.0, 5.0),
            )
            saved = str(_resolve_case_insensitive_output(saved, folder / f"{index:02d}"))
            healthy, message = inspect_download(saved)
            if not healthy:
                raise RuntimeError(message)
            saved_path = Path(saved)
            files = [saved_path] if saved_path.is_file() else sorted(
                p for p in saved_path.rglob("*") if p.is_file())
            kinds, seconds = probe_streams(files[0]) if files else (set(), 0.0)
            if shutil.which("ffprobe"):
                if "audio" not in kinds:
                    raise RuntimeError(f"saved file has no audio stream ({sorted(kinds)})")
                if check.expect_video and "video" not in kinds:
                    raise RuntimeError(f"saved file has no video stream ({sorted(kinds)})")
                if not check.expect_video and "video" in kinds:
                    raise RuntimeError("audio mode saved a file that still has video")
            history.update(history_id, "Complete", "100%", str(saved), str(folder))
            outcome.update(status="Complete",
                           detail=f"{Path(files[0]).name if files else saved} "
                                  f"({'+'.join(sorted(kinds)) or 'unprobed'}, {seconds:.0f}s)")
        except BaseException as error:  # noqa: BLE001 - report every failure
            text = " ".join(str(error).split())[:240]
            if timed_out.is_set():
                text = f"Timed out after {check.timeout}s (no finish); last error: {text}"
            if "was not created" in text:
                # Show what the download really left on disk, to spot a name or format mismatch.
                saved = sorted(
                    str(item.relative_to(folder / f"{index:02d}"))
                    for item in (folder / f"{index:02d}").rglob("*") if item.is_file()
                )
                text += f" | files on disk: {saved[:6] or 'none'}"
            history.update(history_id, "Failed", "-", text, str(folder))
            outcome["detail"] = text
        finally:
            timer.cancel()
        outcome["seconds"] = time.monotonic() - started
        label = "PASS" if outcome["status"] == "Complete" else "FAIL"
        print(f"{label}   {check.name}: {outcome['detail'] or '-'} ({outcome['seconds']:.0f}s)", flush=True)
        return outcome

    return scheduler.submit(job_id, job)


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    checks = parse_checks(argv)
    folder = Path(tempfile.mkdtemp(prefix="live-check-"))
    history = DownloadHistory(folder / "history.db")
    scheduler = DownloadScheduler(3)   # same default as the app: 3 at a time
    futures = [run_check(c, i, history, folder, scheduler) for i, c in enumerate(checks, 1)]
    results = []
    for check, future in zip(checks, futures):
        try:
            results.append(future.result(timeout=check.timeout + 120))
        except Exception as error:  # a worker that never came back
            results.append({"check": check, "status": "Failed", "seconds": 0.0,
                            "detail": f"Did not stop after {check.timeout + 120}s: {error!r}"[:240]})

    lines = ["| Result | Check | Mode | Detail |", "|---|---|---|---|"]
    for item in results:
        check = item["check"]
        icon = "PASS" if item["status"] == "Complete" else ("FAIL" if check.required else "BLOCKED/FAILED")
        lines.append(f"| {icon} | {check.name} | {check.mode} | {item['detail'] or '-'} |")
    reloaded = DownloadHistory(folder / "history.db").list_records()
    done = sum(1 for record in reloaded if record.status == "Complete")
    lines.append("")
    lines.append(f"History after reload: {done} complete of {len(reloaded)} recorded. "
                 f"Parallel limit: {scheduler.max_parallel}.")
    table = "\n".join(lines)
    print(table)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## v14 live site check\n\n" + table + "\n")

    failed_required = [i for i in results if i["check"].required and i["status"] != "Complete"]
    return 1 if failed_required else 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    sys.stdout.flush()
    # A stuck download thread must not keep the run alive after the report is written.
    os._exit(code)
