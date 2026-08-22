"""Shared pytest configuration: isolated SQLite DB + fixed secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

os.environ["ORION_TEST_DATABASE_URL"] = f"sqlite:///{REPO_ROOT / 'data' / 'test.db'}"
os.environ["TRADINGVIEW_WEBHOOK_SECRET"] = "test-webhook-secret-not-a-real-credential"
os.environ["ORION_STARTING_EQUITY"] = "100000"
