from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from zulip_hub.api import ZulipAPIError
from zulip_hub.reader import ReaderError, ReaderManager, serve_once


class ReaderTests(unittest.TestCase):
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
            "recent": [
                {
                    "id": 42, "type": "stream", "sender": "Alice Martin",
                    "channel": "backend", "topic": "deployment",
                    "stream_id": 9, "timestamp": 1788264000, "flags": ["mentioned"],
                },
                {
                    "id": 43, "type": "private", "sender": "Bob Durand",
                    "channel": None, "topic": None, "recipient_ids": [1, 8],
                    "timestamp": 1788264060, "flags": [],
                },
            ],
        }), encoding="utf-8")
        self.secrets = Mock()
        self.secrets.get.return_value = "top-secret"

    def tearDown(self):
        self.temporary.cleanup()

    @patch("zulip_hub.reader.ZulipClient")
    def test_reading_a_listed_message_joins_its_content_to_the_local_metadata(self, client_class):
        client_class.return_value.message.return_value = {
            "id": 42, "content": "Bonjour **équipe**", "sender_full_name": "Ignoré",
        }
        result = ReaderManager(self.config, self.state, self.secrets).read({"message_id": 42})
        client_class.return_value.message.assert_called_once_with(42)
        self.assertTrue(result["ok"])
        shown = result["message"]
        self.assertEqual(shown["content"], "Bonjour **équipe**")
        self.assertEqual(shown["sender"], "Alice Martin")
        self.assertEqual(shown["channel"], "backend")
        self.assertEqual(shown["topic"], "deployment")
        self.assertEqual(shown["type"], "stream")
        self.assertEqual(shown["timestamp"], 1788264000)

    @patch("zulip_hub.reader.ZulipClient")
    def test_a_direct_message_carries_no_channel(self, client_class):
        client_class.return_value.message.return_value = {"id": 43, "content": "Salut"}
        result = ReaderManager(self.config, self.state, self.secrets).read({"message_id": 43})
        self.assertEqual(result["message"]["type"], "private")
        self.assertIsNone(result["message"]["channel"])
        self.assertEqual(result["message"]["sender"], "Bob Durand")

    def test_a_message_absent_from_the_local_state_is_refused(self):
        manager = ReaderManager(self.config, self.state, self.secrets)
        with self.assertRaises(ReaderError):
            manager.read({"message_id": 999})

    def test_an_invalid_identifier_is_refused(self):
        manager = ReaderManager(self.config, self.state, self.secrets)
        for payload in ({"message_id": True}, {"message_id": 0}, {"message_id": "42"}, {}):
            with self.subTest(payload=payload), self.assertRaises(ReaderError):
                manager.read(payload)

    @patch("zulip_hub.reader.ReaderManager.handle")
    def test_the_protocol_reports_a_failure_without_echoing_the_message(self, handle):
        handle.side_effect = ZulipAPIError("serveur Zulip inaccessible")
        output = StringIO()
        serve_once(
            self.config, self.state,
            StringIO(json.dumps({"action": "read", "message_id": 42}) + "\n"),
            output,
        )
        response = json.loads(output.getvalue())
        self.assertFalse(response["ok"])
        self.assertIn("inaccessible", response["error"])


if __name__ == "__main__":
    unittest.main()
