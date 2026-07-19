"""JSON file serializers for import/export."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from ..core import Project


def export_to_json(project: Project, path: Union[str, Path]) -> Path:
    """Write the project to a JSON file. Returns the resolved path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(project.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def import_from_json(path: Union[str, Path]) -> Project:
    """Load a project from a JSON file."""
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return Project.from_dict(data)


def export_to_csv_tasks(project: Project, path: Union[str, Path]) -> Path:
    """Export tasks only to CSV (no dependencies)."""
    import csv
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "title", "description", "duration_minutes", "priority",
            "status", "risk", "progress", "tags", "x", "y",
            "early_start", "early_finish", "late_start", "late_finish",
            "total_slack_minutes",
        ])
        for t in project.tasks():
            w.writerow([
                str(t.id), t.title, t.description, t.duration.minutes,
                int(t.priority), t.status.value, t.risk.value, t.progress.percent,
                "|".join(str(x) for x in t.tags),
                t.x, t.y,
                _dt(t.early_start), _dt(t.early_finish),
                _dt(t.late_start), _dt(t.late_finish),
                t.slack.total_slack.minutes if t.slack else "",
            ])
    return p


def export_to_csv_deps(project: Project, path: Union[str, Path]) -> Path:
    """Export dependencies to CSV."""
    import csv
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["predecessor", "successor", "type", "lag_minutes"])
        for d in project.dependencies():
            w.writerow([
                str(d.predecessor_id), str(d.successor_id),
                d.type.value, d.lag.minutes,
            ])
    return p


def export_to_mermaid(project: Project, path: Union[str, Path]) -> Path:
    """
    Export the task graph as a Mermaid flowchart.

    Critical tasks are highlighted; edges are labelled with their
    dependency type.
    """
    lines = ["flowchart LR"]
    # nodes
    for t in project.tasks():
        label = t.title.replace('"', "'")
        shape_open, shape_close = "([" if t.is_critical else '("', "])" if t.is_critical else '")'
        lines.append(f'    {t.id.value}{shape_open}"{label}"{shape_close}')
    # edges
    for d in project.dependencies():
        lines.append(f"    {d.predecessor_id.value} -->|{d.type.value}| {d.successor_id.value}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _dt(value) -> str:
    return "" if value is None else value.isoformat()
