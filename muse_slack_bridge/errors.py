"""Classify Slack/config failures so the watchdog can stop retrying auth errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_AUTH = 3

AUTH_SLACK_ERRORS = frozenset(
    {
        "invalid_auth",
        "not_authed",
        "token_revoked",
        "account_inactive",
        "token_expired",
        "invalid_token",
        "not_allowed_token_type",
        "incompatible_token_type",
        "missing_scope",
        "access_denied",
        "no_permission",
        "org_login_required",
        "ekm_access_denied",
        "team_access_not_granted",
        "not_allowed",
    }
)

AUTH_HINTS = (
    "invalid_auth",
    "token_revoked",
    "not_authed",
    "token_expired",
    "not_allowed_token_type",
)

_HUMAN = {
    "invalid_auth": "Slack rejected a token. Reissue the app-level token (xapp-) and/or bot token (xoxb-), replace the local files, then start the listener again.",
    "not_authed": "Slack says the request was not authenticated. Check both token files and Socket Mode.",
    "token_revoked": "Slack reports a token was revoked or regenerated. Write the new values into the local token files before restarting.",
    "account_inactive": "The Slack app or workspace is inactive. Confirm the app still exists and is installed.",
    "token_expired": "A token expired. Generate a new one in the Slack app dashboard and replace the local file.",
    "not_allowed_token_type": "Wrong token type for Socket Mode. The listener needs an app-level token with connections:write.",
    "missing_scope": "The app-level token is missing connections:write, or the bot token is missing a required scope.",
    "access_denied": "Slack denied the connection. Confirm the app is enabled and Socket Mode is on.",
}


@dataclass(frozen=True)
class ClassifiedError:
    kind: str  # auth | config | transient
    code: Optional[str]
    message: str

    @property
    def exit_code(self) -> int:
        if self.kind == "auth":
            return EXIT_AUTH
        if self.kind == "config":
            return EXIT_CONFIG
        return EXIT_ERROR


def slack_error_code(exc: BaseException) -> Optional[str]:
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            code = response.get("error") if hasattr(response, "get") else None
        except Exception:  # noqa: BLE001
            code = None
        if code:
            return str(code)
        try:
            code = response["error"]
            if code:
                return str(code)
        except Exception:  # noqa: BLE001
            pass
    text = str(exc)
    for code in AUTH_SLACK_ERRORS:
        if code in text:
            return code
    return None


def classify(exc: BaseException) -> ClassifiedError:
    from muse_slack_bridge.config import ConfigError

    if isinstance(exc, ConfigError):
        return ClassifiedError("config", None, str(exc))
    code = slack_error_code(exc)
    if code in AUTH_SLACK_ERRORS:
        return ClassifiedError("auth", code, _HUMAN.get(code, f"Slack rejected the connection ({code})."))
    lowered = str(exc).lower()
    for hint in AUTH_HINTS:
        if hint in lowered:
            return ClassifiedError("auth", hint, _HUMAN.get(hint, f"Slack rejected the connection ({hint})."))
    return ClassifiedError("transient", code, str(exc))
