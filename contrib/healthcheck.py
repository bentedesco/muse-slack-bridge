#!/usr/bin/env python3
"""Watchdog: revive a crashed listener, but do not retry Slack auth rejection."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from muse_slack_bridge.config import default_config_dir
from muse_slack_bridge.status import read_status
from muse_slack_bridge.watchdog import DEFAULT_STALE_SECONDS, decide


def _config_dir() -> Path:
    override = os.environ.get("MUSE_SLACK_BRIDGE_HOME")
    if override:
        return Path(override).expanduser()
    return default_config_dir()


def _root() -> Path:
    return Path(os.environ.get("MUSE_SLACK_BRIDGE_ROOT", str(ROOT))).expanduser()


def _pgrep_slackd() -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", "[s]lackd.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _kill(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except OSError as exc:
        print(f"could not stop stale pid {pid}: {exc}", file=sys.stderr)


def _start(root: Path, config_dir: Path) -> int:
    log_path = config_dir / "slackd.log"
    config_dir.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(root / "slackd.py"), "--config-dir", str(config_dir)],
        cwd=str(root),
        stdout=handle,
        stderr=handle,
        start_new_session=True,
    )
    handle.close()
    print(f"started slackd.py pid={proc.pid}", file=sys.stderr)
    return 0


def _probe(root: Path, config_dir: Path) -> int:
    return subprocess.run(
        [sys.executable, str(root / "slackd.py"), "--config-dir", str(config_dir), "--probe"],
        cwd=str(root),
        check=False,
    ).returncode


def main() -> int:
    config_dir = _config_dir()
    root = _root()
    stale = int(os.environ.get("MUSE_SLACK_BRIDGE_STALE_SECONDS", str(DEFAULT_STALE_SECONDS)))
    pids = _pgrep_slackd()
    status = read_status(config_dir)
    decision = decide(
        process_running=bool(pids),
        status=status,
        stale_seconds=stale,
        running_pid=pids[0] if pids else None,
    )
    print(decision.message, file=sys.stderr)
    if decision.action == "ok":
        return 0
    if decision.action == "hold":
        return decision.exit_code

    if pids:
        for pid in pids:
            _kill(pid)
        time.sleep(1)

    probe_code = _probe(root, config_dir)
    if probe_code != 0:
        print("probe failed; not starting a crash loop", file=sys.stderr)
        return probe_code
    return _start(root, config_dir)


if __name__ == "__main__":
    sys.exit(main())
