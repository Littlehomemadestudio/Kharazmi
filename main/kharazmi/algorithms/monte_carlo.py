"""
Monte Carlo risk simulation.

Runs N simulations of the project, sampling each task's duration from
a triangular distribution bounded by its PERT optimistic/most-likely/
pessimistic estimates. Produces a histogram of project completion
times and percentile estimates.

This is the standard technique for "what's the realistic range of
outcomes here?" when durations are uncertain.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..core import Project, Task, Duration, PertEstimate
from .critical_path import run_cpm, CPMResult, _add_minutes


@dataclass
class MonteCarloResult:
    iterations: int
    mean_minutes: float
    median_minutes: float
    p10_minutes: int
    p50_minutes: int
    p90_minutes: int
    p95_minutes: int
    histogram: list[int]  # bucket counts
    bucket_size_minutes: int
    min_minutes: int
    max_minutes: int
    probability_within_target: float  # P(duration <= target)

    def to_dict(self) -> dict:
        return {
            "iterations": self.iterations,
            "mean_minutes": self.mean_minutes,
            "median_minutes": self.median_minutes,
            "p10_minutes": self.p10_minutes,
            "p50_minutes": self.p50_minutes,
            "p90_minutes": self.p90_minutes,
            "p95_minutes": self.p95_minutes,
            "min_minutes": self.min_minutes,
            "max_minutes": self.max_minutes,
            "probability_within_target": self.probability_within_target,
            "bucket_size_minutes": self.bucket_size_minutes,
            "histogram": self.histogram,
        }


def _triangular_sample(opt: int, mode: int, pess: int) -> int:
    """Sample from a triangular distribution with given low/mode/high."""
    if opt == pess:
        return opt
    if opt <= mode <= pess:
        u = random.random()
        fc = (mode - opt) / (pess - opt)
        if u < fc:
            return int(opt + math.sqrt(u * (pess - opt) * (mode - opt)) if (pess - opt) * (mode - opt) > 0 else opt)
        else:
            return int(pess - math.sqrt((1 - u) * (pess - opt) * (pess - mode)) if (pess - opt) * (pess - mode) > 0 else pess)
    return mode


import math


def run_monte_carlo(
    project: Project,
    iterations: int = 1000,
    target_minutes: Optional[int] = None,
    start_anchor: Optional[datetime] = None,
    seed: Optional[int] = None,
) -> MonteCarloResult:
    """
    Run a Monte Carlo simulation of the project.

    For each iteration:
      1. Sample a duration for every task from its triangular distribution
         (synthesised from PERT estimates if not present).
      2. Run CPM with these sampled durations.
      3. Record the project duration.

    Returns summary statistics including percentiles and a histogram.
    """
    if seed is not None:
        random.seed(seed)

    if start_anchor is None:
        start_anchor = datetime.utcnow()

    # Ensure PERT estimates exist so we have ranges to sample from
    from .pert import ensure_pert_estimates
    ensure_pert_estimates(project)

    # Snapshot the ORIGINAL pert ranges so we always sample from the
    # real distribution (not from the degenerate 3-point we install
    # after each sample).
    original_pert: dict[str, PertEstimate] = {
        t.id.value: t.pert for t in project.tasks() if t.pert is not None
    }
    # Capture the ranges we'll sample from
    pert_ranges: dict[str, tuple[int, int, int]] = {
        tid: (p.optimistic.minutes, p.most_likely.minutes, p.pessimistic.minutes)
        for tid, p in original_pert.items()
    }

    durations: list[int] = []
    try:
        for _ in range(max(1, iterations)):
            # Sample a duration for every task from its ORIGINAL triangular
            # range, then install a degenerate PertEstimate so that
            # Task.effective_duration returns the sampled value.
            for task in project.tasks():
                rng = pert_ranges.get(task.id.value)
                if rng is None:
                    continue
                sampled = max(1, _triangular_sample(*rng))
                task.pert = PertEstimate(
                    optimistic=Duration(sampled),
                    most_likely=Duration(sampled),
                    pessimistic=Duration(sampled),
                )

            result: CPMResult = run_cpm(project, start_anchor)
            if result.ok:
                durations.append(result.project_duration.minutes)
    finally:
        # Restore original PERT estimates
        for task in project.tasks():
            if task.id.value in original_pert:
                task.pert = original_pert[task.id.value]
            else:
                task.pert = None
        # Recompute CPM with original durations so the project's visible state is consistent
        run_cpm(project, start_anchor)

    if not durations:
        return MonteCarloResult(
            iterations=0,
            mean_minutes=0.0, median_minutes=0.0,
            p10_minutes=0, p50_minutes=0, p90_minutes=0, p95_minutes=0,
            histogram=[], bucket_size_minutes=60,
            min_minutes=0, max_minutes=0,
            probability_within_target=0.0,
        )

    durations.sort()
    n = len(durations)

    def percentile(p: float) -> int:
        idx = max(0, min(n - 1, int(round(p * (n - 1)))))
        return durations[idx]

    mean = sum(durations) / n
    median = durations[n // 2]
    p10 = percentile(0.10)
    p50 = percentile(0.50)
    p90 = percentile(0.90)
    p95 = percentile(0.95)
    mn = durations[0]
    mx = durations[-1]

    # Build histogram — 30 buckets between min and max
    nbuckets = 30
    if mx == mn:
        bucket_size = 60
        histogram = [n]
    else:
        bucket_size = max(1, (mx - mn) // nbuckets)
        histogram = [0] * nbuckets
        for d in durations:
            idx = min(nbuckets - 1, (d - mn) // bucket_size)
            histogram[idx] += 1

    if target_minutes is None:
        # Default: target = mean (so probability ≈ 0.5)
        target_minutes = int(mean)

    within = sum(1 for d in durations if d <= target_minutes)
    prob = within / n

    return MonteCarloResult(
        iterations=n,
        mean_minutes=mean,
        median_minutes=median,
        p10_minutes=p10, p50_minutes=p50,
        p90_minutes=p90, p95_minutes=p95,
        histogram=histogram,
        bucket_size_minutes=bucket_size,
        min_minutes=mn, max_minutes=mx,
        probability_within_target=prob,
    )
