from __future__ import annotations

import unittest

from history_store import normalize_url


class HistoryUrlNormalizationTests(unittest.TestCase):
    def test_normalizes_ipv6_without_removing_required_brackets(self):
        self.assertEqual(
            normalize_url("HTTP://[2001:DB8::1]:80/video#chapter"),
            "http://[2001:db8::1]/video",
        )

    def test_preserves_case_sensitive_url_credentials(self):
        first = normalize_url("https://User:Pass@EXAMPLE.com:443/video#part")
        second = normalize_url("https://user:pass@example.com/video")
        self.assertEqual(first, "https://User:Pass@example.com/video")
        self.assertNotEqual(first, second)

    def test_default_ports_and_fragments_are_still_normalized(self):
        self.assertEqual(
            normalize_url("HTTPS://Example.com:443/video#part"),
            "https://example.com/video",
        )


if __name__ == "__main__":
    unittest.main()

    def test_normalizes_empty_http_path_to_root(self):
        self.assertEqual(
            normalize_url("https://EXAMPLE.com#fragment"),
            "https://example.com/",
        )
        self.assertEqual(
            normalize_url("http://example.com:80"),
            "http://example.com/",
        )

