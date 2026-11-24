from __future__ import annotations

import hashlib
import http.client
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from update_engine import ReleaseUpdate, UpdateError, download_verified_update


class UpdateDownloadFailureRecoveryTests(unittest.TestCase):
    def test_interrupted_http_response_is_normalized_and_preserves_existing_package(self) -> None:
        expected = b"complete package"
        update = ReleaseUpdate(
            version="14.1.0",
            asset_url=(
                "https://github.com/arbazfareed/Youtube-video-downloader/"
                "releases/download/v14.1.0/SmartDownloader14-Windows.zip"
            ),
            digest=f"sha256:{hashlib.sha256(expected).hexdigest()}",
            size=len(expected),
        )
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.side_effect = http.client.IncompleteRead(b"partial", len(expected))

        with TemporaryDirectory() as folder:
            destination = Path(folder) / "SmartDownloader14-14.1.0.zip"
            destination.write_bytes(b"previous verified package")

            with patch("update_engine.urlopen", return_value=response):
                with self.assertRaisesRegex(UpdateError, "Could not download the update"):
                    download_verified_update(update, destination)

            self.assertEqual(destination.read_bytes(), b"previous verified package")
            self.assertEqual(list(Path(folder).glob("*.download")), [])
            self.assertEqual(list(Path(folder).glob(".*.download")), [])


if __name__ == "__main__":
    unittest.main()
