import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yt_dlp
from yt_dlp.extractor.common import InfoExtractor

import download_engine
from download_engine import RetryPolicy


class _NoFormatsExtractor(InfoExtractor):
    """A site whose page loads but offers nothing to download.

    This is what YouTube returns for a "Sign in to confirm you're not a bot"
    response: a video with a title but no formats.
    """

    _VALID_URL = r"https?://nofmt\.test/(?P<id>\w+)"
    calls = 0

    def _real_extract(self, url):
        type(self).calls += 1
        return {"id": self._match_id(url), "title": "Blocked video"}


_REAL_YOUTUBE_DL = yt_dlp.YoutubeDL  # the patch below replaces yt_dlp.YoutubeDL


def _youtube_dl_with_fake_site(options):
    downloader = _REAL_YOUTUBE_DL(options)
    downloader.add_info_extractor(_NoFormatsExtractor())
    # yt-dlp tries extractors in order and the generic one would claim this URL first.
    key = _NoFormatsExtractor.ie_key()
    downloader._ies = {key: downloader._ies[key], **{k: v for k, v in downloader._ies.items() if k != key}}
    return downloader


class NoEndlessExtractionTests(unittest.TestCase):
    def test_a_page_without_formats_fails_once_instead_of_looping_forever(self):
        _NoFormatsExtractor.calls = 0
        outcome = {}

        def run():
            with TemporaryDirectory() as folder:
                try:
                    download_engine.download_url(
                        "https://nofmt.test/abc123",
                        Path(folder),
                        "auto",
                        "video",
                        "best",
                        "single video",
                        threading.Event(),
                        lambda *_args: None,
                        retry_policy=RetryPolicy(2, 0.0, 0.0),
                    )
                    outcome["error"] = None
                except BaseException as error:  # noqa: BLE001
                    outcome["error"] = error

        with patch.object(download_engine.yt_dlp, "YoutubeDL", _youtube_dl_with_fake_site):
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            worker.join(timeout=10)
            finished = not worker.is_alive()
            calls_after_wait = _NoFormatsExtractor.calls
            time.sleep(0.05)

        self.assertTrue(
            finished,
            f"download kept re-requesting the page without end ({calls_after_wait} requests in 10 s)",
        )
        self.assertIsNotNone(outcome.get("error"), "a page with no formats must be reported as an error")
        self.assertLessEqual(_NoFormatsExtractor.calls, 3)

    def test_the_wait_for_video_loop_is_not_enabled(self):
        # yt-dlp's wait_for_video re-extracts without any delay or cancel check when
        # a page has no formats. It must stay off; yt-dlp then reports the real reason.
        source = Path(download_engine.__file__).read_text(encoding="utf-8")
        self.assertFalse('"wait_for_video"' in source, "wait_for_video is enabled again")


if __name__ == "__main__":
    unittest.main()
