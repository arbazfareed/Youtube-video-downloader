import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app_media
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
    def test_preview_splitter_reserves_space_for_compact_timeline(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app._main_splitter_stacked = False
        app._main_splitter = Mock()
        app._main_splitter.winfo_width.return_value = 1004
        app.root = Mock()

        app._set_initial_preview_splitter_position()

        app._main_splitter.sashpos.assert_called_once_with(0, 608)
        self.assertTrue(app._main_splitter_initial_sash_set)

    def test_preview_splitter_retries_before_it_is_mapped(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app._main_splitter_stacked = False
        app._main_splitter = Mock()
        app._main_splitter.winfo_width.return_value = 1
        app.root = Mock()

        app._set_initial_preview_splitter_position()

        app.root.after.assert_called_once_with(
            50,
            app._set_initial_preview_splitter_position,
        )
        self.assertTrue(app._main_splitter_initial_sash_pending)
        app._main_splitter.sashpos.assert_not_called()

    def test_responsive_layout_reflows_preview_without_clipping_narrow_screens(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.root = Mock()
        app.root.winfo_width.side_effect = (600, 900, 1300)
        app._main_outer = Mock()
        app._sidebar_host = Mock()
        app._main_splitter = Mock()
        app._main_splitter_stacked = False
        app._main_content_frame = Mock()
        app._media_inspector = Mock()
        app.preview_image_label = Mock()
        app.preview_details = Mock()

        app._adapt_responsive_layout()

        app._sidebar_host.grid_remove.assert_called_once_with()
        app._main_splitter.forget.assert_any_call(app._main_content_frame)
        app._main_splitter.forget.assert_any_call(app._media_inspector)
        app._main_content_frame.grid.assert_called_with(
            row=0, column=0, sticky="nsew",
        )
        app._media_inspector.grid.assert_called_with(
            row=1, column=0, sticky="nsew",
        )
        app._main_splitter.grid_configure.assert_called_with(
            row=0, column=0, columnspan=1, padx=16, pady=(16, 0),
        )
        app._main_outer.columnconfigure.assert_any_call(0, weight=1, minsize=0)

        app._adapt_responsive_layout()
        app._sidebar_host.grid.assert_called_once_with()
        app._main_splitter.grid_configure.assert_called_with(
            row=0, column=1, columnspan=1, padx=(0, 16), pady=16,
        )
        app.preview_image_label.configure.assert_called_with(wraplength=718)

        app._adapt_responsive_layout()
        app._main_content_frame.grid_forget.assert_called_once_with()
        app._media_inspector.grid_forget.assert_called_once_with()
        app._main_splitter.add.assert_has_calls(
            [
                unittest.mock.call(app._main_content_frame, weight=4),
                unittest.mock.call(app._media_inspector, weight=1),
            ]
        )
        app._main_splitter.grid_configure.assert_called_with(
            row=0, column=1, columnspan=2, padx=(0, 16), pady=16,
        )
        app.preview_details.configure.assert_called_with(wraplength=240)

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
            "_focus_url_shortcut",
            "_focus_queue_shortcut",
            "_focus_progress_shortcut",
            "_toggle_pause_from_queue",
            "play_selected_media_in_preview",
        )
        missing = [
            name for name in required_callbacks
            if not callable(getattr(DownloaderApp, name, None))
        ]
        self.assertEqual(missing, [])

    def test_accessibility_keyboard_shortcuts_focus_their_targets_and_toggle_pause(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.url_entry = Mock()
        app.jobs = Mock()
        app.progress_summary_label = Mock()
        app.toggle_pause_selected = Mock()

        self.assertEqual(app._focus_url_shortcut(), "break")
        app.url_entry.focus_set.assert_called_once_with()
        self.assertEqual(app._focus_queue_shortcut(), "break")
        app.jobs.focus_set.assert_called_once_with()
        self.assertEqual(app._focus_progress_shortcut(), "break")
        app.progress_summary_label.focus_set.assert_called_once_with()
        self.assertEqual(app._toggle_pause_from_queue(), "break")
        app.toggle_pause_selected.assert_called_once_with()

    def test_space_shortcut_toggles_smart_vlc_without_stealing_text_input(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app._in_app_player = Mock()
        app._toggle_in_app_playback = Mock()
        frame_event = SimpleNamespace(widget=SimpleNamespace(
            winfo_class=Mock(return_value="Frame"),
        ))
        button_event = SimpleNamespace(widget=SimpleNamespace(
            winfo_class=Mock(return_value="TButton"),
        ))

        self.assertEqual(app._toggle_in_app_playback_from_key(frame_event), "break")
        app._toggle_in_app_playback.assert_called_once_with()
        self.assertIsNone(app._toggle_in_app_playback_from_key(button_event))
        app._toggle_in_app_playback.assert_called_once_with()

    def test_space_on_queue_pauses_download_when_smart_vlc_is_closed(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app._in_app_player = None
        app.toggle_pause_selected = Mock()

        self.assertEqual(app._toggle_pause_from_queue(), "break")

        app.toggle_pause_selected.assert_called_once_with()

    def test_space_on_queue_toggles_smart_vlc_when_player_is_open(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app._in_app_player = Mock()
        app._toggle_in_app_playback = Mock()
        app.toggle_pause_selected = Mock()

        self.assertEqual(app._toggle_pause_from_queue(), "break")

        app._toggle_in_app_playback.assert_called_once_with()
        app.toggle_pause_selected.assert_not_called()

    def test_keyboard_shortcuts_are_registered_for_app_navigation(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.root = Mock()

        app._bind_keyboard_shortcuts()

        self.assertEqual(
            [call.args[0] for call in app.root.bind_all.call_args_list],
            [
                "<Control-comma>",
                "<F1>",
                "<Control-Return>",
                "<Control-o>",
                "<Control-l>",
                "<Control-j>",
                "<Alt-s>",
                "<space>",
                "<Left>",
                "<Right>",
                "<Up>",
                "<Down>",
            ],
        )
        self.assertTrue(
            all(call.kwargs["add"] == "+" for call in app.root.bind_all.call_args_list)
        )

    def test_playback_arrow_keys_control_smart_vlc_and_dashboard_preview(self):
        app = MediaMixin()
        app.root = Mock()
        player_window = Mock()
        app._in_app_player_window = player_window
        app._in_app_controls_overlay_window = None
        app._in_app_top_controls_overlay_window = None
        app._in_app_player = Mock()
        app._nudge_in_app_player_seek = Mock()
        app._adjust_in_app_volume = Mock()
        app._show_in_app_controls = Mock()
        player_widget = Mock()
        player_widget.master = None
        player_widget.winfo_toplevel.return_value = player_window

        for key, method, argument in (
            ("Left", app._nudge_in_app_player_seek, -5),
            ("Right", app._nudge_in_app_player_seek, 5),
            ("Up", app._adjust_in_app_volume, 5),
            ("Down", app._adjust_in_app_volume, -5),
        ):
            self.assertEqual(
                app._handle_playback_arrow_key(
                    SimpleNamespace(keysym=key, widget=player_widget)
                ),
                "break",
            )
            method.assert_called_with(argument)

        app._in_app_player_window = None
        app._in_app_player = None
        app.preview_container = Mock()
        app._preview_vlc_player = Mock()
        app._nudge_video_preview_seek = Mock()
        app._adjust_video_preview_volume = Mock()
        preview_widget = SimpleNamespace(
            master=app.preview_container,
            winfo_toplevel=Mock(return_value=app.root),
        )
        self.assertEqual(
            app._handle_playback_arrow_key(
                SimpleNamespace(keysym="Left", widget=preview_widget)
            ),
            "break",
        )
        app._nudge_video_preview_seek.assert_called_once_with(-5)
        self.assertEqual(
            app._handle_playback_arrow_key(
                SimpleNamespace(keysym="Up", widget=preview_widget)
            ),
            "break",
        )
        app._adjust_video_preview_volume.assert_called_once_with(5)

    def test_play_in_app_button_toggles_same_open_media_instead_of_reopening(self):
        app = MediaMixin()
        path = Path("existing-video.mp4").resolve()
        app._selected_media_path = Mock(return_value=path)
        app._in_app_media_path = path
        app._in_app_player = Mock()
        app._toggle_in_app_playback = Mock()

        MediaMixin.play_selected_media(app)

        app._toggle_in_app_playback.assert_called_once_with()

    def test_play_in_preview_prompts_for_a_video_when_queue_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-video.mp4"
            path.write_bytes(b"video")
            app = MediaMixin()
            app.root = Mock()
            app.jobs = SimpleNamespace(selection=Mock(return_value=()))
            app._local_media_path = None
            app._choose_local_video = Mock(return_value=path)
            app._show_video_preview = Mock()
            app.preview_details = Mock()
            app._t = lambda text: text

            MediaMixin.play_selected_media_in_preview(app)

        self.assertEqual(app._local_media_path, path)
        app._show_video_preview.assert_called_once_with(path)
        app._choose_local_video.assert_called_once_with()
        app.preview_details.configure.assert_called_once_with(
            text="local-video.mp4\nVideo preview\n0.0 MB"
        )

    def test_preview_video_list_finds_playlist_outputs_and_active_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            playlist = root / "playlist"
            playlist.mkdir()
            completed = playlist / "01 - completed.mp4"
            partial = playlist / "02 - downloading.webm.part"
            audio = playlist / "audio.m4a"
            completed.write_bytes(b"video")
            partial.write_bytes(b"partial")
            audio.write_bytes(b"audio")

            app = MediaMixin()
            app.jobs = Mock()
            app.jobs.selection.return_value = ("job",)
            app._selected_output_path = Mock(return_value=root)
            app._download_paths = {"job": root}
            app.download_options = {}
            app._local_media_path = None
            app._preview_media_path = None
            app._t = lambda text: text
            app.preview_video_selector = Mock()
            app.preview_video_choice = Mock()
            app.preview_video_choice.get.return_value = ""
            app.preview_video_status = Mock()

            paths = MediaMixin._refresh_preview_video_choices(app)

        self.assertEqual(paths, [completed.resolve(), partial.resolve()])
        self.assertEqual(
            list(app._preview_video_choices.values()),
            [completed.resolve(), partial.resolve()],
        )
        app.preview_video_selector.configure.assert_called_once_with(
            values=(
                "playlist/01 - completed.mp4",
                "playlist/02 - downloading.webm.part (Downloading)",
            ),
            state="readonly",
        )
        app.preview_video_choice.set.assert_called_once_with(
            "playlist/01 - completed.mp4"
        )

    def test_selecting_active_partial_video_loads_it_into_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4.part"
            path.write_bytes(b"partial video")
            app = MediaMixin()
            app._t = lambda text: text
            app.root = Mock()
            app.preview_video_choice = Mock()
            app.preview_video_choice.get.return_value = "video.mp4.part (Downloading)"
            app._preview_video_choices = {
                "video.mp4.part (Downloading)": path,
            }
            app.current_thumbnail = None
            app.inspector_status = Mock()
            app.preview_video_status = Mock()
            app._show_video_preview = Mock()
            app.preview_details = Mock()

            MediaMixin._select_preview_video(app)

        app._show_video_preview.assert_called_once_with(path)
        app.inspector_status.set.assert_called_once_with("Downloading")
        app.preview_video_status.set.assert_called_once()
        self.assertEqual(app._local_media_path, path)
        self.assertIn(str(path), app.preview_details.configure.call_args.kwargs["text"])

    def test_active_playlist_preview_uses_finished_entry_and_lists_partial_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            finished = root / "playlist" / "01-finished.mp4"
            partial = root / "playlist" / "02-downloading.mp4.part"
            finished.parent.mkdir()
            finished.write_bytes(b"video")
            partial.write_bytes(b"partial")
            app = MediaMixin()
            app.jobs = Mock()
            app.jobs.selection.return_value = ("active-job",)
            app.jobs.item.return_value = ("Downloading media", "42%")
            app._selected_output_path = Mock(return_value=root)
            app._download_paths = {"active-job": root}
            app.download_options = {}
            app._local_media_path = None
            app._clear_video_preview = Mock()
            app._show_video_preview = Mock()
            app.inspector_status = Mock()
            app.preview_details = Mock()
            app.preview_image_label = Mock()
            app.preview_video_selector = Mock()
            app.preview_video_choice = Mock()
            app.preview_video_choice.get.return_value = ""
            app.preview_video_status = Mock()
            app._t = lambda text: text

            MediaMixin._show_selected_thumbnail(app)

        app._show_video_preview.assert_called_once_with(finished.resolve())
        self.assertEqual(
            list(app._preview_video_choices.values()),
            [finished.resolve(), partial.resolve()],
        )

    def test_active_preview_video_list_refresh_is_scheduled_once(self):
        app = MediaMixin()
        app.jobs = Mock()
        app.jobs.selection.return_value = ("active-job",)
        app._preview_video_refresh_after = None
        app.root = Mock()

        MediaMixin._schedule_preview_video_refresh(app, "active-job")
        MediaMixin._schedule_preview_video_refresh(app, "active-job")

        app.root.after.assert_called_once_with(
            1500,
            app._refresh_scheduled_preview_video_choices,
        )

    def test_video_preview_picker_accepts_supported_local_video(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chosen-video.mkv"
            path.write_bytes(b"video")
            app = MediaMixin()
            app.root = Mock()
            app._t = lambda text: text

            with patch(
                "app_media.filedialog.askopenfilename",
                return_value=str(path),
            ) as choose_file:
                selected = MediaMixin._choose_local_video(app)

        self.assertEqual(selected, path)
        self.assertIn("Choose a video to preview", choose_file.call_args.kwargs["title"])
        self.assertIn("*.mkv", choose_file.call_args.kwargs["filetypes"][0][1])

    def test_shortcut_help_is_localized_for_urdu(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app.language = Mock()
        app.language.get.return_value = "Urdu"

        shortcut_text = app._keyboard_shortcuts_text()

        self.assertIn("کی بورڈ شارٹ کٹس", shortcut_text)
        self.assertIn("Ctrl+L", shortcut_text)
        self.assertIn("Ctrl+J", shortcut_text)
        self.assertIn("Alt+S", shortcut_text)
        self.assertIn("Shift+Tab", shortcut_text)


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
    def test_preview_shows_error_in_video_surface_if_vlc_fails_to_decode(self):
        app = MediaMixin()
        app.root = Mock()
        app._preview_vlc = SimpleNamespace(
            State=SimpleNamespace(Error="error", Playing="playing"),
        )
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.get_state.return_value = "error"
        app._preview_vlc_instance = Mock()
        app._preview_playback_after = None
        app.preview_video_placeholder = Mock()
        app.preview_player_play_button = Mock()
        app._t = lambda text: text

        MediaMixin._poll_video_preview(app)

        app.preview_video_placeholder.configure.assert_called_with(
            text=(
                "VLC could not play this video. Try another file or use "
                "Open in system player."
            )
        )
        app.preview_video_placeholder.place.assert_called_with(
            relx=0.5,
            rely=0.5,
            anchor="center",
        )

    def test_bundled_vlc_runtime_is_selected_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            app_directory = Path(directory)
            vlc_directory = app_directory / "VLC"
            plugin_directory = vlc_directory / "plugins"
            plugin_directory.mkdir(parents=True)
            (vlc_directory / "libvlc.dll").write_bytes(b"test")
            executable = app_directory / "SmartDownloader13.exe"
            dll_directory = Mock()

            with (
                patch("app_media.sys.platform", "win32"),
                patch("app_media.sys.frozen", True, create=True),
                patch("app_media.sys.executable", str(executable)),
                patch.dict("os.environ", {}, clear=True),
                patch(
                    "app_media.os.add_dll_directory",
                    return_value=dll_directory,
                    create=True,
                ),
                patch("app_media._VLC_DLL_DIRECTORY", None),
            ):
                MediaMixin._prepare_bundled_vlc_runtime(MediaMixin())
                MediaMixin._prepare_bundled_vlc_runtime(MediaMixin())

                self.assertEqual(
                    os.environ["PYTHON_VLC_LIB_PATH"],
                    str(vlc_directory.resolve() / "libvlc.dll"),
                )
                self.assertEqual(
                    os.environ["PYTHON_VLC_MODULE_PATH"],
                    str(plugin_directory.resolve()),
                )
                normalized_runtime = os.path.normcase(str(vlc_directory.resolve()))
                self.assertEqual(
                    sum(
                        os.path.normcase(entry) == normalized_runtime
                        for entry in os.environ["PATH"].split(os.pathsep)
                    ),
                    1,
                )
                app_media.os.add_dll_directory.assert_called_once_with(
                    str(vlc_directory.resolve())
                )

    def test_system_vlc_runtime_is_selected_when_not_bundled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app_directory = root / "app"
            app_directory.mkdir()
            vlc_directory = root / "Program Files" / "VideoLAN" / "VLC"
            (vlc_directory / "plugins").mkdir(parents=True)
            (vlc_directory / "libvlc.dll").write_bytes(b"test")
            executable = app_directory / "SmartDownloader13.exe"

            with (
                patch("app_media.sys.platform", "win32"),
                patch("app_media.sys.frozen", True, create=True),
                patch("app_media.sys.executable", str(executable)),
                patch.dict(
                    os.environ,
                    {
                        "ProgramFiles": str(root / "Program Files"),
                        "ProgramFiles(x86)": str(root / "Program Files (x86)"),
                    },
                    clear=True,
                ),
                patch("app_media.shutil.which", return_value=None),
                patch(
                    "app_media.os.add_dll_directory",
                    return_value=Mock(),
                    create=True,
                ) as add_dll_directory,
                patch("app_media._VLC_DLL_DIRECTORY", None),
            ):
                MediaMixin._prepare_bundled_vlc_runtime(MediaMixin())
                self.assertEqual(
                    os.environ["PYTHON_VLC_LIB_PATH"],
                    str(vlc_directory / "libvlc.dll"),
                )
                self.assertEqual(
                    os.environ["PYTHON_VLC_MODULE_PATH"],
                    str(vlc_directory / "plugins"),
                )
                add_dll_directory.assert_called_once_with(str(vlc_directory))

    def test_preview_volume_and_seek_step_buttons_apply_bounded_steps(self):
        app = MediaMixin()
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.is_seekable.return_value = True
        app._preview_vlc_player.get_length.return_value = 60_000
        app._preview_vlc_player.get_time.return_value = 2_000
        app.preview_player_volume = Mock()
        app.preview_player_volume.get.return_value = 80

        MediaMixin._nudge_video_preview_seek(app, -5)
        app._preview_vlc_player.set_time.assert_called_once_with(0)

        app._preview_vlc_player.get_time.return_value = 58_000
        MediaMixin._nudge_video_preview_seek(app, 5)
        app._preview_vlc_player.set_time.assert_called_with(60_000)

        MediaMixin._adjust_video_preview_volume(app, 5)
        app.preview_player_volume.set.assert_called_with(85)
        app._preview_vlc_player.audio_set_volume.assert_called_with(85)

        app.preview_player_volume.get.return_value = 0
        MediaMixin._adjust_video_preview_volume(app, -5)
        app.preview_player_volume.set.assert_called_with(0)
        app._preview_vlc_player.audio_set_volume.assert_called_with(0)

    def test_play_action_uses_separate_player_for_existing_local_media(self):
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

    def test_in_app_playback_opens_separate_player_for_video_and_audio(self):
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
                    preview = Mock()
                    app.preview_image_label = Mock()
                    app.preview_image_label.master = preview
                    app.preview_image_label.winfo_exists.return_value = True
                    vlc_instance = Mock()
                    vlc_player = vlc_instance.media_player_new.return_value
                    vlc_player.get_state.return_value = 0
                    vlc_player.get_length.return_value = 0
                    vlc_player.get_time.return_value = 0
                    vlc_player.is_seekable.return_value = False
                    vlc_player.audio_get_track_description.return_value = []
                    vlc_player.video_get_spu_description.return_value = []
                    vlc_module = SimpleNamespace(
                        Instance=Mock(return_value=vlc_instance),
                        State=SimpleNamespace(Ended=1, Error=2),
                    )
                    video_surface = Mock()
                    video_surface.winfo_id.return_value = 42
                    video_surface.winfo_width.return_value = 1120
                    video_surface.winfo_height.return_value = 700
                    video_surface.winfo_rootx.return_value = 0
                    video_surface.winfo_rooty.return_value = 0
                    controls_overlay = Mock()
                    controls_overlay.winfo_reqheight.return_value = 40
                    controls_window = Mock()
                    top_controls_window = Mock()
                    top_controls = Mock()
                    timeline = Mock()
                    timeline.winfo_width.return_value = 500
                    timeline.winfo_height.return_value = 20
                    player_window = Mock()
                    top_controls.winfo_reqheight.return_value = 40
                    volume = Mock()
                    volume.get.return_value = 80
                    variables = [Mock() for _ in range(7)]
                    player_buttons = [Mock() for _ in range(6)]
                    position = Mock()
                    position.get.return_value = 0
                    with (
                        patch("app_media.sys.platform", "win32"),
                        patch.dict("sys.modules", {"vlc": vlc_module}),
                        patch(
                            "app_media.tk.Toplevel",
                            side_effect=[
                                player_window,
                                controls_window,
                                top_controls_window,
                            ],
                        ) as toplevel,
                        patch(
                            "app_media.tk.Frame",
                            side_effect=[
                                video_surface,
                                top_controls,
                                controls_overlay,
                            ],
                        ),
                        patch("app_media.tk.Canvas", return_value=timeline),
                        patch("app_media.tk.Label") as label_factory,
                        patch(
                            "app_media.tk.Button",
                            side_effect=player_buttons,
                        ) as button_factory,
                        patch("app_media.tk.Scale"),
                        patch("app_media.tk.IntVar", return_value=volume),
                        patch("app_media.tk.DoubleVar", return_value=position),
                        patch(
                            "app_media.tk.StringVar",
                            side_effect=variables,
                        ) as string_var_factory,
                    ):
                        MediaMixin.play_selected_media(app)
                    vlc_instance.media_new.assert_called_once_with(str(path))
                    vlc_player.set_hwnd.assert_called_once_with(42)
                    vlc_player.play.assert_called_once_with()
                    self.assertEqual(
                        toplevel.call_args_list,
                        [
                            unittest.mock.call(app.root),
                            unittest.mock.call(player_window),
                            unittest.mock.call(player_window),
                        ],
                    )
                    player_window.title.assert_called_once_with(
                        f"Smart VLC — {path.name}"
                    )
                    player_window.protocol.assert_called_once_with(
                        "WM_DELETE_WINDOW", app._close_in_app_player
                    )
                    player_window.geometry.assert_called_once_with("1120x700")
                    player_window.minsize.assert_called_once_with(800, 500)
                    player_window.iconbitmap.assert_called_once()
                    player_window.bind.assert_any_call(
                        "<F11>", app._toggle_in_app_fullscreen, add="+"
                    )
                    player_window.bind.assert_any_call(
                        "<Escape>", app._exit_in_app_fullscreen, add="+"
                    )
                    player_window.bind.assert_any_call(
                        "<KeyPress>", app._show_in_app_controls, add="+"
                    )
                    player_window.destroy.assert_not_called()
                    app.preview_image_label.grid_remove.assert_not_called()
                    self.assertIs(app._in_app_player_window, player_window)
                    vlc_player.audio_set_mute.assert_called_once_with(False)
                    vlc_player.audio_set_volume.assert_called_once_with(80)
                    self.assertEqual(
                        [
                            call.kwargs["text"]
                            for call in button_factory.call_args_list
                        ],
                        ["←", "⚙", "Ⅱ", "CC", "⚙", "⛶"],
                    )
                    string_var_factory.assert_any_call(value="1.0x")
                    self.assertIn(
                        unittest.mock.call(
                            top_controls,
                            text=path.name,
                            background="#000000",
                            foreground="#FFFFFF",
                            font=("Segoe UI", 11, "bold"),
                            anchor="center",
                        ),
                        label_factory.call_args_list,
                    )
                    self.assertEqual(app._in_app_timeline, timeline)
                    self.assertIs(
                        app._in_app_controls_overlay_window,
                        controls_window,
                    )
                    self.assertIs(
                        app._in_app_top_controls_overlay_window,
                        top_controls_window,
                    )
                    controls_window.overrideredirect.assert_called_once_with(True)
                    controls_window.transient.assert_called_once_with(player_window)
                    controls_window.attributes.assert_any_call("-alpha", 0.0)
                    controls_window.geometry.assert_called_once_with(
                        "1120x40+0+660"
                    )
                    self.assertEqual(
                        timeline.bind.call_args_list[0].args[0],
                        "<ButtonPress-1>",
                    )
                    controls_overlay.pack.assert_called_once_with(
                        fill="both",
                        expand=True,
                    )
                    self.assertEqual(
                        top_controls_window.bind.call_args_list[0].args[0],
                        "<F11>",
                    )
                    top_controls_window.bind.assert_any_call(
                        "<KeyPress>", app._show_in_app_controls, add="+"
                    )
                    controls_window.bind.assert_any_call(
                        "<KeyPress>", app._show_in_app_controls, add="+"
                    )
                    self.assertIs(
                        app._in_app_top_title_label,
                        label_factory.return_value,
                    )
                    player_window.bind.assert_any_call(
                        "<Motion>", app._show_in_app_controls, add="+"
                    )

    def test_video_preview_autoplays_on_its_embedded_canvas(self):
        app = MediaMixin()
        app._t = lambda text: text
        app.preview_image_label = Mock()
        app.preview_video_surface = Mock()
        app.preview_player_controls = Mock()
        app.preview_video_placeholder = Mock()
        app.preview_player_play_button = Mock()
        app.preview_player_current_time = Mock()
        app.preview_player_duration = Mock()
        app.preview_player_position = Mock()
        app._toggle_video_preview = Mock()
        path = Path("preview.mp4")

        MediaMixin._show_video_preview(app, path)

        self.assertEqual(app._preview_media_path, path)
        app.preview_image_label.grid_remove.assert_called_once_with()
        app.preview_video_surface.grid.assert_called_once_with()
        app.preview_player_controls.grid.assert_called_once_with()
        app.preview_video_placeholder.configure.assert_called_once_with(
            text="preview.mp4\nLoading preview",
        )
        app._toggle_video_preview.assert_called_once_with()
        app.preview_video_placeholder.place.assert_called_with(
            relx=0.5, rely=0.5, anchor="center",
        )

    def test_embedded_preview_uses_vlc_canvas_and_starts_with_audio_enabled(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._prepare_bundled_vlc_runtime = Mock()
        app._preview_media_path = Path("preview.mp4")
        app.preview_video_surface = Mock()
        app.preview_video_surface.winfo_id.return_value = 42
        app.preview_video_placeholder = Mock()
        app.preview_player_volume = Mock()
        app.preview_player_volume.get.return_value = 80
        app.preview_player_play_button = Mock()
        app._preview_playback_rate = Mock()
        app._preview_playback_rate.get.return_value = "1.0x"
        app._preview_playback_after = None
        vlc_instance = Mock()
        vlc_player = vlc_instance.media_player_new.return_value
        vlc_module = SimpleNamespace(Instance=Mock(return_value=vlc_instance))
        with (
            patch("app_media.sys.platform", "win32"),
            patch.dict("sys.modules", {"vlc": vlc_module}),
        ):
            MediaMixin._toggle_video_preview(app)

        vlc_instance.media_new.assert_called_once_with("preview.mp4")
        vlc_player.set_hwnd.assert_called_once_with(42)
        vlc_player.audio_set_mute.assert_called_once_with(False)
        vlc_player.audio_set_volume.assert_called_once_with(80)
        vlc_player.play.assert_called_once_with()
        app.preview_player_play_button.configure.assert_called_once_with(
            text="Ⅱ",
        )

    def test_dashboard_preview_settings_include_speed_audio_and_subtitles(self):
        app = MediaMixin()
        app.root = Mock()
        app._t = lambda text: text
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.audio_get_track_description.return_value = [
            (1, "English"),
            (2, "Urdu"),
        ]
        app._preview_vlc_player.audio_get_track.return_value = 1
        app._preview_vlc_player.video_get_spu_description.return_value = [
            (-1, "Disable"),
            (3, "English"),
        ]
        app._preview_vlc_player.video_get_spu.return_value = -1
        app._preview_audio_track = Mock()
        app._preview_playback_rate = Mock()
        app._preview_subtitle_track = Mock()
        app._preview_audio_tracks = {}
        app._preview_subtitle_tracks = {}
        app.preview_player_settings_button = Mock()
        app.preview_player_settings_button.winfo_rootx.return_value = 300
        app.preview_player_settings_button.winfo_rooty.return_value = 120
        menus = [Mock() for _ in range(4)]
        menus[0].winfo_reqheight.return_value = 80

        with patch("app_media.tk.Menu", side_effect=menus) as menu_factory:
            MediaMixin._show_video_preview_settings(
                app,
                app.preview_player_settings_button,
            )

        self.assertEqual(menu_factory.call_count, 4)
        self.assertEqual(
            [call.kwargs["label"] for call in menus[1].add_radiobutton.call_args_list],
            ["0.5x", "1.0x", "1.5x", "2.0x"],
        )
        self.assertEqual(
            [call.kwargs["label"] for call in menus[2].add_radiobutton.call_args_list],
            ["English", "Urdu"],
        )
        self.assertEqual(
            [call.kwargs["label"] for call in menus[3].add_radiobutton.call_args_list],
            ["Off", "English"],
        )
        self.assertEqual(
            [call.kwargs["label"] for call in menus[0].add_cascade.call_args_list],
            ["Playback speed", "Audio track", "Subtitles"],
        )
        self.assertEqual(app._preview_subtitle_tracks, {"English": 3})
        menus[0].tk_popup.assert_called_once_with(300, 40)
        menus[0].destroy.assert_called_once_with()

    def test_dashboard_preview_refreshes_subtitles_without_a_separate_cc_button(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.video_get_spu_description.return_value = [
            (-1, "Disable"),
        ]
        app._preview_subtitle_track = Mock()

        MediaMixin._refresh_video_preview_subtitle_tracks(app)

        self.assertEqual(app._preview_subtitle_tracks, {})
        app._preview_subtitle_track.set.assert_called_once_with("Off")

    def test_dashboard_preview_cc_enables_first_available_subtitle_track(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.video_get_spu.return_value = -1
        app._preview_vlc_player.video_set_spu.return_value = 0
        app._preview_subtitle_track = Mock()
        app._preview_subtitle_track.get.side_effect = ["Off", "English"]
        app._preview_subtitle_tracks = {"English": 3}
        app._refresh_video_preview_subtitle_tracks = Mock()

        MediaMixin._toggle_video_preview_subtitles(app)

        app._preview_subtitle_track.set.assert_called_once_with("English")
        app._preview_vlc_player.video_set_spu.assert_called_once_with(3)

    def test_dashboard_preview_settings_explain_when_subtitles_are_unavailable(self):
        app = MediaMixin()
        app.root = Mock()
        app._t = lambda text: text
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.audio_get_track_description.return_value = []
        app._preview_vlc_player.video_get_spu_description.return_value = [
            (-1, "Disable"),
        ]
        app._preview_subtitle_track = Mock()
        app._preview_audio_track = Mock()
        app._preview_playback_rate = Mock()
        app._preview_audio_tracks = {}
        app._preview_subtitle_tracks = {}
        app.preview_player_settings_button = Mock()
        app.preview_player_settings_button.winfo_rootx.return_value = 300
        app.preview_player_settings_button.winfo_rooty.return_value = 120
        menus = [Mock() for _ in range(4)]
        menus[0].winfo_reqheight.return_value = 80

        with patch("app_media.tk.Menu", side_effect=menus):
            MediaMixin._show_video_preview_settings(
                app,
                app.preview_player_settings_button,
            )

        menus[3].add_radiobutton.assert_not_called()
        menus[3].add_command.assert_called_once_with(
            label="No subtitles available",
            state="disabled",
        )

    def test_dashboard_video_preview_shows_a_local_file_while_its_job_is_active(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "active-download.mp4"
            path.write_bytes(b"video")
            app = MediaMixin()
            app.jobs = Mock()
            app.jobs.selection.return_value = ("active-job",)
            app.jobs.item.return_value = ("Downloading", "42%")
            app._local_media_path = None
            app._selected_output_path = Mock(return_value=path)
            app._download_paths = {}
            app._clear_video_preview = Mock()
            app._show_video_preview = Mock()
            app.inspector_status = Mock()
            app.preview_details = Mock()

            MediaMixin._show_selected_thumbnail(app)

        app._show_video_preview.assert_called_once_with(path)
        app.inspector_status.set.assert_called_once_with("Downloading")

    def test_stopping_dashboard_preview_clears_tracks_from_previous_media(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._preview_playback_after = None
        app._preview_vlc_player = None
        app._preview_vlc_instance = None
        app._preview_audio_tracks = {"English": 1}
        app._preview_subtitle_tracks = {"English": 2}
        app._preview_audio_track = Mock()
        app._preview_subtitle_track = Mock()

        MediaMixin._stop_video_preview(app)

        self.assertEqual(app._preview_audio_tracks, {})
        self.assertEqual(app._preview_subtitle_tracks, {})
        app._preview_audio_track.set.assert_called_once_with("")
        app._preview_subtitle_track.set.assert_called_once_with("Off")

    def test_dashboard_preview_poll_updates_timestamps_and_seek_position(self):
        app = MediaMixin()
        app.root = Mock()
        app._preview_playback_after = "old-poll"
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.get_length.return_value = 120_000
        app._preview_vlc_player.get_time.return_value = 30_000
        app._preview_vlc_player.is_seekable.return_value = True
        app.preview_player_current_time = Mock()
        app.preview_player_duration = Mock()
        app.preview_player_position = Mock()
        app.preview_player_position.get.return_value = 25
        app.preview_player_timeline = Mock()
        app.preview_player_timeline.winfo_width.return_value = 110
        app.preview_player_timeline.winfo_height.return_value = 16
        app._preview_seeking = False
        app._preview_audio_refresh_ticks = 0

        MediaMixin._poll_video_preview(app)

        app.preview_player_current_time.set.assert_called_once_with("00:30")
        app.preview_player_duration.set.assert_called_once_with("02:00")
        app.preview_player_position.set.assert_called_once_with(25)
        app.preview_player_timeline.delete.assert_called_once_with("all")
        app.root.after.assert_called_once_with(250, app._poll_video_preview)

    def test_dashboard_preview_timeline_draws_red_gray_and_hover_handle(self):
        app = MediaMixin()
        app.preview_player_timeline = Mock()
        app.preview_player_timeline.winfo_width.return_value = 110
        app.preview_player_timeline.winfo_height.return_value = 16
        app.preview_player_position = Mock()
        app.preview_player_position.get.return_value = 50
        app._preview_timeline_hover = True
        app._preview_seeking = False

        MediaMixin._draw_video_preview_timeline(app)

        self.assertEqual(
            [call.kwargs["fill"] for call in app.preview_player_timeline.create_line.call_args_list],
            ["#777777", "#FF3333"],
        )
        self.assertEqual(
            [call.kwargs["width"] for call in app.preview_player_timeline.create_line.call_args_list],
            [8, 8],
        )
        self.assertEqual(
            app.preview_player_timeline.create_oval.call_args.kwargs["fill"],
            "#FFFFFF",
        )

    def test_preview_fullscreen_opens_its_media_in_the_separate_smart_vlc_window(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._preview_media_path = Path("preview.mp4")
        app._preview_vlc_player = Mock()
        app._preview_vlc_player.is_playing.return_value = True
        app.preview_player_play_button = Mock()
        app._stop_video_preview = Mock()
        app._play_media_in_app = Mock()
        app.jobs = Mock()
        app.jobs.selection.return_value = ()
        app._in_app_player = Mock()
        app._toggle_in_app_fullscreen = Mock()

        MediaMixin._open_preview_fullscreen(app)

        app._preview_vlc_player.pause.assert_called_once_with()
        app.preview_player_play_button.configure.assert_called_once_with(
            text="▶",
        )
        app._stop_video_preview.assert_not_called()
        app._play_media_in_app.assert_called_once_with(Path("preview.mp4"))
        app._toggle_in_app_fullscreen.assert_called_once_with()
        self.assertFalse(app._preserve_video_preview)

    def test_stop_keeps_separate_player_interface_open(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_playback_button = Mock()
        app._in_app_player_status = Mock()
        app._t = lambda text: text
        app._close_in_app_player = Mock()

        MediaMixin._stop_in_app_player(app)

        app._in_app_player.stop.assert_called_once_with()
        app._in_app_playback_button.configure.assert_called_once_with(text="▶")
        app._in_app_player_status.set.assert_called_once_with("Playback stopped")
        app._close_in_app_player.assert_not_called()

    def test_playback_toggle_updates_compact_status(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.is_playing.return_value = True
        app._in_app_playback_button = Mock()
        app._in_app_player_status = Mock()
        app._t = lambda text: text

        MediaMixin._toggle_in_app_playback(app)

        app._in_app_player.pause.assert_called_once_with()
        app._in_app_playback_button.configure.assert_called_once_with(text="▶")
        app._in_app_player_status.set.assert_called_once_with("Playback paused")

    def test_playback_rate_selection_applies_the_requested_vlc_rate(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.set_rate.return_value = 0
        app._in_app_playback_rate = Mock()
        app._in_app_playback_rate.get.return_value = "1.5x"

        MediaMixin._set_in_app_playback_rate(app)

        app._in_app_player.set_rate.assert_called_once_with(1.5)

    def test_unavailable_playback_rate_is_reported_and_selection_is_restored(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.set_rate.return_value = -1
        app._in_app_player.get_rate.return_value = 1.0
        app._in_app_playback_rate = Mock()
        app._in_app_playback_rate.get.return_value = "2.0x"
        app._in_app_player_window = Mock()
        app._t = lambda text: text
        with patch("app_media.messagebox.showerror") as show_error:
            MediaMixin._set_in_app_playback_rate(app)

        app._in_app_player.set_rate.assert_called_once_with(2.0)
        app._in_app_playback_rate.set.assert_called_once_with("1.0x")
        show_error.assert_called_once_with(
            "Playback speed unavailable",
            "VLC could not change the playback speed.",
            parent=app._in_app_player_window,
        )

    def test_invalid_playback_rate_is_reported_without_calling_vlc(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_playback_rate = Mock()
        app._in_app_playback_rate.get.return_value = "2.5x"
        app._in_app_player_window = Mock()
        app._t = lambda text: text
        with patch("app_media.messagebox.showerror") as show_error:
            MediaMixin._set_in_app_playback_rate(app)

        app._in_app_player.set_rate.assert_not_called()
        show_error.assert_called_once_with(
            "Invalid playback speed",
            "Choose one of the available playback speeds.",
            parent=app._in_app_player_window,
        )

    def test_playback_title_is_shortened_without_losing_full_filename(self):
        title = "a" * 100 + ".mp4"

        compact_title = MediaMixin._compact_in_app_title(title)

        self.assertEqual(len(compact_title), 72)
        self.assertTrue(compact_title.endswith("..."))
        self.assertEqual(title, "a" * 100 + ".mp4")

    def test_finished_playback_keeps_separate_player_interface_open(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.get_state.return_value = 1
        app._in_app_player.get_length.return_value = 0
        app._in_app_player.get_time.return_value = 0
        app._in_app_player.is_seekable.return_value = False
        app._in_app_vlc = SimpleNamespace(
            State=SimpleNamespace(Ended=1, Error=2)
        )
        app._in_app_player_window = Mock()
        app._in_app_audio_refresh_ticks = 0
        app._in_app_playback_button = Mock()
        app._in_app_player_status = Mock()
        app._in_app_current_time = Mock()
        app._in_app_duration = Mock()
        app._in_app_position_var = Mock()
        app._close_in_app_player = Mock()
        app._t = lambda text: text

        MediaMixin._poll_in_app_playback(app)

        app._in_app_playback_button.configure.assert_called_once_with(text="▶")
        app._in_app_player_status.set.assert_called_once_with("Playback finished")
        app._close_in_app_player.assert_not_called()

    def test_close_separate_player_without_destroying_main_app(self):
        app = MediaMixin()
        app.root = Mock()
        app.preview_image_label = Mock()
        player_window = Mock()
        controls_window = Mock()
        top_controls_window = Mock()
        app._in_app_player_window = player_window
        app._in_app_controls_overlay_window = controls_window
        app._in_app_top_controls_overlay_window = top_controls_window
        player = Mock()
        app._in_app_player = player
        app._in_app_vlc_instance = Mock()
        app._in_app_playback_after = None
        app._in_app_fullscreen = True
        app._in_app_fullscreen_button = Mock()
        app._t = lambda text: text

        with patch("app_media.sys.platform", "win32"):
            MediaMixin._close_in_app_player(app)

        player_window.attributes.assert_called_once_with("-fullscreen", False)
        player_window.destroy.assert_called_once_with()
        app.root.attributes.assert_not_called()
        app.root.geometry.assert_not_called()
        app.root.destroy.assert_not_called()
        player.release.assert_called_once_with()
        controls_window.destroy.assert_called_once_with()
        top_controls_window.destroy.assert_called_once_with()
        self.assertIsNone(app._in_app_top_controls_overlay_window)
        self.assertIsNone(app._in_app_player_window)

    def test_volume_control_updates_vlc_and_displays_rounded_percentage(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_volume_label = Mock()

        MediaMixin._set_in_app_volume(app, "63.7")

        app._in_app_player.audio_set_volume.assert_called_once_with(64)
        app._in_app_volume_label.set.assert_called_once_with("64%")

    def test_audio_track_menu_lists_tracks_and_selects_chosen_track(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.audio_get_track_description.return_value = [
            (1, "English"),
            (2, b"Urdu"),
        ]
        app._in_app_player.audio_get_track.return_value = 2
        app._in_app_audio_track = Mock()
        app._in_app_audio_tracks = {}
        app._t = lambda text: text

        MediaMixin._refresh_in_app_audio_tracks(app)

        self.assertEqual(app._in_app_audio_tracks, {"English": 1, "Urdu": 2})
        app._in_app_audio_track.set.assert_called_once_with("Urdu")
        app._in_app_audio_track.get.return_value = "English"
        app._in_app_player.audio_set_track.return_value = 0
        MediaMixin._select_in_app_audio_track(app)
        app._in_app_player.audio_set_track.assert_called_once_with(1)

    def test_audio_track_menu_handles_missing_vlc_tracks(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.audio_get_track_description.return_value = None
        app._in_app_audio_track = Mock()
        app._in_app_audio_tracks = {}
        app._t = lambda text: text

        MediaMixin._refresh_in_app_audio_tracks(app)

        app._in_app_audio_track.set.assert_called_once_with("")

    def test_settings_menu_contains_speed_audio_and_subtitle_tracks(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._in_app_player_window = Mock()
        app._in_app_player = Mock()
        app._in_app_player.audio_get_track_description.return_value = [
            (1, "English"),
            (2, "Urdu"),
        ]
        app._in_app_player.audio_get_track.return_value = 1
        app._in_app_player.video_get_spu_description.return_value = [
            (-1, "Disable"),
            (3, "English"),
        ]
        app._in_app_player.video_get_spu.return_value = -1
        app._in_app_audio_track = Mock()
        app._in_app_playback_rate = Mock()
        app._in_app_subtitle_track = Mock()
        app._in_app_cc_button = Mock()
        app._begin_in_app_control_interaction = Mock()
        app._end_in_app_control_interaction = Mock()
        button = Mock()
        button.winfo_rootx.return_value = 300
        button.winfo_rooty.return_value = 120
        menus = [Mock() for _ in range(4)]
        menus[0].winfo_reqheight.return_value = 90

        with patch("app_media.tk.Menu", side_effect=menus) as menu_factory:
            MediaMixin._show_in_app_settings_menu(app, button)

        self.assertEqual(menu_factory.call_count, 4)
        self.assertEqual(
            [call.kwargs["label"] for call in menus[1].add_radiobutton.call_args_list],
            list(app_media._IN_APP_PLAYBACK_RATES),
        )
        self.assertEqual(
            app_media._IN_APP_PLAYBACK_RATES,
            ("0.5x", "1.0x", "1.5x", "2.0x"),
        )
        self.assertEqual(
            [
                call.kwargs["label"]
                for call in menus[2].add_radiobutton.call_args_list
            ],
            ["English", "Urdu"],
        )
        self.assertEqual(
            [
                call.kwargs["label"]
                for call in menus[3].add_radiobutton.call_args_list
            ],
            ["Off", "English"],
        )
        self.assertEqual(
            [call.kwargs["label"] for call in menus[0].add_cascade.call_args_list],
            ["Playback speed", "Audio track", "Subtitles"],
        )
        menus[0].tk_popup.assert_called_once_with(300, 30)
        menus[0].grab_release.assert_called_once_with()
        menus[0].destroy.assert_called_once_with()
        app._end_in_app_control_interaction.assert_called_once_with()

    def test_subtitle_button_is_only_shown_when_tracks_are_available(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._in_app_player = Mock()
        app._in_app_player.video_get_spu_description.return_value = [
            (-1, "Disable"),
            (4, "English"),
        ]
        app._in_app_player.video_get_spu.return_value = 4
        app._in_app_subtitle_track = Mock()
        app._in_app_cc_button = Mock()

        MediaMixin._refresh_in_app_subtitle_tracks(app)

        self.assertEqual(app._in_app_subtitle_tracks, {"English": 4})
        app._in_app_subtitle_track.set.assert_called_once_with("English")
        app._in_app_cc_button.grid.assert_called_once_with()
        app._in_app_cc_button.grid_remove.assert_not_called()
        app._in_app_cc_button.configure.assert_called_once_with(
            foreground="#FF3333"
        )

        app._in_app_player.video_get_spu_description.return_value = [
            (-1, "Disable"),
        ]
        MediaMixin._refresh_in_app_subtitle_tracks(app)
        app._in_app_subtitle_track.set.assert_called_with("Off")
        app._in_app_cc_button.grid_remove.assert_called_once_with()

    def test_cc_button_toggles_selected_subtitle_track(self):
        app = MediaMixin()
        app._t = lambda text: text
        app._in_app_player_window = Mock()
        app._in_app_player = Mock()
        app._in_app_player.video_get_spu.side_effect = [-1, 1, 1, 1]
        app._in_app_player.video_get_spu_description.return_value = [
            (1, "English"),
        ]
        app._in_app_player.video_set_spu.return_value = 0
        app._in_app_subtitle_track = Mock()
        app._in_app_subtitle_track.get.side_effect = [
            "Off",
            "English",
            "English",
        ]
        app._in_app_subtitle_tracks = {"English": 1}
        app._in_app_cc_button = Mock()
        app._show_in_app_controls = Mock()

        MediaMixin._toggle_in_app_subtitles(app)

        app._in_app_player.video_set_spu.assert_called_once_with(1)
        app._in_app_subtitle_track.set.assert_has_calls(
            [unittest.mock.call("English"), unittest.mock.call("English")]
        )
        app._in_app_cc_button.configure.assert_called_with(
            foreground="#FF3333"
        )

        MediaMixin._toggle_in_app_subtitles(app)

        app._in_app_player.video_set_spu.assert_has_calls(
            [unittest.mock.call(1), unittest.mock.call(-1)]
        )
        app._in_app_subtitle_track.set.assert_called_with("Off")

    def test_fullscreen_expands_player_and_refreshes_video_target_after_resize(self):
        app = MediaMixin()
        app.root = Mock()
        player_window = Mock()
        app._in_app_player_window = player_window
        app._in_app_player = Mock()
        app._in_app_player.is_playing.return_value = True
        app._in_app_video_surface = Mock()
        app._in_app_video_surface.winfo_id.return_value = 101
        app._in_app_fullscreen = False
        app._in_app_fullscreen_button = Mock()
        app._t = lambda text: text

        self.assertEqual(MediaMixin._toggle_in_app_fullscreen(app), "break")
        player_window.attributes.assert_called_once_with("-fullscreen", True)
        player_window.after.assert_called_once_with(
            150, app._refresh_in_app_video_target
        )
        app._in_app_player.set_hwnd.assert_not_called()
        app.root.attributes.assert_not_called()
        app.root.geometry.assert_not_called()
        self.assertTrue(app._in_app_fullscreen)
        app._in_app_fullscreen_button.configure.assert_called_once_with(
            text="⛶"
        )

        self.assertEqual(MediaMixin._exit_in_app_fullscreen(app), "break")
        player_window.attributes.assert_has_calls(
            [unittest.mock.call("-fullscreen", True), unittest.mock.call("-fullscreen", False)]
        )
        self.assertEqual(player_window.after.call_count, 2)
        app._in_app_player.set_hwnd.assert_not_called()
        app.root.attributes.assert_not_called()
        app.root.geometry.assert_not_called()
        self.assertFalse(app._in_app_fullscreen)
        app._in_app_fullscreen_button.configure.assert_called_with(text="⛶")

    def test_fullscreen_header_is_positioned_at_top_and_hidden_in_windowed_mode(self):
        app = MediaMixin()
        app._in_app_controls_visible = True
        app._in_app_controls_overlay = Mock()
        app._in_app_controls_overlay.winfo_reqheight.return_value = 40
        app._in_app_controls_overlay_window = Mock()
        app._in_app_top_controls_overlay = Mock()
        app._in_app_top_controls_overlay.winfo_reqheight.return_value = 48
        app._in_app_top_controls_overlay_window = Mock()
        app._in_app_video_surface = Mock()
        app._in_app_video_surface.winfo_width.return_value = 1120
        app._in_app_video_surface.winfo_height.return_value = 700
        app._in_app_video_surface.winfo_rootx.return_value = 15
        app._in_app_video_surface.winfo_rooty.return_value = 25
        app._in_app_fullscreen = True

        MediaMixin._raise_in_app_controls_overlay(app)

        app._in_app_top_controls_overlay_window.geometry.assert_called_once_with(
            "1120x48+15+25"
        )
        app._in_app_top_controls_overlay_window.lift.assert_called_once_with()
        app._in_app_top_controls_overlay_window.withdraw.assert_not_called()

        app._in_app_fullscreen = False
        MediaMixin._raise_in_app_controls_overlay(app)
        app._in_app_top_controls_overlay_window.withdraw.assert_called_once_with()

    def test_video_target_refresh_uses_the_resized_player_surface(self):
        app = MediaMixin()
        app._in_app_player_window = Mock()
        app._in_app_player_window.winfo_exists.return_value = True
        app._in_app_video_surface = Mock()
        app._in_app_video_surface.winfo_exists.return_value = True
        app._in_app_player = Mock()
        app._set_in_app_video_target = Mock()

        MediaMixin._refresh_in_app_video_target(app)

        app._in_app_player_window.update_idletasks.assert_called_once_with()
        app._set_in_app_video_target.assert_called_once_with(
            app._in_app_video_surface
        )

    def test_icon_control_hint_is_restored_to_current_player_status(self):
        app = MediaMixin()
        app._in_app_player_status = Mock()
        app._in_app_player_status_text = "Playback paused"
        widget = Mock()

        MediaMixin._bind_in_app_control_hint(app, widget, "Pause")
        MediaMixin._show_in_app_control_hint(app, "Pause")
        MediaMixin._restore_in_app_player_status(app)

        self.assertEqual(
            [call.args[0] for call in widget.bind.call_args_list],
            ["<Enter>", "<Leave>", "<FocusIn>", "<FocusOut>"],
        )
        app._in_app_player_status.set.assert_has_calls(
            [unittest.mock.call("Pause"), unittest.mock.call("Playback paused")]
        )

    def test_player_time_format_supports_long_media(self):
        self.assertEqual(MediaMixin._format_in_app_time(65_000), "01:05")
        self.assertEqual(MediaMixin._format_in_app_time(3_661_000), "1:01:01")

    def test_playback_poll_updates_elapsed_time_and_seek_position(self):
        app = MediaMixin()
        app.root = Mock()
        app._in_app_player = Mock()
        app._in_app_player.get_state.return_value = 0
        app._in_app_player.get_length.return_value = 120_000
        app._in_app_player.get_time.return_value = 30_000
        app._in_app_player.is_seekable.return_value = True
        app._in_app_vlc = SimpleNamespace(State=SimpleNamespace(Ended=1, Error=2))
        app._in_app_player_window = Mock()
        app._in_app_audio_refresh_ticks = 0
        app._in_app_audio_track = Mock()
        app._in_app_audio_tracks = {}
        app._in_app_audio_tracks_loaded = True
        app._in_app_current_time = Mock()
        app._in_app_duration = Mock()
        app._in_app_position_var = Mock()
        app._in_app_seeking = False

        MediaMixin._poll_in_app_playback(app)

        app._in_app_current_time.set.assert_called_once_with("00:30")
        app._in_app_duration.set.assert_called_once_with("02:00")
        app._in_app_position_var.set.assert_called_once_with(25)
        self.assertEqual(app._in_app_duration_ms, 120_000)
        app.root.after.assert_called_once_with(250, app._poll_in_app_playback)

    def test_seek_moves_vlc_to_selected_position(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.is_playing.return_value = False
        app._in_app_player.get_length.return_value = 200_000
        app._in_app_player.is_seekable.return_value = True
        app._in_app_position_var = Mock()
        app._in_app_position_var.get.return_value = 25
        app._in_app_seeking = True
        app._in_app_controls_overlay = Mock()
        app.root = Mock()

        MediaMixin._seek_in_app_player(app)

        app._in_app_player.set_time.assert_called_once_with(50_000)
        self.assertFalse(app._in_app_seeking)

    def test_canvas_timeline_draws_red_played_progress(self):
        app = MediaMixin()
        app._in_app_timeline = Mock()
        app._in_app_timeline.winfo_width.return_value = 110
        app._in_app_timeline.winfo_height.return_value = 20
        app._in_app_position_var = Mock()
        app._in_app_position_var.get.return_value = 50

        MediaMixin._draw_in_app_timeline(app)

        app._in_app_timeline.delete.assert_called_once_with("all")
        self.assertEqual(app._in_app_timeline.create_line.call_count, 2)
        self.assertEqual(
            [call.kwargs["width"] for call in app._in_app_timeline.create_line.call_args_list],
            [4, 4],
        )
        self.assertEqual(
            app._in_app_timeline.create_line.call_args_list[1].kwargs["fill"],
            "#FF3333",
        )
        app._in_app_timeline.create_oval.assert_not_called()

    def test_canvas_timeline_hover_shows_white_handle_and_thickens_track(self):
        app = MediaMixin()
        app._in_app_timeline = Mock()
        app._in_app_timeline.winfo_width.return_value = 110
        app._in_app_timeline.winfo_height.return_value = 20
        app._in_app_position_var = Mock()
        app._in_app_position_var.get.return_value = 50
        app._in_app_timeline_hover = True
        app._in_app_seeking = False

        MediaMixin._draw_in_app_timeline(app)

        self.assertEqual(
            [call.kwargs["width"] for call in app._in_app_timeline.create_line.call_args_list],
            [8, 8],
        )
        self.assertEqual(
            app._in_app_timeline.create_oval.call_args.kwargs["fill"],
            "#FFFFFF",
        )
        self.assertEqual(
            app._in_app_timeline.create_oval.call_args.kwargs["outline"],
            "#FFFFFF",
        )

    def test_canvas_timeline_drag_seeks_and_updates_progress(self):
        app = MediaMixin()
        app._in_app_player = Mock()
        app._in_app_player.is_seekable.return_value = True
        app._in_app_player.get_length.return_value = 200_000
        app._in_app_timeline = Mock()
        app._in_app_timeline.winfo_width.return_value = 110
        app._in_app_timeline.winfo_height.return_value = 20
        app._in_app_position_var = Mock()
        position = {"value": 0}
        app._in_app_position_var.get.side_effect = lambda: position["value"]
        app._in_app_position_var.set.side_effect = (
            lambda value: position.__setitem__("value", value)
        )
        app._in_app_duration_ms = 200_000
        app._in_app_seeking = False
        app._in_app_controls_overlay = Mock()
        app._in_app_controls_visible = True
        app._in_app_current_time = Mock()
        app.root = Mock()

        MediaMixin._begin_in_app_seek(app, SimpleNamespace(x=55))
        MediaMixin._update_in_app_seek(app, SimpleNamespace(x=80))
        MediaMixin._seek_in_app_player(app, SimpleNamespace(x=55))

        app._in_app_position_var.set.assert_any_call(50)
        app._in_app_current_time.set.assert_any_call("01:40")
        app._in_app_player.set_time.assert_called_once_with(100_000)
        self.assertFalse(app._in_app_seeking)

    def test_controls_hide_after_five_seconds_only_during_playback(self):
        app = MediaMixin()
        app.root = Mock()
        app._in_app_player = Mock()
        app._in_app_player.is_playing.return_value = True
        app._in_app_seeking = False
        app._in_app_control_interaction = False
        app._in_app_controls_after = None

        MediaMixin._schedule_in_app_controls_hide(app)

        app.root.after.assert_called_once_with(5000, app._hide_in_app_controls)

        app._in_app_timeline_hover = True
        app.root.after.reset_mock()
        MediaMixin._schedule_in_app_controls_hide(app)
        app.root.after.assert_not_called()

        app._in_app_timeline_hover = False
        app._in_app_player.is_playing.return_value = False
        app.root.after.reset_mock()
        MediaMixin._schedule_in_app_controls_hide(app)
        app.root.after.assert_not_called()

    def test_hidden_controls_remain_visible_when_playback_is_paused(self):
        app = MediaMixin()
        app.root = Mock()
        app._in_app_player = Mock()
        app._in_app_player.is_playing.return_value = False
        app._in_app_controls_overlay = Mock()
        app._in_app_controls_overlay.winfo_reqheight.return_value = 40
        app._in_app_controls_overlay_window = Mock()
        app._in_app_video_surface = Mock()
        app._in_app_video_surface.winfo_width.return_value = 1120
        app._in_app_video_surface.winfo_height.return_value = 700
        app._in_app_video_surface.winfo_rootx.return_value = 0
        app._in_app_video_surface.winfo_rooty.return_value = 0
        app._in_app_controls_after = None
        app._in_app_controls_fade_after = None
        app._in_app_controls_opacity = 0.0
        app._in_app_controls_visible = False

        MediaMixin._hide_in_app_controls(app)

        app._in_app_controls_overlay_window.deiconify.assert_called_once_with()
        app._in_app_controls_overlay_window.lift.assert_called_once_with()
        app._in_app_controls_overlay_window.attributes.assert_any_call(
            "-alpha", 0.0
        )
        app.root.after.assert_called_once_with(
            40,
            app._advance_in_app_controls_fade,
        )
        self.assertTrue(app._in_app_controls_visible)

    def test_playback_controls_fade_out_after_inactivity(self):
        app = MediaMixin()
        app.root = Mock()
        app._in_app_player = Mock()
        app._in_app_player.is_playing.return_value = True
        app._in_app_controls_overlay_window = Mock()
        app._in_app_top_controls_overlay_window = Mock()
        app._in_app_controls_visible = True
        app._in_app_controls_opacity = 0.92
        app._in_app_controls_fade_after = None
        app._in_app_seeking = False
        app._in_app_control_interaction = False
        app._in_app_timeline_hover = False

        MediaMixin._hide_in_app_controls(app)

        self.assertTrue(app._in_app_controls_visible)
        alpha_call = app._in_app_controls_overlay_window.attributes.call_args
        self.assertEqual(alpha_call.args[0], "-alpha")
        self.assertAlmostEqual(alpha_call.args[1], 0.69)
        app.root.after.assert_called_once_with(
            40,
            app._advance_in_app_controls_fade,
        )

        for _ in range(3):
            MediaMixin._advance_in_app_controls_fade(app)

        app._in_app_controls_overlay_window.withdraw.assert_called_once_with()
        app._in_app_top_controls_overlay_window.withdraw.assert_called_once_with()
        self.assertFalse(app._in_app_controls_visible)

    def test_player_help_explains_separate_fullscreen_and_controls(self):
        app = MediaMixin()
        app.root = Mock()
        app._t = lambda text: text

        with patch("app_media.messagebox.showinfo") as show_info:
            MediaMixin._show_in_app_player_help(app)

        title, help_text = show_info.call_args.args
        self.assertEqual(title, "Media player help")
        self.assertIn("separate Smart VLC window", help_text)
        self.assertIn("timeline to seek", help_text)
        self.assertIn("without changing the main app window", help_text)
        self.assertIn("F11", help_text)
        self.assertIn("Escape", help_text)
        self.assertIn("change volume", help_text)
        self.assertIn("playback speed", help_text)
        self.assertIn("audio tracks", help_text)
        self.assertIn("subtitles", help_text)
        self.assertIn("Settings", help_text)
        self.assertIn("Close player", help_text)
        self.assertEqual(show_info.call_args.kwargs["parent"], app.root)

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
