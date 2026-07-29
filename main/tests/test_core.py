"""تست‌های جامع هسته دامنه — اشیاء ارزشی، شمارش‌ها، وظیفه، وابستگی، پروژه و رویدادها"""

import pytest
from datetime import datetime, timedelta

from kharazmi.core.enums import (
    TaskStatus, Priority, DependencyType, RiskLevel, DurationUnit,
    LEGAL_TRANSITIONS,
)
from kharazmi.core.value_objects import (
    TaskId, Duration, Progress, PertEstimate, Tag,
    Resource, ResourceAllocation, Slack, TimeWindow,
)
from kharazmi.core.task import Task
from kharazmi.core.dependency import Dependency
from kharazmi.core.project import Project
from kharazmi.core.events import (
    DomainEvent, TaskCreated, TaskUpdated, TaskDeleted,
    TaskStatusChanged, DependencyAdded, DependencyRemoved,
    CycleDetected, ProjectReset, ProjectLoaded, ScheduleRecalculated,
)


# ═══════════════════════════════════════════════════════════════════
#  test_value_objects
# ═══════════════════════════════════════════════════════════════════


class TestTaskId:
    """تست‌های شناسه وظیفه — ساخت، اعتبارسنجی، برابری و نمایش رشته‌ای"""

    def test_generate_creates_valid_id(self):
        # تولید شناسه تصادفی باید پیشوند پیش‌فرض T داشته باشد
        tid = TaskId.generate()
        assert str(tid).startswith("T")
        assert len(tid.value) == 9  # T + 8 hex chars

    def test_generate_custom_prefix(self):
        # تولید شناسه با پیشوند سفارشی
        tid = TaskId.generate(prefix="BUG")
        assert str(tid).startswith("BUG")

    def test_valid_id_creation(self):
        # ساخت شناسه معتبر با کاراکترهای مجاز
        tid = TaskId("T123")
        assert tid.value == "T123"

    def test_valid_id_with_hyphen_underscore(self):
        # خط تیره و زیرخط مجاز هستند
        tid = TaskId("my-task_001")
        assert tid.value == "my-task_001"

    def test_invalid_id_empty(self):
        # شناسه خالی نامعتبر است
        with pytest.raises(ValueError, match="Invalid TaskId"):
            TaskId("")

    def test_invalid_id_spaces(self):
        # فاصله در شناسه نامعتبر است
        with pytest.raises(ValueError, match="Invalid TaskId"):
            TaskId("my task")

    def test_invalid_id_special_chars(self):
        # کاراکترهای ویژه مثل @ و # نامعتبر هستند
        with pytest.raises(ValueError, match="Invalid TaskId"):
            TaskId("task@123")
        with pytest.raises(ValueError, match="Invalid TaskId"):
            TaskId("task#1")

    def test_invalid_id_unicode(self):
        # کاراکترهای یونیکد (مثل فارسی) نامعتبر هستند
        with pytest.raises(ValueError, match="Invalid TaskId"):
            TaskId("وظیفه")

    def test_equality(self):
        # دو شناسه با مقدار یکسان برابرند
        a = TaskId("T001")
        b = TaskId("T001")
        assert a == b

    def test_inequality(self):
        # دو شناسه با مقادیر متفاوت نابرابرند
        a = TaskId("T001")
        b = TaskId("T002")
        assert a != b

    def test_hash_equal_ids(self):
        # شناسه‌های برابر هش یکسان دارند (برای استفاده در مجموعه‌ها)
        a = TaskId("T001")
        b = TaskId("T001")
        assert hash(a) == hash(b)

    def test_str_returns_value(self):
        # نمایش رشته‌ای شناسه همان مقدار آن است
        tid = TaskId("ABC123")
        assert str(tid) == "ABC123"

    def test_frozen(self):
        # شناسه تغییرناپذیر است — مقدار آن قابل تغییر نیست
        tid = TaskId("T001")
        with pytest.raises(AttributeError):
            tid.value = "T002"


class TestDuration:
    """تست‌های مدت زمان — ساخت با واحدهای مختلف، ویژگی‌ها، حساب و نمایش خوانا"""

    def test_of_minutes(self):
        # ساخت مدت زمان بر حسب دقیقه
        d = Duration.of(30, DurationUnit.MINUTE)
        assert d.minutes == 30

    def test_of_hours(self):
        # ساخت مدت زمان بر حسب ساعت — هر ساعت ۶۰ دقیقه
        d = Duration.of(2, DurationUnit.HOUR)
        assert d.minutes == 120

    def test_of_days(self):
        # ساخت مدت زمان بر حسب روز کاری — هر روز ۸ ساعت = ۴۸۰ دقیقه
        d = Duration.of(1, DurationUnit.DAY)
        assert d.minutes == 480

    def test_of_weeks(self):
        # ساخت مدت زمان بر حسب هفته کاری — ۵ روز × ۸ ساعت = ۲۴۰۰ دقیقه
        d = Duration.of(1, DurationUnit.WEEK)
        assert d.minutes == 2400

    def test_of_fractional_hours(self):
        # ساخت مدت زمان با ساعت اعشاری — گرد کردن
        d = Duration.of(1.5, DurationUnit.HOUR)
        assert d.minutes == 90

    def test_of_fractional_days(self):
        # ساخت مدت زمان با روز اعشاری
        d = Duration.of(0.5, DurationUnit.DAY)
        assert d.minutes == 240

    def test_hours_property(self):
        # ویژگی ساعت — تبدیل دقیقه به ساعت
        d = Duration(120)
        assert d.hours == 2.0

    def test_days_property(self):
        # ویژگی روز کاری — تبدیل دقیقه به روز
        d = Duration(480)
        assert d.days == 1.0

    def test_weeks_property(self):
        # ویژگی هفته کاری — تبدیل دقیقه به هفته
        d = Duration(2400)
        assert d.weeks == 1.0

    def test_to_unit_minute(self):
        # تبدیل به واحد دقیقه
        d = Duration(120)
        assert d.to_unit(DurationUnit.MINUTE) == 120.0

    def test_to_unit_hour(self):
        # تبدیل به واحد ساعت
        d = Duration(120)
        assert d.to_unit(DurationUnit.HOUR) == 2.0

    def test_to_unit_day(self):
        # تبدیل به واحد روز
        d = Duration(480)
        assert d.to_unit(DurationUnit.DAY) == 1.0

    def test_to_unit_week(self):
        # تبدیل به واحد هفته
        d = Duration(2400)
        assert d.to_unit(DurationUnit.WEEK) == 1.0

    def test_add(self):
        # جمع دو مدت زمان
        a = Duration(60)
        b = Duration(30)
        result = a + b
        assert result.minutes == 90

    def test_sub(self):
        # تفریق دو مدت زمان
        a = Duration(60)
        b = Duration(30)
        result = a - b
        assert result.minutes == 30

    def test_sub_clamps_to_zero(self):
        # تفریق مدت زمان بزرگتر از عدد اول — نتیجه صفر می‌شود
        a = Duration(30)
        b = Duration(60)
        result = a - b
        assert result.minutes == 0

    def test_humanize_minutes(self):
        # نمایش خوانای مدت زمان کمتر از یک ساعت — دقیقه
        d = Duration(45)
        assert d.humanize() == "45m"

    def test_humanize_whole_hours(self):
        # نمایش خوانای مدت زمان ساعت کامل
        d = Duration(120)
        assert d.humanize() == "2h"

    def test_humanize_fractional_hours(self):
        # نمایش خوانای مدت زمان ساعت اعشاری
        d = Duration(90)
        assert d.humanize() == "1.5h"

    def test_humanize_whole_days(self):
        # نمایش خوانای مدت زمان روز کامل
        d = Duration(480)
        assert d.humanize() == "1d"

    def test_humanize_fractional_days(self):
        # نمایش خوانای مدت زمان روز اعشاری — ۷۲۰ دقیقه = ۱.۵ روز
        d = Duration(720)
        assert d.humanize() == "1.5d"

    def test_humanize_whole_weeks(self):
        # نمایش خوانای مدت زمان هفته کامل
        d = Duration(2400)
        assert d.humanize() == "1w"

    def test_humanize_fractional_weeks(self):
        # نمایش خوانای مدت زمان هفته اعشاری
        d = Duration(3600)  # 1.5 weeks
        assert d.humanize() == "1.5w"

    def test_as_timedelta(self):
        # تبدیل به timedelta پایتون
        d = Duration(90)
        td = d.as_timedelta()
        assert td == timedelta(minutes=90)

    def test_zero_duration(self):
        # مدت زمان صفر معتبر است
        d = Duration(0)
        assert d.minutes == 0
        assert d.humanize() == "0m"

    def test_negative_duration_raises(self):
        # مدت زمان منفی نامعتبر است
        with pytest.raises(ValueError, match="cannot be negative"):
            Duration(-1)

    def test_frozen(self):
        # مدت زمان تغییرناپذیر است
        d = Duration(60)
        with pytest.raises(AttributeError):
            d.minutes = 120


class TestProgress:
    """تست‌های پیشرفت — درصد، تکمیل، کسر باقیمانده و اعتبارسنجی"""

    def test_zero_percent(self):
        # پیشرفت صفر درصد
        p = Progress(0)
        assert p.percent == 0
        assert not p.is_complete
        assert p.remaining_fraction == 1.0

    def test_fifty_percent(self):
        # پیشرفت ۵۰ درصد
        p = Progress(50)
        assert p.percent == 50
        assert not p.is_complete
        assert p.remaining_fraction == 0.5

    def test_one_hundred_percent(self):
        # پیشرفت ۱۰۰ درصد — تکمیل شده
        p = Progress(100)
        assert p.percent == 100
        assert p.is_complete
        assert p.remaining_fraction == 0.0

    def test_negative_percent_raises(self):
        # پیشرفت منفی نامعتبر است
        with pytest.raises(ValueError, match="0..100"):
            Progress(-1)

    def test_over_100_raises(self):
        # پیشرفت بیش از ۱۰۰ نامعتبر است
        with pytest.raises(ValueError, match="0..100"):
            Progress(101)

    def test_remaining_fraction_boundary(self):
        # کسر باقیمانده در مرز ۱ درصد
        p = Progress(1)
        assert p.remaining_fraction == pytest.approx(0.99)

    def test_frozen(self):
        # پیشرفت تغییرناپذیر است
        p = Progress(50)
        with pytest.raises(AttributeError):
            p.percent = 60


class TestPertEstimate:
    """تست‌های برآورد PERT — مدت مورد انتظار، انحراف معیار، واریانس و اعتبارسنجی"""

    def test_expected_calculation(self):
        # محاسبه مدت مورد انتظار PERT: (o + 4m + p) / 6
        est = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(240),
        )
        # (60 + 4*120 + 240) / 6 = (60 + 480 + 240) / 6 = 780/6 = 130
        assert est.expected.minutes == 130

    def test_std_dev(self):
        # انحراف معیار: (p - o) / 6
        est = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(240),
        )
        assert est.std_dev == pytest.approx(30.0)

    def test_variance(self):
        # واریانس: انحراف معیار به توان ۲
        est = PertEstimate(
            optimistic=Duration(60),
            most_likely=Duration(120),
            pessimistic=Duration(240),
        )
        assert est.variance == pytest.approx(900.0)

    def test_equal_values(self):
        # وقتی هر سه مقدار برابر باشند — انحراف معیار صفر
        est = PertEstimate(
            optimistic=Duration(120),
            most_likely=Duration(120),
            pessimistic=Duration(120),
        )
        assert est.expected.minutes == 120
        assert est.std_dev == 0.0
        assert est.variance == 0.0

    def test_invalid_order_o_greater_than_m(self):
        # خوش‌بینانه بیشتر از محتمل نامعتبر است
        with pytest.raises(ValueError, match="optimistic <= most_likely <= pessimistic"):
            PertEstimate(
                optimistic=Duration(200),
                most_likely=Duration(100),
                pessimistic=Duration(300),
            )

    def test_invalid_order_m_greater_than_p(self):
        # محتمل بیشتر از بدبینانه نامعتبر است
        with pytest.raises(ValueError, match="optimistic <= most_likely <= pessimistic"):
            PertEstimate(
                optimistic=Duration(60),
                most_likely=Duration(300),
                pessimistic=Duration(120),
            )

    def test_frozen(self):
        # برآورد PERT تغییرناپذیر است
        est = PertEstimate(Duration(60), Duration(120), Duration(240))
        with pytest.raises(AttributeError):
            est.optimistic = Duration(100)


class TestTag:
    """تست‌های برچسب — ساخت و اعتبارسنجی"""

    def test_valid_tag(self):
        # ساخت برچسب معتبر
        t = Tag("frontend")
        assert t.name == "frontend"
        assert str(t) == "frontend"

    def test_tag_with_hyphen(self):
        # برچسب با خط تیره
        t = Tag("high-priority")
        assert str(t) == "high-priority"

    def test_empty_tag_raises(self):
        # برچسب خالی نامعتبر است
        with pytest.raises(ValueError, match="Invalid Tag"):
            Tag("")

    def test_tag_with_spaces_raises(self):
        # برچسب با فاصله نامعتبر است
        with pytest.raises(ValueError, match="Invalid Tag"):
            Tag("my tag")

    def test_tag_with_special_chars_raises(self):
        # برچسب با کاراکتر ویژه نامعتبر است
        with pytest.raises(ValueError, match="Invalid Tag"):
            Tag("tag@1")

    def test_tag_equality(self):
        # دو برچسب با نام یکسان برابرند
        assert Tag("bug") == Tag("bug")

    def test_tag_inequality(self):
        # دو برچسب با نام متفاوت نابرابرند
        assert Tag("bug") != Tag("feature")

    def test_tag_hashable(self):
        # برچسب قابل استفاده در مجموعه‌هاست
        s = {Tag("a"), Tag("b"), Tag("a")}
        assert len(s) == 2

    def test_frozen(self):
        # برچسب تغییرناپذیر است
        t = Tag("test")
        with pytest.raises(AttributeError):
            t.name = "other"


class TestResource:
    """تست‌های منبع — ساخت و اعتبارسنجی ظرفیت"""

    def test_default_capacity(self):
        # ظرفیت پیش‌فرض ۱.۰ (تمام‌وقت)
        r = Resource("Alice")
        assert r.name == "Alice"
        assert r.capacity_per_day == 1.0

    def test_custom_capacity(self):
        # ظرفیت سفارشی نیم‌وقت
        r = Resource("Bob", capacity_per_day=0.5)
        assert r.capacity_per_day == 0.5

    def test_empty_name_raises(self):
        # نام خالی نامعتبر است
        with pytest.raises(ValueError, match="Resource name is required"):
            Resource("")

    def test_zero_capacity_raises(self):
        # ظرفیت صفر نامعتبر است
        with pytest.raises(ValueError, match="capacity_per_day"):
            Resource("Alice", capacity_per_day=0.0)

    def test_negative_capacity_raises(self):
        # ظرفیت منفی نامعتبر است
        with pytest.raises(ValueError, match="capacity_per_day"):
            Resource("Alice", capacity_per_day=-0.5)

    def test_over_one_capacity_raises(self):
        # ظرفیت بیش از ۱.۰ نامعتبر است
        with pytest.raises(ValueError, match="capacity_per_day"):
            Resource("Alice", capacity_per_day=1.5)

    def test_capacity_boundary_one(self):
        # ظرفیت دقیقاً ۱.۰ معتبر است
        r = Resource("Alice", capacity_per_day=1.0)
        assert r.capacity_per_day == 1.0

    def test_capacity_just_above_zero(self):
        # ظرفیت خیلی کوچک ولی مثبت معتبر است
        r = Resource("Alice", capacity_per_day=0.01)
        assert r.capacity_per_day == 0.01


class TestResourceAllocation:
    """تست‌های تخصیص منبع — بار و ظرفیت"""

    def test_valid_allocation(self):
        # تخصیص معتبر — بار مساوی ظرفیت
        r = Resource("Alice")
        alloc = ResourceAllocation(r, 1.0)
        assert alloc.resource.name == "Alice"
        assert alloc.load == 1.0

    def test_partial_allocation(self):
        # تخصیص جزئی — بار کمتر از ظرفیت
        r = Resource("Alice")
        alloc = ResourceAllocation(r, 0.5)
        assert alloc.load == 0.5

    def test_zero_load_raises(self):
        # بار صفر نامعتبر است
        r = Resource("Alice")
        with pytest.raises(ValueError, match="out of range"):
            ResourceAllocation(r, 0.0)

    def test_negative_load_raises(self):
        # بار منفی نامعتبر است
        r = Resource("Alice")
        with pytest.raises(ValueError, match="out of range"):
            ResourceAllocation(r, -0.5)

    def test_load_exceeds_capacity_raises(self):
        # بار بیش از ظرفیت نامعتبر است
        r = Resource("Alice", capacity_per_day=0.5)
        with pytest.raises(ValueError, match="out of range"):
            ResourceAllocation(r, 0.6)

    def test_load_at_half_capacity(self):
        # بار مساوی نصف ظرفیت
        r = Resource("Alice", capacity_per_day=0.5)
        alloc = ResourceAllocation(r, 0.5)
        assert alloc.load == 0.5

    def test_load_exceeds_full_capacity(self):
        # بار بیش از ظرفیت کامل (۱.۰) نامعتبر است
        r = Resource("Alice", capacity_per_day=1.0)
        with pytest.raises(ValueError, match="out of range"):
            ResourceAllocation(r, 1.5)


class TestTimeWindow:
    """تست‌های پنجره زمانی — ساخت، تداخل، شامل بودن و اعتبارسنجی"""

    def test_valid_window(self):
        # ساخت پنجره زمانی معتبر
        start = datetime(2024, 1, 1, 9, 0)
        end = datetime(2024, 1, 1, 17, 0)
        tw = TimeWindow(start, end)
        assert tw.start == start
        assert tw.end == end

    def test_duration_property(self):
        # محاسبه مدت پنجره زمانی — ۸ ساعت = ۴۸۰ دقیقه
        start = datetime(2024, 1, 1, 9, 0)
        end = datetime(2024, 1, 1, 17, 0)
        tw = TimeWindow(start, end)
        assert tw.duration.minutes == 480

    def test_overlaps_true(self):
        # دو پنجره زمانی همپوشانی دارند
        tw1 = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        tw2 = TimeWindow(datetime(2024, 1, 1, 14, 0), datetime(2024, 1, 1, 20, 0))
        assert tw1.overlaps(tw2)
        assert tw2.overlaps(tw1)

    def test_overlaps_false_adjacent(self):
        # دو پنجره زمانی مجاور بدون همپوشانی (نیمه‌باز)
        tw1 = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        tw2 = TimeWindow(datetime(2024, 1, 1, 17, 0), datetime(2024, 1, 1, 20, 0))
        assert not tw1.overlaps(tw2)
        assert not tw2.overlaps(tw1)

    def test_overlaps_false_separate(self):
        # دو پنجره زمانی کاملاً جدا
        tw1 = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 12, 0))
        tw2 = TimeWindow(datetime(2024, 1, 1, 14, 0), datetime(2024, 1, 1, 17, 0))
        assert not tw1.overlaps(tw2)

    def test_overlaps_contained(self):
        # پنجره کوچک درون پنجره بزرگ — همپوشانی دارد
        tw1 = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        tw2 = TimeWindow(datetime(2024, 1, 1, 10, 0), datetime(2024, 1, 1, 12, 0))
        assert tw1.overlaps(tw2)

    def test_contains_moment_inside(self):
        # لحظه درون پنجره
        tw = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        moment = datetime(2024, 1, 1, 12, 0)
        assert tw.contains(moment)

    def test_contains_start_inclusive(self):
        # شروع پنجره شامل می‌شود (نیمه‌باز چپ)
        tw = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        assert tw.contains(datetime(2024, 1, 1, 9, 0))

    def test_contains_end_exclusive(self):
        # پایان پنجره شامل نمی‌شود (نیمه‌باز راست)
        tw = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        assert not tw.contains(datetime(2024, 1, 1, 17, 0))

    def test_contains_moment_outside(self):
        # لحظه بیرون پنجره
        tw = TimeWindow(datetime(2024, 1, 1, 9, 0), datetime(2024, 1, 1, 17, 0))
        assert not tw.contains(datetime(2024, 1, 1, 8, 0))

    def test_end_before_start_raises(self):
        # پایان قبل از شروع نامعتبر است
        with pytest.raises(ValueError, match="end precedes start"):
            TimeWindow(datetime(2024, 1, 2), datetime(2024, 1, 1))

    def test_same_start_end_allowed(self):
        # شروع و پایان یکسان — پنجره خالی معتبر
        dt = datetime(2024, 1, 1, 12, 0)
        tw = TimeWindow(dt, dt)
        assert tw.duration.minutes == 0


class TestSlack:
    """تست‌های زمان شل — بحرانی و نزدیک بحرانی"""

    def test_critical_zero_slack(self):
        # زمان شل صفر — وظیفه بحرانی
        s = Slack(total_slack=Duration(0), free_slack=Duration(0))
        assert s.is_critical

    def test_not_critical_nonzero_slack(self):
        # زمان شل غیرصفر — وظیفه بحرانی نیست
        s = Slack(total_slack=Duration(60), free_slack=Duration(30))
        assert not s.is_critical

    def test_near_critical_within_one_day(self):
        # زمان شل کمتر از یک روز — نزدیک بحرانی
        s = Slack(total_slack=Duration(400), free_slack=Duration(0))
        assert s.is_near_critical

    def test_near_critical_exactly_one_day(self):
        # زمان شل دقیقاً یک روز — نزدیک بحرانی
        s = Slack(total_slack=Duration(480), free_slack=Duration(0))
        assert s.is_near_critical

    def test_not_near_critical(self):
        # زمان شل بیش از یک روز — نزدیک بحرانی نیست
        s = Slack(total_slack=Duration(500), free_slack=Duration(0))
        assert not s.is_near_critical

    def test_critical_implies_near_critical(self):
        # بحرانی بودن به معنای نزدیک بحرانی بودن هم هست
        s = Slack(total_slack=Duration(0), free_slack=Duration(0))
        assert s.is_critical
        assert s.is_near_critical


# ═══════════════════════════════════════════════════════════════════
#  test_enums
# ═══════════════════════════════════════════════════════════════════


class TestTaskStatus:
    """تست‌های وضعیت وظیفه — مقادیر و انتقال‌های مجاز"""

    def test_all_values(self):
        # تمام مقادیر وضعیت وظیفه
        assert TaskStatus.DRAFT == "draft"
        assert TaskStatus.READY == "ready"
        assert TaskStatus.ACTIVE == "active"
        assert TaskStatus.BLOCKED == "blocked"
        assert TaskStatus.DONE == "done"
        assert TaskStatus.CANCELLED == "cancelled"
        assert TaskStatus.DEFERRED == "deferred"

    def test_legal_transitions_from_draft(self):
        # انتقال‌های مجاز از وضعیت پیش‌نویس
        legal = LEGAL_TRANSITIONS[TaskStatus.DRAFT]
        assert TaskStatus.READY in legal
        assert TaskStatus.CANCELLED in legal
        assert TaskStatus.DEFERRED in legal
        assert TaskStatus.ACTIVE not in legal

    def test_legal_transitions_from_ready(self):
        # انتقال‌های مجاز از وضعیت آماده
        legal = LEGAL_TRANSITIONS[TaskStatus.READY]
        assert TaskStatus.ACTIVE in legal
        assert TaskStatus.BLOCKED in legal
        assert TaskStatus.CANCELLED in legal
        assert TaskStatus.DEFERRED in legal
        assert TaskStatus.DRAFT not in legal

    def test_legal_transitions_from_active(self):
        # انتقال‌های مجاز از وضعیت فعال
        legal = LEGAL_TRANSITIONS[TaskStatus.ACTIVE]
        assert TaskStatus.DONE in legal
        assert TaskStatus.BLOCKED in legal
        assert TaskStatus.DEFERRED in legal
        assert TaskStatus.READY not in legal

    def test_legal_transitions_from_blocked(self):
        # انتقال‌های مجاز از وضعیت مسدود
        legal = LEGAL_TRANSITIONS[TaskStatus.BLOCKED]
        assert TaskStatus.READY in legal
        assert TaskStatus.ACTIVE in legal
        assert TaskStatus.CANCELLED in legal
        assert TaskStatus.DONE not in legal

    def test_legal_transitions_from_deferred(self):
        # انتقال‌های مجاز از وضعیت به تعویق افتاده
        legal = LEGAL_TRANSITIONS[TaskStatus.DEFERRED]
        assert TaskStatus.READY in legal
        assert TaskStatus.CANCELLED in legal
        assert TaskStatus.ACTIVE not in legal

    def test_done_is_terminal(self):
        # وضعیت انجام‌شده نهایی است — هیچ انتقالی ندارد
        legal = LEGAL_TRANSITIONS[TaskStatus.DONE]
        assert len(legal) == 0

    def test_cancelled_is_terminal(self):
        # وضعیت لغو‌شده نهایی است — هیچ انتقالی ندارد
        legal = LEGAL_TRANSITIONS[TaskStatus.CANCELLED]
        assert len(legal) == 0


class TestPriority:
    """تست‌های اولویت — مقادیر عددی"""

    def test_priority_values(self):
        # مقادیر عددی اولویت از ۰ تا ۴
        assert Priority.TRIVIAL == 0
        assert Priority.LOW == 1
        assert Priority.MEDIUM == 2
        assert Priority.HIGH == 3
        assert Priority.CRITICAL == 4

    def test_priority_ordering(self):
        # اولویت‌ها قابل مقایسه هستند
        assert Priority.TRIVIAL < Priority.LOW < Priority.MEDIUM < Priority.HIGH < Priority.CRITICAL


class TestDependencyType:
    """تست‌های نوع وابستگی — مقادیر استاندارد"""

    def test_dependency_type_values(self):
        # چهار نوع وابستگی استاندارد
        assert DependencyType.FINISH_START == "FS"
        assert DependencyType.FINISH_FINISH == "FF"
        assert DependencyType.START_START == "SS"
        assert DependencyType.START_FINISH == "SF"


# ═══════════════════════════════════════════════════════════════════
#  test_task
# ═══════════════════════════════════════════════════════════════════


class TestTask:
    """تست‌های وظیفه — ساخت، چرخه حیات، پیشرفت، برچسب، منبع و سریال‌سازی"""

    def test_task_creation_defaults(self):
        # ساخت وظیفه با مقادیر پیش‌فرض
        task = Task(id=TaskId("T001"), title="وظیفه تست")
        assert task.id == TaskId("T001")
        assert task.title == "وظیفه تست"
        assert task.description == ""
        assert task.duration.minutes == 60  # پیش‌فرض ۶۰ دقیقه
        assert task.priority == Priority.MEDIUM
        assert task.status == TaskStatus.DRAFT
        assert task.risk == RiskLevel.LOW
        assert task.progress.percent == 0
        assert task.tags == set()
        assert task.resources == []
        assert task.pert is None
        assert task.x == 0.0
        assert task.y == 0.0

    def test_task_creation_custom(self):
        # ساخت وظیفه با مقادیر سفارشی
        task = Task(
            id=TaskId("T001"),
            title="وظیفه سفارشی",
            description="توضیحات",
            duration=Duration.of(2, DurationUnit.DAY),
            priority=Priority.HIGH,
            risk=RiskLevel.HIGH,
        )
        assert task.duration.minutes == 960
        assert task.priority == Priority.HIGH
        assert task.risk == RiskLevel.HIGH

    def test_advance_valid_transition(self):
        # انتقال معتبر از DRAFT به READY
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        assert task.status == TaskStatus.READY

    def test_advance_invalid_transition(self):
        # انتقال نامعتبر — از DRAFT به ACTIVE خطا می‌دهد
        task = Task(id=TaskId("T001"), title="تست")
        with pytest.raises(ValueError, match="Illegal transition"):
            task.advance(TaskStatus.ACTIVE)

    def test_advance_chain(self):
        # زنجیره انتقال‌های معتبر: DRAFT -> READY -> ACTIVE -> DONE
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        task.advance(TaskStatus.DONE)
        assert task.status == TaskStatus.DONE

    def test_advance_from_terminal_raises(self):
        # انتقال از وضعیت نهایی نامعتبر است
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        task.advance(TaskStatus.DONE)
        with pytest.raises(ValueError, match="Illegal transition"):
            task.advance(TaskStatus.READY)

    def test_advance_blocked_to_active(self):
        # انتقال از مسدود به فعال
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.BLOCKED)
        task.advance(TaskStatus.ACTIVE)
        assert task.status == TaskStatus.ACTIVE

    def test_advance_deferred_to_ready(self):
        # انتقال از به تعویق افتاده به آماده
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.DEFERRED)
        task.advance(TaskStatus.READY)
        assert task.status == TaskStatus.READY

    def test_set_progress(self):
        # تنظیم درصد پیشرفت
        task = Task(id=TaskId("T001"), title="تست")
        task.set_progress(50)
        assert task.progress.percent == 50

    def test_set_progress_auto_done_from_active(self):
        # پیشرفت ۱۰۰٪ از وضعیت فعال — انتقال خودکار به DONE
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        task.set_progress(100)
        assert task.status == TaskStatus.DONE
        assert task.progress.is_complete

    def test_set_progress_auto_done_from_ready(self):
        # پیشرفت ۱۰۰٪ از وضعیت آماده — انتقال خودکار به DONE
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.set_progress(100)
        assert task.status == TaskStatus.DONE

    def test_set_progress_no_auto_done_from_blocked(self):
        # پیشرفت ۱۰۰٪ از وضعیت مسدود — بدون انتقال خودکار
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.BLOCKED)
        task.set_progress(100)
        # BLOCKED not in (ACTIVE, READY), so no auto-transition
        assert task.status == TaskStatus.BLOCKED

    def test_set_progress_partial(self):
        # پیشرفت جزئی — بدون تغییر وضعیت
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        task.set_progress(75)
        assert task.status == TaskStatus.ACTIVE
        assert task.progress.percent == 75

    def test_set_duration(self):
        # تنظیم مدت زمان وظیفه
        task = Task(id=TaskId("T001"), title="تست")
        task.set_duration(2, DurationUnit.DAY)
        assert task.duration.minutes == 960

    def test_add_tag(self):
        # افزودن برچسب به وظیفه
        task = Task(id=TaskId("T001"), title="تست")
        tag = Tag("frontend")
        task.add_tag(tag)
        assert tag in task.tags

    def test_add_tag_idempotent(self):
        # افزودن برچسب تکراری — بدون تغییر
        task = Task(id=TaskId("T001"), title="تست")
        tag = Tag("frontend")
        task.add_tag(tag)
        task.add_tag(tag)
        assert len(task.tags) == 1

    def test_remove_tag(self):
        # حذف برچسب از وظیفه
        task = Task(id=TaskId("T001"), title="تست")
        tag = Tag("frontend")
        task.add_tag(tag)
        task.remove_tag(tag)
        assert tag not in task.tags

    def test_remove_nonexistent_tag(self):
        # حذف برچسب ناموجود — بدون خطا
        task = Task(id=TaskId("T001"), title="تست")
        task.remove_tag(Tag("nonexistent"))  # Should not raise

    def test_assign_resource(self):
        # تخصیص منبع به وظیفه
        task = Task(id=TaskId("T001"), title="تست")
        r = Resource("Alice")
        alloc = ResourceAllocation(r, 1.0)
        task.assign_resource(alloc)
        assert len(task.resources) == 1
        assert task.resources[0].resource.name == "Alice"

    def test_assign_resource_replaces_existing(self):
        # تخصیص مجدد منبع با نام یکسان — جایگزین می‌شود
        task = Task(id=TaskId("T001"), title="تست")
        r = Resource("Alice")
        task.assign_resource(ResourceAllocation(r, 1.0))
        task.assign_resource(ResourceAllocation(r, 0.5))
        assert len(task.resources) == 1
        assert task.resources[0].load == 0.5

    def test_unassign_resource(self):
        # حذف تخصیص منبع
        task = Task(id=TaskId("T001"), title="تست")
        r = Resource("Alice")
        task.assign_resource(ResourceAllocation(r, 1.0))
        task.unassign_resource("Alice")
        assert len(task.resources) == 0

    def test_unassign_nonexistent_resource(self):
        # حذف تخصیص منبع ناموجود — بدون خطا
        task = Task(id=TaskId("T001"), title="تست")
        task.unassign_resource("Nobody")  # Should not raise

    def test_is_critical_with_slack(self):
        # وظیفه با زمان شل صفر بحرانی است
        task = Task(id=TaskId("T001"), title="تست")
        task.slack = Slack(total_slack=Duration(0), free_slack=Duration(0))
        assert task.is_critical

    def test_is_critical_without_slack(self):
        # وظیفه بدون زمان شل بحرانی نیست
        task = Task(id=TaskId("T001"), title="تست")
        assert not task.is_critical

    def test_is_critical_with_nonzero_slack(self):
        # وظیفه با زمان شل غیرصفر بحرانی نیست
        task = Task(id=TaskId("T001"), title="تست")
        task.slack = Slack(total_slack=Duration(60), free_slack=Duration(30))
        assert not task.is_critical

    def test_is_terminal_done(self):
        # وضعیت DONE نهایی است
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        task.advance(TaskStatus.DONE)
        assert task.is_terminal

    def test_is_terminal_cancelled(self):
        # وضعیت CANCELLED نهایی است
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.CANCELLED)
        assert task.is_terminal

    def test_is_not_terminal_active(self):
        # وضعیت ACTIVE نهایی نیست
        task = Task(id=TaskId("T001"), title="تست")
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        assert not task.is_terminal

    def test_is_active(self):
        # بررسی وضعیت فعال
        task = Task(id=TaskId("T001"), title="تست")
        assert not task.is_active
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        assert task.is_active

    def test_effective_duration_without_pert(self):
        # مدت موثر بدون PERT — همان مدت زمان عادی
        task = Task(id=TaskId("T001"), title="تست", duration=Duration(120))
        assert task.effective_duration.minutes == 120

    def test_effective_duration_with_pert(self):
        # مدت موثر با PERT — مدت مورد انتظار PERT
        task = Task(id=TaskId("T001"), title="تست", duration=Duration(120))
        task.pert = PertEstimate(Duration(60), Duration(120), Duration(240))
        # expected = (60 + 4*120 + 240)/6 = 130
        assert task.effective_duration.minutes == 130

    def test_remaining_duration(self):
        # مدت زمان باقیمانده
        task = Task(id=TaskId("T001"), title="تست", duration=Duration(100))
        task.set_progress(60)
        # remaining = 100 * 0.4 = 40
        assert task.remaining_duration.minutes == 40

    def test_remaining_duration_zero_progress(self):
        # مدت زمان باقیمانده با پیشرفت صفر
        task = Task(id=TaskId("T001"), title="تست", duration=Duration(100))
        assert task.remaining_duration.minutes == 100

    def test_remaining_duration_full_progress(self):
        # مدت زمان باقیمانده با پیشرفت صد درصد
        task = Task(id=TaskId("T001"), title="تست", duration=Duration(100))
        task.set_progress(100)
        assert task.remaining_duration.minutes == 0

    def test_to_dict(self):
        # سریال‌سازی وظیفه به دیکشنری
        task = Task(id=TaskId("T001"), title="وظیفه تست", description="توضیح")
        d = task.to_dict()
        assert d["id"] == "T001"
        assert d["title"] == "وظیفه تست"
        assert d["description"] == "توضیح"
        assert d["status"] == "draft"
        assert d["progress"] == 0
        assert d["tags"] == []
        assert d["resources"] == []

    def test_to_dict_with_tags_and_resources(self):
        # سریال‌سازی وظیفه با برچسب و منبع
        task = Task(id=TaskId("T001"), title="تست")
        task.add_tag(Tag("alpha"))
        task.add_tag(Tag("beta"))
        r = Resource("Alice", capacity_per_day=0.5)
        task.assign_resource(ResourceAllocation(r, 0.5))
        d = task.to_dict()
        assert sorted(d["tags"]) == ["alpha", "beta"]
        assert len(d["resources"]) == 1
        assert d["resources"][0]["name"] == "Alice"
        assert d["resources"][0]["capacity"] == 0.5
        assert d["resources"][0]["load"] == 0.5

    def test_to_dict_with_pert(self):
        # سریال‌سازی وظیفه با برآورد PERT
        task = Task(id=TaskId("T001"), title="تست")
        task.pert = PertEstimate(Duration(60), Duration(120), Duration(240))
        d = task.to_dict()
        assert d["pert"] is not None
        assert d["pert"]["optimistic"] == 60
        assert d["pert"]["most_likely"] == 120
        assert d["pert"]["pessimistic"] == 240

    def test_from_dict(self):
        # بازسازی وظیفه از دیکشنری
        data = {
            "id": "T001",
            "title": "وظیفه تست",
            "description": "توضیح",
            "duration_minutes": 120,
            "priority": 3,
            "status": "active",
            "risk": "high",
            "progress": 50,
            "tags": ["alpha", "beta"],
            "resources": [{"name": "Alice", "capacity": 1.0, "load": 0.8}],
            "pert": None,
            "x": 10.0,
            "y": 20.0,
        }
        task = Task.from_dict(data)
        assert str(task.id) == "T001"
        assert task.title == "وظیفه تست"
        assert task.duration.minutes == 120
        assert task.priority == Priority.HIGH
        assert task.status == TaskStatus.ACTIVE
        assert task.progress.percent == 50
        assert len(task.tags) == 2
        assert len(task.resources) == 1

    def test_to_dict_from_dict_roundtrip(self):
        # تست رفت‌برگشت سریال‌سازی — from_dict(to_dict(x)) باید معادل x باشد
        task = Task(id=TaskId("T001"), title="وظیفه تست", description="توضیح")
        task.add_tag(Tag("dev"))
        task.set_duration(2, DurationUnit.DAY)
        task.advance(TaskStatus.READY)
        task.advance(TaskStatus.ACTIVE)
        task.set_progress(30)
        task.pert = PertEstimate(Duration(240), Duration(960), Duration(1440))

        d = task.to_dict()
        restored = Task.from_dict(d)

        assert str(restored.id) == str(task.id)
        assert restored.title == task.title
        assert restored.description == task.description
        assert restored.duration.minutes == task.duration.minutes
        assert restored.priority == task.priority
        assert restored.status == task.status
        assert restored.progress.percent == task.progress.percent
        assert restored.pert is not None
        assert restored.pert.optimistic.minutes == task.pert.optimistic.minutes
        assert restored.pert.most_likely.minutes == task.pert.most_likely.minutes
        assert restored.pert.pessimistic.minutes == task.pert.pessimistic.minutes

    def test_touch_updates_timestamp(self):
        # touch() زمان بروزرسانی را تغییر می‌دهد
        task = Task(id=TaskId("T001"), title="تست")
        old_updated = task.updated_at
        task.touch()
        assert task.updated_at >= old_updated


# ═══════════════════════════════════════════════════════════════════
#  test_dependency
# ═══════════════════════════════════════════════════════════════════


class TestDependency:
    """تست‌های وابستگی — ساخت، اعتبارسنجی، کلید و سریال‌سازی"""

    def test_dependency_creation(self):
        # ساخت وابستگی ساده
        dep = Dependency(TaskId("T001"), TaskId("T002"))
        assert dep.predecessor_id == TaskId("T001")
        assert dep.successor_id == TaskId("T002")
        assert dep.type == DependencyType.FINISH_START
        assert dep.lag.minutes == 0

    def test_dependency_with_type(self):
        # ساخت وابستگی با نوع سفارشی
        dep = Dependency(TaskId("T001"), TaskId("T002"), type=DependencyType.START_START)
        assert dep.type == DependencyType.START_START

    def test_dependency_with_lag(self):
        # ساخت وابستگی با تأخیر
        dep = Dependency(TaskId("T001"), TaskId("T002"), lag=Duration(120))
        assert dep.lag.minutes == 120

    def test_self_dependency_raises(self):
        # خودوابستگی نامعتبر است
        with pytest.raises(ValueError, match="cannot depend on itself"):
            Dependency(TaskId("T001"), TaskId("T001"))

    def test_key_property(self):
        # کلید یکتای وابستگی
        dep = Dependency(TaskId("T001"), TaskId("T002"), DependencyType.FINISH_START)
        assert dep.key == ("T001", "T002", "FS")

    def test_key_different_for_types(self):
        # وابستگی‌های مختلف بین دو وظیفه با نوع متفاوت — کلید متفاوت
        dep_fs = Dependency(TaskId("T001"), TaskId("T002"), DependencyType.FINISH_START)
        dep_ss = Dependency(TaskId("T001"), TaskId("T002"), DependencyType.START_START)
        assert dep_fs.key != dep_ss.key

    def test_to_dict(self):
        # سریال‌سازی وابستگی به دیکشنری
        dep = Dependency(TaskId("T001"), TaskId("T002"), lag=Duration(60))
        d = dep.to_dict()
        assert d["predecessor"] == "T001"
        assert d["successor"] == "T002"
        assert d["type"] == "FS"
        assert d["lag_minutes"] == 60

    def test_from_dict(self):
        # بازسازی وابستگی از دیکشنری
        data = {"predecessor": "T001", "successor": "T002", "type": "SS", "lag_minutes": 30}
        dep = Dependency.from_dict(data)
        assert dep.predecessor_id == TaskId("T001")
        assert dep.successor_id == TaskId("T002")
        assert dep.type == DependencyType.START_START
        assert dep.lag.minutes == 30

    def test_to_dict_from_dict_roundtrip(self):
        # تست رفت‌برگشت سریال‌سازی
        dep = Dependency(TaskId("T001"), TaskId("T002"), DependencyType.FINISH_FINISH, Duration(120))
        d = dep.to_dict()
        restored = Dependency.from_dict(d)
        assert restored.predecessor_id == dep.predecessor_id
        assert restored.successor_id == dep.successor_id
        assert restored.type == dep.type
        assert restored.lag.minutes == dep.lag.minutes

    def test_all_dependency_types(self):
        # تمام انواع وابستگی قابل ساخت هستند
        for dt in DependencyType:
            dep = Dependency(TaskId("T001"), TaskId("T002"), type=dt)
            assert dep.type == dt

    def test_frozen(self):
        # وابستگی تغییرناپذیر است
        dep = Dependency(TaskId("T001"), TaskId("T002"))
        with pytest.raises(AttributeError):
            dep.type = DependencyType.START_START


# ═══════════════════════════════════════════════════════════════════
#  test_project
# ═══════════════════════════════════════════════════════════════════


class TestProject:
    """تست‌های پروژه — وظایف، وابستگی‌ها، رویدادها، گراف و سریال‌سازی"""

    # ─── وظایف ────────────────────────────────────────────────

    def test_add_task(self, project):
        # افزودن وظیفه به پروژه
        task = Task(id=TaskId("T001"), title="وظیفه")
        result = project.add_task(task)
        assert result is task
        assert project.task_count == 1

    def test_add_duplicate_task_raises(self, project):
        # افزودن وظیفه تکراری خطا می‌دهد
        task = Task(id=TaskId("T001"), title="وظیفه")
        project.add_task(task)
        with pytest.raises(ValueError, match="already exists"):
            project.add_task(Task(id=TaskId("T001"), title="وظیفه دیگر"))

    def test_create_task(self, project):
        # ساخت و افزودن وظیفه با شناسه خودکار
        task = project.create_task("وظیفه جدید")
        assert task.title == "وظیفه جدید"
        assert project.task_count == 1
        assert str(task.id).startswith("T")

    def test_get_task_existing(self, project):
        # دریافت وظیفه موجود
        task = project.create_task("وظیفه")
        found = project.get_task(task.id)
        assert found is task

    def test_get_task_nonexistent(self, project):
        # دریافت وظیفه ناموجود — None برمی‌گرداند
        found = project.get_task(TaskId("NONEXIST"))
        assert found is None

    def test_require_task_existing(self, project):
        # دریافت الزامی وظیفه موجود
        task = project.create_task("وظیفه")
        found = project.require_task(task.id)
        assert found is task

    def test_require_task_nonexistent_raises(self, project):
        # دریافت الزامی وظیفه ناموجود — خطا
        with pytest.raises(KeyError, match="No such task"):
            project.require_task(TaskId("NONEXIST"))

    def test_delete_task(self, project):
        # حذف وظیفه از پروژه
        task = project.create_task("وظیفه")
        project.delete_task(task.id)
        assert project.task_count == 0
        assert project.get_task(task.id) is None

    def test_delete_task_removes_dependencies(self, project):
        # حذف وظیفه — وابستگی‌هایش هم حذف می‌شوند
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        assert project.dependency_count == 1
        project.delete_task(t1.id)
        assert project.dependency_count == 0

    def test_delete_task_removes_dependent_deps(self, project):
        # حذف وظیفه جانشین — وابستگی‌اش هم حذف می‌شود
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.delete_task(t2.id)
        assert project.dependency_count == 0

    def test_delete_nonexistent_task_no_error(self, project):
        # حذف وظیفه ناموجود — بدون خطا
        project.delete_task(TaskId("NONEXIST"))  # Should not raise

    def test_update_task(self, project):
        # بروزرسانی فیلدهای وظیفه
        task = project.create_task("وظیفه")
        project.update_task(task.id, title="عنوان جدید")
        assert task.title == "عنوان جدید"

    def test_update_task_unknown_field_raises(self, project):
        # بروزرسانی فیلد ناموجود خطا می‌دهد
        task = project.create_task("وظیفه")
        with pytest.raises(AttributeError, match="no field"):
            project.update_task(task.id, nonexistent_field="value")

    def test_change_status(self, project):
        # تغییر وضعیت وظیفه از طریق پروژه
        task = project.create_task("وظیفه")
        project.change_status(task.id, TaskStatus.READY)
        assert task.status == TaskStatus.READY

    def test_change_status_invalid_transition(self, project):
        # تغییر وضعیت نامعتبر — خطا
        task = project.create_task("وظیفه")
        with pytest.raises(ValueError, match="Illegal transition"):
            project.change_status(task.id, TaskStatus.ACTIVE)

    # ─── وابستگی‌ها ────────────────────────────────────────────

    def test_add_dependency(self, project):
        # افزودن وابستگی بین دو وظیفه
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        dep = Dependency(t1.id, t2.id)
        result = project.add_dependency(dep)
        assert result is dep
        assert project.dependency_count == 1

    def test_add_dependency_duplicate_returns_existing(self, project):
        # افزودن وابستگی تکراری — وابستگی موجود برگردانده می‌شود
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        dep1 = Dependency(t1.id, t2.id)
        dep2 = Dependency(t1.id, t2.id)
        project.add_dependency(dep1)
        result = project.add_dependency(dep2)
        assert project.dependency_count == 1
        assert result is dep1

    def test_add_dependency_missing_predecessor(self, project):
        # وابستگی با مقدم ناموجود — خطا
        t2 = project.create_task("وظیفه ۲")
        with pytest.raises(KeyError, match="Predecessor not found"):
            project.add_dependency(Dependency(TaskId("MISSING"), t2.id))

    def test_add_dependency_missing_successor(self, project):
        # وابستگی با جانشین ناموجود — خطا
        t1 = project.create_task("وظیفه ۱")
        with pytest.raises(KeyError, match="Successor not found"):
            project.add_dependency(Dependency(t1.id, TaskId("MISSING")))

    def test_add_dependency_cycle_detection(self, project):
        # تشخیص چرخه — افزودن وابستگی دورانی خطا می‌دهد
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        t3 = project.create_task("وظیفه ۳")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.add_dependency(Dependency(t2.id, t3.id))
        # تلاش برای ایجاد چرخه: t3 -> t1
        with pytest.raises(ValueError, match="Refused"):
            project.add_dependency(Dependency(t3.id, t1.id))

    def test_add_dependency_direct_cycle(self, project):
        # چرخه مستقیم — A -> B -> A
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        with pytest.raises(ValueError, match="Refused"):
            project.add_dependency(Dependency(t2.id, t1.id))

    def test_add_dependency_self_cycle(self, project):
        # خودوابستگی از طریق پروژه — خطا در Dependency
        t1 = project.create_task("وظیفه ۱")
        with pytest.raises(ValueError, match="cannot depend on itself"):
            project.add_dependency(Dependency(t1.id, t1.id))

    def test_remove_dependency(self, project):
        # حذف وابستگی
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.remove_dependency(t1.id, t2.id)
        assert project.dependency_count == 0

    def test_remove_nonexistent_dependency(self, project):
        # حذف وابستگی ناموجود — بدون خطا
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.remove_dependency(t1.id, t2.id)  # Should not raise

    def test_dependencies_of(self, project):
        # وابستگی‌هایی که وظیفه جانشین آنهاست
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        deps = project.dependencies_of(t2.id)
        assert len(deps) == 1
        assert deps[0].predecessor_id == t1.id

    def test_dependencies_of_no_deps(self, project):
        # وظیفه بدون مقدم
        t1 = project.create_task("وظیفه")
        deps = project.dependencies_of(t1.id)
        assert len(deps) == 0

    def test_dependents_of(self, project):
        # وابستگی‌هایی که وظیفه مقدم آنهاست
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        deps = project.dependents_of(t1.id)
        assert len(deps) == 1
        assert deps[0].successor_id == t2.id

    def test_dependents_of_no_deps(self, project):
        # وظیفه بدون جانشین
        t1 = project.create_task("وظیفه")
        deps = project.dependents_of(t1.id)
        assert len(deps) == 0

    # ─── کوئری‌های گراف ────────────────────────────────────────

    def test_tasks_iterator(self, project):
        # تکرارگر وظایف
        project.create_task("وظیفه ۱")
        project.create_task("وظیفه ۲")
        tasks = list(project.tasks())
        assert len(tasks) == 2

    def test_task_count(self, project):
        # تعداد وظایف
        assert project.task_count == 0
        project.create_task("وظیفه")
        assert project.task_count == 1

    def test_dependency_count(self, project):
        # تعداد وابستگی‌ها
        assert project.dependency_count == 0
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        assert project.dependency_count == 1

    def test_roots(self, project):
        # وظایف بدون مقدم — ریشه‌های گراف
        t1 = project.create_task("ریشه")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        roots = project.roots()
        assert len(roots) == 1
        assert roots[0].id == t1.id

    def test_roots_multiple(self, project):
        # چند ریشه در گراف
        t1 = project.create_task("ریشه ۱")
        t2 = project.create_task("ریشه ۲")
        t3 = project.create_task("وظیفه")
        project.add_dependency(Dependency(t1.id, t3.id))
        project.add_dependency(Dependency(t2.id, t3.id))
        roots = project.roots()
        assert len(roots) == 2

    def test_leaves(self, project):
        # وظایف بدون جانشین — برگ‌های گراف
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("برگ")
        project.add_dependency(Dependency(t1.id, t2.id))
        leaves = project.leaves()
        assert len(leaves) == 1
        assert leaves[0].id == t2.id

    def test_leaves_multiple(self, project):
        # چند برگ در گراف
        t1 = project.create_task("وظیفه")
        t2 = project.create_task("برگ ۱")
        t3 = project.create_task("برگ ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.add_dependency(Dependency(t1.id, t3.id))
        leaves = project.leaves()
        assert len(leaves) == 2

    # ─── رویدادها ──────────────────────────────────────────────

    def test_subscribe_and_emit_task_created(self, project):
        # شنود رویداد ساخت وظیفه
        events = []
        project.subscribe(events.append)
        project.create_task("وظیفه")
        assert len(events) == 1
        assert isinstance(events[0], TaskCreated)
        assert events[0].title == "وظیفه"

    def test_subscribe_and_emit_task_deleted(self, project):
        # شنود رویداد حذف وظیفه
        events = []
        project.subscribe(events.append)
        task = project.create_task("وظیفه")
        project.delete_task(task.id)
        # TaskCreated + TaskDeleted
        assert len(events) == 2
        assert isinstance(events[1], TaskDeleted)

    def test_subscribe_and_emit_task_updated(self, project):
        # شنود رویداد بروزرسانی وظیفه
        events = []
        project.subscribe(events.append)
        task = project.create_task("وظیفه")
        project.update_task(task.id, title="عنوان جدید")
        # TaskCreated + TaskUpdated
        assert len(events) == 2
        assert isinstance(events[1], TaskUpdated)
        assert events[1].field == "title"
        assert events[1].old == "وظیفه"
        assert events[1].new == "عنوان جدید"

    def test_subscribe_and_emit_status_changed(self, project):
        # شنود رویداد تغییر وضعیت
        events = []
        project.subscribe(events.append)
        task = project.create_task("وظیفه")
        project.change_status(task.id, TaskStatus.READY)
        # TaskCreated + TaskStatusChanged
        assert len(events) == 2
        assert isinstance(events[1], TaskStatusChanged)
        assert events[1].old == "draft"
        assert events[1].new == "ready"

    def test_subscribe_and_emit_dependency_added(self, project):
        # شنود رویداد افزودن وابستگی
        events = []
        project.subscribe(events.append)
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        # TaskCreated + TaskCreated + DependencyAdded
        assert len(events) == 3
        assert isinstance(events[2], DependencyAdded)

    def test_subscribe_and_emit_dependency_removed(self, project):
        # شنود رویداد حذف وابستگی
        events = []
        project.subscribe(events.append)
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.remove_dependency(t1.id, t2.id)
        # TaskCreated + TaskCreated + DependencyAdded + DependencyRemoved
        assert len(events) == 4
        assert isinstance(events[3], DependencyRemoved)

    def test_subscribe_and_emit_cycle_detected(self, project):
        # شنود رویداد تشخیص چرخه
        events = []
        project.subscribe(events.append)
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        with pytest.raises(ValueError):
            project.add_dependency(Dependency(t2.id, t1.id))
        # CycleDetected event should be emitted before the error
        cycle_events = [e for e in events if isinstance(e, CycleDetected)]
        assert len(cycle_events) == 1

    def test_subscribe_and_emit_project_reset(self, project):
        # شنود رویداد پاکسازی پروژه
        events = []
        project.subscribe(events.append)
        project.create_task("وظیفه")
        project.clear()
        reset_events = [e for e in events if isinstance(e, ProjectReset)]
        assert len(reset_events) == 1

    def test_listener_exception_does_not_corrupt(self, project):
        # خطای شنودگر — نباید پروژه را خراب کند
        def bad_listener(event):
            raise RuntimeError("خطای شنودگر")
        project.subscribe(bad_listener)
        # Should not raise
        task = project.create_task("وظیفه")
        assert project.task_count == 1

    def test_multiple_listeners(self, project):
        # چند شنودگر — همه دریافت می‌کنند
        events_a = []
        events_b = []
        project.subscribe(events_a.append)
        project.subscribe(events_b.append)
        project.create_task("وظیفه")
        assert len(events_a) == 1
        assert len(events_b) == 1

    # ─── عملیات‌های کلی ─────────────────────────────────────────

    def test_clear(self, project):
        # پاکسازی پروژه — حذف تمام وظایف و وابستگی‌ها
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.clear()
        assert project.task_count == 0
        assert project.dependency_count == 0

    def test_snapshot_deep_copy(self, project):
        # اسنپ‌شات — کپی عمیق مستقل
        task = project.create_task("وظیفه")
        snap = project.snapshot()
        # تغییر پروژه اصلی نباید اسنپ‌شات را تغییر دهد
        task.title = "عنوان جدید"
        snap_task = snap.get_task(task.id)
        assert snap_task.title == "وظیفه"

    def test_snapshot_independence(self, project):
        # اسنپ‌شات مستقل — حذف از اصلی اسنپ‌شات را تغییر نمی‌دهد
        task = project.create_task("وظیفه")
        snap = project.snapshot()
        project.delete_task(task.id)
        assert project.task_count == 0
        assert snap.task_count == 1

    # ─── سریال‌سازی ──────────────────────────────────────────────

    def test_to_dict(self, project):
        # سریال‌سازی پروژه به دیکشنری
        project.create_task("وظیفه")
        d = project.to_dict()
        assert d["name"] == "تست پروژه"
        assert d["description"] == "پروژه آزمایشی"
        assert len(d["tasks"]) == 1
        assert len(d["dependencies"]) == 0

    def test_from_dict(self, project):
        # بازسازی پروژه از دیکشنری
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        d = project.to_dict()
        restored = Project.from_dict(d)
        assert restored.name == project.name
        assert restored.task_count == 2
        assert restored.dependency_count == 1

    def test_to_dict_from_dict_roundtrip(self, project):
        # تست رفت‌برگشت سریال‌سازی پروژه
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.START_START, Duration(60)))
        d = project.to_dict()
        restored = Project.from_dict(d)
        assert restored.task_count == project.task_count
        assert restored.dependency_count == project.dependency_count
        # Check tasks are restored
        rt1 = restored.get_task(t1.id)
        assert rt1 is not None
        assert rt1.title == "وظیفه ۱"
        # Check dependency is restored
        deps = list(restored.dependencies())
        assert len(deps) == 1
        assert deps[0].type == DependencyType.START_START
        assert deps[0].lag.minutes == 60

    def test_from_dict_skips_malformed_tasks(self):
        # بازسازی پروژه — وظایف نامعتبر نادیده گرفته می‌شوند
        data = {
            "name": "تست",
            "tasks": [
                {"id": "T001", "title": "معتبر"},
                {"bad": "data"},  # Missing required fields
            ],
            "dependencies": [],
        }
        proj = Project.from_dict(data)
        assert proj.task_count == 1

    def test_from_dict_skips_malformed_dependencies(self):
        # بازسازی پروژه — وابستگی‌های نامعتبر نادیده گرفته می‌شوند
        data = {
            "name": "تست",
            "tasks": [{"id": "T001", "title": "وظیفه"}],
            "dependencies": [
                {"bad": "data"},
            ],
        }
        proj = Project.from_dict(data)
        assert proj.dependency_count == 0

    # ─── تشخیص چرخه با توپولوژی‌های مختلف ──────────────────────

    def test_would_create_cycle_chain(self, project):
        # تشخیص چرخه در زنجیره: A -> B -> C -> A
        t1 = project.create_task("A")
        t2 = project.create_task("B")
        t3 = project.create_task("C")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.add_dependency(Dependency(t2.id, t3.id))
        with pytest.raises(ValueError, match="Refused"):
            project.add_dependency(Dependency(t3.id, t1.id))

    def test_would_create_cycle_diamond(self, project):
        # تشخیص چرخه در گراف الماسی: A -> B, A -> C, B -> D, C -> D, D -> A
        t1 = project.create_task("A")
        t2 = project.create_task("B")
        t3 = project.create_task("C")
        t4 = project.create_task("D")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.add_dependency(Dependency(t1.id, t3.id))
        project.add_dependency(Dependency(t2.id, t4.id))
        project.add_dependency(Dependency(t3.id, t4.id))
        with pytest.raises(ValueError, match="Refused"):
            project.add_dependency(Dependency(t4.id, t1.id))

    def test_no_cycle_independent_paths(self, project):
        # مسیرهای مستقل بدون چرخه
        t1 = project.create_task("A")
        t2 = project.create_task("B")
        t3 = project.create_task("C")
        project.add_dependency(Dependency(t1.id, t2.id))
        # A -> C is fine; no path from C back to A
        project.add_dependency(Dependency(t1.id, t3.id))
        assert project.dependency_count == 2

    def test_no_cycle_long_chain(self, project):
        # زنجیره طولانی بدون چرخه
        tasks = [project.create_task(f"وظیفه {i}") for i in range(5)]
        for i in range(4):
            project.add_dependency(Dependency(tasks[i].id, tasks[i + 1].id))
        assert project.dependency_count == 4

    def test_would_create_cycle_long_chain(self, project):
        # تشخیص چرخه در زنجیره طولانی
        tasks = [project.create_task(f"وظیفه {i}") for i in range(5)]
        for i in range(4):
            project.add_dependency(Dependency(tasks[i].id, tasks[i + 1].id))
        # ایجاد چرخه: آخر -> اول
        with pytest.raises(ValueError, match="Refused"):
            project.add_dependency(Dependency(tasks[4].id, tasks[0].id))

    def test_can_reach_self(self, project):
        # هر گره به خودش می‌رسد — _can_reach(src, src) = True
        t1 = project.create_task("وظیفه")
        assert project._can_reach(t1.id, t1.id)

    def test_can_reach_no_path(self, project):
        # دو گره بدون مسیر
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        assert not project._can_reach(t1.id, t2.id)

    def test_can_reach_with_path(self, project):
        # دو گره با مسیر مستقیم
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        assert project._can_reach(t1.id, t2.id)

    def test_can_reach_transitive(self, project):
        # دسترسی غیرمستقیم — A -> B -> C
        t1 = project.create_task("A")
        t2 = project.create_task("B")
        t3 = project.create_task("C")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.add_dependency(Dependency(t2.id, t3.id))
        assert project._can_reach(t1.id, t3.id)

    def test_find_path_direct(self, project):
        # یافتن مسیر مستقیم
        t1 = project.create_task("A")
        t2 = project.create_task("B")
        project.add_dependency(Dependency(t1.id, t2.id))
        path = project._find_path(t1.id, t2.id)
        assert len(path) == 2
        assert path[0] == t1.id
        assert path[1] == t2.id

    def test_find_path_self(self, project):
        # یافتن مسیر از گره به خودش
        t1 = project.create_task("A")
        path = project._find_path(t1.id, t1.id)
        assert len(path) == 1
        assert path[0] == t1.id

    def test_find_path_no_path(self, project):
        # یافتن مسیر وقتی مسیری وجود ندارد
        t1 = project.create_task("A")
        t2 = project.create_task("B")
        path = project._find_path(t1.id, t2.id)
        assert len(path) == 0

    # ─── حذف وظیفه و شنودگرها ────────────────────────────────────

    def test_delete_task_emits_dependency_removed(self, project):
        # حذف وظیفه — رویداد DependencyRemoved برای هر وابستگی ارسال می‌شود
        events = []
        project.subscribe(events.append)
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id))
        project.delete_task(t1.id)
        dep_removed = [e for e in events if isinstance(e, DependencyRemoved)]
        assert len(dep_removed) == 1

    # ─── وابستگی‌های مختلف بین دو وظیفه ──────────────────────────

    def test_multiple_dep_types_between_same_tasks(self, project):
        # وابستگی‌های مختلف بین دو وظیفه — FS و SS مجزا هستند
        t1 = project.create_task("وظیفه ۱")
        t2 = project.create_task("وظیفه ۲")
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.FINISH_START))
        project.add_dependency(Dependency(t1.id, t2.id, DependencyType.START_START))
        assert project.dependency_count == 2


# ═══════════════════════════════════════════════════════════════════
#  test_events
# ═══════════════════════════════════════════════════════════════════


class TestEvents:
    """تست‌های رویدادهای دامنه — ساخت و دسترسی فیلدها"""

    def test_domain_event_has_timestamp(self):
        # رویداد پایه دارای زمان‌ stamp
        e = DomainEvent()
        assert e.occurred_at is not None
        assert isinstance(e.occurred_at, datetime)

    def test_task_created(self):
        # رویداد ساخت وظیفه
        tid = TaskId("T001")
        e = TaskCreated(task_id=tid, title="وظیفه")
        assert e.task_id == tid
        assert e.title == "وظیفه"
        assert e.occurred_at is not None

    def test_task_updated(self):
        # رویداد بروزرسانی وظیفه
        tid = TaskId("T001")
        e = TaskUpdated(task_id=tid, field="title", old="قدیم", new="جدید")
        assert e.task_id == tid
        assert e.field == "title"
        assert e.old == "قدیم"
        assert e.new == "جدید"

    def test_task_deleted(self):
        # رویداد حذف وظیفه
        tid = TaskId("T001")
        e = TaskDeleted(task_id=tid)
        assert e.task_id == tid

    def test_task_status_changed(self):
        # رویداد تغییر وضعیت
        tid = TaskId("T001")
        e = TaskStatusChanged(task_id=tid, old="draft", new="ready")
        assert e.task_id == tid
        assert e.old == "draft"
        assert e.new == "ready"

    def test_dependency_added(self):
        # رویداد افزودن وابستگی
        pred = TaskId("T001")
        succ = TaskId("T002")
        e = DependencyAdded(predecessor_id=pred, successor_id=succ, dep_type="FS")
        assert e.predecessor_id == pred
        assert e.successor_id == succ
        assert e.dep_type == "FS"

    def test_dependency_removed(self):
        # رویداد حذف وابستگی
        pred = TaskId("T001")
        succ = TaskId("T002")
        e = DependencyRemoved(predecessor_id=pred, successor_id=succ)
        assert e.predecessor_id == pred
        assert e.successor_id == succ

    def test_cycle_detected(self):
        # رویداد تشخیص چرخه
        e = CycleDetected(
            attempted_edge=("T001", "T002"),
            cycle=("T002", "T001"),
        )
        assert e.attempted_edge == ("T001", "T002")
        assert e.cycle == ("T002", "T001")

    def test_project_reset(self):
        # رویداد پاکسازی پروژه
        e = ProjectReset()
        assert e.occurred_at is not None

    def test_project_loaded(self):
        # رویداد بارگذاری پروژه
        e = ProjectLoaded(source="file.json", task_count=5)
        assert e.source == "file.json"
        assert e.task_count == 5

    def test_schedule_recalculated(self):
        # رویداد محاسبه مجدد زمان‌بندی
        e = ScheduleRecalculated(
            project_duration_minutes=4800,
            critical_path=(TaskId("T001"), TaskId("T002")),
        )
        assert e.project_duration_minutes == 4800
        assert len(e.critical_path) == 2

    def test_events_are_frozen(self):
        # رویدادها تغییرناپذیر هستند
        e = TaskCreated(task_id=TaskId("T001"), title="وظیفه")
        with pytest.raises(AttributeError):
            e.title = "عنوان دیگر"

    def test_events_default_values(self):
        # مقادیر پیش‌فرض رویدادها
        e = TaskCreated()
        assert e.task_id is None
        assert e.title == ""

    def test_dependency_added_default_dep_type(self):
        # نوع پیش‌فرض وابستگی در رویداد
        e = DependencyAdded(predecessor_id=TaskId("T001"), successor_id=TaskId("T002"))
        assert e.dep_type == "FS"

    def test_cycle_detected_default_values(self):
        # مقادیر پیش‌فرض رویداد تشخیص چرخه
        e = CycleDetected()
        assert e.attempted_edge == ()
        assert e.cycle == ()
