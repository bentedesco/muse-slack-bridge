from __future__ import annotations

import os
from pathlib import Path

import pytest

from muse_slack_bridge.config import Config, ConfigError, parse_channel_list, read_secret_file


def test_read_secret_file_requires_0600(tmp_path: Path) -> None:
    token = tmp_path / "bot_token"
    token.write_text("xoxb-test-token\n", encoding="utf-8")
    token.chmod(0o644)
    with pytest.raises(ConfigError, match="chmod 600"):
        read_secret_file(token)


def test_read_secret_file_accepts_0600(tmp_path: Path) -> None:
    token = tmp_path / "bot_token"
    token.write_text("xoxb-test-token\n", encoding="utf-8")
    token.chmod(0o600)
    assert read_secret_file(token) == "xoxb-test-token"


def test_env_overrides_token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token = tmp_path / "bot_token"
    token.write_text("from-file", encoding="utf-8")
    token.chmod(0o644)  # would fail if the file were used
    (tmp_path / "app_token").write_text("unused", encoding="utf-8")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "from-env-bot")
    monkeypatch.setenv("SLACK_APP_TOKEN", "from-env-app")
    monkeypatch.setenv("WATCH_CHANNELS", "C1111111111")
    monkeypatch.delenv("SLACK_DEFAULT_CHANNEL", raising=False)
    config = Config.load(config_dir=tmp_path)
    assert config.bot_token == "from-env-bot"
    assert config.app_token == "from-env-app"
    assert config.watch_channels == ["C1111111111"]
    assert config.default_channel == "C1111111111"
    assert config.events_path == tmp_path / "events.jsonl"


def test_missing_channels_refuses_to_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.delenv("WATCH_CHANNELS", raising=False)
    with pytest.raises(ConfigError, match="no channels configured"):
        Config.load(config_dir=tmp_path)


def test_hash_channel_names_rejected() -> None:
    with pytest.raises(ConfigError, match="channel IDs"):
        parse_channel_list("#general")


def test_channel_file_and_events_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    monkeypatch.delenv("WATCH_CHANNELS", raising=False)
    (tmp_path / "channels").write_text("C1111111111, C2222222222\n", encoding="utf-8")
    events = tmp_path / "data" / "events.jsonl"
    monkeypatch.setenv("MUSE_SLACK_BRIDGE_EVENTS", str(events))
    config = Config.load(config_dir=tmp_path)
    assert config.watch_channels == ["C1111111111", "C2222222222"]
    assert config.events_path == events


def test_post_cli_does_not_require_app_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.setenv("WATCH_CHANNELS", "C1111111111")
    config = Config.load(config_dir=tmp_path, require_app_token=False)
    assert config.app_token is None
