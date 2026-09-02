from __future__ import annotations

import logging
import random
import signal
import time
from typing import Callable

from .api import ZulipAPIError
from .state import HubState, StateReducer, StateStore, utc_now


LOGGER = logging.getLogger("zulip_hub")


class BridgeDaemon:
    def __init__(
        self,
        client,
        store: StateStore,
        reducer: StateReducer,
        initial_backoff: float = 1,
        max_backoff: float = 60,
        sleep: Callable[[float], None] = time.sleep,
        notifier=None,
    ):
        self.client = client
        self.store = store
        self.reducer = reducer
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.sleep = sleep
        self.notifier = notifier
        self.running = True
        self.reducer.state.server_url = getattr(client, "site", "")

    def stop(self, *_args) -> None:
        self.running = False

    def _delay_for(self, backoff: float, exc: ZulipAPIError) -> float:
        """Temporisation avant un nouvel essai, jamais nulle.

        Un chemin sans attente transforme une file rejetee en boucle serree sur
        l API, et le quota est celui du compte, partage avec le client Zulip.
        Un delai reclame par le serveur prime sur le report exponentiel.
        """
        delay = min(self.max_backoff, backoff) * random.uniform(0.8, 1.2)
        requested = getattr(exc, "retry_after", None)
        if isinstance(requested, (int, float)) and not isinstance(requested, bool):
            delay = max(delay, float(requested))
        return delay

    def run(self) -> None:
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        backoff = self.initial_backoff
        queue_id = None
        last_event_id = -1
        while self.running:
            try:
                if queue_id is None:
                    registration = self.client.register()
                    queue_id = registration["queue_id"]
                    last_event_id = registration["last_event_id"]
                    self.reducer.initialized(registration)
                    if self.notifier and hasattr(self.notifier, "initialize"):
                        self.notifier.initialize(registration)
                    self.store.write(self.reducer.state)
                    LOGGER.info("connexion Zulip établie")
                for event in self.client.events(queue_id, last_event_id):
                    last_event_id = max(last_event_id, int(event.get("id", last_event_id)))
                    if event.get("type") != "heartbeat":
                        self.reducer.apply(event)
                        if self.notifier:
                            try:
                                if hasattr(self.notifier, "handle_event"):
                                    self.notifier.handle_event(event)
                                elif event.get("type") == "message":
                                    self.notifier.handle_message(event.get("message", {}))
                            except Exception as exc:
                                LOGGER.warning("notification ignorée après erreur %s", type(exc).__name__)
                self.store.write(self.reducer.state)
                backoff = self.initial_backoff
            except ZulipAPIError as exc:
                delay = self._delay_for(backoff, exc)
                if exc.code == "BAD_EVENT_QUEUE_ID":
                    LOGGER.warning("file d'événements expirée; réenregistrement dans %.1fs", delay)
                    self.sleep(delay)
                    backoff = min(self.max_backoff, backoff * 2)
                    queue_id = None
                    continue
                self._record_error(str(exc))
                if not exc.retryable:
                    LOGGER.error("erreur Zulip non récupérable: %s", exc)
                    return
                LOGGER.warning("connexion impossible; nouvel essai dans %.1fs", delay)
                self.sleep(delay)
                backoff = min(self.max_backoff, backoff * 2)
                queue_id = None
            except (KeyError, TypeError, ValueError) as exc:
                self._record_error("réponse Zulip incohérente")
                LOGGER.warning("réponse Zulip incohérente: %s", type(exc).__name__)
                queue_id = None
                self.sleep(backoff)
                backoff = min(self.max_backoff, backoff * 2)
        self.reducer.state.connected = False
        self.reducer.state.error = None
        self.store.write(self.reducer.state)

    def _record_error(self, message: str) -> None:
        self.reducer.state.connected = False
        self.reducer.state.error = message
        self.reducer.state.last_sync = utc_now()
        self.store.write(self.reducer.state)
