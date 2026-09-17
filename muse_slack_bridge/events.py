"""Filter Slack message events and append them to the shared JSONL log."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

ALLOWED_SUBTYPES = {None, "thread_broadcast", "bot_message"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def should_record(
    event: Dict[str, Any],
    watch_channels: Set[str],
    own_bot_id: Optional[str] = None,
    own_user_id: Optional[str] = None,
) -> bool:
    """Keep watched-channel messages, including other bots; skip our own posts."""
    if event.get("type") != "message":
        return False
    if event.get("channel") not in watch_channels:
        return False
    if event.get("subtype") not in ALLOWED_SUBTYPES:
        return False
    if own_bot_id and event.get("bot_id") == own_bot_id:
        return False
    if own_user_id and event.get("user") == own_user_id:
        return False
    return True


def to_record(event: Dict[str, Any], received_at: Optional[str] = None) -> Dict[str, Any]:
    thread_ts = event.get("thread_ts") or None
    return {
        "ts": event.get("ts"),
        "thread_ts": thread_ts,
        "user": event.get("user"),
        "text": event.get("text") or "",
        "channel": event.get("channel"),
        "received_at": received_at or utc_now_iso(),
    }


def append_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
