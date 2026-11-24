from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import api


class ApiArchiveExtractionRecoveryTests(unittest.TestCase):
    def test_extraction_failure_keeps_download_and_returns_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "downloaded.zip"
            archive.write_bytes(b"verified archive contents")
            job = api.ApiJob(
                "api-extract-failure",
                api.JobRequest(
                    url="https://example.test/archive.zip",
                    output=directory,
                    source="direct file",
                    auto_extract=True,
                ),
            )
            job.resume_event.set()

            with patch.object(api, "download_url", return_value=str(archive)), patch(
                "extract.extract_archive",
                side_effect=RuntimeError("unsupported compression method"),
            ) as extract:
                api._run_job(job)

            extract.assert_called_once_with(archive)
            self.assertEqual(job.status, "partial")
            self.assertEqual(job.result, str(archive))
            self.assertIsNone(job.error)
            self.assertIn("extraction failed", job.details.lower())
            self.assertIn("retry extraction manually", job.details.lower())
            self.assertEqual(archive.read_bytes(), b"verified archive contents")


if __name__ == "__main__":
    unittest.main()
