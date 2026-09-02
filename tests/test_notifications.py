import unittest
from unittest.mock import patch

from zulip_hub.config import NotificationConfig
from zulip_hub.notifications import (
    LockDetector, NotificationCoordinator, OmarchyNotificationSender, _plain_preview,
)


class FakeSender:
    def __init__(self):
        self.calls = []

    def send(self, summary, body, url, **kwargs):
        self.calls.append((summary, body, url, kwargs))
        return 100 + len(self.calls)


class FakeLock:
    def __init__(self, locked=False):
        self.locked = locked

    def is_locked(self):
        return self.locked


def stream_message(**overrides):
    message = {
        "id": 42, "type": "stream", "stream_id": 9,
        "display_recipient": "backend", "subject": "deploy",
        "sender_full_name": "Alice", "sender_email": "alice@example.com",
        "content": "**Ship it**", "flags": ["mentioned"],
    }
    message.update(overrides)
    return message


class NotificationTests(unittest.TestCase):
    def coordinator(self, config=None, locked=False, times=None):
        sender = FakeSender()
        values = iter(times or [1.0])
        coordinator = NotificationCoordinator(
            "https://chat.example.com", "me@example.com",
            config or NotificationConfig(), sender, FakeLock(locked), lambda: next(values),
        )
        return coordinator, sender

    def test_mentions_are_notified_but_other_messages_are_not(self):
        coordinator, sender = self.coordinator(times=[1.0])
        coordinator.handle_message(stream_message())
        coordinator.handle_message(stream_message(id=43, flags=[]))
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(sender.calls[0][3]["urgency"], "normal")

    def test_mute_wins_and_always_channel_enables_other_messages(self):
        config = NotificationConfig(muted_channels=("bots",), always_channels=("incidents",))
        coordinator, sender = self.coordinator(config, times=[1.0])
        coordinator.handle_message(stream_message(display_recipient="bots"))
        coordinator.handle_message(stream_message(id=43, display_recipient="incidents", flags=[]))
        self.assertEqual(len(sender.calls), 1)

    def test_group_replaces_notification_with_count(self):
        coordinator, sender = self.coordinator(times=[1.0, 5.0])
        coordinator.handle_message(stream_message())
        coordinator.handle_message(stream_message(id=43))
        self.assertEqual(sender.calls[1][3]["replace_id"], 101)
        self.assertIn("2 nouveaux messages", sender.calls[1][1])

    def test_locked_screen_redacts_sender_conversation_and_body(self):
        coordinator, sender = self.coordinator(locked=True, times=[1.0])
        coordinator.handle_message(stream_message(content="company secret"))
        summary, body, _url, _options = sender.calls[0]
        self.assertEqual(summary, "Zulip")
        self.assertEqual(body, "1 nouveau message")
        self.assertNotIn("secret", summary + body)

    def test_own_messages_are_ignored(self):
        coordinator, sender = self.coordinator()
        coordinator.handle_message(stream_message(sender_email="ME@example.com"))
        self.assertEqual(sender.calls, [])

    def test_followed_topic_state_and_events_control_notifications(self):
        coordinator, sender = self.coordinator(times=[1.0])
        coordinator.initialize({
            "user_topics": [
                {"stream_id": 9, "topic_name": "deploy", "visibility_policy": 3}
            ]
        })
        coordinator.handle_event({"type": "message", "message": stream_message(flags=[])})
        self.assertEqual(len(sender.calls), 1)
        coordinator.handle_event({
            "type": "user_topic", "stream_id": 9,
            "topic_name": "deploy", "visibility_policy": 1,
        })
        self.assertNotIn((9, "deploy"), coordinator.followed_topics)

    def test_modern_wildcard_mention_is_notified(self):
        coordinator, sender = self.coordinator(times=[1.0])
        coordinator.handle_message(stream_message(flags=["topic_wildcard_mentioned"]))
        self.assertEqual(len(sender.calls), 1)

    def test_plain_preview_removes_markup_and_limits_length(self):
        preview = _plain_preview("<b>hello</b> **world** " + "x" * 300)
        self.assertNotIn("<b>", preview)
        self.assertLessEqual(len(preview), 180)
        self.assertEqual(_plain_preview("--exec"), "Message: --exec")

    @patch("zulip_hub.notifications.commands.run")
    def test_sender_uses_argv_click_action_and_replacement(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = "77\n"
        notification_id = OmarchyNotificationSender().send(
            "Alice", "hello", "https://chat.example.com/#narrow/x",
            urgency="normal", replace_id=12,
        )
        command = run.call_args.args[0]
        self.assertNotIn("bash", command)
        self.assertEqual(command[command.index("--app-name") + 1], "zulip-hub")
        self.assertIn("--replace-id", command)
        self.assertEqual(command[-3:], ["zulip-hub", "open-url", "https://chat.example.com/#narrow/x"])
        self.assertEqual(notification_id, 77)

    @patch("zulip_hub.notifications.commands.run")
    def test_lock_detector_fails_closed_on_unavailable_shell(self, run):
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        self.assertTrue(LockDetector().is_locked())
