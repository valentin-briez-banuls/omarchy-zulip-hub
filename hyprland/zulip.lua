-- Omarchy Zulip Hub — Hyprland integration.
-- Loaded from the user's hyprland.lua after the Omarchy defaults.

local zulip_workspace = "zulip"
local zulip_class = "^(Zulip|zulip|zulip-hub|org\\.zulip\\.Zulip)$"

-- Keep the Zulip client on its dedicated special workspace. `workspace` is a
-- static rule, so matching the launch-time class is intentional.
o.window(zulip_class, {
  workspace = "special:" .. zulip_workspace .. " silent",
  focus_on_activate = false,
})

hl.workspace_rule({
  workspace = "special:" .. zulip_workspace,
  persistent = true,
})

-- SUPER+Z used to toggle the workspace in Zulip Hub <= 1.1. Unbind that
-- managed shortcut before assigning the panel-first keyboard workflow.
hl.unbind("SUPER + Z")
o.bind(
  "SUPER + Z",
  "Zulip Hub",
  "omarchy-shell io.github.valentin-briez-banuls.zulip-hub toggle"
)

o.bind(
  "SUPER + SHIFT + Z",
  "Zulip workspace",
  "omarchy-shell io.github.valentin-briez-banuls.zulip-hub workspaceToggle"
)
