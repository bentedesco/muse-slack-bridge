#!/bin/sh
# Cron fallback when a user systemd unit is not available.
# Suggested crontab:
#   @reboot /path/to/muse-slack-bridge/contrib/healthcheck.sh
#   */5 * * * * /path/to/muse-slack-bridge/contrib/healthcheck.sh
set -eu

ROOT="${MUSE_SLACK_BRIDGE_ROOT:-$HOME/muse-slack-bridge}"
CONFIG_DIR="${MUSE_SLACK_BRIDGE_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/muse-slack-bridge}"
LOG="$CONFIG_DIR/slackd.log"

if pgrep -f "[s]lackd.py" >/dev/null 2>&1; then
  exit 0
fi

mkdir -p "$CONFIG_DIR"
# Redirect only the listener's stderr/stdout. The listener never prints tokens.
nohup /usr/bin/env python3 "$ROOT/slackd.py" >>"$LOG" 2>&1 &
exit 0
