from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from live_check import _resolve_case_insensitive_output


class LiveCheckFilenameCaseTests(unittest.TestCase):
    def test_resolves_actual_file_when_extractor_changes_filename_case(self) -> None:
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            actual = directory / "e2e tests [clip].mp4"
            expected = directory / "E2E tests [clip].mp4"
            actual.write_bytes(b"downloaded media")

            self.assertEqual(_resolve_case_insensitive_output(expected), actual)

    def test_keeps_expected_path_when_no_case_insensitive_match_exists(self) -> None:
        with TemporaryDirectory() as temporary:
            expected = Path(temporary) / "missing.mp4"
            self.assertEqual(_resolve_case_insensitive_output(expected), expected)

    def test_keeps_expected_path_when_multiple_case_matches_are_ambiguous(self) -> None:
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = directory / "clip.mp4"
            (directory / "CLIP.mp4").write_bytes(b"one")
            (directory / "Clip.mp4").write_bytes(b"two")

            self.assertEqual(_resolve_case_insensitive_output(expected), expected)


if __name__ == "__main__":
    unittest.main()
