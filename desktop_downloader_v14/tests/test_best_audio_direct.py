"""'Best audio' on a plain video file must save sound only (no re-encode), never lose the download."""
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import download_engine
from download_engine import _convert_to_mp3_if_needed

FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def kinds(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return sorted(line.split(",")[1] for line in out.split() if "," in line), out


def make(path, video=True, acodec="aac"):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    if video:
        cmd += ["-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1:r=10", "-shortest"]
    cmd += ["-c:a", acodec] + (["-c:v", "libx264"] if video else []) + [str(path)]
    subprocess.run(cmd, check=True)


@unittest.skipUnless(FFMPEG, "ffmpeg/ffprobe not installed")
class BestAudioDirectTests(unittest.TestCase):
    def test_video_becomes_audio_only_file_and_original_is_removed(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "clip.mp4"; make(src)
            result = _convert_to_mp3_if_needed(src, "best audio")
            self.assertEqual(result.suffix, ".m4a")
            self.assertTrue(result.is_file() and not src.exists())
            self.assertEqual(kinds(result)[0], ["audio"])

    def test_audio_is_copied_not_re_encoded(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "clip.mp4"; make(src, acodec="mp3")
            result = _convert_to_mp3_if_needed(src, "best audio")
            self.assertEqual(result.suffix, ".mp3")
            self.assertIn("mp3", kinds(result)[1])

    def test_audio_file_is_left_alone(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "song.m4a"; make(src, video=False)
            before = src.read_bytes()
            self.assertEqual(_convert_to_mp3_if_needed(src, "best audio"), src)
            self.assertEqual(src.read_bytes(), before)

    def test_existing_name_is_not_overwritten(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "clip.mp4"; make(src)
            (Path(d) / "clip.m4a").write_bytes(b"mine")
            result = _convert_to_mp3_if_needed(src, "best audio")
            self.assertEqual((Path(d) / "clip.m4a").read_bytes(), b"mine")
            self.assertNotEqual(result.name, "clip.m4a")
            self.assertEqual(kinds(result)[0], ["audio"])

    def test_without_ffmpeg_the_video_is_kept(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "clip.mp4"; make(src)
            with patch.object(download_engine, "_ffmpeg_directory", return_value=None):
                self.assertEqual(_convert_to_mp3_if_needed(src, "best audio"), src)
            self.assertTrue(src.is_file())

    def test_broken_file_is_kept(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "bad.mp4"; src.write_bytes(b"not a video")
            self.assertEqual(_convert_to_mp3_if_needed(src, "best audio"), src)
            self.assertTrue(src.is_file())

    def test_video_modes_do_not_touch_the_file(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "clip.mp4"; make(src)
            self.assertEqual(_convert_to_mp3_if_needed(src, "video"), src)


if __name__ == "__main__":
    unittest.main()
