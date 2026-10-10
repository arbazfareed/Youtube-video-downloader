from __future__ import annotations

import queue
import os
import re
import sqlite3
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlsplit

from download_engine import DownloadCancelled, download_url
from history_store import DownloadHistory


MAX_SPEEDS = {
    "Unlimited": None,
    "256 KB/s": 256 * 1024,
    "512 KB/s": 512 * 1024,
    "1 MB/s": 1024 * 1024,
    "2 MB/s": 2 * 1024 * 1024,
    "5 MB/s": 5 * 1024 * 1024,
}


class DownloaderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Smart Downloader - ArbazFareed (AFJ devops)")
        self.root.minsize(1080, 620)
        self.root.geometry("1180x680")

        self.events: queue.Queue[tuple] = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.history = DownloadHistory()
        self.history.mark_unfinished_interrupted()
        self.history_records = self.history.list_records()
        self.cancel_events: dict[str, threading.Event] = {}
        self.pause_events: dict[str, threading.Event] = {}
        self.schedule_timers: dict[str, threading.Timer] = {}
        self.download_options: dict[str, dict] = {}
        self.destination = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.source = tk.StringVar(value="Auto")
        self.mode = tk.StringVar(value="Video")
        self.quality = tk.StringVar(value="1080p (Full HD)")
        self.playlist_scope = tk.StringVar(value="Auto (from link)")
        self.speed_mode = tk.StringVar(value="Fast")
        self.max_speed = tk.StringVar(value="Unlimited")
        self.scheduled_start = tk.StringVar(value="")
        self._download_paths: dict[str, Path] = {}

        self._build_ui()
        self._restore_history()
        self.root.after(100, self._process_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(10, weight=1)

        ttk.Label(
            frame,
            text=(
                "Public video links: YouTube, TikTok, Facebook, Instagram, Telegram embeds, "
                "and other yt-dlp-supported sites"
            ),
            justify="left",
            wraplength=1050,
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Link").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
        self.url_entry = ttk.Entry(frame)
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        self.url_entry.bind("<Return>", lambda _event: self.add_download())
        ttk.Button(frame, text="Add download", command=self.add_download).grid(
            row=1, column=3, padx=(8, 0), pady=5
        )

        ttk.Label(frame, text="Save to").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=5)
        ttk.Entry(frame, textvariable=self.destination).grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=5
        )
        ttk.Button(frame, text="Browse...", command=self._choose_folder).grid(
            row=2, column=3, padx=(8, 0), pady=5
        )

        options = ttk.Frame(frame)
        options.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 4))
        ttk.Label(options, text="Link type").pack(side="left")
        ttk.Combobox(
            options, textvariable=self.source, values=("Auto", "Direct file", "Supported site"),
            state="readonly", width=14,
        ).pack(side="left", padx=(6, 18))
        ttk.Label(options, text="Media").pack(side="left")
        ttk.Combobox(
            options, textvariable=self.mode, values=("Video", "Best audio", "MP3 audio"),
            state="readonly", width=12,
        ).pack(side="left", padx=(6, 18))
        ttk.Label(options, text="Max resolution").pack(side="left")
        ttk.Combobox(
            options, textvariable=self.quality,
            values=(
                "Best available", "8K (4320p)", "5K (2880p)", "4K (2160p)",
                "1440p (2K)", "1080p (Full HD)", "720p (HD)", "480p",
                "360p", "240p", "144p",
            ),
            state="readonly", width=19,
        ).pack(side="left", padx=6)

        playlist_options = ttk.Frame(frame)
        playlist_options.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(4, 8))
        ttk.Label(playlist_options, text="Download").pack(side="left")
        ttk.Combobox(
            playlist_options,
            textvariable=self.playlist_scope,
            values=("Auto (from link)", "Single video", "Entire playlist"),
            state="readonly",
            width=22,
        ).pack(side="left", padx=6)
        ttk.Label(
            playlist_options,
            text="Auto follows the link: video links download one video; playlist links download the list.",
        ).pack(side="left", padx=(8, 0))

        transfer_options = ttk.Frame(frame)
        transfer_options.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        ttk.Label(transfer_options, text="Download speed").pack(side="left")
        ttk.Combobox(
            transfer_options,
            textvariable=self.speed_mode,
            values=("Balanced", "Fast", "Maximum"),
            state="readonly",
            width=12,
        ).pack(side="left", padx=6)
        ttk.Label(transfer_options, text="Bandwidth cap").pack(side="left", padx=(14, 0))
        ttk.Combobox(
            transfer_options,
            textvariable=self.max_speed,
            values=tuple(MAX_SPEEDS),
            state="readonly",
            width=12,
        ).pack(side="left", padx=6)
        ttk.Label(
            transfer_options,
            text="Large range-capable files use parallel connections; cap is per download.",
        ).pack(side="left", padx=(8, 0))

        schedule_options = ttk.Frame(frame)
        schedule_options.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 4))
        ttk.Label(schedule_options, text="Start at (local time)").pack(side="left")
        ttk.Entry(
            schedule_options,
            textvariable=self.scheduled_start,
            width=20,
        ).pack(side="left", padx=6)
        ttk.Label(schedule_options, text="YYYY-MM-DD HH:MM; leave blank to start now").pack(
            side="left", padx=(4, 0)
        )

        ttk.Label(frame, text="Active download progress").grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(4, 0)
        )
        self.overall_progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.overall_progress.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(4, 8))
        self.progress_summary = tk.StringVar(value="No active downloads")
        ttk.Label(frame, textvariable=self.progress_summary).grid(
            row=9, column=0, columnspan=4, sticky="w", pady=(0, 6)
        )

        columns = ("status", "progress", "details", "location", "link")
        self.jobs = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        self.jobs.heading("status", text="Status")
        self.jobs.heading("progress", text="Progress")
        self.jobs.heading("details", text="Transfer details")
        self.jobs.heading("location", text="Saving to")
        self.jobs.heading("link", text="Link")
        self.jobs.column("status", width=150, stretch=False)
        self.jobs.column("progress", width=100, stretch=False)
        self.jobs.column("details", width=230, stretch=False)
        self.jobs.column("location", width=250, stretch=True)
        self.jobs.column("link", width=300, stretch=True)
        self.jobs.grid(row=10, column=0, columnspan=4, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.jobs.yview)
        scrollbar.grid(row=10, column=4, sticky="ns")
        self.jobs.configure(yscrollcommand=scrollbar.set)

        controls = ttk.Frame(frame)
        controls.grid(row=11, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Pause / resume selected", command=self.toggle_pause_selected).pack(
            side="left"
        )
        ttk.Button(controls, text="Cancel selected", command=self.cancel_selected).pack(side="left")
        ttk.Button(controls, text="Open downloads folder", command=self.open_download_folder).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(controls, text="Open selected location", command=self.open_selected_location).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(controls, text="Help", command=self.show_help).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text="Clear finished", command=self.clear_finished).pack(
            side="left", padx=(8, 0)
        )
        ttk.Label(
            controls,
            text="Public/direct links only. Sign-in, DRM, and protected streams are not supported.",
        ).pack(side="right")

        ttk.Separator(frame, orient="horizontal").grid(
            row=12, column=0, columnspan=4, sticky="ew", pady=(12, 6)
        )
        footer = ttk.Frame(frame)
        footer.grid(row=13, column=0, columnspan=4, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text="Smart Downloader").grid(row=0, column=0, sticky="w")
        ttk.Label(
            footer,
            text="Created by ArbazFareed (AFJ devops)",
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

        self.destination.trace_add("write", self._update_destination_labels)
        self._update_destination_labels()

    def _restore_history(self) -> None:
        for record in self.history_records:
            job_id = str(record.id)
            self._download_paths[job_id] = Path(record.destination)
            self.jobs.insert(
                "",
                "end",
                iid=job_id,
                values=(
                    record.status,
                    record.progress,
                    record.details,
                    record.destination,
                    record.url,
                ),
            )

    @staticmethod
    def _parse_scheduled_start(value: str) -> float | None:
        value = value.strip()
        if not value:
            return None
        try:
            scheduled = datetime.strptime(value, "%Y-%m-%d %H:%M").astimezone()
        except ValueError as error:
            raise ValueError("Schedule must use YYYY-MM-DD HH:MM in local time.") from error
        start_at = scheduled.timestamp()
        if start_at <= datetime.now().timestamp():
            raise ValueError("Scheduled start time must be in the future.")
        return start_at

    def _bandwidth_limit(self) -> int | None:
        try:
            return MAX_SPEEDS[self.max_speed.get()]
        except KeyError as error:
            raise ValueError(f"Unknown bandwidth cap: {self.max_speed.get()}") from error

    def _persist_job(
        self,
        job_id: str,
        status: str,
        progress: str,
        details: str,
    ) -> None:
        self.history.update(
            int(job_id),
            status,
            progress,
            details,
            str(self._download_paths[job_id]),
        )

    def clear_finished(self) -> int:
        finished_statuses = {"Complete", "Failed", "Cancelled", "Interrupted"}
        removed = 0
        for job_id in self.jobs.get_children():
            if self.jobs.set(job_id, "status") not in finished_statuses:
                continue
            self.jobs.delete(job_id)
            self.history.delete(int(job_id))
            self._download_paths.pop(job_id, None)
            self.cancel_events.pop(job_id, None)
            pause_event = self.pause_events.pop(job_id, None)
            if pause_event:
                pause_event.set()
            removed += 1

        if removed:
            self.progress_summary.set(f"Removed {removed} finished download(s) from the list")
        return removed

    def _update_destination_labels(self, *_args: object) -> None:
        for job_id in self.jobs.get_children():
            if job_id not in self._download_paths:
                self.jobs.set(job_id, "location", self.destination.get())

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.destination.get() or str(Path.home()))
        if selected:
            self.destination.set(selected)

    def add_download(self) -> None:
        url = self.url_entry.get().strip()
        destination = Path(self.destination.get()).expanduser()

        if urlsplit(url).scheme.lower() not in {"http", "https"} or not urlsplit(url).hostname:
            messagebox.showerror("Invalid link", "Enter a valid public HTTP or HTTPS link.")
            return
        if not self.destination.get().strip():
            messagebox.showerror("Choose a folder", "Select where downloaded files should be saved.")
            return

        try:
            start_at = self._parse_scheduled_start(self.scheduled_start.get())
            max_speed = self._bandwidth_limit()
            quality = self._quality_key()
        except ValueError as error:
            messagebox.showerror("Invalid download option", str(error))
            return

        status = "Scheduled" if start_at is not None else "Queued"
        try:
            job_id = str(self.history.add(url, status, str(destination)))
        except (OSError, sqlite3.Error) as error:
            messagebox.showerror("Could not save download history", str(error))
            return

        cancel_event = threading.Event()
        pause_event = threading.Event()
        pause_event.set()
        self.cancel_events[job_id] = cancel_event
        self.pause_events[job_id] = pause_event
        self._download_paths[job_id] = destination
        self.download_options[job_id] = {
            "url": url,
            "destination": destination,
            "source": self.source.get().lower(),
            "mode": self.mode.get().lower(),
            "quality": quality,
            "playlist_scope": self.playlist_scope.get().lower(),
            "speed_mode": self.speed_mode.get().lower(),
            "max_speed": max_speed,
        }
        details = (
            datetime.fromtimestamp(start_at).astimezone().strftime("Starts %Y-%m-%d %H:%M")
            if start_at is not None
            else "Waiting"
        )
        self.jobs.insert(
            "",
            0,
            iid=job_id,
            values=(status, "—", details, str(destination), url),
        )
        self._persist_job(job_id, status, "—", details)
        self.url_entry.delete(0, "end")
        if start_at is None:
            self.overall_progress.configure(mode="indeterminate", value=0)
            self.overall_progress.start(12)
            self.progress_summary.set("Queued - " + str(destination))
            self._submit_download(job_id)
        else:
            timer = threading.Timer(
                max(0.0, start_at - datetime.now().timestamp()),
                lambda: self.events.put(("start", job_id)),
            )
            timer.daemon = True
            self.schedule_timers[job_id] = timer
            timer.start()
            self.progress_summary.set(f"{details} - {destination}")

    def _submit_download(self, job_id: str) -> None:
        options = self.download_options.get(job_id)
        cancel_event = self.cancel_events.get(job_id)
        pause_event = self.pause_events.get(job_id)
        if options is None or cancel_event is None or pause_event is None or cancel_event.is_set():
            return
        future = self.executor.submit(
            download_url,
            options["url"],
            options["destination"],
            options["source"],
            options["mode"],
            options["quality"],
            options["playlist_scope"],
            cancel_event,
            lambda status, percent, details: self.events.put(
                ("progress", job_id, status, percent, details)
            ),
            options["speed_mode"],
            pause_event,
            options["max_speed"],
        )
        future.add_done_callback(lambda result: self._job_finished(job_id, result))

    def toggle_pause_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            return
        job_id = selected[0]
        pause_event = self.pause_events.get(job_id)
        if pause_event is None or self.cancel_events.get(job_id, threading.Event()).is_set():
            return
        if pause_event.is_set():
            pause_event.clear()
            self.jobs.set(job_id, "status", "Paused")
            self.progress_summary.set("Paused - partial data is retained for resume")
            self.overall_progress.stop()
        else:
            pause_event.set()
            self.jobs.set(job_id, "status", "Resuming")
            self.progress_summary.set("Resuming download...")

    def _quality_key(self) -> str:
        label = self.quality.get().lower()
        if label.startswith("best"):
            return "best"
        match = re.search(r"(\d{3,4}p)", label)
        if not match:
            raise ValueError(f"Unknown resolution option: {self.quality.get()}")
        return match.group(1)

    def open_download_folder(self) -> None:
        folder = Path(self.destination.get()).expanduser()
        self._open_path(folder)

    def open_selected_location(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            messagebox.showinfo("Select a download", "Select a download row first.")
            return

        job_id = selected[0]
        saved_path = self.jobs.set(job_id, "details")
        path = Path(saved_path)
        if (
            not saved_path
            or saved_path in {"Waiting", "Preparing", "Processing media"}
            or not path.exists()
        ):
            path = self._download_paths.get(job_id, Path(self.destination.get()))
        self._open_path(path)

    def _open_path(self, path: Path) -> None:
        try:
            path = path.expanduser().resolve()
            folder = path if path.is_dir() else path.parent
            folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                if path.is_file():
                    subprocess.Popen(["explorer.exe", f"/select,{path}"])
                else:
                    os.startfile(folder)
            elif sys.platform == "darwin":
                if path.is_file():
                    subprocess.Popen(["open", "-R", str(path)])
                else:
                    subprocess.Popen(["open", str(folder)])
            else:
                opener = shutil.which("xdg-open")
                if not opener:
                    raise OSError("Could not find a desktop folder opener (xdg-open).")
                subprocess.Popen([opener, str(folder)])
        except OSError as error:
            messagebox.showerror("Could not open location", str(error))

    def show_help(self) -> None:
        messagebox.showinfo(
            "Smart Downloader help",
            "Paste a public link, choose where to save it, select options, and click Add download.\n\n"
            "Link type: Auto detects common direct file links; Supported site sends the URL to yt-dlp.\n"
            "Site support: YouTube, TikTok, Facebook, Instagram, and other yt-dlp extractors. "
            "Telegram support is limited to public post video embeds recognized by yt-dlp. "
            "A platform name does not guarantee every URL works; sites may change their formats.\n"
            "Media: Video, Best audio (keeps the source audio format), or MP3 audio. MP3 conversion "
            "and merging separate video/audio streams need FFmpeg.\n"
            "Max resolution: The highest allowed height, not a promise that the source provides it. "
            "Best available uses the best format the source offers.\n"
            "Download: Auto downloads a single video link or the playlist when the link contains one. "
            "Single video ignores playlist items when the source link permits it. Entire playlist "
            "downloads the list when the link is a playlist.\n"
            "Download speed: Balanced, Fast, or Maximum controls parallel media fragments; the source "
            "and your connection determine the actual speed. Large direct files also use parallel "
            "HTTP ranges when supported. Set a bandwidth cap per download if "
            "needed. Use Pause / resume selected to hold or continue a queued or active job. Direct "
            "downloads keep partial data and retry temporary connection failures automatically. "
            "Set Start at to YYYY-MM-DD HH:MM local time to schedule a job, or leave blank to start "
            "immediately. Scheduled jobs need the app to remain open. Download history is saved "
            "between launches. Clear finished removes terminal rows from the list without deleting "
            "any downloaded files.\n"
            "Only public content you have permission to save is supported. Sign-in-only, DRM, "
            "private chats/channels, and protected streams are not supported.",
        )

    def _job_finished(self, job_id: str, future: Future[str]) -> None:
        try:
            result = future.result()
        except DownloadCancelled:
            self.events.put(("finished", job_id, "Cancelled", ""))
        except Exception as error:
            self.events.put(("finished", job_id, "Failed", str(error)))
        else:
            self.events.put(("finished", job_id, "Complete", result))

    def cancel_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            return
        job_id = selected[0]
        cancel_event = self.cancel_events.get(job_id)
        if cancel_event:
            cancel_event.set()
            pause_event = self.pause_events.get(job_id)
            if pause_event:
                pause_event.set()
            timer = self.schedule_timers.pop(job_id, None)
            if timer:
                timer.cancel()
                self.events.put(("finished", job_id, "Cancelled", "Scheduled download cancelled"))
            self.jobs.set(job_id, "status", "Cancelling…")

    def _process_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            if event[0] == "start":
                _, job_id = event
                self.schedule_timers.pop(job_id, None)
                cancel_event = self.cancel_events.get(job_id)
                if (
                    self.jobs.exists(job_id)
                    and cancel_event is not None
                    and not cancel_event.is_set()
                ):
                    self.jobs.set(job_id, "status", "Queued")
                    self.jobs.set(job_id, "details", "Waiting")
                    self._persist_job(job_id, "Queued", "—", "Waiting")
                    self._submit_download(job_id)
                    self.progress_summary.set(
                        f"Scheduled download started - {self._download_paths[job_id]}"
                    )
            elif event[0] == "progress":
                _, job_id, status, percent, details = event
                if self.jobs.exists(job_id):
                    if percent is None:
                        self.overall_progress.stop()
                        self.overall_progress.configure(mode="indeterminate", value=0)
                        self.overall_progress.start(12)
                        progress_text = "Working"
                    else:
                        self.overall_progress.stop()
                        self.overall_progress.configure(mode="determinate", value=percent)
                        progress_text = f"{percent:.1f}%"

                    self.jobs.set(job_id, "status", status)
                    self.jobs.set(job_id, "progress", progress_text)
                    self.jobs.set(job_id, "details", details)
                    self.jobs.set(job_id, "location", str(self._download_paths[job_id]))
                    self._persist_job(job_id, status, progress_text, details)
                    self.progress_summary.set(
                        f"{status}: {progress_text}"
                        + (f" - {details}" if details else "")
                        + f" | Saving to {self._download_paths[job_id]}"
                    )
            else:
                _, job_id, status, detail = event
                if self.jobs.exists(job_id):
                    self.jobs.set(job_id, "status", status)
                    if status == "Complete":
                        self.jobs.set(job_id, "progress", "100%")
                        self.jobs.set(job_id, "details", detail)
                        result_path = Path(detail)
                        if result_path.is_absolute():
                            self._download_paths[job_id] = result_path
                            result_folder = result_path if result_path.is_dir() else result_path.parent
                            self.jobs.set(job_id, "location", str(result_folder))
                        self.overall_progress.stop()
                        self.overall_progress.configure(mode="determinate", value=100)
                        self.progress_summary.set(f"Complete - {detail}")
                    elif status in {"Failed", "Cancelled"}:
                        self.overall_progress.stop()
                        self.overall_progress.configure(mode="determinate", value=0)
                        self.progress_summary.set(
                            f"{status} - {detail or self.jobs.set(job_id, 'link')}"
                        )
                        if status == "Failed" and detail:
                            messagebox.showerror("Download failed", detail)
                    else:
                        self.progress_summary.set(f"{status} - {detail}")
                    self._persist_job(
                        job_id,
                        status,
                        self.jobs.set(job_id, "progress"),
                        detail,
                    )
                self.cancel_events.pop(job_id, None)
                pause_event = self.pause_events.pop(job_id, None)
                if pause_event:
                    pause_event.set()
                self.schedule_timers.pop(job_id, None)
                self.download_options.pop(job_id, None)

        self.root.after(100, self._process_events)

    def _close(self) -> None:
        for timer in self.schedule_timers.values():
            timer.cancel()
        for cancel_event in self.cancel_events.values():
            cancel_event.set()
        for pause_event in self.pause_events.values():
            pause_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
