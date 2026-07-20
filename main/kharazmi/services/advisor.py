"""
Local rule-based advisor.

Replaces the previous Ollama-based "AI" — which was a fragile external
dependency. The advisor uses deterministic rules to:
  - Suggest task breakdowns for vague tasks
  - Infer likely dependencies between tasks
  - Detect schedule conflicts and near-critical tasks
  - Recommend priority adjustments
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..core import Project, Task, TaskId, Priority, TaskStatus, RiskLevel


@dataclass
class Advice:
    kind: str          # "breakdown" | "dependency" | "conflict" | "priority"
    severity: str      # "info" | "warning" | "critical"
    title: str
    detail: str
    related_tasks: list[str] = None  # type: ignore[assignment]


class LocalAdvisor:
    """
    Deterministic advisor that scans the project and produces a list of
    Advice items. No external services, no surprises.
    """
    def analyze(self, project: Project) -> list[Advice]:
        out: list[Advice] = []
        out.extend(self._suggest_breakdowns(project))
        out.extend(self._infer_dependencies(project))
        out.extend(self._detect_conflicts(project))
        out.extend(self._recommend_priorities(project))
        return out

    # ---- Breakdown suggestions ----
    # A task is "vague" if its title contains action verbs suggesting a
    # composite activity AND its duration is more than 5 days.
    _COMPOSITE_VERBS = re.compile(
        r"\b(implement|build|design|develop|create|set up|setup|integrate|deliver|research)\b",
        re.IGNORECASE,
    )

    def _suggest_breakdowns(self, project: Project) -> list[Advice]:
        out: list[Advice] = []
        for t in project.tasks():
            if t.duration.days > 5 and self._COMPOSITE_VERBS.search(t.title):
                out.append(Advice(
                    kind="breakdown",
                    severity="info",
                    title=f"Break down: {t.title}",
                    detail=(
                        f"Task '{t.title}' is {t.duration.days:.1f} days long and "
                        f"uses a composite verb. Consider splitting it into "
                        f"design / implement / review subtasks for better tracking."
                    ),
                    related_tasks=[str(t.id)],
                ))
        return out

    # ---- Dependency inference ----
    # If task A's title ends with a noun that task B's title starts with,
    # or they share a tag, B likely depends on A.
    def _infer_dependencies(self, project: Project) -> list[Advice]:
        out: list[Advice] = []
        tasks = list(project.tasks())
        existing = {(d.predecessor_id.value, d.successor_id.value)
                    for d in project.dependencies()}
        for i, a in enumerate(tasks):
            for b in tasks[i+1:]:
                if (a.id.value, b.id.value) in existing or (b.id.value, a.id.value) in existing:
                    continue
                # Shared tag
                if a.tags and b.tags and (a.tags & b.tags):
                    out.append(Advice(
                        kind="dependency",
                        severity="info",
                        title=f"Possible link: {a.title} → {b.title}",
                        detail=(
                            f"'{a.title}' and '{b.title}' share tags "
                            f"{sorted(str(t) for t in (a.tags & b.tags))}. "
                            f"Consider adding a dependency."
                        ),
                        related_tasks=[str(a.id), str(b.id)],
                    ))
        return out

    # ---- Conflict detection ----
    def _detect_conflicts(self, project: Project) -> list[Advice]:
        out: list[Advice] = []
        for t in project.tasks():
            if t.status == TaskStatus.ACTIVE and t.is_critical and t.progress.percent < 50:
                out.append(Advice(
                    kind="conflict",
                    severity="critical",
                    title=f"Critical task behind: {t.title}",
                    detail=(
                        f"'{t.title}' is on the critical path but only "
                        f"{t.progress.percent}% done. Any delay extends the project."
                    ),
                    related_tasks=[str(t.id)],
                ))
            if t.status == TaskStatus.BLOCKED:
                out.append(Advice(
                    kind="conflict",
                    severity="warning",
                    title=f"Blocked: {t.title}",
                    detail=f"'{t.title}' is BLOCKED. Investigate its dependencies.",
                    related_tasks=[str(t.id)],
                ))
        return out

    # ---- Priority recommendations ----
    def _recommend_priorities(self, project: Project) -> list[Advice]:
        out: list[Advice] = []
        for t in project.tasks():
            if t.is_critical and t.priority < Priority.HIGH:
                out.append(Advice(
                    kind="priority",
                    severity="warning",
                    title=f"Raise priority: {t.title}",
                    detail=(
                        f"'{t.title}' is on the critical path but priority is "
                        f"{t.priority.name}. Critical tasks should be HIGH or CRITICAL."
                    ),
                    related_tasks=[str(t.id)],
                ))
        return out
