from __future__ import annotations

from slack_sdk.errors import SlackApiError

from muse_slack_bridge.config import ConfigError
from muse_slack_bridge.errors import EXIT_AUTH, EXIT_CONFIG, EXIT_ERROR, classify


def test_classifies_invalid_auth() -> None:
    classified = classify(SlackApiError("denied", {"error": "invalid_auth"}))
    assert classified.kind == "auth"
    assert classified.code == "invalid_auth"
    assert classified.exit_code == EXIT_AUTH
    assert "Reissue" in classified.message


def test_classifies_token_revoked_from_message() -> None:
    classified = classify(RuntimeError("apps.connections.open token_revoked"))
    assert classified.kind == "auth"
    assert classified.code == "token_revoked"
    assert classified.exit_code == EXIT_AUTH


def test_classifies_config() -> None:
    classified = classify(ConfigError("missing token file"))
    assert classified.kind == "config"
    assert classified.exit_code == EXIT_CONFIG


def test_classifies_transient() -> None:
    classified = classify(TimeoutError("timed out"))
    assert classified.kind == "transient"
    assert classified.exit_code == EXIT_ERROR
