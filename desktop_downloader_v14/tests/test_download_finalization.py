import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import download_engine


class DirectDownloadFinalizationTests(unittest.TestCase):
    def test_delta_sync_result_is_converted_when_mp3_mode_selected(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "video.mkv"
            target.write_bytes(b"existing")
            response = Mock()
            response.status_code = 206
            response.headers = {
                "Content-Range": "bytes 0-0/10",
                "Content-Disposition": 'attachment; filename="video.mkv"',
                "X-Chunk-Hash-Manifest": "/manifest.json",
                "ETag": '"v1"',
            }
            response.url = "https://example.test/video"
            session = Mock()
            session.headers = {}
            session.get.return_value.__enter__.return_value = response
            converted = Path(folder) / "video.mp3"
            with (
                patch("download_engine.load_cookies", return_value=None),
                patch("download_engine.requests.Session", return_value=session),
                patch("download_engine.ProxyRotator") as proxy,
                patch("download_engine._delta_sync_existing_file", return_value=str(target)),
                patch("download_engine._convert_to_mp3_if_needed", return_value=converted) as convert,
            ):
                proxy.return_value.current_requests_proxy.return_value = None
                proxy.return_value.next_requests_proxy.return_value = None
                result = download_engine._download_direct(
                    "https://example.test/video",
                    Path(folder),
                    threading.Event(),
                    lambda *_: None,
                    mode="mp3 audio",
                )
            convert.assert_called_once_with(target, "mp3 audio")
            self.assertEqual(result, str(converted))

    def test_completed_http_416_resume_is_converted_to_mp3(self):
        with TemporaryDirectory() as folder:
            partial = Path(folder) / "audio.m4a.part"
            partial.write_bytes(b"complete payload")
            response = Mock()
            response.status_code = 416
            response.headers = {"Content-Range": f"bytes */{partial.stat().st_size}"}
            session = Mock()
            session.headers = {}
            session.get.return_value.__enter__.return_value = response
            converted = Path(folder) / "audio.mp3"
            with (
                patch("download_engine.load_cookies", return_value=None),
                patch("download_engine.requests.Session", return_value=session),
                patch("download_engine.ProxyRotator") as proxy,
                patch("download_engine._convert_to_mp3_if_needed", return_value=converted) as convert,
            ):
                proxy.return_value.current_requests_proxy.return_value = None
                proxy.return_value.next_requests_proxy.return_value = None
                result = download_engine._download_direct(
                    "https://example.test/audio.m4a",
                    Path(folder),
                    threading.Event(),
                    lambda *_: None,
                    mode="mp3 audio",
                )
            convert.assert_called_once_with(Path(folder) / "audio.m4a", "mp3 audio")
            self.assertEqual(result, str(converted))


if __name__ == "__main__":
    unittest.main()
