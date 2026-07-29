"""تست‌های جامع لایه پایداری — مخزن SQLite، سریال‌سازها و مخزن تقویم"""

import csv
import json
from datetime import datetime
from pathlib import Path

import pytest

from kharazmi.core.task import Task
from kharazmi.core.project import Project
from kharazmi.core.dependency import Dependency
from kharazmi.core.value_objects import (
    TaskId, Duration, Progress, PertEstimate,
    Tag, Resource, ResourceAllocation, Slack,
)
from kharazmi.core.enums import TaskStatus, DependencyType, RiskLevel, Priority
from kharazmi.persistence.sqlite_store import SQLiteRepository, SnapshotInfo
from kharazmi.persistence.serializers import (
    export_to_json, import_from_json,
    export_to_csv_tasks, export_to_csv_deps,
    export_to_mermaid,
)
from kharazmi.persistence.calendar_repository import CalendarRepository
from kharazmi.calendar.store import CalendarStore
from kharazmi.calendar.calendar import Calendar
from kharazmi.calendar.event import Event


# ═══════════════════════════════════════════════════════════════════
#  فیکسچرهای کمکی
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def sqlite_repo(tmp_dir):
    """مخزن SQLite با مسیر موقت — بسته شدن خودکار بعد از هر تست"""
    db_path = Path(tmp_dir) / "test_rask.sqlite3"
    repo = SQLiteRepository(db_path=db_path)
    yield repo
    repo.close()


@pytest.fixture
def calendar_repo(tmp_dir):
    """مخزن تقویم SQLite با مسیر موقت"""
    db_path = Path(tmp_dir) / "test_calendar.sqlite3"
    repo = CalendarRepository(db_path=db_path)
    yield repo
    repo.close()


def _make_project_with_tasks(name="پروژه نمونه", description="توضیحات پروژه تست"):
    """ساخت پروژه نمونه با وظایف و وابستگی‌ها"""
    proj = Project(name=name, description=description)
    t1 = proj.add_task(Task(id=TaskId.generate(), title="طراحی UI", duration=Duration(480)))
    t2 = proj.add_task(Task(id=TaskId.generate(), title="پیاده‌سازی", duration=Duration(960)))
    t3 = proj.add_task(Task(id=TaskId.generate(), title="تست", duration=Duration(480)))
    proj.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
    proj.add_dependency(Dependency(t2.id, t3.id, DependencyType.FINISH_START))
    return proj


@pytest.fixture
def sample_project():
    """پروژه نمونه با وظایف و وابستگی‌ها برای تست‌های سریال‌سازی"""
    return _make_project_with_tasks()


@pytest.fixture
def rich_project():
    """پروژه غنی با برچسب، منبع، PERT و وضعیت‌های مختلف"""
    proj = Project(name="پروژه غنی", description="تست سریال‌سازی کامل")
    t1 = proj.add_task(Task(
        id=TaskId.generate(),
        title="وظیفه پیشرفته",
        duration=Duration(120),
    ))
    # افزودن برچسب
    t1.add_tag(Tag("backend"))
    t1.add_tag(Tag("urgent"))
    # تخصیص منبع
    t1.assign_resource(ResourceAllocation(
        Resource("علی", 1.0), 0.5
    ))
    # تنظیم PERT
    t1.pert = PertEstimate(
        optimistic=Duration(60),
        most_likely=Duration(120),
        pessimistic=Duration(240),
    )
    # تغییر وضعیت به ready
    t1.advance(TaskStatus.READY)

    t2 = proj.add_task(Task(id=TaskId.generate(), title="وظیفه ساده", duration=Duration(60)))
    proj.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
    return proj


# ═══════════════════════════════════════════════════════════════════
#  تست‌های SQLiteRepository
# ═══════════════════════════════════════════════════════════════════


class TestSQLiteRepository:
    """تست‌های مخزن SQLite پروژه"""

    # ─── upsert_project ───────────────────────────────────────────

    def test_upsert_project_saves_project(self, sqlite_repo, sample_project):
        """ذخیره پروژه جدید — باید در فهرست پروژه‌ها ظاهر شود"""
        pid = sqlite_repo.upsert_project(sample_project)
        assert isinstance(pid, str)
        assert len(pid) > 0

        projects = sqlite_repo.list_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == sample_project.name
        assert projects[0]["description"] == sample_project.description

    def test_upsert_project_returns_slug_id(self, sqlite_repo):
        """شناسه بازگشتی باید بر اساس نام پروژه ساخته شود"""
        proj = Project(name="My Cool Project")
        pid = sqlite_repo.upsert_project(proj)
        assert pid == "my_cool_project"

    def test_upsert_project_default_id_for_empty_name(self, sqlite_repo):
        """اگر نام پروژه خالی باشد، شناسه پیش‌فرض باید 'default' باشد"""
        proj = Project(name="   ")
        pid = sqlite_repo.upsert_project(proj)
        assert pid == "default"

    def test_upsert_project_updates_existing(self, sqlite_repo):
        """بروزرسانی پروژه موجود — نام و توضیحات باید تغییر کنند"""
        proj = Project(name="تست بروزرسانی", description="توضیحات اول")
        pid = sqlite_repo.upsert_project(proj)

        # بروزرسانی با همان نام (همان slug)
        proj_updated = Project(name="تست بروزرسانی", description="توضیحات جدید")
        pid2 = sqlite_repo.upsert_project(proj_updated)
        assert pid2 == pid  # شناسه یکسان

        projects = sqlite_repo.list_projects()
        assert len(projects) == 1  # فقط یک پروژه
        assert projects[0]["description"] == "توضیحات جدید"

    # ─── list_projects ────────────────────────────────────────────

    def test_list_projects_empty_db(self, sqlite_repo):
        """پایگاه داده خالی — فهرست پروژه‌ها باید خالی باشد"""
        projects = sqlite_repo.list_projects()
        assert projects == []

    def test_list_projects_multiple(self, sqlite_repo):
        """ذخیره چند پروژه — فهرست باید همه را برگرداند"""
        proj_a = Project(name="Alpha")
        proj_b = Project(name="Beta")
        sqlite_repo.upsert_project(proj_a)
        sqlite_repo.upsert_project(proj_b)
        projects = sqlite_repo.list_projects()
        assert len(projects) == 2
        names = {p["name"] for p in projects}
        assert "Alpha" in names
        assert "Beta" in names

    # ─── load_latest ──────────────────────────────────────────────

    def test_load_latest_round_trip(self, sqlite_repo, sample_project):
        """ذخیره و بارگذاری — تمام وظایف و وابستگی‌ها باید یکسان باشند"""
        sqlite_repo.save_snapshot(sample_project)
        pid = sqlite_repo.upsert_project(sample_project)
        loaded = sqlite_repo.load_latest(pid)

        assert loaded is not None
        assert loaded.name == sample_project.name
        assert loaded.description == sample_project.description
        assert loaded.task_count == sample_project.task_count
        assert loaded.dependency_count == sample_project.dependency_count

        # بررسی تطابق وظایف
        original_tasks = list(sample_project.tasks())
        loaded_tasks = list(loaded.tasks())
        for orig, loaded_t in zip(original_tasks, loaded_tasks):
            assert orig.title == loaded_t.title
            assert orig.duration.minutes == loaded_t.duration.minutes

        # بررسی تطابق وابستگی‌ها
        original_deps = list(sample_project.dependencies())
        loaded_deps = list(loaded.dependencies())
        for orig_d, loaded_d in zip(original_deps, loaded_deps):
            assert orig_d.predecessor_id.value == loaded_d.predecessor_id.value
            assert orig_d.successor_id.value == loaded_d.successor_id.value
            assert orig_d.type == loaded_d.type

    def test_load_latest_returns_none_when_no_snapshots(self, sqlite_repo):
        """بدون اسنپشات — load_latest باید None برگرداند"""
        proj = Project(name="Empty Snapshots")
        pid = sqlite_repo.upsert_project(proj)
        # فقط پروژه ثبت شده، بدون اسنپشات
        result = sqlite_repo.load_latest(pid)
        assert result is None

    def test_load_latest_empty_db(self, sqlite_repo):
        """پایگاه داده خالی — load_latest باید None برگرداند"""
        result = sqlite_repo.load_latest("nonexistent")
        assert result is None

    def test_load_latest_with_rich_project(self, sqlite_repo, rich_project):
        """بارگذاری پروژه غنی — برچسب، منبع، PERT و وضعیت باید حفظ شوند"""
        sqlite_repo.save_snapshot(rich_project)
        pid = sqlite_repo.upsert_project(rich_project)
        loaded = sqlite_repo.load_latest(pid)

        assert loaded is not None
        tasks = list(loaded.tasks())
        # پیدا کردن وظیفه پیشرفته
        advanced = next(t for t in tasks if t.title == "وظیفه پیشرفته")
        assert advanced is not None
        assert len(advanced.tags) == 2
        tag_names = {str(t) for t in advanced.tags}
        assert "backend" in tag_names
        assert "urgent" in tag_names
        assert len(advanced.resources) == 1
        assert advanced.resources[0].resource.name == "علی"
        assert advanced.pert is not None
        assert advanced.pert.optimistic.minutes == 60
        assert advanced.status == TaskStatus.READY

    def test_load_latest_returns_most_recent(self, sqlite_repo):
        """اگر چند اسنپشات وجود داشته باشد، آخرین باید برگردد"""
        proj = Project(name="تست زمان")
        proj.add_task(Task(id=TaskId.generate(), title="وظیفه اول", duration=Duration(60)))
        sqlite_repo.save_snapshot(proj)

        # افزودن وظیفه جدید و ذخیره دوباره
        proj.add_task(Task(id=TaskId.generate(), title="وظیفه دوم", duration=Duration(120)))
        sqlite_repo.save_snapshot(proj)

        pid = sqlite_repo.upsert_project(proj)
        loaded = sqlite_repo.load_latest(pid)
        assert loaded is not None
        assert loaded.task_count == 2

    # ─── delete_project ───────────────────────────────────────────

    def test_delete_project_removes_project(self, sqlite_repo, sample_project):
        """حذف پروژه — باید از فهرست حذف شود"""
        pid = sqlite_repo.upsert_project(sample_project)
        sqlite_repo.save_snapshot(sample_project)

        sqlite_repo.delete_project(pid)
        projects = sqlite_repo.list_projects()
        assert len(projects) == 0

    def test_delete_project_removes_snapshots(self, sqlite_repo, sample_project):
        """حذف پروژه — اسنپشات‌هایش هم باید حذف شوند"""
        pid = sqlite_repo.upsert_project(sample_project)
        sqlite_repo.save_snapshot(sample_project)

        sqlite_repo.delete_project(pid)
        # بارگذاری اسنپشات باید None برگرداند
        result = sqlite_repo.load_latest(pid)
        assert result is None

    def test_delete_nonexistent_project_does_not_error(self, sqlite_repo):
        """حذف پروژه ناموجود — نباید خطا بدهد"""
        # این عملیات باید بدون خطا انجام شود
        sqlite_repo.delete_project("nonexistent_id")

    # ─── save_snapshot / load_snapshot ────────────────────────────

    def test_save_snapshot_returns_integer_id(self, sqlite_repo, sample_project):
        """ذخیره اسنپشات — باید شناسه عددی صحیح برگرداند"""
        sid = sqlite_repo.save_snapshot(sample_project)
        assert isinstance(sid, int)
        assert sid > 0

    def test_load_snapshot_by_id(self, sqlite_repo, sample_project):
        """بارگذاری اسنپشات با شناسه — باید پروژه صحیح برگرداند"""
        sid = sqlite_repo.save_snapshot(sample_project)
        loaded = sqlite_repo.load_snapshot(sid)
        assert loaded is not None
        assert loaded.name == sample_project.name

    def test_load_snapshot_nonexistent_returns_none(self, sqlite_repo):
        """بارگذاری اسنپشات ناموجود — باید None برگرداند"""
        result = sqlite_repo.load_snapshot(99999)
        assert result is None

    def test_save_snapshot_with_different_kinds(self, sqlite_repo, sample_project):
        """ذخیره اسنپشات با انواع مختلف — manual, autosave, undo"""
        pid = sqlite_repo.upsert_project(sample_project)
        sid1 = sqlite_repo.save_snapshot(sample_project, kind="manual")
        sid2 = sqlite_repo.save_snapshot(sample_project, kind="autosave")
        sid3 = sqlite_repo.save_snapshot(sample_project, kind="undo")

        snapshots = sqlite_repo.list_snapshots(pid)
        assert len(snapshots) == 3
        kinds = {s.kind for s in snapshots}
        assert "manual" in kinds
        assert "autosave" in kinds
        assert "undo" in kinds

    # ─── list_snapshots ──────────────────────────────────────────

    def test_list_snapshots_returns_snapshot_info(self, sqlite_repo, sample_project):
        """فهرست اسنپشات‌ها — باید SnapshotInfo با فیلدهای صحیح برگرداند"""
        pid = sqlite_repo.upsert_project(sample_project)
        sqlite_repo.save_snapshot(sample_project)

        snapshots = sqlite_repo.list_snapshots(pid)
        assert len(snapshots) == 1
        info = snapshots[0]
        assert isinstance(info, SnapshotInfo)
        assert isinstance(info.id, int)
        assert info.project_id == pid
        assert isinstance(info.saved_at, datetime)
        assert info.kind == "manual"

    def test_list_snapshots_empty(self, sqlite_repo):
        """فهرست اسنپشات‌ها بدون ذخیره — باید خالی باشد"""
        pid = sqlite_repo.upsert_project(Project(name="NoSnap"))
        snapshots = sqlite_repo.list_snapshots(pid)
        assert snapshots == []

    def test_list_snapshots_limit(self, sqlite_repo, sample_project):
        """فهرست اسنپشات‌ها با محدودیت تعداد"""
        pid = sqlite_repo.upsert_project(sample_project)
        for _ in range(10):
            sqlite_repo.save_snapshot(sample_project)

        # محدودیت ۵
        snapshots = sqlite_repo.list_snapshots(pid, limit=5)
        assert len(snapshots) == 5

    def test_list_snapshots_ordered_by_time_desc(self, sqlite_repo, sample_project):
        """فهرست اسنپشات‌ها — باید به ترتیب زمان نزولی مرتب شده باشد"""
        pid = sqlite_repo.upsert_project(sample_project)
        import time
        sid1 = sqlite_repo.save_snapshot(sample_project)
        time.sleep(0.01)  # تاخیر کوچک برای تفاوت زمان
        sid2 = sqlite_repo.save_snapshot(sample_project)

        snapshots = sqlite_repo.list_snapshots(pid)
        assert len(snapshots) == 2
        # اسنپشات جدیدتر باید اول باشد
        assert snapshots[0].id == sid2
        assert snapshots[1].id == sid1

    # ─── close ────────────────────────────────────────────────────

    def test_close_does_not_error(self, sqlite_repo):
        """بستن مخزن — نباید خطا بدهد"""
        sqlite_repo.close()

    # ─── Edge Cases ───────────────────────────────────────────────

    def test_empty_db_load_latest_returns_none(self, sqlite_repo):
        """پایگاه داده خالی — load_latest باید None برگرداند"""
        assert sqlite_repo.load_latest("anything") is None

    def test_empty_db_list_projects_returns_empty(self, sqlite_repo):
        """پایگاه داده خالی — list_projects باید لیست خالی برگرداند"""
        assert sqlite_repo.list_projects() == []

    def test_project_with_no_tasks_round_trip(self, sqlite_repo):
        """پروژه بدون وظیفه — ذخیره و بارگذاری باید کار کند"""
        proj = Project(name="Empty Project", description="بدون وظیفه")
        sqlite_repo.save_snapshot(proj)
        pid = sqlite_repo.upsert_project(proj)
        loaded = sqlite_repo.load_latest(pid)

        assert loaded is not None
        assert loaded.task_count == 0
        assert loaded.dependency_count == 0
        assert loaded.name == "Empty Project"

    def test_multiple_projects_isolated(self, sqlite_repo):
        """چند پروژه — اسنپشات‌ها باید از هم ایزوله باشند"""
        proj_a = Project(name="Project A")
        proj_a.add_task(Task(id=TaskId.generate(), title="وظیفه الف", duration=Duration(60)))

        proj_b = Project(name="Project B")
        proj_b.add_task(Task(id=TaskId.generate(), title="وظیفه ب", duration=Duration(120)))

        sqlite_repo.save_snapshot(proj_a)
        sqlite_repo.save_snapshot(proj_b)

        pid_a = sqlite_repo.upsert_project(proj_a)
        pid_b = sqlite_repo.upsert_project(proj_b)

        loaded_a = sqlite_repo.load_latest(pid_a)
        loaded_b = sqlite_repo.load_latest(pid_b)

        assert loaded_a is not None
        assert loaded_b is not None
        assert loaded_a.task_count == 1
        assert loaded_b.task_count == 1
        assert list(loaded_a.tasks())[0].title == "وظیفه الف"
        assert list(loaded_b.tasks())[0].title == "وظیفه ب"


# ═══════════════════════════════════════════════════════════════════
#  تست‌های سریال‌سازها
# ═══════════════════════════════════════════════════════════════════


class TestSerializers:
    """تست‌های سریال‌سازهای فایل JSON، CSV و Mermaid"""

    # ─── export_to_json / import_from_json ────────────────────────

    def test_json_round_trip(self, sample_project, tmp_dir):
        """ذخیره و بارگذاری JSON — تمام وظایف و وابستگی‌ها باید یکسان باشند"""
        path = Path(tmp_dir) / "project.json"
        result_path = export_to_json(sample_project, path)

        assert result_path == path
        assert path.exists()

        loaded = import_from_json(path)
        assert loaded.name == sample_project.name
        assert loaded.description == sample_project.description
        assert loaded.task_count == sample_project.task_count
        assert loaded.dependency_count == sample_project.dependency_count

    def test_json_round_trip_preserves_tasks(self, sample_project, tmp_dir):
        """ذخیره و بارگذاری JSON — وظایف باید دقیقاً حفظ شوند"""
        path = Path(tmp_dir) / "project.json"
        export_to_json(sample_project, path)
        loaded = import_from_json(path)

        original_tasks = sorted(list(sample_project.tasks()), key=lambda t: t.title)
        loaded_tasks = sorted(list(loaded.tasks()), key=lambda t: t.title)

        for orig, loaded_t in zip(original_tasks, loaded_tasks):
            assert orig.title == loaded_t.title
            assert orig.duration.minutes == loaded_t.duration.minutes

    def test_json_round_trip_preserves_deps(self, sample_project, tmp_dir):
        """ذخیره و بارگذاری JSON — وابستگی‌ها باید دقیقاً حفظ شوند"""
        path = Path(tmp_dir) / "project.json"
        export_to_json(sample_project, path)
        loaded = import_from_json(path)

        original_deps = list(sample_project.dependencies())
        loaded_deps = list(loaded.dependencies())
        assert len(original_deps) == len(loaded_deps)

        for orig_d, loaded_d in zip(original_deps, loaded_deps):
            assert orig_d.predecessor_id.value == loaded_d.predecessor_id.value
            assert orig_d.successor_id.value == loaded_d.successor_id.value
            assert orig_d.type == loaded_d.type
            assert orig_d.lag.minutes == loaded_d.lag.minutes

    def test_json_round_trip_rich_project(self, rich_project, tmp_dir):
        """ذخیره و بارگذاری JSON پروژه غنی — برچسب، منبع، PERT"""
        path = Path(tmp_dir) / "rich.json"
        export_to_json(rich_project, path)
        loaded = import_from_json(path)

        tasks = list(loaded.tasks())
        advanced = next(t for t in tasks if t.title == "وظیفه پیشرفته")
        assert advanced is not None
        assert len(advanced.tags) == 2
        assert len(advanced.resources) == 1
        assert advanced.pert is not None
        assert advanced.pert.optimistic.minutes == 60
        assert advanced.status == TaskStatus.READY

    def test_json_creates_parent_dirs(self, tmp_dir):
        """خروجی JSON — باید دایرکتوری‌های والد را بسازد"""
        deep_path = Path(tmp_dir) / "a" / "b" / "c" / "project.json"
        proj = Project(name="Deep Path")
        result = export_to_json(proj, deep_path)
        assert result.exists()

    def test_json_file_is_valid_utf8(self, sample_project, tmp_dir):
        """خروجی JSON — باید فایل UTF-8 معتبر باشد"""
        path = Path(tmp_dir) / "utf8.json"
        export_to_json(sample_project, path)
        # باید بدون خطا خوانده شود
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        assert isinstance(data, dict)
        assert "tasks" in data
        assert "dependencies" in data

    def test_json_empty_project(self, tmp_dir):
        """ذخیره پروژه خالی به JSON"""
        proj = Project(name="خالی")
        path = Path(tmp_dir) / "empty.json"
        export_to_json(proj, path)
        loaded = import_from_json(path)
        assert loaded.task_count == 0
        assert loaded.dependency_count == 0
        assert loaded.name == "خالی"

    # ─── export_to_csv_tasks ──────────────────────────────────────

    def test_csv_tasks_writes_valid_csv(self, sample_project, tmp_dir):
        """خروجی CSV وظایف — باید فایل CSV معتبر باشد"""
        path = Path(tmp_dir) / "tasks.csv"
        result_path = export_to_csv_tasks(sample_project, path)

        assert result_path == path
        assert path.exists()

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # هدر + ۳ وظیفه
        assert len(rows) == 4
        # بررسی هدر
        header = rows[0]
        assert "id" in header
        assert "title" in header
        assert "duration_minutes" in header
        assert "priority" in header
        assert "status" in header

    def test_csv_tasks_contains_task_data(self, sample_project, tmp_dir):
        """خروجی CSV وظایف — باید داده‌های وظایف را شامل شود"""
        path = Path(tmp_dir) / "tasks.csv"
        export_to_csv_tasks(sample_project, path)

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # بررسی وجود عناوین وظایف
        task_titles = [row[1] for row in rows[1:]]  # ستون عنوان
        assert "طراحی UI" in task_titles
        assert "پیاده‌سازی" in task_titles
        assert "تست" in task_titles

    def test_csv_tasks_with_tags(self, rich_project, tmp_dir):
        """خروجی CSV وظایف — برچسب‌ها باید با | جدا شده باشند"""
        path = Path(tmp_dir) / "tasks_tags.csv"
        export_to_csv_tasks(rich_project, path)

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # پیدا کردن ستون tags
        header = rows[0]
        tags_col = header.index("tags")
        # وظیفه پیشرفته (ردیف اول داده)
        tags_val = rows[1][tags_col]
        assert "backend" in tags_val
        assert "urgent" in tags_val

    def test_csv_tasks_empty_project(self, tmp_dir):
        """خروجی CSV وظایف — پروژه بدون وظیفه فقط هدر"""
        proj = Project(name="خالی")
        path = Path(tmp_dir) / "empty_tasks.csv"
        export_to_csv_tasks(proj, path)

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # فقط هدر
        assert len(rows) == 1

    def test_csv_tasks_creates_parent_dirs(self, tmp_dir):
        """خروجی CSV وظایف — باید دایرکتوری‌های والد را بسازد"""
        deep_path = Path(tmp_dir) / "x" / "y" / "tasks.csv"
        proj = Project(name="Deep")
        result = export_to_csv_tasks(proj, deep_path)
        assert result.exists()

    # ─── export_to_csv_deps ───────────────────────────────────────

    def test_csv_deps_writes_valid_csv(self, sample_project, tmp_dir):
        """خروجی CSV وابستگی‌ها — باید فایل CSV معتبر باشد"""
        path = Path(tmp_dir) / "deps.csv"
        result_path = export_to_csv_deps(sample_project, path)

        assert result_path == path
        assert path.exists()

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # هدر + ۲ وابستگی
        assert len(rows) == 3
        # بررسی هدر
        header = rows[0]
        assert "predecessor" in header
        assert "successor" in header
        assert "type" in header
        assert "lag_minutes" in header

    def test_csv_deps_contains_dependency_data(self, sample_project, tmp_dir):
        """خروجی CSV وابستگی‌ها — باید نوع وابستگی FS را شامل شود"""
        path = Path(tmp_dir) / "deps.csv"
        export_to_csv_deps(sample_project, path)

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # همه وابستگی‌ها باید FS باشند
        type_col = rows[0].index("type")
        for row in rows[1:]:
            assert row[type_col] == "FS"

    def test_csv_deps_empty_project(self, tmp_dir):
        """خروجی CSV وابستگی‌ها — پروژه بدون وابستگی فقط هدر"""
        proj = Project(name="بدون وابستگی")
        proj.add_task(Task(id=TaskId.generate(), title="وظیفه", duration=Duration(60)))
        path = Path(tmp_dir) / "empty_deps.csv"
        export_to_csv_deps(proj, path)

        with path.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # فقط هدر
        assert len(rows) == 1

    # ─── export_to_mermaid ────────────────────────────────────────

    def test_mermaid_writes_valid_text(self, sample_project, tmp_dir):
        """خروجی Mermaid — باید متن نمودار معتبر باشد"""
        path = Path(tmp_dir) / "diagram.mmd"
        result_path = export_to_mermaid(sample_project, path)

        assert result_path == path
        assert path.exists()

        content = path.read_text(encoding="utf-8")
        assert "flowchart LR" in content

    def test_mermaid_contains_task_nodes(self, sample_project, tmp_dir):
        """خروجی Mermaid — باید گره‌های وظایف را شامل شود"""
        path = Path(tmp_dir) / "diagram.mmd"
        export_to_mermaid(sample_project, path)
        content = path.read_text(encoding="utf-8")

        # عناوین وظایف باید در نمودار باشند
        assert "طراحی UI" in content
        assert "پیاده‌سازی" in content
        assert "تست" in content

    def test_mermaid_contains_edges(self, sample_project, tmp_dir):
        """خروجی Mermaid — باید یال‌های وابستگی را شامل شود"""
        path = Path(tmp_dir) / "diagram.mmd"
        export_to_mermaid(sample_project, path)
        content = path.read_text(encoding="utf-8")

        # باید حداقل دو یال FS وجود داشته باشد
        assert content.count("FS") >= 2

    def test_mermaid_empty_project(self, tmp_dir):
        """خروجی Mermaid — پروژه بدون وظیفه فقط هدر flowchart"""
        proj = Project(name="خالی")
        path = Path(tmp_dir) / "empty.mmd"
        export_to_mermaid(proj, path)
        content = path.read_text(encoding="utf-8")

        lines = [l for l in content.strip().split("\n") if l.strip()]
        # فقط خط flowchart LR
        assert len(lines) == 1
        assert "flowchart LR" in lines[0]

    def test_mermaid_critical_task_shaping(self, tmp_dir):
        """خروجی Mermaid — وظایف بحرانی باید شکل متفاوت داشته باشند"""
        proj = Project(name="بحرانی")
        t1 = proj.add_task(Task(id=TaskId.generate(), title="وظیفه بحرانی", duration=Duration(60)))
        t2 = proj.add_task(Task(id=TaskId.generate(), title="وظیفه عادی", duration=Duration(120)))

        # تنظیم وظیفه بحرانی با slack صفر
        t1.slack = Slack(total_slack=Duration(0), free_slack=Duration(0))
        # وظیفه عادی بدون slack
        proj.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))

        path = Path(tmp_dir) / "critical.mmd"
        export_to_mermaid(proj, path)
        content = path.read_text(encoding="utf-8")

        # وظیفه بحرانی باید شکل ([...]) داشته باشد
        assert "([" in content
        assert "])" in content

    def test_mermaid_creates_parent_dirs(self, tmp_dir):
        """خروجی Mermaid — باید دایرکتوری‌های والد را بسازد"""
        deep_path = Path(tmp_dir) / "a" / "b" / "diagram.mmd"
        proj = Project(name="Deep")
        result = export_to_mermaid(proj, deep_path)
        assert result.exists()


# ═══════════════════════════════════════════════════════════════════
#  تست‌های CalendarRepository
# ═══════════════════════════════════════════════════════════════════


class TestCalendarRepository:
    """تست‌های مخزن SQLite تقویم"""

    # ─── save / load_latest ───────────────────────────────────────

    def test_save_and_load_round_trip(self, calendar_repo):
        """ذخیره و بارگذاری تقویم — باید داده‌ها را حفظ کند"""
        store = CalendarStore()
        # اضافه کردن یک رویداد به تقویم پیش‌فرض
        default_cal = store.get_calendar("cal-default")
        assert default_cal is not None
        store.create_event(
            calendar_id="cal-default",
            title="جلسه تیمی",
            start=datetime(2025, 3, 21, 10, 0),
            end=datetime(2025, 3, 21, 11, 0),
        )

        sid = calendar_repo.save(store)
        assert isinstance(sid, int)
        assert sid > 0

        loaded = calendar_repo.load_latest()
        assert loaded is not None
        assert loaded.calendar_count == store.calendar_count
        assert loaded.event_count == store.event_count

    def test_save_and_load_preserves_calendars(self, calendar_repo):
        """ذخیره و بارگذاری — تقویم‌ها باید حفظ شوند"""
        store = CalendarStore()
        store.create_calendar("کار", color="#5A7FA8")
        store.create_calendar("شخصی", color="#5A8A5A")

        calendar_repo.save(store)
        loaded = calendar_repo.load_latest()

        assert loaded is not None
        # تقویم پیش‌فرض + ۲ تقویم جدید
        assert loaded.calendar_count == 3
        cal_names = {c.name for c in loaded.calendars()}
        assert "کار" in cal_names
        assert "شخصی" in cal_names

    def test_save_and_load_preserves_events(self, calendar_repo):
        """ذخیره و بارگذاری — رویدادها باید حفظ شوند"""
        store = CalendarStore()
        evt = store.create_event(
            calendar_id="cal-default",
            title="جلسه مهم",
            start=datetime(2025, 6, 15, 14, 0),
            end=datetime(2025, 6, 15, 15, 30),
        )

        calendar_repo.save(store)
        loaded = calendar_repo.load_latest()

        assert loaded is not None
        events = list(loaded.events())
        assert len(events) == 1
        assert events[0].title == "جلسه مهم"

    def test_load_latest_empty_db_returns_none(self, calendar_repo):
        """پایگاه داده خالی — load_latest باید None برگرداند"""
        result = calendar_repo.load_latest()
        assert result is None

    def test_save_returns_snapshot_id(self, calendar_repo):
        """ذخیره — باید شناسه عددی صحیح برگرداند"""
        store = CalendarStore()
        sid = calendar_repo.save(store)
        assert isinstance(sid, int)
        assert sid > 0

    def test_save_with_different_kinds(self, calendar_repo):
        """ذخیره با انواع مختلف — manual و autosave"""
        store = CalendarStore()
        sid1 = calendar_repo.save(store, kind="manual")
        sid2 = calendar_repo.save(store, kind="autosave")

        assert isinstance(sid1, int)
        assert isinstance(sid2, int)
        assert sid1 != sid2

    # ─── has_snapshot ─────────────────────────────────────────────

    def test_has_snapshot_false_when_empty(self, calendar_repo):
        """بدون اسنپشات — has_snapshot باید False باشد"""
        assert calendar_repo.has_snapshot() is False

    def test_has_snapshot_true_after_save(self, calendar_repo):
        """بعد از ذخیره — has_snapshot باید True باشد"""
        store = CalendarStore()
        calendar_repo.save(store)
        assert calendar_repo.has_snapshot() is True

    # ─── Autosave pruning ─────────────────────────────────────────

    def test_autosave_pruning_keeps_latest_five(self, calendar_repo):
        """هرس خودکار — فقط ۵ اسنپشات autosave اخیر باید باقی بمانند"""
        store = CalendarStore()
        # ذخیره ۱۰ اسنپشات autosave
        for _ in range(10):
            calendar_repo.save(store, kind="autosave")

        # ذخیره یک اسنپشات manual
        calendar_repo.save(store, kind="manual")

        # بارگذاری آخرین اسنپشات — باید موفق باشد
        loaded = calendar_repo.load_latest()
        assert loaded is not None

    # ─── close ────────────────────────────────────────────────────

    def test_close_does_not_error(self, calendar_repo):
        """بستن مخزن تقویم — نباید خطا بدهد"""
        calendar_repo.close()

    # ─── Edge Cases ───────────────────────────────────────────────

    def test_load_latest_returns_most_recent(self, calendar_repo):
        """اگر چند اسنپشات وجود داشته باشد، آخرین باید برگردد"""
        store1 = CalendarStore()
        store1.create_calendar("تقویم اول", color="#5A7FA8")
        calendar_repo.save(store1)

        store2 = CalendarStore()
        store2.create_calendar("تقویم دوم", color="#5A8A5A")
        calendar_repo.save(store2)

        loaded = calendar_repo.load_latest()
        assert loaded is not None
        cal_names = {c.name for c in loaded.calendars()}
        # آخرین ذخیره باید تقویم دوم را داشته باشد
        assert "تقویم دوم" in cal_names

    def test_round_trip_with_multiple_calendars_and_events(self, calendar_repo):
        """ذخیره و بارگذاری با چند تقویم و رویداد"""
        store = CalendarStore()
        cal_work = store.create_calendar("کار", color="#5A7FA8")
        cal_personal = store.create_calendar("شخصی", color="#5A8A5A")

        store.create_event(
            calendar_id=cal_work.id,
            title="جلسه صبح",
            start=datetime(2025, 3, 21, 9, 0),
            end=datetime(2025, 3, 21, 10, 0),
        )
        store.create_event(
            calendar_id=cal_personal.id,
            title="ناهار",
            start=datetime(2025, 3, 21, 12, 0),
            end=datetime(2025, 3, 21, 13, 0),
        )

        calendar_repo.save(store)
        loaded = calendar_repo.load_latest()

        assert loaded is not None
        assert loaded.calendar_count == 3  # پیش‌فرض + کار + شخصی
        assert loaded.event_count == 2

    def test_default_calendar_preserved(self, calendar_repo):
        """بعد از بارگذاری — تقویم پیش‌فرض باید حفظ شود"""
        store = CalendarStore()
        calendar_repo.save(store)
        loaded = calendar_repo.load_latest()

        assert loaded is not None
        default_cals = [c for c in loaded.calendars() if c.is_default]
        assert len(default_cals) >= 1
