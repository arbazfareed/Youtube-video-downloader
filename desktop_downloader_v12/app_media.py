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
    _convert_media_to_mp3,
)

class MediaMixin:
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
        menu.add_command(
            label="Open selected file or folder",
            command=self.open_selected_location,
        )
        menu.add_command(
            label="Play selected audio/video",
            command=self.play_selected_media,
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
        path = self._selected_output_path()
        if (
            path is None
            or not path.is_file()
            or path.suffix.lower()
            not in {".avif", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
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
        if self.jobs.identify_column(event.x) == "#4":
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
        path = self._download_paths.get(selected[0])
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
