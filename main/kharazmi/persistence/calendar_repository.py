"""
SQLite-backed persistence for the calendar subsystem.

Stores CalendarStore snapshots in SQLite. Mirrors the Enterprise
plan's SQLiteRepository pattern.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..calendar import CalendarStore


DEFAULT_DB_PATH = Path.home() / ".kharazmi" / "calendar.sqlite3"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS calendar_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_at     TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    kind         TEXT NOT NULL
);
"""


class CalendarRepository:
    """Thread-safe SQLite repository for the CalendarStore."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def save(self, store: CalendarStore, kind: str = "manual") -> int:
        """Persist a snapshot of the calendar store."""
        payload = json.dumps(store.to_dict(), ensure_ascii=False, indent=2)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO calendar_snapshots(saved_at, payload_json, kind) VALUES(?,?,?)",
                (datetime.utcnow().isoformat(), payload, kind),
            )
            return cur.lastrowid

    def load_latest(self) -> Optional[CalendarStore]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT payload_json FROM calendar_snapshots "
                "ORDER BY saved_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                return None
            return CalendarStore.from_dict(json.loads(row["payload_json"]))

    def has_snapshot(self) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) as c FROM calendar_snapshots")
            return cur.fetchone()["c"] > 0
