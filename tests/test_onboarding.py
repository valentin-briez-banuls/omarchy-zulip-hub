from io import StringIO
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from zulip_hub.onboarding import OnboardingManager, serve_once


class FakeSecrets:
    def __init__(self):
        self.values = {}

    def get(self, site, email):
        from zulip_hub.secrets import SecretError
        try:
            return self.values[(site, email)]
        except KeyError as exc:
            raise SecretError("missing") from exc

    def store(self, site, email, key):
        self.values[(site, email)] = key

    def delete(self, site, email):
        self.values.pop((site, email), None)


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config = Path(self.temporary.name) / "config.toml"
        self.state = Path(self.temporary.name) / "state.json"
        source = Path(__file__).resolve().parents[1] / "config/config.example.toml"
        self.config.write_text(source.read_text())
        self.secrets = FakeSecrets()
        self.manager = OnboardingManager(self.config, self.secrets, self.state)

    def tearDown(self):
        self.temporary.cleanup()

    def test_status_hides_example_values_and_never_returns_secret(self):
        status = self.manager.status()
        self.assertFalse(status["configured"])
        self.assertEqual(status["site"], "")
        self.assertNotIn("api_key", status)

    @patch("zulip_hub.onboarding.ZulipClient.test_connection")
    def test_setup_tests_then_stores_config_and_activates(self, test_connection):
        test_connection.return_value = {"full_name": "Ada Lovelace"}
        result = self.manager.setup({
            "site": "https://chat.example.org/",
            "email": "ada@example.org",
            "api_key": "top-secret",
        })
        self.assertTrue(result["configured"])
        self.assertTrue(result["active"])
        self.assertEqual(result["identity"], "Ada Lovelace")
        self.assertEqual(self.secrets.values[
            ("https://chat.example.org", "ada@example.org")
        ], "top-secret")
        text = self.config.read_text()
        self.assertIn('site = "https://chat.example.org"', text)
        self.assertNotIn("top-secret", text)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    @patch("zulip_hub.onboarding.ZulipClient.test_connection")
    def test_disconnect_stops_service_and_deletes_secret(self, test_connection):
        test_connection.return_value = {"email": "ada@example.org"}
        self.manager.setup({
            "site": "https://chat.example.org",
            "email": "ada@example.org",
            "api_key": "top-secret",
        })
        result = self.manager.disconnect()
        self.assertFalse(result["configured"])
        self.assertFalse(result["active"])
        self.assertEqual(self.secrets.values, {})

    @patch("zulip_hub.onboarding.ZulipClient.test_connection")
    def test_paused_service_can_be_reactivated_without_resubmitting_key(self, test_connection):
        test_connection.return_value = {"email": "ada@example.org"}
        self.manager.setup({
            "site": "https://chat.example.org",
            "email": "ada@example.org",
            "api_key": "top-secret",
        })
        self.manager.deactivate()
        result = self.manager.activate()
        self.assertTrue(result["configured"])
        self.assertTrue(result["active"])

    @patch("zulip_hub.onboarding.ZulipClient.test_connection")
    def test_pause_and_restart_are_driven_by_markers_alone(self, test_connection):
        test_connection.return_value = {"email": "ada@example.org"}
        result = self.manager.setup({
            "site": "https://chat.example.org",
            "email": "ada@example.org",
            "api_key": "top-secret",
        })
        self.assertTrue(result["active"])
        self.assertTrue((self.state.parent / "restart").exists())
        self.manager.deactivate()
        self.assertTrue((self.state.parent / "paused").exists())
        self.manager.activate()
        self.assertFalse((self.state.parent / "paused").exists())

    @patch("subprocess.run")
    @patch("zulip_hub.onboarding.ZulipClient.test_connection")
    def test_no_external_command_is_ever_run(self, test_connection, run):
        """Le plugin ne pilote aucun service : la place du bridge est le shell.

        Cette propriete est celle que la place de marche inspecte ; la perdre
        reintroduirait une capacite que le plugin n exerce pas.
        """
        test_connection.return_value = {"email": "ada@example.org"}
        self.manager.setup({
            "site": "https://chat.example.org",
            "email": "ada@example.org",
            "api_key": "top-secret",
        })
        self.manager.save_settings({
            "notifications_enabled": True, "private_messages": True,
            "mentions": True, "followed_topics": True,
            "other_messages": False, "hide_content_when_locked": True,
            "group_window_seconds": 10, "muted_channels": [],
            "always_channels": [], "open_mode": "auto",
            "desktop_command": "", "workspace_launch_command": "",
        })
        self.manager.deactivate()
        self.manager.activate()
        self.manager.reconnect()
        self.manager.status()
        self.manager.diagnostics()
        run.assert_not_called()

    def test_protocol_returns_json_error_without_echoing_secret(self):
        output = StringIO()
        secret = "never-echo-this"
        request = StringIO(json.dumps({
            "action": "setup", "site": "http://unsafe.example",
            "email": "ada@example.org", "api_key": secret,
        }) + "\n")
        self.assertEqual(serve_once(self.config, request, output), 0)
        response = output.getvalue()
        self.assertFalse(json.loads(response)["ok"])
        self.assertNotIn(secret, response)

    def test_protocol_rejects_oversized_input(self):
        output = StringIO()
        serve_once(self.config, StringIO("x" * 65537), output)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    def test_advanced_settings_are_validated_written_and_reported(self):
        result = self.manager.save_settings({
            "notifications_enabled": True,
            "private_messages": False,
            "mentions": True,
            "followed_topics": False,
            "other_messages": True,
            "hide_content_when_locked": True,
            "group_window_seconds": 25,
            "muted_channels": ["bots", "bots", " noise "],
            "always_channels": ["incidents"],
            "open_mode": "desktop",
            "desktop_command": "zulip --new-window",
            "workspace_launch_command": "uwsm-app -- zulip",
        })
        settings = result["settings"]
        self.assertFalse(settings["private_messages"])
        self.assertEqual(settings["muted_channels"], ["bots", "noise"])
        self.assertEqual(settings["desktop_command"], ["zulip", "--new-window"])
        self.assertEqual(settings["workspace_launch_command"], ["uwsm-app", "--", "zulip"])
        self.assertNotIn("api_key", self.config.read_text())

    def test_command_with_spaces_round_trips_without_changing_arguments(self):
        self.manager.save_settings({
            "notifications_enabled": True, "private_messages": True,
            "mentions": True, "followed_topics": True,
            "other_messages": False, "hide_content_when_locked": True,
            "group_window_seconds": 10, "muted_channels": [],
            "always_channels": [], "open_mode": "desktop",
            "desktop_command": "client --profile 'Work Chat'",
            "workspace_launch_command": "",
        })
        text = self.manager.status()["settings"]["desktop_command_text"]
        self.assertEqual(shlex.split(text), ["client", "--profile", "Work Chat"])

    def test_settings_ask_the_bridge_to_restart(self):
        self.manager.save_settings({
            "notifications_enabled": True, "private_messages": True,
            "mentions": True, "followed_topics": True,
            "other_messages": False, "hide_content_when_locked": True,
            "group_window_seconds": 10, "muted_channels": [],
            "always_channels": [], "open_mode": "auto",
            "desktop_command": "", "workspace_launch_command": "",
        })
        self.assertTrue((self.state.parent / "restart").exists())

    def test_diagnostics_read_only_public_bridge_state(self):
        self.state.write_text(json.dumps({
            "schema_version": 1, "connected": True,
            "last_sync": "2026-09-01T20:00:00Z", "error": "",
            "unread": {"total": 2},
        }))
        result = self.manager.diagnostics()
        self.assertTrue(result["connected"])
        self.assertTrue(result["state_available"])
        self.assertEqual(result["state_schema"], 1)
        self.assertNotIn("unread", result)

    def test_reconnect_requires_configured_credentials(self):
        with self.assertRaisesRegex(Exception, "Configurez"):
            self.manager.reconnect()

    @patch("zulip_hub.onboarding.ZulipClient.test_connection")
    def test_reconnect_lifts_the_pause_and_asks_for_a_restart(self, test_connection):
        test_connection.return_value = {"email": "ada@example.org"}
        self.manager.setup({
            "site": "https://chat.example.org", "email": "ada@example.org",
            "api_key": "top-secret",
        })
        self.manager.deactivate()
        self.assertTrue((self.state.parent / "paused").exists())
        (self.state.parent / "restart").unlink(missing_ok=True)
        self.manager.reconnect()
        self.assertFalse((self.state.parent / "paused").exists())
        self.assertTrue((self.state.parent / "restart").exists())
