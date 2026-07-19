"""
Topological sort (Kahn's algorithm).

Returns tasks in dependency order: every predecessor appears before
any of its successors. Raises if the graph contains a cycle.
"""
from __future__ import annotations

from typing import Iterable

from ..core import Project, TaskId


class CycleError(RuntimeError):
    """Raised when a topological sort is requested on a cyclic graph."""
    def __init__(self, cycle: list[str]):
        super().__init__(f"Cycle detected: {' -> '.join(cycle)}")
        self.cycle = cycle


def topological_sort(project: Project) -> list[TaskId]:
    """
    Kahn's algorithm. Returns TaskIds in dependency order.

    Raises CycleError if the project graph is not a DAG.
    """
    # Build in-degree map and adjacency list
    in_degree: dict[str, int] = {t.id.value: 0 for t in project.tasks()}
    adj: dict[str, list[str]] = {t.id.value: [] for t in project.tasks()}

    for dep in project.dependencies():
        # predecessor -> successor
        adj[dep.predecessor_id.value].append(dep.successor_id.value)
        in_degree[dep.successor_id.value] += 1

    # Seed with all zero-in-degree nodes
    queue: list[str] = [tid for tid, d in in_degree.items() if d == 0]
    # Sort for determinism
    queue.sort()
    order: list[str] = []

    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for nxt in adj[cur]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
        queue.sort()  # keep deterministic

    if len(order) != len(in_degree):
        # Find a cycle for the error message
        remaining = [tid for tid, d in in_degree.items() if d > 0]
        cycle = _find_cycle(project, remaining)
        raise CycleError(cycle or remaining)

    return [TaskId(tid) for tid in order]


def _find_cycle(project: Project, candidates: list[str]) -> list[str]:
    """DFS cycle finder — used only to produce a helpful error message."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {t.id.value: WHITE for t in project.tasks()}
    stack: list[str] = []

    def dfs(u: str) -> list[str]:
        color[u] = GRAY
        stack.append(u)
        for dep in project.dependencies():
            if dep.predecessor_id.value == u:
                v = dep.successor_id.value
                if color.get(v, WHITE) == GRAY:
                    # found cycle — slice from v to u
                    idx = stack.index(v)
                    return stack[idx:] + [v]
                if color.get(v, WHITE) == WHITE:
                    found = dfs(v)
                    if found:
                        return found
        stack.pop()
        color[u] = BLACK
        return []

    for start in candidates:
        if color.get(start, WHITE) == WHITE:
            cyc = dfs(start)
            if cyc:
                return cyc
    return []
