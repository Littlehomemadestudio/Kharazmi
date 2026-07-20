"""Base Command class for undo/redo support."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Command(ABC):
    """
    A reversible operation on the project.

    Each command knows how to execute itself (do) and how to undo
    itself. Commands are pushed onto an UndoStack; the UI exposes
    Ctrl+Z / Ctrl+Shift+Z to traverse the stack.

    Commands must be self-contained — they carry all the data they
    need to perform both do and undo. They must NOT hold references
    to UI widgets.
    """
    name: str = "Command"
    description: str = ""

    @abstractmethod
    def execute(self, project: Any) -> None:
        """Apply the command to the project."""

    @abstractmethod
    def undo(self, project: Any) -> None:
        """Reverse the command."""

    def redo(self, project: Any) -> None:
        """Re-apply after an undo. Default = execute()."""
        self.execute(project)
