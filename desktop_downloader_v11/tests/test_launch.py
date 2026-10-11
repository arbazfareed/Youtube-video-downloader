import sys
import unittest
from unittest.mock import patch

from launch import _ensure_dependencies


class FrozenLauncherTests(unittest.TestCase):
    def test_packaged_app_does_not_try_to_install_dependencies(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch("launch.subprocess.run", side_effect=AssertionError("pip must not run")),
        ):
            _ensure_dependencies()


if __name__ == "__main__":
    unittest.main()
