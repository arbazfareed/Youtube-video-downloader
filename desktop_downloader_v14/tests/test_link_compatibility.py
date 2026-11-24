import unittest

from link_compatibility import analyze_link, format_analysis


class LinkCompatibilityTests(unittest.TestCase):
    def test_rejects_invalid_url(self):
        self.assertFalse(analyze_link("not a URL").valid)

    def test_direct_media_is_detected(self):
        result = analyze_link("https://cdn.example.test/video.mp4?token=x")
        self.assertTrue(result.valid)
        self.assertEqual(result.kind, "direct file")

    def test_playlist_query_is_detected(self):
        self.assertTrue(analyze_link("https://example.test/watch?v=abc&list=xyz").playlist)

    def test_drm_service_is_explained(self):
        result = analyze_link("https://www.netflix.com/watch/123")
        self.assertIn("DRM", result.drm_service)
        self.assertIn("official", format_analysis(result).lower())

    def test_magnet_is_supported_as_a_link_type(self):
        result = analyze_link("magnet:?xt=urn:btih:abc")
        self.assertTrue(result.valid)
        self.assertEqual(result.kind, "torrent/magnet")


if __name__ == "__main__":
    unittest.main()
