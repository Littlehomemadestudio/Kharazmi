"""
Resource leveling heuristic.

When two tasks would run concurrently and both need the same resource
beyond its daily capacity, one must be delayed. This module performs
a greedy leveling pass that respects dependencies.

This is a simplified heuristic — production-grade leveling is NP-hard;
we use a priority-rule based serial schedule generation scheme.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..core import Project, TaskId, Resource
from .critical_path import run_cpm, CPMResult


@dataclass
class LevelingResult:
    conflicts_resolved: int
    conflicts_remaining: int
    shifted_tasks: list[TaskId]
    cpm: CPMResult


def run_resource_leveling(project: Project, start_anchor: Optional[datetime] = None) -> LevelingResult:
    """
    Greedy resource leveling.

    Strategy:
      1. Run CPM to get initial early-start times.
      2. Walk through time buckets (one per work-day).
      3. In each bucket, gather tasks active in that window.
      4. If their combined resource load exceeds capacity for any
         resource, defer the lowest-priority task by extending its
         earliest_start constraint to the start of the next bucket.
      5. Re-run CPM. Repeat up to N passes or until no conflicts.
    """
    if start_anchor is None:
        start_anchor = datetime.utcnow()

    # Collect known resources across all tasks
    known_resources: dict[str, Resource] = {}
    for task in project.tasks():
        for alloc in task.resources:
            if alloc.resource.name not in known_resources:
                known_resources[alloc.resource.name] = alloc.resource

    if not known_resources:
        # No resources → nothing to level
        cpm = run_cpm(project, start_anchor)
        return LevelingResult(
            conflicts_resolved=0, conflicts_remaining=0,
            shifted_tasks=[], cpm=cpm,
        )

    shifted: list[TaskId] = []
    conflicts_resolved = 0

    max_passes = 10
    for _ in range(max_passes):
        cpm = run_cpm(project, start_anchor)
        if not cpm.ok:
            break

        # Find earliest conflict
        # Build a per-day aggregate load
        daily_load: dict[datetime, dict[str, float]] = {}
        daily_tasks: dict[datetime, list[tuple[TaskId, str, float]]] = {}

        for task in project.tasks():
            if task.early_start is None or task.early_finish is None:
                continue
            cur = task.early_start
            while cur < task.early_finish:
                day = cur.replace(hour=0, minute=0, second=0, microsecond=0)
                bucket = daily_load.setdefault(day, {r: 0.0 for r in known_resources})
                tlist = daily_tasks.setdefault(day, [])
                for alloc in task.resources:
                    bucket[alloc.resource.name] = bucket.get(alloc.resource.name, 0.0) + alloc.load
                    tlist.append((task.id, alloc.resource.name, alloc.load))
                # advance one day
                from datetime import timedelta
                cur = cur + timedelta(days=1)
                if cur.weekday() >= 5:
                    cur = cur + timedelta(days=7 - cur.weekday())

        # Find a day with over-allocation
        conflict_day = None
        conflict_resource = None
        for day, loads in sorted(daily_load.items()):
            for rname, load in loads.items():
                cap = known_resources[rname].capacity_per_day
                if load > cap + 1e-6:
                    conflict_day = day
                    conflict_resource = rname
                    break
            if conflict_day:
                break

        if conflict_day is None:
            break  # no conflicts

        # Among tasks active on conflict_day needing conflict_resource,
        # pick the lowest priority one to defer.
        candidates = [
            (tid, rname, load)
            for (tid, rname, load) in daily_tasks[conflict_day]
            if rname == conflict_resource
        ]
        if not candidates:
            break

        # Look up priorities
        def priority_of(tid: TaskId) -> int:
            t = project.get_task(tid)
            return int(t.priority) if t else 0

        candidates.sort(key=lambda x: priority_of(x[0]))
        victim_id = candidates[0][0]
        victim = project.get_task(victim_id)
        if victim is None:
            break

        # Defer victim to start of next work day after conflict_day
        from datetime import timedelta
        next_day = conflict_day + timedelta(days=1)
        if next_day.weekday() >= 5:
            next_day = next_day + timedelta(days=7 - next_day.weekday())
        next_day = next_day.replace(hour=9, minute=0, second=0, microsecond=0)

        victim.earliest_start = next_day
        victim.touch()
        shifted.append(victim_id)
        conflicts_resolved += 1

    # Final CPM
    final_cpm = run_cpm(project, start_anchor)

    # Count remaining conflicts
    conflicts_remaining = 0
    daily_load: dict[datetime, dict[str, float]] = {}
    for task in project.tasks():
        if task.early_start is None or task.early_finish is None:
            continue
        cur = task.early_start
        while cur < task.early_finish:
            day = cur.replace(hour=0, minute=0, second=0, microsecond=0)
            bucket = daily_load.setdefault(day, {r: 0.0 for r in known_resources})
            for alloc in task.resources:
                bucket[alloc.resource.name] = bucket.get(alloc.resource.name, 0.0) + alloc.load
            from datetime import timedelta
            cur = cur + timedelta(days=1)
            if cur.weekday() >= 5:
                cur = cur + timedelta(days=7 - cur.weekday())
    for day, loads in daily_load.items():
        for rname, load in loads.items():
            cap = known_resources[rname].capacity_per_day
            if load > cap + 1e-6:
                conflicts_remaining += 1

    return LevelingResult(
        conflicts_resolved=conflicts_resolved,
        conflicts_remaining=conflicts_remaining,
        shifted_tasks=shifted,
        cpm=final_cpm,
    )
