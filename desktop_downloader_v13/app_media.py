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
_IN_APP_PLAYBACK_RATES = ("0.5x", "1.0x", "1.5x", "2.0x")


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
        current_path = getattr(self, "_in_app_media_path", None)
        player = getattr(self, "_in_app_player", None)
        if (
            player is not None
            and current_path is not None
            and Path(current_path) == path.resolve()
        ):
            self._toggle_in_app_playback()
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

    def play_selected_media_in_preview(self) -> None:
        selected = self.jobs.selection()
        choices = getattr(self, "_preview_video_choices", {})
        choice = getattr(self, "preview_video_choice", None)
        path = choices.get(choice.get()) if choice is not None else None
        if path is None:
            path = getattr(self, "_local_media_path", None)
        if path is None and selected:
            if not self._integrity_guard(selected[0]):
                return
            path = self._selected_output_path()
        if path is None or not path.is_file():
            path = self._choose_local_video()
            if path is None:
                return
            self._local_media_path = path
        if path.suffix.lower() not in VIDEO_MEDIA_EXTENSIONS:
            messagebox.showinfo(
                self._t("Video preview only"),
                self._t("Choose a supported video file to play it in the preview."),
                parent=self.root,
            )
            return
        self._local_media_path = path
        self._show_video_preview(path)
        self._refresh_preview_video_choices()
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
        except OSError as error:
            self._clear_thumbnail(f"Preview unavailable:\n{error}")
            return
        self.preview_details.configure(
            text=f"{path.name}\n{self._t('Video preview')}\n{size_mb:.1f} MB"
        )

    @staticmethod
    def _is_preview_video_path(path: Path) -> bool:
        name = path.name.casefold()
        return path.suffix.casefold() in VIDEO_MEDIA_EXTENSIONS or any(
            name.endswith(f"{extension}.part")
            for extension in VIDEO_MEDIA_EXTENSIONS
        )

    def _refresh_preview_video_choices(self) -> list[Path]:
        selected = self.jobs.selection()
        roots: set[Path] = set()
        paths: set[Path] = set()
        local_path = getattr(self, "_local_media_path", None)
        if local_path is not None and local_path.is_file():
            if local_path.suffix.lower() in VIDEO_MEDIA_EXTENSIONS:
                paths.add(local_path.resolve())
        if selected:
            job_id = selected[0]
            output_path = self._selected_output_path()
            job_paths = [
                output_path,
                getattr(self, "_download_paths", {}).get(job_id),
            ]
            options = getattr(self, "download_options", {}).get(job_id, {})
            job_paths.append(options.get("destination"))
            for candidate in job_paths:
                if not candidate:
                    continue
                candidate = Path(candidate).expanduser()
                if candidate.is_file() and self._is_preview_video_path(candidate):
                    paths.add(candidate.resolve())
                elif candidate.is_dir():
                    roots.add(candidate.resolve())
        for root in roots:
            for candidate in root.rglob("*"):
                if candidate.is_file() and self._is_preview_video_path(candidate):
                    paths.add(candidate.resolve())

        ordered_paths = sorted(
            paths,
            key=lambda path: (
                path.name.casefold().endswith(".part"),
                path.as_posix().casefold(),
            ),
        )
        labels: dict[str, Path] = {}
        for path in ordered_paths:
            try:
                display_path = next(
                    path.relative_to(root).as_posix()
                    for root in roots
                    if path.is_relative_to(root)
                )
            except StopIteration:
                display_path = str(path)
            label = display_path
            if path.name.casefold().endswith(".part"):
                label += f" ({self._t('Downloading')})"
            if label in labels:
                label = f"{display_path} — {path.parent.name}"
            labels[label] = path

        selector = getattr(self, "preview_video_selector", None)
        variable = getattr(self, "preview_video_choice", None)
        self._preview_video_choices = labels
        if selector is not None and variable is not None:
            values = tuple(labels)
            current_path = getattr(self, "_preview_media_path", None)
            current_label = next(
                (label for label, path in labels.items() if path == current_path),
                None,
            )
            previous_label = variable.get()
            if previous_label not in labels:
                previous_label = None
            selected_label = current_label or previous_label
            if selected_label is None and values:
                selected_label = values[0]
            selector.configure(
                values=values,
                state="readonly" if values else "disabled",
            )
            variable.set(selected_label or "")

        status = getattr(self, "preview_video_status", None)
        if status is not None:
            selected_path = (
                labels.get(variable.get())
                if variable is not None
                else None
            )
            if (
                selected_path is not None
                and selected_path.name.casefold().endswith(".part")
            ):
                status.set(
                    self._t(
                        "This video is still downloading. Preview may not work "
                        "until the download has finished."
                    )
                )
            elif labels:
                status.set("")
            elif selected:
                status.set(self._t("No videos found in this download."))
            elif local_path is not None:
                status.set(self._t("No videos found for this selection."))
            else:
                status.set(self._t("Select a download to list its videos."))
        return ordered_paths

    def _select_preview_video(self, _event=None) -> None:
        choice = getattr(self, "preview_video_choice", None)
        path = getattr(self, "_preview_video_choices", {}).get(
            choice.get() if choice is not None else ""
        )
        if path is None or not path.is_file():
            self._refresh_preview_video_choices()
            return
        if path.suffix.lower() not in VIDEO_MEDIA_EXTENSIONS:
            status = getattr(self, "preview_video_status", None)
            if status is not None:
                status.set(
                    self._t(
                        "This video is still downloading. Preview may not work "
                        "until the download has finished."
                    )
                )
        self._local_media_path = path
        self.current_thumbnail = None
        self.inspector_status.set(
            self._t("Downloading")
            if path.name.casefold().endswith(".part")
            else self._t("Local file")
        )
        self._show_video_preview(path)
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
        except OSError as error:
            self._clear_thumbnail(f"Preview unavailable:\n{error}")
            return
        self.preview_details.configure(
            text=f"{path}\n{self._t('Video preview')}\n{size_mb:.1f} MB"
        )

    def _schedule_preview_video_refresh(self, job_id: str) -> None:
        if not self.jobs.selection() or self.jobs.selection()[0] != job_id:
            return
        if getattr(self, "_preview_video_refresh_after", None) is not None:
            return
        self._preview_video_refresh_after = self.root.after(
            1500,
            self._refresh_scheduled_preview_video_choices,
        )

    def _refresh_scheduled_preview_video_choices(self) -> None:
        self._preview_video_refresh_after = None
        self._refresh_preview_video_choices()

    def _choose_local_video(self) -> Path | None:
        video_types = " ".join(
            f"*{suffix}" for suffix in sorted(VIDEO_MEDIA_EXTENSIONS)
        )
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=self._t("Choose a video to preview"),
            filetypes=(
                (self._t("Video files"), video_types),
                (self._t("All files"), "*.*"),
            ),
        )
        if not selected:
            return None
        path = Path(selected).expanduser()
        if not path.is_file() or path.suffix.lower() not in VIDEO_MEDIA_EXTENSIONS:
            messagebox.showerror(
                self._t("Unsupported media"),
                self._t("Choose an existing supported video file."),
                parent=self.root,
            )
            return None
        return path

    def _show_video_preview(self, path: Path) -> None:
        self._clear_video_preview()
        self._preview_media_path = path
        self.preview_image_label.grid_remove()
        self.preview_video_surface.grid()
        self.preview_player_controls.grid()
        self.preview_player_current_time.set("00:00")
        self.preview_player_duration.set("00:00")
        self.preview_player_position.set(0)
        self._draw_video_preview_timeline()
        self.preview_video_placeholder.configure(
            text=f"{path.name}\n{self._t('Loading preview')}",
        )
        self._toggle_video_preview()

    def _clear_video_preview(self) -> None:
        self._stop_video_preview()
        self._preview_media_path = None
        surface = getattr(self, "preview_video_surface", None)
        if surface is not None:
            surface.grid_remove()
        controls = getattr(self, "preview_player_controls", None)
        if controls is not None:
            controls.grid_remove()
        preview = getattr(self, "preview_image_label", None)
        if preview is not None:
            preview.grid()

    def _toggle_video_preview(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        if player is not None:
            if player.is_playing():
                player.pause()
                self.preview_player_play_button.configure(text="▶")
            else:
                player.play()
                self.preview_player_play_button.configure(text="Ⅱ")
                self._schedule_video_preview_poll()
            return

        path = getattr(self, "_preview_media_path", None)
        if path is None:
            return
        try:
            import importlib

            self._prepare_bundled_vlc_runtime()
            vlc = importlib.import_module("vlc")
            self._preview_vlc = vlc
            instance = vlc.Instance()
            if instance is None:
                raise RuntimeError(self._t("VLC could not initialize."))
            self._preview_vlc_instance = instance
            player = instance.media_player_new()
            self._preview_vlc_player = player
            player.set_media(instance.media_new(str(path)))
            surface = self.preview_video_surface
            surface.update_idletasks()
            handle = surface.winfo_id()
            if sys.platform == "win32":
                player.set_hwnd(handle)
            elif sys.platform == "darwin":
                player.set_nsobject(handle)
            else:
                player.set_xwindow(handle)
            self.preview_video_placeholder.configure(
                text=f"{path.name}\n{self._t('Loading preview')}",
            )
            self.preview_video_placeholder.place(
                relx=0.5, rely=0.5, anchor="center",
            )
            player.audio_set_mute(False)
            player.audio_set_volume(self.preview_player_volume.get())
            if player.play() == -1:
                raise RuntimeError(self._t("VLC could not start playback."))
            rate = float(self._preview_playback_rate.get().removesuffix("x"))
            if rate != 1.0 and player.set_rate(rate) == -1:
                self._preview_playback_rate.set("1.0x")
                messagebox.showerror(
                    self._t("Playback speed unavailable"),
                    self._t("VLC could not change the playback speed."),
                    parent=self.root,
                )
            self.preview_player_play_button.configure(text="Ⅱ")
            self._preview_duration_ms = 0
            self._preview_seeking = False
            self._schedule_video_preview_poll()
        except (AttributeError, ImportError, OSError, RuntimeError) as error:
            self._stop_video_preview()
            messagebox.showerror(
                self._t("Could not preview video"),
                str(error),
                parent=self.root,
            )

    def _schedule_video_preview_poll(self) -> None:
        root = getattr(self, "root", None)
        if root is None or getattr(self, "_preview_playback_after", None) is not None:
            return
        self._preview_playback_after = root.after(
            250,
            self._poll_video_preview,
        )

    def _poll_video_preview(self) -> None:
        self._preview_playback_after = None
        player = getattr(self, "_preview_vlc_player", None)
        if player is None:
            return
        vlc = getattr(self, "_preview_vlc", None)
        state = player.get_state()
        if vlc is not None and state == vlc.State.Error:
            self._stop_video_preview()
            placeholder = getattr(self, "preview_video_placeholder", None)
            if placeholder is not None:
                placeholder.configure(
                    text=self._t(
                        "VLC could not play this video. Try another file or use "
                        "Open in system player."
                    ),
                )
                placeholder.place(relx=0.5, rely=0.5, anchor="center")
            return
        if vlc is not None and state == vlc.State.Playing:
            self.preview_video_placeholder.place_forget()
        duration = max(0, player.get_length())
        current_time = max(0, player.get_time())
        self._preview_duration_ms = duration
        self.preview_player_duration.set(self._format_in_app_time(duration))
        self.preview_player_current_time.set(
            self._format_in_app_time(current_time)
        )
        if duration > 0 and player.is_seekable() and not self._preview_seeking:
            self.preview_player_position.set(
                min(100, current_time * 100 / duration)
            )
        self._draw_video_preview_timeline()
        self._preview_audio_refresh_ticks = (
            getattr(self, "_preview_audio_refresh_ticks", 0) + 1
        )
        if self._preview_audio_refresh_ticks % 4 == 0:
            self._refresh_video_preview_audio_tracks()
            self._refresh_video_preview_subtitle_tracks()
        self._schedule_video_preview_poll()

    def _draw_video_preview_timeline(self) -> None:
        timeline = getattr(self, "preview_player_timeline", None)
        if timeline is None:
            return
        width = timeline.winfo_width()
        height = timeline.winfo_height()
        if width <= 1 or height <= 1:
            return
        timeline.delete("all")
        start = 5
        end = max(start + 1, width - 5)
        midpoint = height / 2
        active = (
            getattr(self, "_preview_timeline_hover", False)
            or getattr(self, "_preview_seeking", False)
        )
        line_width = 8 if active else 4
        position = max(0.0, min(100.0, self.preview_player_position.get()))
        played_end = start + (end - start) * position / 100
        timeline.create_line(
            start,
            midpoint,
            end,
            midpoint,
            fill="#777777",
            width=line_width,
            capstyle="round",
        )
        timeline.create_line(
            start,
            midpoint,
            played_end,
            midpoint,
            fill="#FF3333",
            width=line_width,
            capstyle="round",
        )
        if active:
            radius = 5
            timeline.create_oval(
                played_end - radius,
                midpoint - radius,
                played_end + radius,
                midpoint + radius,
                fill="#FFFFFF",
                outline="#FFFFFF",
            )

    def _set_video_preview_seek_from_event(self, event) -> None:
        timeline = self.preview_player_timeline
        width = max(1, timeline.winfo_width())
        usable_width = max(1, width - 10)
        position = max(0.0, min(100.0, (float(event.x) - 5) * 100 / usable_width))
        self.preview_player_position.set(position)
        if self._preview_duration_ms > 0:
            self.preview_player_current_time.set(
                self._format_in_app_time(
                    round(self._preview_duration_ms * position / 100)
                )
            )
        self._draw_video_preview_timeline()

    def _begin_video_preview_seek(self, event=None) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        if (
            player is None
            or self._preview_duration_ms <= 0
            or not player.is_seekable()
        ):
            return
        self._preview_seeking = True
        if event is not None:
            self._set_video_preview_seek_from_event(event)

    def _update_video_preview_seek(self, event=None) -> None:
        if self._preview_seeking and event is not None:
            self._set_video_preview_seek_from_event(event)

    def _seek_video_preview(self, event=None) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        if player is not None and self._preview_seeking:
            if event is not None:
                self._set_video_preview_seek_from_event(event)
            duration = max(0, player.get_length())
            if duration > 0 and player.is_seekable():
                position = max(
                    0.0,
                    min(100.0, float(self.preview_player_position.get())),
                )
                player.set_time(round(duration * position / 100))
        self._preview_seeking = False
        self._draw_video_preview_timeline()

    def _nudge_video_preview_seek(self, seconds: int) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        if player is None or not player.is_seekable():
            return
        current_time = max(0, player.get_time())
        duration = max(0, player.get_length())
        target_time = max(0, current_time + seconds * 1000)
        if duration > 0:
            target_time = min(target_time, duration)
        player.set_time(target_time)

    def _adjust_video_preview_volume(self, delta: int) -> None:
        volume = max(
            0,
            min(100, round(float(self.preview_player_volume.get())) + delta),
        )
        self.preview_player_volume.set(volume)
        self._set_video_preview_volume(str(volume))

    @staticmethod
    def _widget_is_within(widget, ancestor) -> bool:
        if ancestor is None:
            return False
        while widget is not None:
            if widget is ancestor:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _handle_playback_arrow_key(self, event=None) -> str | None:
        if event is None:
            return None
        key = getattr(event, "keysym", "")
        widget = getattr(event, "widget", None)
        try:
            top_level = widget.winfo_toplevel() if widget is not None else None
        except tk.TclError:
            return None

        player_window = getattr(self, "_in_app_player_window", None)
        overlay_windows = {
            getattr(self, "_in_app_controls_overlay_window", None),
            getattr(self, "_in_app_top_controls_overlay_window", None),
        }
        if top_level is player_window or top_level in overlay_windows:
            player = getattr(self, "_in_app_player", None)
            if player is None:
                return None
            if key == "Left":
                self._nudge_in_app_player_seek(-5)
            elif key == "Right":
                self._nudge_in_app_player_seek(5)
            elif key == "Up":
                self._adjust_in_app_volume(5)
            elif key == "Down":
                self._adjust_in_app_volume(-5)
            else:
                return None
            self._show_in_app_controls()
            return "break"

        preview = getattr(self, "preview_container", None)
        if (
            top_level is getattr(self, "root", None)
            and self._widget_is_within(widget, preview)
            and getattr(self, "_preview_vlc_player", None) is not None
        ):
            if key == "Left":
                self._nudge_video_preview_seek(-5)
            elif key == "Right":
                self._nudge_video_preview_seek(5)
            elif key == "Up":
                self._adjust_video_preview_volume(5)
            elif key == "Down":
                self._adjust_video_preview_volume(-5)
            else:
                return None
            return "break"
        return None

    def _nudge_in_app_player_seek(self, seconds: int) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is None or not player.is_seekable():
            return
        current_time = max(0, player.get_time())
        duration = max(0, player.get_length())
        target_time = max(0, current_time + seconds * 1000)
        if duration > 0:
            target_time = min(target_time, duration)
        player.set_time(target_time)

    def _adjust_in_app_volume(self, delta: int) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is None:
            return
        volume = getattr(self, "_in_app_volume_var", None)
        current = volume.get() if volume is not None else player.audio_get_volume()
        self._set_in_app_volume(str(max(0, min(100, round(float(current)) + delta))))

    def _set_video_preview_timeline_hover(self, active: bool) -> None:
        self._preview_timeline_hover = active
        self._draw_video_preview_timeline()

    def _set_video_preview_volume(self, value: str) -> None:
        volume = max(0, min(100, round(float(value))))
        label = getattr(self, "preview_player_volume_label", None)
        if label is not None:
            label.configure(text=f"{volume}%")
        player = getattr(self, "_preview_vlc_player", None)
        if player is not None:
            player.audio_set_volume(volume)

    def _refresh_video_preview_audio_tracks(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        variable = getattr(self, "_preview_audio_track", None)
        if player is None or variable is None:
            return
        tracks = {}
        for track_id, description in player.audio_get_track_description() or []:
            label = (
                description.decode("utf-8", errors="replace")
                if isinstance(description, bytes)
                else str(description)
            ) or self._t("Audio track")
            if label in tracks:
                label = f"{label} ({track_id})"
            tracks[label] = int(track_id)
        self._preview_audio_tracks = tracks
        if not tracks:
            variable.set("")
            return
        active = player.audio_get_track()
        variable.set(
            next(
                (label for label, track_id in tracks.items() if track_id == active),
                next(iter(tracks)),
            )
        )

    def _refresh_video_preview_subtitle_tracks(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        variable = getattr(self, "_preview_subtitle_track", None)
        if player is None or variable is None:
            return
        tracks = {}
        for track_id, description in player.video_get_spu_description() or []:
            track_id = int(track_id)
            if track_id < 0:
                continue
            label = (
                description.decode("utf-8", errors="replace")
                if isinstance(description, bytes)
                else str(description)
            ) or self._t("Subtitles")
            if label.strip().lower() in {"disable", "off", "none"}:
                continue
            if label in tracks:
                label = f"{label} ({track_id})"
            tracks[label] = track_id
        self._preview_subtitle_tracks = tracks
        if not tracks:
            variable.set(self._t("Off"))
            return
        active = player.video_get_spu()
        variable.set(
            next(
                (label for label, track_id in tracks.items() if track_id == active),
                self._t("Off"),
            )
        )

    def _set_video_preview_playback_rate(self, _event=None) -> None:
        variable = getattr(self, "_preview_playback_rate", None)
        if variable is None:
            return
        selected = variable.get()
        if selected not in _IN_APP_PLAYBACK_RATES:
            messagebox.showerror(
                self._t("Invalid playback speed"),
                self._t("Choose one of the available playback speeds."),
                parent=self.root,
            )
            return
        player = getattr(self, "_preview_vlc_player", None)
        if player is None or player.set_rate(float(selected.removesuffix("x"))) != -1:
            return
        current_rate = player.get_rate()
        variable.set(
            next(
                (
                    option
                    for option in _IN_APP_PLAYBACK_RATES
                    if float(option.removesuffix("x")) == current_rate
                ),
                f"{current_rate:g}x",
            )
        )
        messagebox.showerror(
            self._t("Playback speed unavailable"),
            self._t("VLC could not change the playback speed."),
            parent=self.root,
        )

    def _select_video_preview_audio_track(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        variable = getattr(self, "_preview_audio_track", None)
        if player is None or variable is None:
            return
        track_id = self._preview_audio_tracks.get(variable.get())
        if track_id is not None and player.audio_set_track(track_id) == -1:
            messagebox.showerror(
                self._t("Audio track unavailable"),
                self._t("VLC could not select this audio track."),
                parent=self.root,
            )

    def _set_video_preview_subtitle_track(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        variable = getattr(self, "_preview_subtitle_track", None)
        if player is None or variable is None:
            return
        label = variable.get()
        if label == self._t("Off"):
            self._disable_video_preview_subtitles()
            return
        track_id = self._preview_subtitle_tracks.get(label)
        if track_id is not None and player.video_set_spu(track_id) == -1:
            messagebox.showerror(
                self._t("Subtitle track unavailable"),
                self._t("VLC could not select this subtitle track."),
                parent=self.root,
            )
        self._refresh_video_preview_subtitle_tracks()

    def _disable_video_preview_subtitles(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        if player is None:
            return
        if player.video_set_spu(-1) == -1:
            messagebox.showerror(
                self._t("Subtitle track unavailable"),
                self._t("VLC could not change subtitle visibility."),
                parent=self.root,
            )
            return
        self._preview_subtitle_track.set(self._t("Off"))

    def _toggle_video_preview_subtitles(self) -> None:
        player = getattr(self, "_preview_vlc_player", None)
        if player is None:
            return
        self._refresh_video_preview_subtitle_tracks()
        if not self._preview_subtitle_tracks:
            return
        if player.video_get_spu() >= 0:
            self._disable_video_preview_subtitles()
            return
        selected = self._preview_subtitle_track.get()
        if selected not in self._preview_subtitle_tracks:
            selected = next(iter(self._preview_subtitle_tracks))
        self._preview_subtitle_track.set(selected)
        self._set_video_preview_subtitle_track()

    def _show_video_preview_settings(self, button=None) -> None:
        if button is None:
            return
        self._refresh_video_preview_audio_tracks()
        self._refresh_video_preview_subtitle_tracks()
        menu_options = {
            "tearoff": False,
            "background": "#202020",
            "foreground": "#FFFFFF",
            "activebackground": "#333333",
            "activeforeground": "#FFFFFF",
        }
        menu = tk.Menu(
            self.root,
            **menu_options,
        )
        speed_menu = tk.Menu(menu, **menu_options)
        for rate in _IN_APP_PLAYBACK_RATES:
            speed_menu.add_radiobutton(
                label=rate,
                variable=self._preview_playback_rate,
                value=rate,
                command=self._set_video_preview_playback_rate,
            )
        menu.add_cascade(label=self._t("Playback speed"), menu=speed_menu)
        audio_menu = tk.Menu(menu, **menu_options)
        if self._preview_audio_tracks:
            for label in self._preview_audio_tracks:
                audio_menu.add_radiobutton(
                    label=label,
                    variable=self._preview_audio_track,
                    value=label,
                    command=self._select_video_preview_audio_track,
                )
        else:
            audio_menu.add_command(
                label=self._t("No audio tracks available"),
                state="disabled",
            )
        menu.add_cascade(label=self._t("Audio track"), menu=audio_menu)
        subtitle_menu = tk.Menu(menu, **menu_options)
        if self._preview_subtitle_tracks:
            subtitle_menu.add_radiobutton(
                label=self._t("Off"),
                variable=self._preview_subtitle_track,
                value=self._t("Off"),
                command=self._disable_video_preview_subtitles,
            )
            for label in self._preview_subtitle_tracks:
                subtitle_menu.add_radiobutton(
                    label=label,
                    variable=self._preview_subtitle_track,
                    value=label,
                    command=self._set_video_preview_subtitle_track,
                )
        else:
            subtitle_menu.add_command(
                label=self._t("No subtitles available"),
                state="disabled",
            )
        menu.add_cascade(label=self._t("Subtitles"), menu=subtitle_menu)
        try:
            menu.tk_popup(
                button.winfo_rootx(),
                max(0, button.winfo_rooty() - menu.winfo_reqheight()),
            )
        finally:
            menu.grab_release()
            menu.destroy()

    def _stop_video_preview(self) -> None:
        after_id = getattr(self, "_preview_playback_after", None)
        root = getattr(self, "root", None)
        if root is not None and after_id is not None:
            try:
                root.after_cancel(after_id)
            except tk.TclError:
                pass
        self._preview_playback_after = None
        self._preview_audio_tracks = {}
        self._preview_subtitle_tracks = {}
        player = getattr(self, "_preview_vlc_player", None)
        if player is not None:
            player.stop()
            player.release()
        instance = getattr(self, "_preview_vlc_instance", None)
        if instance is not None:
            instance.release()
        self._preview_vlc_player = None
        self._preview_vlc_instance = None
        self._preview_vlc = None
        button = getattr(self, "preview_player_play_button", None)
        if button is not None:
            button.configure(text="▶")
        volume_label = getattr(self, "preview_player_volume_label", None)
        if volume_label is not None:
            volume = max(
                0,
                min(100, round(float(self.preview_player_volume.get()))),
            )
            volume_label.configure(text=f"{volume}%")
        placeholder = getattr(self, "preview_video_placeholder", None)
        if placeholder is not None:
            placeholder.place(relx=0.5, rely=0.5, anchor="center")
        self._preview_duration_ms = 0
        cc_button = getattr(self, "preview_player_cc_button", None)
        if cc_button is not None:
            cc_button.configure(state="disabled")
        audio_variable = getattr(self, "_preview_audio_track", None)
        if audio_variable is not None:
            audio_variable.set("")
        subtitle_variable = getattr(self, "_preview_subtitle_track", None)
        if subtitle_variable is not None:
            subtitle_variable.set(self._t("Off"))
        if hasattr(self, "preview_player_position"):
            self.preview_player_position.set(0)
        if hasattr(self, "preview_player_current_time"):
            self.preview_player_current_time.set("00:00")
        if hasattr(self, "preview_player_duration"):
            self.preview_player_duration.set("00:00")

    def _open_preview_fullscreen(self) -> None:
        path = getattr(self, "_preview_media_path", None)
        if path is None:
            return
        preview_player = getattr(self, "_preview_vlc_player", None)
        if preview_player is not None and preview_player.is_playing():
            preview_player.pause()
            self.preview_player_play_button.configure(text="▶")
        selected = getattr(self, "jobs", None)
        selection = selected.selection() if selected is not None else ()
        if selection and self._selected_output_path() == path:
            if not self._integrity_guard(selection[0]):
                return
        self._preserve_video_preview = True
        try:
            self._play_media_in_app(path)
        except (AttributeError, ImportError, OSError, RuntimeError) as error:
            if messagebox.askyesno(
                self._t("In-app playback unavailable"),
                self._t(
                    "VLC is required for in-app playback. Open this file in your system player instead?"
                )
                + f"\n\n{error}",
                parent=self.root,
            ):
                self.open_media_in_system_player(path)
        finally:
            self._preserve_video_preview = False
        if getattr(self, "_in_app_player", None) is not None:
            self._toggle_in_app_fullscreen()

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

        if not getattr(self, "_preserve_video_preview", False):
            self._stop_video_preview()
        self._prepare_bundled_vlc_runtime()
        vlc = importlib.import_module("vlc")
        if getattr(self, "_in_app_player_window", None) is not None:
            self._close_in_app_player()

        window = tk.Toplevel(self.root)
        window.title(f"Smart VLC — {path.name}")
        window.geometry("1120x700")
        window.minsize(800, 500)
        window.configure(background="#101318")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        window.protocol("WM_DELETE_WINDOW", self._close_in_app_player)
        window.bind("<F11>", self._toggle_in_app_fullscreen, add="+")
        window.bind("<Escape>", self._exit_in_app_fullscreen, add="+")
        window.bind("<space>", self._toggle_in_app_playback_from_key, add="+")
        window.bind("<KeyPress>", self._show_in_app_controls, add="+")
        window.bind("<Motion>", self._show_in_app_controls, add="+")
        window.bind("<ButtonPress-1>", self._begin_in_app_control_interaction, add="+")
        window.bind("<ButtonRelease-1>", self._end_in_app_control_interaction, add="+")
        self._in_app_player_window = window
        self._in_app_media_title = path.name
        self._in_app_media_path = path.resolve()

        self._in_app_player_status = tk.StringVar(value=self._t("Playback started"))
        self._in_app_controls_visible = False
        self._in_app_controls_after = None
        self._in_app_controls_fade_after = None
        self._in_app_controls_opacity = 0.0
        self._in_app_pointer_after = None
        self._in_app_control_interaction = False
        self._in_app_pointer_down = False
        self._in_app_last_pointer = None
        self._in_app_timeline_hover = False
        self._in_app_duration_ms = 0
        self._in_app_seeking = False

        video_surface = tk.Frame(window, background="#000000")
        video_surface.grid(row=0, column=0, sticky="nsew")
        self._in_app_video_surface = video_surface
        video_surface.bind("<Configure>", self._raise_in_app_controls_overlay, add="+")
        video_surface.bind("<Motion>", self._show_in_app_controls, add="+")
        video_surface.bind("<ButtonPress-1>", self._show_in_app_controls, add="+")
        video_surface.bind("<Double-Button-1>", self._toggle_in_app_fullscreen, add="+")

        controls_window = tk.Toplevel(window)
        controls_window.withdraw()
        controls_window.overrideredirect(True)
        controls_window.transient(window)
        controls_window.attributes("-alpha", 0.0)
        controls_window.bind("<F11>", self._toggle_in_app_fullscreen, add="+")
        controls_window.bind("<Escape>", self._exit_in_app_fullscreen, add="+")
        controls_window.bind("<space>", self._toggle_in_app_playback_from_key, add="+")
        controls_window.bind("<KeyPress>", self._show_in_app_controls, add="+")
        self._in_app_controls_overlay_window = controls_window
        top_controls_window = tk.Toplevel(window)
        top_controls_window.withdraw()
        top_controls_window.overrideredirect(True)
        top_controls_window.transient(window)
        top_controls_window.attributes("-alpha", 0.0)
        top_controls_window.bind("<F11>", self._toggle_in_app_fullscreen, add="+")
        top_controls_window.bind("<Escape>", self._exit_in_app_fullscreen, add="+")
        top_controls_window.bind("<space>", self._toggle_in_app_playback_from_key, add="+")
        top_controls_window.bind("<KeyPress>", self._show_in_app_controls, add="+")
        self._in_app_top_controls_overlay_window = top_controls_window
        top_controls = tk.Frame(
            top_controls_window,
            background="#000000",
            padx=12,
            pady=5,
            highlightthickness=0,
        )
        top_controls.pack(fill="both", expand=True)
        top_controls.columnconfigure(1, weight=1)
        self._in_app_top_controls_overlay = top_controls
        self._in_app_top_back_button = tk.Button(
            top_controls,
            text="←",
            command=self._exit_in_app_fullscreen,
            width=3,
            cursor="hand2",
            font=("Segoe UI Symbol", 15),
            background="#000000",
            foreground="#FFFFFF",
            activebackground="#202020",
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._in_app_top_back_button.grid(row=0, column=0, sticky="w")
        self._in_app_top_title_label = tk.Label(
            top_controls,
            text=self._in_app_media_title,
            background="#000000",
            foreground="#FFFFFF",
            font=("Segoe UI", 11, "bold"),
            anchor="center",
        )
        self._in_app_top_title_label.grid(row=0, column=1, sticky="ew")
        self._in_app_top_settings_button = tk.Button(
            top_controls,
            text="⚙",
            command=lambda: self._show_in_app_settings_menu(
                self._in_app_top_settings_button
            ),
            width=3,
            cursor="hand2",
            font=("Segoe UI Symbol", 14),
            background="#000000",
            foreground="#FFFFFF",
            activebackground="#202020",
            activeforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._in_app_top_settings_button.grid(row=0, column=2, sticky="e")
        controls_overlay = tk.Frame(
            controls_window,
            background="#000000",
            padx=8,
            pady=4,
            highlightthickness=0,
        )
        controls_overlay.pack(fill="both", expand=True)
        self._in_app_controls_overlay = controls_overlay
        controls_overlay.columnconfigure(5, weight=1, minsize=100)

        def make_button(parent, text: str, command, font_size: int = 13):
            button = tk.Button(
                parent,
                text=text,
                command=command,
                width=3,
                takefocus=True,
                cursor="hand2",
                font=("Segoe UI Symbol", font_size),
                background="#000000",
                foreground="#FFFFFF",
                activebackground="#202020",
                activeforeground="#FFFFFF",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                padx=5,
                pady=3,
            )
            return button

        playback_button = make_button(
            controls_overlay, "Ⅱ", self._toggle_in_app_playback, 12
        )
        playback_button.grid(row=0, column=0, padx=(0, 2))
        self._in_app_playback_button = playback_button

        self._in_app_current_time = tk.StringVar(value="00:00")
        self._in_app_duration = tk.StringVar(value="00:00")
        self._in_app_position_var = tk.DoubleVar(value=0)
        current_time_label = tk.Label(
            controls_overlay,
            textvariable=self._in_app_current_time,
            width=6,
            anchor="e",
            background="#000000",
            foreground="#FFFFFF",
            font=("Segoe UI", 9),
        )
        current_time_label.grid(row=0, column=4, padx=(8, 6))
        self._in_app_timeline = tk.Canvas(
            controls_overlay,
            height=20,
            background="#000000",
            highlightthickness=0,
            cursor="hand2",
        )
        self._in_app_timeline.grid(row=0, column=5, sticky="ew", padx=4)
        self._in_app_timeline.bind("<ButtonPress-1>", self._begin_in_app_seek, add="+")
        self._in_app_timeline.bind("<B1-Motion>", self._update_in_app_seek, add="+")
        self._in_app_timeline.bind("<ButtonRelease-1>", self._seek_in_app_player, add="+")
        self._in_app_timeline.bind(
            "<Enter>", lambda _event: self._set_in_app_timeline_hover(True), add="+"
        )
        self._in_app_timeline.bind(
            "<Leave>", lambda _event: self._set_in_app_timeline_hover(False), add="+"
        )
        duration_label = tk.Label(
            controls_overlay,
            textvariable=self._in_app_duration,
            width=6,
            anchor="w",
            background="#000000",
            foreground="#D0D0D0",
            font=("Segoe UI", 9),
        )
        duration_label.grid(row=0, column=6, padx=(6, 8))
        self._in_app_audio_track = tk.StringVar(value="")
        self._in_app_audio_tracks: dict[str, int] = {}
        self._in_app_audio_tracks_loaded = False
        self._in_app_playback_rate = tk.StringVar(value="1.0x")
        self._in_app_subtitle_track = tk.StringVar(value="")
        self._in_app_subtitle_tracks: dict[str, int] = {}
        self._in_app_subtitle_tracks_loaded = False
        self._in_app_cc_button = make_button(
            controls_overlay,
            "CC",
            self._toggle_in_app_subtitles,
            10,
        )
        self._in_app_cc_button.grid(row=0, column=7, padx=(0, 4))
        self._in_app_cc_button.grid_remove()
        self._in_app_settings_button = make_button(
            controls_overlay,
            "⚙",
            lambda: self._show_in_app_settings_menu(
                self._in_app_settings_button
            ),
            14,
        )
        self._in_app_settings_button.grid(row=0, column=8, padx=(2, 2))

        volume_icon = tk.Label(
            controls_overlay,
            text="◖))",
            background="#000000",
            foreground="#FFFFFF",
            font=("Segoe UI", 9),
        )
        volume_icon.grid(row=0, column=1, padx=(2, 3))
        volume = tk.IntVar(value=80)
        self._in_app_volume_var = volume
        self._in_app_volume_label = tk.StringVar(value="80%")
        volume_value_label = tk.Label(
            controls_overlay,
            textvariable=self._in_app_volume_label,
            width=4,
            anchor="e",
            background="#000000",
            foreground="#D0D0D0",
            font=("Segoe UI", 9),
        )
        volume_value_label.grid(row=0, column=2, padx=(0, 2))
        volume_scale = tk.Scale(
            controls_overlay,
            from_=0,
            to=100,
            orient="horizontal",
            variable=volume,
            command=lambda value: self._set_in_app_volume(value),
            length=76,
            showvalue=False,
            sliderlength=10,
            troughcolor="#707070",
            background="#000000",
            foreground="#FFFFFF",
            activebackground="#FF3333",
            highlightthickness=0,
            borderwidth=0,
            relief="flat",
            takefocus=True,
        )
        volume_scale.grid(row=0, column=3, padx=(0, 4))

        fullscreen_button = make_button(
            controls_overlay,
            "⛶",
            self._toggle_in_app_fullscreen,
            14,
        )
        fullscreen_button.grid(row=0, column=9, padx=(0, 2))
        self._in_app_fullscreen_button = fullscreen_button

        top_widgets = (
            self._in_app_top_back_button,
            self._in_app_top_title_label,
            self._in_app_top_settings_button,
        )
        for widget in top_widgets:
            widget.bind("<Enter>", self._show_in_app_controls, add="+")
            widget.bind("<Motion>", self._show_in_app_controls, add="+")
            widget.bind(
                "<ButtonPress-1>",
                self._begin_in_app_control_interaction,
                add="+",
            )
            widget.bind(
                "<ButtonRelease-1>",
                self._end_in_app_control_interaction,
                add="+",
            )

        self._in_app_vlc = vlc
        self._in_app_player_status_text = self._t("Playback started")
        self._in_app_audio_refresh_ticks = 0
        self._in_app_playback_after = None
        self._in_app_fullscreen = False
        for widget in (
            playback_button,
            current_time_label,
            self._in_app_timeline,
            duration_label,
            self._in_app_cc_button,
            self._in_app_settings_button,
            volume_icon,
            volume_value_label,
            volume_scale,
            fullscreen_button,
        ):
            widget.bind("<Enter>", self._show_in_app_controls, add="+")
            widget.bind("<Motion>", self._show_in_app_controls, add="+")
            widget.bind(
                "<ButtonPress-1>",
                self._begin_in_app_control_interaction,
                add="+",
            )
            widget.bind(
                "<ButtonRelease-1>",
                self._end_in_app_control_interaction,
                add="+",
            )

        window.update_idletasks()

        try:
            instance = vlc.Instance()
            self._in_app_vlc_instance = instance
            player = instance.media_player_new()
            self._in_app_player = player
            player.set_media(instance.media_new(str(path)))
            self._set_in_app_video_target(video_surface)
            window.lift()
            window.focus_set()
            player.audio_set_mute(False)
            player.audio_set_volume(volume.get())
            if player.play() == -1:
                raise RuntimeError(self._t("VLC could not start playback."))
            self._set_in_app_launcher_buttons(True)
        except Exception:
            self._close_in_app_player()
            raise
        self._refresh_in_app_audio_tracks()
        self._refresh_in_app_subtitle_tracks()
        self._draw_in_app_timeline()
        self._poll_in_app_playback()
        self._show_in_app_controls()
        self._in_app_pointer_after = self.root.after(
            150,
            self._poll_in_app_pointer,
        )

    def _prepare_bundled_vlc_runtime(self) -> None:
        global _VLC_DLL_DIRECTORY

        if sys.platform != "win32":
            return
        app_directory = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
        candidates = [app_directory / "VLC"]
        for program_files in (
            os.environ.get("ProgramFiles", "C:/Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
        ):
            candidates.append(Path(program_files) / "VideoLAN" / "VLC")
        vlc_executable = shutil.which("vlc")
        if vlc_executable:
            candidates.append(Path(vlc_executable).resolve().parent)

        vlc_directory = next(
            (
                candidate for candidate in candidates
                if (candidate / "libvlc.dll").is_file()
                and (candidate / "plugins").is_dir()
            ),
            None,
        )
        if vlc_directory is None:
            return

        plugin_directory = vlc_directory / "plugins"
        libvlc_path = vlc_directory / "libvlc.dll"
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
        self._in_app_duration_ms = duration
        self._in_app_duration.set(self._format_in_app_time(duration))
        self._in_app_current_time.set(self._format_in_app_time(current_time))
        if duration > 0 and player.is_seekable() and not self._in_app_seeking:
            self._in_app_position_var.set(min(100, current_time * 100 / duration))
        self._draw_in_app_timeline()
        self._in_app_audio_refresh_ticks = (
            getattr(self, "_in_app_audio_refresh_ticks", 0) + 1
        )
        if self._in_app_audio_refresh_ticks % 4 == 0:
            self._refresh_in_app_audio_tracks()
            self._refresh_in_app_subtitle_tracks()
        if state == vlc.State.Ended:
            self._in_app_playback_button.configure(text="▶")
            self._set_in_app_launcher_buttons(False)
            self._set_in_app_player_status(self._t("Playback finished"))
            self._show_in_app_controls()
            return
        if state == vlc.State.Error:
            self._in_app_playback_button.configure(text="▶")
            self._set_in_app_launcher_buttons(False)
            self._set_in_app_player_status(self._t("Playback failed"))
            self._show_in_app_controls()
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

    def _draw_in_app_timeline(self) -> None:
        timeline = getattr(self, "_in_app_timeline", None)
        if timeline is None:
            return
        width = max(1, timeline.winfo_width())
        height = max(1, timeline.winfo_height())
        start = 5
        end = max(start + 1, width - 5)
        center_y = height / 2
        active = (
            getattr(self, "_in_app_timeline_hover", False)
            or getattr(self, "_in_app_seeking", False)
        )
        thickness = 8 if active else 4
        timeline.delete("all")
        timeline.create_line(
            start,
            center_y,
            end,
            center_y,
            fill="#707070",
            width=thickness,
            capstyle="round",
        )
        position_var = getattr(self, "_in_app_position_var", None)
        progress = (
            max(0.0, min(100.0, float(position_var.get())))
            if position_var is not None
            else 0.0
        )
        played_end = start + (end - start) * progress / 100
        if played_end > start:
            timeline.create_line(
                start,
                center_y,
                played_end,
                center_y,
                fill="#FF3333",
                width=thickness,
                capstyle="butt",
            )
        if active:
            radius = 6
            timeline.create_oval(
                played_end - radius,
                center_y - radius,
                played_end + radius,
                center_y + radius,
                fill="#FFFFFF",
                outline="#FFFFFF",
            )

    def _set_in_app_timeline_hover(self, hovering: bool) -> None:
        self._in_app_timeline_hover = hovering
        self._draw_in_app_timeline()
        if hovering:
            self._cancel_in_app_controls_hide()
        else:
            self._show_in_app_controls()

    def _set_in_app_seek_from_event(self, event) -> None:
        timeline = getattr(self, "_in_app_timeline", None)
        if timeline is None:
            return
        width = max(1, timeline.winfo_width())
        usable_width = max(1, width - 10)
        position = (float(event.x) - 5) * 100 / usable_width
        position = max(0.0, min(100.0, position))
        self._in_app_position_var.set(position)
        current_time = getattr(self, "_in_app_current_time", None)
        duration_ms = getattr(self, "_in_app_duration_ms", 0)
        if current_time is not None and duration_ms > 0:
            current_time.set(
                self._format_in_app_time(round(duration_ms * position / 100))
            )
        self._draw_in_app_timeline()

    def _begin_in_app_seek(self, event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is None or self._in_app_duration_ms <= 0 or not player.is_seekable():
            return
        self._in_app_seeking = True
        self._in_app_control_interaction = True
        self._cancel_in_app_controls_hide()
        if event is not None:
            self._set_in_app_seek_from_event(event)

    def _update_in_app_seek(self, event=None) -> None:
        if not self._in_app_seeking:
            return
        if event is not None:
            self._set_in_app_seek_from_event(event)

    def _seek_in_app_player(self, event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is not None and self._in_app_seeking:
            if event is not None:
                self._set_in_app_seek_from_event(event)
            duration = max(0, player.get_length())
            if duration > 0 and player.is_seekable():
                position = max(0.0, min(100.0, float(self._in_app_position_var.get())))
                player.set_time(round(duration * position / 100))
        self._in_app_seeking = False
        self._in_app_control_interaction = False
        self._draw_in_app_timeline()
        self._show_in_app_controls()

    def _begin_in_app_control_interaction(self, _event=None) -> None:
        self._in_app_control_interaction = True
        self._cancel_in_app_controls_hide()
        self._show_in_app_controls()

    def _end_in_app_control_interaction(self, _event=None) -> None:
        self._in_app_control_interaction = False
        self._show_in_app_controls()

    def _show_in_app_controls(self, _event=None) -> None:
        overlay = getattr(self, "_in_app_controls_overlay", None)
        overlay_window = getattr(self, "_in_app_controls_overlay_window", None)
        if overlay is None or overlay_window is None:
            return
        top_window = getattr(self, "_in_app_top_controls_overlay_window", None)
        if not getattr(self, "_in_app_controls_visible", False):
            self._in_app_controls_opacity = 0.0
            for control_window in (overlay_window, top_window):
                if control_window is not None:
                    control_window.attributes("-alpha", 0.0)
            self._in_app_controls_visible = True
        overlay_window.deiconify()
        if top_window is not None:
            if getattr(self, "_in_app_fullscreen", False):
                top_window.deiconify()
            else:
                top_window.withdraw()
        self._raise_in_app_controls_overlay()
        if getattr(self, "_in_app_controls_opacity", 0.0) < 0.92:
            self._start_in_app_controls_fade(0.92)
        self._schedule_in_app_controls_hide()

    def _cancel_in_app_controls_hide(self) -> None:
        after_id = getattr(self, "_in_app_controls_after", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self._in_app_controls_after = None

    def _cancel_in_app_controls_fade(self) -> None:
        after_id = getattr(self, "_in_app_controls_fade_after", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self._in_app_controls_fade_after = None

    def _start_in_app_controls_fade(self, target: float) -> None:
        self._cancel_in_app_controls_fade()
        self._in_app_controls_fade_target = target
        self._in_app_controls_fade_remaining = 4
        self._advance_in_app_controls_fade()

    def _advance_in_app_controls_fade(self) -> None:
        overlay_window = getattr(self, "_in_app_controls_overlay_window", None)
        if overlay_window is None:
            self._in_app_controls_fade_after = None
            return
        top_window = getattr(self, "_in_app_top_controls_overlay_window", None)
        remaining = self._in_app_controls_fade_remaining
        target = self._in_app_controls_fade_target
        current = self._in_app_controls_opacity
        self._in_app_controls_opacity = current + (target - current) / remaining
        for control_window in (overlay_window, top_window):
            if control_window is not None:
                control_window.attributes("-alpha", self._in_app_controls_opacity)
        self._in_app_controls_fade_remaining = remaining - 1
        if self._in_app_controls_fade_remaining == 0:
            self._in_app_controls_fade_after = None
            if target == 0.0:
                for control_window in (overlay_window, top_window):
                    if control_window is not None:
                        control_window.withdraw()
                self._in_app_controls_visible = False
            return
        self._in_app_controls_fade_after = self.root.after(
            40,
            self._advance_in_app_controls_fade,
        )

    def _schedule_in_app_controls_hide(self) -> None:
        self._cancel_in_app_controls_hide()
        player = getattr(self, "_in_app_player", None)
        if (
            player is None
            or not player.is_playing()
            or self._in_app_seeking
            or self._in_app_control_interaction
            or getattr(self, "_in_app_timeline_hover", False)
        ):
            return
        self._in_app_controls_after = self.root.after(
            5000,
            self._hide_in_app_controls,
        )

    def _hide_in_app_controls(self) -> None:
        self._in_app_controls_after = None
        player = getattr(self, "_in_app_player", None)
        if player is None or not player.is_playing():
            self._show_in_app_controls()
            return
        if (
            self._in_app_seeking
            or self._in_app_control_interaction
            or getattr(self, "_in_app_timeline_hover", False)
        ):
            return
        self._start_in_app_controls_fade(0.0)

    def _left_mouse_button_down(self) -> bool:
        if sys.platform != "win32":
            return False
        import ctypes

        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)

    def _poll_in_app_pointer(self) -> None:
        window = getattr(self, "_in_app_player_window", None)
        if window is None:
            return
        try:
            if not window.winfo_exists():
                return
            pointer = (window.winfo_pointerx(), window.winfo_pointery())
            left = window.winfo_rootx()
            top = window.winfo_rooty()
            inside = (
                left <= pointer[0] < left + window.winfo_width()
                and top <= pointer[1] < top + window.winfo_height()
            )
            pressed = self._left_mouse_button_down()
            moved = pointer != self._in_app_last_pointer
            if inside and (moved or (pressed and not self._in_app_pointer_down)):
                self._show_in_app_controls()
            if inside and pressed:
                self._in_app_control_interaction = True
                self._cancel_in_app_controls_hide()
            if self._in_app_pointer_down and not pressed:
                self._in_app_control_interaction = False
                self._show_in_app_controls()
            self._in_app_last_pointer = pointer
            self._in_app_pointer_down = pressed
            self._in_app_pointer_after = self.root.after(
                150,
                self._poll_in_app_pointer,
            )
        except tk.TclError:
            return

    def _raise_in_app_controls_overlay(self, _event=None) -> None:
        overlay = getattr(self, "_in_app_controls_overlay", None)
        overlay_window = getattr(self, "_in_app_controls_overlay_window", None)
        top_overlay = getattr(self, "_in_app_top_controls_overlay", None)
        top_window = getattr(self, "_in_app_top_controls_overlay_window", None)
        surface = getattr(self, "_in_app_video_surface", None)
        if (
            overlay is None
            or overlay_window is None
            or surface is None
            or not getattr(self, "_in_app_controls_visible", False)
        ):
            return
        width = max(1, surface.winfo_width())
        height = max(1, overlay.winfo_reqheight())
        x = surface.winfo_rootx()
        surface_y = surface.winfo_rooty()
        surface_height = surface.winfo_height()
        bottom_y = surface_y + surface_height - height
        overlay_window.geometry(f"{width}x{height}{x:+d}{bottom_y:+d}")
        overlay_window.lift()
        if top_overlay is not None and top_window is not None:
            if getattr(self, "_in_app_fullscreen", False):
                top_height = max(1, top_overlay.winfo_reqheight())
                top_window.geometry(f"{width}x{top_height}{x:+d}{surface_y:+d}")
                top_window.lift()
            else:
                top_window.withdraw()

    def _toggle_in_app_playback(self) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is None:
            return
        if player.is_playing():
            player.pause()
            label = self._t("Play")
            status = self._t("Playback paused")
            self._set_in_app_launcher_buttons(False)
        else:
            player.play()
            label = self._t("Pause")
            status = self._t("Playback started")
            self._set_in_app_launcher_buttons(True)
        button = getattr(self, "_in_app_playback_button", None)
        if button is not None:
            button.configure(text="▶" if label == self._t("Play") else "Ⅱ")
        self._set_in_app_player_status(status)
        self._show_in_app_controls()

    def _set_in_app_launcher_buttons(self, playing: bool) -> None:
        label = self._t("Pause in app") if playing else self._t("Play in app")
        for name in ("_play_in_app_button", "_open_smart_vlc_button"):
            button = getattr(self, name, None)
            if button is not None:
                button.configure(text=label)

    def _toggle_in_app_playback_from_key(self, event=None) -> str:
        widget = getattr(event, "widget", None)
        if widget is not None:
            try:
                widget_class = widget.winfo_class()
            except tk.TclError:
                widget_class = ""
            if widget_class in {
                "Button", "TButton", "Scale", "TScale", "Entry", "TEntry",
                "TCombobox", "Spinbox", "TSpinbox", "Text",
            }:
                return None
        if getattr(self, "_in_app_player", None) is not None:
            self._toggle_in_app_playback()
            return "break"
        return None

    def _set_in_app_playback_rate(self, _event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        rate_var = getattr(self, "_in_app_playback_rate", None)
        if player is None or rate_var is None:
            return
        self._show_in_app_controls()
        selected_rate = rate_var.get()
        try:
            rate = float(selected_rate.removesuffix("x"))
        except ValueError:
            messagebox.showerror(
                self._t("Invalid playback speed"),
                self._t("Choose one of the available playback speeds."),
                parent=self._in_app_player_window,
            )
            return
        if selected_rate not in _IN_APP_PLAYBACK_RATES:
            messagebox.showerror(
                self._t("Invalid playback speed"),
                self._t("Choose one of the available playback speeds."),
                parent=self._in_app_player_window,
            )
            return
        if player.set_rate(rate) == -1:
            current_rate = player.get_rate()
            restored_rate = next(
                (
                    option
                    for option in _IN_APP_PLAYBACK_RATES
                    if float(option.removesuffix("x")) == current_rate
                ),
                f"{current_rate:g}x",
            )
            rate_var.set(restored_rate)
            messagebox.showerror(
                self._t("Playback speed unavailable"),
                self._t("VLC could not change the playback speed."),
                parent=self._in_app_player_window,
            )

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
        variable = getattr(self, "_in_app_audio_track", None)
        if player is None or variable is None:
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
        if not track_labels:
            variable.set("")
            return

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

    def _refresh_in_app_subtitle_tracks(self) -> None:
        player = getattr(self, "_in_app_player", None)
        variable = getattr(self, "_in_app_subtitle_track", None)
        button = getattr(self, "_in_app_cc_button", None)
        if player is None or variable is None or button is None:
            return

        descriptions = player.video_get_spu_description() or []
        subtitle_tracks: dict[str, int] = {}
        for track_id, description in descriptions:
            track_id = int(track_id)
            if track_id < 0:
                continue
            if isinstance(description, bytes):
                name = description.decode("utf-8", errors="replace")
            else:
                name = str(description)
            label = name or self._t("Subtitles")
            if label.strip().lower() in {"disable", "off", "none"}:
                continue
            if label in subtitle_tracks:
                label = f"{label} ({track_id})"
            subtitle_tracks[label] = track_id

        self._in_app_subtitle_tracks = subtitle_tracks
        self._in_app_subtitle_tracks_loaded = True
        if not subtitle_tracks:
            variable.set(self._t("Off"))
            button.grid_remove()
            return

        button.grid()
        active_track = player.video_get_spu()
        selected = next(
            (
                label
                for label, track_id in subtitle_tracks.items()
                if track_id == active_track
            ),
            self._t("Off"),
        )
        variable.set(selected)
        button.configure(
            foreground="#FF3333" if active_track >= 0 else "#FFFFFF"
        )

    def _select_in_app_audio_track(self, _event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        variable = getattr(self, "_in_app_audio_track", None)
        if player is None or variable is None:
            return
        self._show_in_app_controls()
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

    def _set_in_app_subtitle_track(self, _event=None) -> None:
        player = getattr(self, "_in_app_player", None)
        variable = getattr(self, "_in_app_subtitle_track", None)
        if player is None or variable is None:
            return
        self._show_in_app_controls()
        if variable.get() == self._t("Off"):
            self._disable_in_app_subtitles()
            return
        track_id = (getattr(self, "_in_app_subtitle_tracks", None) or {}).get(
            variable.get()
        )
        if track_id is None:
            return
        if player.video_set_spu(track_id) == -1:
            messagebox.showerror(
                self._t("Subtitle track unavailable"),
                self._t("VLC could not select this subtitle track."),
                parent=self._in_app_player_window,
            )
            self._refresh_in_app_subtitle_tracks()
            return
        self._refresh_in_app_subtitle_tracks()

    def _disable_in_app_subtitles(self) -> None:
        player = getattr(self, "_in_app_player", None)
        variable = getattr(self, "_in_app_subtitle_track", None)
        button = getattr(self, "_in_app_cc_button", None)
        if player is None or variable is None:
            return
        self._show_in_app_controls()
        if player.video_get_spu() < 0:
            variable.set(self._t("Off"))
            if button is not None:
                button.configure(foreground="#FFFFFF")
            return
        if player.video_set_spu(-1) == -1:
            messagebox.showerror(
                self._t("Subtitle track unavailable"),
                self._t("VLC could not change subtitle visibility."),
                parent=self._in_app_player_window,
            )
            return
        variable.set(self._t("Off"))
        if button is not None:
            button.configure(foreground="#FFFFFF")

    def _toggle_in_app_subtitles(self) -> None:
        player = getattr(self, "_in_app_player", None)
        variable = getattr(self, "_in_app_subtitle_track", None)
        tracks = getattr(self, "_in_app_subtitle_tracks", {})
        if player is None or variable is None or not tracks:
            return
        self._show_in_app_controls()
        if player.video_get_spu() >= 0:
            self._disable_in_app_subtitles()
            return
        selected = variable.get()
        if selected not in tracks:
            selected = next(iter(tracks))
        variable.set(selected)
        self._set_in_app_subtitle_track()

    def _show_in_app_settings_menu(self, button=None) -> None:
        if button is None or not getattr(self, "_in_app_player_window", None):
            return
        self._begin_in_app_control_interaction()
        self._refresh_in_app_audio_tracks()
        self._refresh_in_app_subtitle_tracks()
        menu = tk.Menu(
            self._in_app_player_window,
            tearoff=False,
            background="#202020",
            foreground="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
        )
        speed_menu = tk.Menu(
            menu,
            tearoff=False,
            background="#202020",
            foreground="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
        )
        for rate in _IN_APP_PLAYBACK_RATES:
            speed_menu.add_radiobutton(
                label=rate,
                variable=self._in_app_playback_rate,
                value=rate,
                command=self._set_in_app_playback_rate,
            )
        menu.add_cascade(
            label=self._t("Playback speed"),
            menu=speed_menu,
        )

        audio_menu = tk.Menu(
            menu,
            tearoff=False,
            background="#202020",
            foreground="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
        )
        if self._in_app_audio_tracks:
            for label in self._in_app_audio_tracks:
                audio_menu.add_radiobutton(
                    label=label,
                    variable=self._in_app_audio_track,
                    value=label,
                    command=self._select_in_app_audio_track,
                )
        else:
            audio_menu.add_command(
                label=self._t("No audio tracks available"),
                state="disabled",
            )
        menu.add_cascade(
            label=self._t("Audio track"),
            menu=audio_menu,
        )

        subtitle_menu = tk.Menu(
            menu,
            tearoff=False,
            background="#202020",
            foreground="#FFFFFF",
            activebackground="#333333",
            activeforeground="#FFFFFF",
        )
        subtitle_menu.add_radiobutton(
            label=self._t("Off"),
            variable=self._in_app_subtitle_track,
            value=self._t("Off"),
            command=self._disable_in_app_subtitles,
        )
        for label in self._in_app_subtitle_tracks:
            subtitle_menu.add_radiobutton(
                label=label,
                variable=self._in_app_subtitle_track,
                value=label,
                command=self._set_in_app_subtitle_track,
            )
        menu.add_cascade(
            label=self._t("Subtitles"),
            menu=subtitle_menu,
        )

        try:
            menu.tk_popup(
                button.winfo_rootx(),
                max(0, button.winfo_rooty() - menu.winfo_reqheight()),
            )
        finally:
            menu.grab_release()
            menu.destroy()
            self._end_in_app_control_interaction()

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
        self._show_in_app_controls()
        window.after(150, self._refresh_in_app_video_target)
        return "break"

    def _exit_in_app_fullscreen(self, _event=None) -> str:
        if not getattr(self, "_in_app_fullscreen", False):
            return "break"
        window = getattr(self, "_in_app_player_window", None)
        self._in_app_fullscreen = False
        if window is not None:
            window.attributes("-fullscreen", False)
            window.after(150, self._refresh_in_app_video_target)
            self._show_in_app_controls()
        button = getattr(self, "_in_app_fullscreen_button", None)
        if button is not None:
            button.configure(text="⛶")
        return "break"

    def _refresh_in_app_video_target(self) -> None:
        window = getattr(self, "_in_app_player_window", None)
        surface = getattr(self, "_in_app_video_surface", None)
        player = getattr(self, "_in_app_player", None)
        if window is None or surface is None or player is None:
            return
        try:
            if not window.winfo_exists() or not surface.winfo_exists():
                return
        except tk.TclError:
            return
        window.update_idletasks()
        self._set_in_app_video_target(surface)
        self._raise_in_app_controls_overlay()

    def _show_in_app_player_help(self) -> None:
        messagebox.showinfo(
            self._t("Media player help"),
            self._t(
                "Playback opens in a separate Smart VLC window, so the downloader "
                "preview remains available. Use Full screen or F11 to expand the "
                "player without changing the main app window. Press Escape or F11 "
                "to return to windowed playback. Use the timeline to seek, and "
                "the controls to pause, stop, or change volume. Select playback "
                "speed, audio tracks, and subtitles from Settings. Close player "
                "to stop playback and close the player window."
            ),
            parent=self.root,
        )

    def _stop_in_app_player(self) -> None:
        player = getattr(self, "_in_app_player", None)
        if player is not None:
            player.stop()
        self._set_in_app_launcher_buttons(False)
        playback_button = getattr(self, "_in_app_playback_button", None)
        if playback_button is not None:
            playback_button.configure(text="▶")
        status = getattr(self, "_in_app_player_status", None)
        if status is not None:
            self._set_in_app_player_status(self._t("Playback stopped"))
        self._show_in_app_controls()

    def _close_in_app_player(self) -> None:
        window = getattr(self, "_in_app_player_window", None)
        if window is not None:
            if getattr(self, "_in_app_fullscreen", False):
                self._exit_in_app_fullscreen()
        for attribute in (
            "_in_app_playback_after",
            "_in_app_controls_after",
            "_in_app_controls_fade_after",
            "_in_app_pointer_after",
        ):
            after_id = getattr(self, attribute, None)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
            setattr(self, attribute, None)
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
        self._in_app_media_path = None
        self._set_in_app_launcher_buttons(False)
        controls_window = getattr(self, "_in_app_controls_overlay_window", None)
        if controls_window is not None:
            try:
                controls_window.destroy()
            except tk.TclError:
                pass
        self._in_app_controls_overlay_window = None
        top_window = getattr(self, "_in_app_top_controls_overlay_window", None)
        if top_window is not None:
            try:
                top_window.destroy()
            except tk.TclError:
                pass
        self._in_app_top_controls_overlay_window = None
        self._in_app_vlc = None
        self._in_app_playback_after = None
        self._in_app_audio_tracks = {}
        self._in_app_audio_tracks_loaded = False
        self._in_app_audio_track = None
        self._in_app_subtitle_tracks = {}
        self._in_app_subtitle_tracks_loaded = False
        self._in_app_subtitle_track = None
        self._in_app_cc_button = None
        self._in_app_fullscreen = False
        self._in_app_playback_button = None
        self._in_app_player_status = None
        self._in_app_player_status_text = None
        self._in_app_fullscreen_button = None
        self._in_app_video_surface = None
        self._in_app_controls_overlay = None
        self._in_app_top_controls_overlay = None
        self._in_app_top_back_button = None
        self._in_app_top_title_label = None
        self._in_app_top_settings_button = None
        self._in_app_settings_button = None
        self._in_app_timeline = None
        self._in_app_controls_visible = False
        self._in_app_volume_var = None
        self._in_app_position_var = None
        self._in_app_seeking = False
        self._in_app_control_interaction = False
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
        self._refresh_preview_video_choices()
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
        if media_kind == "VIDEO":
            self._show_video_preview(path)
        else:
            self._clear_video_preview()
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
        self._clear_video_preview()
        if not selected:
            self._refresh_preview_video_choices()
            self.inspector_status.set(self._t("No item selected"))
            self._clear_thumbnail(
                "Select a video task or choose Browse local media to preview a video."
            )
            return
        job_id = selected[0]
        path = self._selected_output_path()
        if path is None:
            path = self._download_paths.get(job_id)
        values = self.jobs.item(job_id, "values")
        status = values[0] if values else "Unknown"
        progress = values[1] if len(values) > 1 else "—"
        self.inspector_status.set(status)
        video_paths = self._refresh_preview_video_choices()
        if path is None or not path.is_file():
            completed_videos = [
                candidate
                for candidate in video_paths
                if candidate.suffix.lower() in VIDEO_MEDIA_EXTENSIONS
            ]
            if completed_videos:
                path = completed_videos[0]
            elif video_paths:
                candidate = video_paths[0]
                label = next(
                    (
                        label for label, choice_path
                        in self._preview_video_choices.items()
                        if choice_path == candidate
                    ),
                    "",
                )
                self.preview_video_choice.set(label)
                self.preview_image_label.configure(
                    image="",
                    text=(
                        f"{status}\n"
                        f"{candidate.name}\n"
                        f"{self._t('Video is still downloading')}"
                    ),
                )
                self.preview_details.configure(text=str(candidate))
                return
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
            if media_kind == "VIDEO":
                self._show_video_preview(path)
            else:
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
        self._clear_video_preview()
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
