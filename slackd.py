#!/usr/bin/env python3
"""Shared Slack listener daemon. One instance per workspace."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from muse_slack_bridge.listener import main


if __name__ == "__main__":
    sys.exit(main())
