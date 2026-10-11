from __future__ import annotations

import tarfile
import os
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient

import api
import download_engine
from cookies import load_cookies
from extract import extract_archive
from proxy import ProxyRotator, parse_proxy_list


class ProxyAndCookieTests(unittest.TestCase):
    def test_proxy_list_validation_and_rotation(self):
        rotator = ProxyRotator(
            "http://user:pass@proxy-one.test:8080, socks5h://proxy-two.test:1080"
        )
        self.assertEqual(
            rotator.next_requests_proxy(),
            {
                "http": "http://user:pass@proxy-one.test:8080",
                "https": "http://user:pass@proxy-one.test:8080",
            },
        )
        self.assertEqual(rotator.next_url(), "socks5h://proxy-two.test:1080")
        self.assertEqual(rotator.next_url(), "http://user:pass@proxy-one.test:8080")
        self.assertEqual(parse_proxy_list(""), ())
        with self.assertRaises(ValueError):
            parse_proxy_list("ftp://proxy.test:21")

    def test_browser_cookies_are_opt_in_and_use_supported_browser_names(self):
        self.assertIsNone(load_cookies("none"))
        jar = object()
        with patch(
            "yt_dlp.cookies.extract_cookies_from_browser", return_value=jar
        ) as extract:
            self.assertIs(load_cookies("Brave"), jar)
        extract.assert_called_once_with("brave")

    def test_download_url_passes_proxy_and_cookie_choices_to_engine(self):
        with patch.object(download_engine, "_download_direct", return_value="saved.bin") as direct:
            result = download_engine.download_url(
                "https://example.test/file.bin",
                Path("."),
                "direct file",
                "video",
                "1080p",
                "single video",
                threading.Event(),
                lambda *_args: None,
                proxy="http://proxy.test:8080",
                browser_cookies="chrome",
            )
        self.assertEqual(result, "saved.bin")
        self.assertEqual(direct.call_args.args[-2:], ("http://proxy.test:8080", "chrome"))

        with patch.object(
            download_engine, "_download_with_ytdlp", return_value="saved.mp4"
        ) as media:
            download_engine.download_url(
                "https://example.test/watch/1",
                Path("."),
                "supported site",
                "video",
                "1080p",
                "single video",
                threading.Event(),
                lambda *_args: None,
                proxy="http://first.test:8080,https://second.test:8443",
                browser_cookies="firefox",
            )
        self.assertEqual(media.call_args.args[-2:], ("http://first.test:8080", "firefox"))

    def test_direct_requests_use_selected_proxy_and_browser_cookie_jar(self):
        class Response:
            status_code = 200
            headers = {
                "Content-Length": "4",
                "Content-Type": "application/octet-stream",
            }
            url = "https://example.test/file.bin"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield b"data"

        with tempfile.TemporaryDirectory() as directory:
            session = Mock()
            session.get.return_value = Response()
            cookie_jar = Mock()
            with patch("download_engine.requests.Session", return_value=session), patch(
                "download_engine.load_cookies", return_value=cookie_jar
            ):
                result = download_engine._download_direct(
                    "https://example.test/file.bin",
                    Path(directory),
                    threading.Event(),
                    lambda *_args: None,
                    speed_mode="balanced",
                    proxy="http://first.test:8080,http://second.test:8080",
                    browser_cookies="chrome",
                )
            self.assertEqual(Path(result).read_bytes(), b"data")
            self.assertEqual(
                session.get.call_args.kwargs["proxies"],
                {"http": "http://first.test:8080", "https": "http://first.test:8080"},
            )
            session.cookies.update.assert_called_once_with(cookie_jar)
            session.close.assert_called_once()

    def test_ytdlp_receives_proxy_and_browser_cookie_settings(self):
        ydl = MagicMock()
        ydl.__enter__.return_value.extract_info.return_value = {
            "_filename": "saved.mp4",
        }
        with patch("download_engine.yt_dlp.YoutubeDL", return_value=ydl) as youtube_dl:
            result = download_engine._download_with_ytdlp(
                "https://example.test/watch/1",
                Path("downloads"),
                "video",
                "1080p",
                "single video",
                threading.Event(),
                lambda *_args: None,
                proxy="socks5://proxy.test:1080",
                browser_cookies="firefox",
            )
        self.assertTrue(result.endswith("saved.mp4"))
        options = youtube_dl.call_args.args[0]
        self.assertEqual(options["proxy"], "socks5://proxy.test:1080")
        self.assertEqual(options["cookiesfrombrowser"], ("firefox", None, None, None))


class ArchiveExtractionTests(unittest.TestCase):
    def test_extracts_zip_to_sibling_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("folder/readme.txt", "hello")
            extracted = extract_archive(archive_path)
            self.assertEqual(extracted, (Path(directory) / "package").resolve())
            self.assertEqual((extracted / "folder" / "readme.txt").read_text(), "hello")

    def test_rejects_zip_slip_and_tar_links(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "no")
            with self.assertRaisesRegex(ValueError, "Unsafe archive member"):
                extract_archive(archive_path)
            self.assertFalse((Path(directory).parent / "escape.txt").exists())

            tar_path = Path(directory) / "linked.tar"
            with tarfile.open(tar_path, "w") as archive:
                link = tarfile.TarInfo("shortcut")
                link.type = tarfile.SYMTYPE
                link.linkname = "..\\escape.txt"
                archive.addfile(link)
            with self.assertRaisesRegex(ValueError, "Links and special files"):
                extract_archive(tar_path)

    def test_refuses_to_overwrite_extraction_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "package.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("readme.txt", "hello")
            (Path(directory) / "package").mkdir()
            with self.assertRaises(FileExistsError):
                extract_archive(archive_path)

    def test_leaves_unsupported_7z_for_manual_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "package.7z"
            archive_path.write_bytes(b"not extracted")
            self.assertIsNone(extract_archive(archive_path))


class ApiTests(unittest.TestCase):
    def setUp(self):
        api._JOBS.clear()
        self.client = TestClient(api.app)
        self.headers = {"Authorization": f"Bearer {api._TOKEN}"}

    def test_api_requires_bearer_token(self):
        response = self.client.get("/jobs")
        self.assertEqual(response.status_code, 401)

    def test_api_creates_job_and_never_returns_proxy_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            api, "download_url", return_value="saved.bin"
        ):
            response = self.client.post(
                "/jobs",
                headers=self.headers,
                json={
                    "url": "https://example.test/file.bin",
                    "output": directory,
                    "source": "direct file",
                    "proxy": "http://secret:password@proxy.test:8080",
                },
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["id"]
            for _ in range(50):
                record = self.client.get(f"/jobs/{job_id}", headers=self.headers).json()
                if record["status"] == "completed":
                    break
                threading.Event().wait(0.01)
            self.assertEqual(record["status"], "completed")
            self.assertNotIn("secret", str(record))
            self.assertNotIn("password", str(record))
            self.assertEqual(len(self.client.get("/jobs", headers=self.headers).json()), 1)

    def test_api_rejects_invalid_proxy_and_protects_terminal_actions(self):
        invalid = self.client.post(
            "/jobs",
            headers=self.headers,
            json={"url": "https://example.test/file", "proxy": "ftp://proxy.test"},
        )
        self.assertEqual(invalid.status_code, 422)
        completed = api.ApiJob("done", api.JobRequest(url="https://example.test/"), status="completed")
        api._JOBS[completed.id] = completed
        self.assertEqual(
            self.client.post("/jobs/done/cancel", headers=self.headers).status_code,
            409,
        )

    def test_api_pause_resume_and_cancel_controls(self):
        with patch.object(api._EXECUTOR, "submit"):
            response = self.client.post(
                "/jobs",
                headers=self.headers,
                json={"url": "https://example.test/file.bin"},
            )
        job_id = response.json()["id"]
        self.assertEqual(
            self.client.post(f"/jobs/{job_id}/pause", headers=self.headers).json()["status"],
            "paused",
        )
        self.assertEqual(
            self.client.post(f"/jobs/{job_id}/resume", headers=self.headers).json()["status"],
            "running",
        )
        self.assertEqual(
            self.client.post(f"/jobs/{job_id}/cancel", headers=self.headers).json()["status"],
            "cancelling",
        )

    def test_mobile_handoff_is_job_scoped_and_expires(self):
        job = api.ApiJob("phone-job", api.JobRequest(url="https://example.test/video"))
        api._JOBS[job.id] = job
        scoped_headers = {"Authorization": f"Bearer {job.handoff_token}"}

        status_response = self.client.get(
            f"/mobile/jobs/{job.id}", headers=scoped_headers
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertNotIn("url", status_response.json())
        self.assertNotIn("result", status_response.json())
        self.assertEqual(
            self.client.post(
                f"/mobile/jobs/{job.id}/pause", headers=scoped_headers
            ).json()["status"],
            "paused",
        )
        self.assertEqual(
            self.client.post(
                f"/mobile/jobs/{job.id}/resume", headers=scoped_headers
            ).json()["status"],
            "running",
        )
        self.assertEqual(
            self.client.get(
                f"/mobile/jobs/{job.id}",
                headers={"Authorization": "Bearer wrong-token"},
            ).status_code,
            401,
        )
        job.handoff_expires_at = 0
        self.assertEqual(
            self.client.get(
                f"/mobile/jobs/{job.id}", headers=scoped_headers
            ).status_code,
            401,
        )

    def test_phone_qr_requires_lan_bind_and_returns_png(self):
        job = api.ApiJob("qr-job", api.JobRequest(url="https://example.test/video"))
        api._JOBS[job.id] = job
        self.assertEqual(
            self.client.post(
                f"/jobs/{job.id}/handoff/qr", headers=self.headers
            ).status_code,
            409,
        )

        with patch.dict(
            os.environ,
            {"SMART_DOWNLOADER_API_HOST": "0.0.0.0", "SMART_DOWNLOADER_API_PORT": "8765"},
        ), patch.object(api, "mobile_handoff_url", return_value="http://192.0.2.5/mobile"), patch.object(
            api, "make_qr_png", return_value=b"\x89PNG\r\n\x1a\nimage"
        ):
            response = self.client.post(
                f"/jobs/{job.id}/handoff/qr", headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_mobile_page_is_served_without_exposing_job_tokens(self):
        response = self.client.get("/mobile")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Phone control", response.text)
        self.assertEqual(self.client.get("/mobile.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
