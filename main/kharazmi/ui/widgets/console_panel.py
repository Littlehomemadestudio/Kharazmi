"""
ConsolePanel — a command-line interface inside the app.

Supports commands like:
  add <title> [dur:<num><unit>] [p:<priority>]
  del <task_id>
  link <predecessor> <successor> [type:FS|FF|SS|SF]
  unlink <predecessor> <successor> [type]
  list [filter]
  status <task_id> <new_status>
  pert <task_id> <opt> <likely> <pess>
  schedule
  mc [iterations]
  layout
  stats
  save [name]
  load <name>
  export <json|csv|mermaid> <path>
  help
  clear
"""
from __future__ import annotations

import shlex
from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QFont, QColor, QTextCursor, QKeyEvent, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QLineEdit,
    QFrame, QApplication,
)

from ...core import (
    Project, TaskId, DependencyType, TaskStatus, Priority, RiskLevel,
    Duration, DurationUnit, PertEstimate,
)
from ...services import TaskService, SchedulingService, ExportService
from ...persistence import SQLiteRepository
from ..theme import Palette
from ..icons import get_icon


class ConsoleOutput(QPlainTextEdit):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("JetBrains Mono", 10))
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {Palette.BG_DEEPEST};
                color: {Palette.TEXT_PRIMARY};
                border: none;
                padding: 8px;
            }}
        """)

    def append(self, text: str, color: str = Palette.TEXT_PRIMARY) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text + "\n")
        self.setTextCursor(cursor)
        self.ensureCursorVisible()


class ConsoleInput(QLineEdit):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("type a command and press Enter  •  type 'help' for help")
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Palette.BG_TERTIARY};
                color: {Palette.GOLD_BRIGHT};
                border: 1px solid {Palette.BORDER_NORMAL};
                border-top: 1px solid {Palette.BORDER_SUBTLE};
                border-radius: 0;
                padding: 8px 12px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Palette.GOLD_PRIMARY};
                border-top: 1px solid {Palette.BORDER_SUBTLE};
            }}
        """)
        self.setFont(QFont("JetBrains Mono", 10))


class ConsolePanel(QWidget):
    """The integrated command console."""

    def __init__(self, project: Project, task_service: TaskService,
                 scheduling: SchedulingService, export_service: ExportService,
                 parent: QWidget = None) -> None:
        super().__init__(parent)
        self.project = project
        self.task_service = task_service
        self.scheduling = scheduling
        self.export_service = export_service
        self._history: list[str] = []
        self._history_idx: int = -1
        self._repo: Optional[SQLiteRepository] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("CONSOLE")
        header.setStyleSheet(
            f"background-color: {Palette.BG_SECONDARY}; color: {Palette.GOLD_PRIMARY}; "
            f"font-size: 10px; font-weight: bold; letter-spacing: 2px; padding: 6px 12px; "
            f"border-bottom: 1px solid {Palette.BORDER_SUBTLE};"
        )
        layout.addWidget(header)

        self._output = ConsoleOutput()
        layout.addWidget(self._output)

        self._input = ConsoleInput()
        self._input.returnPressed.connect(self._execute)
        layout.addWidget(self._input)

        self._print_banner()

    def _print_banner(self) -> None:
        self._output.append("╔══════════════════════════════════════════════╗", Palette.GOLD_DEEP)
        self._output.append("║   KHARAZMI CONSOLE  •  type 'help' for help  ║", Palette.GOLD_PRIMARY)
        self._output.append("╚══════════════════════════════════════════════╝", Palette.GOLD_DEEP)
        self._output.append("")

    def focus(self) -> None:
        self._input.setFocus()

    # ---- Input handling ----
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Forward to input
        super().keyPressEvent(event)

    def _execute(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._history.append(text)
        self._history_idx = len(self._history)
        self._input.clear()
        self._output.append(f"$ {text}", Palette.GOLD_BRIGHT)
        try:
            self._dispatch(text)
        except Exception as e:
            self._output.append(f"  ERROR: {e}", Palette.STATUS_BLOCKED)
        self._output.append("")

    def _dispatch(self, line: str) -> None:
        try:
            parts = shlex.split(line)
        except ValueError as e:
            self._output.append(f"  parse error: {e}", Palette.STATUS_BLOCKED)
            return
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        handler = getattr(self, f"_cmd_{cmd}", None)
        if handler is None:
            self._output.append(f"  unknown command: {cmd}  (try 'help')", Palette.STATUS_BLOCKED)
            return
        handler(args)

    # ---- Commands ----
    def _cmd_help(self, args: list[str]) -> None:
        self._output.append("Available commands:", Palette.GOLD_PRIMARY)
        commands = [
            ("add <title> [dur:Nh|Nd|Nw] [p:0-4] [t:tag1,tag2]", "Create a new task"),
            ("del <task_id>", "Delete a task"),
            ("list [filter]", "List tasks (optional substring filter)"),
            ("link <pre> <suc> [type:FS|FF|SS|SF]", "Add dependency"),
            ("unlink <pre> <suc> [type]", "Remove dependency"),
            ("status <task_id> <new_status>", "Change task status"),
            ("move <task_id> <x> <y>", "Move task in graph"),
            ("pert <task_id> <opt> <likely> <pess>", "Set PERT 3-point estimate"),
            ("schedule", "Recalculate CPM schedule"),
            ("mc [iterations]", "Run Monte Carlo simulation"),
            ("layout", "Auto-layout the node graph"),
            ("stats", "Show project statistics"),
            ("save [name]", "Save project snapshot"),
            ("load <name>", "Load latest snapshot of project"),
            ("export <json|csv|mermaid> <path>", "Export project to file"),
            ("clear", "Clear console output"),
            ("help", "This message"),
        ]
        for cmd, desc in commands:
            self._output.append(f"  {cmd:50s}  {desc}", Palette.TEXT_PRIMARY)

    def _cmd_clear(self, args: list[str]) -> None:
        self._output.clear()
        self._print_banner()

    def _cmd_add(self, args: list[str]) -> None:
        if not args:
            self._output.append("  usage: add <title> [dur:Nh|Nd|Nw] [p:0-4] [t:tag1,tag2]",
                                Palette.STATUS_BLOCKED)
            return
        # Parse args
        title_parts = []
        dur_minutes = 60
        priority = Priority.MEDIUM
        tags = []
        for a in args:
            if a.startswith("dur:"):
                dur_minutes = self._parse_duration(a[4:])
            elif a.startswith("p:"):
                try:
                    priority = Priority(int(a[2:]))
                except (ValueError, IndexError):
                    pass
            elif a.startswith("t:"):
                for t in a[2:].split(","):
                    t = t.strip()
                    if t:
                        tags.append(t)
            else:
                title_parts.append(a)
        title = " ".join(title_parts)
        if not title:
            self._output.append("  error: title required", Palette.STATUS_BLOCKED)
            return
        tid = self.task_service.create_task(
            title=title,
            duration_minutes=dur_minutes,
            priority=priority,
        )
        if tid and tags:
            from ...core import Tag
            task = self.project.get_task(tid)
            for t in tags:
                try:
                    task.add_tag(Tag(t))
                except ValueError:
                    pass
        self._output.append(f"  created {tid}  '{title}'  ({dur_minutes}m, {priority.name})",
                            Palette.GOLD_BRIGHT)

    def _cmd_del(self, args: list[str]) -> None:
        if not args:
            self._output.append("  usage: del <task_id>", Palette.STATUS_BLOCKED)
            return
        tid = TaskId(args[0])
        self.task_service.delete_task(tid)
        self._output.append(f"  deleted {tid}", Palette.GOLD_BRIGHT)

    def _cmd_list(self, args: list[str]) -> None:
        query = args[0] if args else ""
        tasks = self.task_service.search(query) if query else list(self.project.tasks())
        if not tasks:
            self._output.append("  (no tasks)", Palette.TEXT_TERTIARY)
            return
        self._output.append(f"  {len(tasks)} task(s):", Palette.TEXT_SECONDARY)
        for t in sorted(tasks, key=lambda x: x.title.lower()):
            crit = " *" if t.is_critical else "  "
            self._output.append(
                f"  {crit} {str(t.id):10s}  {t.title:30s}  "
                f"[{t.status.value:9s}]  {t.duration.humanize():>8s}  "
                f"p={int(t.priority)}",
                Palette.GOLD_BRIGHT if t.is_critical else Palette.TEXT_PRIMARY
            )

    def _cmd_link(self, args: list[str]) -> None:
        if len(args) < 2:
            self._output.append("  usage: link <pre> <suc> [type:FS|FF|SS|SF]",
                                Palette.STATUS_BLOCKED)
            return
        pre = TaskId(args[0])
        suc = TaskId(args[1])
        dep_type = DependencyType.FINISH_START
        if len(args) >= 3 and args[2].startswith("type:"):
            try:
                dep_type = DependencyType(args[2][5:])
            except ValueError:
                self._output.append(f"  invalid type: {args[2][5:]}", Palette.STATUS_BLOCKED)
                return
        ok = self.task_service.add_dependency(pre, suc, dep_type)
        if ok:
            self._output.append(f"  linked {pre} → {suc} ({dep_type.value})",
                                Palette.GOLD_BRIGHT)
        else:
            self._output.append(f"  refused: would create cycle", Palette.STATUS_BLOCKED)

    def _cmd_unlink(self, args: list[str]) -> None:
        if len(args) < 2:
            self._output.append("  usage: unlink <pre> <suc> [type]", Palette.STATUS_BLOCKED)
            return
        pre = TaskId(args[0])
        suc = TaskId(args[1])
        dep_type = DependencyType.FINISH_START
        if len(args) >= 3 and args[2].startswith("type:"):
            try:
                dep_type = DependencyType(args[2][5:])
            except ValueError:
                pass
        self.task_service.remove_dependency(pre, suc, dep_type)
        self._output.append(f"  unlinked {pre} → {suc}", Palette.GOLD_BRIGHT)

    def _cmd_status(self, args: list[str]) -> None:
        if len(args) < 2:
            self._output.append("  usage: status <task_id> <new_status>", Palette.STATUS_BLOCKED)
            return
        tid = TaskId(args[0])
        try:
            new_status = TaskStatus(args[1])
        except ValueError:
            self._output.append(f"  invalid status: {args[1]}", Palette.STATUS_BLOCKED)
            return
        self.task_service.change_status(tid, new_status)
        self._output.append(f"  {tid} → {new_status.value}", Palette.GOLD_BRIGHT)

    def _cmd_move(self, args: list[str]) -> None:
        if len(args) < 3:
            self._output.append("  usage: move <task_id> <x> <y>", Palette.STATUS_BLOCKED)
            return
        tid = TaskId(args[0])
        x = float(args[1])
        y = float(args[2])
        self.task_service.move_task(tid, x, y, recalc=False)
        self._output.append(f"  moved {tid} to ({x}, {y})", Palette.GOLD_BRIGHT)

    def _cmd_pert(self, args: list[str]) -> None:
        if len(args) < 4:
            self._output.append("  usage: pert <task_id> <opt> <likely> <pess> [unit]",
                                Palette.STATUS_BLOCKED)
            return
        tid = TaskId(args[0])
        task = self.project.get_task(tid)
        if task is None:
            self._output.append(f"  no such task: {tid}", Palette.STATUS_BLOCKED)
            return
        unit = DurationUnit.HOUR
        if len(args) >= 5:
            try:
                unit = DurationUnit(args[4])
            except ValueError:
                pass
        try:
            opt = Duration.of(float(args[1]), unit)
            ml = Duration.of(float(args[2]), unit)
            pess = Duration.of(float(args[3]), unit)
            task.pert = PertEstimate(opt, ml, pess)
            task.touch()
            self.scheduling.recalculate()
            self._output.append(
                f"  PERT set: expected {task.pert.expected.humanize()} "
                f"σ={task.pert.std_dev:.1f}m",
                Palette.GOLD_BRIGHT
            )
        except ValueError as e:
            self._output.append(f"  error: {e}", Palette.STATUS_BLOCKED)

    def _cmd_schedule(self, args: list[str]) -> None:
        result = self.scheduling.recalculate()
        if not result.ok:
            self._output.append(f"  schedule error: {result.cycle_error}", Palette.STATUS_BLOCKED)
            return
        self._output.append(
            f"  project duration: {result.project_duration.humanize()}",
            Palette.GOLD_BRIGHT
        )
        self._output.append(
            f"  critical path ({len(result.critical_path)}): "
            + " → ".join(str(t) for t in result.critical_path),
            Palette.GOLD_PRIMARY
        )

    def _cmd_mc(self, args: list[str]) -> None:
        iterations = int(args[0]) if args and args[0].isdigit() else 500
        self._output.append(f"  running {iterations} iterations...", Palette.TEXT_SECONDARY)
        QApplication.processEvents()
        result = self.scheduling.run_monte_carlo(iterations=iterations, seed=42)
        self._output.append(
            f"  mean  {result.mean_minutes:>8.0f}m   "
            f"P10 {result.p10_minutes:>6d}m   "
            f"P50 {result.p50_minutes:>6d}m   "
            f"P90 {result.p90_minutes:>6d}m",
            Palette.GOLD_BRIGHT
        )

    def _cmd_layout(self, args: list[str]) -> None:
        # The view handles the actual layout; emit a signal instead
        self._output.append("  use Ctrl+L in the graph view to auto-layout",
                            Palette.TEXT_TERTIARY)

    def _cmd_stats(self, args: list[str]) -> None:
        s = self.task_service.statistics()
        self._output.append(f"  Total tasks:     {s['total']}", Palette.TEXT_PRIMARY)
        self._output.append(f"  Done:            {s['done']}", Palette.STATUS_DONE)
        self._output.append(f"  Active:          {s['active']}", Palette.STATUS_ACTIVE)
        self._output.append(f"  Blocked:         {s['blocked']}", Palette.STATUS_BLOCKED)
        self._output.append(f"  Critical:        {s['critical_count']}", Palette.GOLD_BRIGHT)
        self._output.append(f"  Completion:      {s['completion_pct']:.1f}%", Palette.GOLD_PRIMARY)
        self._output.append(f"  Total duration:  {s['total_minutes']}m", Palette.TEXT_SECONDARY)

    def _cmd_save(self, args: list[str]) -> None:
        name = args[0] if args else self.project.name
        self.project.name = name
        if self._repo is None:
            self._repo = SQLiteRepository()
        sid = self._repo.save_snapshot(self.project, kind="manual")
        self._output.append(f"  saved snapshot #{sid} for '{name}'", Palette.GOLD_BRIGHT)

    def _cmd_load(self, args: list[str]) -> None:
        if not args:
            self._output.append("  usage: load <name>", Palette.STATUS_BLOCKED)
            return
        if self._repo is None:
            self._repo = SQLiteRepository()
        from ...persistence.sqlite_store import _slug
        pid = _slug(args[0])
        proj = self._repo.load_latest(pid)
        if proj is None:
            self._output.append(f"  no project found: {args[0]}", Palette.STATUS_BLOCKED)
            return
        self.project.clear()
        for t in proj.tasks():
            self.project._tasks[t.id.value] = t
        for d in proj.dependencies():
            self.project._deps[d.key] = d
        self.project.name = proj.name
        self.scheduling.recalculate()
        self._output.append(f"  loaded '{proj.name}' ({proj.task_count} tasks)",
                            Palette.GOLD_BRIGHT)

    def _cmd_export(self, args: list[str]) -> None:
        if len(args) < 2:
            self._output.append("  usage: export <json|csv|mermaid> <path>",
                                Palette.STATUS_BLOCKED)
            return
        fmt = args[0].lower()
        path = args[1]
        try:
            if fmt == "json":
                self.export_service.to_json(path)
            elif fmt == "csv":
                self.export_service.to_csv_tasks(path)
                self.export_service.to_csv_deps(path + ".deps.csv")
            elif fmt == "mermaid":
                self.export_service.to_mermaid(path)
            else:
                self._output.append(f"  unknown format: {fmt}", Palette.STATUS_BLOCKED)
                return
            self._output.append(f"  exported {fmt} → {path}", Palette.GOLD_BRIGHT)
        except Exception as e:
            self._output.append(f"  export failed: {e}", Palette.STATUS_BLOCKED)

    def _parse_duration(self, s: str) -> int:
        if not s:
            return 60
        unit_char = s[-1].lower()
        try:
            val = float(s[:-1] if unit_char in "mhw" else s)
        except ValueError:
            return 60
        if unit_char == "h":
            return int(val * 60)
        if unit_char == "d":
            return int(val * 60 * 8)
        if unit_char == "w":
            return int(val * 60 * 8 * 5)
        return int(val)  # minutes

    # ---- External hooks ----
    def set_repository(self, repo: SQLiteRepository) -> None:
        self._repo = repo
