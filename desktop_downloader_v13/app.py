from __future__ import annotations

from app_support import (
    queue,
    os,
    re,
    sqlite3,
    shutil,
    subprocess,
    sys,
    tempfile,
    threading,
    time,
    hashlib,
    json,
    webbrowser,
    tk,
    Callable,
    Future,
    ThreadPoolExecutor,
    datetime,
    Path,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
    urlsplit,
    RequestException,
    GlobalBandwidthLimiter,
    verify_checksum,
    is_configured,
    save_credentials,
    select_upload_source,
    upload_path,
    SUPPORTED_BROWSERS,
    convert_docx_to_pdf,
    convert_pdf_to_docx,
    DownloadCancelled,
    _clean_terminal_text,
    _ffmpeg_directory,
    download_url,
    extract_archive,
    DownloadHistory,
    normalize_url,
    convert_image,
    generate_sequence_urls,
    resize_image,
    scrape_image_urls,
    strip_exif,
    notify,
    load_plugins,
    parse_proxy_list,
    is_torrent_url,
    MAX_SPEEDS,
    PLAYABLE_MEDIA_EXTENSIONS,
    FINISHED_STATUSES,
    MEDIA_EXTENSIONS,
    _convert_media_to_mp3,
)
from app_downloads import DownloadsMixin
from app_events import EventsMixin
from app_media import MediaMixin
from app_preferences import PreferencesMixin
from app_queue import QueueMixin
from app_theme import ThemeMixin
from app_ui import UiMixin

class DownloaderApp(UiMixin, ThemeMixin, PreferencesMixin, QueueMixin, DownloadsMixin, MediaMixin, EventsMixin):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Smart Downloader")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(1440, max(1180, screen_width - 80))
        window_height = min(860, max(680, screen_height - 80))
        self.root.minsize(1180, 680)
        self.root.geometry(f"{window_width}x{window_height}")

        self.events: queue.Queue[tuple] = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._progress_lock = threading.Lock()
        self._last_progress_update: dict[str, tuple[float, str]] = {}
        self.history = DownloadHistory()
        load_plugins()
        self.history.mark_unfinished_interrupted()
        self.history_records = self.history.list_records()
        self.cancel_events: dict[str, threading.Event] = {}
        self.resume_events: dict[str, threading.Event] = {}
        self.schedule_timers: dict[str, threading.Timer] = {}
        self._download_futures: dict[str, Future[str]] = {}
        self.download_options: dict[str, dict] = {}
        self.bandwidth_limiter = GlobalBandwidthLimiter()
        self.verified_checksums: dict[str, tuple[str, str]] = {}
        self._integrity_baselines: dict[str, tuple[Path, str]] = {}
        self.destination = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.destination_label = tk.StringVar(value="Save to")
        self.cloud_provider = tk.StringVar(
            value=self.history.get_setting("cloud_provider", "Local folder")
        )
        self.cloud_folder = tk.StringVar(value=self.history.get_setting("cloud_folder", ""))
        self.source = tk.StringVar(value="Auto")
        self.mode = tk.StringVar(value="Video")
        self.quality = tk.StringVar(value="1080p (Full HD)")
        self.playlist_scope = tk.StringVar(value="Auto (from link)")
        self.speed_mode = tk.StringVar(value="Fast")
        self.max_speed = tk.StringVar(value="Unlimited")
        self.global_max_speed = tk.StringVar(value="Unlimited")
        self.expected_checksum = tk.StringVar(value="")
        self.checksum_algorithm = tk.StringVar(value="SHA256")
        self.language = tk.StringVar(
            value=self.history.get_setting("language", "English")
        )
        self.large_text = tk.BooleanVar(
            value=self.history.get_setting("large_text", "0") == "1"
        )
        self.high_contrast = tk.BooleanVar(
            value=self.history.get_setting("high_contrast", "0") == "1"
        )
        self.check_updates = tk.BooleanVar(
            value=self.history.get_setting("check_updates", "1") == "1"
        )
        self.diagnostics_enabled = tk.BooleanVar(
            value=self.history.get_setting("diagnostics_enabled", "0") == "1"
        )
        self._diagnostics_enabled = self.history.get_setting(
            "diagnostics_enabled", "0"
        ) == "1"
        self.proxy_list = tk.StringVar(value="")
        self.browser_cookies = tk.StringVar(value="None")
        self.retry_attempts = tk.StringVar(
            value=self.history.get_setting("retry_attempts", "10")
        )
        self.retry_base_delay = tk.StringVar(
            value=self.history.get_setting("retry_base_delay", "1")
        )
        self.retry_max_delay = tk.StringVar(
            value=self.history.get_setting("retry_max_delay", "30")
        )
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
        self._last_clipboard_error: str | None = None
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
        if self.history.recovery_backup_path is not None:
            messagebox.showwarning(
                "Download history recovered",
                "The saved history database was corrupted. A copy was preserved at:\n"
                f"{self.history.recovery_backup_path}\n\n"
                "The app created a new history database; the previous history "
                "was not deleted.",
                parent=self.root,
            )
        self.global_max_speed.trace_add("write", self._update_global_bandwidth)
        self.root.after(100, self._process_events)
        self.root.after(800, self._watch_clipboard)
        self._bind_keyboard_shortcuts()
        if self.check_updates.get():
            self.root.after(2500, lambda: self._check_for_updates(interactive=False))
        self.root.protocol("WM_DELETE_WINDOW", self._close)


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
