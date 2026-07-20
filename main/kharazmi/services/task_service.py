"""
TaskService — high-level task operations that combine Project mutations
with the undo stack and emit a recalculated schedule.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..core import (
    Project, Task, TaskId, Dependency, DependencyType,
    TaskStatus, Priority, RiskLevel, Duration, DurationUnit, Tag,
)
from ..commands import (
    UndoStack, CreateTaskCommand, DeleteTaskCommand, UpdateTaskCommand,
    MoveTaskCommand, ChangeStatusCommand,
    AddDependencyCommand, RemoveDependencyCommand,
)
from .scheduling_service import SchedulingService


class TaskService:
    """
    Application service for task operations.

    Every mutating method goes through the UndoStack so the user can
    undo/redo. After mutations, the schedule is recalculated.
    """
    def __init__(self, project: Project, undo_stack: UndoStack,
                 scheduling: SchedulingService) -> None:
        self.project = project
        self.undo = undo_stack
        self.scheduling = scheduling

    # ---- Task CRUD ----
    def create_task(self, title: str, duration_minutes: int = 60,
                    priority: Priority = Priority.MEDIUM,
                    x: float = 0.0, y: float = 0.0,
                    recalc: bool = True) -> Optional[TaskId]:
        cmd = CreateTaskCommand(
            title=title,
            duration_minutes=duration_minutes,
            priority=priority,
            x=x, y=y,
        )
        cmd.execute(self.project)
        # We need the created id before pushing (so undo works correctly)
        self.undo.push(cmd)
        if recalc:
            self.scheduling.recalculate()
        # Find the task we just created (cmd stores _created_id)
        return TaskId(cmd._created_id) if cmd._created_id else None

    def delete_task(self, task_id: TaskId, recalc: bool = True) -> None:
        cmd = DeleteTaskCommand(task_id=task_id)
        cmd.execute(self.project)
        self.undo.push(cmd)
        if recalc:
            self.scheduling.recalculate()

    def update_task(self, task_id: TaskId, recalc: bool = True, **changes) -> None:
        cmd = UpdateTaskCommand(task_id=task_id, changes=changes)
        cmd.execute(self.project)
        self.undo.push(cmd)
        if recalc:
            self.scheduling.recalculate()

    def move_task(self, task_id: TaskId, x: float, y: float,
                  recalc: bool = False) -> None:
        """Move in the graph — doesn't affect schedule, so no recalc by default."""
        cmd = MoveTaskCommand(task_id=task_id, new_x=x, new_y=y)
        cmd.execute(self.project)
        # Position changes are too frequent to spam the undo stack with.
        # We push anyway so the user can undo them; this matches what
        # diagramming apps like draw.io do.
        self.undo.push(cmd)

    def change_status(self, task_id: TaskId, new_status: TaskStatus,
                      recalc: bool = True) -> None:
        cmd = ChangeStatusCommand(task_id=task_id, new_status=new_status)
        cmd.execute(self.project)
        self.undo.push(cmd)
        if recalc:
            self.scheduling.recalculate()

    # ---- Dependencies ----
    def add_dependency(self, predecessor_id: TaskId, successor_id: TaskId,
                       dep_type: DependencyType = DependencyType.FINISH_START,
                       lag_minutes: int = 0,
                       recalc: bool = True) -> bool:
        cmd = AddDependencyCommand(
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            dep_type=dep_type,
            lag_minutes=lag_minutes,
        )
        cmd.execute(self.project)
        if cmd._executed:
            self.undo.push(cmd)
            if recalc:
                self.scheduling.recalculate()
            return True
        return False

    def remove_dependency(self, predecessor_id: TaskId, successor_id: TaskId,
                          dep_type: DependencyType = DependencyType.FINISH_START,
                          recalc: bool = True) -> None:
        # Find the existing dep to capture its lag for undo
        existing = None
        for d in self.project.dependencies():
            if (d.predecessor_id == predecessor_id and
                d.successor_id == successor_id and
                d.type == dep_type):
                existing = d
                break
        lag = existing.lag.minutes if existing else 0
        cmd = RemoveDependencyCommand(
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            dep_type=dep_type,
            lag_minutes=lag,
        )
        cmd.execute(self.project)
        self.undo.push(cmd)
        if recalc:
            self.scheduling.recalculate()

    # ---- Query helpers ----
    def tasks_sorted_by(self, key: str = "title") -> list[Task]:
        tasks = list(self.project.tasks())
        if key == "title":
            tasks.sort(key=lambda t: t.title.lower())
        elif key == "priority":
            tasks.sort(key=lambda t: -int(t.priority))
        elif key == "status":
            tasks.sort(key=lambda t: t.status.value)
        elif key == "start":
            tasks.sort(key=lambda t: (t.early_start or datetime.max))
        elif key == "duration":
            tasks.sort(key=lambda t: -t.duration.minutes)
        return tasks

    def search(self, query: str) -> list[Task]:
        q = query.lower().strip()
        if not q:
            return []
        return [
            t for t in self.project.tasks()
            if q in t.title.lower() or q in t.description.lower()
            or any(q in str(tag).lower() for tag in t.tags)
        ]

    def statistics(self) -> dict:
        tasks = list(self.project.tasks())
        if not tasks:
            return {
                "total": 0, "done": 0, "active": 0, "blocked": 0,
                "completion_pct": 0.0, "total_minutes": 0,
                "critical_count": 0, "by_priority": {}, "by_status": {},
            }
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        active = sum(1 for t in tasks if t.status == TaskStatus.ACTIVE)
        blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
        total_min = sum(t.duration.minutes for t in tasks)
        by_priority: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for t in tasks:
            by_priority[t.priority.name] = by_priority.get(t.priority.name, 0) + 1
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        critical_count = sum(1 for t in tasks if t.is_critical)
        completion = sum(t.progress.percent for t in tasks) / len(tasks)
        return {
            "total": len(tasks),
            "done": done,
            "active": active,
            "blocked": blocked,
            "completion_pct": round(completion, 1),
            "total_minutes": total_min,
            "critical_count": critical_count,
            "by_priority": by_priority,
            "by_status": by_status,
        }
