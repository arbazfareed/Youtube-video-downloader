import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import DownloaderApp, _convert_media_to_mp3
from app_media import MediaMixin


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
            "open_statistics_dashboard",
            "copy_selected_link",
            "resume_selected",
            "play_selected_media",
            "open_selected_media_in_system_player",
            "_play_media_in_app",
            "browse_local_media",
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
        app.jobs = Mock()
        app.jobs.selection.return_value = ()
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
        app.jobs = Mock()
        app.jobs.selection.return_value = ()
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


class MediaPlaybackTests(unittest.TestCase):
    def test_play_action_uses_embedded_player_for_existing_local_media(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing-video.mp4"
            path.write_bytes(b"test media")
            app = MediaMixin()
            app.root = Mock()
            app.jobs = SimpleNamespace(selection=Mock(return_value=()))
            app._selected_media_path = Mock(return_value=path)
            app._t = lambda text: text

            with patch.object(MediaMixin, "_play_media_in_app") as embedded_player:
                MediaMixin.play_selected_media(app)

            app._selected_media_path.assert_called_once_with()
            embedded_player.assert_called_once_with(path)

    def test_play_action_offers_system_player_when_embedded_player_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing-video.mp4"
            path.write_bytes(b"test media")
            app = MediaMixin()
            app.root = Mock()
            app.jobs = SimpleNamespace(selection=Mock(return_value=()))
            app._selected_media_path = Mock(return_value=path)
            app._t = lambda text: text

            with (
                patch.object(
                    MediaMixin,
                    "_play_media_in_app",
                    side_effect=ImportError("VLC is not installed"),
                ),
                patch("app_media.messagebox.askyesno", return_value=True) as ask,
                patch.object(MediaMixin, "open_media_in_system_player") as system_player,
            ):
                MediaMixin.play_selected_media(app)

            app._selected_media_path.assert_called_once_with()
            ask.assert_called_once()
            system_player.assert_called_once_with(path)

    def test_system_player_action_remains_available_without_vlc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing-video.mp4"
            path.write_bytes(b"test media")
            app = MediaMixin()
            app.root = Mock()
            with (
                patch("app_media.sys.platform", "win32"),
                patch("app_media.shutil.which", return_value=None),
                patch("app_media.subprocess.Popen") as player,
                patch("app_media.os.startfile", create=True) as startfile,
            ):
                app.open_media_in_system_player(path)
            self.assertTrue(player.called or startfile.called)
            if player.called:
                self.assertIn(str(path), player.call_args.args[0])
            else:
                startfile.assert_called_once_with(path)

    def test_local_media_picker_accepts_audio_and_video_and_rejects_other_files(self):
        app = SimpleNamespace(root=Mock(), _t=lambda text: text)
        with tempfile.TemporaryDirectory() as directory:
            media_path = Path(directory) / "existing-audio.mp3"
            media_path.write_bytes(b"audio")
            with patch(
                "app_media.filedialog.askopenfilename",
                return_value=str(media_path),
            ) as picker:
                selected = MediaMixin._choose_local_media(app)
            self.assertEqual(selected, media_path)
            self.assertIn("*.mp3", picker.call_args.kwargs["filetypes"][0][1])

            unsupported_path = Path(directory) / "notes.txt"
            unsupported_path.write_text("not media", encoding="utf-8")
            with (
                patch(
                    "app_media.filedialog.askopenfilename",
                    return_value=str(unsupported_path),
                ),
                patch("app_media.messagebox.showerror") as show_error,
            ):
                selected = MediaMixin._choose_local_media(app)
            self.assertIsNone(selected)
            show_error.assert_called_once()

    def test_in_app_playback_opens_supported_video_and_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            for suffix in (".mp4", ".mp3"):
                with self.subTest(suffix=suffix):
                    path = Path(directory) / f"sample{suffix}"
                    path.write_bytes(b"test media")
                    app = MediaMixin()
                    app.root = Mock()
                    app.jobs = SimpleNamespace(
                        selection=Mock(return_value=("job-1",))
                    )
                    app._integrity_guard = Mock(return_value=True)
                    app._selected_output_path = Mock(return_value=path)
                    app._t = lambda text: text
                    vlc_instance = Mock()
                    vlc_player = vlc_instance.media_player_new.return_value
                    vlc_player.get_state.return_value = 0
                    vlc_module = SimpleNamespace(
                        Instance=Mock(return_value=vlc_instance),
                        State=SimpleNamespace(Ended=1, Error=2),
                    )
                    video_surface = Mock()
                    video_surface.winfo_id.return_value = 42
                    window = Mock()
                    volume = Mock()
                    volume.get.return_value = 80
                    with (
                        patch("app_media.sys.platform", "win32"),
                        patch.dict("sys.modules", {"vlc": vlc_module}),
                        patch("app_media.tk.Toplevel", return_value=window),
                        patch("app_media.tk.Frame", return_value=video_surface),
                        patch("app_media.tk.IntVar", return_value=volume),
                        patch("app_media.ttk.Frame"),
                        patch("app_media.ttk.Button"),
                        patch("app_media.ttk.Label"),
                        patch("app_media.ttk.Scale"),
                    ):
                        MediaMixin.play_selected_media(app)
                    vlc_instance.media_new.assert_called_once_with(str(path))
                    vlc_player.set_hwnd.assert_called_once_with(42)
                    vlc_player.play.assert_called_once_with()

    def test_copy_selected_link_uses_clipboard_and_reports_success(self):
        app = SimpleNamespace(
            root=SimpleNamespace(
                clipboard_clear=Mock(),
                clipboard_append=Mock(),
                update_idletasks=Mock(),
            ),
            jobs=SimpleNamespace(
                selection=Mock(return_value=("job-1",)),
                set=Mock(return_value="https://example.com/audio.mp3"),
            ),
            progress_summary=SimpleNamespace(set=Mock()),
            _t=lambda text: text,
        )

        DownloaderApp.copy_selected_link(app)

        app.root.clipboard_clear.assert_called_once_with()
        app.root.clipboard_append.assert_called_once_with(
            "https://example.com/audio.mp3"
        )
        app.progress_summary.set.assert_called_once_with("Link copied to clipboard.")


if __name__ == "__main__":
    unittest.main()
