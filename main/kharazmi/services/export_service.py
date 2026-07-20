"""Export service — wraps the persistence serializers with project context."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from ..core import Project
from ..persistence import (
    export_to_json, import_from_json,
    export_to_csv_tasks, export_to_csv_deps, export_to_mermaid,
)


class ExportService:
    def __init__(self, project: Project) -> None:
        self.project = project

    def to_json(self, path: Union[str, Path]) -> Path:
        return export_to_json(self.project, path)

    def from_json(self, path: Union[str, Path]) -> Project:
        return import_from_json(path)

    def to_csv_tasks(self, path: Union[str, Path]) -> Path:
        return export_to_csv_tasks(self.project, path)

    def to_csv_deps(self, path: Union[str, Path]) -> Path:
        return export_to_csv_deps(self.project, path)

    def to_mermaid(self, path: Union[str, Path]) -> Path:
        return export_to_mermaid(self.project, path)
