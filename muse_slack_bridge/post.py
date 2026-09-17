"""Verbatim chat.postMessage helper used by slack-post.py."""

from __future__ import annotations

from typing import Any, Dict, Optional

from slack_sdk.errors import SlackApiError
from slack_sdk.web import WebClient


class PostError(Exception):
    """chat.postMessage failed."""


def post_message(
    bot_token: str,
    channel: str,
    text: str,
    thread_ts: Optional[str] = None,
    client: Optional[WebClient] = None,
) -> Dict[str, Any]:
    web = client or WebClient(token=bot_token)
    kwargs: Dict[str, Any] = {"channel": channel, "text": text}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    try:
        response = web.chat_postMessage(**kwargs)
    except SlackApiError as exc:
        detail = ""
        if exc.response is not None:
            detail = str(exc.response.get("error") or exc.response.get("detail") or "")
        raise PostError(detail or str(exc)) from exc
    return {"ok": True, "ts": response.get("ts")}
