import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import launch
import app_support
from launch import (
    _ensure_dependencies,
    _smoke_test_app,
    _smoke_test_vlc_runtime,
)


class AppIconTests(unittest.TestCase):
    def test_windows_uses_bundled_ico_for_each_window(self):
        window = unittest.mock.Mock()
        icon_path = Path("smart_downloader.ico")
        with (
            patch.object(app_support.sys, "platform", "win32"),
            patch.object(app_support, "app_resource_path", return_value=icon_path),
        ):
            app_support.set_app_window_icon(window)
        window.iconbitmap.assert_called_once_with(str(icon_path))
        window.iconphoto.assert_not_called()

    def test_other_platforms_retain_png_icon_for_the_window_lifetime(self):
        window = unittest.mock.Mock()
        image = unittest.mock.sentinel.icon
        with (
            patch.object(app_support.sys, "platform", "linux"),
            patch.object(app_support, "app_resource_path", return_value=Path("smart_downloader.png")),
            patch.object(app_support.tk, "PhotoImage", return_value=image) as photo_image,
        ):
            app_support.set_app_window_icon(window)
        photo_image.assert_called_once_with(file=str(Path("smart_downloader.png")))
        window.iconphoto.assert_called_once_with(True, image)
        self.assertIs(window._smart_downloader_icon, image)


class FrozenLauncherTests(unittest.TestCase):
    def test_packaged_app_does_not_try_to_install_dependencies(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch("launch.subprocess.run", side_effect=AssertionError("pip must not run")),
        ):
            _ensure_dependencies()


class DependencyBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.app_directory = Path(self.temporary_directory.name)
        self.requirements_path = self.app_directory / "requirements.txt"
        self.requirements_path.write_text("example-package>=1\n", encoding="utf-8")
        (self.app_directory / ".venv").mkdir()

    def test_installs_requirements_once_and_reinstalls_when_the_file_changes(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch("launch.__file__", str(self.app_directory / "launch.py")),
            patch("launch.importlib.metadata.distribution", return_value=object()),
            patch("launch.subprocess.run", return_value=completed) as run,
            patch.object(sys, "frozen", False, create=True),
        ):
            _ensure_dependencies()
            run.assert_called_once()

            stamp = self.app_directory / ".venv" / ".requirements-sha256"
            digest = hashlib.sha256(self.requirements_path.read_bytes()).hexdigest()
            self.assertEqual(stamp.read_text(encoding="ascii"), digest)

            run.reset_mock()
            _ensure_dependencies()
            run.assert_not_called()

            self.requirements_path.write_text("example-package>=2\n", encoding="utf-8")
            _ensure_dependencies()
            run.assert_called_once()

    def test_failed_install_does_not_record_a_successful_requirements_stamp(self):
        failed = subprocess.CompletedProcess([], 1, "", "package installation failed")
        with (
            patch("launch.__file__", str(self.app_directory / "launch.py")),
            patch("launch.importlib.metadata.distribution", return_value=object()),
            patch("launch.subprocess.run", return_value=failed),
            patch.object(sys, "frozen", False, create=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "package installation failed"):
                _ensure_dependencies()

        stamp = self.app_directory / ".venv" / ".requirements-sha256"
        self.assertFalse(stamp.exists())


class PackagedSmokeTestTests(unittest.TestCase):
    def test_smoke_test_requires_visible_window_and_always_closes_root(self):
        class FakeRoot:
            def __init__(self, visible):
                self.visible = visible
                self.destroyed = False

            def update(self):
                return None

            def title(self):
                return "Smart Downloader"

            def winfo_viewable(self):
                return self.visible

            def destroy(self):
                self.destroyed = True

        root = FakeRoot(visible=True)
        with patch("launch.tk.Tk", return_value=root):
            _smoke_test_app(lambda _root: None)
        self.assertTrue(root.destroyed)

        hidden_root = FakeRoot(visible=False)
        with patch("launch.tk.Tk", return_value=hidden_root):
            with self.assertRaisesRegex(RuntimeError, "did not become visible"):
                _smoke_test_app(lambda _root: None)
        self.assertTrue(hidden_root.destroyed)

    def test_vlc_smoke_test_initializes_and_releases_native_runtime(self):
        import app_media

        instance = unittest.mock.Mock()
        vlc_module = type(
            "VlcModule",
            (),
            {
                "Instance": staticmethod(lambda *_args: instance),
                "libvlc_get_version": staticmethod(lambda: b"3.0.23"),
            },
        )
        with (
            patch.object(app_media.MediaMixin, "_prepare_bundled_vlc_runtime") as prepare,
            patch.dict(sys.modules, {"vlc": vlc_module}),
            patch("builtins.print") as print_version,
        ):
            self.assertEqual(_smoke_test_vlc_runtime(), 0)

        prepare.assert_called_once_with(unittest.mock.ANY)
        instance.release.assert_called_once_with()
        print_version.assert_called_once_with("VLC native runtime initialized: 3.0.23")


class PortableLauncherModeTests(unittest.TestCase):
    def test_cli_mode_forwards_arguments_and_returns_the_cli_status(self):
        with (
            patch.object(sys, "argv", ["launch.py", "--cli", "--help"]),
            patch("launch._attach_console") as attach_console,
            patch("launch._ensure_dependencies") as ensure_dependencies,
            patch("cli.main", return_value=7) as run_cli,
        ):
            self.assertEqual(launch.main(), 7)
        attach_console.assert_called_once_with()
        ensure_dependencies.assert_called_once_with()
        run_cli.assert_called_once_with(["--help"])

    def test_api_mode_starts_the_rest_server_without_opening_the_gui(self):
        with (
            patch.object(sys, "argv", ["launch.py", "--api"]),
            patch("launch._attach_console") as attach_console,
            patch("launch._ensure_dependencies") as ensure_dependencies,
            patch("api.main") as run_api,
        ):
            self.assertEqual(launch.main(), 0)
        attach_console.assert_called_once_with()
        ensure_dependencies.assert_called_once_with()
        run_api.assert_called_once_with()

    def test_vlc_smoke_mode_initializes_runtime_without_starting_gui(self):
        with (
            patch.object(sys, "argv", ["launch.py", "--vlc-smoke-test"]),
            patch("launch._attach_console") as attach_console,
            patch("launch._ensure_dependencies") as ensure_dependencies,
            patch("launch._smoke_test_vlc_runtime", return_value=0) as run_smoke,
        ):
            self.assertEqual(launch.main(), 0)
        attach_console.assert_called_once_with()
        ensure_dependencies.assert_not_called()
        run_smoke.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
