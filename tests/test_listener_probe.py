from __future__ import annotations

import json
from pathlib import Path
from threading import Event

from slack_sdk.errors import SlackApiError

from muse_slack_bridge.config import Config
from muse_slack_bridge.errors import EXIT_AUTH, EXIT_OK
from muse_slack_bridge.listener import probe_tokens, run_listener
from muse_slack_bridge.status import read_status


class FakeWeb:
    def __init__(self, auth_error=None, open_error=None) -> None:  # noqa: ANN001
        self.auth_error = auth_error
        self.open_error = open_error
        self.opens = 0

    def auth_test(self):
        if self.auth_error:
            raise self.auth_error
        return {"bot_id": "B0000000001", "user_id": "U0000000001"}

    def apps_connections_open(self, app_token=None):  # noqa: ANN001
        self.opens += 1
        if self.open_error:
            raise self.open_error
        return {"url": "wss://example.test/socket"}


class FakeClient:
    def __init__(self) -> None:
        self.socket_mode_request_listeners = []
        self.on_message_listeners = []
        self.on_error_listeners = []
        self.on_close_listeners = []
        self.auto_reconnect_enabled = True

    def connect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    def close(self) -> None:
        return None


def _config(tmp_path: Path) -> Config:
    return Config(
        config_dir=tmp_path,
        bot_token="xoxb-test",
        app_token="xapp-test",
        watch_channels=["C1111111111"],
        events_path=tmp_path / "events.jsonl",
        default_channel="C1111111111",
    )


def test_probe_rejects_revoked_app_token() -> None:
    web = FakeWeb(open_error=SlackApiError("nope", {"error": "token_revoked"}))
    try:
        probe_tokens(web, "xapp-test")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "classified").code == "token_revoked"
    else:
        raise AssertionError("expected AuthRejected")


def test_run_listener_writes_auth_rejected_status(tmp_path: Path) -> None:
    web = FakeWeb(auth_error=SlackApiError("nope", {"error": "invalid_auth"}))
    code = run_listener(_config(tmp_path), web=web, stop=Event())
    assert code == EXIT_AUTH
    status = read_status(tmp_path)
    assert status is not None
    assert status["state"] == "auth_rejected"
    assert status["reason"] == "invalid_auth"
    dumped = json.dumps(status)
    assert "xoxb-test" not in dumped
    assert "xapp-test" not in dumped


def test_run_listener_exits_cleanly_when_stopped(tmp_path: Path) -> None:
    stop = Event()
    stop.set()
    code = run_listener(
        _config(tmp_path),
        web=FakeWeb(),
        client_factory=lambda _token, _web: FakeClient(),
        stop=stop,
        heartbeat_seconds=0.01,
    )
    assert code == EXIT_OK
    status = read_status(tmp_path)
    assert status is not None
    assert status["state"] == "stopped"
