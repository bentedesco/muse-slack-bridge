from __future__ import annotations

import json
from pathlib import Path

from muse_slack_bridge.events import append_record, should_record, to_record
from muse_slack_bridge.listener import Identity, record_event
from muse_slack_bridge.redact import redact

WATCH = {"C1111111111"}
OWN = "B0000000001"
OWN_USER = "U0000000001"


def _msg(**overrides):
    event = {
        "type": "message",
        "subtype": None,
        "channel": "C1111111111",
        "user": "U9999999999",
        "text": "hello",
        "ts": "1710000000.000100",
    }
    event.update(overrides)
    return event


def test_records_plain_message_in_watched_channel() -> None:
    assert should_record(_msg(), WATCH, OWN, OWN_USER) is True


def test_records_thread_broadcast() -> None:
    assert should_record(_msg(subtype="thread_broadcast", thread_ts="1710000000.000050"), WATCH, OWN, OWN_USER)


def test_skips_other_subtypes() -> None:
    assert should_record(_msg(subtype="message_changed"), WATCH, OWN, OWN_USER) is False
    assert should_record(_msg(subtype="message_deleted"), WATCH, OWN, OWN_USER) is False


def test_records_other_bots_bot_message() -> None:
    assert should_record(_msg(subtype="bot_message", bot_id="B9999999999", user="U8888888888"), WATCH, OWN, OWN_USER) is True


def test_skips_own_bot_message() -> None:
    assert should_record(_msg(subtype="bot_message", bot_id=OWN), WATCH, OWN, OWN_USER) is False


def test_skips_unwatched_channel() -> None:
    assert should_record(_msg(channel="C9999999999"), WATCH, OWN, OWN_USER) is False


def test_skips_own_bot_id_and_user_id() -> None:
    assert should_record(_msg(bot_id=OWN, user=OWN_USER), WATCH, OWN, OWN_USER) is False
    assert should_record(_msg(user=OWN_USER), WATCH, OWN, OWN_USER) is False


def test_record_shape_and_jsonl_append(tmp_path: Path) -> None:
    event = _msg(thread_ts="1710000000.000050")
    record = to_record(event, received_at="2026-09-17T17:00:00Z")
    assert record == {
        "ts": "1710000000.000100",
        "thread_ts": "1710000000.000050",
        "user": "U9999999999",
        "text": "hello",
        "channel": "C1111111111",
        "received_at": "2026-09-17T17:00:00Z",
    }
    path = tmp_path / "events.jsonl"
    append_record(path, record)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "hello"


def test_record_event_writes_only_when_matched(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    identity = Identity(bot_id=OWN, user_id=OWN_USER)
    assert record_event(_msg(), WATCH, identity, path) is True
    assert record_event(_msg(bot_id=OWN), WATCH, identity, path) is False
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_redact_strips_token_shapes() -> None:
    leaked = "failed xoxb-123-456-abcdef and xapp-1-2-3"
    assert "xoxb-" not in redact(leaked)
    assert "xapp-" not in redact(leaked)
    assert "[redacted]" in redact(leaked)
