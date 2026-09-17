"""Keep secrets out of logs."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"(?:xox[a-zA-Z]-|xapp-)[A-Za-z0-9-]+")


def redact(text: str) -> str:
    """Replace Slack token-shaped strings before printing."""
    return _TOKEN_RE.sub("[redacted]", text)
