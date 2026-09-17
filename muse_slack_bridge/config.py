"""Load tokens and watch-list from env or chmod-600 files."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

APP_NAME = "muse-slack-bridge"


class ConfigError(Exception):
    """Invalid or missing bridge configuration."""


def default_config_dir() -> Path:
    override = os.environ.get("MUSE_SLACK_BRIDGE_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def _file_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def read_secret_file(path: Path) -> str:
    if not path.is_file():
        raise ConfigError(f"missing token file: {path}")
    mode = _file_mode(path)
    if mode != 0o600:
        raise ConfigError(
            f"{path} must be chmod 600 (found {stat.filemode(path.stat().st_mode)} / {oct(mode)})"
        )
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ConfigError(f"token file is empty: {path}")
    return value


def resolve_secret(env_name: str, filename: str, config_dir: Path) -> str:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value
    return read_secret_file(config_dir / filename)


def parse_channel_list(raw: str) -> List[str]:
    channels: List[str] = []
    for part in raw.replace("\n", ",").split(","):
        channel = part.strip()
        if not channel:
            continue
        if channel.startswith("#"):
            raise ConfigError(
                "use Slack channel IDs (for example C0123456789), not #channel-names"
            )
        channels.append(channel)
    return channels


def resolve_channels(config_dir: Path) -> List[str]:
    raw = os.environ.get("WATCH_CHANNELS", "").strip()
    if not raw:
        path = config_dir / "channels"
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
    channels = parse_channel_list(raw)
    if not channels:
        raise ConfigError(
            "no channels configured; set WATCH_CHANNELS or write channel IDs to "
            f"{config_dir / 'channels'}"
        )
    return channels


@dataclass
class Config:
    config_dir: Path
    bot_token: str
    watch_channels: List[str]
    events_path: Path
    default_channel: str
    app_token: Optional[str] = None

    @classmethod
    def load(
        cls,
        config_dir: Optional[Path] = None,
        events_path: Optional[Path] = None,
        require_app_token: bool = True,
    ) -> "Config":
        resolved_dir = Path(config_dir) if config_dir else default_config_dir()
        bot_token = resolve_secret("SLACK_BOT_TOKEN", "bot_token", resolved_dir)
        app_token = None
        if require_app_token:
            app_token = resolve_secret("SLACK_APP_TOKEN", "app_token", resolved_dir)
        watch_channels = resolve_channels(resolved_dir)
        if events_path is not None:
            resolved_events = Path(events_path).expanduser()
        else:
            events_override = os.environ.get("MUSE_SLACK_BRIDGE_EVENTS", "").strip()
            resolved_events = (
                Path(events_override).expanduser()
                if events_override
                else resolved_dir / "events.jsonl"
            )
        default_channel = os.environ.get("SLACK_DEFAULT_CHANNEL", "").strip() or watch_channels[0]
        return cls(
            config_dir=resolved_dir,
            app_token=app_token,
            bot_token=bot_token,
            watch_channels=watch_channels,
            events_path=resolved_events,
            default_channel=default_channel,
        )
