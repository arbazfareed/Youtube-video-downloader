from __future__ import annotations

from app_support import (
    json,
    webbrowser,
    tk,
    Path,
    filedialog,
    messagebox,
    simpledialog,
    ttk,
    urlsplit,
    save_credentials,
    is_torrent_url,
    MAX_SPEEDS,
    record_diagnostic,
    diagnostics_path,
    export_diagnostics,
    NoPublishedReleaseError,
    UpdateError,
    check_for_update,
    download_verified_update,
    LANGUAGES,
    APP_VERSION,
)

class PreferencesMixin:
    def _save_language_preference(self, *_args: object) -> None:
        language = self.language.get()
        if language not in LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        self.history.set_setting("language", language)
        messagebox.showinfo(
            "Language saved",
            "Restart Smart Downloader to apply the selected language.",
            parent=self.settings_window,
        )

    def _save_accessibility_preferences(self) -> None:
        self.history.set_setting("large_text", "1" if self.large_text.get() else "0")
        self.history.set_setting(
            "high_contrast", "1" if self.high_contrast.get() else "0"
        )
        self._apply_theme()

    def _save_update_preference(self) -> None:
        self.history.set_setting(
            "check_updates", "1" if self.check_updates.get() else "0"
        )

    def _save_diagnostics_preference(self) -> None:
        self._diagnostics_enabled = self.diagnostics_enabled.get()
        self.history.set_setting(
            "diagnostics_enabled",
            "1" if self._diagnostics_enabled else "0",
        )

    def _capture_diagnostic(self, component: str, error: BaseException) -> None:
        try:
            record_diagnostic(
                getattr(self, "_diagnostics_enabled", False),
                component,
                error,
            )
        except OSError as write_error:
            self.events.put(("diagnostic_failed", str(write_error)))

    def _export_local_diagnostics(self) -> None:
        destination_name = filedialog.asksaveasfilename(
            parent=self.settings_window,
            title="Export local diagnostics",
            defaultextension=".jsonl",
            filetypes=(("JSON Lines", "*.jsonl"),),
        )
        if not destination_name:
            return
        try:
            exported = export_diagnostics(Path(destination_name))
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Could not export diagnostics", str(error), parent=self.settings_window
            )
            return
        messagebox.showinfo(
            "Diagnostics exported",
            f"Saved local diagnostic events to:\n{exported}",
            parent=self.settings_window,
        )

    def _check_for_updates(self, *, interactive: bool) -> None:
        if getattr(self, "_update_check_active", False):
            return
        self._update_check_active = True
        if interactive:
            self.progress_summary.set("Checking for updates…")
        try:
            future = self.executor.submit(check_for_update, APP_VERSION)
        except RuntimeError as error:
            self._update_check_active = False
            self._capture_diagnostic("update check", error)
            messagebox.showerror("Update check failed", str(error), parent=self.root)
            return

        def poll() -> None:
            if not future.done():
                self.root.after(100, poll)
                return
            self._update_check_active = False
            try:
                update = future.result()
            except NoPublishedReleaseError as error:
                self.progress_summary.set(str(error))
                if interactive:
                    messagebox.showinfo(
                        "No release published yet", str(error), parent=self.root
                    )
                return
            except (UpdateError, OSError) as error:
                self._capture_diagnostic("update check", error)
                self.progress_summary.set(f"Update check failed: {error}")
                if interactive:
                    messagebox.showerror(
                        "Update check failed", str(error), parent=self.root
                    )
                return
            if update is None:
                self.progress_summary.set("Smart Downloader is up to date.")
                if interactive:
                    messagebox.showinfo(
                        "No update available",
                        "You are using the latest release.",
                        parent=self.root,
                    )
                return
            if messagebox.askyesno(
                "Update available",
                f"Version {update.version} is available. Download it now?\n\n"
                "The package SHA-256 will be verified before it is saved. "
                "Diagnostics are never included.",
                parent=self.root,
            ):
                self._download_update(update)

        self.root.after(100, poll)

    def _download_update(self, update) -> None:
        updates_directory = diagnostics_path().parent / "updates"
        filename = f"SmartDownloader13-{update.version}.zip"
        destination = updates_directory / filename
        self.progress_summary.set(f"Downloading verified update {update.version}…")
        future = self.executor.submit(download_verified_update, update, destination)

        def poll() -> None:
            if not future.done():
                self.root.after(100, poll)
                return
            try:
                package = future.result()
            except (UpdateError, OSError) as error:
                self._capture_diagnostic("update download", error)
                self.progress_summary.set(f"Update download failed: {error}")
                messagebox.showerror("Update download failed", str(error), parent=self.root)
                return
            self.progress_summary.set(f"Verified update saved to {package}")
            messagebox.showinfo(
                "Update verified",
                f"The release package passed SHA-256 verification and was saved to:\n"
                f"{package}\n\nClose the app, extract the ZIP, and replace the "
                "portable app files to finish updating.",
                parent=self.root,
            )

        self.root.after(100, poll)

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
                if (
                    parsed.scheme.lower() not in {"http", "https"}
                    or not parsed.hostname
                ) and not is_torrent_url(url):
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
