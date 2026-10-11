import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import DownloaderApp, _convert_media_to_mp3


class _FakeQueue:
    def __init__(self, statuses):
        self.rows = {job_id: {"status": status} for job_id, status in statuses.items()}
        self.children = list(statuses)

    def exists(self, job_id):
        return job_id in self.rows

    def set(self, job_id, column):
        return self.rows[job_id][column]

    def move(self, job_id, _parent, index):
        if job_id in self.children:
            self.children.remove(job_id)
        self.children.insert(index, job_id)

    def detach(self, job_id):
        if job_id in self.children:
            self.children.remove(job_id)


class LocalMp3ConversionTests(unittest.TestCase):
    def test_converts_to_mp3_using_ffmpeg_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "offline-video.mkv"
            destination = root / "offline-audio.mp3"
            ffmpeg_directory = root / "bin"
            source.write_bytes(b"source")

            def fake_ffmpeg(command, **_kwargs):
                Path(command[-1]).write_bytes(b"encoded mp3")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("app.subprocess.run", side_effect=fake_ffmpeg) as run:
                _convert_media_to_mp3(source, destination, ffmpeg_directory)

            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(destination.read_bytes(), b"encoded mp3")
            command = run.call_args.args[0]
            self.assertIn("libmp3lame", command)
            self.assertIn("-vn", command)
            self.assertEqual(command[command.index("-i") + 1], str(source))

    def test_failed_conversion_preserves_existing_output_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "offline-audio.wav"
            destination = root / "offline-audio.mp3"
            source.write_bytes(b"source")
            destination.write_bytes(b"previous output")

            with patch(
                "app.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, "", "unsupported codec"),
            ):
                with self.assertRaisesRegex(RuntimeError, "unsupported codec"):
                    _convert_media_to_mp3(source, destination, root / "bin")

            self.assertEqual(destination.read_bytes(), b"previous output")
            self.assertEqual(list(root.glob(".offline-audio.*.mp3")), [])


class QueueFilterTests(unittest.TestCase):
    def test_filters_reattach_rows_without_changing_queue_order(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.jobs = _FakeQueue({
            "video": "Complete",
            "live": "Downloading",
            "image": "Complete",
            "queued": "Queued",
            "failed": "Failed",
            "archive": "Complete",
        })
        app._queue_job_ids = ["video", "live", "image", "queued", "failed", "archive"]
        app._download_paths = {
            "video": Path("video.mp4"),
            "live": Path("live.mp4"),
            "image": Path("cover.png"),
            "queued": Path("bundle.zip"),
            "failed": Path("broken.mkv"),
            "archive": Path("backup.zip"),
        }
        app.queue_hint_label = Mock()
        expected = {
            "all": app._queue_job_ids,
            "downloading": ["live", "queued"],
            "completed": ["video", "image", "archive"],
            "media": ["video", "image"],
        }

        for filter_name in ("media", "completed", "downloading", "all", "media", "all"):
            app._queue_filter = filter_name
            app._apply_queue_filter()
            self.assertEqual(app.jobs.children, expected[filter_name])


class UiStartupWiringTests(unittest.TestCase):
    def test_sidebar_and_queue_callbacks_exist(self):
        required_callbacks = (
            "resume_selected",
            "play_selected_media",
            "open_selected_location",
            "extract_selected_archive",
            "extract_local_archive",
            "create_zip_from_file",
            "create_zip_from_folder",
            "open_selected_image_tools",
            "_select_image_gallery_mode",
            "open_batch_dialog",
            "open_sequence_dialog",
            "convert_local_file_to_mp3",
            "convert_docx_file_to_pdf",
            "convert_pdf_file_to_docx",
            "_show_image_context_menu",
            "_open_clicked_row_action",
            "_show_selected_thumbnail",
        )
        missing = [
            name for name in required_callbacks
            if not callable(getattr(DownloaderApp, name, None))
        ]
        self.assertEqual(missing, [])

    def test_sidebar_wheel_scrolls_only_when_pointer_is_inside_it(self):
        class FakeWidget:
            def __init__(self, name):
                self.name = name

            def __str__(self):
                return self.name

        class FakeCanvas(FakeWidget):
            def __init__(self):
                super().__init__(".app.sidebar")
                self.scrolls = []

            def yview_scroll(self, units, _kind):
                self.scrolls.append(units)

        app = DownloaderApp.__new__(DownloaderApp)
        app.sidebar_canvas = FakeCanvas()
        app.root = Mock()
        app.root.winfo_containing.return_value = FakeWidget(".app.sidebar.content.button")

        result = app._scroll_sidebar(SimpleNamespace(num=5, x_root=5, y_root=5))

        self.assertEqual(result, "break")
        self.assertEqual(app.sidebar_canvas.scrolls, [1])
        app.root.winfo_containing.return_value = FakeWidget(".app.queue")
        result = app._scroll_sidebar(SimpleNamespace(delta=120, x_root=5, y_root=5))
        self.assertIsNone(result)
        self.assertEqual(app.sidebar_canvas.scrolls, [1])

    def test_image_tools_allow_choosing_a_local_image_without_a_queue_selection(self):
        source = Path("local-photo.jpg")
        app = DownloaderApp.__new__(DownloaderApp)
        app.root = Mock()
        app.root.winfo_rootx.return_value = 0
        app.root.winfo_rooty.return_value = 0
        app._selected_output_path = Mock(return_value=None)
        app._style_context_menu = Mock()
        app._add_image_tools = Mock()
        menu = Mock()

        with (
            patch("app.filedialog.askopenfilename", return_value=str(source)) as picker,
            patch("app.tk.Menu", return_value=menu),
        ):
            app.open_selected_image_tools()

        picker.assert_called_once()
        self.assertEqual(picker.call_args.kwargs["title"], "Choose an image to edit")
        app._add_image_tools.assert_called_once_with(menu, source)
        menu.tk_popup.assert_called_once()

    def test_image_tools_reject_unsupported_local_file_selection(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.root = Mock()
        app._selected_output_path = Mock(return_value=None)

        with (
            patch(
                "app.filedialog.askopenfilename",
                return_value="local-document.pdf",
            ),
            patch("app.messagebox.showerror") as show_error,
            patch("app.tk.Menu") as make_menu,
        ):
            app.open_selected_image_tools()

        show_error.assert_called_once()
        make_menu.assert_not_called()


if __name__ == "__main__":
    unittest.main()
