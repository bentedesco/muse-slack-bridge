#!/bin/sh
# Cron fallback when a user systemd unit is not available.
# Suggested crontab:
#   @reboot /path/to/muse-slack-bridge/contrib/healthcheck.sh
#   */5 * * * * /path/to/muse-slack-bridge/contrib/healthcheck.sh
#
# Exit 0: listener is healthy or was restarted after a crash.
# Exit 2: local config is invalid — do not retry until files are fixed.
# Exit 3: Slack rejected auth — reissue tokens, then start slackd again.
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/env python3 "$DIR/healthcheck.py"
