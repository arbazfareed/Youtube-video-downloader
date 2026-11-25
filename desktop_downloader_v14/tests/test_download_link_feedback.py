import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app_downloads import DownloadsMixin
from app_ui import UiMixin


class DownloadLinkFeedbackTests(unittest.TestCase):
    def test_full_link_preview_preserves_entire_manual_or_clipboard_url(self):
        url = "https://vt.tiktok.com/ZS9PxxBmhBvCk-9Ho0z/"
        app = SimpleNamespace(
            url_text=SimpleNamespace(get=Mock(return_value=url)),
            link_preview_var=SimpleNamespace(set=Mock()),
            _t=lambda text: text,
        )

        UiMixin._update_link_preview(app)

        app.link_preview_var.set.assert_called_once_with(f"Link preview: {url}")

    def test_compatibility_hint_is_inline_not_a_modal_or_download_failure(self):
        url = "https://vt.tiktok.com/ZS9PxxBmhBvCk-9Ho0z/"
        app = SimpleNamespace(
            url_entry=SimpleNamespace(get=Mock(return_value=url)),
            link_feedback_var=SimpleNamespace(set=Mock()),
            _t=lambda text: text,
            root=Mock(),
            _set_link_feedback=lambda message: app.link_feedback_var.set(message),
        )
        result = SimpleNamespace(valid=True)
        with patch("link_compatibility.analyze_link", return_value=result), \
             patch("link_compatibility.format_analysis", return_value="yt-dlp recognizes TikTok"), \
             patch("app_downloads.messagebox.showinfo") as show_info, \
             patch("app_downloads.messagebox.showwarning") as show_warning:
            DownloadsMixin.inspect_link(app)

        show_info.assert_not_called()
        show_warning.assert_not_called()
        feedback = app.link_feedback_var.set.call_args.args[0]
        self.assertIn("not a download failure", feedback)
        self.assertIn("does not start, stop, or block downloads", feedback)
        self.assertIn("Add download", feedback)

    def test_invalid_link_check_is_inline_and_does_not_interrupt_other_jobs(self):
        app = SimpleNamespace(
            url_entry=SimpleNamespace(get=Mock(return_value="bad link")),
            link_feedback_var=SimpleNamespace(set=Mock()),
            _t=lambda text: text,
            root=Mock(),
            _set_link_feedback=lambda message: app.link_feedback_var.set(message),
        )
        result = SimpleNamespace(valid=False, message="Malformed URL")
        with patch("link_compatibility.analyze_link", return_value=result), \
             patch("app_downloads.messagebox.showwarning") as show_warning:
            DownloadsMixin.inspect_link(app)

        show_warning.assert_not_called()
        self.assertIn("does not change existing downloads", app.link_feedback_var.set.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
