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


MAX_SPEEDS = {
    "Unlimited": None,
    "256 KB/s": 256 * 1024,
    "512 KB/s": 512 * 1024,
    "1 MB/s": 1024 * 1024,
    "2 MB/s": 2 * 1024 * 1024,
    "5 MB/s": 5 * 1024 * 1024,
}
FINISHED_STATUSES = {"Complete", "Failed", "Cancelled", "Interrupted"}
MEDIA_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".gif", ".jpeg", ".jpg", ".m4a", ".mkv",
    ".mov", ".mp3", ".mp4", ".mpeg", ".mpg", ".ogg", ".png", ".wav",
    ".webm", ".webp", ".wmv",
}
PLAYABLE_MEDIA_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".ogg", ".wav", ".webm", ".wmv",
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


class DownloaderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Smart Downloader")
        self.root.minsize(1080, 620)
        window_height = min(700, max(620, self.root.winfo_screenheight() - 80))
        self.root.geometry(f"1280x{window_height}")

        self.events: queue.Queue[tuple] = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.history = DownloadHistory()
        load_plugins()
        self.history.mark_unfinished_interrupted()
        self.history_records = self.history.list_records()
        self.cancel_events: dict[str, threading.Event] = {}
        self.resume_events: dict[str, threading.Event] = {}
        self.schedule_timers: dict[str, threading.Timer] = {}
        self.download_options: dict[str, dict] = {}
        self.bandwidth_limiter = GlobalBandwidthLimiter()
        self.verified_checksums: dict[str, tuple[str, str]] = {}
        self.destination = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.destination_label = tk.StringVar(value="Save to")
        self.cloud_provider = tk.StringVar(
            value=self.history.get_setting("cloud_provider", "Local folder")
        )
        self.cloud_folder = tk.StringVar(
            value=self.history.get_setting("cloud_folder", "")
        )
        self.source = tk.StringVar(value="Auto")
        self.mode = tk.StringVar(value="Video")
        self.quality = tk.StringVar(value="1080p (Full HD)")
        self.playlist_scope = tk.StringVar(value="Auto (from link)")
        self.speed_mode = tk.StringVar(value="Fast")
        self.max_speed = tk.StringVar(value="Unlimited")
        self.global_max_speed = tk.StringVar(value="Unlimited")
        self.expected_checksum = tk.StringVar(value="")
        self.checksum_algorithm = tk.StringVar(value="SHA256")
        self.proxy_list = tk.StringVar(value="")
        self.browser_cookies = tk.StringVar(value="None")
        self.auto_extract = tk.BooleanVar(
            value=self.history.get_setting("auto_extract", "0") == "1"
        )
        self.dark_mode = tk.BooleanVar(
            value=self.history.get_setting("dark_mode", "0") == "1"
        )
        self.warn_on_duplicates = tk.BooleanVar(
            value=self.history.get_setting("warn_on_duplicates", "1") == "1"
        )
        self.clipboard_autofill = tk.BooleanVar(
            value=self.history.get_setting("clipboard_autofill", "0") == "1"
        )
        self._last_clipboard = ""
        self._last_autofilled_clipboard = ""
        self.show_hidden = tk.BooleanVar(value=False)
        self.scheduled_start = tk.StringVar(value="")
        self._download_paths: dict[str, Path] = {}
        self._job_destinations: dict[str, str] = {}
        self._speed_state: dict[str, tuple[float, float]] = {}
        self._speed_history: dict[str, list[float]] = {}
        self._active_graph_job: str | None = None
        self._last_graph_draw = 0.0
        self._queue_filter = "all"
        self._queue_job_ids: list[str] = []
        self._resume_errors: dict[str, str] = {}

        self._build_ui()
        self._apply_theme()
        self._restore_history()
        self.global_max_speed.trace_add("write", self._update_global_bandwidth)
        self.root.after(100, self._process_events)
        self.root.after(800, self._watch_clipboard)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(outer, style="Sidebar.TFrame", padding=(10, 14))
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(
            sidebar, text="SMART\nDOWNLOADER", style="SidebarTitle.TLabel",
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(2, 20))
        self.navigation_buttons: dict[str, ttk.Button] = {}
        navigation_items = (
            ("all", "All tasks"),
            ("downloading", "Downloading"),
            ("completed", "Completed"),
            ("media", "Media library"),
        )
        for row, (filter_name, label) in enumerate(navigation_items, start=1):
            button = ttk.Button(
                sidebar, text=label, style="Navigation.TButton",
                command=lambda value=filter_name: self._set_queue_filter(value),
            )
            button.grid(row=row, column=0, sticky="ew", pady=2)
            self.navigation_buttons[filter_name] = button
        ttk.Separator(sidebar).grid(row=5, column=0, sticky="ew", pady=12)
        ttk.Button(
            sidebar, text="Settings", style="Navigation.TButton",
            command=self.open_download_settings,
        ).grid(row=6, column=0, sticky="ew", pady=2)
        tools_button = ttk.Menubutton(
            sidebar, text="Tools & utilities", style="Navigation.TMenubutton",
        )
        self.tools_menu = tk.Menu(tools_button, tearoff=False)
        self.tools_menu.add_command(
            label="Resume / retry selected", command=self.resume_selected,
        )
        self.tools_menu.add_command(
            label="Play selected audio/video", command=self.play_selected_media,
        )
        self.tools_menu.add_command(
            label="Open selected file or folder", command=self.open_selected_location,
        )
        self.tools_menu.add_command(
            label="Extract selected archive", command=self.extract_selected_archive,
        )
        self.tools_menu.add_command(
            label="Image tools for selected image",
            command=self.open_selected_image_tools,
        )
        self.tools_menu.add_separator()
        self.tools_menu.add_command(
            label="Add several links", command=self.open_batch_dialog,
        )
        self.tools_menu.add_command(
            label="Download an image sequence", command=self.open_sequence_dialog,
        )
        self.tools_menu.add_command(
            label="Find images on a page",
            command=lambda: self._select_image_gallery_mode(),
        )
        self.tools_menu.add_command(
            label="Convert local media to MP3", command=self.convert_local_file_to_mp3,
        )
        self.tools_menu.add_command(
            label="Convert DOCX to PDF", command=self.convert_docx_file_to_pdf,
        )
        self.tools_menu.add_command(
            label="Convert PDF to DOCX", command=self.convert_pdf_file_to_docx,
        )
        tools_button.configure(menu=self.tools_menu)
        tools_button.grid(row=7, column=0, sticky="ew", pady=2)
        ttk.Button(
            sidebar, text="Convert to MP3", style="Navigation.TButton",
            command=self.convert_local_file_to_mp3,
        ).grid(row=8, column=0, sticky="ew", pady=2)
        ttk.Label(
            sidebar, text="Download and organize\nlocal media", style="SidebarHint.TLabel",
            justify="left",
        ).grid(row=9, column=0, sticky="sw", padx=8, pady=(24, 0))

        frame = ttk.Frame(outer, padding=16)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        header = ttk.Frame(frame, style="Card.TFrame", padding=(16, 12))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Smart Downloader", style="Card.TLabel",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header, text="Paste a link, choose where to save it, and add it to your queue.",
            style="Card.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(
            header, text="Use recommended", command=self._use_recommended_settings,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Checkbutton(
            header, text="Auto-fill copied links", variable=self.clipboard_autofill,
            command=self._save_clipboard_preference,
        ).grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(4, 0))
        ttk.Checkbutton(
            header, text="Dark mode", variable=self.dark_mode,
            command=self._save_theme_preference,
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(16, 0))

        add_card = ttk.Frame(frame, style="Card.TFrame", padding=12)
        add_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        add_card.columnconfigure(1, weight=1)
        ttk.Label(add_card, text="Link", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.url_entry = ttk.Entry(add_card)
        self.url_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        self.url_entry.bind("<Return>", lambda _event: self.add_download())
        add_buttons = ttk.Frame(add_card, style="Card.TFrame")
        add_buttons.grid(row=0, column=2, sticky="e", padx=(10, 0), pady=(0, 8))
        ttk.Button(
            add_buttons, text="Add download", command=self.add_download,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            add_buttons, text="Batch", command=self.open_batch_dialog,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            add_buttons, text="Sequence", command=self.open_sequence_dialog,
        ).pack(side="left", padx=(6, 0))
        ttk.Label(add_card, textvariable=self.destination_label, style="Card.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10)
        )
        self.destination_entry = ttk.Entry(add_card, textvariable=self.destination)
        self.destination_entry.grid(row=1, column=1, sticky="ew")
        self.destination_browse_button = ttk.Button(
            add_card, text="Browse", command=self._choose_folder,
        )
        self.destination_browse_button.grid(row=1, column=2, padx=(10, 0))
        self._build_remaining_ui(frame)

        footer = ttk.Frame(outer, padding=(16, 4))
        footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Separator(footer, orient="horizontal").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4),
        )
        ttk.Label(footer, text="Smart Downloader").grid(row=1, column=0, sticky="w")
        ttk.Label(
            footer, text="Created by Arbaz Fareed · AFJ DEVOPS", anchor="e",
        ).grid(row=1, column=1, sticky="e")
        self.footer = footer
        self.destination.trace_add("write", self._update_destination_labels)
        self._update_destination_labels()

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Download settings")
        self.settings_window.geometry("700x500")
        self.settings_window.minsize(620, 440)
        self.settings_window.transient(self.root)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
        self.settings_window.bind("<Escape>", lambda _event: self.settings_window.withdraw())
        self._build_settings_ui()
        self.settings_window.withdraw()
        self._set_queue_filter("all")

    def open_download_settings(self) -> None:
        self.settings_window.deiconify()
        self.settings_window.lift()
        self.settings_window.focus_set()

    def convert_local_file_to_mp3(self) -> None:
        source_name = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a local audio or video file",
            filetypes=(
                ("Media files", "*.aac *.avi *.flac *.m4a *.mkv *.mov *.mp3 *.mp4 *.mpeg *.mpg *.ogg *.wav *.webm *.wmv"),
                ("All files", "*.*"),
            ),
        )
        if not source_name:
            return
        ffmpeg_directory = _ffmpeg_directory()
        if ffmpeg_directory is None:
            messagebox.showerror(
                "FFmpeg is required",
                "Install FFmpeg to convert local files to MP3, then restart Smart Downloader.",
                parent=self.root,
            )
            return
        source = Path(source_name)
        initial_name = f"{source.stem}_converted.mp3" if source.suffix.lower() == ".mp3" else f"{source.stem}.mp3"
        destination_name = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save MP3 file",
            initialdir=str(source.parent),
            initialfile=initial_name,
            defaultextension=".mp3",
            filetypes=(("MP3 audio", "*.mp3"),),
        )
        if not destination_name:
            return
        destination = Path(destination_name)
        if destination.suffix.lower() != ".mp3":
            messagebox.showerror(
                "Choose an MP3 filename",
                "The output filename must end in .mp3.",
                parent=self.root,
            )
            return
        if source.resolve() == destination.resolve():
            messagebox.showerror(
                "Choose a different output file",
                "The converted MP3 must not overwrite the source file.",
                parent=self.root,
            )
            return

        self.progress_summary.set(f"Converting local file to MP3: {source.name}")
        future = self.executor.submit(
            _convert_media_to_mp3, source, destination, ffmpeg_directory,
        )

        def conversion_finished(completed: Future[None]) -> None:
            try:
                completed.result()
            except Exception as error:
                self.events.put(("conversion_failed", str(error)))
            else:
                self.events.put(("conversion_complete", str(destination)))

        future.add_done_callback(conversion_finished)

    def convert_docx_file_to_pdf(self) -> None:
        self._convert_document_file(
            ".docx", ".pdf", convert_docx_to_pdf, "Convert DOCX to PDF"
        )

    def convert_pdf_file_to_docx(self) -> None:
        self._convert_document_file(
            ".pdf", ".docx", convert_pdf_to_docx, "Convert PDF to DOCX"
        )

    def _convert_document_file(
        self,
        source_extension: str,
        output_extension: str,
        converter: Callable[..., Path],
        title: str,
    ) -> None:
        source_name = filedialog.askopenfilename(
            parent=self.root,
            title=f"Choose a {source_extension[1:].upper()} file",
            filetypes=(
                (f"{source_extension[1:].upper()} files", f"*{source_extension}"),
                ("All files", "*.*"),
            ),
        )
        if not source_name:
            return
        source = Path(source_name)
        output_name = filedialog.asksaveasfilename(
            parent=self.root,
            title=f"Save converted {output_extension[1:].upper()} file",
            initialdir=str(source.parent),
            initialfile=f"{source.stem}{output_extension}",
            defaultextension=output_extension,
            filetypes=(
                (f"{output_extension[1:].upper()} files", f"*{output_extension}"),
            ),
            confirmoverwrite=True,
        )
        if not output_name:
            return
        output = Path(output_name)
        if output.suffix.lower() != output_extension:
            messagebox.showerror(
                "Choose the correct output format",
                f"The output filename must end in {output_extension}.",
                parent=self.root,
            )
            return
        self._process_document(
            lambda: converter(source, output, overwrite=True),
            title,
        )

    def _process_document(self, operation, description: str) -> None:
        future = self.executor.submit(operation)

        def check_result() -> None:
            if not future.done():
                self.root.after(100, check_result)
                return
            try:
                result = future.result()
            except Exception as error:
                messagebox.showerror(f"{description} failed", str(error), parent=self.root)
                return
            messagebox.showinfo(description, f"Saved converted file:\n{result}", parent=self.root)

        self.root.after(100, check_result)

    def _save_clipboard_preference(self) -> None:
        self.history.set_setting(
            "clipboard_autofill",
            "1" if self.clipboard_autofill.get() else "0",
        )

    def _save_extract_preference(self) -> None:
        self.history.set_setting("auto_extract", "1" if self.auto_extract.get() else "0")

    def _save_cloud_preferences(self, *_args: object) -> None:
        self.history.set_setting("cloud_provider", self.cloud_provider.get())
        self.history.set_setting("cloud_folder", self.cloud_folder.get())
        self._update_destination_mode()

    def _update_destination_mode(self) -> None:
        is_cloud = self.cloud_provider.get() != "Local folder"
        self.destination_label.set(
            "Temporary local staging" if is_cloud else "Save to"
        )
        self.destination_entry.configure(state="disabled" if is_cloud else "normal")
        self.destination_browse_button.configure(state="disabled" if is_cloud else "normal")

    def _configure_cloud_account(self) -> None:
        provider = self.cloud_provider.get()
        try:
            if provider == "Amazon S3":
                access_key = simpledialog.askstring(
                    "Amazon S3 setup", "Access key ID:", parent=self.root
                )
                if not access_key:
                    return
                secret_key = simpledialog.askstring(
                    "Amazon S3 setup", "Secret access key:", show="*", parent=self.root
                )
                if not secret_key:
                    return
                bucket = simpledialog.askstring(
                    "Amazon S3 setup", "Bucket name:", parent=self.root
                )
                if not bucket:
                    return
                region = simpledialog.askstring(
                    "Amazon S3 setup", "Region (for example, us-east-1):", parent=self.root
                )
                if not region:
                    return
                save_credentials(provider, {
                    "access_key": access_key,
                    "secret_key": secret_key,
                    "bucket": bucket,
                    "region": region,
                })
            elif provider == "Google Drive":
                config_file = filedialog.askopenfilename(
                    parent=self.root,
                    title="Choose Google OAuth client JSON",
                    filetypes=(("JSON files", "*.json"),),
                )
                if not config_file:
                    return
                config_text = Path(config_file).read_text(encoding="utf-8")
                config_value = json.loads(config_text)
                if not isinstance(config_value, dict) or not (
                    "installed" in config_value or "web" in config_value
                ):
                    raise ValueError("Choose a Google OAuth client configuration JSON file.")
                save_credentials(provider, {"client_config": config_text})
            elif provider == "Dropbox":
                app_key = simpledialog.askstring(
                    "Dropbox setup", "Dropbox app key:", parent=self.root
                )
                if not app_key:
                    return
                app_secret = simpledialog.askstring(
                    "Dropbox setup", "Dropbox app secret:", show="*", parent=self.root
                )
                if not app_secret:
                    return
                import dropbox

                flow = dropbox.DropboxOAuth2FlowNoRedirect(
                    app_key,
                    consumer_secret=app_secret,
                    token_access_type="offline",
                )
                authorization_url = flow.start()
                if not webbrowser.open(authorization_url):
                    messagebox.showinfo(
                        "Dropbox sign-in",
                        f"Open this address in your browser:\n{authorization_url}",
                        parent=self.root,
                    )
                auth_code = simpledialog.askstring(
                    "Dropbox sign-in",
                    "Sign in in your browser, then paste the authorization code:",
                    parent=self.root,
                )
                if not auth_code:
                    return
                try:
                    result = flow.finish(auth_code.strip())
                except dropbox.exceptions.DropboxException as error:
                    raise RuntimeError(f"Dropbox sign-in failed: {error}") from error
                if not result.refresh_token:
                    raise RuntimeError(
                        "Dropbox did not return a refresh token. Check the app's offline access settings."
                    )
                save_credentials(provider, {
                    "access_token": result.access_token,
                    "refresh_token": result.refresh_token,
                    "app_key": app_key,
                    "app_secret": app_secret,
                })
            else:
                messagebox.showinfo(
                    "Cloud setup",
                    "Choose Amazon S3, Google Drive, or Dropbox first.",
                    parent=self.root,
                )
                return
        except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as error:
            messagebox.showerror("Cloud account setup failed", str(error), parent=self.root)
            return
        messagebox.showinfo(
            "Cloud account saved",
            f"{provider} credentials were saved in the operating system credential store.",
            parent=self.root,
        )

    def _watch_clipboard(self) -> None:
        if self.clipboard_autofill.get():
            try:
                clipboard = self.root.clipboard_get().strip()
            except tk.TclError:
                clipboard = ""
            if clipboard != self._last_clipboard:
                self._last_clipboard = clipboard
                try:
                    parsed = urlsplit(clipboard)
                except ValueError:
                    parsed = None
                if (
                    parsed is not None
                    and parsed.scheme.lower() in {"http", "https"}
                    and parsed.hostname
                    and self.url_entry.get().strip()
                    in {"", self._last_autofilled_clipboard}
                ):
                    self.url_entry.delete(0, "end")
                    self.url_entry.insert(0, clipboard)
                    self._last_autofilled_clipboard = clipboard
        self.root.after(800, self._watch_clipboard)

    def open_batch_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Add several links")
        dialog.transient(self.root)
        dialog.geometry("680x440")
        dialog.minsize(500, 320)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(
            dialog,
            text=(
                "Paste one public link per line. Blank lines are ignored. "
                "Checksum verification is not applied to batch links."
            ),
            padding=(12, 10),
        ).grid(row=0, column=0, sticky="w")
        links = tk.Text(dialog, wrap="none", undo=True)
        links.grid(row=1, column=0, sticky="nsew", padx=12)
        actions = ttk.Frame(dialog, padding=12)
        actions.grid(row=2, column=0, sticky="ew")

        def load_file() -> None:
            path = filedialog.askopenfilename(
                parent=dialog,
                title="Load links from a text file",
                filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
            )
            if not path:
                return
            try:
                content = Path(path).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as error:
                messagebox.showerror("Could not read link file", str(error), parent=dialog)
                return
            links.delete("1.0", "end")
            links.insert("1.0", content)

        def paste_clipboard() -> None:
            try:
                content = self.root.clipboard_get()
            except tk.TclError as error:
                messagebox.showwarning(
                    "Clipboard unavailable",
                    f"Could not read the clipboard: {error}",
                    parent=dialog,
                )
                return
            links.delete("1.0", "end")
            links.insert("1.0", content)

        def add_all() -> None:
            candidates = [
                line.strip()
                for line in links.get("1.0", "end-1c").splitlines()
                if line.strip()
            ]
            accepted, valid_count = self._add_batch_urls(candidates)
            if accepted:
                self.progress_summary.set(f"Added {accepted} link(s) to the download list.")
                dialog.destroy()
            else:
                messagebox.showinfo(
                    "No links added",
                    f"No links were added from {valid_count} valid link(s). "
                    "Check for duplicate warnings or invalid download options.",
                    parent=dialog,
                )

        ttk.Button(actions, text="Load from .txt file", command=load_file).pack(side="left")
        ttk.Button(actions, text="Paste from clipboard", command=paste_clipboard).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(actions, text="Add all", command=add_all, style="Accent.TButton").pack(
            side="right"
        )
        ttk.Button(actions, text="Close", command=dialog.destroy).pack(
            side="right", padx=(0, 6)
        )
        links.focus_set()
        dialog.grab_set()

    def _add_batch_urls(self, candidates: list[str]) -> tuple[int, int]:
        previous_value = self.url_entry.get()
        previous_checksum = self.expected_checksum.get()
        self.expected_checksum.set("")
        accepted = 0
        valid_count = 0
        try:
            for url in candidates:
                try:
                    parsed = urlsplit(url)
                except ValueError:
                    continue
                if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                    continue
                valid_count += 1
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, url)
                before = len(self.jobs.get_children())
                self.add_download()
                if len(self.jobs.get_children()) > before:
                    accepted += 1
        finally:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, previous_value)
            self.expected_checksum.set(previous_checksum)
        return accepted, valid_count

    def _build_remaining_ui(self, frame: ttk.Frame) -> None:
        options = ttk.Frame(frame, style="Card.TFrame", padding=(12, 10))
        options.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for column in range(4):
            options.columnconfigure(column, weight=1)
        quick_options = (
            ("Source", self.source, ("Auto", "Direct file", "Supported site")),
            ("Media", self.mode, ("Video", "Best audio", "MP3 audio", "Image gallery")),
            ("Resolution", self.quality, (
                "Best available", "8K (4320p)", "5K (2880p)", "4K (2160p)",
                "1440p (2K)", "1080p (Full HD)", "720p (HD)", "480p",
                "360p", "240p", "144p",
            )),
            ("Playlist", self.playlist_scope, (
                "Auto (from link)", "Single video", "Entire playlist",
            )),
        )
        for column, (label, variable, values) in enumerate(quick_options):
            ttk.Label(options, text=label, style="Card.TLabel").grid(
                row=0, column=column, sticky="w", padx=(0, 12)
            )
            ttk.Combobox(
                options, textvariable=variable, values=values,
                state="readonly", width=18,
            ).grid(row=1, column=column, sticky="ew", padx=(0, 12))
        ttk.Button(
            options, text="More settings", command=self.open_download_settings,
        ).grid(row=0, column=4, rowspan=2, sticky="e", padx=(8, 0))

        progress_card = ttk.Frame(frame, style="Card.TFrame", padding=(12, 9))
        progress_card.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        progress_card.columnconfigure(0, weight=1)
        progress_header = ttk.Frame(progress_card, style="Card.TFrame")
        progress_header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            progress_header, text="Overall progress", style="Card.TLabel",
        ).pack(side="left")
        self.progress_summary = tk.StringVar(value="No active downloads")
        ttk.Label(
            progress_header, textvariable=self.progress_summary, style="Card.TLabel",
        ).pack(side="right")
        self.overall_progress = ttk.Progressbar(
            progress_card, mode="determinate", maximum=100,
        )
        self.overall_progress.grid(row=1, column=0, sticky="ew", pady=(8, 5))
        self.speed_graph = tk.Canvas(
            progress_card, height=50, background="#f4f6f8", highlightthickness=0,
        )
        self.speed_graph.grid(row=2, column=0, sticky="ew")
        self.speed_graph.bind("<Configure>", lambda _event: self._draw_speed_graph())

        queue_header = ttk.Frame(frame)
        queue_header.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        queue_header.columnconfigure(0, weight=1)
        self.queue_title_label = ttk.Label(
            queue_header, text="All tasks", font=("Segoe UI", 12, "bold"),
        )
        self.queue_title_label.grid(
            row=0, column=0, sticky="w"
        )
        self.queue_hint_label = ttk.Label(
            queue_header, text="Right-click an image download for image tools.",
        )
        self.queue_hint_label.grid(row=0, column=1, sticky="e")

        queue_frame = ttk.Frame(frame)
        queue_frame.grid(row=5, column=0, sticky="nsew")
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)
        columns = ("status", "progress", "details", "location", "link")
        self.jobs = ttk.Treeview(
            queue_frame, columns=columns, show="headings", selectmode="browse",
        )
        self.jobs.heading("status", text="Status")
        self.jobs.heading("progress", text="Progress")
        self.jobs.heading("details", text="Transfer details")
        self.jobs.heading("location", text="Saving to")
        self.jobs.heading("link", text="Link")
        self.jobs.column("status", width=105, stretch=False)
        self.jobs.column("progress", width=85, stretch=False)
        self.jobs.column("details", width=155, stretch=False)
        self.jobs.column("location", width=230, stretch=True)
        self.jobs.column("link", width=260, stretch=True)
        self.jobs.tag_configure("hidden", foreground="#888888")
        self.jobs.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(queue_frame, orient="vertical", command=self.jobs.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar = ttk.Scrollbar(
            queue_frame, orient="horizontal", command=self.jobs.xview,
        )
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.jobs.configure(
            yscrollcommand=scrollbar.set, xscrollcommand=horizontal_scrollbar.set,
        )
        self.jobs.bind("<Button-3>", self._show_image_context_menu)
        self.jobs.bind("<Double-1>", self._open_clicked_row_action)
        self.jobs.bind("<<TreeviewSelect>>", self._show_selected_thumbnail)

        preview = ttk.Labelframe(queue_frame, text="Image preview", padding=8)
        preview.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        preview.columnconfigure(0, weight=1)
        queue_frame.columnconfigure(2, minsize=190)
        self.preview_image_label = ttk.Label(preview, text="Select a downloaded image")
        self.preview_image_label.grid(row=0, column=0, sticky="nsew")
        self.preview_details = ttk.Label(preview, text="", wraplength=190)
        self.preview_details.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.current_thumbnail = None

        controls = ttk.Frame(frame)
        controls.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(
            controls, text="Pause / resume", command=self.toggle_pause_selected,
        ).pack(side="left")
        ttk.Button(
            controls, text="Resume / retry", command=self.resume_selected,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls, text="Cancel selected", command=self.cancel_selected,
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            controls, text="Open selected location", command=self.open_selected_location,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            controls, text="Open downloads folder", command=self.open_download_folder,
        ).pack(side="left", padx=(6, 0))
        more_button = ttk.Menubutton(controls, text="History")
        more_menu = tk.Menu(more_button, tearoff=False)
        self.history_menu = more_menu
        more_menu.add_command(label="Hide selected", command=self.hide_selected)
        more_menu.add_command(label="Restore selected", command=self.restore_selected)
        more_menu.add_command(label="Clear finished", command=self.clear_finished)
        more_menu.add_checkbutton(
            label="Show hidden", variable=self.show_hidden, command=self._refresh_history,
        )
        more_menu.add_separator()
        more_menu.add_command(label="Help", command=self.show_help)
        more_button.configure(menu=more_menu)
        more_button.pack(side="left", padx=(6, 0))
    def _build_settings_ui(self) -> None:
        container = ttk.Frame(self.settings_window, padding=14)
        container.pack(fill="both", expand=True)
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        transfer = ttk.Frame(notebook, padding=16)
        transfer.columnconfigure(1, weight=1)
        notebook.add(transfer, text="Speed & checks")
        ttk.Label(transfer, text="Download speed").grid(row=0, column=0, sticky="w", pady=7)
        ttk.Combobox(
            transfer, textvariable=self.speed_mode,
            values=("Balanced", "Fast", "Maximum"), state="readonly", width=18,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=7)
        ttk.Label(transfer, text="Limit for this download").grid(
            row=1, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            transfer, textvariable=self.max_speed, values=tuple(MAX_SPEEDS),
            state="readonly", width=18,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=7)
        ttk.Label(transfer, text="Shared limit for all downloads").grid(
            row=2, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            transfer, textvariable=self.global_max_speed, values=tuple(MAX_SPEEDS),
            state="readonly", width=18,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=7)
        ttk.Label(
            transfer,
            text="The shared limit applies to the combined speed of active downloads.",
            wraplength=540,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Separator(transfer).grid(row=4, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Label(transfer, text="Verify downloaded file").grid(
            row=5, column=0, sticky="w", pady=7
        )
        checksum_controls = ttk.Frame(transfer)
        checksum_controls.grid(row=5, column=1, sticky="ew", padx=10, pady=7)
        ttk.Combobox(
            checksum_controls, textvariable=self.checksum_algorithm,
            values=("SHA256", "MD5"), state="readonly", width=10,
        ).pack(side="left")
        ttk.Entry(
            checksum_controls, textvariable=self.expected_checksum,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(
            transfer, text="Optional: paste the expected checksum from the download page.",
        ).grid(row=6, column=1, sticky="w", padx=10, pady=(0, 4))

        connection = ttk.Frame(notebook, padding=16)
        connection.columnconfigure(1, weight=1)
        notebook.add(connection, text="Connection")
        ttk.Label(connection, text="Proxy (optional)").grid(
            row=0, column=0, sticky="w", pady=7
        )
        ttk.Entry(connection, textvariable=self.proxy_list).grid(
            row=0, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Label(
            connection, text="HTTP or SOCKS5 address. Separate retry addresses with commas.",
            wraplength=540,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(0, 10))
        ttk.Label(connection, text="Browser cookies").grid(
            row=2, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            connection, textvariable=self.browser_cookies,
            values=("None", "Chrome", "Firefox", "Edge", "Brave"),
            state="readonly", width=18,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=7)

        automation = ttk.Frame(notebook, padding=16)
        automation.columnconfigure(1, weight=1)
        notebook.add(automation, text="Schedule & files")
        ttk.Label(automation, text="Start at (local time)").grid(
            row=0, column=0, sticky="w", pady=7
        )
        ttk.Entry(automation, textvariable=self.scheduled_start, width=24).grid(
            row=0, column=1, sticky="w", padx=10, pady=7
        )
        ttk.Label(
            automation, text="Use YYYY-MM-DD HH:MM, or leave blank to start now.",
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(0, 8))
        ttk.Checkbutton(
            automation, text="Warn if this link was already downloaded",
            variable=self.warn_on_duplicates, command=self._save_duplicate_preference,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=7)
        ttk.Checkbutton(
            automation, text="Automatically extract supported archives",
            variable=self.auto_extract, command=self._save_extract_preference,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=7)
        ttk.Separator(automation).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=12
        )
        ttk.Label(automation, text="Save to cloud").grid(
            row=5, column=0, sticky="w", pady=7
        )
        cloud_controls = ttk.Frame(automation)
        cloud_controls.grid(row=5, column=1, sticky="ew", padx=10, pady=7)
        ttk.Combobox(
            cloud_controls, textvariable=self.cloud_provider,
            values=("Local folder", "Amazon S3", "Google Drive", "Dropbox"),
            state="readonly", width=18,
        ).pack(side="left")
        ttk.Button(
            cloud_controls, text="Account setup", command=self._configure_cloud_account,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(automation, text="Remote folder / prefix").grid(
            row=6, column=0, sticky="w", pady=7
        )
        ttk.Entry(automation, textvariable=self.cloud_folder).grid(
            row=6, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Label(
            automation, text="Cloud downloads use a temporary local staging folder.",
        ).grid(row=7, column=1, sticky="w", padx=10, pady=(0, 6))
        self.cloud_provider.trace_add("write", self._save_cloud_preferences)
        self.cloud_folder.trace_add("write", self._save_cloud_preferences)
        self._update_destination_mode()

    def _set_queue_filter(self, filter_name: str) -> None:
        self._queue_filter = filter_name
        labels = {
            "all": "All tasks",
            "downloading": "Downloading",
            "completed": "Completed",
            "media": "Media library",
        }
        self.queue_title_label.configure(text=labels[filter_name])
        for name, button in self.navigation_buttons.items():
            button.configure(
                style="NavigationActive.TButton" if name == filter_name else "Navigation.TButton"
            )
        self._apply_queue_filter()

    def _apply_queue_filter(self) -> None:
        visible_items = []
        visible_index = 0
        for job_id in self._queue_job_ids:
            if not self.jobs.exists(job_id):
                continue
            status = self.jobs.set(job_id, "status")
            if self._queue_filter == "downloading":
                matches = status not in FINISHED_STATUSES
            elif self._queue_filter == "completed":
                matches = status == "Complete"
            elif self._queue_filter == "media":
                media_path = self._download_paths.get(job_id)
                matches = (
                    status == "Complete"
                    and media_path is not None
                    and media_path.suffix.lower() in MEDIA_EXTENSIONS
                )
            else:
                matches = True
            if matches:
                self.jobs.move(job_id, "", visible_index)
                visible_items.append(job_id)
                visible_index += 1
            else:
                self.jobs.detach(job_id)
        if visible_items:
            self.queue_hint_label.configure(
                text=f"{len(visible_items)} item(s) · Right-click images for tools"
            )
        else:
            self.queue_hint_label.configure(text="No downloads in this view")

    def _refresh_job_style(self, job_id: str) -> None:
        if not self.jobs.exists(job_id):
            return
        status = self.jobs.set(job_id, "status")
        if status == "Complete":
            status_tag = "status_complete"
        elif status in {"Downloading", "Recording live stream", "Waiting for connection"}:
            status_tag = "status_active"
        elif status == "Failed":
            status_tag = "status_failed"
        else:
            status_tag = "status_other"
        tags = [status_tag]
        if "hidden" in self.jobs.item(job_id, "tags"):
            tags.append("hidden")
        self.jobs.item(job_id, tags=tuple(tags))

    def _restore_history(self) -> None:
        for record in self.history_records:
            job_id = str(record.id)
            options = record.options
            output_path = options.get("output_path")
            if output_path:
                self._download_paths[job_id] = Path(output_path)
            elif record.details:
                detail_path = Path(record.details)
                self._download_paths[job_id] = (
                    detail_path
                    if detail_path.is_absolute() and detail_path.exists()
                    else Path(options.get("destination", record.destination))
                )
            else:
                self._download_paths[job_id] = Path(
                    options.get("destination", record.destination)
                )
            if record.destination.startswith(
                ("Amazon S3 /", "Google Drive /", "Dropbox /")
            ):
                self._job_destinations[job_id] = record.destination
            self._job_destinations[job_id] = record.destination
            if record.status != "Complete":
                try:
                    self.download_options[job_id] = self._options_for_record(record)
                except ValueError as error:
                    self._resume_errors[job_id] = str(error)
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
                tags=("hidden",) if record.hidden else (),
            )
            self._queue_job_ids.append(job_id)
            self._refresh_job_style(job_id)
        self._apply_queue_filter()

    def _refresh_history(self) -> None:
        for job_id in tuple(self._queue_job_ids):
            if self.jobs.exists(job_id):
                self.jobs.delete(job_id)
        self._queue_job_ids.clear()
        self._resume_errors.clear()
        for record in self.history.list_records(include_hidden=self.show_hidden.get()):
            job_id = str(record.id)
            options = record.options
            output_path = options.get("output_path")
            if output_path:
                self._download_paths[job_id] = Path(output_path)
            elif record.details:
                detail_path = Path(record.details)
                self._download_paths[job_id] = (
                    detail_path
                    if detail_path.is_absolute() and detail_path.exists()
                    else Path(options.get("destination", record.destination))
                )
            else:
                self._download_paths[job_id] = Path(
                    options.get("destination", record.destination)
                )
            if record.destination.startswith(
                ("Amazon S3 /", "Google Drive /", "Dropbox /")
            ):
                self._job_destinations[job_id] = record.destination
            else:
                self._job_destinations[job_id] = record.destination
            if record.status != "Complete":
                try:
                    self.download_options[job_id] = self._options_for_record(record)
                except ValueError as error:
                    self._resume_errors[job_id] = str(error)
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
                tags=("hidden",) if record.hidden else (),
            )
            self._queue_job_ids.append(job_id)
            self._refresh_job_style(job_id)
        self._apply_queue_filter()

    def _update_global_bandwidth(self, *_args: object) -> None:
        try:
            limit = MAX_SPEEDS[self.global_max_speed.get()]
        except KeyError as error:
            messagebox.showerror("Invalid global bandwidth cap", str(error))
            return
        self.bandwidth_limiter.set_limit(limit)

    def _save_duplicate_preference(self) -> None:
        self.history.set_setting(
            "warn_on_duplicates",
            "1" if self.warn_on_duplicates.get() else "0",
        )

    def _save_theme_preference(self) -> None:
        self.history.set_setting("dark_mode", "1" if self.dark_mode.get() else "0")
        self._apply_theme()
        self._draw_speed_graph()

    def _use_recommended_settings(self) -> None:
        self.source.set("Auto")
        self.mode.set("Video")
        self.quality.set("1080p (Full HD)")
        self.playlist_scope.set("Auto (from link)")
        self.speed_mode.set("Balanced")
        self.max_speed.set("Unlimited")
        self.progress_summary.set(
            "Recommended settings selected. Paste a link, choose a folder, then add the download."
        )

    def _apply_theme(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        if self.dark_mode.get():
            background = "#121214"
            surface = "#1a1a1e"
            sidebar_background = "#151519"
            foreground = "#ededed"
            muted = "#b7b7c0"
            field = "#18181d"
            accent = "#1ba987"
            select_background = "#28554b"
            button_active = "#303038"
            completed_color = "#65d6a6"
            active_color = "#62c9ed"
            failed_color = "#ff8585"
            other_color = "#e8c675"
        else:
            background = "#f3f5f8"
            surface = "#ffffff"
            sidebar_background = "#e9eef4"
            foreground = "#182230"
            muted = "#526174"
            field = "#ffffff"
            accent = "#1769aa"
            select_background = "#cfe4f8"
            button_active = "#e3ebf4"
            completed_color = "#167346"
            active_color = "#087d9d"
            failed_color = "#b42318"
            other_color = "#805b00"
        style.configure(".", background=background, foreground=foreground)
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=foreground)
        style.configure(
            "TNotebook", background=background, borderwidth=0, tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "TNotebook.Tab", background=surface, foreground=foreground,
            padding=(12, 8), focuscolor=surface,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", accent), ("active", button_active)],
            foreground=[("selected", "#ffffff"), ("active", foreground)],
        )
        style.configure(
            "TLabelframe", background=background, foreground=foreground,
            bordercolor=muted,
        )
        style.configure(
            "TLabelframe.Label", background=background, foreground=foreground,
        )
        style.configure("Sidebar.TFrame", background=sidebar_background)
        style.configure(
            "SidebarTitle.TLabel", background=sidebar_background, foreground=foreground,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "SidebarHint.TLabel", background=sidebar_background, foreground=muted,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Navigation.TButton", background=sidebar_background, foreground=foreground,
            anchor="w", padding=(12, 9), borderwidth=0,
        )
        style.map(
            "Navigation.TButton",
            background=[("active", button_active), ("pressed", button_active)],
            foreground=[("disabled", muted), ("active", foreground)],
        )
        style.configure(
            "Navigation.TMenubutton", background=sidebar_background,
            foreground=foreground, anchor="w", padding=(12, 9), borderwidth=0,
        )
        style.map(
            "Navigation.TMenubutton",
            background=[("active", button_active), ("pressed", button_active)],
            foreground=[("active", foreground)],
        )
        style.configure(
            "NavigationActive.TButton", background=select_background,
            foreground=foreground, anchor="w", padding=(12, 9), borderwidth=0,
        )
        style.map(
            "NavigationActive.TButton",
            background=[("active", select_background), ("pressed", select_background)],
            foreground=[("active", foreground)],
        )
        style.configure("Card.TFrame", background=surface)
        style.configure(
            "Card.TLabel",
            background=surface,
            foreground=foreground,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "TButton",
            background=surface,
            foreground=foreground,
            padding=(10, 5),
            borderwidth=1,
        )
        style.map(
            "TButton",
            background=[("disabled", background), ("pressed", button_active), ("active", button_active)],
            foreground=[("disabled", muted)],
        )
        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="#ffffff",
            padding=(12, 6),
            borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", muted), ("pressed", select_background), ("active", select_background)],
            foreground=[("disabled", background), ("!disabled", "#ffffff")],
        )
        style.configure("TCheckbutton", background=background, foreground=foreground)
        style.map(
            "TCheckbutton",
            background=[("active", background)],
            foreground=[("disabled", muted), ("active", foreground)],
        )
        style.configure(
            "TEntry",
            fieldbackground=field,
            foreground=foreground,
            borderwidth=1,
            padding=5,
        )
        style.configure(
            "TCombobox",
            fieldbackground=field,
            foreground=foreground,
            arrowcolor=foreground,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", field), ("disabled", background)],
            foreground=[("readonly", foreground), ("disabled", muted)],
            selectbackground=[("readonly", select_background)],
            selectforeground=[("readonly", foreground)],
        )
        style.configure("TSeparator", background=muted)
        style.configure(
            "Treeview",
            background=field,
            fieldbackground=field,
            foreground=foreground,
            rowheight=28,
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", select_background)],
            foreground=[("selected", foreground)],
        )
        style.configure(
            "Treeview.Heading",
            background=surface,
            foreground=foreground,
            padding=(8, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", button_active)],
            foreground=[("active", foreground)],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=accent,
            troughcolor=surface,
            bordercolor=surface,
        )
        style.configure(
            "Vertical.TScrollbar",
            background=surface,
            troughcolor=background,
            arrowcolor=foreground,
        )
        self.root.configure(background=background)
        self._style_menu(self.history_menu, surface, foreground, muted, accent)
        self._style_menu(self.tools_menu, surface, foreground, muted, accent)
        self.settings_window.configure(background=background)
        self.jobs.tag_configure("hidden", foreground=muted)
        self.jobs.tag_configure("status_complete", foreground=completed_color)
        self.jobs.tag_configure("status_active", foreground=active_color)
        self.jobs.tag_configure("status_failed", foreground=failed_color)
        self.jobs.tag_configure("status_other", foreground=other_color)
        for job_id in self._queue_job_ids:
            self._refresh_job_style(job_id)
        self.speed_graph.configure(background=field)
        self._draw_speed_graph()

    @staticmethod
    def _style_menu(
        menu: tk.Menu,
        background: str,
        foreground: str,
        muted: str,
        accent: str,
    ) -> None:
        menu.configure(
            background=background,
            foreground=foreground,
            activebackground=accent,
            activeforeground="#ffffff",
            disabledforeground=muted,
            selectcolor=accent,
            borderwidth=0,
            relief="flat",
        )

    def _style_context_menu(self, menu: tk.Menu) -> None:
        if self.dark_mode.get():
            palette = ("#1a1a1e", "#ededed", "#b7b7c0", "#1ba987")
        else:
            palette = ("#ffffff", "#182230", "#526174", "#1769aa")
        self._style_menu(menu, *palette)

    def _has_pending_duplicate(self, url: str) -> bool:
        normalized = normalize_url(url)
        return any(
            self.jobs.exists(job_id)
            and
            self.jobs.set(job_id, "status") not in FINISHED_STATUSES
            and normalize_url(self.jobs.set(job_id, "link")) == normalized
            for job_id in self._queue_job_ids
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

    def _checksum_options(self) -> tuple[str, str]:
        algorithm = self.checksum_algorithm.get().lower()
        expected = self.expected_checksum.get().strip()
        if ":" in expected:
            prefix, expected = expected.split(":", 1)
            algorithm = prefix.lower()
        if algorithm not in {"md5", "sha256"}:
            raise ValueError("Choose MD5 or SHA256 for checksum verification.")
        if expected:
            try:
                digest_size = hashlib.new(algorithm).digest_size * 2
            except ValueError as error:
                raise ValueError(f"Unsupported checksum algorithm: {algorithm}") from error
            if len(expected) != digest_size or not re.fullmatch(r"[0-9a-fA-F]+", expected):
                raise ValueError(f"{algorithm.upper()} checksum must contain {digest_size} hex characters.")
        return algorithm, expected

    def _persist_job(
        self,
        job_id: str,
        status: str,
        progress: str,
        details: str,
    ) -> None:
        options = self.download_options.get(job_id)
        self.history.update(
            int(job_id),
            status,
            progress,
            details,
            getattr(self, "_job_destinations", {}).get(
                job_id, str(self._download_paths[job_id])
            ),
            self._persistent_job_options(job_id, options) if options else None,
        )

    def _persistent_job_options(
        self,
        job_id: str,
        options: dict,
    ) -> dict:
        return self._persistent_job_options_values(
            options, self._download_paths.get(job_id)
        )

    @staticmethod
    def _persistent_job_options_values(
        options: dict,
        output_path: Path | None = None,
    ) -> dict:
        saved = {
            key: options[key]
            for key in (
                "source", "mode", "quality", "playlist_scope", "speed_mode",
                "max_speed", "checksum_algorithm", "expected_checksum",
                "browser_cookies", "auto_extract", "cloud_provider", "cloud_folder",
            )
            if key in options
        }
        saved["destination"] = str(options["destination"])
        if output_path is not None:
            saved["output_path"] = str(output_path)
        return saved

    def _options_for_record(self, record) -> dict:
        saved = record.options
        cloud_provider = saved.get("cloud_provider", "local")
        default_destination = record.destination if cloud_provider == "local" else ""
        destination = saved.get("destination", default_destination)
        if not destination:
            raise ValueError(
                "This older cloud-download record has no saved staging folder and cannot be resumed."
            )
        return {
            "url": record.url,
            "destination": Path(destination),
            "source": saved.get("source", "auto"),
            "mode": saved.get("mode", "video"),
            "quality": saved.get("quality", "best"),
            "playlist_scope": saved.get("playlist_scope", "auto (from link)"),
            "speed_mode": saved.get("speed_mode", "balanced"),
            "max_speed": saved.get("max_speed"),
            "checksum_algorithm": saved.get("checksum_algorithm", "sha256"),
            "expected_checksum": saved.get("expected_checksum", ""),
            "proxy": self.proxy_list.get().strip(),
            "browser_cookies": self.browser_cookies.get().lower(),
            "auto_extract": saved.get("auto_extract", False),
            "cloud_provider": cloud_provider,
            "cloud_folder": saved.get("cloud_folder", ""),
        }

    def clear_finished(self) -> int:
        removed = 0
        for job_id in tuple(self._queue_job_ids):
            if not self.jobs.exists(job_id):
                continue
            if self.jobs.set(job_id, "status") not in FINISHED_STATUSES:
                continue
            self.history.set_hidden(int(job_id), True)
            self.jobs.delete(job_id)
            self._queue_job_ids.remove(job_id)
            self._download_paths.pop(job_id, None)
            getattr(self, "_job_destinations", {}).pop(job_id, None)
            self.download_options.pop(job_id, None)
            self._resume_errors.pop(job_id, None)
            self.cancel_events.pop(job_id, None)
            resume_event = self.resume_events.pop(job_id, None)
            if resume_event:
                resume_event.set()
            removed += 1

        if removed:
            self._apply_queue_filter()
            if self.show_hidden.get():
                self._refresh_history()
            self.progress_summary.set(
                f"Hidden {removed} finished download(s); use Show hidden to review history"
            )
        return removed

    def hide_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            return
        job_id = selected[0]
        if self.jobs.set(job_id, "status") not in FINISHED_STATUSES:
            messagebox.showinfo("Download is still active", "Only finished downloads can be hidden.")
            return
        self.history.set_hidden(int(job_id), True)
        self._refresh_history()

    def restore_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            return
        self.history.set_hidden(int(selected[0]), False)
        self._refresh_history()

    def _update_destination_labels(self, *_args: object) -> None:
        for job_id in self._queue_job_ids:
            if not self.jobs.exists(job_id):
                continue
            if self.jobs.set(job_id, "status") in {"Queued", "Scheduled"}:
                self.jobs.set(job_id, "location", self.destination.get())

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.destination.get() or str(Path.home()))
        if selected:
            self.destination.set(selected)

    def add_download(self) -> None:
        url = self.url_entry.get().strip()
        mode = getattr(self, "mode", None)
        if mode is not None and mode.get().lower() == "image gallery":
            self._start_gallery_scan(url)
            return
        selected_destination = Path(self.destination.get()).expanduser()
        provider_setting = getattr(self, "cloud_provider", None)
        provider_label = provider_setting.get() if provider_setting else "Local folder"
        cloud_folder_setting = getattr(self, "cloud_folder", None)
        cloud_folder = cloud_folder_setting.get().strip() if cloud_folder_setting else ""
        cloud_provider = {
            "Local folder": "local",
            "Amazon S3": "s3",
            "Google Drive": "google drive",
            "Dropbox": "dropbox",
        }.get(provider_label)
        if cloud_provider is None:
            messagebox.showerror("Invalid destination", "Choose a supported destination.")
            return

        try:
            parsed_url = urlsplit(url)
        except ValueError:
            messagebox.showerror("Invalid link", "Enter a valid public HTTP or HTTPS link.")
            return
        if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.hostname:
            messagebox.showerror("Invalid link", "Enter a valid public HTTP or HTTPS link.")
            return
        if self._has_pending_duplicate(url):
            messagebox.showwarning(
                "Download already queued",
                "This URL is already queued, scheduled, or downloading.",
            )
            return
        browser_cookie_setting = getattr(self, "browser_cookies", None)
        browser_cookies = (
            browser_cookie_setting.get().lower() if browser_cookie_setting else "none"
        )
        if browser_cookies != "none" and browser_cookies not in SUPPORTED_BROWSERS:
            messagebox.showerror("Invalid browser", "Choose a supported browser for cookies.")
            return
        previous_download = self.history.find_by_url(url)
        if (
            previous_download is not None
            and self.warn_on_duplicates.get()
            and not messagebox.askyesno(
                "Downloaded before",
                "This link is already in your download history.\n\n"
                "Would you like to download it again?",
                default=messagebox.NO,
            )
        ):
            return
        if cloud_provider == "local" and not self.destination.get().strip():
            messagebox.showerror("Choose a folder", "Select where downloaded files should be saved.")
            return
        if cloud_provider != "local":
            try:
                if not is_configured(cloud_provider):
                    raise RuntimeError(
                        f"Set up your {provider_label} account before adding this download."
                    )
            except (OSError, RuntimeError, ValueError) as error:
                messagebox.showerror("Cloud account not ready", str(error))
                return

        try:
            start_at = self._parse_scheduled_start(self.scheduled_start.get())
            max_speed = self._bandwidth_limit()
            quality = self._quality_key()
            checksum_algorithm, expected_checksum = self._checksum_options()
            proxy_setting = getattr(self, "proxy_list", None)
            proxy_value = proxy_setting.get().strip() if proxy_setting else ""
            parse_proxy_list(proxy_value)
        except ValueError as error:
            messagebox.showerror("Invalid download option", str(error))
            return

        destination = (
            Path(tempfile.mkdtemp(prefix="smart-downloader-cloud-"))
            if cloud_provider != "local"
            else selected_destination
        )
        job_destination = (
            str(selected_destination)
            if cloud_provider == "local"
            else f"{provider_label} / {cloud_folder or '/'}"
        )
        status = "Scheduled" if start_at is not None else "Queued"
        job_options = {
            "url": url,
            "destination": destination,
            "source": self.source.get().lower(),
            "mode": self.mode.get().lower(),
            "quality": quality,
            "playlist_scope": self.playlist_scope.get().lower(),
            "speed_mode": self.speed_mode.get().lower(),
            "max_speed": max_speed,
            "checksum_algorithm": checksum_algorithm,
            "expected_checksum": expected_checksum,
            "proxy": proxy_value,
            "browser_cookies": browser_cookies,
            "auto_extract": getattr(self, "auto_extract", None).get()
            if getattr(self, "auto_extract", None)
            else False,
            "cloud_provider": cloud_provider,
            "cloud_folder": cloud_folder,
        }
        try:
            job_id = str(
                self.history.add(
                    url,
                    status,
                    job_destination,
                    self._persistent_job_options_values(job_options),
                )
            )
        except (OSError, sqlite3.Error) as error:
            detail = str(error)
            if cloud_provider != "local":
                try:
                    shutil.rmtree(destination)
                except OSError as cleanup_error:
                    detail += (
                        f"\nTemporary staging folder could not be removed: "
                        f"{destination} ({cleanup_error})"
                    )
            messagebox.showerror("Could not save download history", detail)
            return

        cancel_event = threading.Event()
        resume_event = threading.Event()
        resume_event.set()
        self.cancel_events[job_id] = cancel_event
        self.resume_events[job_id] = resume_event
        self._download_paths[job_id] = destination
        self._job_destinations[job_id] = job_destination
        self.download_options[job_id] = job_options
        details = (
            datetime.fromtimestamp(start_at).astimezone().strftime("Starts %Y-%m-%d %H:%M")
            if start_at is not None
            else "Waiting"
        )
        self.jobs.insert(
            "",
            0,
            iid=job_id,
            values=(status, "—", details, job_destination, url),
        )
        self._queue_job_ids.append(job_id)
        self._refresh_job_style(job_id)
        self._apply_queue_filter()
        self._persist_job(job_id, status, "—", details)
        self.url_entry.delete(0, "end")
        if start_at is None:
            self.overall_progress.configure(mode="indeterminate", value=0)
            self.overall_progress.start(12)
            self.progress_summary.set("Queued - " + job_destination)
            self._submit_download(job_id)
        else:
            timer = threading.Timer(
                max(0.0, start_at - datetime.now().timestamp()),
                lambda: self.events.put(("start", job_id)),
            )
            timer.daemon = True
            self.schedule_timers[job_id] = timer
            timer.start()
            self.progress_summary.set(f"{details} - {job_destination}")

    def _submit_download(self, job_id: str) -> None:
        options = self.download_options.get(job_id)
        cancel_event = self.cancel_events.get(job_id)
        resume_event = self.resume_events.get(job_id)
        if options is None or cancel_event is None or resume_event is None or cancel_event.is_set():
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
            resume_event,
            options["max_speed"],
            self.bandwidth_limiter,
            job_id,
            options["proxy"],
            options["browser_cookies"],
        )
        future.add_done_callback(lambda result: self._job_finished(job_id, result))

    def _record_speed_sample(self, job_id: str, details: str) -> None:
        speed_match = re.search(r"([\d.]+)\s*(KiB/s|MiB/s|KB/s|MB/s)", details, re.I)
        now = time.monotonic()
        if speed_match:
            value = float(speed_match.group(1))
            unit = speed_match.group(2).lower()
            speed = value * (1024 if unit in {"kib/s", "kb/s"} else 1024 * 1024)
        else:
            amount_match = re.search(r"([\d.]+)\s*/\s*[\d.]+\s*MB", details, re.I)
            if amount_match is None:
                return
            amount = float(amount_match.group(1)) * 1024 * 1024
            previous = self._speed_state.get(job_id)
            self._speed_state[job_id] = (amount, now)
            if previous is None or now <= previous[1]:
                return
            speed = max(0.0, (amount - previous[0]) / (now - previous[1]))
        history = self._speed_history.setdefault(job_id, [])
        self._active_graph_job = job_id
        history.append(speed)
        del history[:-60]
        if now - self._last_graph_draw >= 1:
            self._last_graph_draw = now
            self._draw_speed_graph()

    def _draw_speed_graph(self) -> None:
        if not hasattr(self, "speed_graph"):
            return
        self.speed_graph.delete("all")
        width = max(self.speed_graph.winfo_width(), 120)
        height = max(self.speed_graph.winfo_height(), 50)
        samples = self._speed_history.get(self._active_graph_job or "", [])
        color = "#1769aa" if not self.dark_mode.get() else "#58a6ff"
        background = "#f4f6f8" if not self.dark_mode.get() else "#11161e"
        self.speed_graph.configure(background=background)
        self.speed_graph.create_text(
            8, 8, anchor="nw", text="Speed (last 60 samples)", fill=color
        )
        if len(samples) < 2:
            return
        maximum = max(max(samples), 1)
        points = []
        for index, speed in enumerate(samples):
            x = 8 + index * (width - 16) / max(len(samples) - 1, 1)
            y = height - 8 - (speed / maximum) * (height - 28)
            points.extend((x, y))
        self.speed_graph.create_line(*points, fill=color, width=2, smooth=True)
        self.speed_graph.create_text(
            width - 8, 8, anchor="ne", text=f"{maximum / (1024 * 1024):.2f} MB/s", fill=color
        )

    def open_sequence_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Download an image sequence")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        pattern = tk.StringVar(value="https://example.com/image_{:03d}.jpg")
        start = tk.StringVar(value="1")
        end = tk.StringVar(value="500")
        ttk.Label(dialog, text="Link pattern (use {:03d} for the number)").grid(
            row=0, column=0, columnspan=2, padx=12, pady=(12, 4), sticky="w"
        )
        ttk.Entry(dialog, textvariable=pattern, width=60).grid(
            row=1, column=0, columnspan=2, padx=12, sticky="ew"
        )
        ttk.Label(dialog, text="From").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        ttk.Entry(dialog, textvariable=start, width=12).grid(row=2, column=1, padx=12, pady=8, sticky="w")
        ttk.Label(dialog, text="To (up to 10,000 images)").grid(row=3, column=0, padx=12, sticky="w")
        ttk.Entry(dialog, textvariable=end, width=12).grid(row=3, column=1, padx=12, sticky="w")

        def add_sequence() -> None:
            try:
                urls = generate_sequence_urls(pattern.get().strip(), int(start.get()), int(end.get()))
            except ValueError as error:
                messagebox.showerror("Invalid sequence", str(error), parent=dialog)
                return
            old_source, old_mode = self.source.get(), self.mode.get()
            try:
                self.source.set("Direct file")
                self.mode.set("Video")
                accepted, _ = self._add_batch_urls(urls)
            finally:
                self.source.set(old_source)
                self.mode.set(old_mode)
            if accepted:
                self.progress_summary.set(f"Added {accepted} sequence image(s) to the download list.")
                dialog.destroy()

        ttk.Button(dialog, text="Add sequence", command=add_sequence, style="Accent.TButton").grid(
            row=4, column=0, columnspan=2, padx=12, pady=12, sticky="e"
        )
        dialog.grab_set()

    def _start_gallery_scan(self, page_url: str) -> None:
        try:
            parsed = urlsplit(page_url)
        except ValueError:
            messagebox.showerror("Invalid page link", "Enter a valid public HTTP or HTTPS page link.")
            return
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            messagebox.showerror("Invalid page link", "Enter a valid public HTTP or HTTPS page link.")
            return
        if not self.destination.get().strip():
            messagebox.showerror("Choose a folder", "Select where downloaded images should be saved.")
            return
        if self.expected_checksum.get().strip():
            messagebox.showerror("Checksum unavailable", "A single checksum cannot verify an image gallery.")
            return
        self.progress_summary.set("Scanning the page for image links…")
        future = self.executor.submit(scrape_image_urls, page_url)

        def check_result() -> None:
            if not future.done():
                self.root.after(100, check_result)
                return
            try:
                image_urls = future.result()
            except (RequestException, OSError, ValueError) as error:
                messagebox.showerror("Could not scan image page", str(error))
                return
            if not image_urls:
                messagebox.showinfo("No images found", "No supported image links were found on that page.")
                return
            preview = "\n".join(image_urls[:20])
            if len(image_urls) > 20:
                preview += f"\n… and {len(image_urls) - 20} more"
            if not messagebox.askyesno(
                "Image gallery found",
                f"Found {len(image_urls)} image(s):\n\n{preview}\n\nDownload all to the selected folder?",
            ):
                return
            previous_source = self.source.get()
            previous_mode = self.mode.get()
            try:
                self.source.set("Direct file")
                self.mode.set("Video")
                accepted, _ = self._add_batch_urls(image_urls)
            finally:
                self.source.set(previous_source)
                self.mode.set(previous_mode)
            self.progress_summary.set(f"Added {accepted} of {len(image_urls)} gallery image(s).")

        self.root.after(100, check_result)

    def _show_image_context_menu(self, event) -> None:
        row_id = self.jobs.identify_row(event.y)
        if not row_id:
            return
        self.jobs.selection_set(row_id)
        menu = tk.Menu(self.root, tearoff=False)
        self._style_context_menu(menu)
        menu.add_command(label="Open selected file or folder", command=self.open_selected_location)
        menu.add_command(label="Play selected audio/video", command=self.play_selected_media)
        menu.add_command(label="Resume / retry", command=self.resume_selected)
        menu.add_command(label="Extract selected archive", command=self.extract_selected_archive)
        menu.add_separator()
        path = self._selected_output_path()
        if path is not None and path.is_file() and path.suffix.lower() in {
            ".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp",
        }:
            self._add_image_tools(menu, path)
        menu.tk_popup(event.x_root, event.y_root)

    def _selected_output_path(self) -> Path | None:
        selected = self.jobs.selection()
        if not selected:
            return None
        job_id = selected[0]
        details = self.jobs.set(job_id, "details").strip()
        if details:
            candidate = Path(details).expanduser()
            if candidate.is_absolute() and candidate.exists():
                return candidate
        path = self._download_paths.get(job_id)
        return path if path is not None and path.exists() else None

    def _add_image_tools(self, menu: tk.Menu, path: Path) -> None:
        menu.add_command(
            label="Strip EXIF (save copy)",
            command=lambda: self._process_image(
                lambda: strip_exif(path), "Strip image metadata"
            ),
        )
        convert_menu = tk.Menu(menu, tearoff=False)
        self._style_context_menu(convert_menu)
        for label, image_format in (
            ("PNG", "PNG"),
            ("JPEG", "JPEG"),
            ("WebP", "WEBP"),
            ("AVIF", "AVIF"),
        ):
            convert_menu.add_command(
                label=label,
                command=lambda fmt=image_format, name=label: self._process_image(
                    lambda: convert_image(path, fmt), f"Convert to {name}"
                ),
            )
        menu.add_cascade(label="Convert image to", menu=convert_menu)
        menu.add_command(label="Resize image…", command=lambda: self._resize_selected_image(path))

    def open_selected_image_tools(self) -> None:
        path = self._selected_output_path()
        if (
            path is None
            or not path.is_file()
            or path.suffix.lower() not in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
        ):
            messagebox.showinfo(
                "Select a downloaded image",
                "Select a completed image in the queue before choosing image tools.",
                parent=self.root,
            )
            return
        menu = tk.Menu(self.root, tearoff=False)
        self._style_context_menu(menu)
        self._add_image_tools(menu, path)
        menu.tk_popup(
            self.root.winfo_rootx() + 80,
            self.root.winfo_rooty() + 180,
        )

    def extract_selected_archive(self) -> None:
        path = self._selected_output_path()
        if path is None or not path.is_file():
            messagebox.showinfo(
                "Select a downloaded archive",
                "Select a completed ZIP, RAR, or TAR archive in the queue.",
                parent=self.root,
            )
            return
        if path.suffix.lower() not in {".zip", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz"}:
            messagebox.showinfo(
                "Unsupported archive",
                "Supported archives are ZIP, RAR, TAR, TGZ, TAR.GZ, TAR.BZ2, and TAR.XZ.",
                parent=self.root,
            )
            return
        self._run_local_file_action(
            lambda: extract_archive(path),
            "Extract archive",
            parent=path.parent,
        )

    def _run_local_file_action(self, operation, title: str, parent: Path) -> None:
        future = self.executor.submit(operation)

        def check_result() -> None:
            if not future.done():
                self.root.after(100, check_result)
                return
            try:
                result = future.result()
            except (OSError, ValueError, RuntimeError) as error:
                messagebox.showerror(f"{title} failed", str(error), parent=self.root)
                return
            if result is None:
                messagebox.showinfo(title, "This file type is not a supported archive.", parent=self.root)
                return
            self.progress_summary.set(f"{title} complete: {result}")
            messagebox.showinfo(
                f"{title} complete",
                f"Saved to:\n{result}",
                parent=self.root,
            )
            self._open_path(Path(result))

        self.root.after(100, check_result)

    def play_selected_media(self) -> None:
        path = self._selected_output_path()
        if path is None or not path.is_file():
            messagebox.showinfo(
                "Select downloaded media",
                "Select a completed audio or video file in the queue.",
                parent=self.root,
            )
            return
        if path.suffix.lower() not in PLAYABLE_MEDIA_EXTENSIONS:
            messagebox.showinfo(
                "Unsupported media",
                "The selected file is not a recognized audio or video format.",
                parent=self.root,
            )
            return
        try:
            if sys.platform == "win32":
                vlc = shutil.which("vlc")
                if vlc is None:
                    for candidate in (
                        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                        / "VideoLAN" / "VLC" / "vlc.exe",
                        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
                        / "VideoLAN" / "VLC" / "vlc.exe",
                    ):
                        if candidate.is_file():
                            vlc = str(candidate)
                            break
                if vlc:
                    subprocess.Popen([vlc, str(path)])
                else:
                    os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                opener = shutil.which("xdg-open")
                if opener is None:
                    raise OSError("Could not find a media player or xdg-open.")
                subprocess.Popen([opener, str(path)])
        except OSError as error:
            messagebox.showerror("Could not play media", str(error), parent=self.root)

    def _select_image_gallery_mode(self) -> None:
        self.mode.set("Image gallery")
        self.url_entry.focus_set()
        self.progress_summary.set(
            "Paste a public webpage link, then click Add download to find its images."
        )

    def _open_clicked_row_action(self, event) -> None:
        row_id = self.jobs.identify_row(event.y)
        if not row_id:
            return
        self.jobs.selection_set(row_id)
        column = self.jobs.identify_column(event.x)
        if column == "#4":
            location = self.jobs.set(row_id, "location").strip()
            if location and not location.startswith(
                ("Amazon S3 /", "Google Drive /", "Dropbox /")
            ):
                self._open_path(Path(location))
            else:
                self.open_selected_location()
            return
        path = self._selected_output_path()
        if (
            self.jobs.set(row_id, "status") == "Complete"
            and path is not None
            and path.suffix.lower() in PLAYABLE_MEDIA_EXTENSIONS
        ):
            self.play_selected_media()

    def _show_selected_thumbnail(self, _event=None) -> None:
        selected = self.jobs.selection()
        if not selected:
            self._clear_thumbnail("Select a downloaded image")
            return
        path = self._selected_output_path()
        if path is None or not path.is_file() or path.suffix.lower() not in {
            ".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp",
        }:
            self._clear_thumbnail("Select a downloaded image")
            return
        try:
            from PIL import Image, ImageTk

            with Image.open(path) as image:
                image.thumbnail((200, 200), Image.Resampling.LANCZOS)
                thumbnail = image.copy()
            photo = ImageTk.PhotoImage(thumbnail, master=self.root)
        except (OSError, ValueError, RuntimeError, tk.TclError) as error:
            self._clear_thumbnail(f"Preview unavailable:\n{error}")
            return
        self.current_thumbnail = photo
        self.preview_image_label.configure(image=photo, text="")
        self.preview_details.configure(text=path.name)

    def _clear_thumbnail(self, message: str) -> None:
        self.current_thumbnail = None
        self.preview_image_label.configure(image="", text=message)
        self.preview_details.configure(text="")

    def _resize_selected_image(self, path: Path) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Resize image")
        dialog.transient(self.root)
        width = tk.StringVar(value="1920")
        height = tk.StringVar(value="1080")
        ttk.Label(dialog, text="Maximum width").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        ttk.Entry(dialog, textvariable=width, width=12).grid(row=0, column=1, padx=12, pady=8)
        ttk.Label(dialog, text="Maximum height").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        ttk.Entry(dialog, textvariable=height, width=12).grid(row=1, column=1, padx=12, pady=8)

        def resize() -> None:
            try:
                max_width, max_height = int(width.get()), int(height.get())
            except ValueError:
                messagebox.showerror("Invalid size", "Enter whole-number width and height values.", parent=dialog)
                return
            self._process_image(
                lambda: resize_image(path, max_width, max_height),
                "Resize image",
            )
            dialog.destroy()

        ttk.Button(dialog, text="Resize", command=resize, style="Accent.TButton").grid(
            row=2, column=0, columnspan=2, padx=12, pady=12, sticky="e"
        )
        dialog.grab_set()

    def _process_image(self, operation, description: str) -> None:
        future = self.executor.submit(operation)

        def check_result() -> None:
            if not future.done():
                self.root.after(100, check_result)
                return
            try:
                result = future.result()
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                messagebox.showerror(f"{description} failed", str(error))
                return
            messagebox.showinfo(description, f"Saved image:\n{result}")

        self.root.after(100, check_result)

    def toggle_pause_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            return
        job_id = selected[0]
        resume_event = self.resume_events.get(job_id)
        if resume_event is None or self.cancel_events.get(job_id, threading.Event()).is_set():
            return
        if resume_event.is_set():
            resume_event.clear()
            self.jobs.set(job_id, "status", "Paused")
            self.progress_summary.set("Paused - partial data is retained for resume")
            self.overall_progress.stop()
        else:
            resume_event.set()
            self.jobs.set(job_id, "status", "Resuming")
            self.progress_summary.set("Resuming download...")
        self._refresh_job_style(job_id)
        self._apply_queue_filter()

    def resume_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            messagebox.showinfo("Select a download", "Select an interrupted or failed download first.")
            return
        job_id = selected[0]
        status = self.jobs.set(job_id, "status")
        if status not in {"Interrupted", "Failed", "Cancelled"}:
            messagebox.showinfo(
                "Download cannot be resumed",
                "Choose a failed, cancelled, or interrupted download to retry.",
            )
            return
        if job_id in self._resume_errors:
            messagebox.showerror("Cannot resume download", self._resume_errors[job_id])
            return
        options = self.download_options.get(job_id)
        if options is None:
            messagebox.showerror(
                "Cannot resume download",
                "This history entry has no saved download information. "
                "Add the link again to start a new download.",
            )
            return
        cancel_event = threading.Event()
        resume_event = threading.Event()
        resume_event.set()
        self.cancel_events[job_id] = cancel_event
        self.resume_events[job_id] = resume_event
        self.jobs.set(job_id, "status", "Queued")
        self.jobs.set(job_id, "progress", "—")
        self.jobs.set(job_id, "details", "Resuming saved download data")
        self._persist_job(job_id, "Queued", "—", "Resuming saved download data")
        self._refresh_job_style(job_id)
        self._apply_queue_filter()
        self.progress_summary.set("Retrying download; any supported partial data will be resumed.")
        self._submit_download(job_id)

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
        cloud_destination = getattr(self, "_job_destinations", {}).get(job_id, "")
        if cloud_destination.startswith(
            ("Amazon S3 /", "Google Drive /", "Dropbox /")
        ):
            messagebox.showinfo(
                "Cloud destination",
                f"This download was uploaded to {cloud_destination}.",
            )
            return
        path = self._selected_output_path() or self._download_paths.get(
            job_id, Path(self.destination.get())
        )
        self._open_path(path)

    def _open_path(self, path: Path) -> None:
        try:
            path = path.expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"Location does not exist: {path}")
            folder = path if path.is_dir() else path.parent
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
        except (OSError, RuntimeError) as error:
            messagebox.showerror("Could not open location", str(error))

    def show_help(self) -> None:
        messagebox.showinfo(
            "Smart Downloader help",
            "Getting started\n"
            "1. Paste the page or file link.\n"
            "2. Choose where to save it (Downloads is the usual choice).\n"
            "3. Keep the recommended settings, then click Add download.\n\n"
            "Use Batch... to paste several links or load them from a text file. "
            "Auto-fill copied links places copied web links into the link box when enabled.\n\n"
            "The app can remind you if you have already downloaded a link. Turn off "
            "Warn if already downloaded to stop these reminders. Finished downloads "
            "show a small notification. Your dark or light theme choice is remembered.\n\n"
            "Optional choices\n"
            "Choose Best audio or MP3 if you only want sound. Choose a lower picture "
            "quality to use less storage. Enter an MD5 or SHA-256 hash if you want the app "
            "to check that a downloaded file matches it. Pause, continue, or cancel a selected download "
            "with the buttons below the list. Use Open selected location to find a finished file.\n\n"
            "Choose Image gallery to preview and queue images found in common page image tags. "
            "Use Sequence... for numbered image links. Right-click a finished image to convert "
            "or resize it. The speed chart shows recent transfer speed.\n\n"
            "Your download list is saved between app launches. Clear finished hides old "
            "rows rather than deleting their history; turn on Show hidden and use Restore "
            "selected to bring a row back.\n\n"
            "Only public links and content you have permission to save are supported. "
            "Some sites may block downloads or require unavailable sign-in.",
        )

    def _job_finished(self, job_id: str, future: Future[str]) -> None:
        try:
            result = future.result()
            options = self.download_options.get(job_id, {})
            expected = options.get("expected_checksum", "")
            if expected:
                result_file = Path(result)
                if not result_file.is_file():
                    raise RuntimeError("Checksum verification requires a single output file.")
                algorithm = options["checksum_algorithm"]
                actual, matches = verify_checksum(result_file, algorithm, expected)
                if not matches:
                    raise RuntimeError(
                        f"{algorithm.upper()} checksum mismatch. "
                        f"Expected {expected}; actual {actual}."
                    )
                self.verified_checksums[job_id] = (algorithm, actual)
            if options.get("auto_extract"):
                extracted_folder = extract_archive(Path(result))
                if extracted_folder is not None:
                    result = str(extracted_folder)
            cloud_provider = options.get("cloud_provider", "local")
            if cloud_provider != "local":
                staging = options["destination"]
                try:
                    remote_paths = upload_path(
                        select_upload_source(Path(result), staging),
                        cloud_provider,
                        options["cloud_folder"],
                    )
                except Exception as error:
                    raise RuntimeError(
                        f"Cloud upload failed; your local copy is still at {staging}: {error}"
                    ) from error
                result = "; ".join(remote_paths)
                try:
                    shutil.rmtree(staging)
                except OSError as error:
                    result += (
                        f" (upload complete; local staging copy remains at {staging}: "
                        f"{error})"
                    )
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
            resume_event = self.resume_events.get(job_id)
            if resume_event:
                resume_event.set()
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

            if event[0] == "conversion_complete":
                _, output_path = event
                self.progress_summary.set(f"MP3 conversion complete: {Path(output_path).name}")
                messagebox.showinfo(
                    "MP3 conversion complete",
                    f"Saved MP3 file to:\n{output_path}",
                    parent=self.root,
                )
            elif event[0] == "conversion_failed":
                _, error = event
                self.progress_summary.set(f"MP3 conversion failed: {error}")
                messagebox.showerror("MP3 conversion failed", error, parent=self.root)
            elif event[0] == "start":
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
                    self._refresh_job_style(job_id)
                    self._apply_queue_filter()
                    self._persist_job(job_id, "Queued", "—", "Waiting")
                    self._submit_download(job_id)
                    self.progress_summary.set(
                        f"Scheduled download started - {self._download_paths[job_id]}"
                    )
            elif event[0] == "progress":
                _, job_id, status, percent, details = event
                details = _clean_terminal_text(details)
                self._record_speed_sample(job_id, details)
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
                    self._refresh_job_style(job_id)
                    self._apply_queue_filter()
                    self.jobs.set(
                        job_id,
                        "location",
                        getattr(self, "_job_destinations", {}).get(
                            job_id, str(self._download_paths[job_id])
                        ),
                    )
                    self._persist_job(job_id, status, progress_text, details)
                    self.progress_summary.set(
                        f"{status}: {progress_text}"
                        + (f" - {details}" if details else "")
                        + f" | Saving to {self._download_paths[job_id]}"
                    )
            else:
                _, job_id, status, detail = event
                detail = _clean_terminal_text(detail)
                display_detail = detail
                if self.jobs.exists(job_id):
                    self.jobs.set(job_id, "status", status)
                    if status == "Complete":
                        checksum = self.verified_checksums.pop(job_id, None)
                        if checksum:
                            algorithm, digest = checksum
                            display_detail = f"Verified {algorithm.upper()}: {digest}"
                        self.jobs.set(job_id, "progress", "100%")
                        self.jobs.set(job_id, "details", display_detail)
                        result_path = Path(detail)
                        if result_path.is_absolute():
                            self._download_paths[job_id] = result_path
                            result_folder = result_path if result_path.is_dir() else result_path.parent
                            self.jobs.set(job_id, "location", str(result_folder))
                        self.overall_progress.stop()
                        self.overall_progress.configure(mode="determinate", value=100)
                        self.progress_summary.set(f"Complete - {display_detail}")
                    elif status in {"Failed", "Cancelled"}:
                        if status == "Failed":
                            detail = self._friendly_download_error(detail)
                            display_detail = detail
                        self.jobs.set(job_id, "progress", status)
                        self.jobs.set(job_id, "details", display_detail)
                        if status == "Failed" and detail.startswith("Cloud upload failed;"):
                            staging = self._download_paths.get(job_id)
                            if staging is not None:
                                self._job_destinations[job_id] = str(staging)
                                self.jobs.set(job_id, "location", str(staging))
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
                        display_detail,
                    )
                    self._refresh_job_style(job_id)
                    self._apply_queue_filter()
                    if status == "Complete":
                        try:
                            notify(
                                "Download complete",
                                Path(detail).name if detail else self.jobs.set(job_id, "link"),
                            )
                        except Exception as error:
                            warning = f"OS notification failed: {error}"
                            self.progress_summary.set(
                                f"{self.progress_summary.get()} | {warning}"
                            )
                            messagebox.showwarning("Notification unavailable", warning)
                self.cancel_events.pop(job_id, None)
                resume_event = self.resume_events.pop(job_id, None)
                if resume_event:
                    resume_event.set()
                self.schedule_timers.pop(job_id, None)
                self.download_options.pop(job_id, None)

        self.root.after(100, self._process_events)

    @staticmethod
    def _friendly_download_error(detail: str) -> str:
        if "winerror 5" in detail.casefold() or "access is denied" in detail.casefold():
            return (
                "Windows denied access to the output file. Close any media player or "
                "preview using the file, check folder permissions and free disk space, "
                f"then choose Resume / retry. Details: {detail}"
            )
        return detail

    def _close(self) -> None:
        for timer in self.schedule_timers.values():
            timer.cancel()
        for job_id, cancel_event in self.cancel_events.items():
            if not self.jobs.exists(job_id):
                cancel_event.set()
                continue
            status = self.jobs.set(job_id, "status")
            if status not in FINISHED_STATUSES:
                self.jobs.set(job_id, "status", "Interrupted")
                progress = self.jobs.set(job_id, "progress")
                details = self.jobs.set(job_id, "details")
                try:
                    self._persist_job(job_id, "Interrupted", progress, details)
                except (OSError, sqlite3.Error, KeyError) as error:
                    messagebox.showerror(
                        "Could not save download state",
                        f"Download {job_id} may need to be added again after restart:\n{error}",
                        parent=self.root,
                    )
            cancel_event.set()
        for resume_event in self.resume_events.values():
            resume_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        DownloaderApp(root)
    except Exception:
        root.destroy()
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
