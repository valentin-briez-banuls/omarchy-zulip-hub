from pathlib import Path
import tempfile
import unittest

from zulip_hub.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "config.toml"

    def tearDown(self):
        self.temporary.cleanup()

    def test_load_valid_config(self):
        self.path.write_text('[account]\nsite="https://chat.example.com/"\nemail="me@example.com"\n')
        config = load_config(self.path)
        self.assertEqual(config.account.site, "https://chat.example.com")
        self.assertEqual(config.recent_message_limit, 30)

    def test_rejects_plaintext_secret(self):
        for field in ("key", "api_key"):
            with self.subTest(field=field):
                self.path.write_text(
                    f'[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n{field}="secret"\n'
                )
                with self.assertRaisesRegex(ConfigError, "clé API"):
                    load_config(self.path)

    def test_requires_https(self):
        self.path.write_text('[account]\nsite="http://chat.example.com"\nemail="me@example.com"\n')
        with self.assertRaisesRegex(ConfigError, "https"):
            load_config(self.path)

    def test_non_finite_or_absurd_bridge_values_are_refused(self):
        head = '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n[bridge]\n'
        for body in (
            "request_timeout_seconds = 999999999",
            "request_timeout_seconds = nan",
            "initial_backoff_seconds = nan",
            "max_backoff_seconds = inf",
            "max_backoff_seconds = 999999999",
            'request_timeout_seconds = "beaucoup"',
        ):
            with self.subTest(body=body):
                self.path.write_text(head + body + "\n")
                with self.assertRaises(ConfigError):
                    load_config(self.path)

    def test_loads_notification_and_opening_rules(self):
        self.path.write_text(
            '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n'
            '[notifications]\nother_messages=true\ngroup_window_seconds=25\n'
            'muted_channels=["bots"]\nalways_channels=["incidents"]\n'
            '[open]\nmode="desktop"\ndesktop_command=["zulip", "--new-window"]\n'
        )
        config = load_config(self.path)
        self.assertTrue(config.notifications.other_messages)
        self.assertEqual(config.notifications.muted_channels, ("bots",))
        self.assertEqual(config.opening.desktop_command, ("zulip", "--new-window"))

    def test_rejects_string_instead_of_notification_boolean(self):
        self.path.write_text(
            '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n'
            '[notifications]\nenabled="false"\n'
        )
        with self.assertRaisesRegex(ConfigError, "booléen"):
            load_config(self.path)

    def test_loads_workspace_configuration(self):
        self.path.write_text(
            '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n'
            '[workspace]\nname="team-chat"\nclass_pattern="^TeamChat$"\n'
            'launch_command=["team-chat", "--single"]\n'
        )
        config = load_config(self.path)
        self.assertEqual(config.workspace.name, "team-chat")
        self.assertEqual(config.workspace.class_pattern, "^TeamChat$")
        self.assertEqual(config.workspace.launch_command, ("team-chat", "--single"))

    def test_rejects_unsafe_workspace_name_and_non_re2_pattern(self):
        for values in (
            'name="bad:name"',
            'class_pattern="^(?=Zulip)"',
        ):
            with self.subTest(values=values):
                self.path.write_text(
                    '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n'
                    f'[workspace]\n{values}\n'
                )
                with self.assertRaises(ConfigError):
                    load_config(self.path)

    def test_accepts_legacy_config_but_rejects_unknown_schema(self):
        self.path.write_text(
            '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n'
            '[meta]\nschema_version=2\n'
        )
        with self.assertRaisesRegex(ConfigError, "non prise en charge"):
            load_config(self.path)
