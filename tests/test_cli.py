from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_config_ok(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_APP_TOKEN": "xapp-test",
            "WATCH_CHANNELS": "C1111111111",
        }
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "slackd.py"), "--config-dir", str(tmp_path), "--check-config"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "C1111111111" in result.stdout


def test_check_config_fails_without_channels(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update({"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"})
    env.pop("WATCH_CHANNELS", None)
    result = subprocess.run(
        [sys.executable, str(ROOT / "slackd.py"), "--config-dir", str(tmp_path), "--check-config"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "channels" in result.stderr.lower()
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "config_error"


def test_example_consumer_once_advances_offset(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "ts": "1.0",
                "thread_ts": None,
                "user": "U1",
                "text": "hello",
                "channel": "C1111111111",
                "received_at": "2026-09-17T17:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "example_consumer.py"),
            "--name",
            "demo",
            "--config-dir",
            str(tmp_path),
            "--events",
            str(events),
            "--once",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "hello" in result.stdout
    assert (tmp_path / "demo.offset").read_text(encoding="utf-8").strip() == "0"


def test_example_consumer_skips_corrupt_line_and_keeps_going(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"text":"ok","channel":"C1"}\nNOT JSON\n{"text":"after","channel":"C1"}\n', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "example_consumer.py"),
            "--name",
            "demo",
            "--config-dir",
            str(tmp_path),
            "--events",
            str(events),
            "--once",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
    assert "after" in result.stdout
    assert (tmp_path / "demo.offset").read_text(encoding="utf-8").strip() == "2"
