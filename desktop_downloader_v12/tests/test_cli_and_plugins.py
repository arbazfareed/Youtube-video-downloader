import io
import threading
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cli
import download_engine
import plugins
from download_engine import DownloadCancelled
from plugins import load_plugins
from plugins.example_plugin import rename_lowercase


class CliAndPluginTests(unittest.TestCase):
    def test_cli_passes_options_and_returns_download_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with patch("cli.download_url", return_value="saved.zip") as download:
                with redirect_stdout(output), redirect_stderr(io.StringIO()):
                    result = cli.main(
                        [
                            "https://example.org/archive.zip",
                            "--output",
                            directory,
                            "--source",
                            "direct file",
                            "--cap",
                            "1024",
                            "--speed",
                            "balanced",
                            "--header",
                            "X-Api-Key: test-token",
                            "--retry-attempts",
                            "3",
                            "--retry-base-delay",
                            "0.5",
                            "--retry-max-delay",
                            "2",
                        ]
                    )
            self.assertEqual(result, 0)
            self.assertEqual(output.getvalue().strip(), "saved.zip")
            self.assertEqual(download.call_args.args[2], "direct file")
            self.assertEqual(download.call_args.args[10], 1024)
            self.assertEqual(download.call_args.args[-3], "cli")
            self.assertEqual(download.call_args.args[-2:], ("", "none"))
            self.assertEqual(
                download.call_args.kwargs["custom_headers"],
                {"X-Api-Key": "test-token"},
            )
            policy = download.call_args.kwargs["retry_policy"]
            self.assertEqual((policy.attempts, policy.base_delay, policy.max_delay), (3, 0.5, 2))

    def test_cli_returns_failure_for_download_error_and_cancel_for_interrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("cli.download_url", side_effect=RuntimeError("rejected")):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["https://example.org/file", "-o", directory]), 1)
            with patch("cli.download_url", side_effect=DownloadCancelled("cancelled")):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["https://example.org/file", "-o", directory]), 130)

    def test_download_engine_dispatches_plugin_lifecycle_events(self):
        with patch.object(download_engine, "_download_direct", return_value="archive.zip"), patch.object(
            download_engine,
            "emit_plugin_event",
            side_effect=[None, "archive.zip"],
        ) as emit:
            result = download_engine.download_url(
                "https://example.org/archive.zip",
                Path("."),
                "direct file",
                "video",
                "1080p",
                "single video",
                threading.Event(),
                lambda *_args: None,
                job_id="job-7",
            )
        self.assertEqual(result, "archive.zip")
        self.assertEqual(emit.call_args_list[0].args, ("on_start", "job-7", "https://example.org/archive.zip"))
        self.assertEqual(emit.call_args_list[-1].args, ("on_complete", "job-7", "archive.zip"))

    def test_example_plugin_renames_lowercase_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "MyFile.JPG"
            source.write_bytes(b"image")
            occupied = Path(directory) / "myfile.jpg"
            case_insensitive_match = occupied.exists() and occupied.samefile(source)
            if not case_insensitive_match:
                occupied.write_bytes(b"existing")
            result = Path(rename_lowercase("job-1", str(source)))
            self.assertEqual(
                result.name,
                "myfile.jpg" if case_insensitive_match else "myfile (1).jpg",
            )
            self.assertEqual(result.read_bytes(), b"image")
            if not case_insensitive_match:
                self.assertEqual(occupied.read_bytes(), b"existing")

    def test_plugin_folder_discovers_example_plugin(self):
        self.assertIn("example-lowercase-filenames", load_plugins())

    def test_portable_app_loads_user_plugins_from_next_to_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            executable_directory = Path(directory)
            plugin_directory = executable_directory / "plugins"
            plugin_directory.mkdir()
            (plugin_directory / "custom_plugin.py").write_text(
                "def register():\n"
                "    return {'name': 'portable-custom', 'events': {}}\n",
                encoding="utf-8",
            )
            system_modules = __import__("sys").modules
            portable_sys = SimpleNamespace(
                frozen=True,
                executable=str(executable_directory / "SmartDownloader12.exe"),
                modules=system_modules,
            )
            with (
                patch.object(plugins, "sys", portable_sys),
                patch.object(plugins, "_loaded", False),
                patch.object(plugins, "_plugins", []),
            ):
                self.assertIn("portable-custom", plugins.load_plugins())
            system_modules.pop("plugins.custom_plugin", None)


if __name__ == "__main__":
    unittest.main()
