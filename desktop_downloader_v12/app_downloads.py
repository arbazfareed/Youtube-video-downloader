from __future__ import annotations

from app_support import (
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
    tk,
    datetime,
    Path,
    filedialog,
    messagebox,
    ttk,
    urlsplit,
    is_configured,
    SUPPORTED_BROWSERS,
    download_url,
    generate_sequence_urls,
    parse_proxy_list,
    parse_custom_headers,
    RetryPolicy,
    is_torrent_url,
    MAX_SPEEDS,
)

class DownloadsMixin:
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
        source = self.source.get().lower()
        torrent_selected = source in {"torrent/magnet", "torrent"}

        try:
            parsed_url = urlsplit(url)
            torrent_url = is_torrent_url(url)
        except ValueError:
            messagebox.showerror(
                "Invalid link",
                "Enter a valid HTTP(S) link or magnet URI.",
            )
            return
        if torrent_selected and not torrent_url:
            messagebox.showerror(
                "Invalid torrent link",
                "Enter a magnet URI or a direct HTTP(S) .torrent link.",
            )
            return
        if not torrent_selected and not torrent_url and (
            parsed_url.scheme.lower() not in {"http", "https"}
            or not parsed_url.hostname
        ):
            messagebox.showerror(
                "Invalid link",
                "Enter a valid HTTP(S) link, or choose Torrent/magnet for a torrent link.",
            )
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
        proxy_setting = getattr(self, "proxy_list", None)
        proxy_value = proxy_setting.get().strip() if proxy_setting else ""
        if browser_cookies != "none" and browser_cookies not in SUPPORTED_BROWSERS:
            messagebox.showerror("Invalid browser", "Choose a supported browser for cookies.")
            return
        if (torrent_selected or torrent_url) and (
            proxy_value or browser_cookies != "none"
        ):
            messagebox.showerror(
                "Unsupported torrent option",
                "Proxies and browser cookies are not supported for torrent downloads.",
            )
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
            parse_proxy_list(proxy_value)
            custom_headers = parse_custom_headers(
                self.custom_headers_text.get("1.0", "end-1c").splitlines()
                if hasattr(self, "custom_headers_text")
                else ()
            )
            retry_policy = RetryPolicy(
                int(self.retry_attempts.get()) if hasattr(self, "retry_attempts") else 10,
                float(self.retry_base_delay.get()) if hasattr(self, "retry_base_delay") else 1.0,
                float(self.retry_max_delay.get()) if hasattr(self, "retry_max_delay") else 30.0,
            )
            if (torrent_selected or torrent_url) and custom_headers:
                raise ValueError("Custom HTTP headers are not supported for torrent downloads.")
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
        try:
            job_id = str(self.history.add(url, status, job_destination))
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
        self.download_options[job_id] = {
            "url": url,
            "destination": destination,
            "source": source,
            "mode": self.mode.get().lower(),
            "quality": quality,
            "playlist_scope": self.playlist_scope.get().lower(),
            "speed_mode": self.speed_mode.get().lower(),
            "max_speed": max_speed,
            "checksum_algorithm": checksum_algorithm,
            "expected_checksum": expected_checksum,
            "proxy": proxy_value,
            "browser_cookies": browser_cookies,
            "custom_headers": custom_headers,
            "retry_policy": retry_policy,
            "auto_extract": getattr(self, "auto_extract", None).get()
            if getattr(self, "auto_extract", None)
            else False,
            "cloud_provider": cloud_provider,
            "cloud_folder": cloud_folder,
        }
        self.history.set_setting("retry_attempts", str(retry_policy.attempts))
        self.history.set_setting("retry_base_delay", str(retry_policy.base_delay))
        self.history.set_setting("retry_max_delay", str(retry_policy.max_delay))
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
            custom_headers=options.get("custom_headers", {}),
            retry_policy=options.get("retry_policy", RetryPolicy()),
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

    def resume_selected(self) -> None:
        selected = self.jobs.selection()
        if not selected:
            messagebox.showinfo(
                "Select a download",
                "Select an interrupted or failed download first.",
                parent=self.root,
            )
            return
        job_id = selected[0]
        status = self.jobs.set(job_id, "status")
        if status not in {"Interrupted", "Failed", "Cancelled"}:
            messagebox.showinfo(
                "Download cannot be resumed",
                "Choose a failed, cancelled, or interrupted download to retry.",
                parent=self.root,
            )
            return
        if job_id in self._resume_errors:
            messagebox.showerror(
                "Cannot resume download",
                self._resume_errors[job_id],
                parent=self.root,
            )
            return
        options = self.download_options.get(job_id)
        if options is None:
            messagebox.showerror(
                "Cannot resume download",
                "This history entry has no saved download information. "
                "Add the link again to start a new download.",
                parent=self.root,
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
        self.progress_summary.set(
            "Retrying download; any supported partial data will be resumed."
        )
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
            "Smart Downloader 12.0 help",
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
            "Torrent links need aria2 to be installed. Only public links and content you "
            "have permission to save are supported. Some sites may block downloads or "
            "require unavailable sign-in.",
        )

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
