from __future__ import annotations

from app_support import (
    queue,
    shutil,
    Future,
    Path,
    messagebox,
    verify_checksum,
    calculate_checksum,
    select_upload_source,
    upload_path,
    DownloadCancelled,
    extract_archive,
    notify,
)

class EventsMixin:
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
            if (
                options.get("cloud_provider", "local") == "local"
                and Path(result).is_file()
            ):
                integrity_path = Path(result).resolve()
                options["integrity_path"] = str(integrity_path)
                options["integrity_sha256"] = calculate_checksum(
                    integrity_path, "sha256"
                )
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
            self._capture_diagnostic("download", error)
            self.events.put(("finished", job_id, "Failed", str(error)))
        else:
            self.events.put(("finished", job_id, "Complete", result))

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
            elif event[0] == "diagnostic_failed":
                _, error = event
                self.progress_summary.set(
                    f"Could not save local diagnostic event: {error}"
                )
            elif event[0] == "conversion_failed":
                _, error = event
                self._capture_diagnostic("media conversion", RuntimeError(error))
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
                display_detail = detail
                if self.jobs.exists(job_id):
                    self.jobs.set(job_id, "status", status)
                    if status == "Complete":
                        options = self.download_options.get(job_id, {})
                        integrity_path = options.get("integrity_path")
                        integrity_sha256 = options.get("integrity_sha256")
                        if isinstance(integrity_path, str) and isinstance(
                            integrity_sha256, str
                        ):
                            self._integrity_baselines[job_id] = (
                                Path(integrity_path),
                                integrity_sha256,
                            )
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

    def _close(self) -> None:
        for timer in self.schedule_timers.values():
            timer.cancel()
        for cancel_event in self.cancel_events.values():
            cancel_event.set()
        for resume_event in self.resume_events.values():
            resume_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()
