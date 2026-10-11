from __future__ import annotations

from app_support import (
    Path,
    messagebox,
    normalize_url,
    FINISHED_STATUSES,
    MEDIA_EXTENSIONS,
)

class QueueMixin:
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
        elif status in {"Downloading", "Recording live stream"}:
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
            saved_output = options.get("output_path")
            saved_destination = options.get("destination", record.destination)
            self._download_paths[job_id] = Path(
                saved_output or saved_destination
            )
            self._job_destinations[job_id] = record.destination
            if record.destination.startswith(
                ("Amazon S3 /", "Google Drive /", "Dropbox /")
            ):
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
            saved_output = options.get("output_path")
            saved_destination = options.get("destination", record.destination)
            self._download_paths[job_id] = Path(
                saved_output or saved_destination
            )
            self._job_destinations[job_id] = record.destination
            if record.destination.startswith(
                ("Amazon S3 /", "Google Drive /", "Dropbox /")
            ):
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

    def _has_pending_duplicate(self, url: str) -> bool:
        normalized = normalize_url(url)
        return any(
            self.jobs.exists(job_id)
            and
            self.jobs.set(job_id, "status") not in FINISHED_STATUSES
            and normalize_url(self.jobs.set(job_id, "link")) == normalized
            for job_id in self._queue_job_ids
        )

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

    def _persistent_job_options(self, job_id: str, options: dict) -> dict:
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
        destination = saved.get(
            "destination",
            record.destination if cloud_provider == "local" else "",
        )
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
            self._job_destinations.pop(job_id, None)
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
