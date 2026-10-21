import unittest

from app import DownloaderApp


class SpeedGraphTests(unittest.TestCase):
    def test_speed_samples_keep_only_the_latest_sixty_points(self):
        app = DownloaderApp.__new__(DownloaderApp)
        app._speed_state = {}
        app._speed_history = {}
        app._active_graph_job = None
        app._last_graph_draw = 0.0
        app._draw_speed_graph = lambda: None

        for _ in range(65):
            app._record_speed_sample("job-1", "1.25 MB/s")

        self.assertEqual(len(app._speed_history["job-1"]), 60)
        self.assertAlmostEqual(app._speed_history["job-1"][-1], 1.25 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
