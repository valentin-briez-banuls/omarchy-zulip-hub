import unittest
from unittest.mock import patch

from zulip_hub.config import OpenConfig
from zulip_hub.opening import OpenError, UrlOpener


class OpeningTests(unittest.TestCase):
    @patch("zulip_hub.opening.commands.available")
    def test_auto_prefers_configured_desktop_client(self, available):
        available.side_effect = lambda command: command == "zulip"
        command = UrlOpener(OpenConfig("auto", ("zulip", "--new-window"))).command("https://chat/#narrow/x")
        self.assertEqual(command, ["zulip", "--new-window", "https://chat/#narrow/x"])

    @patch("zulip_hub.opening.commands.available")
    def test_auto_falls_back_to_uwsm_browser(self, available):
        available.side_effect = lambda command: command == "uwsm-app"
        command = UrlOpener(OpenConfig()).command("https://chat/#narrow/x")
        self.assertEqual(command, ["uwsm-app", "--", "xdg-open", "https://chat/#narrow/x"])

    @patch("zulip_hub.opening.commands.available", return_value=False)
    def test_desktop_mode_fails_closed(self, _available):
        with self.assertRaises(OpenError):
            UrlOpener(OpenConfig("desktop", ("zulip",))).command("https://chat/#narrow/x")

