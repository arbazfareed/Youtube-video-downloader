from __future__ import annotations

from datetime import datetime, timedelta

from app_support import (
    tk,
    ttk,
    MAX_SPEEDS,
    LANGUAGES,
    messagebox,
    translate,
)
from statistics_engine import DownloadStatistics, calculate_statistics

class UiMixin:
    def _t(self, text: str) -> str:
        return translate(text, self.language.get())

    def _update_link_preview(self, *_args) -> None:
        value = self.url_text.get().strip()
        self.link_preview_var.set(
            f"{self._t('Link preview')}: {value}"
            if value
            else self._t("Paste or type a link here.")
        )

    def _open_settings_shortcut(self, _event=None) -> str:
        self.open_download_settings()
        return "break"

    def _help_shortcut(self, _event=None) -> str:
        self.show_help()
        return "break"

    def _add_download_shortcut(self, _event=None) -> str:
        self.add_download()
        return "break"

    def _open_location_shortcut(self, _event=None) -> str:
        self.open_selected_location()
        return "break"

    def _focus_url_shortcut(self, _event=None) -> str:
        self.url_entry.focus_set()
        return "break"

    def _focus_queue_shortcut(self, _event=None) -> str:
        self.jobs.focus_set()
        return "break"

    def _focus_progress_shortcut(self, _event=None) -> str:
        self.progress_summary_label.focus_set()
        return "break"

    def _keyboard_shortcuts_text(self) -> str:
        return "\n".join(
            (
                self._t("Keyboard shortcuts:"),
                f"Ctrl+, — {self._t('Settings')}",
                f"F1 — {self._t('Help')}",
                f"Ctrl+Enter — {self._t('Add download')}",
                f"Ctrl+O — {self._t('Open selected location')}",
                self._t("Ctrl+L — focus link field"),
                self._t("Ctrl+J — focus download list"),
                self._t("Alt+S — focus progress status"),
                self._t(
                    "Space — toggle Smart VLC playback when open; otherwise "
                    "pause/resume the focused download"
                ),
                self._t(
                    "Smart VLC and preview: Left/Right seek 5 seconds; "
                    "Up/Down change volume 5%"
                ),
                self._t("Press F1 for help. Use Tab and Shift+Tab to move between controls."),
            )
        )

    def _keyboard_shortcuts_summary_text(self) -> str:
        return "\n".join(
            (
                self._t("Keyboard shortcuts:"),
                f"Ctrl+, {self._t('Settings')} · F1 {self._t('Help')} · "
                f"Ctrl+Enter {self._t('Add download')}",
                f"Ctrl+O {self._t('Open selected location')} · "
                f"{self._t('Ctrl+L — focus link field')} · "
                f"{self._t('Ctrl+J — focus download list')}",
                f"{self._t('Alt+S — focus progress status')} · "
                f"{self._t('Space — toggle Smart VLC playback when open; otherwise pause/resume the focused download')}",
                self._t(
                    "Smart VLC and preview: Left/Right seek 5 seconds; "
                    "Up/Down change volume 5%"
                ),
                self._t("Press F1 for help. Use Tab and Shift+Tab to move between controls."),
            )
        )

    def _toggle_pause_from_queue(self, _event=None) -> str:
        if getattr(self, "_in_app_player", None) is not None:
            self._toggle_in_app_playback()
        else:
            self.toggle_pause_selected()
        return "break"

    def _bind_keyboard_shortcuts(self) -> None:
        shortcuts = (
            ("<Control-comma>", self._open_settings_shortcut),
            ("<F1>", self._help_shortcut),
            ("<Control-Return>", self._add_download_shortcut),
            ("<Control-o>", self._open_location_shortcut),
            ("<Control-l>", self._focus_url_shortcut),
            ("<Control-j>", self._focus_queue_shortcut),
            ("<Alt-s>", self._focus_progress_shortcut),
            ("<space>", self._toggle_in_app_playback_from_key),
            ("<Left>", self._handle_playback_arrow_key),
            ("<Right>", self._handle_playback_arrow_key),
            ("<Up>", self._handle_playback_arrow_key),
            ("<Down>", self._handle_playback_arrow_key),
        )
        for sequence, callback in shortcuts:
            self.root.bind_all(sequence, callback, add="+")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=0, minsize=190)
        outer.columnconfigure(1, weight=1, minsize=660)
        outer.columnconfigure(2, weight=0, minsize=0)
        outer.rowconfigure(0, weight=1)
        self._main_outer = outer
        splitter = ttk.Panedwindow(outer, orient="horizontal")
        splitter.grid(
            row=0, column=1, columnspan=2, sticky="nsew",
            padx=(0, 16), pady=16,
        )
        self._main_splitter = splitter
        self._main_splitter_stacked = False
        self._main_splitter_initial_sash_set = False
        self._main_splitter_initial_sash_pending = False
        sidebar_host = ttk.Frame(outer, style="Sidebar.TFrame")
        sidebar_host.grid(row=0, column=0, sticky="nsew")
        self._sidebar_host = sidebar_host
        sidebar_host.rowconfigure(0, weight=1)
        sidebar_host.columnconfigure(0, weight=1)
        self.sidebar_canvas = tk.Canvas(
            sidebar_host,
            width=220,
            borderwidth=0,
            highlightthickness=0,
            background="#151519" if self.dark_mode.get() else "#e9eef4",
        )
        self.sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_host,
            orient="vertical",
            command=self.sidebar_canvas.yview,
        )
        self.sidebar_scrollbar.grid(row=0, column=1, sticky="ns")
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        sidebar = ttk.Frame(self.sidebar_canvas, style="Sidebar.TFrame", padding=(10, 14))
        self.sidebar_window = self.sidebar_canvas.create_window(
            (0, 0), window=sidebar, anchor="nw"
        )
        sidebar.bind("<Configure>", self._update_sidebar_scroll_region)
        self.sidebar_canvas.bind("<Configure>", self._resize_sidebar_content)
        self.root.bind_all("<MouseWheel>", self._scroll_sidebar, add="+")
        self.root.bind_all("<Button-4>", self._scroll_sidebar, add="+")
        self.root.bind_all("<Button-5>", self._scroll_sidebar, add="+")
        sidebar.columnconfigure(0, weight=1)
        ttk.Label(
            sidebar, text="SMART\nDOWNLOADER", style="SidebarTitle.TLabel",
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(2, 20))
        self.navigation_buttons: dict[str, ttk.Button] = {}
        navigation_items = (
            ("all", self._t("All tasks")),
            ("downloading", self._t("Downloading")),
            ("completed", self._t("Completed")),
            ("media", self._t("Media library")),
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
            sidebar, text=self._t("Settings"), style="Navigation.TButton",
            command=self.open_download_settings,
        ).grid(row=6, column=0, sticky="ew", pady=2)
        ttk.Button(
            sidebar, text=self._t("Statistics"), style="Navigation.TButton",
            command=self.open_statistics_dashboard,
        ).grid(row=7, column=0, sticky="ew", pady=2)
        tools_button = ttk.Menubutton(
            sidebar, text=self._t("Tools & utilities"), style="Navigation.TMenubutton",
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
            label="Extract an archive…", command=self.extract_local_archive,
        )
        self.tools_menu.add_command(
            label="Create ZIP from a file…", command=self.create_zip_from_file,
        )
        self.tools_menu.add_command(
            label="Create ZIP from a folder…", command=self.create_zip_from_folder,
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
            command=self._select_image_gallery_mode,
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
        tools_button.grid(row=8, column=0, sticky="ew", pady=2)
        ttk.Button(
            sidebar, text=self._t("Convert to MP3"), style="Navigation.TButton",
            command=self.convert_local_file_to_mp3,
        ).grid(row=9, column=0, sticky="ew", pady=2)
        ttk.Button(
            sidebar, text=self._t("Image tools"), style="Navigation.TButton",
            command=self.open_selected_image_tools,
        ).grid(row=10, column=0, sticky="ew", pady=2)
        ttk.Button(
            sidebar, text=self._t("Image gallery"), style="Navigation.TButton",
            command=self._select_image_gallery_mode,
        ).grid(row=11, column=0, sticky="ew", pady=2)
        ttk.Label(
            sidebar, text=self._t("Download and organize\nlocal media"), style="SidebarHint.TLabel",
            justify="left",
        ).grid(row=12, column=0, sticky="sw", padx=8, pady=(24, 0))

        frame = ttk.Frame(splitter, padding=16)
        self._main_content_frame = frame
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        inspector = ttk.Frame(splitter, style="Card.TFrame", padding=14)
        self._media_inspector = inspector
        inspector.columnconfigure(0, weight=1)
        inspector.rowconfigure(2, weight=1)
        splitter.add(frame, weight=4)
        splitter.add(inspector, weight=1)

        header = ttk.Frame(frame, style="Card.TFrame", padding=(14, 9))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header, text="Smart Downloader 14", style="Card.TLabel",
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header, text=self._t("Paste a link, choose where to save it, and add it to your queue."),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))
        ttk.Button(
            header, text=self._t("Use recommended"), command=self._use_recommended_settings,
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Checkbutton(
            header, text=self._t("Auto-fill copied links"), variable=self.clipboard_autofill,
            command=self._save_clipboard_preference,
        ).grid(row=0, column=2, sticky="e", padx=(12, 0))
        ttk.Checkbutton(
            header, text=self._t("Dark mode"), variable=self.dark_mode,
            command=self._save_theme_preference,
        ).grid(row=1, column=2, sticky="e", padx=(12, 0), pady=(4, 0))

        add_card = ttk.Frame(frame, style="Card.TFrame", padding=12)
        add_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        add_card.columnconfigure(1, weight=1)
        ttk.Label(add_card, text=self._t("Link"), style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.url_text = tk.StringVar(value="")
        self.link_preview_var = tk.StringVar(value=self._t("Paste or type a link here."))
        self.link_feedback_var = tk.StringVar(value="")
        self.url_entry = ttk.Entry(add_card, textvariable=self.url_text)
        self.url_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        self.url_text.trace_add("write", self._update_link_preview)
        self.link_preview_label = ttk.Label(
            add_card,
            textvariable=self.link_preview_var,
            style="SidebarHint.TLabel",
            wraplength=760,
            justify="left",
        )
        self.link_preview_label.grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(0, 6)
        )
        self.link_feedback_label = ttk.Label(
            add_card,
            textvariable=self.link_feedback_var,
            style="SidebarHint.TLabel",
            wraplength=760,
            justify="left",
        )
        self.link_feedback_label.grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )
        self.url_entry.bind("<Return>", lambda _event: self.add_download())
        add_buttons = ttk.Frame(add_card, style="Card.TFrame")
        add_buttons.grid(row=0, column=2, sticky="e", padx=(10, 0), pady=(0, 8))
        ttk.Button(
            add_buttons, text=self._t("Inspect link"), command=self.inspect_link,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            add_buttons, text=self._t("Add download"), command=self.add_download,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(add_buttons, text=self._t("Playlist items"), command=self.open_playlist_selection_dialog).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(add_buttons, text=self._t("Format tips"), command=self.show_format_tips).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(add_buttons, text=self._t("Batch"), command=self.open_batch_dialog).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(add_buttons, text=self._t("Sequence"), command=self.open_sequence_dialog).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(add_buttons, text=self._t("Search"), command=self.open_youtube_search_dialog).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(add_buttons, text=self._t("Schedule"), command=self.open_schedule_dialog).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(add_card, textvariable=self.destination_label, style="Card.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 10)
        )
        self.destination_entry = ttk.Entry(add_card, textvariable=self.destination)
        self.destination_entry.grid(row=2, column=1, sticky="ew")
        self.destination_browse_button = ttk.Button(
            add_card, text=self._t("Browse"), command=self._choose_folder,
        )
        self.destination_browse_button.grid(row=2, column=2, padx=(10, 0))
        self._build_remaining_ui(frame, inspector)

        footer = ttk.Frame(outer, padding=(16, 4))
        footer.grid(row=1, column=0, columnspan=3, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Separator(footer, orient="horizontal").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4),
        )
        ttk.Label(footer, text="Smart Downloader 14").grid(row=1, column=0, sticky="w")
        ttk.Label(
            footer, text="Created by Arbaz Fareed · AFJ DEVOPS", anchor="e",
        ).grid(row=1, column=1, sticky="e")
        self.footer = footer
        self.destination.trace_add("write", self._update_destination_labels)
        self._update_destination_labels()

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title(self._t("Settings"))
        self.settings_window.geometry("760x560")
        self.settings_window.minsize(660, 480)
        self.settings_window.transient(self.root)
        self.settings_window.protocol("WM_DELETE_WINDOW", self.settings_window.withdraw)
        self.settings_window.bind("<Escape>", lambda _event: self.settings_window.withdraw())
        self._build_settings_ui()
        self.settings_window.withdraw()
        self._set_queue_filter("all")

    def _resize_preview_text(self, event=None) -> None:
        width = max(180, int(getattr(event, "width", 280)) - 32)
        for widget_name in (
            "preview_video_placeholder", "preview_image_label",
            "preview_video_status", "preview_details",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                try:
                    widget.configure(wraplength=width)
                except (tk.TclError, AttributeError):
                    pass

    def open_download_settings(self) -> None:
        self.settings_window.deiconify()
        self.settings_window.lift()
        self.settings_window.focus_set()

    def open_youtube_search_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self._t("Search YouTube"))
        dialog.geometry("740x500")
        dialog.minsize(580, 360)
        dialog.transient(self.root)

        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        search_header = ttk.Frame(dialog, padding=(12, 10))
        search_header.grid(row=0, column=0, sticky="ew")
        search_header.columnconfigure(1, weight=1)

        ttk.Label(search_header, text=self._t("Search:")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        query_var = tk.StringVar(value="")
        query_entry = ttk.Entry(search_header, textvariable=query_var)
        query_entry.grid(row=0, column=1, sticky="ew")

        search_status_var = tk.StringVar(value=self._t("Type a search term and press Search."))
        status_label = ttk.Label(dialog, textvariable=search_status_var, padding=(12, 0))
        status_label.grid(row=1, column=0, sticky="w")

        tree_frame = ttk.Frame(dialog, padding=12)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        columns = ("title", "channel", "duration", "link")
        results_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        results_tree.heading("title", text=self._t("Title"))
        results_tree.heading("channel", text=self._t("Channel"))
        results_tree.heading("duration", text=self._t("Duration"))
        results_tree.heading("link", text=self._t("Link"))

        results_tree.column("title", width=340, stretch=True)
        results_tree.column("channel", width=140, stretch=False)
        results_tree.column("duration", width=75, stretch=False)
        results_tree.column("link", width=160, stretch=False)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=results_tree.yview)
        results_tree.configure(yscrollcommand=tree_scroll.set)
        results_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll.grid(row=0, column=1, sticky="ns")

        actions_frame = ttk.Frame(dialog, padding=12)
        actions_frame.grid(row=3, column=0, sticky="ew")

        def _format_sec(seconds) -> str:
            if not seconds or not isinstance(seconds, (int, float)):
                return "--:--"
            total = int(seconds)
            h, rem = divmod(total, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        def do_search() -> None:
            query = query_var.get().strip()
            if not query:
                return
            search_btn.configure(state="disabled")
            search_status_var.set(f"Searching YouTube for '{query}'…")
            results_tree.delete(*results_tree.get_children())

            def background_search():
                try:
                    import yt_dlp
                    ydl_opts = {
                        "extract_flat": True,
                        "quiet": True,
                        "no_warnings": True,
                        "skip_download": True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        data = ydl.extract_info(f"ytsearch12:{query}", download=False)
                    entries = data.get("entries") or []

                    def update_ui():
                        search_btn.configure(state="normal")
                        if not entries:
                            search_status_var.set("No results found. Try a different search term.")
                            return
                        search_status_var.set(f"Found {len(entries)} result(s). Double-click or select to download.")
                        for item in entries:
                            title = item.get("title") or "Unknown"
                            channel = item.get("uploader") or item.get("channel") or ""
                            duration = _format_sec(item.get("duration"))
                            url = item.get("url") or f"https://www.youtube.com/watch?v={item.get('id')}"
                            results_tree.insert("", "end", values=(title, channel, duration, url))

                    dialog.after(0, update_ui)
                except Exception as error:
                    # `error` is deleted when this block ends; capture the text so
                    # the deferred callback can still re-enable the Search button.
                    failure_text = f"Search failed: {error}"

                    def report_err():
                        search_btn.configure(state="normal")
                        search_status_var.set(failure_text)
                    dialog.after(0, report_err)

            self.executor.submit(background_search)

        search_btn = ttk.Button(search_header, text=self._t("Search"), command=do_search, style="Accent.TButton")
        search_btn.grid(row=0, column=2, padx=(8, 0))
        query_entry.bind("<Return>", lambda _event: do_search())

        def download_selected() -> None:
            selected = results_tree.selection()
            if not selected:
                messagebox.showinfo("No selection", "Please select a video to download.", parent=dialog)
                return
            values = results_tree.item(selected[0], "values")
            if not values:
                return
            url = values[3]
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, url)
            dialog.destroy()
            self.add_download()

        def copy_selected_link() -> None:
            selected = results_tree.selection()
            if not selected:
                return
            values = results_tree.item(selected[0], "values")
            if values:
                self.root.clipboard_clear()
                self.root.clipboard_append(values[3])
                search_status_var.set("Link copied to clipboard.")

        results_tree.bind("<Double-1>", lambda _e: download_selected())

        ttk.Button(actions_frame, text=self._t("Download Selected"), command=download_selected, style="Accent.TButton").pack(side="left")
        ttk.Button(actions_frame, text=self._t("Copy Link"), command=copy_selected_link).pack(side="left", padx=(8, 0))
        ttk.Button(actions_frame, text=self._t("Close"), command=dialog.destroy).pack(side="right")

        query_entry.focus_set()

    def open_schedule_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self._t("Schedule Downloads"))
        dialog.geometry("480x380")
        dialog.minsize(420, 320)
        dialog.transient(self.root)

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        ttk.Label(
            content,
            text=self._t("Quick Schedule Presets"),
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 6))

        ttk.Label(
            content,
            text=self._t("Queue will automatically pause until the scheduled time arrives."),
            wraplength=440,
        ).pack(anchor="w", pady=(0, 10))

        presets_frame = ttk.Frame(content)
        presets_frame.pack(fill="x", pady=(0, 14))
        for col in range(2):
            presets_frame.columnconfigure(col, weight=1)

        def set_preset_minutes(minutes: int) -> None:
            target = datetime.now() + timedelta(minutes=minutes)
            time_str = target.strftime("%Y-%m-%d %H:%M")
            self.scheduled_start.set(time_str)
            self.progress_summary.set(f"Downloads scheduled for {time_str}")
            dialog.destroy()

        def set_preset_night(hour: int) -> None:
            now = datetime.now()
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            time_str = target.strftime("%Y-%m-%d %H:%M")
            self.scheduled_start.set(time_str)
            self.progress_summary.set(f"Downloads scheduled for {time_str}")
            dialog.destroy()

        def clear_schedule() -> None:
            self.scheduled_start.set("")
            self.progress_summary.set("Schedule cleared. Downloads will start immediately.")
            dialog.destroy()

        ttk.Button(presets_frame, text="In 15 minutes", command=lambda: set_preset_minutes(15)).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        ttk.Button(presets_frame, text="In 30 minutes", command=lambda: set_preset_minutes(30)).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        ttk.Button(presets_frame, text="In 1 hour", command=lambda: set_preset_minutes(60)).grid(row=1, column=0, sticky="ew", padx=3, pady=3)
        ttk.Button(presets_frame, text="In 2 hours", command=lambda: set_preset_minutes(120)).grid(row=1, column=1, sticky="ew", padx=3, pady=3)
        ttk.Button(presets_frame, text="Tonight at 2:00 AM", command=lambda: set_preset_night(2)).grid(row=2, column=0, sticky="ew", padx=3, pady=3)
        ttk.Button(presets_frame, text="Tonight at 4:00 AM", command=lambda: set_preset_night(4)).grid(row=2, column=1, sticky="ew", padx=3, pady=3)

        ttk.Separator(content).pack(fill="x", pady=10)

        ttk.Label(
            content,
            text=self._t("Custom Schedule (YYYY-MM-DD HH:MM):"),
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 4))

        custom_frame = ttk.Frame(content)
        custom_frame.pack(fill="x", pady=(0, 10))
        custom_entry = ttk.Entry(custom_frame, textvariable=self.scheduled_start, width=24)
        custom_entry.pack(side="left", padx=(0, 8))

        def apply_custom() -> None:
            val = self.scheduled_start.get().strip()
            if val:
                self.progress_summary.set(f"Downloads scheduled for {val}")
            else:
                self.progress_summary.set("Downloads set to start immediately.")
            dialog.destroy()

        ttk.Button(custom_frame, text="Apply", command=apply_custom, style="Accent.TButton").pack(side="left")

        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Start Immediately (Clear)", command=clear_schedule).pack(side="left")
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")


    def open_statistics_dashboard(self) -> None:
        existing = getattr(self, "_statistics_window", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()

        statistics = calculate_statistics(
            self.history.list_records(include_hidden=True)
        )
        window = tk.Toplevel(self.root)
        self._statistics_window = window
        window.title(self._t("Statistics dashboard"))
        window.geometry("760x560")
        window.minsize(620, 460)
        window.transient(self.root)

        content = ttk.Frame(window, padding=18)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text=self._t("Statistics dashboard"),
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=self._t(
                "Lifetime statistics from saved download history, including hidden rows."
            ),
        ).pack(anchor="w", pady=(4, 16))

        cards = ttk.Frame(content)
        cards.pack(fill="x", pady=(0, 18))
        for column in range(4):
            cards.columnconfigure(column, weight=1)
        metrics = (
            (self._t("Total downloads"), statistics.total_downloads),
            (self._t("Completed files"), statistics.completed),
            (self._t("Success rate"), f"{statistics.success_rate:.1f}%"),
            (
                self._t("Failed or stopped"),
                statistics.failed + statistics.cancelled + statistics.interrupted,
            ),
        )
        for column, (label, value) in enumerate(metrics):
            card = ttk.Frame(cards, style="Card.TFrame", padding=12)
            card.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
            ttk.Label(card, text=label, style="Card.TLabel").pack(anchor="w")
            ttk.Label(
                card,
                text=str(value),
                style="Card.TLabel",
                font=("Segoe UI", 20, "bold"),
            ).pack(anchor="w", pady=(6, 0))

        ttk.Label(
            content,
            text=self._t("Top source domains"),
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        chart_background = "#151519" if self.dark_mode.get() else "#f4f6f8"
        chart_foreground = "#ffffff" if self.dark_mode.get() else "#242424"
        if self.high_contrast.get():
            chart_background = "#000000"
            chart_foreground = "#ffffff"
        chart = tk.Canvas(
            content,
            height=250,
            background=chart_background,
            highlightthickness=0,
        )
        chart.pack(fill="both", expand=True, pady=(8, 0))
        chart.bind(
            "<Configure>",
            lambda _event: self._draw_domain_statistics_chart(
                chart, statistics, chart_foreground
            ),
        )
        self._draw_domain_statistics_chart(chart, statistics, chart_foreground)

    def _draw_domain_statistics_chart(
        self,
        canvas: tk.Canvas,
        statistics: DownloadStatistics,
        foreground: str,
    ) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 420)
        if not statistics.top_domains:
            canvas.create_text(
                16,
                24,
                text=self._t("No source domains recorded yet."),
                anchor="nw",
                fill=foreground,
            )
            return

        maximum = max(count for _, count in statistics.top_domains)
        label_width = min(220, max(150, int(width * 0.38)))
        bar_start = label_width + 16
        bar_width = max(40, width - bar_start - 48)
        for index, (domain, count) in enumerate(statistics.top_domains):
            top = 12 + index * 42
            canvas.create_text(
                12,
                top + 12,
                text=domain,
                anchor="w",
                width=label_width,
                fill=foreground,
            )
            canvas.create_rectangle(
                bar_start,
                top + 4,
                bar_start + bar_width * count / maximum,
                top + 24,
                fill="#3b82f6",
                outline="",
            )
            canvas.create_text(
                bar_start + bar_width + 8,
                top + 14,
                text=str(count),
                anchor="w",
                fill=foreground,
            )

    def copy_selected_link(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            messagebox.showinfo(
                self._t("No task selected"),
                self._t("Select a task before copying its link."),
                parent=self.root,
            )
            return
        link = self.jobs.set(selected[0], "link")
        self.root.clipboard_clear()
        self.root.clipboard_append(link)
        self.root.update_idletasks()
        self.progress_summary.set(self._t("Link copied to clipboard."))

    def _build_remaining_ui(
        self,
        frame: ttk.Frame,
        inspector: ttk.Frame,
    ) -> None:
        options = ttk.Frame(frame, style="Card.TFrame", padding=(12, 10))
        options.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for column in range(2):
            options.columnconfigure(column, weight=1)
        options.columnconfigure(2, weight=0)
        quick_options = (
            (self._t("Source"), self.source, ("Auto", "Direct file", "Supported site", "Torrent/magnet")),
            (self._t("Media"), self.mode, ("Video", "Best audio", "MP3 audio", "Image gallery")),
            (self._t("Resolution"), self.quality, (
                "Best available", "Smart: Balanced 1080p", "Smart: Smaller file (720p)",
                "Smart: MP4 compatible", "Smart: Fastest", "8K (4320p)", "5K (2880p)", "4K (2160p)",
                "1440p (2K)", "1080p (Full HD)", "720p (HD)", "480p",
                "360p", "240p", "144p",
            )),
            (self._t("Audio language"), self.audio_languages, (
                "All languages", "English only", "Hindi only", "English + Hindi", "Original only",
            )),
            (self._t("Playlist"), self.playlist_scope, (
                "Auto (from link)", "Single video", "Entire playlist",
            )),
        )
        for index, (label, variable, values) in enumerate(quick_options):
            row, column = divmod(index, 2)
            label_row = row * 2
            ttk.Label(options, text=label, style="Card.TLabel").grid(
                row=label_row, column=column, sticky="w",
                padx=(0, 12), pady=(0, 3),
            )
            ttk.Combobox(
                options, textvariable=variable, values=values,
                state="readonly", width=18,
            ).grid(
                row=label_row + 1, column=column, sticky="ew",
                padx=(0, 12), pady=(0, 8),
            )
        ttk.Button(
            options, text=self._t("More settings"), command=self.open_download_settings,
        ).grid(row=0, column=2, rowspan=6, sticky="e", padx=(8, 0))

        progress_card = ttk.Frame(frame, style="Card.TFrame", padding=(12, 9))
        progress_card.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        progress_card.columnconfigure(0, weight=1)
        progress_header = ttk.Frame(progress_card, style="Card.TFrame")
        progress_header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            progress_header, text=self._t("Overall progress"), style="Card.TLabel",
        ).pack(side="left")
        self.progress_summary = tk.StringVar(value="No active downloads")
        self.progress_summary_label = ttk.Label(
            progress_header, textvariable=self.progress_summary, style="Card.TLabel",
            takefocus=True,
        )
        self.progress_summary_label.pack(side="right")
        self.overall_progress = ttk.Progressbar(
            progress_card, mode="determinate", maximum=100, takefocus=True,
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
            queue_header, text=self._t("All tasks"), font=("Segoe UI", 12, "bold"),
        )
        self.queue_title_label.grid(
            row=0, column=0, sticky="w"
        )
        self.queue_hint_label = ttk.Label(
            queue_header, text=self._t("Right-click an image download for image tools."),
        )
        self.queue_hint_label.grid(row=0, column=1, sticky="e")
        self.shutdown_checkbutton = ttk.Checkbutton(
            queue_header,
            text=self._t("Shutdown PC when finished"),
            variable=self.shutdown_on_complete,
            command=self._save_shutdown_preference,
        )
        self.shutdown_checkbutton.grid(row=0, column=2, sticky="e", padx=(10, 0))

        queue_frame = ttk.Frame(frame)
        queue_frame.grid(row=5, column=0, sticky="nsew")
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)
        columns = ("status", "progress", "details", "location", "link")
        self.jobs = ttk.Treeview(
            queue_frame, columns=columns, show="headings", selectmode="browse",
            takefocus=True,
        )
        self.jobs.heading("status", text=self._t("Status"))
        self.jobs.heading("progress", text=self._t("Progress"))
        self.jobs.heading("details", text=self._t("Transfer details"))
        self.jobs.heading("location", text=self._t("Saving to"))
        self.jobs.heading("link", text=self._t("Link"))
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
        self.jobs.bind("<space>", self._toggle_pause_from_queue)
        self.jobs.bind("<<TreeviewSelect>>", self._show_selected_thumbnail)

        preview_header = ttk.Frame(inspector, style="Card.TFrame")
        preview_header.grid(row=0, column=0, columnspan=2, sticky="ew")
        preview_header.columnconfigure(0, weight=1)
        ttk.Label(
            preview_header,
            text=self._t("Media preview"),
            style="Card.TLabel",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.inspector_status = tk.StringVar(value=self._t("No item selected"))
        ttk.Label(
            preview_header,
            textvariable=self.inspector_status,
            style="Preview.Status.TLabel",
            anchor="e",
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Separator(inspector).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(10, 12)
        )

        preview = ttk.Frame(inspector, style="Card.TFrame", padding=10)
        self.preview_container = preview
        preview.configure(takefocus=True)
        preview.bind("<Button-1>", lambda _event: preview.focus_set(), add="+")
        preview.grid(row=2, column=0, columnspan=2, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1, minsize=224)

        # Cinematic preview stage: a consistent dark surface in both app themes.
        self.preview_video_surface = tk.Frame(
            preview, background="#081426", height=224, takefocus=True,
            highlightthickness=1, highlightbackground="#24466d",
        )
        self.preview_video_surface.grid(
            row=0, column=0, sticky="nsew", pady=(0, 10),
        )
        self.preview_video_surface.grid_remove()
        self.preview_video_placeholder = tk.Label(
            self.preview_video_surface,
            text=self._t("Select a video to preview"),
            background="#081426",
            foreground="#dcecff",
            font=("Segoe UI", 12, "bold"),
            anchor="center",
            justify="center",
            wraplength=260,
            padx=18,
            pady=18,
        )
        self.preview_video_placeholder.place(
            relx=0.5, rely=0.5, anchor="center",
        )

        self.preview_player_controls = ttk.Frame(
            preview, style="Preview.Toolbar.TFrame", padding=(8, 8),
        )
        self.preview_player_controls.grid(
            row=1, column=0, sticky="ew", pady=(0, 10),
        )
        for column in range(7):
            self.preview_player_controls.columnconfigure(column, weight=0)
        self.preview_player_controls.columnconfigure(2, weight=1)

        self.preview_player_play_button = ttk.Button(
            self.preview_player_controls,
            text=self._t("Play"),
            command=self._toggle_video_preview,
            style="Preview.Play.TButton",
            width=7,
        )
        self.preview_player_play_button.grid(
            row=0, column=0, rowspan=2, sticky="ns", padx=(0, 8),
        )
        ttk.Label(
            self.preview_player_controls,
            text=self._t("Volume"),
            style="Preview.Muted.TLabel",
            takefocus=False,
        ).grid(row=0, column=1, sticky="w", padx=(0, 5))
        self.preview_player_volume = tk.IntVar(value=80)
        ttk.Scale(
            self.preview_player_controls,
            from_=0,
            to=100,
            variable=self.preview_player_volume,
            command=self._set_video_preview_volume,
            takefocus=True,
            length=104,
        ).grid(row=0, column=2, sticky="ew", padx=(0, 6))
        self.preview_player_volume_label = ttk.Label(
            self.preview_player_controls,
            text="80%",
            style="Preview.Value.TLabel",
            width=4,
            anchor="e",
            takefocus=False,
        )
        self.preview_player_volume_label.grid(row=0, column=3, padx=(0, 8))
        self.preview_player_current_time = tk.StringVar(value="00:00")
        ttk.Label(
            self.preview_player_controls,
            textvariable=self.preview_player_current_time,
            width=5,
            anchor="e",
            style="Preview.Value.TLabel",
        ).grid(row=1, column=1, padx=(0, 4), sticky="w")
        self.preview_player_position = tk.DoubleVar(value=0)
        self.preview_player_timeline = tk.Canvas(
            self.preview_player_controls,
            width=20,
            height=18,
            background="#14243a",
            highlightthickness=0,
            cursor="hand2",
        )
        self.preview_player_timeline.grid(
            row=1, column=2, sticky="ew", padx=(0, 4),
        )
        self.preview_player_timeline.bind(
            "<Configure>", lambda _event: self._draw_video_preview_timeline(),
            add="+",
        )
        self.preview_player_timeline.bind(
            "<ButtonPress-1>", self._begin_video_preview_seek, add="+",
        )
        self.preview_player_timeline.bind(
            "<B1-Motion>", self._update_video_preview_seek, add="+",
        )
        self.preview_player_timeline.bind(
            "<ButtonRelease-1>", self._seek_video_preview, add="+",
        )
        self.preview_player_timeline.bind(
            "<Enter>", lambda _event: self._set_video_preview_timeline_hover(True),
            add="+",
        )
        self.preview_player_timeline.bind(
            "<Leave>", lambda _event: self._set_video_preview_timeline_hover(False),
            add="+",
        )
        self.preview_player_duration = tk.StringVar(value="00:00")
        ttk.Label(
            self.preview_player_controls,
            textvariable=self.preview_player_duration,
            width=5,
            anchor="w",
            style="Preview.Value.TLabel",
        ).grid(row=1, column=3, sticky="w")

        # Keep secondary actions on their own row so they never squeeze the
        # volume slider or timeline in a narrow inspector pane.
        self.preview_player_action_controls = ttk.Frame(
            preview, style="Preview.Toolbar.TFrame", padding=(8, 6),
        )
        self.preview_player_action_controls.grid(
            row=2, column=0, sticky="ew", pady=(0, 10),
        )
        self.preview_player_action_controls.columnconfigure(0, weight=1)
        self.preview_player_action_controls.columnconfigure(1, weight=1)
        self.preview_player_settings_button = ttk.Button(
            self.preview_player_action_controls,
            text=self._t("Settings"),
            command=lambda: self._show_video_preview_settings(
                self.preview_player_settings_button
            ),
            style="Preview.Action.TButton",
        )
        self.preview_player_settings_button.grid(
            row=0, column=0, sticky="ew", padx=(0, 5),
        )
        self.preview_player_fullscreen_button = ttk.Button(
            self.preview_player_action_controls,
            text=self._t("Fullscreen"),
            command=self._open_preview_fullscreen,
            style="Preview.Action.TButton",
        )
        self.preview_player_fullscreen_button.grid(
            row=0, column=1, sticky="ew", padx=(5, 0),
        )

        videos_header = ttk.Frame(preview, style="Card.TFrame")
        videos_header.grid(row=3, column=0, sticky="ew", pady=(0, 4))
        videos_header.columnconfigure(0, weight=1)
        videos_header.columnconfigure(1, weight=0)
        ttk.Label(
            videos_header,
            text=self._t("Available videos"),
            style="Preview.Section.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self.preview_video_count = tk.StringVar(value="0 items")
        ttk.Label(
            videos_header, textvariable=self.preview_video_count,
            style="Preview.Count.TLabel", anchor="e",
        ).grid(row=0, column=1, sticky="e")
        self.preview_video_choice = tk.StringVar(value="")
        self.preview_video_selector = ttk.Combobox(
            preview,
            textvariable=self.preview_video_choice,
            state="disabled",
            takefocus=True,
        )
        self.preview_video_selector.grid(
            row=4, column=0, sticky="ew", pady=(0, 8),
        )
        preview.bind("<Configure>", self._resize_preview_text, add="+")
        self.preview_video_selector.bind(
            "<<ComboboxSelected>>",
            self._select_preview_video,
            add="+",
        )

        audio_header = ttk.Label(
            preview,
            text=self._t("Audio track"),
            style="Preview.Section.TLabel",
        )
        audio_header.grid(row=5, column=0, sticky="w", pady=(0, 4))
        self._preview_audio_track = tk.StringVar(value="")
        self.preview_audio_selector = ttk.Combobox(
            preview,
            textvariable=self._preview_audio_track,
            state="disabled",
            takefocus=True,
        )
        self.preview_audio_selector.grid(
            row=6, column=0, sticky="ew", pady=(0, 8),
        )
        self.preview_audio_selector.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._select_video_preview_audio_track(),
            add="+",
        )
        self.preview_video_status = tk.StringVar(
            value=self._t("Select a download to list its videos.")
        )
        ttk.Label(
            preview,
            textvariable=self.preview_video_status,
            style="Preview.StatusText.TLabel",
            wraplength=260,
            justify="left",
        ).grid(row=7, column=0, sticky="ew", pady=(2, 0))

        self._preview_video_choices = {}
        self._preview_video_refresh_after = None
        self._preview_playback_rate = tk.StringVar(value="1.0x")
        self._preview_audio_tracks = {}
        self._preview_subtitle_track = tk.StringVar(value="Off")
        self._preview_subtitle_tracks = {}
        self._preview_playback_after = None
        self._preview_audio_refresh_ticks = 0
        self._preview_duration_ms = 0
        self._preview_timeline_hover = False
        self._preview_seeking = False
        self.preview_image_label = ttk.Label(
            preview,
            text=self._t("Select a video to preview"),
            style="Preview.Empty.TLabel",
            anchor="center",
            justify="center",
            wraplength=260,
            padding=(16, 22),
        )
        self.preview_image_label.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.preview_video_surface.bind(
            "<Double-Button-1>", lambda _event: self._open_preview_fullscreen(),
        )
        self.preview_video_surface.bind(
            "<Button-1>",
            lambda _event: self.preview_video_surface.focus_set(),
            add="+",
        )
        ttk.Label(
            inspector,
            text=self._t("File attributes"),
            style="Card.TLabel",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(14, 5))
        self.preview_details = ttk.Label(
            inspector,
            text="",
            style="Card.TLabel",
            wraplength=240,
            justify="left",
            padding=(8, 7),
            relief="solid",
            borderwidth=1,
        )
        self.preview_details.grid(row=4, column=0, columnspan=2, sticky="new")
        inspector_actions = ttk.Frame(inspector, style="Card.TFrame")
        inspector_actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for column in range(2):
            inspector_actions.columnconfigure(column, weight=1)
        self._open_smart_vlc_button = ttk.Button(
            inspector_actions,
            text=self._t("Open Smart VLC"),
            command=self.play_selected_media,
            style="Accent.TButton",
        )
        self._open_smart_vlc_button.grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6),
        )
        self._play_in_preview_button = ttk.Button(
            inspector_actions,
            text=self._t("Play in preview"),
            command=self.play_selected_media_in_preview,
        )
        self._play_in_preview_button.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6),
        )
        ttk.Button(
            inspector_actions,
            text=self._t("Open in system player"),
            command=self.open_selected_media_in_system_player,
        ).grid(row=2, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(
            inspector_actions,
            text=self._t("Show file"),
            command=self.open_selected_location,
        ).grid(row=3, column=0, sticky="ew", padx=(0, 3), pady=(6, 0))
        ttk.Button(
            inspector_actions,
            text=self._t("Browse local media"),
            command=self.browse_local_media,
        ).grid(row=2, column=1, sticky="ew", padx=(3, 0))
        ttk.Button(
            inspector_actions,
            text=self._t("Copy link"),
            command=self.copy_selected_link,
        ).grid(row=3, column=1, sticky="ew", padx=(3, 0), pady=(6, 0))
        self.current_thumbnail = None
        ttk.Label(
            inspector,
            text=self._t("Choose an existing file or select a downloaded task."),
            style="SidebarHint.TLabel",
            wraplength=240,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(12, 0))

        controls = ttk.Frame(frame)
        controls.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        for column in range(4):
            controls.columnconfigure(column, weight=1)
        ttk.Button(
            controls, text=self._t("Pause / resume"), command=self.toggle_pause_selected,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4))
        ttk.Button(
            controls, text=self._t("Resume / retry"), command=self.resume_selected,
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=(0, 4))
        ttk.Button(
            controls, text=self._t("Cancel selected"), command=self.cancel_selected,
        ).grid(row=0, column=2, sticky="ew", padx=4, pady=(0, 4))
        ttk.Button(
            controls, text=self._t("Open selected location"), command=self.open_selected_location,
        ).grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self._play_in_app_button = ttk.Button(
            controls, text=self._t("Play in app"), command=self.play_selected_media,
            style="Accent.TButton",
        )
        self._play_in_app_button.grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(
            controls,
            text=self._t("Open in system player"),
            command=self.open_selected_media_in_system_player,
        ).grid(row=1, column=3, sticky="ew", padx=(4, 0))
        ttk.Button(
            controls, text=self._t("Open downloads folder"), command=self.open_download_folder,
        ).grid(row=1, column=2, sticky="ew", padx=4)
        more_button = ttk.Menubutton(controls, text=self._t("History"))
        more_menu = tk.Menu(more_button, tearoff=False)
        self.history_menu = more_menu
        more_menu.add_command(label=self._t("Hide selected"), command=self.hide_selected)
        more_menu.add_command(label=self._t("Restore selected"), command=self.restore_selected)
        more_menu.add_command(label=self._t("Clear finished"), command=self.clear_finished)
        more_menu.add_checkbutton(
            label=self._t("Show hidden"), variable=self.show_hidden, command=self._refresh_history,
        )
        more_menu.add_separator()
        more_menu.add_command(label=self._t("Help"), command=self.show_help)
        more_button.configure(menu=more_menu)
        more_button.grid(row=1, column=3, sticky="ew", padx=(4, 0))

    def _adapt_responsive_layout(self, event=None) -> None:
        if event is not None and event.widget is not self.root:
            return
        width = self.root.winfo_width()
        outer = self._main_outer
        sidebar = self._sidebar_host
        splitter = self._main_splitter
        stacked = width < 1240
        if stacked != self._main_splitter_stacked:
            if stacked:
                splitter.forget(self._main_content_frame)
                splitter.forget(self._media_inspector)
                self._main_content_frame.grid(
                    row=0, column=0, sticky="nsew",
                )
                self._media_inspector.grid(
                    row=1, column=0, sticky="nsew",
                )
                splitter.columnconfigure(0, weight=1)
                splitter.rowconfigure(0, weight=3)
                splitter.rowconfigure(1, weight=1)
            else:
                self._main_content_frame.grid_forget()
                self._media_inspector.grid_forget()
                splitter.add(self._main_content_frame, weight=4)
                splitter.add(self._media_inspector, weight=1)
            self._main_splitter_stacked = stacked

        if (
            not stacked
            and not getattr(self, "_main_splitter_initial_sash_set", False)
            and not getattr(self, "_main_splitter_initial_sash_pending", False)
        ):
            self._main_splitter_initial_sash_pending = True
            self.root.after_idle(self._set_initial_preview_splitter_position)

        if width < 760:
            sidebar.grid_remove()
            splitter.grid_configure(
                row=0, column=0, columnspan=1, padx=16, pady=(16, 0),
            )
            outer.columnconfigure(0, weight=1, minsize=0)
            outer.columnconfigure(1, weight=0, minsize=0)
            outer.columnconfigure(2, weight=0, minsize=0)
            outer.rowconfigure(1, weight=1)
        elif width < 1180:
            sidebar.grid()
            splitter.grid_configure(
                row=0, column=1, columnspan=1, padx=(0, 16), pady=16,
            )
            outer.columnconfigure(0, weight=0, minsize=150)
            outer.columnconfigure(1, weight=1, minsize=360)
            outer.columnconfigure(2, weight=0, minsize=0)
            outer.rowconfigure(1, weight=1)
        else:
            sidebar.grid()
            splitter.grid_configure(
                row=0, column=1, columnspan=2, padx=(0, 16), pady=16,
            )
            outer.columnconfigure(0, weight=0, minsize=190)
            outer.columnconfigure(1, weight=1, minsize=660)
            outer.columnconfigure(2, weight=0, minsize=0)
            outer.rowconfigure(1, weight=0)
        preview_width = (
            240
            if width >= 1180
            else max(180, width - (32 if width < 760 else 182))
        )
        self.preview_image_label.configure(wraplength=preview_width)
        self.preview_details.configure(wraplength=preview_width)
        placeholder = getattr(self, "preview_video_placeholder", None)
        if placeholder is not None:
            placeholder.configure(wraplength=max(140, preview_width - 20))

    def _set_initial_preview_splitter_position(self) -> None:
        self._main_splitter_initial_sash_pending = False
        if self._main_splitter_stacked:
            return
        splitter = self._main_splitter
        width = splitter.winfo_width()
        if width < 600:
            self._main_splitter_initial_sash_pending = True
            self.root.after(50, self._set_initial_preview_splitter_position)
            return
        self._main_splitter_initial_sash_set = True
        preview_pane_width = min(396, max(0, width - 600))
        splitter.sashpos(0, max(0, width - preview_pane_width))

    def _resize_sidebar_content(self, event) -> None:
        self.sidebar_canvas.itemconfigure(self.sidebar_window, width=event.width)

    def _update_sidebar_scroll_region(self, _event=None) -> None:
        canvas = self.sidebar_canvas
        canvas.configure(scrollregion=canvas.bbox("all"))
        bounds = canvas.bbox("all")
        if bounds and bounds[3] - bounds[1] > canvas.winfo_height():
            self.sidebar_scrollbar.grid()
        else:
            self.sidebar_scrollbar.grid_remove()

    def _scroll_sidebar(self, event):
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        canvas_name = str(self.sidebar_canvas)
        if widget is None or (
            widget != self.sidebar_canvas
            and not str(widget).startswith(f"{canvas_name}.")
        ):
            return None

        if getattr(event, "num", None) == 4:
            scroll_units = -1
        elif getattr(event, "num", None) == 5:
            scroll_units = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return None
            scroll_units = -max(1, round(abs(delta) / 120)) if delta > 0 else max(
                1, round(abs(delta) / 120)
            )
        self.sidebar_canvas.yview_scroll(scroll_units, "units")
        return "break"

    def _build_settings_ui(self) -> None:
        container = ttk.Frame(self.settings_window, padding=14)
        container.pack(fill="both", expand=True)
        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        general = ttk.Frame(notebook, padding=16)
        general.columnconfigure(1, weight=1)
        notebook.add(general, text=self._t("General"))
        ttk.Label(general, text=self._t("Language")).grid(
            row=0, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            general,
            textvariable=self.language,
            values=tuple(LANGUAGES),
            state="readonly",
            width=18,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=7)
        self.language.trace_add("write", self._save_language_preference)
        ttk.Separator(general).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Label(general, text=self._t("Accessibility")).grid(
            row=2, column=0, sticky="w", pady=7
        )
        ttk.Checkbutton(
            general,
            text=self._t("Use larger text"),
            variable=self.large_text,
            command=self._save_accessibility_preferences,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=5)
        ttk.Checkbutton(
            general,
            text=self._t("High contrast"),
            variable=self.high_contrast,
            command=self._save_accessibility_preferences,
        ).grid(row=3, column=1, sticky="w", padx=10, pady=5)
        ttk.Label(
            general,
            text=self._keyboard_shortcuts_summary_text(),
            wraplength=580,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 14))
        ttk.Separator(general).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=8
        )
        ttk.Checkbutton(
            general,
            text=self._t("Check for updates at startup"),
            variable=self.check_updates,
            command=self._save_update_preference,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Button(
            general,
            text=self._t("Check for updates now"),
            command=lambda: self._check_for_updates(interactive=True),
        ).grid(row=7, column=0, sticky="w", pady=5)
        ttk.Separator(general).grid(
            row=8, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Checkbutton(
            general,
            text=self._t("Record local diagnostic events"),
            variable=self.diagnostics_enabled,
            command=self._save_diagnostics_preference,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(
            general,
            text="Off by default. When enabled, only event time, component, and error type are stored locally. Nothing is sent automatically.",
            wraplength=580,
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Button(
            general,
            text=self._t("Export local diagnostics…"),
            command=self._export_local_diagnostics,
        ).grid(row=11, column=0, sticky="w", pady=5)
        ttk.Separator(general).grid(
            row=12, column=0, columnspan=2, sticky="ew", pady=10
        )
        ttk.Label(general, text=self._t("Maintenance & Data")).grid(
            row=13, column=0, sticky="w", pady=4
        )
        maintenance_frame = ttk.Frame(general)
        maintenance_frame.grid(row=14, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Button(
            maintenance_frame,
            text=self._t("Update yt-dlp library now"),
            command=self._update_ytdlp_action,
            style="Accent.TButton",
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            maintenance_frame,
            text=self._t("Export download history to CSV…"),
            command=self._export_history_csv,
        ).pack(side="left")

        transfer = ttk.Frame(notebook, padding=16)
        transfer.columnconfigure(1, weight=1)
        notebook.add(transfer, text=self._t("Speed & checks"))
        ttk.Label(transfer, text=self._t("Download speed")).grid(row=0, column=0, sticky="w", pady=7)
        ttk.Combobox(
            transfer, textvariable=self.speed_mode,
            values=("Balanced", "Fast", "Maximum"), state="readonly", width=18,
        ).grid(row=0, column=1, sticky="w", padx=10, pady=7)
        ttk.Label(transfer, text=self._t("Limit for this download")).grid(
            row=1, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            transfer, textvariable=self.max_speed, values=tuple(MAX_SPEEDS),
            state="readonly", width=18,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=7)
        ttk.Label(transfer, text=self._t("Shared limit for all downloads")).grid(
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
        ttk.Label(transfer, text=self._t("Verify downloaded file")).grid(
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

        media_tab = ttk.Frame(notebook, padding=16)
        media_tab.columnconfigure(1, weight=1)
        notebook.add(media_tab, text=self._t("Audio & Subtitles"))

        ttk.Label(media_tab, text=self._t("Preferred audio tracks"), font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Label(media_tab, text=self._t("Audio language")).grid(
            row=1, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            media_tab,
            textvariable=self.audio_languages,
            values=("All languages", "English only", "Hindi only", "English + Hindi", "Original only"),
            state="readonly",
            width=20,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=7)
        self.audio_languages.trace_add("write", lambda *_: self._save_media_preferences())
        ttk.Label(
            media_tab,
            text=self._t("Choose which audio tracks to download. Selecting specific languages downloads smaller files faster and keeps the voice you prefer."),
            wraplength=540,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Separator(media_tab).grid(row=3, column=0, columnspan=2, sticky="ew", pady=8)

        ttk.Label(media_tab, text=self._t("Subtitles (.srt)"), font=("Segoe UI", 10, "bold")).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        ttk.Checkbutton(
            media_tab,
            text=self._t("Download subtitles with videos"),
            variable=self.download_subtitles,
            command=self._save_media_preferences,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=5)

        ttk.Label(media_tab, text=self._t("Subtitle languages")).grid(
            row=6, column=0, sticky="w", pady=7
        )
        ttk.Entry(media_tab, textvariable=self.subtitle_languages, width=22).grid(
            row=6, column=1, sticky="w", padx=10, pady=7
        )
        self.subtitle_languages.trace_add("write", lambda *_: self._save_media_preferences())
        ttk.Label(
            media_tab,
            text=self._t("Comma-separated language codes (e.g., 'en,hi' for English and Hindi). Subtitles are saved as standard .srt files."),
            wraplength=540,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 8))

        connection = ttk.Frame(notebook, padding=16)
        connection.columnconfigure(1, weight=1)
        notebook.add(connection, text=self._t("Connection"))
        ttk.Label(connection, text=self._t("Proxy (optional)")).grid(
            row=0, column=0, sticky="w", pady=7
        )
        ttk.Entry(connection, textvariable=self.proxy_list).grid(
            row=0, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Label(
            connection, text="HTTP or SOCKS5 address; comma-separate proxies. For geo retry, label exits once: US=http://proxy:8080,GB=socks5h://proxy:1080.",
            wraplength=540,
        ).grid(row=1, column=1, sticky="w", padx=10, pady=(0, 10))
        ttk.Label(connection, text=self._t("Browser cookies")).grid(
            row=2, column=0, sticky="w", pady=7
        )
        ttk.Combobox(
            connection, textvariable=self.browser_cookies,
            values=("None", "Chrome", "Firefox", "Edge", "Brave"),
            state="readonly", width=18,
        ).grid(row=2, column=1, sticky="w", padx=10, pady=7)
        ttk.Label(connection, text="Geo-bypass country code (optional)").grid(
            row=3, column=0, sticky="w", pady=7
        )
        ttk.Entry(connection, textvariable=self.geo_bypass_country, width=10).grid(
            row=3, column=1, sticky="w", padx=10, pady=7
        )
        self.geo_bypass_country.trace_add(
            "write", lambda *_: self._save_geo_bypass_country()
        )
        ttk.Label(
            connection,
            text="Two-letter ISO code (for example US or GB). This sends yt-dlp's geo hint; a regional proxy may still be needed.",
            wraplength=540,
        ).grid(row=4, column=1, sticky="w", padx=10, pady=(0, 8))
        ttk.Label(connection, text=self._t("Custom HTTP headers")).grid(
            row=5, column=0, sticky="nw", pady=7
        )
        header_frame = ttk.Frame(connection)
        header_frame.grid(row=5, column=1, sticky="ew", padx=10, pady=7)
        header_frame.columnconfigure(0, weight=1)
        self.custom_headers_text = tk.Text(
            header_frame, height=4, wrap="none", undo=True,
        )
        self.custom_headers_text.grid(row=0, column=0, sticky="ew")
        header_scrollbar = ttk.Scrollbar(
            header_frame, orient="vertical", command=self.custom_headers_text.yview,
        )
        header_scrollbar.grid(row=0, column=1, sticky="ns")
        self.custom_headers_text.configure(yscrollcommand=header_scrollbar.set)
        ttk.Label(
            connection,
            text="One Name: value header per line. Headers may be sent to redirected hosts.",
            wraplength=540,
        ).grid(row=6, column=1, sticky="w", padx=10, pady=(0, 8))
        ttk.Label(connection, text=self._t("Retry attempts")).grid(
            row=7, column=0, sticky="w", pady=7
        )
        retry_controls = ttk.Frame(connection)
        retry_controls.grid(row=7, column=1, sticky="ew", padx=10, pady=7)
        ttk.Spinbox(
            retry_controls, from_=1, to=20, textvariable=self.retry_attempts, width=6,
        ).pack(side="left")
        ttk.Label(retry_controls, text="Base delay (sec)").pack(
            side="left", padx=(12, 4)
        )
        ttk.Entry(
            retry_controls, textvariable=self.retry_base_delay, width=7,
        ).pack(side="left")
        ttk.Label(retry_controls, text="Maximum").pack(side="left", padx=(12, 4))
        ttk.Entry(
            retry_controls, textvariable=self.retry_max_delay, width=7,
        ).pack(side="left")
        ttk.Label(
            connection,
            text="Exponential backoff; attempts 1-20, base delay 0-60 seconds, maximum at most 300.",
            wraplength=540,
        ).grid(row=8, column=1, sticky="w", padx=10, pady=(0, 8))
        ttk.Label(connection, text=self._t("Parallel downloads")).grid(
            row=9, column=0, sticky="w", pady=7
        )
        parallel_spinbox = ttk.Spinbox(
            connection, from_=1, to=10, textvariable=self.max_parallel_downloads,
            width=6, command=self._save_parallel_downloads,
        )
        parallel_spinbox.grid(row=9, column=1, sticky="w", padx=10, pady=7)
        parallel_spinbox.bind("<FocusOut>", self._normalize_parallel_downloads)
        parallel_spinbox.bind("<Return>", self._normalize_parallel_downloads)
        if not getattr(self, "_parallel_downloads_trace_added", False):
            self.max_parallel_downloads.trace_add(
                "write", self._save_parallel_downloads
            )
            self._parallel_downloads_trace_added = True
        ttk.Label(
            connection,
            text="How many downloads run at the same time (1-10). Extra links wait in the queue; paused downloads free their place.",
            wraplength=540,
        ).grid(row=10, column=1, sticky="w", padx=10, pady=(0, 8))

        automation = ttk.Frame(notebook, padding=16)
        automation.columnconfigure(1, weight=1)
        notebook.add(automation, text=self._t("Schedule & files"))
        ttk.Label(automation, text=self._t("Start at (local time)")).grid(
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
        ttk.Checkbutton(
            automation, text=self._t("Shutdown PC when all downloads in queue finish"),
            variable=self.shutdown_on_complete, command=self._save_shutdown_preference,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=7)
        ttk.Separator(automation).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=12
        )
        ttk.Label(automation, text=self._t("Save to cloud")).grid(
            row=6, column=0, sticky="w", pady=7
        )
        cloud_controls = ttk.Frame(automation)
        cloud_controls.grid(row=6, column=1, sticky="ew", padx=10, pady=7)
        ttk.Combobox(
            cloud_controls, textvariable=self.cloud_provider,
            values=("Local folder", "Amazon S3", "Google Drive", "Dropbox"),
            state="readonly", width=18,
        ).pack(side="left")
        ttk.Button(
            cloud_controls, text="Account setup", command=self._configure_cloud_account,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(automation, text="Remote folder / prefix").grid(
            row=7, column=0, sticky="w", pady=7
        )
        ttk.Entry(automation, textvariable=self.cloud_folder).grid(
            row=7, column=1, sticky="ew", padx=10, pady=7
        )
        ttk.Label(
            automation, text="Cloud downloads use a temporary local staging folder.",
        ).grid(row=8, column=1, sticky="w", padx=10, pady=(0, 6))
        self.cloud_provider.trace_add("write", self._save_cloud_preferences)
        self.cloud_folder.trace_add("write", self._save_cloud_preferences)
        self._update_destination_mode()
