"""Process status file for the watchdog. Never write tokens."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from muse_slack_bridge.redact import redact

STATUS_NAME = "status.json"


def status_path(config_dir: Path) -> Path:
    return Path(config_dir) / STATUS_NAME


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_status(
    config_dir: Path,
    state: str,
    *,
    reason: Optional[str] = None,
    detail: Optional[str] = None,
    pid: Optional[int] = None,
) -> Path:
    path = status_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "state": state,
        "updated_at": utc_now_iso(),
        "pid": pid if pid is not None else os.getpid(),
    }
    if reason:
        payload["reason"] = redact(reason)
    if detail:
        payload["detail"] = redact(detail)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_status(config_dir: Path) -> Optional[Dict[str, Any]]:
    path = status_path(config_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def parse_updated_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
