import hashlib
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from download_engine import (
    _AudioLanguageMetadataPP,
    _delta_sync_existing_file,
    _download_with_ytdlp,
)
from plugins.example_plugin import rename_lowercase
from proxy import ProxyRotator


class _Response:
    def __init__(
        self,
        *,
        status=200,
        headers=None,
        content=b"",
        payload=None,
        url="https://example.org/asset.bin",
    ):
        self.status_code = status
        self.headers = headers or {}
        self.content = content
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        del _args
        return None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class _ManifestSession:
    def __init__(self, chunks, manifest):
        self.chunks = chunks
        self.manifest = manifest
        self.requests = []

    def get(self, url, headers=None, **_kwargs):
        del _kwargs
        self.requests.append((url, headers or {}))
        if url.endswith("manifest.json"):
            return _Response(payload=self.manifest)
        range_header = (headers or {}).get("Range", "")
        start, end = (int(value) for value in range_header.removeprefix("bytes=").split("-"))
        content = self.chunks[start : end + 1]
        return _Response(
            status=206,
            headers={"Content-Range": f"bytes {start}-{end}/{len(self.chunks)}"},
            content=content,
        )

    def close(self):
        return None


class _DeltaDownloadSession(_ManifestSession):
    def get(self, url, headers=None, **kwargs):
        request_headers = headers or {}
        if request_headers.get("Range") == "bytes=0-0":
            self.requests.append((url, request_headers))
            return _Response(
                status=206,
                headers={
                    "Content-Range": f"bytes 0-0/{len(self.chunks)}",
                    "Content-Disposition": 'attachment; filename="asset.bin"',
                    "Content-Type": "application/octet-stream",
                    "ETag": '"version-2"',
                    "X-Chunk-Hash-Manifest": "/manifest.json",
                },
                url=url,
            )
        return super().get(url, headers=headers, **kwargs)


class LiveDeltaAudioTests(unittest.TestCase):
    def test_multilingual_tracks_are_tagged_and_english_is_default(self):
        from yt_dlp import YoutubeDL

        with YoutubeDL({"quiet": True}) as downloader:
            processor = _AudioLanguageMetadataPP(downloader)
            processor.run_ffmpeg = Mock()
            info = {
                "filepath": "video.mkv",
                "requested_formats": [
                    {"vcodec": "avc1", "acodec": "none"},
                    {"vcodec": "none", "acodec": "opus", "language": "hi"},
                    {"vcodec": "none", "acodec": "opus", "language": "en-US"},
                ],
            }

            with patch("download_engine.os.replace") as replace:
                _, result = processor.run(info)

            options = processor.run_ffmpeg.call_args.args[2]
            self.assertIn("-metadata:s:a:0", options)
            self.assertIn("language=hin", options)
            self.assertIn("language=eng", options)
            self.assertEqual(options[options.index("-disposition:a:0") + 1], "0")
            self.assertEqual(options[options.index("-disposition:a:1") + 1], "default")
            replace.assert_called_once()
            self.assertIs(result, info)

    def test_live_stream_progress_uses_recording_status_without_eta(self):
        with TemporaryDirectory() as folder, patch("download_engine.yt_dlp.YoutubeDL") as youtube_dl:
            downloader = youtube_dl.return_value.__enter__.return_value
            downloader.extract_info.return_value = {"_filename": "live.mkv"}
            progress_events = []
            _download_with_ytdlp(
                "https://example.org/live",
                Path(folder),
                "video",
                "1080p",
                "single video",
                threading.Event(),
                lambda *event: progress_events.append(event),
            )

            hook = youtube_dl.call_args.args[0]["progress_hooks"][0]
            hook({
                "status": "downloading",
                "downloaded_bytes": 4096,
                "filename": "live.mkv",
                "info_dict": {"is_live": True},
            })

        self.assertEqual(progress_events[-1][0], "Recording live stream")
        self.assertIsNone(progress_events[-1][1])
        self.assertIn("Recorded ", progress_events[-1][2])
        self.assertNotIn("ETA", progress_events[-1][2])
        downloader.add_post_processor.assert_called_once()

    def test_delta_sync_fetches_only_chunks_that_differ(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "asset.bin"
            target.write_bytes(b"aaabbbccc")
            remote = b"aaaxxxccc"
            manifest = {
                "chunk_size": 3,
                "size": len(remote),
                "algorithm": "sha256",
                "chunks": [
                    hashlib.sha256(remote[start : start + 3]).hexdigest()
                    for start in range(0, len(remote), 3)
                ],
            }
            session = _ManifestSession(remote, manifest)
            progress_events = []

            result = _delta_sync_existing_file(
                session,
                "https://example.org/asset.bin",
                target,
                len(remote),
                "https://example.org/manifest.json",
                threading.Event(),
                None,
                lambda *event: progress_events.append(event),
                None,
                None,
                ProxyRotator(""),
                'etag:"version-2"',
            )

            self.assertEqual(result, str(target))
            self.assertEqual(target.read_bytes(), remote)
            self.assertEqual(len(session.requests), 2)
            self.assertEqual(session.requests[1][1]["Range"], "bytes=3-5")
            self.assertEqual(session.requests[1][1]["If-Match"], '"version-2"')
            self.assertEqual(progress_events[-1][0], "Download complete")

    def test_direct_download_uses_advertised_delta_manifest(self):
        from download_engine import _download_direct

        with TemporaryDirectory() as folder:
            target = Path(folder) / "asset.bin"
            target.write_bytes(b"aaabbbccc")
            remote = b"aaaxxxccc"
            manifest = {
                "chunk_size": 3,
                "size": len(remote),
                "algorithm": "sha256",
                "chunks": [
                    hashlib.sha256(remote[start : start + 3]).hexdigest()
                    for start in range(0, len(remote), 3)
                ],
            }
            session = _DeltaDownloadSession(remote, manifest)

            with patch("download_engine.requests.Session", return_value=session):
                result = _download_direct(
                    "https://example.org/asset.bin",
                    Path(folder),
                    threading.Event(),
                    Mock(),
                )

            self.assertEqual(result, str(target))
            self.assertEqual(target.read_bytes(), remote)
            self.assertEqual(
                [headers.get("Range") for _, headers in session.requests],
                ["bytes=0-0", None, "bytes=3-5"],
            )

    def test_delta_hash_mismatch_keeps_original_file(self):
        with TemporaryDirectory() as folder:
            target = Path(folder) / "asset.bin"
            target.write_bytes(b"old")
            remote = b"new"
            manifest = {
                "chunk_size": 3,
                "size": 3,
                "algorithm": "sha256",
                "chunks": [hashlib.sha256(b"other").hexdigest()],
            }
            session = _ManifestSession(remote, manifest)

            with self.assertRaisesRegex(RuntimeError, "did not match"):
                _delta_sync_existing_file(
                    session,
                    "https://example.org/asset.bin",
                    target,
                    3,
                    "https://example.org/manifest.json",
                    threading.Event(),
                    None,
                    Mock(),
                    None,
                    None,
                    ProxyRotator(""),
                    "",
                )

            self.assertEqual(target.read_bytes(), b"old")
            self.assertFalse(target.with_name("asset.bin.delta.part").exists())

    def test_example_plugin_does_not_rename_a_playlist_directory(self):
        with TemporaryDirectory() as folder:
            playlist_directory = Path(folder) / "Downloads"
            playlist_directory.mkdir()

            result = rename_lowercase("job", str(playlist_directory))

            self.assertEqual(result, str(playlist_directory))
            self.assertTrue(playlist_directory.is_dir())
            self.assertEqual([path.name for path in Path(folder).iterdir()], ["Downloads"])

    def test_example_plugin_still_lowercases_completed_files(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "Video.MP4"
            source.write_bytes(b"video")

            result = rename_lowercase("job", str(source))

            self.assertEqual(Path(result).name, "video.mp4")
            self.assertEqual(Path(result).read_bytes(), b"video")


if __name__ == "__main__":
    unittest.main()
