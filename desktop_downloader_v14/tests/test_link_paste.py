import unittest

from link_compatibility import (
    analyze_link,
    format_multi_link_summary,
    normalize_link_text,
    split_pasted_links,
)


class NormalizeLinkTests(unittest.TestCase):
    def test_adds_https_to_addresses_pasted_without_a_scheme(self):
        self.assertEqual(
            normalize_link_text("www.youtube.com/watch?v=jNQXAC9IVRw"),
            "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        )
        self.assertEqual(normalize_link_text("youtu.be/jNQXAC9IVRw"), "https://youtu.be/jNQXAC9IVRw")
        self.assertEqual(normalize_link_text("  vimeo.com/76979871\n"), "https://vimeo.com/76979871")

    def test_leaves_real_links_and_other_text_alone(self):
        for text in (
            "https://example.org/a.mp4",
            "http://example.org",
            "magnet:?xt=urn:btih:abc",
            "clip.mp4",
            "my notes",
            "C:\\Videos\\a.mp4",
            "",
        ):
            with self.subTest(text=text):
                self.assertEqual(normalize_link_text(text), text.strip())

    def test_checker_accepts_a_link_pasted_without_scheme(self):
        result = analyze_link("youtu.be/jNQXAC9IVRw")
        self.assertTrue(result.valid)


class SplitPastedLinksTests(unittest.TestCase):
    def test_splits_links_separated_by_spaces_and_new_lines(self):
        text = "https://youtu.be/AAAAAAAAAAA\nhttps://youtu.be/BBBBBBBBBBB  vimeo.com/123\r\n"
        self.assertEqual(
            split_pasted_links(text),
            [
                "https://youtu.be/AAAAAAAAAAA",
                "https://youtu.be/BBBBBBBBBBB",
                "https://vimeo.com/123",
            ],
        )

    def test_single_link_or_ordinary_text_is_not_split(self):
        self.assertEqual(split_pasted_links("https://youtu.be/AAAAAAAAAAA"), [])
        self.assertEqual(split_pasted_links("watch this https://youtu.be/AAAAAAAAAAA"), [])
        self.assertEqual(split_pasted_links(""), [])

    def test_a_link_containing_a_comma_is_kept_whole(self):
        self.assertEqual(
            split_pasted_links("https://a.example/x?ids=1,2 https://b.example/y"),
            ["https://a.example/x?ids=1,2", "https://b.example/y"],
        )


class MultiLinkCheckerTests(unittest.TestCase):
    def test_checker_no_longer_calls_several_links_one_valid_generic_link(self):
        result = analyze_link("https://youtu.be/AAAAAAAAAAA https://youtu.be/BBBBBBBBBBB")
        self.assertFalse(result.valid)
        self.assertIn("more than one link", result.message)

    def test_summary_lists_each_link(self):
        links = ["https://youtu.be/AAAAAAAAAAA", "https://vimeo.com/76979871", "https://example.org/a.mp4"]
        summary = format_multi_link_summary(links)
        self.assertIn("3 links detected", summary)
        self.assertIn("1. ", summary)
        self.assertIn("3. ", summary)

    def test_summary_is_capped_for_very_long_pastes(self):
        links = [f"https://example.org/{i}.mp4" for i in range(30)]
        summary = format_multi_link_summary(links, limit=5)
        self.assertIn("30 links detected", summary)
        self.assertIn("and 25 more", summary)


if __name__ == "__main__":
    unittest.main()
