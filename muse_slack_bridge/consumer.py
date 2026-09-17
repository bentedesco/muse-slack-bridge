"""Per-bot offset helpers so many consumers can share one event log."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

log = logging.getLogger(__name__)


def offset_path(config_dir: Path, bot_name: str) -> Path:
    if not bot_name or "/" in bot_name or bot_name in {".", ".."}:
        raise ValueError("bot name must be a simple filename stem")
    return config_dir / f"{bot_name}.offset"


def read_offset(path: Path) -> int:
    """Return the last processed line index, or -1 if none have been read."""
    if not path.is_file():
        return -1
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return -1
    return int(text)


def write_offset(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"{value}\n", encoding="utf-8")
    tmp.replace(path)


def iter_new_events(
    events_path: Path, last_index: int
) -> Iterator[Tuple[int, Optional[Dict[str, Any]]]]:
    """Yield (line_index, event) for complete JSONL lines after last_index.

    A complete line that is not valid JSON yields ``(index, None)`` so callers
    can advance the offset instead of stalling forever. A truncated last line
    (no trailing newline) is left for the next read.
    """
    if not events_path.is_file():
        return
    with events_path.open("r", encoding="utf-8") as handle:
        for index, raw in enumerate(handle):
            if index <= last_index:
                continue
            line = raw.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                if not raw.endswith("\n"):
                    return
                log.warning("skipping corrupt JSONL line %s in %s", index, events_path)
                yield index, None
                continue
            if not isinstance(parsed, dict):
                log.warning("skipping non-object JSONL line %s in %s", index, events_path)
                yield index, None
                continue
            yield index, parsed
