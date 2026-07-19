"""
JournalStore — persists AI-generated routes as a searchable journal.

Each entry records:
  - The user's original goal
  - The clarifying questions asked and the user's answers
  - The complete generated Route
  - Optional notes the user added later

Stored as a single JSON file (~/.rask/journal.json) for simplicity.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .ai_service import JournalEntry, Route


JOURNAL_PATH = Path.home() / ".rask" / "journal.json"


class JournalStore:
    """File-backed store of journal entries."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else JOURNAL_PATH
        self._entries: list[JournalEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for entry_data in data.get("entries", []):
                try:
                    self._entries.append(JournalEntry.from_dict(entry_data))
                except Exception:
                    continue
        except Exception:
            self._entries = []

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {"entries": [e.to_dict() for e in self._entries]}
            self.path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def add(self, goal: str, clarifying_qa: list[tuple[str, str]],
            route: Optional[Route], notes: str = "") -> JournalEntry:
        """Create a new journal entry and persist it."""
        entry = JournalEntry(
            id=f"je-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.utcnow().isoformat(),
            user_goal=goal,
            clarifying_questions_asked=[q for q, _ in clarifying_qa],
            user_answers=[a for _, a in clarifying_qa],
            route=route,
            notes=notes,
        )
        self._entries.append(entry)
        self._save()
        return entry

    def update_notes(self, entry_id: str, notes: str) -> None:
        for e in self._entries:
            if e.id == entry_id:
                e.notes = notes
                self._save()
                return

    def delete(self, entry_id: str) -> None:
        self._entries = [e for e in self._entries if e.id != entry_id]
        self._save()

    def get(self, entry_id: str) -> Optional[JournalEntry]:
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    def all(self) -> list[JournalEntry]:
        """Return all entries, newest first."""
        return sorted(self._entries,
                       key=lambda e: e.timestamp,
                       reverse=True)

    def search(self, query: str) -> list[JournalEntry]:
        """Search entries by goal text or notes."""
        q = query.lower().strip()
        if not q:
            return self.all()
        return [
            e for e in self.all()
            if q in e.user_goal.lower() or q in e.notes.lower()
            or (e.route and q in e.route.summary.lower())
        ]

    def __iter__(self) -> Iterator[JournalEntry]:
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._entries)
