import unittest
from unittest.mock import patch

from zulip_hub.config import OpenConfig
from zulip_hub.opening import OpenError, UrlOpener


class OpeningTests(unittest.TestCase):
    @patch("zulip_hub.opening.shutil.which")
    def test_auto_prefers_configured_desktop_client(self, which):
        which.side_effect = lambda command: "/usr/bin/zulip" if command == "zulip" else None
        command = UrlOpener(OpenConfig("auto", ("zulip", "--new-window"))).command("https://chat/#narrow/x")
        self.assertEqual(command, ["zulip", "--new-window", "https://chat/#narrow/x"])

    @patch("zulip_hub.opening.shutil.which")
    def test_auto_falls_back_to_uwsm_browser(self, which):
        which.side_effect = lambda command: "/usr/bin/uwsm-app" if command == "uwsm-app" else None
        command = UrlOpener(OpenConfig()).command("https://chat/#narrow/x")
        self.assertEqual(command, ["uwsm-app", "--", "xdg-open", "https://chat/#narrow/x"])

    @patch("zulip_hub.opening.shutil.which", return_value=None)
    def test_desktop_mode_fails_closed(self, _which):
        with self.assertRaises(OpenError):
            UrlOpener(OpenConfig("desktop", ("zulip",))).command("https://chat/#narrow/x")

