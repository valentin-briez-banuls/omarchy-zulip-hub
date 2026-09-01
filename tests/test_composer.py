from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from zulip_hub.api import ZulipAPIError
from zulip_hub.composer import ComposerError, ComposerManager, serve_once


class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.config = root / "config.toml"
        self.state = root / "state.json"
        self.config.write_text(
            '[account]\nsite="https://chat.example.com"\nemail="me@example.com"\n',
            encoding="utf-8",
        )
        self.state.write_text(json.dumps({
            "max_message_length": 120,
            "recent": [
                {
                    "id": 42, "type": "private", "sender_id": 7,
                    "recipient_ids": [1, 7, 8],
                },
                {
                    "id": 43, "type": "stream", "sender_id": 7, "stream_id": 9,
                    "channel": "backend", "topic": "deployment", "recipient_ids": [],
                },
            ],
        }), encoding="utf-8")
        self.secrets = Mock()
        self.secrets.get.return_value = "top-secret"

    def tearDown(self):
        self.temporary.cleanup()

    @patch("zulip_hub.composer.ZulipClient")
    def test_directory_filters_accounts_and_returns_recent_contacts(self, client_class):
        client = client_class.return_value
        client.test_connection.return_value = {"user_id": 1}
        client.users.return_value = [
            {"user_id": 1, "full_name": "Moi", "email": "me@example.com", "is_active": True},
            {"user_id": 7, "full_name": "Alice", "email": "alice@example.com", "is_active": True},
            {"user_id": 8, "full_name": "Bob", "email": "bob@example.com", "is_active": True},
            {"user_id": 9, "full_name": "Robot", "email": "bot@example.com", "is_active": True, "is_bot": True},
            {"user_id": 10, "full_name": "Parti", "email": "old@example.com", "is_active": False},
            {"user_id": 11, "full_name": "Import", "email": "stub@example.com", "is_active": True, "is_imported_stub": True},
        ]
        result = ComposerManager(self.config, self.state, self.secrets).directory()
        self.assertEqual([user["id"] for user in result["users"]], [7, 8])
        self.assertEqual(result["recent_user_ids"], [7, 8])
        self.assertEqual(result["max_message_length"], 120)
        self.assertNotIn("top-secret", json.dumps(result))

    @patch("zulip_hub.composer.ZulipClient")
    def test_send_validates_deduplicates_and_returns_only_message_id(self, client_class):
        client_class.return_value.send_direct.return_value = 42
        manager = ComposerManager(self.config, self.state, self.secrets)
        result = manager.send_direct({
            "recipient_ids": [7, 7, 8], "content": "Bonjour **équipe**",
        })
        client_class.return_value.send_direct.assert_called_once_with(
            [7, 8], "Bonjour **équipe**",
        )
        self.assertEqual(result, {"ok": True, "message_id": 42})

    def test_send_rejects_missing_recipient_empty_and_oversized_content(self):
        manager = ComposerManager(self.config, self.state, self.secrets)
        for payload in (
            {"recipient_ids": [], "content": "Bonjour"},
            {"recipient_ids": [7], "content": "   "},
            {"recipient_ids": [7], "content": "x" * 121},
            {"recipient_ids": [True], "content": "Bonjour"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ComposerError):
                manager.send_direct(payload)

    @patch("zulip_hub.composer.ZulipClient")
    def test_reply_to_a_direct_message_answers_the_same_people_without_me(self, client_class):
        client = client_class.return_value
        client.test_connection.return_value = {"user_id": 1}
        client.send_direct.return_value = 51
        manager = ComposerManager(self.config, self.state, self.secrets)
        result = manager.reply({"message_id": 42, "content": "Bien reçu"})
        client.send_direct.assert_called_once_with([7, 8], "Bien reçu")
        self.assertEqual(result, {"ok": True, "message_id": 51})

    @patch("zulip_hub.composer.ZulipClient")
    def test_reply_to_a_channel_message_answers_in_the_same_topic(self, client_class):
        client_class.return_value.send_stream.return_value = 52
        manager = ComposerManager(self.config, self.state, self.secrets)
        result = manager.reply({"message_id": 43, "content": "Je m’en occupe"})
        client_class.return_value.send_stream.assert_called_once_with(
            9, "deployment", "Je m’en occupe",
        )
        self.assertEqual(result, {"ok": True, "message_id": 52})

    @patch("zulip_hub.composer.ZulipClient")
    def test_handle_routes_the_reply_action(self, client_class):
        client_class.return_value.send_stream.return_value = 53
        manager = ComposerManager(self.config, self.state, self.secrets)
        result = manager.handle({"action": "reply", "message_id": 43, "content": "ok"})
        self.assertEqual(result, {"ok": True, "message_id": 53})

    def test_reply_refuses_a_message_absent_from_the_local_state(self):
        manager = ComposerManager(self.config, self.state, self.secrets)
        with self.assertRaises(ComposerError):
            manager.reply({"message_id": 999, "content": "Bonjour"})

    def test_reply_applies_the_same_content_limits_as_a_new_message(self):
        manager = ComposerManager(self.config, self.state, self.secrets)
        for payload in (
            {"message_id": 42, "content": "   "},
            {"message_id": 42, "content": "x" * 121},
            {"message_id": True, "content": "Bonjour"},
            {"message_id": 42},
        ):
            with self.subTest(payload=payload), self.assertRaises(ComposerError):
                manager.reply(payload)

    @patch("zulip_hub.composer.ComposerManager.handle")
    def test_protocol_reports_uncertain_delivery_without_echoing_content(self, handle):
        handle.side_effect = ZulipAPIError("serveur inaccessible", retryable=True)
        output = StringIO()
        serve_once(
            self.config,
            self.state,
            StringIO(json.dumps({
                "action": "send_direct", "recipient_ids": [7], "content": "très secret",
            }) + "\n"),
            output,
        )
        response = json.loads(output.getvalue())
        self.assertFalse(response["ok"])
        self.assertTrue(response["delivery_uncertain"])
        self.assertNotIn("très secret", output.getvalue())
