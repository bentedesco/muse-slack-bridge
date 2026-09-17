# Muse Slack Bridge

Shared, bot-agnostic transport between Slack and Muse AI bots.

One listener daemon (`slackd.py`) receives Slack events over Socket Mode and appends them to `events.jsonl`. One post CLI (`slack-post.py`) sends text back, verbatim. Bots never talk to Slack or a browser. Each bot runs its own consumer over the shared log, with its own offset file and its own rules.

The bridge knows nothing about any particular bot's prefixes, reply policy, or conventions.

There is no public HTTP endpoint. Socket Mode does not need one.

## Layout

```
slackd.py              # shared listener → events.jsonl
slack-post.py          # shared post CLI
example_consumer.py    # reference per-bot loop (~offset + rules)
manifest.json          # Slack app manifest
contrib/               # systemd user unit + cron healthcheck
muse_slack_bridge/     # library used by the scripts
```

## One-time Slack app setup

1. Open [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From an app manifest**.
2. Paste `manifest.json` from this repo and create the app.
3. **Basic Information** → **App-Level Tokens** → generate a token with the `connections:write` scope. Copy the `xapp-` value.
4. **OAuth & Permissions** → **Install to Workspace**. Copy the bot token (`xoxb-`).
5. Invite the app to every channel it should see (`/invite @Muse Bridge`). Private channels are invisible until invited.

The committed manifest enables Socket Mode and subscribes to `message.groups` only (`chat:write`, `groups:history`, `groups:read`, `users:read`). Invite the app into each private channel it should see. It does not include a request URL or interactivity.

## Configure

Tokens live in the process environment **or** in chmod-600 files. Never commit them. Never paste them into chat.

Default config directory: `~/.config/muse-slack-bridge/`  
Override with `MUSE_SLACK_BRIDGE_HOME` or `--config-dir`.

```bash
mkdir -p ~/.config/muse-slack-bridge
chmod 700 ~/.config/muse-slack-bridge

# Option A — environment
export SLACK_APP_TOKEN="xapp-..."
export SLACK_BOT_TOKEN="xoxb-..."
export WATCH_CHANNELS="C0123456789,C9876543210"

# Option B — files (must be chmod 600 or the listener refuses to start)
printf '%s\n' "$SLACK_APP_TOKEN" > ~/.config/muse-slack-bridge/app_token
printf '%s\n' "$SLACK_BOT_TOKEN" > ~/.config/muse-slack-bridge/bot_token
printf '%s\n' "$WATCH_CHANNELS" > ~/.config/muse-slack-bridge/channels
chmod 600 ~/.config/muse-slack-bridge/app_token ~/.config/muse-slack-bridge/bot_token
```

| Setting | Env | File | Required |
| --- | --- | --- | --- |
| App-level token | `SLACK_APP_TOKEN` | `app_token` | listener |
| Bot token | `SLACK_BOT_TOKEN` | `bot_token` | listener and post |
| Channel IDs | `WATCH_CHANNELS` | `channels` | yes — no default |
| Event log | `MUSE_SLACK_BRIDGE_EVENTS` | `events.jsonl` | created automatically |
| Default post channel | `SLACK_DEFAULT_CHANNEL` | — | optional; otherwise first watch channel |

Use Slack channel IDs (`C…` or `G…`), not `#names`. There is no hardcoded workspace or channel.

Env vars win over files. If a token file is used, it must be mode `600`.

## Install and run the listener

```bash
python3 -m pip install -r requirements.txt
python3 slackd.py --check-config
python3 slackd.py
```

On each Socket Mode envelope the listener:

1. Acknowledges immediately.
2. Keeps `message` events whose channel is watched and whose subtype is empty, `thread_broadcast`, or `bot_message` (so other bots' posts are visible).
3. Drops its own posts (`auth.test` bot id / user id) so a reply cannot re-trigger the log.
4. Appends one JSON line to `events.jsonl` and fsyncs.

```json
{"ts":"1710000000.000100","thread_ts":null,"user":"U0123456789","text":"hello","channel":"C0123456789","received_at":"2026-09-17T17:00:00.000000Z"}
```

Errors go to stderr. Token-shaped strings are redacted. The Slack SDK reconnects if the websocket drops.

## Post

```bash
python3 slack-post.py --text "PING"
python3 slack-post.py --text "reply" --thread-ts 1710000000.000100 --channel C0123456789
```

The bridge adds no prefix. Each calling bot prepends its own label if it wants one. Success prints `{"ok":true,"ts":"..."}` and exits 0.

## Per-bot consumer

Each bot owns its loop and its offset file. Offsets are never shared.

```
~/.config/muse-slack-bridge/<bot-name>.offset
```

The offset is the last processed **line index**. A missing file is treated as `-1`, so the first log line is not skipped. A complete line that is not valid JSON yields `None` and is logged so the offset can still advance; a truncated last line is left for the next read.

```python
from muse_slack_bridge.consumer import iter_new_events, offset_path, read_offset, write_offset

offset_file = offset_path(config_dir, "my-bot")
last = read_offset(offset_file)
for index, event in iter_new_events(events_path, last):
    if event is not None:
        apply_this_bots_rules(event)
    write_offset(offset_file, index)
```

Reference CLI (print new events; optional PING → PONG for a smoke test):

```bash
python3 example_consumer.py --name my-bot --once --dry-run
# cron every 2 minutes:
# */2 * * * * python3 /path/to/muse-slack-bridge/example_consumer.py --name my-bot --once
```

Two bots with two offset files each see every event exactly once.

## Deploy

User systemd unit (`contrib/muse-slack-bridge.service`). Edit `WorkingDirectory` / `ExecStart` if the clone is not `$HOME/muse-slack-bridge`:

```bash
mkdir -p ~/.config/systemd/user
cp contrib/muse-slack-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now muse-slack-bridge.service
```

Fallback when systemd is unavailable: `@reboot` plus a 5-minute cron calling `contrib/healthcheck.sh`. That script starts `slackd.py` only if it is not already running.

## Verify

- A test message in a watched channel appears in `events.jsonl` within a few seconds, with the correct `ts`, `thread_ts`, and `text`.
- `slack-post.py --text "PING"` is visible in the channel.
- A `--thread-ts` reply lands in the same thread.
- The bot's own posts do not appear again in the log.
- Killing the network connection and restoring it does not require a manual restart (SDK reconnect; systemd `Restart=always` covers process death).
- Two consumers with separate offset files each process every new line once.

## Security

- Tokens exist only in `~/.config/muse-slack-bridge/` (mode `600`) or process env. They are never logged and never stored in git.
- If a token leaks, rotate it at [api.slack.com/apps](https://api.slack.com/apps) and rewrite the local files.
- The app can only see private channels it has been invited to.
- No inbound HTTP listener is opened.

## Development

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

## License

MIT
