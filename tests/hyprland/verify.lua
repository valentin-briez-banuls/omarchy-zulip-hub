-- Minimal Hyprland config used to validate the project module with the same
-- Omarchy bootstrap as a real user session.
dofile((os.getenv("OMARCHY_PATH") or "/usr/share/omarchy") .. "/default/hypr/bootstrap.lua")
require("default.hypr.helpers")
dofile(assert(os.getenv("ZULIP_HUB_HYPR_MODULE"), "missing ZULIP_HUB_HYPR_MODULE"))
