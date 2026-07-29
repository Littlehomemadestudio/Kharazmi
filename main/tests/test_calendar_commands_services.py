"""
تست‌های جامع برای زیرسیستم‌های تقویم، فرمان‌ها و سرویس‌ها

این ماژول تست‌های زیر را پوشش می‌دهد:
- تقویم: Event, RecurrenceRule, Calendar, CalendarStore
- فرمان‌ها: UndoStack, CreateTaskCommand, DeleteTaskCommand, ...
- سرویس‌ها: TaskService, SchedulingService, LocalAdvisor
"""

import pytest
from datetime import datetime, timedelta

# ─── واردات تقویم ─────────────────────────────────────────────
from kharazmi.calendar.event import Event
from kharazmi.calendar.recurrence import RecurrenceRule, ByDay, PRESET_RULES
from kharazmi.calendar.calendar import Calendar
from kharazmi.calendar.store import (
    CalendarStore,
    CalendarAdded, CalendarRemoved, CalendarUpdated,
    CalendarVisibilityChanged,
    EventAdded, EventUpdated, EventRemoved,
)
from kharazmi.calendar.enums import (
    EventType, Availability, EventStatus,
    RecurrenceFrequency, Weekday, ReminderMethod, AttendeeStatus,
)
from kharazmi.calendar.attendees import Reminder, Attendee

# ─── واردات فرمان‌ها ──────────────────────────────────────────
from kharazmi.commands.base import Command
from kharazmi.commands.undo_stack import UndoStack
from kharazmi.commands.task_commands import (
    CreateTaskCommand, DeleteTaskCommand, UpdateTaskCommand,
    MoveTaskCommand, ChangeStatusCommand,
    AddDependencyCommand, RemoveDependencyCommand,
)

# ─── واردات سرویس‌ها ──────────────────────────────────────────
from kharazmi.services.task_service import TaskService
from kharazmi.services.scheduling_service import SchedulingService
from kharazmi.services.advisor import LocalAdvisor, Advice

# ─── واردات هسته ──────────────────────────────────────────────
from kharazmi.core.task import Task
from kharazmi.core.project import Project
from kharazmi.core.dependency import Dependency
from kharazmi.core.value_objects import (
    TaskId, Duration, Progress, PertEstimate,
    Tag, Resource, ResourceAllocation, Slack,
)
from kharazmi.core.enums import TaskStatus, DependencyType, RiskLevel, Priority


# ═══════════════════════════════════════════════════════════════
#  تست‌های Event
# ═══════════════════════════════════════════════════════════════

class TestEvent:
    """تست‌های مربوط به موجودیت رویداد"""

    # ساخت رویداد با متد create
    def test_create_basic(self):
        """ساخت رویداد ساده با create()"""
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(calendar_id="cal-1", title="جلسه", start=start)
        assert evt.id.startswith("evt-")
        assert evt.calendar_id == "cal-1"
        assert evt.title == "جلسه"
        assert evt.start == start
        assert evt.end == start + timedelta(hours=1)

    # ساخت رویداد با زمان پایان مشخص
    def test_create_with_end(self):
        """ساخت رویداد با زمان پایان مشخص‌شده"""
        start = datetime(2024, 6, 15, 10, 0)
        end = datetime(2024, 6, 15, 12, 0)
        evt = Event.create(calendar_id="cal-1", title="کارگاه", start=start, end=end)
        assert evt.end == end

    # ساخت رویداد با کلمات کلیدی اضافی
    def test_create_with_kwargs(self):
        """ساخت رویداد با پارامترهای اضافی"""
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(
            calendar_id="cal-1", title="تست",
            start=start, event_type=EventType.TASK, location="اتاق ۱"
        )
        assert evt.event_type == EventType.TASK
        assert evt.location == "اتاق ۱"

    # اصلاح زمان پایان قبل از شروع
    def test_post_init_fixes_end_before_start(self):
        """اگر پایان قبل از شروع باشد، یک ساعت اضافه می‌شود"""
        start = datetime(2024, 6, 15, 10, 0)
        end = datetime(2024, 6, 15, 9, 0)  # قبل از شروع
        evt = Event(id="evt-test", calendar_id="cal-1", title="تست", start=start, end=end)
        assert evt.end == start + timedelta(hours=1)

    # تولید شناسه خودکار
    def test_post_init_generates_id(self):
        """اگر شناسه خالی باشد، شناسه خودکار تولید می‌شود"""
        evt = Event(id="", calendar_id="cal-1", title="تست")
        assert evt.id.startswith("evt-")

    # تنظیم زمان شروع و پایان
    def test_set_time(self):
        """تنظیم زمان شروع و پایان رویداد"""
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(calendar_id="cal-1", title="تست", start=start)
        new_start = datetime(2024, 6, 16, 14, 0)
        new_end = datetime(2024, 6, 16, 16, 0)
        evt.set_time(new_start, new_end)
        assert evt.start == new_start
        assert evt.end == new_end

    # خطای پایان قبل از شروع در set_time
    def test_set_time_raises_if_end_before_start(self):
        """خطا اگر پایان قبل از شروع باشد"""
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(calendar_id="cal-1", title="تست", start=start)
        with pytest.raises(ValueError, match="end precedes start"):
            evt.set_time(datetime(2024, 6, 16, 10, 0), datetime(2024, 6, 16, 9, 0))

    # جابجایی رویداد
    def test_move_to(self):
        """جابجایی رویداد به زمان شروع جدید با حفظ مدت"""
        start = datetime(2024, 6, 15, 10, 0)
        end = datetime(2024, 6, 15, 12, 0)
        evt = Event.create(calendar_id="cal-1", title="تست", start=start, end=end)
        new_start = datetime(2024, 6, 16, 14, 0)
        evt.move_to(new_start)
        assert evt.start == new_start
        assert evt.end == new_start + timedelta(hours=2)

    # تنظیم مدت زمان
    def test_set_duration(self):
        """تنظیم مدت زمان رویداد به دقیقه"""
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(calendar_id="cal-1", title="تست", start=start)
        evt.set_duration(90)
        assert evt.end == start + timedelta(minutes=90)

    # افزودن شرکت‌کننده
    def test_add_attendee(self):
        """افزودن شرکت‌کننده به رویداد"""
        evt = Event.create(calendar_id="cal-1", title="جلسه", start=datetime(2024, 6, 15))
        a1 = Attendee(name="علی", email="ali@example.com")
        evt.add_attendee(a1)
        assert len(evt.attendees) == 1
        assert evt.attendees[0].name == "علی"

    # جایگزینی شرکت‌کننده با ایمیل تکراری
    def test_add_attendee_replaces_same_email(self):
        """افزودن شرکت‌کننده با ایمیل تکراری جایگزین قبلی می‌شود"""
        evt = Event.create(calendar_id="cal-1", title="جلسه", start=datetime(2024, 6, 15))
        a1 = Attendee(name="علی", email="ali@example.com")
        a2 = Attendee(name="علی رضایی", email="ali@example.com")
        evt.add_attendee(a1)
        evt.add_attendee(a2)
        assert len(evt.attendees) == 1
        assert evt.attendees[0].name == "علی رضایی"

    # حذف شرکت‌کننده
    def test_remove_attendee(self):
        """حذف شرکت‌کننده از رویداد"""
        evt = Event.create(calendar_id="cal-1", title="جلسه", start=datetime(2024, 6, 15))
        a1 = Attendee(name="علی", email="ali@example.com")
        evt.add_attendee(a1)
        evt.remove_attendee("ali@example.com")
        assert len(evt.attendees) == 0

    # حذف شرکت‌کننده با نام
    def test_remove_attendee_by_name(self):
        """حذف شرکت‌کننده با نام"""
        evt = Event.create(calendar_id="cal-1", title="جلسه", start=datetime(2024, 6, 15))
        a1 = Attendee(name="سارا", email="")
        evt.add_attendee(a1)
        evt.remove_attendee("سارا")
        assert len(evt.attendees) == 0

    # علامت‌گذاری تکمیل وظیفه
    def test_complete(self):
        """علامت‌گذاری رویداد وظیفه‌ای به عنوان تکمیل"""
        evt = Event.create(
            calendar_id="cal-1", title="وظیفه",
            start=datetime(2024, 6, 15), event_type=EventType.TASK
        )
        assert evt.completed is False
        evt.complete()
        assert evt.completed is True
        assert evt.status == EventStatus.CONFIRMED

    # بررسی تداخل — رویدادهای همپوشان
    def test_overlaps_true(self):
        """دو رویداد همپوشان دارند"""
        evt = Event.create(
            calendar_id="cal-1", title="تست",
            start=datetime(2024, 6, 15, 10, 0),
            end=datetime(2024, 6, 15, 12, 0),
        )
        # همپوشانی جزئی
        assert evt.overlaps(
            datetime(2024, 6, 15, 11, 0),
            datetime(2024, 6, 15, 13, 0)
        ) is True
        # همپوشانی کامل
        assert evt.overlaps(
            datetime(2024, 6, 15, 9, 0),
            datetime(2024, 6, 15, 13, 0)
        ) is True

    # بررسی تداخل — رویدادهای بدون همپوشانی
    def test_overlaps_false(self):
        """دو رویداد بدون همپوشانی"""
        evt = Event.create(
            calendar_id="cal-1", title="تست",
            start=datetime(2024, 6, 15, 10, 0),
            end=datetime(2024, 6, 15, 12, 0),
        )
        assert evt.overlaps(
            datetime(2024, 6, 15, 12, 0),
            datetime(2024, 6, 15, 14, 0)
        ) is False
        assert evt.overlaps(
            datetime(2024, 6, 15, 8, 0),
            datetime(2024, 6, 15, 10, 0)
        ) is False

    # خاصیت مدت زمان
    def test_duration_property(self):
        """محاسبه مدت زمان رویداد"""
        start = datetime(2024, 6, 15, 10, 0)
        end = datetime(2024, 6, 15, 12, 30)
        evt = Event(id="e1", calendar_id="cal-1", title="تست", start=start, end=end)
        assert evt.duration == timedelta(hours=2, minutes=30)

    # خاصیت مدت زمان به دقیقه
    def test_duration_minutes_property(self):
        """محاسبه مدت زمان به دقیقه"""
        start = datetime(2024, 6, 15, 10, 0)
        end = datetime(2024, 6, 15, 12, 30)
        evt = Event(id="e1", calendar_id="cal-1", title="تست", start=start, end=end)
        assert evt.duration_minutes == 150

    # خاصیت تکرارشونده
    def test_is_recurring(self):
        """بررسی تکرارشونده بودن رویداد"""
        evt = Event.create(calendar_id="cal-1", title="تست", start=datetime(2024, 6, 15))
        assert evt.is_recurring is False
        evt.recurrence = RecurrenceRule(freq=RecurrenceFrequency.DAILY)
        assert evt.is_recurring is True

    # خاصیت وظیفه‌ای
    def test_is_task(self):
        """بررسی وظیفه‌ای بودن رویداد"""
        evt = Event.create(calendar_id="cal-1", title="تست", start=datetime(2024, 6, 15))
        assert evt.is_task is False
        evt.event_type = EventType.TASK
        assert evt.is_task is True

    # خاصیت تمام‌روز
    def test_is_all_day(self):
        """بررسی تمام‌روز بودن رویداد"""
        evt = Event.create(calendar_id="cal-1", title="تست", start=datetime(2024, 6, 15))
        assert evt.is_all_day is False
        evt.all_day = True
        assert evt.is_all_day is True

    # خاصیت جلسه
    def test_is_meeting(self):
        """بررسی جلسه بودن رویداد — نوع MEETING یا داشتن شرکت‌کننده"""
        evt = Event.create(calendar_id="cal-1", title="تست", start=datetime(2024, 6, 15))
        assert evt.is_meeting is False
        evt.event_type = EventType.MEETING
        assert evt.is_meeting is True
        evt.event_type = EventType.NORMAL
        evt.add_attendee(Attendee(name="علی"))
        assert evt.is_meeting is True

    # سریال‌سازی و بازسازی
    def test_to_dict_from_dict_roundtrip(self):
        """بازگشت از to_dict به from_dict باید همان رویداد را بسازد"""
        start = datetime(2024, 6, 15, 10, 0)
        end = datetime(2024, 6, 15, 12, 0)
        evt = Event.create(
            calendar_id="cal-1", title="جلسه مهم",
            start=start, end=end,
            description="توضیحات",
            location="اتاق ۵",
            event_type=EventType.MEETING,
            all_day=False,
        )
        evt.add_attendee(Attendee(name="سارا", email="sara@example.com", status=AttendeeStatus.ACCEPTED))

        d = evt.to_dict()
        restored = Event.from_dict(d)

        assert restored.id == evt.id
        assert restored.calendar_id == evt.calendar_id
        assert restored.title == evt.title
        assert restored.description == evt.description
        assert restored.location == evt.location
        assert restored.start == evt.start
        assert restored.end == evt.end
        assert restored.all_day == evt.all_day
        assert restored.event_type == evt.event_type
        assert len(restored.attendees) == 1
        assert restored.attendees[0].name == "سارا"

    # بازسازی با فیلدهای ناقص
    def test_from_dict_with_missing_fields(self):
        """from_dict با فیلدهای ناقص باید مقادیر پیش‌فرض بدهد"""
        d = {"id": "e1", "calendar_id": "cal-1", "title": "تست"}
        evt = Event.from_dict(d)
        assert evt.description == ""
        assert evt.all_day is False
        assert evt.event_type == EventType.NORMAL


# ═══════════════════════════════════════════════════════════════
#  تست‌های RecurrenceRule
# ═══════════════════════════════════════════════════════════════

class TestRecurrenceRule:
    """تست‌های مربوط به قواعد تکرار"""

    # ساخت قانون روزانه
    def test_daily_creation(self):
        """ساخت قانون تکرار روزانه"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY)
        assert rule.freq == RecurrenceFrequency.DAILY
        assert rule.interval == 1

    # ساخت قانون هفتگی
    def test_weekly_creation(self):
        """ساخت قانون تکرار هفتگی"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.WEEKLY)
        assert rule.freq == RecurrenceFrequency.WEEKLY

    # ساخت قانون ماهانه
    def test_monthly_creation(self):
        """ساخت قانون تکرار ماهانه"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.MONTHLY)
        assert rule.freq == RecurrenceFrequency.MONTHLY

    # ساخت قانون سالانه
    def test_yearly_creation(self):
        """ساخت قانون تکرار سالانه"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.YEARLY)
        assert rule.freq == RecurrenceFrequency.YEARLY

    # اعتبارسنجی: فاصله باید حداقل ۱ باشد
    def test_interval_must_be_at_least_1(self):
        """فاصله تکرار باید حداقل ۱ باشد"""
        with pytest.raises(ValueError, match="interval must be >= 1"):
            RecurrenceRule(freq=RecurrenceFrequency.DAILY, interval=0)

    # اعتبارسنجی: تعداد باید حداقل ۱ باشد
    def test_count_must_be_at_least_1(self):
        """تعداد تکرار باید حداقل ۱ باشد"""
        with pytest.raises(ValueError, match="count must be >= 1"):
            RecurrenceRule(freq=RecurrenceFrequency.DAILY, count=0)

    # اعتبارسنجی: count و until انحصاری هستند
    def test_count_and_until_exclusive(self):
        """count و until نمی‌توانند همزمان باشند"""
        with pytest.raises(ValueError, match="mutually exclusive"):
            RecurrenceRule(
                freq=RecurrenceFrequency.DAILY,
                count=5,
                until=datetime(2024, 12, 31),
            )

    # بسط تکرار روزانه
    def test_expand_daily(self):
        """بسط تکرار روزانه — تولید رخدادهای صحیح"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY, count=5)
        start = datetime(2024, 6, 15, 10, 0)
        window_start = datetime(2024, 6, 15, 0, 0)
        window_end = datetime(2024, 6, 25, 23, 59)
        occurrences = list(rule.expand(start, window_start, window_end))
        assert len(occurrences) == 5
        assert occurrences[0] == start
        assert occurrences[1] == start + timedelta(days=1)
        assert occurrences[4] == start + timedelta(days=4)

    # بسط تکرار روزانه با فاصله
    def test_expand_daily_with_interval(self):
        """بسط تکرار روزانه با فاصله ۲"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY, interval=2, count=4)
        start = datetime(2024, 6, 15, 10, 0)
        window_start = datetime(2024, 6, 15, 0, 0)
        window_end = datetime(2024, 7, 15, 23, 59)
        occurrences = list(rule.expand(start, window_start, window_end))
        assert len(occurrences) == 4
        assert occurrences[0] == start
        assert occurrences[1] == start + timedelta(days=2)
        assert occurrences[2] == start + timedelta(days=4)

    # بسط تکرار هفتگی با روزهای خاص
    def test_expand_weekly_by_day(self):
        """بسط تکرار هفتگی با روزهای خاص (دوشنبه و چهارشنبه)"""
        rule = RecurrenceRule(
            freq=RecurrenceFrequency.WEEKLY,
            by_day=(ByDay(Weekday.MONDAY), ByDay(Weekday.WEDNESDAY)),
            count=6,
        )
        start = datetime(2024, 6, 10, 10, 0)  # Monday
        window_start = datetime(2024, 6, 10, 0, 0)
        window_end = datetime(2024, 7, 10, 23, 59)
        occurrences = list(rule.expand(start, window_start, window_end))
        assert len(occurrences) == 6
        # همه رخدادها باید دوشنبه یا چهارشنبه باشند
        for occ in occurrences:
            # شنبه=۵ ... پنجشنبه=3 (python weekday)
            # شنبه=0 ... پنجشنبه=6 (ایرانی)
            # دوشنبه=2 ایرانی → python weekday() = 0
            # چهارشنبه=4 ایرانی → python weekday() = 2
            assert occ.weekday() in (0, 2)  # Monday or Wednesday in Python

    # بسط تکرار با until
    def test_expand_daily_with_until(self):
        """بسط تکرار روزانه با محدودیت until"""
        rule = RecurrenceRule(
            freq=RecurrenceFrequency.DAILY,
            until=datetime(2024, 6, 19, 23, 59),
        )
        start = datetime(2024, 6, 15, 10, 0)
        window_start = datetime(2024, 6, 15, 0, 0)
        window_end = datetime(2024, 6, 30, 23, 59)
        occurrences = list(rule.expand(start, window_start, window_end))
        # 15, 16, 17, 18, 19 → 5 occurrences
        assert len(occurrences) == 5

    # تبدیل به رشته RRULE
    def test_to_rrule_str_daily(self):
        """تبدیل قانون روزانه به رشته RRULE"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY)
        s = rule.to_rrule_str()
        assert "FREQ=DAILY" in s

    # تبدیل به رشته RRULE با فاصله
    def test_to_rrule_str_with_interval(self):
        """تبدیل قانون با فاصله به رشته RRULE"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.WEEKLY, interval=2)
        s = rule.to_rrule_str()
        assert "FREQ=WEEKLY" in s
        assert "INTERVAL=2" in s

    # تبدیل به رشته RRULE با تعداد
    def test_to_rrule_str_with_count(self):
        """تبدیل قانون با تعداد به رشته RRULE"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY, count=10)
        s = rule.to_rrule_str()
        assert "COUNT=10" in s

    # تبدیل به رشته RRULE با until
    def test_to_rrule_str_with_until(self):
        """تبدیل قانون با until به رشته RRULE"""
        until = datetime(2024, 12, 31, 23, 59, 0)
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY, until=until)
        s = rule.to_rrule_str()
        assert "UNTIL=" in s

    # تبدیل به رشته RRULE با روزهای هفته
    def test_to_rrule_str_with_by_day(self):
        """تبدیل قانون با روزهای هفته به رشته RRULE"""
        rule = RecurrenceRule(
            freq=RecurrenceFrequency.WEEKLY,
            by_day=(ByDay(Weekday.MONDAY), ByDay(Weekday.FRIDAY)),
        )
        s = rule.to_rrule_str()
        assert "BYDAY=" in s

    # بازگشت از رشته RRULE
    def test_from_rrule_str_roundtrip(self):
        """بازگشت از to_rrule_str به from_rrule_str"""
        rule = RecurrenceRule(
            freq=RecurrenceFrequency.WEEKLY,
            interval=2,
            count=10,
            by_day=(ByDay(Weekday.MONDAY), ByDay(Weekday.WEDNESDAY)),
        )
        s = rule.to_rrule_str()
        restored = RecurrenceRule.from_rrule_str(s)
        assert restored.freq == RecurrenceFrequency.WEEKLY
        assert restored.interval == 2
        assert restored.count == 10
        assert len(restored.by_day) == 2

    # سریال‌سازی و بازسازی دیکشنری
    def test_to_dict_from_dict_roundtrip(self):
        """بازگشت از to_dict به from_dict"""
        rule = RecurrenceRule(
            freq=RecurrenceFrequency.DAILY,
            interval=3,
            count=7,
        )
        d = rule.to_dict()
        restored = RecurrenceRule.from_dict(d)
        assert restored.freq == RecurrenceFrequency.DAILY
        assert restored.interval == 3
        assert restored.count == 7

    # قواعد پیش‌فرض
    def test_preset_rules_exist(self):
        """بررسی وجود قواعد پیش‌فرض"""
        assert "Every day" in PRESET_RULES
        assert "Every week" in PRESET_RULES
        assert "Every month" in PRESET_RULES
        assert "Every year" in PRESET_RULES
        assert "Every weekday" in PRESET_RULES
        assert "Every 2 weeks" in PRESET_RULES
        assert "Weekends" in PRESET_RULES

    # قواعد پیش‌فرض — نوع فرکانس
    def test_preset_rules_frequency(self):
        """بررسی فرکانس قواعد پیش‌فرض"""
        assert PRESET_RULES["Every day"].freq == RecurrenceFrequency.DAILY
        assert PRESET_RULES["Every week"].freq == RecurrenceFrequency.WEEKLY
        assert PRESET_RULES["Every month"].freq == RecurrenceFrequency.MONTHLY
        assert PRESET_RULES["Every year"].freq == RecurrenceFrequency.YEARLY
        assert PRESET_RULES["Every 2 weeks"].interval == 2

    # بسط اگر شروع بعد از پنجره باشد
    def test_expand_start_after_window(self):
        """اگر شروع بعد از پنجره باشد، رخدادی تولید نمی‌شود"""
        rule = RecurrenceRule(freq=RecurrenceFrequency.DAILY, count=5)
        start = datetime(2024, 7, 15, 10, 0)
        window_start = datetime(2024, 6, 1, 0, 0)
        window_end = datetime(2024, 6, 30, 23, 59)
        occurrences = list(rule.expand(start, window_start, window_end))
        assert len(occurrences) == 0

    # from_dict بدون کلید rrule
    def test_from_dict_missing_rrule(self):
        """from_dict بدون کلید rrule باید قانون پیش‌فرض بسازد"""
        rule = RecurrenceRule.from_dict({})
        assert rule.freq == RecurrenceFrequency.WEEKLY  # default

    # ByDay نمایش رشته‌ای
    def test_by_day_str(self):
        """نمایش رشته‌ای ByDay"""
        bd = ByDay(Weekday.MONDAY)
        assert str(bd) == "MO"
        bd_with_ord = ByDay(Weekday.FRIDAY, ordinal=2)
        assert str(bd_with_ord) == "2FR"


# ═══════════════════════════════════════════════════════════════
#  تست‌های Calendar
# ═══════════════════════════════════════════════════════════════

class TestCalendarEntity:
    """تست‌های مربوط به موجودیت تقویم"""

    # ساخت تقویم با create
    def test_create(self):
        """ساخت تقویم جدید با شناسه خودکار"""
        cal = Calendar.create(name="کاری", color="#5A7FA8")
        assert cal.id.startswith("cal-")
        assert cal.name == "کاری"
        assert cal.color == "#5A7FA8"
        assert cal.visible is True
        assert cal.is_default is False

    # ساخت تقویم با توضیحات
    def test_create_with_description(self):
        """ساخت تقویم با توضیحات"""
        cal = Calendar.create(name="شخصی", description="تقویم شخصی")
        assert cal.description == "تقویم شخصی"

    # سریال‌سازی و بازسازی
    def test_to_dict_from_dict_roundtrip(self):
        """بازگشت از to_dict به from_dict"""
        cal = Calendar(
            id="cal-test", name="تست", color="#D4AF37",
            visible=True, description="تقویم تست",
            is_default=True, is_readonly=False, owner="me"
        )
        d = cal.to_dict()
        restored = Calendar.from_dict(d)
        assert restored.id == "cal-test"
        assert restored.name == "تست"
        assert restored.color == "#D4AF37"
        assert restored.visible is True
        assert restored.description == "تقویم تست"
        assert restored.is_default is True
        assert restored.is_readonly is False
        assert restored.owner == "me"

    # تولید شناسه خودکار
    def test_post_init_generates_id(self):
        """اگر شناسه خالی باشد، شناسه خودکار تولید می‌شود"""
        cal = Calendar(id="", name="تست")
        assert cal.id.startswith("cal-")


# ═══════════════════════════════════════════════════════════════
#  تست‌های CalendarStore
# ═══════════════════════════════════════════════════════════════

class TestCalendarStore:
    """تست‌های مربوط به مخزن تقویم"""

    # مخزن پیش‌فرض
    def test_default_calendar(self):
        """مخزن باید یک تقویم پیش‌فرض داشته باشد"""
        store = CalendarStore()
        assert store.calendar_count >= 1
        default = store.get_calendar("cal-default")
        assert default is not None
        assert default.is_default is True

    # افزودن تقویم
    def test_add_calendar(self):
        """افزودن تقویم جدید"""
        store = CalendarStore()
        cal = Calendar.create(name="کاری")
        store.add_calendar(cal)
        assert store.calendar_count == 2
        assert store.get_calendar(cal.id) is not None

    # خطای افزودن تقویم تکراری
    def test_add_duplicate_calendar_raises(self):
        """خطا هنگام افزودن تقویم با شناسه تکراری"""
        store = CalendarStore()
        cal = Calendar(id="cal-default", name="تکراری")
        with pytest.raises(ValueError, match="already exists"):
            store.add_calendar(cal)

    # ساخت و افزودن تقویم
    def test_create_calendar(self):
        """ساخت و افزودن تقویم با create_calendar"""
        store = CalendarStore()
        cal = store.create_calendar("کاری", color="#5A8A5A")
        assert cal.name == "کاری"
        assert cal.color == "#5A8A5A"
        assert store.get_calendar(cal.id) is not None

    # حذف تقویم
    def test_delete_calendar(self):
        """حذف تقویم و رویدادهایش"""
        store = CalendarStore()
        cal = store.create_calendar("موقت")
        start = datetime(2024, 6, 15, 10, 0)
        store.create_event(cal.id, "جلسه", start)
        store.delete_calendar(cal.id)
        assert store.get_calendar(cal.id) is None
        assert store.event_count == 0

    # عدم حذف تقویم پیش‌فرض
    def test_cannot_delete_default_calendar(self):
        """تقویم پیش‌فرض حذف نمی‌شود"""
        store = CalendarStore()
        store.delete_calendar("cal-default")
        assert store.get_calendar("cal-default") is not None

    # بروزرسانی تقویم
    def test_update_calendar(self):
        """بروزرسانی فیلدهای تقویم"""
        store = CalendarStore()
        store.update_calendar("cal-default", name="شخصی", color="#5A7FA8")
        cal = store.get_calendar("cal-default")
        assert cal.name == "شخصی"
        assert cal.color == "#5A7FA8"

    # تغییر وضعیت نمایش تقویم
    def test_set_calendar_visible(self):
        """تغییر وضعیت نمایش تقویم"""
        store = CalendarStore()
        store.set_calendar_visible("cal-default", False)
        cal = store.get_calendar("cal-default")
        assert cal.visible is False

    # افزودن رویداد
    def test_add_event(self):
        """افزودن رویداد به تقویم"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(calendar_id="cal-default", title="جلسه", start=start)
        store.add_event(evt)
        assert store.event_count == 1
        assert store.get_event(evt.id) is not None

    # خطای افزودن رویداد به تقویم ناموجود
    def test_add_event_unknown_calendar_raises(self):
        """خطا هنگام افزودن رویداد به تقویم ناموجود"""
        store = CalendarStore()
        evt = Event.create(calendar_id="cal-nonexistent", title="تست", start=datetime(2024, 6, 15))
        with pytest.raises(KeyError, match="does not exist"):
            store.add_event(evt)

    # خطای افزودن رویداد تکراری
    def test_add_duplicate_event_raises(self):
        """خطا هنگام افزودن رویداد با شناسه تکراری"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(calendar_id="cal-default", title="تست", start=start)
        store.add_event(evt)
        with pytest.raises(ValueError, match="already exists"):
            store.add_event(evt)

    # ساخت و افزودن رویداد
    def test_create_event(self):
        """ساخت و افزودن رویداد با create_event"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = store.create_event("cal-default", "جلسه", start)
        assert evt.title == "جلسه"
        assert store.event_count == 1

    # حذف رویداد
    def test_delete_event(self):
        """حذف رویداد"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = store.create_event("cal-default", "جلسه", start)
        store.delete_event(evt.id)
        assert store.event_count == 0
        assert store.get_event(evt.id) is None

    # بروزرسانی رویداد
    def test_update_event(self):
        """بروزرسانی فیلدهای رویداد"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = store.create_event("cal-default", "جلسه", start)
        store.update_event(evt.id, title="جلسه جدید", location="اتاق ۳")
        updated = store.get_event(evt.id)
        assert updated.title == "جلسه جدید"
        assert updated.location == "اتاق ۳"

    # رویدادها در بازه زمانی
    def test_events_in_range(self):
        """یافتن رویدادها در بازه زمانی مشخص"""
        store = CalendarStore()
        e1 = store.create_event("cal-default", "جلسه۱", datetime(2024, 6, 15, 10, 0))
        e2 = store.create_event("cal-default", "جلسه۲", datetime(2024, 6, 16, 14, 0))
        e3 = store.create_event("cal-default", "جلسه۳", datetime(2024, 6, 20, 10, 0))

        # فقط ۱۵ و ۱۶ ژوئن
        results = store.events_in_range(
            datetime(2024, 6, 15, 0, 0),
            datetime(2024, 6, 17, 0, 0),
        )
        ids = {e.id for e in results}
        assert e1.id in ids
        assert e2.id in ids
        assert e3.id not in ids

    # رویدادهای آینده
    def test_upcoming_events(self):
        """بررسی رویدادهای آینده"""
        store = CalendarStore()
        now = datetime.utcnow()
        # یک رویداد گذشته و یک رویداد آینده
        store.create_event("cal-default", "گذشته", now - timedelta(days=2))
        store.create_event("cal-default", "آینده", now + timedelta(hours=1))
        store.create_event("cal-default", "آینده۲", now + timedelta(days=2))

        upcoming = store.upcoming_events(days=7)
        titles = {e.title for e in upcoming}
        assert "آینده" in titles
        assert "آینده۲" in titles

    # جستجوی رویداد
    def test_search_by_title(self):
        """جستجوی رویداد بر اساس عنوان"""
        store = CalendarStore()
        store.create_event("cal-default", "جلسه تیمی", datetime(2024, 6, 15))
        store.create_event("cal-default", "کارگاه آموزشی", datetime(2024, 6, 16))
        store.create_event("cal-default", "مرخصی", datetime(2024, 6, 17))

        results = store.search("جلسه")
        assert len(results) == 1
        assert results[0].title == "جلسه تیمی"

    # جستجوی خالی
    def test_search_empty_query(self):
        """جستجوی با عبارت خالی"""
        store = CalendarStore()
        store.create_event("cal-default", "جلسه", datetime(2024, 6, 15))
        assert store.search("") == []

    # شنودگر CalendarAdded
    def test_listener_calendar_added(self):
        """شنودگر رویداد افزودن تقویم"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        store.create_calendar("کاری")
        assert any(isinstance(e, CalendarAdded) for e in received)

    # شنودگر EventAdded
    def test_listener_event_added(self):
        """شنودگر رویداد افزودن رویداد"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        store.create_event("cal-default", "جلسه", datetime(2024, 6, 15))
        assert any(isinstance(e, EventAdded) for e in received)

    # شنودگر EventRemoved
    def test_listener_event_removed(self):
        """شنودگر رویداد حذف رویداد"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        evt = store.create_event("cal-default", "جلسه", datetime(2024, 6, 15))
        store.delete_event(evt.id)
        assert any(isinstance(e, EventRemoved) for e in received)

    # شنودگر CalendarUpdated
    def test_listener_calendar_updated(self):
        """شنودگر رویداد بروزرسانی تقویم"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        store.update_calendar("cal-default", name="تازه")
        assert any(isinstance(e, CalendarUpdated) for e in received)

    # شنودگر CalendarVisibilityChanged
    def test_listener_calendar_visibility_changed(self):
        """شنودگر تغییر وضعیت نمایش تقویم"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        store.set_calendar_visible("cal-default", False)
        assert any(isinstance(e, CalendarVisibilityChanged) for e in received)

    # شنودگر CalendarRemoved
    def test_listener_calendar_removed(self):
        """شنودگر حذف تقویم"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        cal = store.create_calendar("موقت")
        store.delete_calendar(cal.id)
        assert any(isinstance(e, CalendarRemoved) for e in received)

    # شنودگر EventUpdated
    def test_listener_event_updated(self):
        """شنودگر بروزرسانی رویداد"""
        store = CalendarStore()
        received = []
        store.subscribe(lambda e: received.append(e))
        evt = store.create_event("cal-default", "جلسه", datetime(2024, 6, 15))
        store.update_event(evt.id, title="جلسه جدید")
        assert any(isinstance(e, EventUpdated) for e in received)

    # سریال‌سازی و بازسازی
    def test_to_dict_from_dict_roundtrip(self):
        """بازگشت از to_dict به from_dict"""
        store = CalendarStore()
        store.create_calendar("کاری", color="#5A7FA8")
        store.create_event("cal-default", "جلسه", datetime(2024, 6, 15, 10, 0))

        d = store.to_dict()
        restored = CalendarStore.from_dict(d)
        assert restored.calendar_count == 2
        assert restored.event_count == 1

    # require_calendar خطا
    def test_require_calendar_raises(self):
        """خطا در require_calendar با شناسه ناموجود"""
        store = CalendarStore()
        with pytest.raises(KeyError, match="No such calendar"):
            store.require_calendar("cal-nonexistent")

    # require_event خطا
    def test_require_event_raises(self):
        """خطا در require_event با شناسه ناموجود"""
        store = CalendarStore()
        with pytest.raises(KeyError, match="No such event"):
            store.require_event("evt-nonexistent")

    # رویدادهای لغو‌شده در events_in_range
    def test_events_in_range_excludes_cancelled(self):
        """رویدادهای لغو‌شده در events_in_range نمایش داده نمی‌شوند"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = store.create_event("cal-default", "لغو", start)
        store.update_event(evt.id, status=EventStatus.CANCELLED)
        results = store.events_in_range(
            datetime(2024, 6, 15, 0, 0),
            datetime(2024, 6, 16, 0, 0),
        )
        assert len(results) == 0

    # رویدادهای تکرارشونده در events_in_range
    def test_events_in_range_with_recurrence(self):
        """رویدادهای تکرارشونده در events_in_range بسط داده می‌شوند"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(
            calendar_id="cal-default", title="تکراری",
            start=start, end=start + timedelta(hours=1),
            recurrence=RecurrenceRule(freq=RecurrenceFrequency.DAILY, count=3),
        )
        store.add_event(evt)
        results = store.events_in_range(
            datetime(2024, 6, 15, 0, 0),
            datetime(2024, 6, 18, 0, 0),
        )
        assert len(results) == 3

    # تقویم‌های قابل نمایش
    def test_visible_calendars(self):
        """تکرارگر تقویم‌های قابل نمایش"""
        store = CalendarStore()
        cal = store.create_calendar("مخفی")
        store.set_calendar_visible(cal.id, False)
        visible = list(store.visible_calendars())
        assert all(c.visible for c in visible)

    # رویدادهای یک تقویم
    def test_events_in_calendar(self):
        """تکرارگر رویدادهای یک تقویم"""
        store = CalendarStore()
        cal = store.create_calendar("کاری")
        store.create_event("cal-default", "شخصی", datetime(2024, 6, 15))
        store.create_event(cal.id, "کاری", datetime(2024, 6, 15))
        events = list(store.events_in_calendar(cal.id))
        assert len(events) == 1
        assert events[0].title == "کاری"


# ═══════════════════════════════════════════════════════════════
#  تست‌های UndoStack
# ═══════════════════════════════════════════════════════════════

class TestUndoStack:
    """تست‌های مربوط به پشته برگشت/اجرای مجدد"""

    # فرمان ساده برای تست
    @staticmethod
    def _make_command(name="Test", data=None):
        """ساخت فرمان ساده برای تست"""
        if data is None:
            data = []
        class SimpleCommand(Command):
            def __init__(self, name, shared_data):
                super().__init__(name=name)
                self.data = shared_data
                self._executed = False
                self._undone = False

            def execute(self, project):
                self.data.append("executed")
                self._executed = True

            def undo(self, project):
                self.data.append("undone")
                self._undone = True

        return SimpleCommand(name=name, shared_data=data)

    # افزودن فرمان
    def test_push(self):
        """افزودن فرمان به پشته"""
        stack = UndoStack()
        data = []
        cmd = self._make_command(data=data)
        stack.push(cmd)
        assert stack.can_undo() is True
        assert stack.can_redo() is False

    # اجرای فرمان و افزودن
    def test_execute(self):
        """اجرای فرمان و افزودن به پشته"""
        stack = UndoStack()
        data = []
        cmd = self._make_command(data=data)
        stack.execute(cmd, project=None)
        assert "executed" in data
        assert stack.can_undo() is True

    # برگرداندن فرمان
    def test_undo(self):
        """برگرداندن آخرین فرمان"""
        stack = UndoStack()
        data = []
        cmd = self._make_command(data=data)
        stack.execute(cmd, project=None)
        result = stack.undo(project=None)
        assert result is True
        assert "undone" in data

    # برگرداندن بدون فرمان
    def test_undo_empty(self):
        """برگرداندن بدون فرمان — باید False برگرداند"""
        stack = UndoStack()
        assert stack.undo(project=None) is False

    # اجرای مجدد
    def test_redo(self):
        """اجرای مجدد فرمان برگردانده‌شده"""
        stack = UndoStack()
        data = []
        cmd = self._make_command(data=data)
        stack.execute(cmd, project=None)
        stack.undo(project=None)
        # پاک کردن data برای بررسی اجرای مجدد
        data.clear()
        result = stack.redo(project=None)
        assert result is True
        assert "executed" in data

    # اجرای مجدد بدون فرمان
    def test_redo_empty(self):
        """اجرای مجدد بدون فرمان — باید False برگرداند"""
        stack = UndoStack()
        assert stack.redo(project=None) is False

    # بررسی can_undo و can_redo
    def test_can_undo_can_redo(self):
        """بررسی وضعیت can_undo و can_redo"""
        stack = UndoStack()
        assert stack.can_undo() is False
        assert stack.can_redo() is False

        cmd = self._make_command()
        stack.execute(cmd, project=None)
        assert stack.can_undo() is True
        assert stack.can_redo() is False

        stack.undo(project=None)
        assert stack.can_undo() is False
        assert stack.can_redo() is True

    # نام فرمان بعدی برگشت
    def test_next_undo_name(self):
        """نام فرمان بعدی برگشت"""
        stack = UndoStack()
        assert stack.next_undo_name() is None
        cmd = self._make_command(name="فرمان ۱")
        stack.execute(cmd, project=None)
        assert stack.next_undo_name() == "فرمان ۱"

    # نام فرمان بعدی اجرای مجدد
    def test_next_redo_name(self):
        """نام فرمان بعدی اجرای مجدد"""
        stack = UndoStack()
        cmd = self._make_command(name="فرمان ۱")
        stack.execute(cmd, project=None)
        stack.undo(project=None)
        assert stack.next_redo_name() == "فرمان ۱"

    # پاک کردن پشته
    def test_clear(self):
        """پاک کردن پشته"""
        stack = UndoStack()
        cmd = self._make_command()
        stack.execute(cmd, project=None)
        stack.clear()
        assert stack.can_undo() is False
        assert stack.can_redo() is False

    # محدودیت اندازه پشته
    def test_limit_enforcement(self):
        """اعمال محدودیت اندازه پشته (حداکثر ۲۰۰)"""
        stack = UndoStack(limit=5)
        for i in range(10):
            stack.execute(self._make_command(name=f"فرمان {i}"), project=None)
        # فقط ۵ فرمان آخر باید باقی مانده باشد
        assert stack.can_undo() is True
        # برگرداندن ۵ بار باید ممکن باشد
        for _ in range(5):
            assert stack.undo(project=None) is True
        assert stack.undo(project=None) is False

    # حذف تاریخچه اجرای مجدد بعد از افزودن فرمان جدید
    def test_push_truncates_redo_history(self):
        """افزودن فرمان جدید بعد از برگشت، تاریخچه اجرای مجدد را حذف می‌کند"""
        stack = UndoStack()
        data1 = []
        data2 = []
        cmd1 = self._make_command(name="فرمان ۱", data=data1)
        cmd2 = self._make_command(name="فرمان ۲", data=data2)
        stack.execute(cmd1, project=None)
        stack.execute(cmd2, project=None)
        stack.undo(project=None)  # برگرداندن فرمان ۲
        assert stack.can_redo() is True

        # افزودن فرمان جدید
        cmd3 = self._make_command(name="فرمان ۳")
        stack.push(cmd3)
        assert stack.can_redo() is False

    # شنودگر تغییرات
    def test_subscribe(self):
        """شنودگر تغییرات پشته"""
        stack = UndoStack()
        notifications = []
        stack.subscribe(lambda: notifications.append(1))
        stack.execute(self._make_command(), project=None)
        assert len(notifications) == 1
        stack.undo(project=None)
        assert len(notifications) == 2


# ═══════════════════════════════════════════════════════════════
#  تست‌های TaskCommands
# ═══════════════════════════════════════════════════════════════

class TestTaskCommands:
    """تست‌های مربوط به فرمان‌های وظایف"""

    # فرمان ساخت وظیفه
    def test_create_task_command(self, project):
        """اجرای فرمان ساخت وظیفه"""
        cmd = CreateTaskCommand(title="وظیفه جدید", duration_minutes=120)
        cmd.execute(project)
        assert cmd._created_id is not None
        task = project.get_task(TaskId(cmd._created_id))
        assert task is not None
        assert task.title == "وظیفه جدید"
        assert task.duration.minutes == 120

    # برگرداندن فرمان ساخت وظیفه
    def test_create_task_command_undo(self, project):
        """برگرداندن فرمان ساخت وظیفه — وظیفه حذف می‌شود"""
        cmd = CreateTaskCommand(title="وظیفه موقت")
        cmd.execute(project)
        task_id = TaskId(cmd._created_id)
        assert project.get_task(task_id) is not None
        cmd.undo(project)
        assert project.get_task(task_id) is None

    # فرمان حذف وظیفه
    def test_delete_task_command(self, project):
        """اجرای فرمان حذف وظیفه"""
        task = project.create_task("وظیفه برای حذف")
        cmd = DeleteTaskCommand(task_id=task.id)
        cmd.execute(project)
        assert project.get_task(task.id) is None

    # برگرداندن فرمان حذف وظیفه
    def test_delete_task_command_undo(self, project):
        """برگرداندن فرمان حذف وظیفه — وظیفه بازیابی می‌شود"""
        task = project.create_task("وظیفه بازیابی")
        cmd = DeleteTaskCommand(task_id=task.id)
        cmd.execute(project)
        cmd.undo(project)
        restored = project.get_task(task.id)
        assert restored is not None
        assert restored.title == "وظیفه بازیابی"

    # حذف وظیفه با وابستگی و بازگردانی
    def test_delete_task_command_undo_with_deps(self, project):
        """حذف وظیفه با وابستگی و بازگردانی — وابستگی‌ها هم بازیابی می‌شوند"""
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
        assert project.dependency_count == 1

        cmd = DeleteTaskCommand(task_id=t1.id)
        cmd.execute(project)
        # حذف t1 باید وابستگی‌ها را هم حذف کند
        assert project.get_task(t1.id) is None
        assert project.dependency_count == 0

        cmd.undo(project)
        # t1 و وابستگی‌اش باید بازیابی شده باشند
        assert project.get_task(t1.id) is not None
        assert project.dependency_count == 1

    # فرمان بروزرسانی وظیفه
    def test_update_task_command(self, project):
        """اجرای فرمان بروزرسانی وظیفه"""
        task = project.create_task("وظیفه اصلی", duration=Duration(60))
        cmd = UpdateTaskCommand(task_id=task.id, changes={"title": "وظیفه جدید"})
        cmd.execute(project)
        assert task.title == "وظیفه جدید"

    # برگرداندن فرمان بروزرسانی
    def test_update_task_command_undo(self, project):
        """برگرداندن فرمان بروزرسانی — مقدار قبلی بازیابی می‌شود"""
        task = project.create_task("عنوان اصلی")
        cmd = UpdateTaskCommand(task_id=task.id, changes={"title": "عنوان جدید"})
        cmd.execute(project)
        assert task.title == "عنوان جدید"
        cmd.undo(project)
        assert task.title == "عنوان اصلی"

    # فرمان جابجایی وظیفه
    def test_move_task_command(self, project):
        """اجرای فرمان جابجایی وظیفه"""
        task = project.create_task("وظیفه")
        cmd = MoveTaskCommand(task_id=task.id, new_x=100.0, new_y=200.0)
        cmd.execute(project)
        assert task.x == 100.0
        assert task.y == 200.0

    # برگرداندن فرمان جابجایی
    def test_move_task_command_undo(self, project):
        """برگرداندن فرمان جابجایی — موقعیت قبلی بازیابی می‌شود"""
        task = project.create_task("وظیفه")
        task.x = 10.0
        task.y = 20.0
        cmd = MoveTaskCommand(task_id=task.id, new_x=100.0, new_y=200.0)
        cmd.execute(project)
        cmd.undo(project)
        assert task.x == 10.0
        assert task.y == 20.0

    # فرمان تغییر وضعیت
    def test_change_status_command(self, project):
        """اجرای فرمان تغییر وضعیت"""
        task = project.create_task("وظیفه")
        # DRAFT → READY
        cmd = ChangeStatusCommand(task_id=task.id, new_status=TaskStatus.READY)
        cmd.execute(project)
        assert task.status == TaskStatus.READY

    # برگرداندن فرمان تغییر وضعیت
    def test_change_status_command_undo(self, project):
        """برگرداندن فرمان تغییر وضعیت — وضعیت قبلی بازیابی می‌شود"""
        task = project.create_task("وظیفه")
        original_status = task.status  # DRAFT
        cmd = ChangeStatusCommand(task_id=task.id, new_status=TaskStatus.READY)
        cmd.execute(project)
        assert task.status == TaskStatus.READY
        cmd.undo(project)
        assert task.status == original_status

    # فرمان افزودن وابستگی
    def test_add_dependency_command(self, project):
        """اجرای فرمان افزودن وابستگی"""
        t1 = project.create_task("مقدم")
        t2 = project.create_task("جانشین")
        cmd = AddDependencyCommand(
            predecessor_id=t1.id, successor_id=t2.id,
            dep_type=DependencyType.FINISH_START,
        )
        cmd.execute(project)
        assert cmd._executed is True
        assert project.dependency_count == 1

    # برگرداندن فرمان افزودن وابستگی
    def test_add_dependency_command_undo(self, project):
        """برگرداندن فرمان افزودن وابستگی — وابستگی حذف می‌شود"""
        t1 = project.create_task("مقدم")
        t2 = project.create_task("جانشین")
        cmd = AddDependencyCommand(
            predecessor_id=t1.id, successor_id=t2.id,
            dep_type=DependencyType.FINISH_START,
        )
        cmd.execute(project)
        assert project.dependency_count == 1
        cmd.undo(project)
        assert project.dependency_count == 0

    # فرمان افزودن وابستگی چرخه‌ای
    def test_add_dependency_command_cycle(self, project):
        """فرمان افزودن وابستگی چرخه‌ای — اجرا نمی‌شود"""
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
        # تلاش برای ایجاد چرخه: t2 → t1
        cmd = AddDependencyCommand(
            predecessor_id=t2.id, successor_id=t1.id,
            dep_type=DependencyType.FINISH_START,
        )
        cmd.execute(project)
        assert cmd._executed is False

    # فرمان حذف وابستگی
    def test_remove_dependency_command(self, project):
        """اجرای فرمان حذف وابستگی"""
        t1 = project.create_task("مقدم")
        t2 = project.create_task("جانشین")
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
        assert project.dependency_count == 1

        cmd = RemoveDependencyCommand(
            predecessor_id=t1.id, successor_id=t2.id,
            dep_type=DependencyType.FINISH_START,
        )
        cmd.execute(project)
        assert project.dependency_count == 0
        assert cmd._existed is True

    # برگرداندن فرمان حذف وابستگی
    def test_remove_dependency_command_undo(self, project):
        """برگرداندن فرمان حذف وابستگی — وابستگی بازیابی می‌شود"""
        t1 = project.create_task("مقدم")
        t2 = project.create_task("جانشین")
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))

        cmd = RemoveDependencyCommand(
            predecessor_id=t1.id, successor_id=t2.id,
            dep_type=DependencyType.FINISH_START,
            lag_minutes=0,
        )
        cmd.execute(project)
        assert project.dependency_count == 0
        cmd.undo(project)
        assert project.dependency_count == 1

    # حذف وابستگی ناموجود
    def test_remove_dependency_command_nonexistent(self, project):
        """حذف وابستگی ناموجود — _existed باید False باشد"""
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        cmd = RemoveDependencyCommand(
            predecessor_id=t1.id, successor_id=t2.id,
            dep_type=DependencyType.FINISH_START,
        )
        cmd.execute(project)
        assert cmd._existed is False

    # برگرداندن حذف وابستگی ناموجود — هیچ اثری ندارد
    def test_remove_dependency_command_undo_nonexistent(self, project):
        """برگرداندن حذف وابستگی ناموجود — وابستگی اضافه نمی‌شود"""
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        cmd = RemoveDependencyCommand(
            predecessor_id=t1.id, successor_id=t2.id,
            dep_type=DependencyType.FINISH_START,
        )
        cmd.execute(project)
        cmd.undo(project)
        assert project.dependency_count == 0


# ═══════════════════════════════════════════════════════════════
#  تست‌های TaskService
# ═══════════════════════════════════════════════════════════════

class TestTaskService:
    """تست‌های مربوط به سرویس وظایف"""

    # ساخت وظیفه از طریق سرویس
    def test_create_task(self, task_service, project_with_tasks):
        """ساخت وظیفه از طریق سرویس"""
        initial_count = project_with_tasks.task_count
        task_id = task_service.create_task("وظیفه جدید", duration_minutes=120)
        assert task_id is not None
        assert project_with_tasks.task_count == initial_count + 1
        task = project_with_tasks.get_task(task_id)
        assert task.title == "وظیفه جدید"

    # حذف وظیفه از طریق سرویس
    def test_delete_task(self, task_service, project_with_tasks):
        """حذف وظیفه از طریق سرویس"""
        tasks = list(project_with_tasks.tasks())
        task_id = tasks[0].id
        task_service.delete_task(task_id)
        assert project_with_tasks.get_task(task_id) is None

    # بروزرسانی وظیفه از طریق سرویس
    def test_update_task(self, task_service, project_with_tasks):
        """بروزرسانی وظیفه از طریق سرویس"""
        tasks = list(project_with_tasks.tasks())
        task_id = tasks[0].id
        task_service.update_task(task_id, title="عنوان جدید")
        assert project_with_tasks.get_task(task_id).title == "عنوان جدید"

    # تغییر وضعیت از طریق سرویس
    def test_change_status(self, task_service, project_with_tasks):
        """تغییر وضعیت وظیفه از طریق سرویس"""
        tasks = list(project_with_tasks.tasks())
        task_id = tasks[0].id
        # DRAFT → READY
        task_service.change_status(task_id, TaskStatus.READY)
        assert project_with_tasks.get_task(task_id).status == TaskStatus.READY

    # افزودن وابستگی از طریق سرویس
    def test_add_dependency(self, task_service, project_with_tasks):
        """افزودن وابستگی از طریق سرویس"""
        tasks = list(project_with_tasks.tasks())
        # حذف وابستگی‌ها و اضافه کردن از طریق سرویس
        initial_deps = project_with_tasks.dependency_count
        # ساخت وظیفه جدید
        new_id = task_service.create_task("وظیفه اضافی")
        # اضافه کردن وابستگی
        result = task_service.add_dependency(tasks[0].id, new_id)
        assert result is True
        assert project_with_tasks.dependency_count > initial_deps

    # مرتب‌سازی وظایف بر اساس عنوان
    def test_tasks_sorted_by_title(self, task_service):
        """مرتب‌سازی وظایف بر اساس عنوان"""
        sorted_tasks = task_service.tasks_sorted_by("title")
        titles = [t.title for t in sorted_tasks]
        assert titles == sorted(titles, key=lambda x: x.lower())

    # مرتب‌سازی وظایف بر اساس اولویت
    def test_tasks_sorted_by_priority(self, task_service):
        """مرتب‌سازی وظایف بر اساس اولویت (نزولی)"""
        sorted_tasks = task_service.tasks_sorted_by("priority")
        priorities = [int(t.priority) for t in sorted_tasks]
        assert priorities == sorted(priorities, reverse=True)

    # جستجوی وظایف
    def test_search(self, task_service, project_with_tasks):
        """جستجوی وظایف بر اساس عنوان"""
        results = task_service.search("طراحی")
        assert len(results) >= 1
        assert any("طراحی" in t.title for t in results)

    # جستجوی خالی
    def test_search_empty(self, task_service):
        """جستجوی با عبارت خالی"""
        assert task_service.search("") == []

    # آمار پروژه
    def test_statistics(self, task_service, project_with_tasks):
        """بررسی آمار پروژه"""
        stats = task_service.statistics()
        assert stats["total"] == 4
        assert "done" in stats
        assert "active" in stats
        assert "blocked" in stats
        assert "completion_pct" in stats
        assert "total_minutes" in stats
        assert "critical_count" in stats
        assert "by_priority" in stats
        assert "by_status" in stats

    # آمار پروژه خالی
    def test_statistics_empty_project(self):
        """آمار پروژه خالی"""
        project = Project(name="خالی")
        scheduling = SchedulingService(project)
        undo = UndoStack()
        service = TaskService(project, undo, scheduling)
        stats = service.statistics()
        assert stats["total"] == 0
        assert stats["completion_pct"] == 0.0

    # خنثی‌سازی از طریق سرویس
    def test_undo_via_service(self, task_service, project_with_tasks):
        """خنثی‌سازی عملیات از طریق سرویس"""
        initial_count = project_with_tasks.task_count
        task_id = task_service.create_task("وظیفه موقت")
        assert project_with_tasks.task_count == initial_count + 1
        # خنثی‌سازی
        task_service.undo.undo(project_with_tasks)
        assert project_with_tasks.task_count == initial_count


# ═══════════════════════════════════════════════════════════════
#  تست‌های SchedulingService
# ═══════════════════════════════════════════════════════════════

class TestSchedulingService:
    """تست‌های مربوط به سرویس زمان‌بندی"""

    # محاسبه مجدد CPM
    def test_recalculate(self, scheduling_service, project_with_tasks):
        """اجرای CPM و بررسی نتیجه"""
        result = scheduling_service.recalculate()
        assert result.ok is True
        assert result.project_duration.minutes > 0
        assert len(result.critical_path) > 0

    # ذخیره آخرین نتیجه CPM
    def test_last_cpm(self, scheduling_service, project_with_tasks):
        """بررسی ذخیره آخرین نتیجه CPM"""
        assert scheduling_service.last_cpm is None
        scheduling_service.recalculate()
        assert scheduling_service.last_cpm is not None

    # اجرای PERT
    def test_run_pert(self, scheduling_service, project_with_tasks):
        """اجرای PERT و بررسی خلاصه"""
        summary = scheduling_service.run_pert()
        assert summary.expected_duration.minutes > 0
        assert summary.variance >= 0
        assert summary.std_dev >= 0

    # ذخیره آخرین نتیجه PERT
    def test_last_pert(self, scheduling_service, project_with_tasks):
        """بررسی ذخیره آخرین نتیجه PERT"""
        assert scheduling_service.last_pert is None
        scheduling_service.run_pert()
        assert scheduling_service.last_pert is not None

    # اجرای شبیه‌سازی مونت‌کارلو
    def test_run_monte_carlo(self, scheduling_service, project_with_tasks):
        """اجرای شبیه‌سازی مونت‌کارلو"""
        result = scheduling_service.run_monte_carlo(iterations=100, seed=42)
        assert result.iterations > 0
        assert result.mean_minutes > 0
        assert result.p50_minutes > 0
        assert result.p90_minutes > 0
        assert result.p10_minutes > 0
        assert result.min_minutes <= result.p50_minutes <= result.max_minutes

    # تسطیح منابع
    def test_level_resources(self, scheduling_service, project_with_tasks):
        """اجرای تسطیح منابع"""
        result = scheduling_service.level_resources()
        assert result.cpm is not None
        assert result.cpm.ok is True
        # بدون منابع، هیچ تعارضی نیست
        assert result.conflicts_resolved == 0
        assert result.conflicts_remaining == 0

    # محاسبه مجدد با لنگر زمانی
    def test_recalculate_with_anchor(self, scheduling_service, project_with_tasks):
        """محاسبه مجدد با لنگر زمانی مشخص"""
        anchor = datetime(2024, 6, 15, 9, 0)
        result = scheduling_service.recalculate(start_anchor=anchor)
        assert result.ok is True
        assert result.project_start == anchor

    # CPM با پروژه موازی
    def test_recalculate_parallel_paths(self, project_with_parallel):
        """محاسبه مسیر بحرانی در پروژه موازی"""
        service = SchedulingService(project_with_parallel)
        result = service.recalculate()
        assert result.ok is True
        assert len(result.critical_path) > 0

    # مونت‌کارلو با هدف مشخص
    def test_run_monte_carlo_with_target(self, scheduling_service, project_with_tasks):
        """اجرای مونت‌کارلو با هدف مشخص"""
        result = scheduling_service.run_monte_carlo(
            iterations=100, target_minutes=5000, seed=42
        )
        assert result.probability_within_target >= 0.0
        assert result.probability_within_target <= 1.0


# ═══════════════════════════════════════════════════════════════
#  تست‌های LocalAdvisor
# ═══════════════════════════════════════════════════════════════

class TestLocalAdvisor:
    """تست‌های مربوط به مشاور محلی"""

    # تحلیل خالی
    def test_analyze_empty_project(self):
        """تحلیل پروژه خالی — بدون توصیه"""
        project = Project(name="خالی")
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        assert isinstance(result, list)
        assert len(result) == 0

    # پیشنهاد تفکیک وظایف بزرگ
    def test_suggest_breakdown(self):
        """پیشنهاد تفکیک وظایف بزرگ با فعل مرکب"""
        project = Project(name="تست")
        # وظیفه بزرگ با فعل مرکب — بیش از ۵ روز
        task = Task(
            id=TaskId.generate(),
            title="Implement the new system",
            duration=Duration(60 * 8 * 7),  # ۷ روز کاری
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        breakdowns = [a for a in result if a.kind == "breakdown"]
        assert len(breakdowns) >= 1
        assert "Implement" in breakdowns[0].title or "Break down" in breakdowns[0].title

    # عدم پیشنهاد تفکیک وظایف کوتاه
    def test_no_breakdown_for_short_tasks(self):
        """وظایف کوتاه نیاز به تفکیک ندارند"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="Implement the new system",
            duration=Duration(60 * 8 * 2),  # ۲ روز کاری
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        breakdowns = [a for a in result if a.kind == "breakdown"]
        assert len(breakdowns) == 0

    # عدم پیشنهاد تفکیک بدون فعل مرکب
    def test_no_breakdown_without_composite_verb(self):
        """وظایف بدون فعل مرکب نیاز به تفکیک ندارند"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="وظیفه عادی",
            duration=Duration(60 * 8 * 7),  # ۷ روز کاری
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        breakdowns = [a for a in result if a.kind == "breakdown"]
        assert len(breakdowns) == 0

    # تشخیص تداخل — وظیفه بحرانی با پیشرفت کم
    def test_detect_conflict_critical_behind(self):
        """تشخیص تداخل — وظیفه بحرانی با پیشرفت کمتر از ۵۰٪"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="وظیفه بحرانی",
            duration=Duration(480),
            status=TaskStatus.ACTIVE,
            progress=Progress(30),
            slack=Slack(total_slack=Duration(0), free_slack=Duration(0)),
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        conflicts = [a for a in result if a.kind == "conflict" and a.severity == "critical"]
        assert len(conflicts) >= 1
        assert "بحرانی" in conflicts[0].title or "Critical" in conflicts[0].title

    # تشخیص وظیفه مسدود
    def test_detect_blocked_task(self):
        """تشخیص وظیفه مسدود"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="وظیفه مسدود",
            duration=Duration(480),
            status=TaskStatus.BLOCKED,
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        blocked = [a for a in result if a.kind == "conflict" and "BLOCKED" in a.detail]
        assert len(blocked) >= 1

    # توصیه اولویت — وظیفه بحرانی با اولویت پایین
    def test_recommend_priority_for_critical(self):
        """توصیه افزایش اولویت وظیفه بحرانی با اولویت پایین"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="وظیفه مهم",
            duration=Duration(480),
            priority=Priority.LOW,
            slack=Slack(total_slack=Duration(0), free_slack=Duration(0)),
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        priority_advice = [a for a in result if a.kind == "priority"]
        assert len(priority_advice) >= 1
        assert "Raise priority" in priority_advice[0].title or "priority" in priority_advice[0].detail.lower()

    # عدم توصیه اولویت برای وظیفه بحرانی با اولویت بالا
    def test_no_priority_advice_for_high_priority(self):
        """وظیفه بحرانی با اولویت بالا نیاز به توصیه ندارد"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="وظیفه مهم",
            duration=Duration(480),
            priority=Priority.HIGH,
            slack=Slack(total_slack=Duration(0), free_slack=Duration(0)),
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        priority_advice = [a for a in result if a.kind == "priority"]
        assert len(priority_advice) == 0

    # تحلیل جامع با چند نوع توصیه
    def test_analyze_returns_multiple_advice_types(self):
        """تحلیل جامع باید چند نوع توصیه تولید کند"""
        project = Project(name="تست")
        # وظیفه بحرانی با اولویت پایین
        t1 = Task(
            id=TaskId.generate(),
            title="وظیفه بحرانی",
            duration=Duration(480),
            status=TaskStatus.ACTIVE,
            priority=Priority.LOW,
            progress=Progress(30),
            slack=Slack(total_slack=Duration(0), free_slack=Duration(0)),
        )
        project.add_task(t1)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        kinds = {a.kind for a in result}
        # باید حداقل conflict و priority داشته باشد
        assert "conflict" in kinds
        assert "priority" in kinds

    # استنتاج وابستگی از برچسب مشترک
    def test_infer_dependency_from_shared_tags(self):
        """استنتاج وابستگی از برچسب مشترک"""
        project = Project(name="تست")
        shared_tag = Tag("frontend")
        t1 = Task(id=TaskId.generate(), title="وظیفه ۱", duration=Duration(480), tags={shared_tag})
        t2 = Task(id=TaskId.generate(), title="وظیفه ۲", duration=Duration(480), tags={shared_tag})
        project.add_task(t1)
        project.add_task(t2)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        dep_advice = [a for a in result if a.kind == "dependency"]
        assert len(dep_advice) >= 1

    # ساختار Advice
    def test_advice_structure(self):
        """بررسی ساختار Advice"""
        project = Project(name="تست")
        task = Task(
            id=TaskId.generate(),
            title="Implement the new system",
            duration=Duration(60 * 8 * 7),  # ۷ روز
        )
        project.add_task(task)
        advisor = LocalAdvisor()
        result = advisor.analyze(project)
        if result:
            a = result[0]
            assert hasattr(a, "kind")
            assert hasattr(a, "severity")
            assert hasattr(a, "title")
            assert hasattr(a, "detail")
            assert hasattr(a, "related_tasks")
            assert a.severity in ("info", "warning", "critical")


# ═══════════════════════════════════════════════════════════════
#  تست‌های کمک‌کننده‌های تقویم (Reminder, Attendee)
# ═══════════════════════════════════════════════════════════════

class TestReminderAndAttendee:
    """تست‌های مربوط به یادآور و شرکت‌کننده"""

    # ساخت یادآور
    def test_reminder_creation(self):
        """ساخت یادآور"""
        r = Reminder(minutes_before=15, method=ReminderMethod.POPUP)
        assert r.minutes_before == 15
        assert r.method == ReminderMethod.POPUP

    # خطای یادآور با دقیقه منفی
    def test_reminder_negative_minutes(self):
        """خطا اگر دقیقه منفی باشد"""
        with pytest.raises(ValueError, match="minutes_before must be >= 0"):
            Reminder(minutes_before=-1)

    # سریال‌سازی و بازسازی یادآور
    def test_reminder_roundtrip(self):
        """بازگشت از to_dict به from_dict یادآور"""
        r = Reminder(minutes_before=30, method=ReminderMethod.EMAIL)
        d = r.to_dict()
        restored = Reminder.from_dict(d)
        assert restored.minutes_before == 30
        assert restored.method == ReminderMethod.EMAIL

    # ساخت شرکت‌کننده
    def test_attendee_creation(self):
        """ساخت شرکت‌کننده"""
        a = Attendee(name="سارا", email="sara@example.com", status=AttendeeStatus.ACCEPTED)
        assert a.name == "سارا"
        assert a.email == "sara@example.com"
        assert a.status == AttendeeStatus.ACCEPTED

    # سریال‌سازی و بازسازی شرکت‌کننده
    def test_attendee_roundtrip(self):
        """بازگشت از to_dict به from_dict شرکت‌کننده"""
        a = Attendee(name="علی", email="ali@example.com", is_organizer=True)
        d = a.to_dict()
        restored = Attendee.from_dict(d)
        assert restored.name == "علی"
        assert restored.email == "ali@example.com"
        assert restored.is_organizer is True


# ═══════════════════════════════════════════════════════════════
#  تست‌های ادغام — تقویم + فرمان + سرویس
# ═══════════════════════════════════════════════════════════════

class TestIntegration:
    """تست‌های ادغام — ترکیب چند زیرسیستم"""

    # خنثی‌سازی زنجیره‌ای
    def test_undo_chain(self, project_with_tasks, undo_stack):
        """خنثی‌سازی زنجیره‌ای از فرمان‌ها"""
        scheduling = SchedulingService(project_with_tasks)
        service = TaskService(project_with_tasks, undo_stack, scheduling)

        # ساخت دو وظیفه
        id1 = service.create_task("وظیفه ۱", recalc=False)
        id2 = service.create_task("وظیفه ۲", recalc=False)

        assert project_with_tasks.task_count == 6  # ۴ اصلی + ۲ جدید

        # خنثی‌سازی دوبار
        undo_stack.undo(project_with_tasks)
        undo_stack.undo(project_with_tasks)

        assert project_with_tasks.task_count == 4  # بازگشت به وضع اول

    # اجرای مجدد زنجیره‌ای
    def test_redo_chain(self, project_with_tasks, undo_stack):
        """اجرای مجدد زنجیره‌ای از فرمان‌ها"""
        scheduling = SchedulingService(project_with_tasks)
        service = TaskService(project_with_tasks, undo_stack, scheduling)

        id1 = service.create_task("وظیفه ۱", recalc=False)
        initial_count = project_with_tasks.task_count

        undo_stack.undo(project_with_tasks)
        assert project_with_tasks.task_count == initial_count - 1

        undo_stack.redo(project_with_tasks)
        assert project_with_tasks.task_count == initial_count

    # مخزن تقویم با رویداد تکرارشونده
    def test_store_with_recurring_event(self):
        """مخزن تقویم با رویداد تکرارشونده — بررسی بسط"""
        store = CalendarStore()
        start = datetime(2024, 6, 15, 10, 0)
        evt = Event.create(
            calendar_id="cal-default", title="جلسه هفتگی",
            start=start, end=start + timedelta(hours=1),
            recurrence=RecurrenceRule(freq=RecurrenceFrequency.WEEKLY, count=3),
        )
        store.add_event(evt)

        # بررسی رویدادها در بازه ۳ هفته
        results = store.events_in_range(
            datetime(2024, 6, 15, 0, 0),
            datetime(2024, 7, 10, 23, 59),
        )
        assert len(results) == 3

    # سرویس وظایف با خنثی‌سازی کامل
    def test_full_undo_redo_cycle(self, project_with_tasks):
        """چرخه کامل ساخت → خنثی → اجرای مجدد"""
        scheduling = SchedulingService(project_with_tasks)
        undo = UndoStack()
        service = TaskService(project_with_tasks, undo, scheduling)

        initial_count = project_with_tasks.task_count
        task_id = service.create_task("وظیفه تست", duration_minutes=60)
        assert project_with_tasks.task_count == initial_count + 1

        # خنثی
        undo.undo(project_with_tasks)
        assert project_with_tasks.task_count == initial_count

        # اجرای مجدد — CreateTaskCommand.redo فرمان را مجدداً اجرا می‌کند
        # که شناسه جدید تولید می‌کند، بنابراین تعداد وظایف برمی‌گردد
        undo.redo(project_with_tasks)
        assert project_with_tasks.task_count == initial_count + 1
