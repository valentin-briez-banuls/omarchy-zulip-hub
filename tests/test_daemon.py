import json
from pathlib import Path
import tempfile
import unittest

from zulip_hub.api import ZulipAPIError
from zulip_hub.daemon import IDLE_RETRY_SECONDS, BridgeDaemon
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


class AlwaysExpiredClient:
    """Rejette chaque interrogation : le cas qui bouclait sans temporisation."""

    def __init__(self, stop_after: int):
        self.registrations = 0
        self.stop_after = stop_after
        self.daemon = None

    def register(self):
        self.registrations += 1
        if self.daemon is not None and self.registrations > self.stop_after:
            self.daemon.running = False
        return {"queue_id": "q", "last_event_id": 0, "unread_msgs": {}}

    def events(self, queue_id, last_event_id):
        raise ZulipAPIError("expired", code="BAD_EVENT_QUEUE_ID")


class RateLimitedClient(AlwaysExpiredClient):
    def events(self, queue_id, last_event_id):
        raise ZulipAPIError(
            "limite", code="RATE_LIMIT_HIT", retryable=True, retry_after=30,
        )


class RejectingClient:
    """Refus definitif du serveur : une cle revoquee, par exemple.

    Sortir sur ce refus fait relancer le bridge par le service toutes les cinq
    secondes, et chaque relance rappelle l API. Le compte serait martele
    indefiniment pour une erreur qui ne se resoudra pas seule.
    """

    def __init__(self, stop_after: int):
        self.registrations = 0
        self.stop_after = stop_after
        self.daemon = None

    def register(self):
        self.registrations += 1
        if self.daemon is not None and self.registrations > self.stop_after:
            self.daemon.running = False
        raise ZulipAPIError("clé révoquée", code="UNAUTHORIZED", retryable=False)

    def events(self, queue_id, last_event_id):
        return []


class DaemonTests(unittest.TestCase):
    def test_a_definitive_refusal_does_not_end_the_process(self):
        client = RejectingClient(stop_after=3)
        self._run_until_stopped(client, initial_backoff=1, max_backoff=60)
        self.assertGreaterEqual(client.registrations, 3)

    def test_a_definitive_refusal_waits_long_between_attempts(self):
        delays = self._run_until_stopped(
            RejectingClient(stop_after=3), initial_backoff=1, max_backoff=60,
        )
        self.assertTrue(delays)
        self.assertTrue(all(delay >= IDLE_RETRY_SECONDS for delay in delays), delays)

    def test_a_definitive_refusal_is_reported_while_the_bridge_waits(self):
        """Ce qui compte est ce que le panneau lit pendant l attente, non
        l etat laisse apres une extinction propre."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            client = RejectingClient(stop_after=1)
            daemon = BridgeDaemon(
                client, StateStore(path), StateReducer(), sleep=lambda _: None,
            )
            client.daemon = daemon
            observees = []
            ecriture = daemon.store.write

            def capture(state):
                observees.append((state.connected, state.error))
                ecriture(state)

            daemon.store.write = capture
            daemon.run()
        self.assertTrue(
            any(not connecte and erreur and "révoquée" in erreur for connecte, erreur in observees),
            observees,
        )

    def test_the_idle_delay_is_long_enough_to_spare_the_account(self):
        self.assertGreaterEqual(IDLE_RETRY_SECONDS, 300)

    def _run_until_stopped(self, client, **options):
        delays = []
        with tempfile.TemporaryDirectory() as directory:
            daemon = BridgeDaemon(
                client, StateStore(Path(directory) / "state.json"), StateReducer(),
                sleep=delays.append, **options,
            )
            client.daemon = daemon
            daemon.run()
        return delays

    def test_a_queue_rejected_over_and_over_backs_off_instead_of_hammering(self):
        delays = self._run_until_stopped(
            AlwaysExpiredClient(stop_after=6), initial_backoff=1, max_backoff=60,
        )
        self.assertTrue(delays, "le reenregistrement na attendu a aucun moment")
        self.assertGreater(delays[-1], delays[0])

    def test_a_rate_limited_poll_waits_at_least_the_delay_the_server_asked_for(self):
        delays = self._run_until_stopped(
            RateLimitedClient(stop_after=3), initial_backoff=1, max_backoff=60,
        )
        self.assertTrue(delays)
        self.assertTrue(all(delay >= 30 for delay in delays), delays)


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
