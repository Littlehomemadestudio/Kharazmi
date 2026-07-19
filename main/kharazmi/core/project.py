"""
The Project aggregate root.

A Project is a directed graph of Tasks connected by Dependencies. It is
the only object that may create / delete tasks and dependencies —
external code goes through Project's methods so invariants are always
enforced:

  1. No self-dependencies.
  2. No duplicate dependencies (same predecessor, successor, type).
  3. No cycles (a dependency that would close a cycle is rejected and
     a CycleDetected event is emitted).
  4. Deleting a task also deletes every dependency that references it.

The Project emits DomainEvents; the UI listens and refreshes itself.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterator, Optional

from .dependency import Dependency
from .enums import DependencyType
from .events import (
    TaskCreated, TaskDeleted, TaskUpdated, TaskStatusChanged,
    DependencyAdded, DependencyRemoved, CycleDetected, ProjectReset,
    DomainEvent,
)
from .task import Task
from .value_objects import TaskId, Duration, Tag


EventListener = Callable[[DomainEvent], None]


@dataclass
class Project:
    """
    The project graph.

    Internally uses dicts for O(1) lookup; the public API is graph-aware
    so callers never see the dicts directly.
    """
    name: str = "Untitled Project"
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    _tasks: dict[str, Task] = field(default_factory=dict)
    _deps: dict[tuple, Dependency] = field(default_factory=dict)
    _listeners: list[EventListener] = field(default_factory=list)

    # ---- Subscription ----
    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: DomainEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                # A listener failure must never corrupt the project.
                pass

    # ---- Task lifecycle ----
    def add_task(self, task: Task) -> Task:
        if task.id.value in self._tasks:
            raise ValueError(f"Task {task.id} already exists")
        self._tasks[task.id.value] = task
        self._emit(TaskCreated(task_id=task.id, title=task.title))
        return task

    def create_task(self, title: str, **kwargs) -> Task:
        """Convenience factory that generates a fresh TaskId."""
        task = Task(id=TaskId.generate(), title=title, **kwargs)
        return self.add_task(task)

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._tasks.get(task_id.value)

    def require_task(self, task_id: TaskId) -> Task:
        t = self.get_task(task_id)
        if t is None:
            raise KeyError(f"No such task: {task_id}")
        return t

    def delete_task(self, task_id: TaskId) -> None:
        if task_id.value not in self._tasks:
            return
        # Remove every dependency that references this task
        to_remove = [
            key for key in self._deps
            if key[0] == task_id.value or key[1] == task_id.value
        ]
        for key in to_remove:
            dep = self._deps.pop(key)
            self._emit(DependencyRemoved(
                predecessor_id=dep.predecessor_id,
                successor_id=dep.successor_id,
            ))
        del self._tasks[task_id.value]
        self._emit(TaskDeleted(task_id=task_id))

    def update_task(self, task_id: TaskId, **changes) -> None:
        """Patch a task's fields. Unknown keys raise."""
        task = self.require_task(task_id)
        for k, v in changes.items():
            if not hasattr(task, k):
                raise AttributeError(f"Task has no field {k!r}")
            old = getattr(task, k)
            if old == v:
                continue
            setattr(task, k, v)
            task.touch()
            self._emit(TaskUpdated(task_id=task_id, field=k, old=old, new=v))

    def change_status(self, task_id: TaskId, new_status) -> None:
        task = self.require_task(task_id)
        old = task.status
        task.advance(new_status)
        self._emit(TaskStatusChanged(task_id=task_id, old=old.value, new=new_status.value))

    # ---- Dependencies ----
    def add_dependency(self, dep: Dependency) -> Dependency:
        if dep.predecessor_id.value not in self._tasks:
            raise KeyError(f"Predecessor not found: {dep.predecessor_id}")
        if dep.successor_id.value not in self._tasks:
            raise KeyError(f"Successor not found: {dep.successor_id}")
        if dep.key in self._deps:
            return self._deps[dep.key]

        # Cycle check: would adding predecessor->successor create a cycle?
        # That happens if there's already a path from successor back to predecessor.
        if self._would_create_cycle(dep.predecessor_id, dep.successor_id):
            cycle = self._find_path(dep.successor_id, dep.predecessor_id)
            self._emit(CycleDetected(
                attempted_edge=(dep.predecessor_id.value, dep.successor_id.value),
                cycle=tuple(n.value for n in cycle),
            ))
            raise ValueError(
                f"Refused: dependency {dep.predecessor_id} -> {dep.successor_id} "
                f"would close a cycle: {' -> '.join(n.value for n in cycle)}"
            )

        self._deps[dep.key] = dep
        self._emit(DependencyAdded(
            predecessor_id=dep.predecessor_id,
            successor_id=dep.successor_id,
            dep_type=dep.type.value,
        ))
        return dep

    def remove_dependency(self, predecessor_id: TaskId, successor_id: TaskId,
                          dep_type: DependencyType = DependencyType.FINISH_START) -> None:
        key = (predecessor_id.value, successor_id.value, dep_type.value)
        if key in self._deps:
            self._deps.pop(key)
            self._emit(DependencyRemoved(
                predecessor_id=predecessor_id, successor_id=successor_id,
            ))

    def dependencies_of(self, task_id: TaskId) -> list[Dependency]:
        """Dependencies where task_id is the SUCCESSOR (i.e. its predecessors)."""
        return [d for d in self._deps.values() if d.successor_id == task_id]

    def dependents_of(self, task_id: TaskId) -> list[Dependency]:
        """Dependencies where task_id is the PREDECESSOR (i.e. its successors)."""
        return [d for d in self._deps.values() if d.predecessor_id == task_id]

    # ---- Graph queries ----
    def _would_create_cycle(self, predecessor: TaskId, successor: TaskId) -> bool:
        # If there's a path successor -> ... -> predecessor already, adding
        # predecessor -> successor closes a cycle.
        return self._can_reach(successor, predecessor)

    def _can_reach(self, src: TaskId, dst: TaskId) -> bool:
        if src == dst:
            return True
        visited: set[str] = set()
        stack = [src.value]
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for dep in self._deps.values():
                if dep.predecessor_id.value == cur:
                    if dep.successor_id.value == dst.value:
                        return True
                    stack.append(dep.successor_id.value)
        return False

    def _find_path(self, src: TaskId, dst: TaskId) -> list[TaskId]:
        """BFS path search, returns the list of nodes from src to dst (inclusive)."""
        if src == dst:
            return [src]
        visited: dict[str, Optional[TaskId]] = {src.value: None}
        queue = [src.value]
        while queue:
            cur = queue.pop(0)
            for dep in self._deps.values():
                if dep.predecessor_id.value == cur and dep.successor_id.value not in visited:
                    visited[dep.successor_id.value] = TaskId(cur)
                    if dep.successor_id.value == dst.value:
                        # reconstruct
                        path = [dst]
                        node = dst
                        while visited[node.value] is not None:
                            node = visited[node.value]
                            path.append(node)
                        path.reverse()
                        return path
                    queue.append(dep.successor_id.value)
        return []

    # ---- Iteration ----
    def tasks(self) -> Iterator[Task]:
        return iter(self._tasks.values())

    def dependencies(self) -> Iterator[Dependency]:
        return iter(self._deps.values())

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def dependency_count(self) -> int:
        return len(self._deps)

    def roots(self) -> list[Task]:
        """Tasks with no predecessors — entry points of the graph."""
        return [t for t in self._tasks.values() if not self.dependencies_of(t.id)]

    def leaves(self) -> list[Task]:
        """Tasks with no successors — exit points of the graph."""
        return [t for t in self._tasks.values() if not self.dependents_of(t.id)]

    # ---- Bulk operations ----
    def clear(self) -> None:
        self._tasks.clear()
        self._deps.clear()
        self._emit(ProjectReset())

    # ---- Serialisation ----
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "dependencies": [d.to_dict() for d in self._deps.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        proj = cls(
            name=data.get("name", "Untitled Project"),
            description=data.get("description", ""),
        )
        for t_data in data.get("tasks", []):
            try:
                task = Task.from_dict(t_data)
                proj._tasks[task.id.value] = task
            except Exception:
                # Skip malformed tasks rather than failing the whole load
                continue
        for d_data in data.get("dependencies", []):
            try:
                dep = Dependency.from_dict(d_data)
                # Don't re-emit events during load
                if dep.predecessor_id.value in proj._tasks and dep.successor_id.value in proj._tasks:
                    proj._deps[dep.key] = dep
            except Exception:
                continue
        return proj

    def snapshot(self) -> "Project":
        """Deep copy for undo/redo."""
        return copy.deepcopy(self)
