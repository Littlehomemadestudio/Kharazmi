"""
SchedulingService — orchestrates CPM/PERT/Monte Carlo and emits
ScheduleRecalculated events to the project.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..core import Project, ScheduleRecalculated
from ..algorithms import (
    run_cpm, run_pert, run_monte_carlo, run_resource_leveling,
    CPMResult, PERTSummary, MonteCarloResult, LevelingResult,
)


class SchedulingService:
    """
    The single entry point for scheduling calculations.

    All UI / controller code that needs CPM, PERT, MC, or resource
    leveling goes through here — never calls the algorithm modules
    directly. This way the service can emit a ScheduleRecalculated
    event exactly once per recalculation.
    """
    def __init__(self, project: Project) -> None:
        self.project = project
        self._last_cpm: Optional[CPMResult] = None
        self._last_pert: Optional[PERTSummary] = None

    def recalculate(self, start_anchor: Optional[datetime] = None) -> CPMResult:
        """Run CPM and emit ScheduleRecalculated."""
        result = run_cpm(self.project, start_anchor)
        self._last_cpm = result
        if result.ok:
            # Emit event by directly invoking listeners
            event = ScheduleRecalculated(
                project_duration_minutes=result.project_duration.minutes,
                critical_path=tuple(tid.value for tid in result.critical_path),
            )
            for listener in list(self.project._listeners):
                try:
                    listener(event)
                except Exception:
                    pass
        return result

    def run_pert(self, start_anchor: Optional[datetime] = None) -> PERTSummary:
        summary = run_pert(self.project, start_anchor)
        self._last_pert = summary
        # PERT also recalculates CPM internally, so emit
        if self._last_cpm is not None:
            event = ScheduleRecalculated(
                project_duration_minutes=self._last_cpm.project_duration.minutes,
                critical_path=tuple(tid.value for tid in self._last_cpm.critical_path),
            )
            for listener in list(self.project._listeners):
                try:
                    listener(event)
                except Exception:
                    pass
        return summary

    def run_monte_carlo(self, iterations: int = 1000,
                        target_minutes: Optional[int] = None,
                        start_anchor: Optional[datetime] = None,
                        seed: Optional[int] = None) -> MonteCarloResult:
        return run_monte_carlo(
            self.project,
            iterations=iterations,
            target_minutes=target_minutes,
            start_anchor=start_anchor,
            seed=seed,
        )

    def level_resources(self, start_anchor: Optional[datetime] = None) -> LevelingResult:
        result = run_resource_leveling(self.project, start_anchor)
        # Leveling changes earliest_start constraints, so emit recalc
        if result.cpm.ok:
            event = ScheduleRecalculated(
                project_duration_minutes=result.cpm.project_duration.minutes,
                critical_path=tuple(tid.value for tid in result.cpm.critical_path),
            )
            for listener in list(self.project._listeners):
                try:
                    listener(event)
                except Exception:
                    pass
        return result

    @property
    def last_cpm(self) -> Optional[CPMResult]:
        return self._last_cpm

    @property
    def last_pert(self) -> Optional[PERTSummary]:
        return self._last_pert
