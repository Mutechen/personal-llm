#!/usr/bin/env bash
# Install the systemd *user* timer that runs the nightly sleep-time loop.
#
# Portable: works from any clone. `Persistent=true` means a run missed because
# the machine was asleep at 03:00 fires on next wake. If you run from a source
# checkout via uv (e.g. exFAT), export UV_PROJECT_ENVIRONMENT first and it is
# baked into the unit.
#
#   ./deploy/install-sleep-timer.sh
#
# Uninstall with deploy/uninstall-sleep-timer.sh.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"

chmod +x "$REPO/deploy/run-sleep.sh"
EXEC="$REPO/deploy/run-sleep.sh"

# Carry the exFAT/uv venv override into the unit if the caller has it set.
ENVIRON=""
if [ -n "${UV_PROJECT_ENVIRONMENT:-}" ]; then
  ENVIRON="Environment=UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT}"
fi

sed -e "s#@EXEC@#${EXEC}#g" -e "s#@ENVIRON@#${ENVIRON}#g" \
  "$REPO/deploy/systemd/personal-llm-sleep.service.in" \
  > "$UNIT_DIR/personal-llm-sleep.service"
cp "$REPO/deploy/systemd/personal-llm-sleep.timer" "$UNIT_DIR/personal-llm-sleep.timer"
# Unit files copied off an exec-everything mount (exFAT) keep an exec bit that
# makes systemd warn; clear it.
chmod 644 "$UNIT_DIR/personal-llm-sleep.service" "$UNIT_DIR/personal-llm-sleep.timer"

systemctl --user daemon-reload
systemctl --user enable --now personal-llm-sleep.timer

# Let the timer fire even when no graphical session is logged in. Best-effort;
# may prompt for authentication or be disallowed on locked-down systems.
loginctl enable-linger "$USER" 2>/dev/null \
  || echo "note: could not enable lingering; the timer runs only while you are logged in."

echo
echo "Installed personal-llm-sleep.timer. Next run:"
systemctl --user list-timers personal-llm-sleep.timer --no-pager || true
echo
echo "Run once now to test:  systemctl --user start personal-llm-sleep.service"
echo "Watch the log:         journalctl --user -u personal-llm-sleep.service -e"
