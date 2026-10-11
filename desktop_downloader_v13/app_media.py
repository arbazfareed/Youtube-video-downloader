from __future__ import annotations

from app_support import (
    os,
    shutil,
    subprocess,
    sys,
    tk,
    Callable,
    Future,
    Path,
    filedialog,
    messagebox,
    ttk,
    urlsplit,
    RequestException,
    convert_docx_to_pdf,
    convert_pdf_to_docx,
    _ffmpeg_directory,
    extract_archive,
    convert_image,
    resize_image,
    scrape_image_urls,
    strip_exif,
    PLAYABLE_MEDIA_EXTENSIONS,
    VIDEO_MEDIA_EXTENSIONS,
    AUDIO_MEDIA_EXTENSIONS,
    _convert_media_to_mp3,
    create_zip_archive,
    parse_custom_headers,
    calculate_checksum,
)

_VLC_DLL_DIRECTORY = None


class MediaMixin:
    def _integrity_guard(self, job_id: str) -> bool:
        baseline = getattr(self, "_integrity_baselines", {}).get(job_id)
        if baseline is None:
            return True
        path, expected_digest = baseline
        try:
            actual_digest = calculate_checksum(path, "sha256")
        except OSError as error:
            messagebox.showerror(
                "Integrity check failed",
                f"The downloaded file is missing or unreadable:\n{path}\n\n{error}",
                parent=self.root,
            )
            return False
        if actual_digest.casefold() != expected_digest.casefold():
            messagebox.showerror(
                "File changed after download",
                f"SHA-256 verification failed for:\n{path}\n\n"
                f"Expected: {expected_digest}\nActual: {actual_digest}\n\n"
                "The file was not opened or extracted.",
                parent=self.root,
            )
            return False
        return True

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
        try:
            headers = parse_custom_headers(
                self.custom_headers_text.get("1.0", "end-1c").splitlines()
                if hasattr(self, "custom_headers_text")
                else ()
            )
        except ValueError as error:
            messagebox.showerror("Invalid HTTP headers", str(error), parent=self.root)
            return
        self.progress_summary.set("Scanning the page for image links…")
        future = self.executor.submit(scrape_image_urls, page_url, headers=headers)

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
        menu.add_command(
            label="Open selected file or folder",
            command=self.open_selected_location,
        )
        menu.add_command(
            label="Play selected audio/video",
            command=self.play_selected_media,
        )
        menu.add_command(
            label="Open in system player",
            command=self.open_selected_media_in_system_player,
        )
        menu.add_command(label="Resume / retry", command=self.resume_selected)
        menu.add_command(
            label="Extract selected archive",
            command=self.extract_selected_archive,
        )
        menu.add_separator()
        path = self._selected_output_path()
        if (
            path is not None
            and path.is_file()
            and path.suffix.lower() in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
        ):
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
        menu.add_command(
            label="Resize image…",
            command=lambda: self._resize_selected_image(path),
        )

    def open_selected_image_tools(self) -> None:
        selected = self.jobs.selection()
        if selected and not self._integrity_guard(selected[0]):
            return
        path = self._selected_output_path()
        if (
            path is None
            or not path.is_file()
            or path.suffix.lower()
            not in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
        ):
            image_name = filedialog.askopenfilename(
                parent=self.root,
                title="Choose an image to edit",
                filetypes=(
                    ("Images", "*.avif *.gif *.jpeg *.jpg *.png *.webp"),
                    ("All files", "*.*"),
                ),
            )
            if not image_name:
                return
            path = Path(image_name)
            if path.suffix.lower() not in {
                ".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp",
            }:
                messagebox.showerror(
                    "Unsupported image",
                    "Choose an AVIF, GIF, JPEG, PNG, or WebP image.",
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
        selected = self.jobs.selection()
        if selected and not self._integrity_guard(selected[0]):
            return
        path = self._selected_output_path()
        if path is None or not path.is_file():
            messagebox.showinfo(
                "Select a downloaded archive",
                "Select a completed ZIP, RAR, or TAR archive in the queue.",
                parent=self.root,
            )
            return
        if path.suffix.lower() not in {
            ".zip", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz",
        }:
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

    def extract_local_archive(self) -> None:
        archive_name = filedialog.askopenfilename(
            parent=self.root,
            title="Choose an archive to extract",
            filetypes=(
                (
                    "Supported archives",
                    "*.zip *.rar *.tar *.tgz *.tar.gz *.tar.bz2 *.tar.xz",
                ),
                ("All files", "*.*"),
            ),
        )
        if not archive_name:
            return
        archive_path = Path(archive_name)
        self._run_local_file_action(
            lambda: extract_archive(archive_path),
            "Extract archive",
            parent=archive_path.parent,
        )

    def create_zip_from_file(self) -> None:
        source_name = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a file to add to a ZIP archive",
            filetypes=(("All files", "*.*"),),
        )
        if source_name:
            self._save_zip_archive(Path(source_name))

    def create_zip_from_folder(self) -> None:
        source_name = filedialog.askdirectory(
            parent=self.root,
            title="Choose a folder to add to a ZIP archive",
            mustexist=True,
        )
        if source_name:
            self._save_zip_archive(Path(source_name))

    def _save_zip_archive(self, source: Path) -> None:
        default_name = f"{source.stem if source.is_file() else source.name}.zip"
        destination_name = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save ZIP archive",
            initialdir=str(source.parent),
            initialfile=default_name,
            defaultextension=".zip",
            filetypes=(("ZIP archives", "*.zip"),),
            confirmoverwrite=True,
        )
        if not destination_name:
            return
        destination = Path(destination_name)
        if destination.suffix.lower() != ".zip":
            messagebox.showerror(
                "Choose a ZIP filename",
                "The output filename must end in .zip.",
                parent=self.root,
            )
            return
        self._run_local_file_action(
            lambda: create_zip_archive(source, destination, overwrite=True),
            "Create ZIP archive",
            parent=destination.parent,
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
                messagebox.showinfo(
                    title,
                    "This file type is not a supported archive.",
                    parent=self.root,
                )
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
        path = self._selected_media_path()
        if path is None:
            return
        try:
            self._play_media_in_app(path)
        except (AttributeError, ImportError, OSError, RuntimeError) as error:
            if messagebox.askyesno(
                self._t("In-app playback unavailable"),
                self._t("VLC is required for in-app playback. Open this file in your system player instead?")
                + f"\n\n{error}",
                parent=self.root,
            ):
                self.open_media_in_system_player(path)

    def _selected_media_path(self) -> Path | None:
        path = getattr(self, "_local_media_path", None)
        selected = self.jobs.selection()
        if path is None and selected:
            if not self._integrity_guard(selected[0]):
                return None
            path = self._selected_output_path()
        if path is None or not path.is_file():
            path = self._choose_local_media()
            if path is None:
                return None
        if path.suffix.lower() not in PLAYABLE_MEDIA_EXTENSIONS:
            messagebox.showinfo(
                self._t("Unsupported media"),
                self._t("The selected file is not a recognized audio or video format."),
                parent=self.root,
            )
            return None
        return path

    def _play_media_in_app(self, path: Path) -> None:
        import importlib

        self._prepare_bundled_vlc_runtime()
        vlc = importlib.import_module("vlc")
        if getattr(self, "_in_app_player_window", None) is not None:
            self._close_in_app_player()

        window = tk.Toplevel(self.root)
        window.title(f"Smart VLC — {path.name}")
        window.geometry("960x640")
        window.minsize(640, 420)
        window.configure(background="#101318")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        window.protocol("WM_DELETE_WINDOW", self._close_in_app_player)
        window.bind("<F11>", self._toggle_in_app_fullscreen, add="+")
        window.bind("<Escape>", self._exit_in_app_fullscreen, add="+")
        self._in_app_player_window = window
        self._in_app_media_title = path.name

        header = ttk.Frame(window, style="Card.TFrame", padding=(10, 6))
        header.grid(row=0, column=0, sticky="ew")
        self._in_app_player_status = tk.StringVar(value=self._t("Playback started"))
        ttk.Label(
            header,
            text=(
                f"{self._t('Now playing')}: "
                f"{self._compact_in_app_title(path.name)}"
            ),
            style="Card.TLabel",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(
            header,
            textvariable=self._in_app_player_status,
            style="SidebarHint.TLabel",
            anchor="e",
        ).pack(side="right", padx=(10, 0))
        video_surface = tk.Frame(window, background="#000000")
        video_surface.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)

        controls = ttk.Frame(window, style="Card.TFrame", padding=(6, 4))
        controls.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 6))
        for column in range(3):
            controls.columnconfigure(column, weight=1)
        timeline = ttk.Frame(controls, style="Card.TFrame")
        timeline.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        timeline.columnconfigure(1, weight=1)
        self._in_app_position_var = tk.DoubleVar(value=0)
        self._in_app_current_time = tk.StringVar(value="00:00")
        self._in_app_duration = tk.StringVar(value="00:00")
        ttk.Label(timeline, textvariable=self._in_app_current_time, width=6).grid(
            row=0, column=0, padx=(0, 8)
        )
        self._in_app_seek_scale = ttk.Scale(
            timeline,
            from_=0,
            to=100,
            variable=self._in_app_position_var,
            takefocus=True,
            state="disabled",
        )
        self._in_app_seek_scale.grid(row=0, column=1, sticky="ew")
        self._in_app_seek_scale.bind(
            "<ButtonPress-1>", self._begin_in_app_seek, add="+"
        )
        self._in_app_seek_scale.bind(
            "<ButtonRelease-1>", self._seek_in_app_player, add="+"
        )
        ttk.Label(timeline, textvariable=self._in_app_duration, width=6).grid(
            row=0, column=2, padx=(8, 0)
        )

        transport_controls = ttk.Frame(controls, style="Card.TFrame")
        transport_controls.grid(row=1, column=0, columnspan=3, sticky="ew")
        playback_button = ttk.Button(
            transport_controls, text="Ⅱ", width=3, padding=(2, 2), takefocus=True
        )
        playback_button.pack(side="left")
        stop_button = ttk.Button(
            transport_controls,
            text="■",
            command=self._stop_in_app_player,
            width=3,
            padding=(2, 2),
            takefocus=True,
        )
        stop_button.pack(side="left", padx=(4, 0))
        fullscreen_button = ttk.Button(
            transport_controls,
            text="⛶",
            command=self._toggle_in_app_fullscreen,
            width=3,
            padding=(2, 2),
            takefocus=True,
        )
        fullscreen_button.pack(side="left", padx=(4, 0))
        close_button = ttk.Button(
            transport_controls,
            text="×",
            command=self._close_in_app_player,
            width=3,
            padding=(2, 2),
            takefocus=True,
        )
        close_button.pack(side="right")

        volume_controls = ttk.Frame(controls, style="Card.TFrame")
        volume_controls.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        volume_controls.columnconfigure(2, weight=1)
        volume_icon = ttk.Label(volume_controls, text="◖))")
        volume_icon.pack(side="left", padx=(0, 4))
        volume = tk.IntVar(value=80)
        self._in_app_volume_var = volume
        self._in_app_volume_label = tk.StringVar(value="80%")
        volume_value_label = ttk.Label(
            volume_controls,
            textvariable=self._in_app_volume_label,
            width=5,
            anchor="e",
        )
        volume_value_label.pack(side="left", padx=(0, 5))
        volume_scale = ttk.Scale(
            volume_controls,
            from_=0,
            to=100,
            variable=volume,
            command=lambda value: self._set_in_app_volume(value),
            takefocus=True,
        )
        volume_scale.pack(side="left", fill="x", expand=True)

        track_controls = ttk.Frame(controls, style="Card.TFrame")
        track_controls.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(3, 0))
        track_controls.columnconfigure(1, weight=1)
        audio_icon = ttk.Label(track_controls, text="♫")
        audio_icon.pack(side="left", padx=(0, 4))
        self._in_app_audio_track = tk.StringVar(value="")
        self._in_app_audio_tracks: dict[str, int] = {}
        self._in_app_audio_tracks_loaded = False
        self._in_app_audio_track_combo = ttk.Combobox(
            track_controls,
            textvariable=self._in_app_audio_track,
            state="disabled",
            width=14,
            takefocus=True,
        )
        self._in_app_audio_track_combo.pack(side="left", fill="x", expand=True)
        self._in_app_audio_track_combo.bind(
            "<<ComboboxSelected>>", self._select_in_app_audio_track
        )
        footer_help_button = ttk.Button(
            controls,
            text="?",
            command=self._show_in_app_player_help,
            width=3,
            padding=(2, 2),
            takefocus=True,
        )
        footer_help_button.grid(row=2, column=2, sticky="e", padx=(8, 0), pady=(3, 0))
        window.update_idletasks()

        self._in_app_vlc = vlc
        self._in_app_fullscreen_button = fullscreen_button
        self._in_app_player_status_text = self._t("Playback started")
        for widget, hint in (
            (playback_button, "Pause"),
            (stop_button, "Stop"),
            (fullscreen_button, "Full screen"),
            (close_button, "Close player"),
            (volume_icon, "Volume"),
            (volume_value_label, "Volume"),
            (volume_scale, "Volume"),
            (audio_icon, "Audio track"),
            (self._in_app_audio_track_combo, "Audio track"),
            (footer_help_button, "Help"),
        ):
            self._bind_in_app_control_hint(widget, self._t(hint))
        self._in_app_fullscreen = False
        self._in_app_audio_refresh_ticks = 0
        self._in_app_playback_after = None
        self._in_app_seeking = False
        try:
            instance = vlc.Instance()
            self._in_app_vlc_instance = instance
            player = instance.media_player_new()
            self._in_app_player = player
            player.set_media(instance.media_new(str(path)))
            self._in_app_video_surface = video_surface
            self._set_in_app_video_target(video_surface)
            playback_button.configure(command=self._toggle_in_app_playback)
            self._in_app_playback_button = playback_button
            window.lift()
            player.audio_set_volume(volume.get())
            if player.play() == -1:
                raise RuntimeError(self._t("VLC could not start playback."))
        except Exception:
            self._close_in_app_player()
            raise
        self._refresh_in_app_audio_tracks()
        self._poll_in_app_playback()

    def _prepare_bundled_vlc_runtime(self) -> None:
        global _VLC_DLL_DIRECTORY

        if sys.platform != "win32":
            return
        app_directory = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
        vlc_directory = app_directory / "VLC"
        plugin_directory = vlc_directory / "plugins"
        libvlc_path = vlc_directory / "libvlc.dll"
        if not libvlc_path.is_file() or not plugin_directory.is_dir():
            return

        os.environ["PYTHON_VLC_LIB_PATH"] = str(libvlc_path)
        os.environ["PYTHON_VLC_MODULE_PATH"] = str(plugin_directory)
        os.environ["VLC_PLUGIN_PATH"] = str(plugin_directory)
        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        normalized_vlc_directory = os.path.normcase(str(vlc_directory))
        if normalized_vlc_directory not in {
            os.path.normcase(entry) for entry in path_entries
        }:
            os.environ["PATH"] = str(vlc_directory) + os.pathsep + os.environ.get(
                "PATH", ""
            )
        if _VLC_DLL_DIRECTORY is None and hasattr(os, "add_dll_directory"):
            _VLC_DLL_DIRECTORY = os.add_dll_directory(str(vlc_directory))

    @staticmethod
    def _compact_in_app_title(title: str, max_length: int = 72) -> str:
        if len(title) <= max_length:
            return title
        return f"{title[:max_length - 3]}..."

    def _poll_in_app_playback(self) -> None:
        player = getattr(self, "_in_app_player", None)
        window = getattr(self, "_in_app_player_window", None)
        if player is None or window is None:
            return
        vlc = self._in_app_vlc
        state = player.get_state()
        duration = max(0, player.get_length())
        current_time = max(0, player.get_time())
        self._in_app_duration.set(self._format_in_app_time(duration))
        self._in_app_current_time.set(self._format_in_app_time(current_time))
        seek_scale = getattr(self, "_in_app_seek_scale", None)
        if seek_scale is not None:
            seekable = duration > 0 and player.is_seekable()
            seek_scale.configure(state="normal" if seekable else "disabled")
            if seekable and not getattr(self, "_in_app_seeking", False):
                self._in_app_position_var.set(
                    min(100, current_time * 100 / duration)
                )
        self._in_app_audio_refresh_ticks = (
            getattr(self, "_in_app_audio_refresh_ticks", 0) + 1
        )
        if self._in_app_audio_refresh_ticks % 4 == 0:
            self._refresh_in_app_audio_tracks()
        if state == vlc.State.Ended:
            self._in_app_playback_button.configure(text="▶")
            self._set_in_app_player_status(self._t("Playback finished"))
            return
        if state == vlc.State.Error:
            self._in_app_playback_button.configure(text="▶")
            self._set_in_app_player_status(self._t("Playback failed"))
            messagebox.showerror(
                self._t("Could not play media"),
                self._t("VLC could not play this media file."),
                parent=window,
            )
            return
        self._in_app_playback_after = self.root.after(250, self._poll_in_app_playback)

    @staticmethod
    def _format_in_app_time(milliseconds: int) -> str:
        total_seconds = max(0, milliseconds // 1000)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

    def _begin_in_app_seek(self, _event=None) -> None:
        self._in_app_seeking = True

    def _seek_in_app_player(self, _event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is not None:
            duration = max(0, player.get_length())
            if duration > 0 and player.is_seekable():
                position = max(0.0, min(100.0, float(self._in_app_position_var.get())))
                player.set_time(round(duration * position / 100))
        self._in_app_seeking = False

    def _toggle_in_app_playback(self) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is None:
            return
        if player.is_playing():
            player.pause()
            label = self._t("Play")
            status = self._t("Playback paused")
        else:
            player.play()
            label = self._t("Pause")
            status = self._t("Playback started")
        button = getattr(self, "_in_app_playback_button", None)
        if button is not None:
            button.configure(text="▶" if label == self._t("Play") else "Ⅱ")
        self._set_in_app_player_status(status)

    def _set_in_app_player_status(self, text: str) -> None:
        self._in_app_player_status_text = text
        status = getattr(self, "_in_app_player_status", None)
        if status is not None:
            status.set(text)

    def _bind_in_app_control_hint(self, widget, text: str) -> None:
        widget.bind(
            "<Enter>",
            lambda _event: self._show_in_app_control_hint(text),
            add="+",
        )
        widget.bind(
            "<Leave>",
            lambda _event: self._restore_in_app_player_status(),
            add="+",
        )
        widget.bind(
            "<FocusIn>",
            lambda _event: self._show_in_app_control_hint(text),
            add="+",
        )
        widget.bind(
            "<FocusOut>",
            lambda _event: self._restore_in_app_player_status(),
            add="+",
        )

    def _show_in_app_control_hint(self, text: str) -> None:
        status = getattr(self, "_in_app_player_status", None)
        if status is not None:
            status.set(text)

    def _restore_in_app_player_status(self) -> None:
        status = getattr(self, "_in_app_player_status", None)
        if status is not None:
            status_text = getattr(self, "_in_app_player_status_text", None)
            if status_text is None:
                status_text = self._t("Playback started")
            status.set(status_text)

    def _set_in_app_video_target(self, surface) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is None:
            return
        surface.update_idletasks()
        handle = surface.winfo_id()
        if sys.platform == "win32":
            player.set_hwnd(handle)
        elif sys.platform == "darwin":
            player.set_nsobject(handle)
        else:
            player.set_xwindow(handle)

    def _set_in_app_volume(self, value: str) -> None:
        player = getattr(self, "_in_app_player", None)
        volume = max(0, min(100, round(float(value))))
        volume_label = getattr(self, "_in_app_volume_label", None)
        if volume_label is not None:
            volume_label.set(f"{volume}%")
        volume_var = getattr(self, "_in_app_volume_var", None)
        if volume_var is not None and round(float(value)) != volume:
            volume_var.set(volume)
        if player is not None:
            player.audio_set_volume(volume)

    def _refresh_in_app_audio_tracks(self) -> None:
        player = getattr(self, "_in_app_player", None)
        combo = getattr(self, "_in_app_audio_track_combo", None)
        variable = getattr(self, "_in_app_audio_track", None)
        if player is None or combo is None or variable is None:
            return

        descriptions = player.audio_get_track_description() or []
        track_labels: dict[str, int] = {}
        for track_id, description in descriptions:
            if isinstance(description, bytes):
                name = description.decode("utf-8", errors="replace")
            else:
                name = str(description)
            label = name or self._t("Audio track")
            if label in track_labels:
                label = f"{label} ({track_id})"
            track_labels[label] = int(track_id)

        if (
            track_labels == getattr(self, "_in_app_audio_tracks", {})
            and getattr(self, "_in_app_audio_tracks_loaded", False)
        ):
            return
        self._in_app_audio_tracks = track_labels
        self._in_app_audio_tracks_loaded = True
        combos = (
            getattr(self, "_in_app_audio_track_combo", None),
        )
        if not track_labels:
            variable.set(self._t("No audio tracks available"))
            for track_combo in combos:
                if track_combo is not None:
                    track_combo.configure(values=(), state="disabled")
            return

        for track_combo in combos:
            if track_combo is not None:
                track_combo.configure(values=tuple(track_labels), state="readonly")
        active_track = player.audio_get_track()
        selected = next(
            (
                label
                for label, track_id in track_labels.items()
                if track_id == active_track
            ),
            next(iter(track_labels)),
        )
        variable.set(selected)

    def _select_in_app_audio_track(self, _event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        variable = getattr(self, "_in_app_audio_track", None)
        if player is None or variable is None:
            return
        track_id = (getattr(self, "_in_app_audio_tracks", None) or {}).get(
            variable.get()
        )
        if track_id is None:
            return
        if player.audio_set_track(track_id) == -1:
            messagebox.showerror(
                self._t("Audio track unavailable"),
                self._t("VLC could not select this audio track."),
                parent=self._in_app_player_window,
            )

    def _toggle_in_app_fullscreen(self, _event=None) -> str:
        window = getattr(self, "_in_app_player_window", None)
        if window is None:
            return "break"
        if getattr(self, "_in_app_fullscreen", False):
            self._exit_in_app_fullscreen()
            return "break"

        window.attributes("-fullscreen", True)
        window.lift()
        self._in_app_fullscreen = True
        self._in_app_fullscreen_button.configure(text="⛶")
        return "break"

    def _exit_in_app_fullscreen(self, _event=None) -> str:
        if not getattr(self, "_in_app_fullscreen", False):
            return "break"
        window = getattr(self, "_in_app_player_window", None)
        self._in_app_fullscreen = False
        if window is not None:
            window.attributes("-fullscreen", False)
        button = getattr(self, "_in_app_fullscreen_button", None)
        if button is not None:
            button.configure(text="⛶")
        return "break"

    def _show_in_app_player_help(self) -> None:
        messagebox.showinfo(
            self._t("Media player help"),
            self._t(
                "Playback opens in a separate Smart VLC window, so the downloader "
                "preview remains available. Use Full screen or F11 to expand the "
                "player without changing the main app window. Press Escape or F11 "
                "to return to windowed playback. Use the timeline to seek, and "
                "the controls to pause, stop, change volume, or select an audio "
                "track. Close player to stop playback and close the player window."
            ),
            parent=self.root,
        )

    def _stop_in_app_player(self) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is not None:
            player.stop()
        playback_button = getattr(self, "_in_app_playback_button", None)
        if playback_button is not None:
            playback_button.configure(text="▶")
        status = getattr(self, "_in_app_player_status", None)
        if status is not None:
            self._set_in_app_player_status(self._t("Playback stopped"))

    def _close_in_app_player(self) -> None:
        window = getattr(self, "_in_app_player_window", None)
        if window is not None:
            if getattr(self, "_in_app_fullscreen", False):
                self._exit_in_app_fullscreen()
            after_id = getattr(self, "_in_app_playback_after", None)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
        player = getattr(self, "_in_app_player", None)
        if player is not None:
            player.stop()
            player.release()
        instance = getattr(self, "_in_app_vlc_instance", None)
        if instance is not None:
            instance.release()
        self._in_app_player = None
        self._in_app_vlc_instance = None
        self._in_app_player_window = None
        self._in_app_vlc = None
        self._in_app_playback_after = None
        self._in_app_audio_tracks = {}
        self._in_app_audio_tracks_loaded = False
        self._in_app_audio_track_combo = None
        self._in_app_audio_track = None
        self._in_app_fullscreen = False
        self._in_app_playback_button = None
        self._in_app_player_status = None
        self._in_app_player_status_text = None
        self._in_app_fullscreen_button = None
        self._in_app_video_surface = None
        self._in_app_volume_var = None
        self._in_app_seek_scale = None
        self._in_app_position_var = None
        self._in_app_seeking = False
        if window is not None:
            window.destroy()

    def open_selected_media_in_system_player(self) -> None:
        path = self._selected_media_path()
        if path is not None:
            self.open_media_in_system_player(path)

    def open_media_in_system_player(self, path: Path) -> None:
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
            messagebox.showerror(
                self._t("Could not play media"), str(error), parent=self.root
            )

    def browse_local_media(self) -> None:
        path = self._choose_local_media()
        if path is None:
            return
        self._local_media_path = path
        self._show_local_media_details(path)

    def _choose_local_media(self) -> Path | None:
        media_types = " ".join(f"*{suffix}" for suffix in sorted(PLAYABLE_MEDIA_EXTENSIONS))
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=self._t("Choose an existing audio or video file"),
            filetypes=(
                (self._t("Audio and video files"), media_types),
                (self._t("All files"), "*.*"),
            ),
        )
        if not selected:
            return None
        path = Path(selected).expanduser()
        if not path.is_file() or path.suffix.lower() not in PLAYABLE_MEDIA_EXTENSIONS:
            messagebox.showerror(
                self._t("Unsupported media"),
                self._t("Choose an existing supported audio or video file."),
                parent=self.root,
            )
            return None
        return path

    def _show_local_media_details(self, path: Path) -> None:
        self.inspector_status.set(self._t("Local file"))
        media_kind = (
            "VIDEO"
            if path.suffix.lower() in VIDEO_MEDIA_EXTENSIONS
            else "AUDIO"
        )
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
        except OSError as error:
            self._clear_thumbnail(f"Preview unavailable:\n{error}")
            return
        self.current_thumbnail = None
        self.preview_image_label.configure(
            image="",
            text=f"{media_kind}\n{path.suffix.lstrip('.').upper()}",
        )
        self.preview_details.configure(
            text=f"{path.name}\n{self._t('Existing local file')}\n{size_mb:.1f} MB"
        )

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
        if self.jobs.identify_column(event.x) == "#4":
            if not self._integrity_guard(row_id):
                return
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
        self._local_media_path = None
        if not selected:
            self.inspector_status.set(self._t("No item selected"))
            self._clear_thumbnail("Select a task to inspect")
            return
        job_id = selected[0]
        path = self._selected_output_path()
        if path is None:
            path = self._download_paths.get(job_id)
        values = self.jobs.item(job_id, "values")
        status = values[0] if values else "Unknown"
        progress = values[1] if len(values) > 1 else "—"
        self.inspector_status.set(status)
        if path is None or not path.is_file():
            self._clear_thumbnail(f"{status}\n{progress}\nFile is not available locally.")
            return
        if path.suffix.lower() not in {
            ".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp",
        }:
            media_kind = (
                "VIDEO"
                if path.suffix.lower() in VIDEO_MEDIA_EXTENSIONS
                else "AUDIO"
                if path.suffix.lower() in AUDIO_MEDIA_EXTENSIONS
                else "FILE"
            )
            self.current_thumbnail = None
            self.preview_image_label.configure(
                image="",
                text=f"{media_kind}\n{path.suffix.lstrip('.').upper()}",
            )
            try:
                size_mb = path.stat().st_size / (1024 * 1024)
            except OSError as error:
                self._clear_thumbnail(f"Preview unavailable:\n{error}")
                return
            self.preview_details.configure(
                text=f"{path.name}\n{status} · {progress}\n{size_mb:.1f} MB"
            )
            return
        try:
            from PIL import Image, ImageTk

            try:
                with Image.open(path) as image:
                    image.thumbnail((200, 200), Image.Resampling.LANCZOS)
                    thumbnail = image.copy()
            except Image.DecompressionBombError as error:
                raise ValueError(
                    "Image dimensions exceed the safe preview limit."
                ) from error
            photo = ImageTk.PhotoImage(thumbnail, master=self.root)
        except (OSError, ValueError, RuntimeError, tk.TclError) as error:
            self._clear_thumbnail(f"Preview unavailable:\n{error}")
            return
        self.current_thumbnail = photo
        self.preview_image_label.configure(image=photo, text="")
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
        except OSError as error:
            self._clear_thumbnail(f"Preview unavailable:\n{error}")
            return
        self.preview_details.configure(
            text=f"{path.name}\n{status} · {progress}\n{size_mb:.1f} MB"
        )

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
