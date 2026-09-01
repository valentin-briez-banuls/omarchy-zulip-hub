# Zulip Hub for Omarchy

[Version française](README.fr.md)

Zulip Hub brings unread counters, recent conversations, native notifications,
direct-message composition, and an optional Zulip workspace to the Omarchy
bar. The interface follows the current Omarchy theme and is fully usable with
the keyboard.

![Zulip Hub preview](preview.png)

## Requirements

- Omarchy with the Quattro shell plugin system
- Python 3.11 or newer
- `secret-tool` from libsecret
- A personal Zulip API key

The plugin runs unsandboxed, like every Omarchy shell plugin. It connects only
to the HTTPS Zulip server configured by the user. The API key is sent to the
local helper over standard input and stored in Secret Service; it is never
written to the repository, configuration file, shell state, or process
arguments.

## Install

```sh
omarchy plugin add https://github.com/valentin-briez-banuls/omarchy-zulip-hub.git --enable
```

Open the bar widget and enter the Zulip server URL, account email, and API key.
No terminal is needed after the plugin has been added.

The optional **Omarchy integration** control in Settings adds:

- `Super+Z` — open or close Zulip Hub
- `Super+Shift+Z` — show or hide the dedicated Zulip workspace

The control changes only the user-owned Hyprland configuration under
`~/.config/hypr/` after explicit activation.

## Keyboard controls

- `Tab`, arrows, or `j` / `k` — navigate
- `Enter` — activate or open
- `Ctrl+Enter` — send a direct message
- `X` — mark the selected message as read
- `R` — refresh
- `Escape` — go back or close

## Data and permissions

Zulip Hub creates user-owned data only:

- `~/.config/zulip-hub/config.toml` — identity and preferences, mode `0600`
- `~/.local/state/zulip-hub/` — public counters and control markers
- Secret Service — the personal API key
- optionally `~/.config/hypr/zulip_hub.lua` plus one managed include block

Message bodies and drafts are not persisted. Notification content is redacted
while the session is locked or when lock state cannot be confirmed.

## Remove

First open **Settings → Omarchy integration** and remove the shortcuts. Then:

```sh
omarchy plugin remove io.github.valentin-briez-banuls.zulip-hub
```

Configuration and the keyring entry are preserved deliberately. To erase the
key, use **Edit Zulip account → Disconnect** before removal.

## Development and validation

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
omarchy plugin validate .
tests/run_release_checks.sh
```

Tests never use real Zulip credentials.

## License

MIT © 2026 Valentin Briez-Banuls
