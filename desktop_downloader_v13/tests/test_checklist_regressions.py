from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import launch
from download_engine import (
    RetryPolicy,
    _clean_terminal_text,
    _download_direct,
    _response_filename,
    download_url,
)
from history_store import DownloadHistory


class _Response:
    def __init__(
        self,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        payload: bytes = b"",
        url: str = "https://example.org/file.bin",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def iter_content(self, chunk_size: int):
        if self.payload:
            yield self.payload


class _Session:
    def __init__(self, *responses: _Response) -> None:
        self.headers: dict[str, str] = {}
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.closed = False

    def get(self, _url: str, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def _download(
    session: _Session,
    directory: Path,
    *,
    retry_policy: RetryPolicy = RetryPolicy(attempts=1, base_delay=0, max_delay=0),
) -> str:
    with patch("download_engine.requests.Session", return_value=session):
        return _download_direct(
            "https://example.org/file.bin",
            directory,
            threading.Event(),
            lambda *_args: None,
            speed_mode="slow",
            retry_policy=retry_policy,
        )


class StartupErrorHandlingTests(unittest.TestCase):
    def _run_startup_error(
        self, error: Exception, *, dependency_failure: bool = False
    ) -> tuple[int, Mock]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        app_directory = Path(temporary_directory.name)
        root = Mock()
        fake_app = types.ModuleType("app")
        fake_app.DownloaderApp = object
        fake_app.main = Mock(side_effect=error)
        with (
            patch.object(sys, "argv", ["launch.py"]),
            patch.object(sys, "frozen", False, create=True),
            patch.object(launch, "__file__", str(app_directory / "launch.py")),
            patch("launch.tk.Tk", return_value=root),
            patch(
                "launch._ensure_dependencies",
                side_effect=error if dependency_failure else None,
            ),
            patch.dict(sys.modules, {"app": fake_app}),
            patch("launch.messagebox.showerror") as show_error,
        ):
            result = launch.main()
        self.assertTrue((app_directory / "startup-error.log").is_file())
        return result, show_error

    def test_dependency_failure_is_shown_instead_of_crashing(self):
        result, show_error = self._run_startup_error(
            RuntimeError("Could not install app dependencies: network unavailable"),
            dependency_failure=True,
        )

        self.assertEqual(result, 1)
        self.assertIn("network unavailable", show_error.call_args.args[1])

    def test_corrupt_or_locked_history_failure_is_shown_instead_of_crashing(self):
        for message in (
            "database disk image is malformed",
            "database is locked",
        ):
            with self.subTest(message=message):
                result, show_error = self._run_startup_error(
                    sqlite3.DatabaseError(message)
                )
                self.assertEqual(result, 1)
                self.assertIn(message, show_error.call_args.args[1])


class HistoryDatabaseResilienceTests(unittest.TestCase):
    def test_corrupt_database_is_backed_up_and_rebuilt(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "history.sqlite3"
            corrupt_contents = b"not a sqlite database"
            database_path.write_bytes(corrupt_contents)

            history = DownloadHistory(database_path)

            self.assertTrue(database_path.is_file())
            self.assertEqual(history.list_records(), [])
            self.assertIsNotNone(history.recovery_backup_path)
            self.assertEqual(
                history.recovery_backup_path.read_bytes(),
                corrupt_contents,
            )

    def test_corrupt_database_backup_preserves_sqlite_sidecars(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "history.sqlite3"
            database_path.write_bytes(b"corrupt database")
            sidecar_path = Path(f"{database_path}-wal")
            sidecar_contents = b"preserved write-ahead log"
            sidecar_path.write_bytes(sidecar_contents)
            history = DownloadHistory.__new__(DownloadHistory)
            history.database_path = database_path

            backup_path = history._backup_corrupt_database()

            self.assertEqual(
                Path(f"{backup_path}-wal").read_bytes(),
                sidecar_contents,
            )
            self.assertFalse(database_path.exists())
            self.assertFalse(sidecar_path.exists())

    def test_external_exclusive_lock_is_reported_without_silent_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "history.sqlite3"
            history = DownloadHistory(database_path)
            external_connection = sqlite3.connect(database_path, timeout=0.01)
            external_connection.execute("BEGIN EXCLUSIVE")

            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                history.get_setting("language")
            external_connection.rollback()
            external_connection.close()

    def test_two_history_instances_can_read_and_write_the_same_database(self):
        with tempfile.TemporaryDirectory() as folder:
            database_path = Path(folder) / "history.sqlite3"
            first = DownloadHistory(database_path)
            second = DownloadHistory(database_path)

            record_id = first.add(
                "https://example.org/file.bin", "Queued", folder
            )

            self.assertEqual(second.list_records()[0].id, record_id)


class UrlValidationBehaviorTests(unittest.TestCase):
    def test_supported_http_urls_are_forwarded_unchanged_without_network_access(self):
        urls = (
            "http://example.org/file.zip",
            "https://example.org/file.zip?token=abc",
            "https://example.org/my file.zip",
            "https://example.org/फाइल.zip",
            "https://example.org/" + "x" * 5000,
            "https://user:pass@example.org/file.zip",
        )
        for url in urls:
            with self.subTest(url=url), patch(
                "download_engine._download_direct", return_value="saved-file"
            ) as direct_download:
                result = download_url(
                    url,
                    Path("."),
                    "direct file",
                    "video",
                    "best",
                    "single video",
                    threading.Event(),
                    lambda *_args: None,
                )
                self.assertEqual(result, "saved-file")
                self.assertEqual(direct_download.call_args.args[0], url)

    def test_requests_encodes_spaces_and_unicode_and_root_urls_get_a_safe_name(self):
        prepared_space = requests.Request(
            "GET", "https://example.org/my file.zip"
        ).prepare()
        prepared_unicode = requests.Request(
            "GET", "https://example.org/फाइल.zip"
        ).prepare()
        response = _Response(url="https://example.org/folder/")

        self.assertIn("my%20file.zip", prepared_space.url)
        self.assertNotIn("फाइल", prepared_unicode.url)
        self.assertTrue(prepared_unicode.url.endswith(".zip"))
        self.assertEqual(_response_filename(response), "index.html")

    def test_invalid_schemes_and_malformed_urls_are_rejected_before_transfer(self):
        for url in (
            "",
            "ftp://example.org/file.zip",
            "ht!tp://bad",
            "https:///file.zip",
            "https://[broken/file.zip",
        ):
            with self.subTest(url=url), patch(
                "download_engine._download_direct"
            ) as direct_download:
                with self.assertRaises(ValueError):
                    download_url(
                        url,
                        Path("."),
                        "direct file",
                        "video",
                        "best",
                        "single video",
                        threading.Event(),
                        lambda *_args: None,
                    )
                direct_download.assert_not_called()

    def test_basic_auth_url_is_parsed_and_credentials_are_redacted_from_errors(self):
        url = "https://user:private%40password@example.org/file.zip"
        prepared = requests.Request("GET", url).prepare()

        self.assertEqual(prepared.headers["Authorization"], "Basic dXNlcjpwcml2YXRlQHBhc3N3b3Jk")
        self.assertEqual(
            _clean_terminal_text(f"failed for {url}"),
            "failed for https://[redacted]@example.org/file.zip",
        )


class DirectDownloadChecklistTests(unittest.TestCase):
    def test_zero_byte_file_and_chunked_stream_without_length_complete_safely(self):
        cases = (
            ("zero-byte", {"Content-Length": "0"}, b""),
            ("chunked", {"Transfer-Encoding": "chunked"}, b"chunked bytes"),
        )
        with tempfile.TemporaryDirectory() as folder:
            for name, headers, payload in cases:
                with self.subTest(name=name):
                    session = _Session(
                        _Response(),
                        _Response(headers=headers, payload=payload),
                    )
                    result = _download(session, Path(folder) / name)
                    self.assertEqual(Path(result).read_bytes(), payload)
                    self.assertEqual(session.headers["Accept-Encoding"], "identity")

    def test_truncated_response_retries_from_partial_and_verifies_final_size(self):
        with tempfile.TemporaryDirectory() as folder:
            session = _Session(
                _Response(),
                _Response(
                    headers={
                        "Content-Length": "6",
                        "Content-Type": "application/octet-stream",
                    },
                    payload=b"abc",
                ),
                _Response(
                    status_code=206,
                    headers={
                        "Content-Length": "3",
                        "Content-Range": "bytes 3-5/6",
                        "Content-Type": "application/octet-stream",
                    },
                    payload=b"def",
                ),
            )
            result = _download(
                session,
                Path(folder),
                retry_policy=RetryPolicy(attempts=2, base_delay=0, max_delay=0),
            )

            self.assertEqual(Path(result).read_bytes(), b"abcdef")
            self.assertEqual(session.requests[2]["headers"], {"Range": "bytes=3-"})

    def test_advertised_response_size_mismatch_fails_instead_of_finalizing_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            session = _Session(
                _Response(),
                _Response(
                    headers={"Content-Length": "6"},
                    payload=b"abc",
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "incorrect byte count"):
                _download(session, Path(folder))
            self.assertFalse((Path(folder) / "file.bin").exists())

    def test_html_error_status_and_redirect_behavior_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            cases = (
                (
                    "html",
                    _Response(headers={"Content-Type": "text/html"}, payload=b"<html>"),
                    "web page",
                ),
                ("not found", _Response(status_code=404), "404"),
                ("forbidden", _Response(status_code=403), "403"),
            )
            for name, response, expected_error in cases:
                with self.subTest(name=name):
                    session = _Session(_Response(), response)
                    expected_exception = ValueError if name == "html" else RuntimeError
                    with self.assertRaisesRegex(expected_exception, expected_error):
                        _download(session, Path(folder) / name)
                    self.assertTrue(session.requests[-1]["allow_redirects"])

    def test_http_429_retries_and_resume_server_200_replaces_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            rate_limited = _Session(
                _Response(),
                _Response(status_code=429),
                _Response(
                    headers={
                        "Content-Length": "3",
                        "Content-Type": "application/octet-stream",
                    },
                    payload=b"abc",
                ),
            )
            result = _download(
                rate_limited,
                Path(folder) / "rate-limited",
                retry_policy=RetryPolicy(attempts=2, base_delay=0, max_delay=0),
            )
            self.assertEqual(Path(result).read_bytes(), b"abc")

            resume_folder = Path(folder) / "resume"
            resume_folder.mkdir()
            (resume_folder / "file.bin.part").write_bytes(b"stale")
            resumed = _Session(
                _Response(
                    headers={
                        "Content-Length": "6",
                        "Content-Type": "application/octet-stream",
                    },
                    payload=b"fresh!",
                )
            )
            result = _download(resumed, resume_folder)
            self.assertEqual(Path(result).read_bytes(), b"fresh!")
            self.assertEqual(resumed.requests[0]["headers"], {"Range": "bytes=5-"})

    def test_416_with_matching_partial_size_finishes_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "file.bin.part").write_bytes(b"complete")
            session = _Session(
                _Response(
                    status_code=416,
                    headers={"Content-Range": "bytes */8"},
                )
            )

            result = _download(session, directory)

            self.assertEqual(Path(result).read_bytes(), b"complete")

    def test_known_insufficient_disk_space_fails_before_body_request(self):
        with tempfile.TemporaryDirectory() as folder:
            session = _Session(
                _Response(
                    status_code=206,
                    headers={
                        "Content-Length": "1",
                        "Content-Range": "bytes 0-0/1000",
                        "Content-Type": "application/octet-stream",
                    },
                )
            )
            with (
                patch("download_engine.requests.Session", return_value=session),
                patch(
                    "download_engine.shutil.disk_usage",
                    return_value=types.SimpleNamespace(free=10),
                ),
            ):
                with self.assertRaisesRegex(OSError, "Insufficient disk space"):
                    _download_direct(
                        "https://example.org/file.bin",
                        Path(folder),
                        threading.Event(),
                        lambda *_args: None,
                        speed_mode="slow",
                    )
            self.assertEqual(len(session.requests), 1)


if __name__ == "__main__":
    unittest.main()
