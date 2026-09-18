"""Decide whether a dead listener should be revived or left down."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from muse_slack_bridge.status import parse_updated_at

DEFAULT_STALE_SECONDS = 300


@dataclass(frozen=True)
class WatchdogDecision:
    action: str  # ok | restart | hold
    exit_code: int
    message: str


def decide(
    *,
    process_running: bool,
    status: Optional[Dict[str, Any]],
    now: Optional[datetime] = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
    running_pid: Optional[int] = None,
) -> WatchdogDecision:
    """Return what healthcheck should do. Never restarts after Slack auth rejection."""
    clock = now or datetime.now(timezone.utc)
    state = (status or {}).get("state")
    reason = (status or {}).get("reason") or state or "unknown"
    detail = (status or {}).get("detail") or ""

    if state == "auth_rejected":
        return WatchdogDecision(
            action="hold",
            exit_code=3,
            message=f"not restarting: Slack rejected auth ({reason}). {detail}".strip(),
        )
    if state == "config_error":
        return WatchdogDecision(
            action="hold",
            exit_code=2,
            message=f"not restarting: config error ({reason}). {detail}".strip(),
        )

    if process_running:
        updated = parse_updated_at((status or {}).get("updated_at"))
        status_pid = (status or {}).get("pid")
        pid_matches = running_pid is None or status_pid is None or int(status_pid) == int(running_pid)
        if (
            updated is not None
            and pid_matches
            and (clock - updated).total_seconds() > stale_seconds
        ):
            return WatchdogDecision(
                action="restart",
                exit_code=0,
                message=f"listener process is up but status is stale ({int((clock - updated).total_seconds())}s); restarting",
            )
        return WatchdogDecision(action="ok", exit_code=0, message="listener is running")

    return WatchdogDecision(action="restart", exit_code=0, message="listener is not running; starting")
