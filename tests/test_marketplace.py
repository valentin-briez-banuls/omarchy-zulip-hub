from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from zulip_hub.files import HYPR_BLOCK
from zulip_hub.marketplace import OsIntegration


class MarketplaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.main = self.home / ".config/hypr/hyprland.lua"
        self.main.parent.mkdir(parents=True)
        self.main.write_text("-- user config\n")
        self.source = Path(__file__).resolve().parents[1]
        self.integration = OsIntegration(self.source, self.home)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def completed(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "", "")

    @staticmethod
    def hyprland_refuses(argv, **kwargs):
        if argv[0] == "hyprland":
            raise OSError("hyprland indisponible")
        return subprocess.CompletedProcess(argv, 0, "", "")

    @patch("zulip_hub.marketplace.subprocess.run", side_effect=completed)
    def test_install_and_remove_only_manage_the_owned_hyprland_block(self, run):
        self.assertFalse(self.integration.status()["installed"])
        self.assertTrue(self.integration.install()["installed"])
        self.assertIn(HYPR_BLOCK.strip(), self.main.read_text())
        self.assertTrue(self.integration.hypr_module.exists())
        self.assertFalse(self.integration.remove()["installed"])
        self.assertNotIn(HYPR_BLOCK.strip(), self.main.read_text())
        self.assertFalse(self.integration.hypr_module.exists())

    @patch("zulip_hub.marketplace.subprocess.run", side_effect=completed)
    def test_remove_refuses_a_modified_managed_module(self, run):
        self.integration.install()
        self.integration.hypr_module.write_text("-- local change\n")
        with self.assertRaisesRegex(Exception, "modifié"):
            self.integration.remove()
        self.assertTrue(self.integration.hypr_module.exists())


    def _downgrade_module_to_the_previous_version(self):
        legacy = self.integration.hypr_module.read_text(encoding="utf-8").replace(
            "io.github.valentin-briez-banuls.zulip-hub toggle", "zulip-hub toggle"
        )
        self.integration.hypr_module.write_text(legacy, encoding="utf-8")

    @patch("zulip_hub.marketplace.subprocess.run", side_effect=completed)
    def test_install_upgrades_a_managed_module_left_by_an_older_version(self, run):
        self.integration.install()
        self._downgrade_module_to_the_previous_version()
        self.assertFalse(self.integration.status()["installed"])
        self.assertTrue(self.integration.install()["installed"])
        self.assertEqual(
            self.integration.hypr_module.read_bytes(),
            self.integration.source_module.read_bytes(),
        )

    @patch("zulip_hub.marketplace.subprocess.run", side_effect=completed)
    def test_remove_clears_a_managed_module_left_by_an_older_version(self, run):
        self.integration.install()
        self._downgrade_module_to_the_previous_version()
        self.assertFalse(self.integration.remove()["installed"])
        self.assertFalse(self.integration.hypr_module.exists())

    def test_a_failed_upgrade_restores_the_module_the_hyprland_block_requires(self):
        with patch("zulip_hub.marketplace.subprocess.run", side_effect=self.completed):
            self.integration.install()
        self._downgrade_module_to_the_previous_version()
        previous = self.integration.hypr_module.read_bytes()
        with patch("zulip_hub.marketplace.subprocess.run", side_effect=self.hyprland_refuses):
            with self.assertRaises(Exception):
                self.integration.install()
        self.assertTrue(self.integration.hypr_module.exists())
        self.assertEqual(self.integration.hypr_module.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
