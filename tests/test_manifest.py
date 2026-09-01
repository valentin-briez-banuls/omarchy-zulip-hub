import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.bar_widget = self.manifest["barWidget"]

    def test_every_widget_default_is_exposed_in_the_settings_schema(self):
        keys = {entry["key"] for entry in self.bar_widget.get("schema", [])}
        self.assertEqual(keys, set(self.bar_widget["defaults"]))

    def test_the_settings_schema_agrees_with_the_declared_defaults(self):
        defaults = self.bar_widget["defaults"]
        for entry in self.bar_widget.get("schema", []):
            self.assertEqual(entry["defaultValue"], defaults[entry["key"]], entry["key"])

    def test_the_root_manifest_is_the_only_plugin_manifest(self):
        found = sorted(
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("manifest.json")
            if ".git" not in path.parts
        )
        self.assertEqual(found, ["manifest.json"])


if __name__ == "__main__":
    unittest.main()
