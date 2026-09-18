from __future__ import annotations

from datetime import datetime, timedelta, timezone

from muse_slack_bridge.status import write_status
from muse_slack_bridge.watchdog import decide


def test_hold_on_auth_rejected_even_if_process_is_down() -> None:
    decision = decide(
        process_running=False,
        status={"state": "auth_rejected", "reason": "invalid_auth", "detail": "reissue tokens"},
    )
    assert decision.action == "hold"
    assert decision.exit_code == 3
    assert "not restarting" in decision.message


def test_hold_on_config_error() -> None:
    decision = decide(process_running=False, status={"state": "config_error", "reason": "config"})
    assert decision.action == "hold"
    assert decision.exit_code == 2


def test_restart_when_process_missing() -> None:
    decision = decide(process_running=False, status={"state": "listening"})
    assert decision.action == "restart"


def test_ok_when_process_running_and_fresh(tmp_path) -> None:  # noqa: ANN001
    write_status(tmp_path, "listening", pid=9)
    from muse_slack_bridge.status import read_status

    decision = decide(process_running=True, status=read_status(tmp_path), running_pid=9)
    assert decision.action == "ok"


def test_restart_when_status_is_stale() -> None:
    stale = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat().replace("+00:00", "Z")
    decision = decide(
        process_running=True,
        status={"state": "listening", "updated_at": stale, "pid": 9},
        running_pid=9,
        stale_seconds=300,
    )
    assert decision.action == "restart"
    assert "stale" in decision.message
