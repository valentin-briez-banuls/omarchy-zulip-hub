from __future__ import annotations

import argparse
import getpass
import json
import logging
from pathlib import Path
import sys

from .api import ZulipClient
from .config import ConfigError, Paths, load_config
from .composer import serve_once as serve_composer_once
from .daemon import BridgeDaemon
from .files import single_instance
from .links import LinkError, summary_url
from .marketplace import IntegrationError, run_action
from .hyprland import HyprlandController, HyprlandError, resolve_launch_command
from .notifications import NotificationCoordinator
from .onboarding import serve_once
from .opening import OpenError, UrlOpener
from .reader import serve_once as serve_reader_once
from .secrets import SecretError, SecretToolProvider
from .state import StateReducer, StateStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="zulip-hub", description="Bridge Zulip local pour Omarchy")
    result.add_argument("--config", type=Path, help="chemin vers config.toml")
    result.add_argument("--state", type=Path, help="chemin vers state.json")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("daemon", help="écouter les événements Zulip")
    sub.add_parser("status", help="afficher l'état local")
    sub.add_parser("check-config", help="valider la configuration")
    sub.add_parser("login", help="enregistrer la clé API dans le trousseau")
    open_url = sub.add_parser("open-url", help="ouvrir une URL Zulip HTTPS")
    open_url.add_argument("url")
    open_message = sub.add_parser("open-message", help="ouvrir un message récent par son identifiant")
    open_message.add_argument("message_id", type=int)
    mark_read = sub.add_parser("mark-read", help="marquer un message comme lu")
    mark_read.add_argument("message_id", type=int)
    sub.add_parser("workspace-toggle", help="afficher, masquer ou lancer le workspace Zulip")
    sub.add_parser("workspace-status", help="diagnostiquer la détection de la fenêtre Zulip")
    sub.add_parser("onboarding", help=argparse.SUPPRESS)
    sub.add_parser("compose", help=argparse.SUPPRESS)
    sub.add_parser("read-message", help=argparse.SUPPRESS)
    os_integration = sub.add_parser("os-integration", help=argparse.SUPPRESS)
    os_integration.add_argument("action", choices=("status", "install", "remove"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    paths = Paths.defaults()
    config_path = args.config or paths.config
    state_path = args.state or paths.state
    try:
        if args.command == "onboarding":
            return serve_once(args.config)
        if args.command == "compose":
            return serve_composer_once(args.config, args.state)
        if args.command == "read-message":
            return serve_reader_once(args.config, args.state)
        if args.command == "os-integration":
            print(json.dumps(
                run_action(Path(__file__).resolve().parents[2], args.action),
                ensure_ascii=False,
            ))
            return 0
        config = load_config(config_path)
        if args.command == "check-config":
            print(f"configuration valide: {config.account.site} ({config.account.email})")
            return 0
        if args.command == "status":
            try:
                print(json.dumps(StateStore(state_path).read(), ensure_ascii=False, indent=2))
                return 0
            except FileNotFoundError:
                print("aucun état disponible; le daemon a-t-il démarré ?", file=sys.stderr)
                return 3
        if args.command == "open-url":
            expected = config.account.site.rstrip("/") + "/#narrow/"
            if not args.url.startswith(expected):
                raise OpenError("l’URL ne correspond pas au serveur Zulip configuré")
            UrlOpener(config.opening).open(args.url)
            return 0
        if args.command == "open-message":
            state = StateStore(state_path).read()
            row = next(
                (item for item in state.get("recent", []) if item.get("id") == args.message_id),
                None,
            )
            if row is None:
                raise OpenError("message absent de l’état récent")
            UrlOpener(config.opening).open(summary_url(config.account.site, row))
            return 0
        if args.command in {"workspace-toggle", "workspace-status"}:
            controller = HyprlandController(
                config.workspace, resolve_launch_command(config)
            )
            if args.command == "workspace-toggle":
                print(controller.toggle())
            else:
                print(json.dumps(controller.status(), ensure_ascii=False, indent=2))
            return 0
        secrets = SecretToolProvider()
        if args.command == "login":
            key = getpass.getpass("Clé API Zulip: ")
            secrets.store(config.account.site, config.account.email, key)
            print("clé enregistrée dans le trousseau")
            return 0
        key = secrets.get(config.account.site, config.account.email)
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        client = ZulipClient(
            config.account.site, config.account.email, key, config.request_timeout_seconds
        )
        if args.command == "mark-read":
            if args.message_id <= 0:
                raise ConfigError("message_id doit être positif")
            client.mark_read([args.message_id])
            print("message marqué comme lu")
            return 0
        notifier = NotificationCoordinator(
            config.account.site, config.account.email, config.notifications
        )
        with single_instance(state_path.parent / "bridge.lock"):
            BridgeDaemon(
                client,
                StateStore(state_path),
                StateReducer(config.recent_message_limit),
                config.initial_backoff_seconds,
                config.max_backoff_seconds,
                notifier=notifier,
            ).run()
        return 0
    except (
        ConfigError, SecretError, OpenError, LinkError, HyprlandError, IntegrationError,
        FileNotFoundError
    ) as exc:
        print(f"erreur: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
