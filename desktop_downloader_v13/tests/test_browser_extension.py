import json
import unittest
from pathlib import Path


class BrowserExtensionManifestTests(unittest.TestCase):
    def test_chrome_and_firefox_manifests_reference_packaged_assets(self):
        extension_dir = Path(__file__).resolve().parents[1] / "browser_extension"
        for manifest_name in ("manifest.json", "manifest.firefox.json"):
            with self.subTest(manifest=manifest_name):
                manifest = json.loads(
                    (extension_dir / manifest_name).read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["name"], "Smart Downloader 13")
                background_file = (
                    manifest["background"].get("service_worker")
                    or manifest["background"]["scripts"][0]
                )
                self.assertTrue((extension_dir / background_file).is_file())
                self.assertTrue(
                    (extension_dir / manifest["action"]["default_popup"]).is_file()
                )
                for content_script in manifest["content_scripts"]:
                    for script in content_script["js"]:
                        self.assertTrue((extension_dir / script).is_file())
                self.assertIn("contextMenus", manifest["permissions"])

    def test_firefox_manifest_uses_a_v13_specific_addon_id(self):
        extension_dir = Path(__file__).resolve().parents[1] / "browser_extension"
        manifest = json.loads(
            (extension_dir / "manifest.firefox.json").read_text(encoding="utf-8")
        )
        self.assertIn("v13", manifest["browser_specific_settings"]["gecko"]["id"])


if __name__ == "__main__":
    unittest.main()
