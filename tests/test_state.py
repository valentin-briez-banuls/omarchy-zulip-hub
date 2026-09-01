import json
from pathlib import Path
import tempfile
import unittest

from zulip_hub.state import StateReducer, StateStore


class StateTests(unittest.TestCase):
    def test_message_updates_counts_and_recent_without_content(self):
        reducer = StateReducer(limit=2)
        reducer.apply({"type": "message", "message": {
            "id": 42, "type": "private", "sender_full_name": "Alice",
            "sender_id": 7,
            "content": "secret body", "timestamp": 10, "flags": ["mentioned"],
            "display_recipient": [{"id": 7}, {"id": 8}],
        }})
        self.assertEqual(reducer.state.unread, {"total": 1, "mentions": 1, "private": 1})
        self.assertNotIn("content", reducer.state.recent[0])
        self.assertEqual(reducer.state.recent[0]["recipient_ids"], [7, 8])
        self.assertEqual(reducer.state.recent[0]["sender_id"], 7)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            StateStore(path).write(reducer.state)
            self.assertEqual(json.loads(path.read_text())["recent"][0]["id"], 42)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_read_flags_never_make_count_negative(self):
        reducer = StateReducer()
        reducer.apply({"type": "update_message_flags", "flag": "read", "operation": "add", "messages": [1, 2]})
        self.assertEqual(reducer.state.unread["total"], 0)

    def test_read_flags_update_all_categories(self):
        reducer = StateReducer()
        reducer.apply({"type": "message", "message": {
            "id": 42, "type": "private", "flags": ["mentioned"]
        }})
        reducer.apply({
            "type": "update_message_flags", "flag": "read",
            "operation": "add", "messages": [42],
        })
        self.assertEqual(reducer.state.unread, {"total": 0, "mentions": 0, "private": 0})

    def test_registration_counts_unique_unread_ids(self):
        reducer = StateReducer()
        reducer.initialized({"unread_msgs": {
            "mentions": [2], "pms": [1], "streams": [[7, [2, 3]]]
        }})
        self.assertEqual(reducer.state.unread, {"total": 3, "mentions": 1, "private": 1})

    def test_registration_records_server_message_limit(self):
        reducer = StateReducer()
        reducer.initialized({"unread_msgs": {}, "max_message_length": 12345})
        self.assertEqual(reducer.state.max_message_length, 12345)

    def test_mark_all_read_uses_modern_op_field(self):
        reducer = StateReducer()
        reducer.apply({"type": "message", "message": {
            "id": 42, "type": "private", "flags": ["topic_wildcard_mentioned"]
        }})
        reducer.apply({"type": "update_message_flags", "flag": "read", "op": "add", "all": True, "messages": []})
        self.assertEqual(reducer.state.unread, {"total": 0, "mentions": 0, "private": 0})
