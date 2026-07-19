"""
SQLite-backed project repository.

Stores project snapshots in SQLite. Each save creates a new snapshot
row, so the full history of project states is preserved — this powers
undo/redo across sessions.

Schema:
  projects(id, name, description, created_at)
  snapshots(id, project_id, saved_at, payload_json, kind)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core import Project


DEFAULT_DB_PATH = Path.home() / ".rask" / "kharazmi.sqlite3"


_schema = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL,
    saved_at     TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    kind         TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_project
    ON snapshots(project_id, saved_at DESC);
"""


@dataclass
class SnapshotInfo:
    id: int
    project_id: str
    saved_at: datetime
    kind: str  # "manual" | "autosave" | "undo"


class SQLiteRepository:
    """
    Thread-safe SQLite repository. Opens a single connection and guards
    it with a lock (SQLite handles concurrency poorly across threads
    when sharing a connection).
    """
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_schema)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- Projects ----
    def upsert_project(self, project: Project) -> str:
        """Insert or update a project row. Returns the project id."""
        pid = _slug(project.name) or "default"
        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM projects WHERE id = ?", (pid,)
            )
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO projects(id, name, description, created_at) VALUES(?,?,?,?)",
                    (pid, project.name, project.description, project.created_at.isoformat()),
                )
            else:
                self._conn.execute(
                    "UPDATE projects SET name=?, description=? WHERE id=?",
                    (project.name, project.description, pid),
                )
        return pid

    def list_projects(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, name, description, created_at FROM projects ORDER BY name"
            )
            return [dict(r) for r in cur.fetchall()]

    def delete_project(self, project_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM snapshots WHERE project_id=?", (project_id,))
            self._conn.execute("DELETE FROM projects WHERE id=?", (project_id,))

    # ---- Snapshots ----
    def save_snapshot(self, project: Project, kind: str = "manual") -> int:
        """Persist a project snapshot. Returns the snapshot id."""
        pid = self.upsert_project(project)
        payload = json.dumps(project.to_dict(), ensure_ascii=False, indent=2)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO snapshots(project_id, saved_at, payload_json, kind) VALUES(?,?,?,?)",
                (pid, datetime.utcnow().isoformat(), payload, kind),
            )
            return cur.lastrowid

    def load_latest(self, project_id: str) -> Optional[Project]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT payload_json FROM snapshots WHERE project_id=? "
                "ORDER BY saved_at DESC LIMIT 1",
                (project_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Project.from_dict(json.loads(row["payload_json"]))

    def load_snapshot(self, snapshot_id: int) -> Optional[Project]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT payload_json FROM snapshots WHERE id=?",
                (snapshot_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Project.from_dict(json.loads(row["payload_json"]))

    def list_snapshots(self, project_id: str, limit: int = 50) -> list[SnapshotInfo]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, project_id, saved_at, kind FROM snapshots "
                "WHERE project_id=? ORDER BY saved_at DESC LIMIT ?",
                (project_id, limit),
            )
            return [
                SnapshotInfo(
                    id=r["id"],
                    project_id=r["project_id"],
                    saved_at=datetime.fromisoformat(r["saved_at"]),
                    kind=r["kind"],
                )
                for r in cur.fetchall()
            ]


def _slug(name: str) -> str:
    """Make a string safe for use as a SQLite primary key."""
    out = []
    for ch in name.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("_")
    return "".join(out)
