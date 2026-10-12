from __future__ import annotations

import hashlib
import io
import json
import queue
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import Mock, patch

import diagnostics
import update_engine
from app import DownloaderApp
from localization import LANGUAGES, translate
from update_engine import NoPublishedReleaseError, ReleaseUpdate, UpdateError


class _Response:
    def __init__(self, content: bytes):
        self.content = io.BytesIO(content)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int = -1) -> bytes:
        return self.content.read(size)


class LocalizationTests(unittest.TestCase):
    def test_supported_languages_translate_core_actions_and_fallback_cleanly(self):
        self.assertEqual(
            set(LANGUAGES),
            {"English", "Urdu", "Arabic", "Spanish", "Hindi", "Bangla"},
        )
        for language in ("Urdu", "Arabic", "Spanish", "Hindi", "Bangla"):
            self.assertNotEqual(translate("Settings", language), "Settings")
        self.assertEqual(translate("Untranslated status", "Spanish"), "Untranslated status")
        self.assertEqual(translate("Settings", "unsupported"), "Settings")

    def test_urdu_translates_primary_download_and_accessibility_controls(self):
        core_labels = (
            "All tasks",
            "Add download",
            "Link",
            "Source",
            "Media",
            "Resolution",
            "Playlist",
            "Browse",
            "Overall progress",
            "Status",
            "Accessibility",
            "Use larger text",
            "High contrast",
            "Keyboard shortcuts:",
            "Ctrl+L — focus link field",
            "Ctrl+J — focus download list",
            "Alt+S — focus progress status",
        )
        for label in core_labels:
            with self.subTest(label=label):
                translated = translate(label, "Urdu")
                self.assertNotEqual(translated, label)
                self.assertTrue(
                    any("\u0600" <= character <= "\u06ff" for character in translated),
                    translated,
                )

    def test_urdu_translates_preview_and_smart_vlc_actions(self):
        for label in (
            "Play in preview",
            "Open Smart VLC",
            "Pause in app",
            "Available videos",
            "Select a download to list its videos.",
            "No videos found in this download.",
            "Video is still downloading",
            "This video is still downloading. Preview may not work until the download has finished.",
        ):
            with self.subTest(label=label):
                translated = translate(label, "Urdu")
                self.assertNotEqual(translated, label)
                self.assertTrue(
                    any("\u0600" <= character <= "\u06ff" for character in translated),
                    translated,
                )


class DiagnosticsTests(unittest.TestCase):
    def test_diagnostics_are_disabled_by_default_and_store_only_minimal_local_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostics.jsonl"
            self.assertFalse(
                diagnostics.record_diagnostic(
                    False, "download", RuntimeError("secret url/token"), path
                )
            )
            self.assertFalse(path.exists())

            self.assertTrue(
                diagnostics.record_diagnostic(
                    True, "download", RuntimeError("secret url/token"), path
                )
            )
            event = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual(event["component"], "download")
            self.assertEqual(event["error_type"], "RuntimeError")
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))
            self.assertNotIn("url/token", path.read_text(encoding="utf-8"))
            self.assertIn("time", event)
            self.assertEqual(set(event), {"time", "component", "error_type"})

    def test_export_requires_existing_diagnostics_and_copies_the_log(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "diagnostics.jsonl"
            destination = Path(directory) / "support" / "export.jsonl"
            with self.assertRaises(FileNotFoundError):
                diagnostics.export_diagnostics(destination, source)
            source.write_text('{"error_type":"ValueError"}\n', encoding="utf-8")
            self.assertEqual(
                diagnostics.export_diagnostics(destination, source), destination
            )
            self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_export_includes_rotated_local_diagnostic_history(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "diagnostics.jsonl"
            rotated = source.with_suffix(".jsonl.1")
            destination = Path(directory) / "export.jsonl"
            rotated.write_text('{"component":"older"}\n', encoding="utf-8")
            source.write_text('{"component":"newer"}\n', encoding="utf-8")
            diagnostics.export_diagnostics(destination, source)
            self.assertEqual(
                destination.read_text(encoding="utf-8"),
                '{"component":"older"}\n{"component":"newer"}\n',
            )


class UpdateEngineTests(unittest.TestCase):
    def _release_document(self, *, digest: str | None = None) -> bytes:
        asset = {
            "name": "SmartDownloader13-Windows.zip",
            "browser_download_url": (
                "https://github.com/arbazfareed/Youtube-video-downloader/"
                "releases/download/v13.1/SmartDownloader13-Windows.zip"
            ),
            "size": 4,
        }
        if digest is not None:
            asset["digest"] = digest
        return json.dumps(
            {"tag_name": "v13.1", "assets": [asset]}
        ).encode("utf-8")

    def test_release_check_compares_versions_and_requires_published_sha256(self):
        current = json.dumps(
            {"tag_name": "v13.0", "assets": []}
        ).encode("utf-8")
        with patch("update_engine.urlopen", return_value=_Response(current)):
            self.assertIsNone(
                update_engine.check_for_update("13.0.0", system="Windows")
            )

        with patch(
            "update_engine.urlopen", return_value=_Response(self._release_document())
        ):
            with self.assertRaisesRegex(UpdateError, "no valid SHA-256"):
                update_engine.check_for_update("13.0", system="Windows")

    def test_missing_latest_release_reports_that_none_is_published(self):
        error = HTTPError(
            "https://api.github.com/repos/example/repo/releases/latest",
            404,
            "Not Found",
            {},
            None,
        )
        with patch("update_engine.urlopen", side_effect=error):
            with self.assertRaisesRegex(
                NoPublishedReleaseError, "no published GitHub release yet"
            ):
                update_engine.check_for_update("13.0", system="Windows")

    def test_release_check_rejects_untrusted_asset_urls(self):
        document = json.loads(
            self._release_document(digest="sha256:" + "a" * 64)
        )
        document["assets"][0]["browser_download_url"] = "https://evil.example/update.zip"
        with patch(
            "update_engine.urlopen",
            return_value=_Response(json.dumps(document).encode("utf-8")),
        ):
            with self.assertRaisesRegex(UpdateError, "not trusted"):
                update_engine.check_for_update("13.0", system="Windows")

    def test_download_saves_only_digest_verified_release_and_preserves_existing_file(self):
        content = b"zip!"
        url = (
            "https://github.com/arbazfareed/Youtube-video-downloader/"
            "releases/download/v13.1/SmartDownloader13-Windows.zip"
        )
        update = ReleaseUpdate(
            "v13.1",
            url,
            f"sha256:{hashlib.sha256(content).hexdigest()}",
            len(content),
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "update.zip"
            with patch("update_engine.urlopen", return_value=_Response(content)):
                self.assertEqual(
                    update_engine.download_verified_update(update, destination),
                    destination,
                )
            self.assertEqual(destination.read_bytes(), content)

            destination.write_bytes(b"previous")
            bad_update = ReleaseUpdate("v13.1", url, "sha256:" + "0" * 64, 4)
            with patch("update_engine.urlopen", return_value=_Response(content)):
                with self.assertRaisesRegex(UpdateError, "verification failed"):
                    update_engine.download_verified_update(bad_update, destination)
            self.assertEqual(destination.read_bytes(), b"previous")
            self.assertEqual(list(Path(directory).glob("*.download")), [])


class IntegrityGuardTests(unittest.TestCase):
    def test_guard_detects_changed_file_and_allows_unchanged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "download.bin"
            path.write_bytes(b"original")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            app = DownloaderApp.__new__(DownloaderApp)
            app.root = Mock()
            app._integrity_baselines = {"job": (path, digest)}

            self.assertTrue(app._integrity_guard("job"))
            path.write_bytes(b"changed")
            with patch("app_media.messagebox.showerror") as show_error:
                self.assertFalse(app._integrity_guard("job"))
            show_error.assert_called_once()

    def test_guard_blocks_missing_baseline_file_and_does_not_block_legacy_records(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.root = Mock()
        app._integrity_baselines = {}
        self.assertTrue(app._integrity_guard("legacy-job"))

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "removed.bin"
            app._integrity_baselines["new-job"] = (missing, "a" * 64)
            with patch("app_media.messagebox.showerror") as show_error:
                self.assertFalse(app._integrity_guard("new-job"))
            show_error.assert_called_once()

    def test_selected_archive_is_not_extracted_after_integrity_mismatch(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.root = Mock()
        app.jobs = Mock()
        app.jobs.selection.return_value = ("job",)
        app._integrity_guard = Mock(return_value=False)
        app._selected_output_path = Mock()

        with patch("app_media.extract_archive") as extract:
            app.extract_selected_archive()

        app._integrity_guard.assert_called_once_with("job")
        app._selected_output_path.assert_not_called()
        extract.assert_not_called()

    def test_completion_records_a_persistent_sha256_baseline_for_local_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "download.bin"
            path.write_bytes(b"verified at completion")
            app = DownloaderApp.__new__(DownloaderApp)
            app.download_options = {"job": {"cloud_provider": "local"}}
            app.verified_checksums = {}
            app.events = queue.Queue()
            future = Future()
            future.set_result(str(path))

            app._job_finished("job", future)

            options = app.download_options["job"]
            self.assertEqual(options["integrity_path"], str(path.resolve()))
            self.assertEqual(
                options["integrity_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            self.assertEqual(app.events.get_nowait()[2], "Complete")

            persisted = DownloaderApp._persistent_job_options_values(
                {**options, "destination": Path(directory)}, path
            )
            self.assertEqual(persisted["integrity_path"], str(path.resolve()))
            self.assertEqual(persisted["integrity_sha256"], options["integrity_sha256"])


class PreferenceTests(unittest.TestCase):
    def test_setting_callbacks_persist_accessibility_update_and_telemetry_choices(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.history = Mock()
        app.language = Mock()
        app.language.get.return_value = "Urdu"
        app.large_text = Mock()
        app.large_text.get.return_value = True
        app.high_contrast = Mock()
        app.high_contrast.get.return_value = False
        app.check_updates = Mock()
        app.check_updates.get.return_value = True
        app.diagnostics_enabled = Mock()
        app.diagnostics_enabled.get.return_value = False
        app.settings_window = Mock()
        app._apply_theme = Mock()

        with patch("app_preferences.messagebox.showinfo") as show_info:
            app._save_language_preference()
        app._save_accessibility_preferences()
        app._save_update_preference()
        app._save_diagnostics_preference()

        self.assertEqual(
            app.history.set_setting.call_args_list,
            [
                unittest.mock.call("language", "Urdu"),
                unittest.mock.call("large_text", "1"),
                unittest.mock.call("high_contrast", "0"),
                unittest.mock.call("check_updates", "1"),
                unittest.mock.call("diagnostics_enabled", "0"),
            ],
        )
        app._apply_theme.assert_called_once()
        show_info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
