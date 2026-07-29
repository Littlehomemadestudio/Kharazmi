"""تنظیمات مشترک تست — فیکسچرها و کمک‌کننده‌ها"""

import sys
import os
import tempfile
from datetime import datetime, timedelta

# اضافه کردن مسیر پروژه به sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from kharazmi.core.task import Task
from kharazmi.core.project import Project
from kharazmi.core.dependency import Dependency
from kharazmi.core.value_objects import (
    TaskId, Duration, Progress, PertEstimate,
    Tag, Resource, ResourceAllocation, Slack, TimeWindow,
)
from kharazmi.core.enums import TaskStatus, DependencyType, RiskLevel, Priority, DurationUnit
from kharazmi.commands.undo_stack import UndoStack
from kharazmi.services.scheduling_service import SchedulingService
from kharazmi.services.task_service import TaskService


# ─── فیکسچرهای پایه ───────────────────────────────────────────


@pytest.fixture
def project():
    """پروژه خالی برای تست"""
    return Project(name="تست پروژه", description="پروژه آزمایشی")


@pytest.fixture
def project_with_tasks(project):
    """پروژه با ۴ وظیفه و وابستگی‌های زنجیره‌ای"""
    t1 = project.create_task("طراحی", duration=Duration(480))   # ۱ روز
    t2 = project.create_task("پیاده‌سازی", duration=Duration(960))  # ۲ روز
    t3 = project.create_task("تست", duration=Duration(480))      # ۱ روز
    t4 = project.create_task("استقرار", duration=Duration(240))   # ۰.۵ روز
    project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(t2.id, t3.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(t3.id, t4.id, DependencyType.FINISH_START))
    return project


@pytest.fixture
def project_with_parallel(project):
    """پروژه با مسیرهای موازی برای تست مسیر بحرانی"""
    t1 = project.create_task("شروع", duration=Duration(480))
    t2 = project.create_task("مسیر الف", duration=Duration(1440))  # ۳ روز — مسیر بحرانی
    t3 = project.create_task("مسیر ب", duration=Duration(480))      # ۱ روز
    t4 = project.create_task("پایان", duration=Duration(240))
    project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(t1.id, t3.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(t2.id, t4.id, DependencyType.FINISH_START))
    project.add_dependency(Dependency(t3.id, t4.id, DependencyType.FINISH_START))
    return project


@pytest.fixture
def undo_stack():
    """پشته خنثی‌سازی خالی"""
    return UndoStack(limit=50)


@pytest.fixture
def task_service(project_with_tasks, undo_stack):
    """سرویس وظایف با پروژه و پشته خنثی‌سازی"""
    scheduling = SchedulingService(project_with_tasks)
    return TaskService(project_with_tasks, undo_stack, scheduling)


@pytest.fixture
def scheduling_service(project_with_tasks):
    """سرویس زمان‌بندی"""
    return SchedulingService(project_with_tasks)


@pytest.fixture
def tmp_dir():
    """دایرکتوری موقت برای تست‌های فایل"""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_task():
    """وظیفه نمونه برای تست"""
    return Task(
        id=TaskId.generate(),
        title="وظیفه نمونه",
        description="توضیحات تست",
        duration=Duration.of(2, DurationUnit.DAY),
        priority=Priority.HIGH,
    )


# ─── کمک‌کننده‌ها ─────────────────────────────────────────────


def make_task(project, title="وظیفه", duration_minutes=480, **kwargs):
    """ساخت وظیفه و اضافه کردن به پروژه"""
    return project.create_task(title, duration=Duration(duration_minutes), **kwargs)


def make_chain(project, n=3, duration_minutes=480):
    """ساخت زنجیره‌ای از n وظیفه با وابستگی FS"""
    tasks = [project.create_task(f"وظیفه {i+1}", duration=Duration(duration_minutes)) for i in range(n)]
    for i in range(n - 1):
        project.add_dependency(Dependency(tasks[i].id, tasks[i+1].id, DependencyType.FINISH_START))
    return tasks
