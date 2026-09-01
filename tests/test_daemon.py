from pathlib import Path
import tempfile
import unittest

from zulip_hub.api import ZulipAPIError
from zulip_hub.daemon import BridgeDaemon
from zulip_hub.state import StateReducer, StateStore


class FakeClient:
    def __init__(self):
        self.registrations = 0
        self.polls = 0

    def register(self):
        self.registrations += 1
        return {"queue_id": f"q{self.registrations}", "last_event_id": 0, "unread_msgs": {}}

    def events(self, queue_id, last_event_id):
        self.polls += 1
        if self.polls == 1:
            raise ZulipAPIError("expired", code="BAD_EVENT_QUEUE_ID")
        return [{"id": 1, "type": "message", "message": {"id": 9, "type": "stream", "flags": []}}]


class FakeNotifier:
    def __init__(self):
        self.messages = []
        self.registrations = []

    def initialize(self, registration):
        self.registrations.append(registration)

    def handle_event(self, event):
        if event.get("type") == "message":
            self.messages.append(event["message"])


class DaemonTests(unittest.TestCase):
    def test_expired_queue_is_registered_again(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            notifier = FakeNotifier()
            daemon = BridgeDaemon(
                client, StateStore(Path(directory) / "state.json"), StateReducer(),
                sleep=lambda _: None, notifier=notifier,
            )
            original_write = daemon.store.write

            def stop_after_message(state):
                original_write(state)
                if state.recent:
                    daemon.running = False

            daemon.store.write = stop_after_message
            daemon.run()
            self.assertEqual(client.registrations, 2)
            self.assertEqual(len(notifier.registrations), 2)
            self.assertEqual(daemon.reducer.state.recent[0]["id"], 9)
            self.assertEqual(notifier.messages[0]["id"], 9)
