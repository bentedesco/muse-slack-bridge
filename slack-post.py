#!/usr/bin/env python3
"""Shared post CLI. Posts text verbatim — callers add their own prefixes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from muse_slack_bridge.config import Config, ConfigError
from muse_slack_bridge.post import PostError, post_message
from muse_slack_bridge.redact import redact


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post a message through Muse Slack Bridge.")
    parser.add_argument("--text", required=True, help="Message body (posted unchanged)")
    parser.add_argument("--thread-ts", help="Parent message ts for a thread reply")
    parser.add_argument("--channel", help="Channel ID (defaults to SLACK_DEFAULT_CHANNEL or first watch channel)")
    parser.add_argument("--config-dir", type=Path, help="Override config directory")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = Config.load(config_dir=args.config_dir, require_app_token=False)
        channel = args.channel or config.default_channel
        result = post_message(
            bot_token=config.bot_token,
            channel=channel,
            text=args.text,
            thread_ts=args.thread_ts,
        )
    except (ConfigError, PostError) as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
