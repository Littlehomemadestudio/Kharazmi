# پشته برگشت/اجرای مجدد فرمان‌ها
from __future__ import annotations

from typing import Callable, Optional

from .base import Command


class UndoStack:
    """
    Holds executed commands and supports undo/redo.

    The stack is bounded; once it exceeds `limit`, the oldest commands
    are discarded.
    """

    # مقداردهی اولیه پشته برگشت
    def __init__(self, limit: int = 200) -> None:
        self._stack: list[Command] = []
        self._index: int = 0  # index of the NEXT command to be executed
        self._limit = limit
        self._listeners: list[Callable[[], None]] = []

    # ثبت شنودگر تغییرات پشته
    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    # اطلاع‌رسانی به شنودگرها
    def _notify(self) -> None:
        for l in list(self._listeners):
            try:
                l()
            except Exception:
                pass

    # افزودن فرمان به پشته
    def push(self, command: Command) -> None:
        """Execute and push a command. Truncates any redo history."""
        # Drop any commands after the current index (we just branched)
        self._stack = self._stack[:self._index]
        self._stack.append(command)
        if len(self._stack) > self._limit:
            self._stack = self._stack[-self._limit:]
        self._index = len(self._stack)
        self._notify()

    # اجرای فرمان و افزودن به پشته
    def execute(self, command: Command, project) -> None:
        """Execute a command against `project`, then push it."""
        command.execute(project)
        self.push(command)

    # برگرداندن آخرین فرمان
    def undo(self, project) -> bool:
        """Undo the most recent command. Returns False if nothing to undo."""
        if self._index == 0:
            return False
        self._index -= 1
        cmd = self._stack[self._index]
        cmd.undo(project)
        self._notify()
        return True

    # اجرای مجدد فرمان بعدی
    def redo(self, project) -> bool:
        """Re-execute the next command. Returns False if nothing to redo."""
        if self._index >= len(self._stack):
            return False
        cmd = self._stack[self._index]
        cmd.redo(project)
        self._index += 1
        self._notify()
        return True

    # آیا برگشت ممکن است
    def can_undo(self) -> bool:
        return self._index > 0

    # آیا اجرای مجدد ممکن است
    def can_redo(self) -> bool:
        return self._index < len(self._stack)

    # نام فرمان بعدی برگشت
    def next_undo_name(self) -> Optional[str]:
        if not self.can_undo():
            return None
        return self._stack[self._index - 1].name

    # نام فرمان بعدی اجرای مجدد
    def next_redo_name(self) -> Optional[str]:
        if not self.can_redo():
            return None
        return self._stack[self._index].name

    # پاک کردن پشته برگشت
    def clear(self) -> None:
        self._stack.clear()
        self._index = 0
        self._notify()
