from __future__ import annotations

import unittest

from history_store import DownloadRecord
from statistics_engine import calculate_statistics


def _record(url: str, status: str) -> DownloadRecord:
    return DownloadRecord(
        id=1,
        url=url,
        status=status,
        progress="100%",
        details="",
        destination="downloads",
        created_at="2026-10-11T12:00:00+00:00",
        hidden=False,
    )


class DownloadStatisticsTests(unittest.TestCase):
    def test_summarizes_lifetime_statuses_and_top_domains(self):
        records = [
            _record("https://example.com/a", "Complete"),
            _record("https://example.com/b", "Complete"),
            _record("https://other.example/video", "Failed"),
            _record("https://another.example/file", "Cancelled"),
            _record("https://another.example/stream", "Downloading"),
        ]

        statistics = calculate_statistics(records)

        self.assertEqual(statistics.total_downloads, 5)
        self.assertEqual(statistics.completed, 2)
        self.assertEqual(statistics.failed, 1)
        self.assertEqual(statistics.cancelled, 1)
        self.assertEqual(statistics.interrupted, 0)
        self.assertEqual(statistics.active, 1)
        self.assertEqual(statistics.success_rate, 50.0)
        self.assertEqual(
            statistics.top_domains,
            (
                ("another.example", 2),
                ("example.com", 2),
                ("other.example", 1),
            ),
        )

    def test_empty_history_and_records_without_web_domains_are_safe(self):
        statistics = calculate_statistics(
            [_record("magnet:?xt=urn:btih:abc", "Queued")]
        )

        self.assertEqual(statistics.total_downloads, 1)
        self.assertEqual(statistics.success_rate, 0.0)
        self.assertEqual(statistics.active, 1)
        self.assertEqual(statistics.top_domains, ())
        self.assertEqual(calculate_statistics([]).total_downloads, 0)
        generator_statistics = calculate_statistics(
            iter([_record("https://example.com/file", "Complete")])
        )
        self.assertEqual(generator_statistics.top_domains, (("example.com", 1),))

    def test_top_domain_limit_is_applied_and_rejects_negative_values(self):
        records = [
            _record(f"https://site-{index}.example/file", "Complete")
            for index in range(3)
        ]

        self.assertEqual(len(calculate_statistics(records, top_limit=2).top_domains), 2)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            calculate_statistics(records, top_limit=-1)


if __name__ == "__main__":
    unittest.main()
