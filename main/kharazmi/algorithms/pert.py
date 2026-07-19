"""
PERT (Program Evaluation and Review Technique).

Uses three-point estimates (optimistic, most likely, pessimistic) to
compute an expected duration and variance per task. The expected
durations can be fed into CPM, and the variances enable probabilistic
project-duration estimates.

This module provides:
  * aggregate_pert(project) — collects PERT stats along the critical path
  * probability_of_finishing_by(project, target) — Z-score based probability
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from ..core import Project, TaskId, PertEstimate, Duration
from .critical_path import run_cpm, CPMResult


@dataclass
class PERTSummary:
    expected_duration: Duration
    variance: float
    std_dev: float
    critical_path: list[TaskId]

    def probability_by(self, target_minutes: int) -> float:
        """
        P(project finishes within `target_minutes`).

        Uses the classical PERT formula:
            Z = (target - expected) / std_dev
            P = Φ(Z)
        """
        if self.std_dev <= 0:
            return 1.0 if target_minutes >= self.expected_duration.minutes else 0.0
        z = (target_minutes - self.expected_duration.minutes) / self.std_dev
        return _normal_cdf(z)


def _normal_cdf(z: float) -> float:
    """Standard normal CDF using the error function approximation."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def ensure_pert_estimates(project: Project) -> None:
    """
    For every task that lacks a PERT estimate, synthesise one from its
    plain duration using a ±20% spread. This lets PERT run on projects
    that the user hasn't fully specified.
    """
    for task in project.tasks():
        if task.pert is not None:
            continue
        base = task.duration.minutes
        opt = max(1, int(base * 0.8))
        likely = base
        pess = int(base * 1.2)
        task.pert = PertEstimate(
            optimistic=Duration(opt),
            most_likely=Duration(likely),
            pessimistic=Duration(pess),
        )


def run_pert(project: Project, start_anchor: Optional[datetime] = None) -> PERTSummary:
    """
    Compute the PERT summary for the project.

    Side effects: ensures every task has a PertEstimate, then runs CPM
    using the *expected* durations (which Task.effective_duration
    already returns when PERT is set).
    """
    ensure_pert_estimates(project)
    result = run_cpm(project, start_anchor)
    if not result.ok or not result.critical_path:
        return PERTSummary(
            expected_duration=result.project_duration,
            variance=0.0,
            std_dev=0.0,
            critical_path=result.critical_path,
        )

    total_variance = 0.0
    for tid in result.critical_path:
        task = project.get_task(tid)
        if task is None or task.pert is None:
            continue
        total_variance += task.pert.variance

    return PERTSummary(
        expected_duration=result.project_duration,
        variance=total_variance,
        std_dev=math.sqrt(total_variance),
        critical_path=result.critical_path,
    )
