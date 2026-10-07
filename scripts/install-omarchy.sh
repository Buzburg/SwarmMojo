#!/usr/bin/env bash
# Native Omarchy Linux / Arch XDG Desktop & Systemd Installer
# Ported from AeonHarness packaging architecture.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/omarchy"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}"

install -d "$HOME/.local/bin" "$config_dir/systemd/user" "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
install -m755 "$root/packaging/omarchy-menu" "$HOME/.local/bin/omarchy-menu"
install -m644 "$root/packaging/omarchy.desktop" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/omarchy.desktop"
install -m644 "$root/packaging/omarchy-model@.service" "$config_dir/systemd/user/omarchy-model@.service"

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload || true
fi

printf '%s\n' \
    "Installed Omarchy Desktop & Systemd user integration." \
    "  - Launcher: ~/.local/bin/omarchy-menu" \
    "  - Desktop Entry: ${XDG_DATA_HOME:-$HOME/.local/share}/applications/omarchy.desktop" \
    "  - Systemd Template: $config_dir/systemd/user/omarchy-model@.service"
