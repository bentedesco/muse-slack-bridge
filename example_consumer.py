#!/usr/bin/env python3
"""Reference per-bot consumer.

Each bot keeps its own offset file and applies its own rules. The bridge
never interprets prefixes or reply policy — copy this loop and replace
`apply_bot_rules`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from muse_slack_bridge.config import default_config_dir
from muse_slack_bridge.consumer import iter_new_events, offset_path, read_offset, write_offset
from muse_slack_bridge.redact import redact


def apply_bot_rules(event: Dict[str, Any], args: argparse.Namespace) -> Optional[Dict[str, str]]:
    """Return a slack-post payload, or None to skip.

    Demo rule (off unless --echo-ping): reply PONG in-thread to a bare PING.
    Replace this function with the calling bot's own filters.
    """
    text = (event.get("text") or "").strip()
    if args.echo_ping and text == "PING":
        return {
            "text": "PONG",
            "channel": event["channel"],
            "thread_ts": event.get("thread_ts") or event.get("ts") or "",
        }
    if args.print_events:
        print(json.dumps(event, separators=(",", ":")), flush=True)
    return None


def post_via_cli(payload: Dict[str, str], config_dir: Path) -> None:
    command = [
        sys.executable,
        str(ROOT / "slack-post.py"),
        "--text",
        payload["text"],
        "--channel",
        payload["channel"],
        "--config-dir",
        str(config_dir),
    ]
    if payload.get("thread_ts"):
        command.extend(["--thread-ts", payload["thread_ts"]])
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError("slack-post.py failed")


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    config_dir = Path(args.config_dir) if args.config_dir else default_config_dir()
    if args.events:
        events_path = Path(args.events)
    else:
        override = os.environ.get("MUSE_SLACK_BRIDGE_EVENTS", "").strip()
        events_path = Path(override).expanduser() if override else config_dir / "events.jsonl"
    return config_dir, events_path


def consume_once(args: argparse.Namespace, config_dir: Path, events_path: Path) -> int:
    path = offset_path(config_dir, args.name)
    last = read_offset(path)
    processed = 0
    for index, event in iter_new_events(events_path, last):
        if event is not None:
            payload = apply_bot_rules(event, args)
            if payload and not args.dry_run:
                post_via_cli(payload, config_dir)
        last = index
        write_offset(path, last)
        processed += 1
    return processed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Example per-bot events.jsonl consumer.")
    parser.add_argument("--name", required=True, help="Bot name; used as the offset filename stem")
    parser.add_argument("--config-dir", type=Path, help="Override config directory")
    parser.add_argument("--events", type=Path, help="Override events.jsonl path")
    parser.add_argument("--once", action="store_true", help="Process new lines once and exit")
    parser.add_argument("--interval", type=int, default=120, help="Seconds between polls (default 120)")
    parser.add_argument("--echo-ping", action="store_true", help="Reply PONG to messages that are exactly PING")
    parser.add_argument("--dry-run", action="store_true", help="Apply rules but do not post")
    parser.add_argument("--quiet", action="store_true", help="Do not print unhandled events")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    args.print_events = not args.quiet
    config_dir, events_path = resolve_paths(args)
    try:
        if args.once:
            consume_once(args, config_dir, events_path)
            return 0
        while True:
            consume_once(args, config_dir, events_path)
            time.sleep(max(args.interval, 1))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        print(redact(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
