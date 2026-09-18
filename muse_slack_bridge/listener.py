"""Socket Mode listener: ack every envelope, append matching messages."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path
from threading import Event
from typing import Any, Callable, Optional, Set

from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web import WebClient

from muse_slack_bridge.config import Config, ConfigError, default_config_dir
from muse_slack_bridge.errors import EXIT_ERROR, EXIT_OK, ClassifiedError, classify
from muse_slack_bridge.events import append_record, should_record, to_record
from muse_slack_bridge.redact import redact
from muse_slack_bridge.status import write_status


class Identity:
    def __init__(self, bot_id: Optional[str], user_id: Optional[str]) -> None:
        self.bot_id = bot_id
        self.user_id = user_id


class AuthRejected(Exception):
    def __init__(self, classified: ClassifiedError) -> None:
        super().__init__(classified.message)
        self.classified = classified


def fetch_identity(web: WebClient) -> Identity:
    auth = web.auth_test()
    return Identity(bot_id=auth.get("bot_id"), user_id=auth.get("user_id"))


def probe_tokens(web: WebClient, app_token: str) -> Identity:
    """Fail fast if Slack will refuse the Socket Mode handshake."""
    try:
        identity = fetch_identity(web)
    except Exception as exc:  # noqa: BLE001
        classified = classify(exc)
        if classified.kind == "auth":
            raise AuthRejected(classified) from exc
        raise
    try:
        web.apps_connections_open(app_token=app_token)
    except Exception as exc:  # noqa: BLE001
        classified = classify(exc)
        if classified.kind == "auth":
            raise AuthRejected(classified) from exc
        raise
    return identity


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


def _print_classified(classified: ClassifiedError) -> None:
    print(redact(f"{classified.kind} rejected: {classified.code or classified.kind}"), file=sys.stderr)
    print(redact(classified.message), file=sys.stderr)
    print("not retrying; update tokens or config, then start slackd again", file=sys.stderr)


def _fail_status(config: Config, classified: ClassifiedError) -> int:
    state = "auth_rejected" if classified.kind == "auth" else "config_error"
    if classified.kind == "transient":
        state = "error"
    write_status(
        config.config_dir,
        state,
        reason=classified.code or classified.kind,
        detail=classified.message,
    )
    _print_classified(classified)
    return classified.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Shared Slack Socket Mode listener. Writes events.jsonl for all bots."
    )
    parser.add_argument("--config-dir", type=Path, help="Override config directory")
    parser.add_argument("--events", type=Path, help="Override events.jsonl path")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate local tokens and channels, then exit",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Call Slack auth.test and apps.connections.open, then exit",
    )
    return parser


def run_listener(
    config: Config,
    *,
    web: Optional[WebClient] = None,
    client_factory: Optional[Callable[[str, WebClient], SocketModeClient]] = None,
    stop: Optional[Event] = None,
    heartbeat_seconds: float = 30.0,
) -> int:
    assert config.app_token is not None
    client_web = web or WebClient(token=config.bot_token)
    try:
        identity = probe_tokens(client_web, config.app_token)
    except AuthRejected as exc:
        return _fail_status(config, exc.classified)
    except Exception as exc:  # noqa: BLE001
        print(redact(f"Slack probe failed: {exc}"), file=sys.stderr)
        write_status(config.config_dir, "error", reason="probe_failed", detail=str(exc))
        return EXIT_ERROR

    watch = set(config.watch_channels)
    factory = client_factory or (lambda app_token, web_client: SocketModeClient(app_token=app_token, web_client=web_client))
    client = factory(config.app_token, client_web)
    stop_event = stop or Event()
    fatal: list[ClassifiedError] = []
    saw_hello = {"ok": False}

    def process(socket_client: SocketModeClient, req: SocketModeRequest) -> None:
        try:
            handle_socket_request(req, socket_client, watch, identity, config.events_path)
            write_status(config.config_dir, "listening")
        except Exception as exc:  # noqa: BLE001 — listener must stay up
            print(redact(f"event handler error: {exc}"), file=sys.stderr)

    def on_ws_message(message: str) -> None:
        try:
            payload = json.loads(message) if message.startswith("{") else {}
        except json.JSONDecodeError:
            return
        if payload.get("type") == "hello":
            saw_hello["ok"] = True
            write_status(config.config_dir, "listening")

    def mark_fatal(exc: BaseException) -> None:
        classified = classify(exc)
        if classified.kind != "auth":
            return
        fatal.append(classified)
        try:
            client.auto_reconnect_enabled = False
        except Exception:  # noqa: BLE001
            pass
        stop_event.set()

    def on_error(error: Exception) -> None:
        print(redact(f"socket error: {error}"), file=sys.stderr)
        mark_fatal(error)

    def on_close(_code: int, reason: Optional[str] = None) -> None:
        if saw_hello["ok"]:
            write_status(config.config_dir, "reconnecting", reason="socket_close", detail=reason or "")
            return
        try:
            probe_tokens(client_web, config.app_token or "")
        except AuthRejected as exc:
            mark_fatal(exc)
            return
        except Exception as exc:  # noqa: BLE001
            print(redact(f"handshake close probe failed: {exc}"), file=sys.stderr)

    client.socket_mode_request_listeners.append(process)
    if hasattr(client, "on_message_listeners"):
        client.on_message_listeners.append(on_ws_message)
    if hasattr(client, "on_error_listeners"):
        client.on_error_listeners.append(on_error)
    if hasattr(client, "on_close_listeners"):
        client.on_close_listeners.append(on_close)

    print(
        f"listening channels={','.join(config.watch_channels)} events={config.events_path}",
        file=sys.stderr,
    )
    try:
        client.connect()
    except Exception as exc:  # noqa: BLE001
        classified = classify(exc)
        if classified.kind == "auth":
            return _fail_status(config, classified)
        print(redact(f"socket mode error: {exc}"), file=sys.stderr)
        write_status(config.config_dir, "error", reason=classified.code or "connect", detail=str(exc))
        return EXIT_ERROR

    write_status(config.config_dir, "listening")

    def _handle_stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    try:
        signal.signal(signal.SIGTERM, _handle_stop)
    except Exception:  # noqa: BLE001 — not available on all platforms
        pass

    try:
        while not stop_event.is_set():
            if fatal:
                return _fail_status(config, fatal[-1])
            write_status(
                config.config_dir,
                "listening" if getattr(client, "is_connected", lambda: True)() else "reconnecting",
            )
            stop_event.wait(heartbeat_seconds)
        if fatal:
            return _fail_status(config, fatal[-1])
        write_status(config.config_dir, "stopped")
        return EXIT_OK
    except KeyboardInterrupt:
        write_status(config.config_dir, "stopped")
        return EXIT_OK
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.load(config_dir=args.config_dir, events_path=args.events)
    except ConfigError as exc:
        classified = classify(exc)
        print(redact(str(exc)), file=sys.stderr)
        try:
            write_status(
                args.config_dir or default_config_dir(),
                "config_error",
                reason="config",
                detail=str(exc),
            )
        except Exception:  # noqa: BLE001
            pass
        return classified.exit_code

    if args.check_config:
        print(
            f"ok config_dir={config.config_dir} events={config.events_path} "
            f"channels={','.join(config.watch_channels)}"
        )
        return EXIT_OK

    if args.probe:
        web = WebClient(token=config.bot_token)
        try:
            probe_tokens(web, config.app_token or "")
        except AuthRejected as exc:
            return _fail_status(config, exc.classified)
        except Exception as exc:  # noqa: BLE001
            print(redact(f"Slack probe failed: {exc}"), file=sys.stderr)
            write_status(config.config_dir, "error", reason="probe_failed", detail=str(exc))
            return EXIT_ERROR
        write_status(config.config_dir, "probe_ok")
        print(
            f"ok probe config_dir={config.config_dir} channels={','.join(config.watch_channels)}"
        )
        return EXIT_OK

    return run_listener(config)
