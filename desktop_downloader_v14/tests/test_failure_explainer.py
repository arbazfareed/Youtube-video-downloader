import unittest

from failure_explainer import explain_failure


class FailureExplainerTests(unittest.TestCase):
    def test_http_forbidden_explains_authentication(self):
        explanation, action = explain_failure("HTTP 403 Forbidden")
        self.assertIn("refused", explanation)
        self.assertIn("cookies", action)

    def test_html_response_suggests_extractor(self):
        explanation, action = explain_failure("Content-Type text/html")
        self.assertIn("web page", explanation)
        self.assertIn("Supported site", action)

    def test_unknown_error_has_action(self):
        explanation, action = explain_failure("unrecognized runtime error")
        self.assertTrue(explanation)
        self.assertTrue(action)


if __name__ == "__main__":
    unittest.main()
