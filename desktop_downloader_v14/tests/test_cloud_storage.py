from __future__ import annotations

import queue
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

import cloud_storage
import api
from app import DownloaderApp


class CloudStorageTests(unittest.TestCase):
    def test_s3_credentials_use_normalized_provider_key(self):
        with patch.object(cloud_storage, "_set_secret") as set_secret:
            cloud_storage.save_credentials(
                "Amazon S3",
                {
                    "access_key": "key",
                    "secret_key": "secret",
                    "bucket": "bucket",
                    "region": "region",
                },
            )
        self.assertEqual(set_secret.call_args.args[0], "s3")

    def test_remote_folder_rejects_traversal(self):
        with self.assertRaisesRegex(ValueError, "cannot contain"):
            cloud_storage._remote_path("../outside", "file.bin")

    def test_single_file_upload_rejects_symlink_to_external_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private.txt"
            private.write_text("private data", encoding="utf-8")
            link = root / "selected.txt"
            try:
                link.symlink_to(private)
            except (OSError, NotImplementedError):
                self.skipTest("File symlinks are unavailable on this platform")

            with patch("cloud_storage._upload_s3") as upload:
                with self.assertRaisesRegex(ValueError, "cannot be symbolic links"):
                    cloud_storage.upload_path(link, "s3")
            upload.assert_not_called()

    def test_select_upload_source_rejects_symlink_result_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private.bin"
            private.write_bytes(b"private")
            link = root / "download.bin"
            try:
                link.symlink_to(private)
            except (OSError, NotImplementedError):
                self.skipTest("File symlinks are unavailable on this platform")

            with self.assertRaisesRegex(ValueError, "cannot be symbolic links"):
                cloud_storage.select_upload_source(link, root / "staging")

    def test_folder_upload_skips_symlinks_to_files_outside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected"
            selected.mkdir()
            inside = selected / "inside.txt"
            inside.write_text("inside", encoding="utf-8")
            outside = root / "private.txt"
            outside.write_text("outside", encoding="utf-8")
            link = selected / "outside-link.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("File symlinks are unavailable on this platform")

            with patch("cloud_storage._upload_s3", side_effect=lambda path, relative, prefix: relative) as upload:
                results = cloud_storage.upload_path(selected, "s3")

            self.assertEqual(results, ["inside.txt"])
            self.assertEqual(upload.call_count, 1)
            self.assertEqual(upload.call_args.args[0], inside)

    def test_folder_upload_skips_incomplete_download_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            selected = Path(directory) / "playlist"
            selected.mkdir()
            complete = selected / "episode.mp4"
            complete.write_bytes(b"complete")
            for suffix in (".part", ".ytdl", ".tmp"):
                (selected / f"episode.mp4{suffix}").write_bytes(b"incomplete")

            with patch(
                "cloud_storage._upload_s3",
                side_effect=lambda path, relative, prefix: relative,
            ) as upload:
                results = cloud_storage.upload_path(selected, "s3")

            self.assertEqual(results, ["episode.mp4"])
            self.assertEqual(upload.call_count, 1)
            self.assertEqual(upload.call_args.args[0], complete)

    def test_playlist_upload_source_includes_all_staged_files(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            staging.mkdir()
            first = staging / "first.mp4"
            first.write_bytes(b"first")
            (staging / "second.mp4").write_bytes(b"second")

            self.assertEqual(
                cloud_storage.select_upload_source(first, staging),
                staging.resolve(),
            )

    def test_cloud_completion_removes_staging_after_successful_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            staging.mkdir()
            output = staging / "file.bin"
            output.write_bytes(b"content")
            app = DownloaderApp.__new__(DownloaderApp)
            app.download_options = {
                "job": {
                    "destination": str(staging),
                    "cloud_provider": "s3",
                    "cloud_folder": "downloads",
                }
            }
            app.verified_checksums = {}
            app.events = queue.Queue()
            future = Future()
            future.set_result(str(output))

            with patch(
                "app_events.upload_path",
                return_value=["s3://bucket/downloads/file.bin"],
            ):
                app._job_finished("job", future)

            event = app.events.get_nowait()
            self.assertEqual(event[2], "Complete")
            self.assertIn("s3://bucket/downloads/file.bin", event[3])
            self.assertFalse(staging.exists())

    def test_cloud_upload_failure_reports_retained_staging_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "staging"
            staging.mkdir()
            output = staging / "file.bin"
            output.write_bytes(b"content")
            app = DownloaderApp.__new__(DownloaderApp)
            app.download_options = {
                "job": {
                    "destination": str(staging),
                    "cloud_provider": "s3",
                    "cloud_folder": "",
                }
            }
            app.verified_checksums = {}
            app.events = queue.Queue()
            future = Future()
            future.set_result(str(output))

            with patch("app_events.upload_path", side_effect=OSError("offline")):
                app._job_finished("job", future)

            event = app.events.get_nowait()
            self.assertEqual(event[2], "Failed")
            self.assertIn(str(staging), event[3])
            self.assertTrue(output.exists())


class CloudApiTests(unittest.TestCase):
    def _run_job(self, upload_error: OSError | None = None) -> tuple[api.ApiJob, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        staging = Path(temporary.name) / "staging"
        staging.mkdir()
        output = staging / "file.bin"
        output.write_bytes(b"content")
        job = api.ApiJob(
            "cloud-job",
            api.JobRequest(
                url="https://example.test/file.bin",
                output=str(staging),
                source="direct file",
                cloud_provider="s3",
            ),
        )
        upload = (
            patch("cloud_storage.upload_path", side_effect=upload_error)
            if upload_error is not None
            else patch(
                "cloud_storage.upload_path",
                return_value=["s3://bucket/file.bin"],
            )
        )
        with patch.object(api, "download_url", return_value=str(output)), upload:
            api._run_job(job)
        return job, staging

    def test_api_cloud_job_cleans_staging_after_success(self):
        job, staging = self._run_job()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.result, "s3://bucket/file.bin")
        self.assertFalse(staging.exists())

    def test_api_cloud_failure_keeps_staging(self):
        job, staging = self._run_job(OSError("offline"))
        self.assertEqual(job.status, "failed")
        self.assertIn(str(staging), job.error or "")
        self.assertTrue(staging.exists())


    def test_api_cloud_download_failure_reports_retained_staging_path(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "cloud-staging"
            staging.mkdir()
            partial = staging / "recoverable-file.part"
            job = api.ApiJob(
                "cloud-download-failure",
                api.JobRequest(
                    url="https://example.test/file.bin",
                    output=str(staging),
                    source="direct file",
                    cloud_provider="s3",
                ),
            )

            def fail_download(*_args, **_kwargs):
                partial.write_bytes(b"recoverable partial data")
                raise OSError("remote server disconnected")

            with patch.object(api, "download_url", side_effect=fail_download):
                api._run_job(job)

            self.assertEqual(job.status, "failed")
            self.assertIn(str(staging), job.error or "")
            self.assertTrue(partial.is_file())
            self.assertEqual(partial.read_bytes(), b"recoverable partial data")

    def test_api_cloud_cancellation_reports_retained_staging_path(self):
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "cloud-staging"
            staging.mkdir()
            retained = staging / "already-downloaded.mp4"
            retained.write_bytes(b"completed earlier item")
            job = api.ApiJob(
                "cloud-cancelled",
                api.JobRequest(
                    url="https://example.test/playlist",
                    output=str(staging),
                    source="direct file",
                    cloud_provider="dropbox",
                ),
            )

            with patch.object(api, "download_url", side_effect=api.DownloadCancelled("cancelled")):
                api._run_job(job)

            self.assertEqual(job.status, "cancelled")
            self.assertIn(str(staging), job.error or "")
            self.assertTrue(retained.is_file())


if __name__ == "__main__":
    unittest.main()
