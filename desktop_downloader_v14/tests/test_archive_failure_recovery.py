from __future__ import annotations

import queue
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from app_events import EventsMixin


class _EventsHarness(EventsMixin):
    def __init__(self, output: Path) -> None:
        self.events = queue.Queue()
        self.download_options = {
            "job-archive": {
                "auto_extract": True,
                "cloud_provider": "local",
            }
        }
        self.verified_checksums = {}
        self.diagnostics = []
        self.output = output

    def _capture_diagnostic(self, category, error):
        self.diagnostics.append((category, error))


class AutoExtractFailureRecoveryTests(unittest.TestCase):
    def test_auto_extract_error_preserves_download_and_finishes_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "downloaded.zip"
            archive.write_bytes(b"valid downloaded bytes")
            harness = _EventsHarness(archive)
            future = Future()
            future.set_result(str(archive))

            with patch("media_health.inspect_download", return_value=(True, "ok")), patch(
                "app_events.calculate_checksum", return_value="verified-hash"
            ), patch(
                "app_events.extract_archive",
                side_effect=RuntimeError("unsupported compression method"),
            ) as extract:
                harness._job_finished("job-archive", future)

            extract.assert_called_once_with(archive)
            queued = []
            while not harness.events.empty():
                queued.append(harness.events.get_nowait())

            finished = next(item for item in queued if item[0] == "finished")
            self.assertEqual(
                finished[2],
                "Partial",
                f"Expected preserved partial completion; queued events: {queued!r}",
            )
            warning = next(item for item in queued if item[0] == "archive_extract_warning")
            self.assertEqual(finished, ("finished", "job-archive", "Partial", str(archive)))
            self.assertIn(str(archive), warning[2])
            self.assertIn("retry extraction manually", warning[2])
            self.assertEqual(archive.read_bytes(), b"valid downloaded bytes")
            self.assertEqual(harness.diagnostics, [])
            self.assertEqual(
                harness.download_options["job-archive"]["archive_extract_warning"],
                warning[2],
            )


if __name__ == "__main__":
    unittest.main()
