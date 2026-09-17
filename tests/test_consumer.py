from __future__ import annotations

import json
from pathlib import Path

import pytest

from muse_slack_bridge.consumer import iter_new_events, offset_path, read_offset, write_offset


def _write_events(path: Path, texts: list[str]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for text in texts:
            handle.write(json.dumps({"text": text}) + "\n")


def test_first_event_is_processed_when_offset_missing(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    _write_events(events, ["one", "two"])
    seen = list(iter_new_events(events, read_offset(tmp_path / "bot.offset")))
    assert [item[1]["text"] for item in seen] == ["one", "two"]
    assert [item[0] for item in seen] == [0, 1]


def test_offset_skips_already_processed_lines(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    offset = tmp_path / "bot.offset"
    _write_events(events, ["one", "two", "three"])
    write_offset(offset, 0)
    seen = list(iter_new_events(events, read_offset(offset)))
    assert [item[1]["text"] for item in seen] == ["two", "three"]


def test_two_consumers_each_see_every_event_once(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    _write_events(events, ["a", "b"])
    alpha = tmp_path / "alpha.offset"
    beta = tmp_path / "beta.offset"
    assert [e["text"] for _, e in iter_new_events(events, read_offset(alpha))] == ["a", "b"]
    write_offset(alpha, 1)
    assert [e["text"] for _, e in iter_new_events(events, read_offset(beta))] == ["a", "b"]
    write_offset(beta, 1)
    _write_events(events, ["a", "b", "c"])
    assert [e["text"] for _, e in iter_new_events(events, read_offset(alpha))] == ["c"]
    assert [e["text"] for _, e in iter_new_events(events, read_offset(beta))] == ["c"]


def test_partial_last_line_is_not_consumed(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"text":"ok"}\n{"text":', encoding="utf-8")
    seen = list(iter_new_events(events, -1))
    assert [item[1]["text"] for item in seen] == ["ok"]


def test_offset_path_rejects_unsafe_names(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        offset_path(tmp_path, "../escape")
