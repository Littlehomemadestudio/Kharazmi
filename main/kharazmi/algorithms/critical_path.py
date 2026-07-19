"""
Critical Path Method (CPM).

Implements the classical forward/backward pass used in project
management since the 1950s. The result is injected back into each
Task as early_start, early_finish, late_start, late_finish, and slack.

Assumptions:
  * The project graph is a DAG (cycles are rejected before this runs).
  * Working calendar is simplified to 8-hour days, 5-day weeks,
    starting from project.start_anchor (default: now).
  * Lag on FS dependencies extends the successor's earliest start.
  * For FF/SS/SF we apply the standard precedence arithmetic.

The "critical path" is the longest chain through the graph — any
delay on it delays the whole project. Rask paints these nodes
in gold.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..core import (
    Project, Task, TaskId, Duration, Slack, DependencyType,
    ScheduleRecalculated,
)
from .topological_sort import topological_sort, CycleError


WORK_DAY_MINUTES = 60 * 8       # 8h
WORK_WEEK_MINUTES = WORK_DAY_MINUTES * 5  # 40h


@dataclass
class CPMResult:
    """Outcome of a CPM run."""
    project_start: datetime
    project_end: datetime
    project_duration: Duration
    critical_path: list[TaskId]
    cycle_error: Optional[CycleError] = None

    @property
    def ok(self) -> bool:
        return self.cycle_error is None


def _add_minutes(start: datetime, minutes: int) -> datetime:
    """Add (or subtract) working minutes from a datetime.

    Simplified calendar: work happens 09:00-17:00 Mon-Fri. Minutes that
    fall outside work hours roll forward (for +) or backward (for -) to
    the appropriate work slot.
    """
    if minutes == 0:
        return _snap_to_work_hours(start)

    if minutes > 0:
        return _add_working_minutes_forward(start, minutes)
    else:
        return _add_working_minutes_backward(start, -minutes)


def _add_working_minutes_forward(start: datetime, minutes: int) -> datetime:
    cur = _snap_to_work_hours(start)
    remaining = minutes
    while remaining > 0:
        end_of_day = cur.replace(hour=17, minute=0, second=0, microsecond=0)
        avail = int((end_of_day - cur).total_seconds() // 60)
        if avail <= 0:
            cur = _next_work_window(cur)
            continue
        if remaining <= avail:
            cur = cur + timedelta(minutes=remaining)
            remaining = 0
        else:
            cur = _next_work_window(end_of_day)
            remaining -= avail
    return cur


def _add_working_minutes_backward(start: datetime, minutes: int) -> datetime:
    """Subtract `minutes` working minutes from `start`."""
    cur = _snap_to_work_hours_backward(start)
    remaining = minutes
    while remaining > 0:
        start_of_day = cur.replace(hour=9, minute=0, second=0, microsecond=0)
        avail = int((cur - start_of_day).total_seconds() // 60)
        if avail <= 0:
            cur = _prev_work_window(cur)
            continue
        if remaining <= avail:
            cur = cur - timedelta(minutes=remaining)
            remaining = 0
        else:
            cur = _prev_work_window(start_of_day)
            remaining -= avail
    return cur


def _snap_to_work_hours_backward(dt: datetime) -> datetime:
    """Snap backward: if outside work hours, snap to end of previous work window."""
    if dt.weekday() >= 5:  # Sat or Sun → go back to Friday 17:00
        days_back = dt.weekday() - 4  # Friday is 4
        dt = dt - timedelta(days=days_back)
        return dt.replace(hour=17, minute=0, second=0, microsecond=0)
    if dt.hour < 9:
        # Go to previous work day's 17:00
        prev_day = dt - timedelta(days=1)
        if prev_day.weekday() >= 5:
            prev_day = prev_day - timedelta(days=prev_day.weekday() - 4)
        return prev_day.replace(hour=17, minute=0, second=0, microsecond=0)
    if dt.hour >= 17:
        return dt.replace(hour=17, minute=0, second=0, microsecond=0)
    return dt


def _prev_work_window(dt: datetime) -> datetime:
    """Return the start of the previous work window strictly before dt."""
    prev_day = dt - timedelta(days=1)
    if prev_day.weekday() >= 5:
        # Go back to Friday
        prev_day = prev_day - timedelta(days=prev_day.weekday() - 4)
    return prev_day.replace(hour=17, minute=0, second=0, microsecond=0)


def _snap_to_work_hours(dt: datetime) -> datetime:
    """If dt is outside Mon-Fri 09-17, snap forward to next work window."""
    if dt.weekday() >= 5:  # Sat or Sun
        days_ahead = 7 - dt.weekday()  # days until Monday
        dt = dt + timedelta(days=days_ahead)
        return dt.replace(hour=9, minute=0, second=0, microsecond=0)
    if dt.hour < 9:
        return dt.replace(hour=9, minute=0, second=0, microsecond=0)
    if dt.hour >= 17:
        # Move to next work day
        next_day = dt + timedelta(days=1)
        if next_day.weekday() >= 5:
            next_day = next_day + timedelta(days=7 - next_day.weekday())
        return next_day.replace(hour=9, minute=0, second=0, microsecond=0)
    return dt


def _next_work_window(dt: datetime) -> datetime:
    """Return the start of the next work window strictly after dt."""
    next_day = dt + timedelta(days=1)
    if next_day.weekday() >= 5:
        next_day = next_day + timedelta(days=7 - next_day.weekday())
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)


def run_cpm(project: Project, start_anchor: Optional[datetime] = None) -> CPMResult:
    """
    Execute the CPM forward + backward pass on the project.

    Mutates every Task on the project by setting:
      early_start, early_finish, late_start, late_finish, slack
    """
    if start_anchor is None:
        start_anchor = datetime.utcnow()

    # 1. Topological order — bails on cycles
    try:
        order = topological_sort(project)
    except CycleError as e:
        return CPMResult(
            project_start=start_anchor,
            project_end=start_anchor,
            project_duration=Duration(0),
            critical_path=[],
            cycle_error=e,
        )

    # Reset previously computed values
    for t in project.tasks():
        t.early_start = None
        t.early_finish = None
        t.late_start = None
        t.late_finish = None
        t.slack = None

    # 2. FORWARD PASS — compute early_start / early_finish
    project_start = start_anchor
    for tid in order:
        task = project.require_task(tid)
        dur = task.effective_duration

        # Earliest start = max(early_finish of FS predecessors + lag,
        #                       early_start of SS predecessors + lag, ...)
        preds = project.dependencies_of(tid)
        if not preds:
            es = task.earliest_start or project_start
            es = _snap_to_work_hours(es)
        else:
            es = task.earliest_start or project_start
            es = _snap_to_work_hours(es)
            for dep in preds:
                pred_task = project.get_task(dep.predecessor_id)
                if pred_task is None or pred_task.early_finish is None and pred_task.early_start is None:
                    continue
                lag = dep.lag.minutes
                if dep.type == DependencyType.FINISH_START:
                    candidate = pred_task.early_finish
                    if candidate is not None:
                        candidate = _add_minutes(candidate, lag)
                        es = max(es, candidate)
                elif dep.type == DependencyType.START_START:
                    candidate = pred_task.early_start
                    if candidate is not None:
                        candidate = _add_minutes(candidate, lag)
                        es = max(es, candidate)
                elif dep.type == DependencyType.FINISH_FINISH:
                    # successor must finish after predecessor finishes;
                    # so successor starts at (pred_finish + lag - succ_dur)
                    pred_finish = pred_task.early_finish
                    if pred_finish is not None:
                        candidate = _add_minutes(pred_finish, lag)
                        # subtract own duration to get start
                        candidate = _add_minutes(candidate, -dur.minutes)
                        es = max(es, candidate)
                elif dep.type == DependencyType.START_FINISH:
                    # successor finishes after predecessor starts;
                    # successor starts at (pred_start + lag - succ_dur)
                    pred_start = pred_task.early_start
                    if pred_start is not None:
                        candidate = _add_minutes(pred_start, lag)
                        candidate = _add_minutes(candidate, -dur.minutes)
                        es = max(es, candidate)

        ef = _add_minutes(es, dur.minutes)
        task.early_start = es
        task.early_finish = ef

    # Project end = max(early_finish) across all tasks
    project_end = max(
        (t.early_finish for t in project.tasks() if t.early_finish is not None),
        default=start_anchor,
    )
    project_duration = Duration(
        int((project_end - project_start).total_seconds() // 60)
    )

    # 3. BACKWARD PASS — compute late_start / late_finish
    # Start from project_end and walk the topo order backwards.
    for tid in reversed(order):
        task = project.require_task(tid)
        succs = project.dependents_of(tid)
        if not succs:
            # Leaf: late_finish = project_end (or task.latest_finish if set)
            lf = task.latest_finish or project_end
            lf = _snap_to_work_hours(lf)
        else:
            lf = project_end
            for dep in succs:
                succ_task = project.get_task(dep.successor_id)
                if succ_task is None or succ_task.late_start is None and succ_task.late_finish is None:
                    continue
                lag = dep.lag.minutes
                if dep.type == DependencyType.FINISH_START:
                    candidate = succ_task.late_start
                    if candidate is not None:
                        candidate = _add_minutes(candidate, -lag)
                        lf = min(lf, candidate)
                elif dep.type == DependencyType.FINISH_FINISH:
                    candidate = succ_task.late_finish
                    if candidate is not None:
                        candidate = _add_minutes(candidate, -lag)
                        lf = min(lf, candidate)
                elif dep.type == DependencyType.START_START:
                    # successor starts after predecessor starts;
                    # predecessor must finish before successor starts + dur - lag
                    candidate = succ_task.late_start
                    if candidate is not None:
                        candidate = _add_minutes(candidate, -lag)
                        # predecessor can finish as late as (succ_late_start - lag + succ_dur)? actually
                        # for SS, late_finish of predecessor = succ_late_start + succ_dur - lag
                        succ_dur = succ_task.effective_duration
                        candidate = _add_minutes(candidate, succ_dur.minutes)
                        lf = min(lf, candidate)
                elif dep.type == DependencyType.START_FINISH:
                    # successor finishes after predecessor starts
                    candidate = succ_task.late_finish
                    if candidate is not None:
                        candidate = _add_minutes(candidate, -lag)
                        succ_dur = succ_task.effective_duration
                        candidate = _add_minutes(candidate, succ_dur.minutes)
                        lf = min(lf, candidate)

        dur = task.effective_duration
        ls = _add_minutes(lf, -dur.minutes)
        task.late_finish = lf
        task.late_start = ls

        # Slack
        if task.early_start is not None and task.late_start is not None:
            total_slack_min = max(
                0, int((task.late_start - task.early_start).total_seconds() // 60)
            )
            # Free slack: how much we can slip without delaying any successor's early_start
            succs_list = project.dependents_of(tid)
            if not succs_list:
                free_slack_min = total_slack_min
            else:
                free_slack_min = total_slack_min
                for dep in succs_list:
                    succ = project.get_task(dep.successor_id)
                    if succ is None or succ.early_start is None:
                        continue
                    if task.early_finish is None:
                        continue
                    if dep.type == DependencyType.FINISH_START:
                        gap = int((succ.early_start - task.early_finish).total_seconds() // 60) - dep.lag.minutes
                    elif dep.type == DependencyType.START_START:
                        gap = int((succ.early_start - task.early_start).total_seconds() // 60) - dep.lag.minutes
                    elif dep.type == DependencyType.FINISH_FINISH:
                        gap = int((succ.early_finish - task.early_finish).total_seconds() // 60) - dep.lag.minutes
                    else:  # START_FINISH
                        gap = int((succ.early_finish - task.early_start).total_seconds() // 60) - dep.lag.minutes
                    free_slack_min = min(free_slack_min, max(0, gap))

            task.slack = Slack(
                total_slack=Duration(total_slack_min),
                free_slack=Duration(free_slack_min),
            )

    # 4. CRITICAL PATH = chain of tasks with zero total slack
    critical = [t.id for t in project.tasks() if t.is_critical]
    # Order critical path nodes topologically for display
    critical_set = {tid.value for tid in critical}
    critical_path = [tid for tid in order if tid.value in critical_set]

    # Emit schedule-recalculated event
    from ..core.events import ScheduleRecalculated
    project.__dict__.setdefault("_listeners", [])
    # We can't easily emit from here without coupling — caller (SchedulingService) emits.

    return CPMResult(
        project_start=project_start,
        project_end=project_end,
        project_duration=project_duration,
        critical_path=critical_path,
    )
