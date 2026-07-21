"""
CreditsPanel — a small widget that shows AI Credits usage counter.

Stores count in ~/.rask/credits.json and displays like "🪙 12 AI Operations"
in the AI planner view's header bar.
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ..theme import Palette


CREDITS_PATH = Path.home() / ".rask" / "credits.json"


def _load_credits() -> int:
    """Read credits count from disk, return 0 if missing/corrupt."""
    try:
        if CREDITS_PATH.exists():
            data = json.loads(CREDITS_PATH.read_text(encoding="utf-8"))
            return int(data.get("count", 0))
    except Exception:
        pass
    return 0


def _save_credits(count: int) -> None:
    """Persist credits count to disk."""
    try:
        CREDITS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CREDITS_PATH.write_text(
            json.dumps({"count": count}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


class CreditsPanel(QLabel):
    """Small gold-on-dark label showing AI operation count."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._count = _load_credits()
        self._update_text()
        self.setStyleSheet(
            f"color: {Palette.GOLD_PRIMARY}; font-size: 11px; "
            f"font-family: 'JetBrains Mono', monospace; padding-left: 12px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    @property
    def count(self) -> int:
        return self._count

    def increment(self, amount: int = 1) -> None:
        """Increment the credit counter and persist."""
        self._count += amount
        _save_credits(self._count)
        self._update_text()

    def _update_text(self) -> None:
        self.setText(f"🪙 {self._count} AI Operations")
