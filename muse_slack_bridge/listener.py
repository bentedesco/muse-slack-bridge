"""Socket Mode listener: ack every envelope, append matching messages."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from threading import Event
from typing import Any, Optional, Set

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from muse_slack_bridge.config import Config, ConfigError
from muse_slack_bridge.events import append_record, should_record, to_record
from muse_slack_bridge.redact import redact


class Identity:
    def __init__(self, bot_id: Optional[str], user_id: Optional[str]) -> None:
        self.bot_id = bot_id
        self.user_id = user_id


def fetch_identity(web: WebClient) -> Identity:
    auth = web.auth_test()
    return Identity(bot_id=auth.get("bot_id"), user_id=auth.get("user_id"))


def record_event(
    event: Any,
    watch_channels: Set[str],
    identity: Identity,
    events_path: Path,
) -> bool:
    if not isinstance(event, dict):
        return False
    if not should_record(event, watch_channels, identity.bot_id, identity.user_id):
        return False
    append_record(events_path, to_record(event))
    return True


def handle_socket_request(
    req: SocketModeRequest,
    client: SocketModeClient,
    watch_channels: Set[str],
    identity: Identity,
    events_path: Path,
) -> None:
    # Ack every envelope first so Slack does not retry on slow disk writes.
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    if req.type != "events_api":
        return
    payload = req.payload if isinstance(req.payload, dict) else {}
    event = payload.get("event")
    record_event(event, watch_channels, identity, events_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shared Slack Socket Mode listener. Writes events.jsonl for all bots."
    )
    parser.add_argument("--config-dir", type=Path, help="Override config directory")
    parser.add_argument("--events", type=Path, help="Override events.jsonl path")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate tokens and channels, then exit",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.load(config_dir=args.config_dir, events_path=args.events)
    except ConfigError as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 1

    if args.check_config:
        print(
            f"ok config_dir={config.config_dir} events={config.events_path} "
            f"channels={','.join(config.watch_channels)}"
        )
        return 0

    assert config.app_token is not None
    web = WebClient(token=config.bot_token)
    try:
        identity = fetch_identity(web)
    except Exception as exc:  # noqa: BLE001 — surface Slack/network errors, redacted
        print(redact(f"auth.test failed: {exc}"), file=sys.stderr)
        return 1

    watch = set(config.watch_channels)
    client = SocketModeClient(app_token=config.app_token, web_client=web)

    def process(socket_client: SocketModeClient, req: SocketModeRequest) -> None:
        try:
            handle_socket_request(req, socket_client, watch, identity, config.events_path)
        except Exception as exc:  # noqa: BLE001 — listener must stay up
            print(redact(f"event handler error: {exc}"), file=sys.stderr)

    client.socket_mode_request_listeners.append(process)
    print(
        f"listening channels={','.join(config.watch_channels)} events={config.events_path}",
        file=sys.stderr,
    )
    try:
        client.connect()
        Event().wait()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        print(redact(f"socket mode error: {exc}"), file=sys.stderr)
        return 1
    return 0
