import unittest

from playlist_selection import normalize_playlist_items


class PlaylistSelectionTests(unittest.TestCase):
    def test_blank_means_all_items(self):
        self.assertEqual(normalize_playlist_items(" "), "")

    def test_normalizes_ranges_and_spaces(self):
        self.assertEqual(normalize_playlist_items(" 1, 3 - 5,8 "), "1,3-5,8")

    def test_rejects_zero_and_descending_ranges(self):
        for value in ("0", "5-2", "1,,2", "x"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_playlist_items(value)

    def test_limits_selection_size(self):
        with self.assertRaises(ValueError):
            normalize_playlist_items("1-10001")


if __name__ == "__main__":
    unittest.main()
