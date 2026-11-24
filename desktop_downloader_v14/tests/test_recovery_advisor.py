import unittest

from recovery_advisor import recovery_advice


class RecoveryAdviceTests(unittest.TestCase):
    def test_network_errors_are_retryable(self):
        retry, advice = recovery_advice("Connection timed out")
        self.assertTrue(retry)
        self.assertIn("partial", advice)

    def test_auth_errors_are_not_retryable_without_credentials(self):
        retry, advice = recovery_advice("HTTP 403 Forbidden")
        self.assertFalse(retry)
        self.assertIn("cookies", advice)

    def test_rate_limit_suggests_waiting(self):
        retry, advice = recovery_advice("HTTP 429 Too Many Requests")
        self.assertTrue(retry)
        self.assertIn("minutes", advice)

    def test_unknown_error_has_safe_fallback(self):
        retry, advice = recovery_advice("Unexpected extractor crash")
        self.assertTrue(retry)
        self.assertIn("diagnostic", advice)


if __name__ == "__main__":
    unittest.main()
