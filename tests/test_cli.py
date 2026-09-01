import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zulip_hub.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.config = root / "config.toml"
        self.state = root / "state.json"
        self.config.write_text(
            '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n'
        )
        self.state.write_text(json.dumps({
            "recent": [{
                "id": 42, "type": "stream", "stream_id": 9,
                "channel": "backend", "topic": "deploy", "recipient_ids": [],
            }]
        }))

    def tearDown(self):
        self.temporary.cleanup()

    @patch("zulip_hub.cli.UrlOpener.open")
    def test_open_message_uses_recent_metadata(self, open_url):
        result = main([
            "--config", str(self.config), "--state", str(self.state),
            "open-message", "42",
        ])
        self.assertEqual(result, 0)
        open_url.assert_called_once_with(
            "https://chat.example.com/#narrow/channel/9-backend/topic/deploy/near/42"
        )

    @patch("zulip_hub.cli.UrlOpener.open")
    def test_open_url_rejects_another_server(self, open_url):
        result = main([
            "--config", str(self.config), "open-url",
            "https://evil.example/#narrow/channel/1-x/topic/y/near/2",
        ])
        self.assertEqual(result, 2)
        open_url.assert_not_called()

    @patch("zulip_hub.cli.ZulipClient")
    @patch("zulip_hub.cli.SecretToolProvider.get", return_value="test-key")
    def test_mark_read_calls_api(self, _secret, client_class):
        result = main(["--config", str(self.config), "mark-read", "42"])
        self.assertEqual(result, 0)
        client_class.return_value.mark_read.assert_called_once_with([42])

    @patch("zulip_hub.cli.resolve_launch_command", return_value=("zulip",))
    @patch("zulip_hub.cli.HyprlandController")
    def test_workspace_toggle_needs_no_secret(self, controller, _resolve):
        controller.return_value.toggle.return_value = "launched"
        result = main(["--config", str(self.config), "workspace-toggle"])
        self.assertEqual(result, 0)
        controller.return_value.toggle.assert_called_once_with()

    @patch("zulip_hub.cli.resolve_launch_command", return_value=("zulip",))
    @patch("zulip_hub.cli.HyprlandController")
    def test_workspace_status_needs_no_secret(self, controller, _resolve):
        controller.return_value.status.return_value = {
            "workspace": "special:zulip", "visible": False, "client": None
        }
        result = main(["--config", str(self.config), "workspace-status"])
        self.assertEqual(result, 0)
        controller.return_value.status.assert_called_once_with()

    @patch("zulip_hub.cli.run_action", return_value={"ok": True, "installed": False})
    def test_os_integration_routes_to_the_marketplace_action(self, run_action):
        result = main(["os-integration", "status"])
        self.assertEqual(result, 0)
        run_action.assert_called_once_with(Path(__file__).resolve().parents[1], "status")

    @patch("zulip_hub.cli.serve_composer_once", return_value=0)
    def test_compose_routes_to_private_stdin_protocol(self, serve):
        result = main([
            "--config", str(self.config), "--state", str(self.state), "compose",
        ])
        self.assertEqual(result, 0)
        serve.assert_called_once_with(self.config, self.state)
