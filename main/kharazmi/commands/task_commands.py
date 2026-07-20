"""Commands that operate on tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..core import (
    Project, Task, TaskId, Dependency, DependencyType,
    TaskStatus, Priority, RiskLevel, Duration, DurationUnit, Tag,
)
from .base import Command


@dataclass
class CreateTaskCommand(Command):
    title: str = ""
    duration_minutes: int = 60
    priority: Priority = Priority.MEDIUM
    x: float = 0.0
    y: float = 0.0
    _created_id: Optional[str] = None

    name: str = "Create Task"

    def execute(self, project: Project) -> None:
        task = Task(
            id=TaskId.generate(),
            title=self.title or "Untitled Task",
            duration=Duration(self.duration_minutes),
            priority=self.priority,
            x=self.x, y=self.y,
        )
        project.add_task(task)
        self._created_id = task.id.value

    def undo(self, project: Project) -> None:
        if self._created_id:
            project.delete_task(TaskId(self._created_id))


@dataclass
class DeleteTaskCommand(Command):
    task_id: TaskId = None  # type: ignore[assignment]
    _snapshot: Optional[dict] = None
    _deps: list[Dependency] = field(default_factory=list)

    name: str = "Delete Task"

    def execute(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None:
            return
        self._snapshot = task.to_dict()
        # capture dependencies to restore on undo
        self._deps = list(project.dependencies_of(self.task_id)) + \
                     list(project.dependents_of(self.task_id))
        project.delete_task(self.task_id)

    def undo(self, project: Project) -> None:
        if self._snapshot is None:
            return
        task = Task.from_dict(self._snapshot)
        # Re-add directly to internal dict to avoid re-emitting TaskCreated
        # with a different ID
        project._tasks[task.id.value] = task
        for dep in self._deps:
            if dep.predecessor_id.value in project._tasks and dep.successor_id.value in project._tasks:
                project._deps[dep.key] = dep


@dataclass
class UpdateTaskCommand(Command):
    """Update one or more fields on a task. Captures old values for undo."""
    task_id: TaskId = None  # type: ignore[assignment]
    changes: dict = field(default_factory=dict)
    _old_values: dict = field(default_factory=dict)

    name: str = "Update Task"

    def execute(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None:
            return
        for k, v in self.changes.items():
            if not hasattr(task, k):
                continue
            self._old_values[k] = getattr(task, k)
            setattr(task, k, v)
        task.touch()

    def undo(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None:
            return
        for k, v in self._old_values.items():
            setattr(task, k, v)
        task.touch()


@dataclass
class MoveTaskCommand(Command):
    """Move a task to a new (x, y) position in the node graph."""
    task_id: TaskId = None  # type: ignore[assignment]
    new_x: float = 0.0
    new_y: float = 0.0
    _old_x: float = 0.0
    _old_y: float = 0.0

    name: str = "Move Task"

    def execute(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None:
            return
        self._old_x = task.x
        self._old_y = task.y
        task.x = self.new_x
        task.y = self.new_y
        task.touch()

    def undo(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None:
            return
        task.x = self._old_x
        task.y = self._old_y
        task.touch()


@dataclass
class ChangeStatusCommand(Command):
    task_id: TaskId = None  # type: ignore[assignment]
    new_status: TaskStatus = TaskStatus.READY
    _old_status: Optional[TaskStatus] = None

    name: str = "Change Status"

    def execute(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None:
            return
        self._old_status = task.status
        task.advance(self.new_status)

    def undo(self, project: Project) -> None:
        task = project.get_task(self.task_id)
        if task is None or self._old_status is None:
            return
        # Bypass advance() legality check on undo — we know the prior state was legal
        task.status = self._old_status
        task.touch()


@dataclass
class AddDependencyCommand(Command):
    predecessor_id: TaskId = None  # type: ignore[assignment]
    successor_id: TaskId = None  # type: ignore[assignment]
    dep_type: DependencyType = DependencyType.FINISH_START
    lag_minutes: int = 0
    _executed: bool = False

    name: str = "Add Dependency"

    def execute(self, project: Project) -> None:
        try:
            project.add_dependency(Dependency(
                predecessor_id=self.predecessor_id,
                successor_id=self.successor_id,
                type=self.dep_type,
                lag=Duration(self.lag_minutes),
            ))
            self._executed = True
        except ValueError:
            # Cycle / invalid — silently fail so the UI doesn't crash
            self._executed = False

    def undo(self, project: Project) -> None:
        if not self._executed:
            return
        project.remove_dependency(self.predecessor_id, self.successor_id, self.dep_type)


@dataclass
class RemoveDependencyCommand(Command):
    predecessor_id: TaskId = None  # type: ignore[assignment]
    successor_id: TaskId = None  # type: ignore[assignment]
    dep_type: DependencyType = DependencyType.FINISH_START
    lag_minutes: int = 0
    _existed: bool = False

    name: str = "Remove Dependency"

    def execute(self, project: Project) -> None:
        key = (self.predecessor_id.value, self.successor_id.value, self.dep_type.value)
        if key in project._deps:
            self._existed = True
            project.remove_dependency(self.predecessor_id, self.successor_id, self.dep_type)

    def undo(self, project: Project) -> None:
        if not self._existed:
            return
        try:
            project.add_dependency(Dependency(
                predecessor_id=self.predecessor_id,
                successor_id=self.successor_id,
                type=self.dep_type,
                lag=Duration(self.lag_minutes),
            ))
        except ValueError:
            pass
