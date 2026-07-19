"""Standalone cycle detection (Tarjan's SCC)."""
from __future__ import annotations

from typing import Optional

from ..core import Project, TaskId


def has_cycle(project: Project) -> bool:
    """True if the project graph contains any cycle."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {t.id.value: WHITE for t in project.tasks()}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for dep in project.dependencies():
            if dep.predecessor_id.value == u:
                v = dep.successor_id.value
                if color.get(v, WHITE) == GRAY:
                    return True
                if color.get(v, WHITE) == WHITE and dfs(v):
                    return True
        color[u] = BLACK
        return False

    for t in project.tasks():
        if color[t.id.value] == WHITE:
            if dfs(t.id.value):
                return True
    return False


def find_any_cycle(project: Project) -> Optional[list[TaskId]]:
    """Return one cycle as a list of TaskIds, or None if acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {t.id.value: WHITE for t in project.tasks()}
    parent: dict[str, Optional[str]] = {t.id.value: None for t in project.tasks()}
    cycle_start: Optional[str] = None
    cycle_end: Optional[str] = None

    def dfs(u: str) -> bool:
        nonlocal cycle_start, cycle_end
        color[u] = GRAY
        for dep in project.dependencies():
            if dep.predecessor_id.value == u:
                v = dep.successor_id.value
                if color.get(v, WHITE) == GRAY:
                    cycle_start = v
                    cycle_end = u
                    return True
                if color.get(v, WHITE) == WHITE:
                    parent[v] = u
                    if dfs(v):
                        return True
        color[u] = BLACK
        return False

    for t in project.tasks():
        if color[t.id.value] == WHITE:
            if dfs(t.id.value):
                break

    if cycle_start is None:
        return None

    # Reconstruct
    path = [cycle_start]
    cur = cycle_end
    while cur is not None and cur != cycle_start:
        path.append(cur)
        cur = parent[cur]
    path.append(cycle_start)
    path.reverse()
    return [TaskId(n) for n in path]
