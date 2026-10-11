from __future__ import annotations

from app_support import (
    tk,
    ttk,
    MAX_SPEEDS,
)

class UiMixin:
    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)
        sidebar_host = ttk.Frame(outer, style="Sidebar.TFrame")
        sidebar_host.grid(row=0, column=0, sticky="nsew")
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
            header, text="Smart Downloader 12.0", style="Card.TLabel",
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
        ttk.Button(add_buttons, text="Batch", command=self.open_batch_dialog).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(add_buttons, text="Sequence", command=self.open_sequence_dialog).pack(
            side="left", padx=(6, 0)
        )
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
        ttk.Label(footer, text="Smart Downloader 12.0").grid(row=1, column=0, sticky="w")
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

    def _build_remaining_ui(self, frame: ttk.Frame) -> None:
        options = ttk.Frame(frame, style="Card.TFrame", padding=(12, 10))
        options.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for column in range(4):
            options.columnconfigure(column, weight=1)
        quick_options = (
            ("Source", self.source, ("Auto", "Direct file", "Supported site", "Torrent/magnet")),
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
