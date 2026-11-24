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

    def test_merges_overlapping_ranges_without_duplicate_positions(self):
        self.assertEqual(normalize_playlist_items("1-3,3-5,2,5"), "1-5")

    def test_merges_adjacent_ranges_and_sorts_positions(self):
        self.assertEqual(normalize_playlist_items("8-9,1,3-4,2"), "1-4,8-9")

    def test_limit_applies_to_unique_selected_positions(self):
        # Repeated positions should not inflate the selection count.
        self.assertEqual(normalize_playlist_items("1-6000,5000-10000"), "1-10000")



if __name__ == "__main__":
    unittest.main()
