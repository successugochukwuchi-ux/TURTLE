"""
In-memory Signal Log with optional JSON persistence.
Keeps a rolling window of the most recent N signals.
"""

import json
import os
from datetime import datetime, timezone
from collections import deque
from typing import Optional

import pandas as pd


class SignalLog:
    """
    Thread-safe in-memory log of triggered trading signals.
    Optionally persists to a JSON file on disk.

    Attributes:
        max_entries: Maximum number of entries to retain.
        persist_path: Optional path to a JSON file for persistence.
    """

    def __init__(self, max_entries: int = 100, persist_path: Optional[str] = None):
        self.max_entries  = max_entries
        self.persist_path = persist_path
        self._log: deque = deque(maxlen=max_entries)

        if persist_path and os.path.exists(persist_path):
            self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def add(
        self,
        signal: str,
        price: float,
        asset: str,
        timeframe: str,
        ts: Optional[datetime] = None,
    ) -> None:
        """Append a new signal entry."""
        entry = {
            "timestamp": (ts or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S"),
            "signal":    signal,
            "asset":     asset,
            "price":     round(price, 4),
            "timeframe": timeframe,
        }
        self._log.appendleft(entry)   # newest first
        if self.persist_path:
            self._save()

    def as_dataframe(self) -> pd.DataFrame:
        """Return the log as a pandas DataFrame (newest first)."""
        if not self._log:
            return pd.DataFrame(columns=["timestamp", "signal", "asset", "price", "timeframe"])
        return pd.DataFrame(list(self._log))

    def clear(self) -> None:
        self._log.clear()
        if self.persist_path and os.path.exists(self.persist_path):
            os.remove(self.persist_path)

    def __len__(self) -> int:
        return len(self._log)

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            with open(self.persist_path, "w") as f:
                json.dump(list(self._log), f, indent=2)
        except OSError:
            pass

    def _load(self) -> None:
        try:
            with open(self.persist_path) as f:
                data = json.load(f)
            for entry in reversed(data[-self.max_entries:]):
                self._log.appendleft(entry)
        except (OSError, json.JSONDecodeError):
            pass
