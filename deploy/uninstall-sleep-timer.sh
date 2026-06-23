#!/usr/bin/env bash
# Remove the systemd user timer installed by install-sleep-timer.sh.
set -euo pipefail

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

systemctl --user disable --now personal-llm-sleep.timer 2>/dev/null || true
rm -f "$UNIT_DIR/personal-llm-sleep.timer" "$UNIT_DIR/personal-llm-sleep.service"
systemctl --user daemon-reload

echo "Removed personal-llm-sleep timer and service."
echo "(Lingering, if you enabled it, is left as-is: loginctl disable-linger \"$USER\")"
