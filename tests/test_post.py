from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from muse_slack_bridge.post import PostError, post_message


class FakeResp(dict):
    def get(self, key, default=None):  # noqa: ANN001
        return dict.get(self, key, default)


class FakeWebClient:
    def __init__(self) -> None:
        self.calls: list[Dict[str, Any]] = []
        self.error: Optional[Exception] = None

    def chat_postMessage(self, **kwargs: Any) -> Dict[str, Any]:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"ok": True, "ts": "1710000000.000200"}


def test_posts_verbatim_without_prefix() -> None:
    client = FakeWebClient()
    result = post_message("token", "C1111111111", "PING", client=client)
    assert result == {"ok": True, "ts": "1710000000.000200"}
    assert client.calls == [{"channel": "C1111111111", "text": "PING"}]


def test_thread_reply() -> None:
    client = FakeWebClient()
    post_message("token", "C1111111111", "reply", thread_ts="1710000000.000100", client=client)
    assert client.calls[0]["thread_ts"] == "1710000000.000100"


def test_failure_is_post_error() -> None:
    from slack_sdk.errors import SlackApiError

    client = FakeWebClient()
    client.error = SlackApiError("nope", {"error": "channel_not_found"})
    with pytest.raises(PostError, match="channel_not_found"):
        post_message("token", "C1111111111", "PING", client=client)
