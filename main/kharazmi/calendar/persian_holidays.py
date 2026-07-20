"""
Built-in Persian (Iranian) holidays and observances.

These are added as a read-only calendar when the user first runs the
Basic plan. Each holiday is a recurring yearly event.

Sources: standard Iranian official holidays. Religious holidays follow
the Lunar Hijri calendar and shift each Gregorian year; for simplicity
we approximate them by their typical Shamsi date (some inaccuracy is
expected — proper lunar conversion would require an additional
algorithm).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..core.shamsi import ShamsiDate, days_in_month
from .calendar import Calendar
from .event import Event
from .enums import EventType, Availability, EventStatus
from .recurrence import RecurrenceRule, RecurrenceFrequency


# ---- Fixed Shamsi holidays ----
# (month, day, name, is_national)

FIXED_HOLIDAYS = [
    (1, 1,  "نوروز (Nowruz — Persian New Year)", True),
    (1, 2,  "نوروز (Nowruz — Day 2)", True),
    (1, 3,  "نوروز (Nowruz — Day 3)", True),
    (1, 4,  "نوروز (Nowruz — Day 4)", True),
    (1, 12, "روز جمهوری اسلامی (Islamic Republic Day)", True),
    (1, 13, "سیزده‌بدر (Sizdah Bedar — Nature Day)", True),
    (3, 14, "وفات امام خمینی (Demise of Imam Khomeini)", True),
    (3, 15, "قیام ۱۵ خرداد (Khordad 15 Uprising)", True),
    (11, 22, "پیروزی انقلاب اسلامی (Victory of Islamic Revolution)", True),
    (12, 29, "روز ملی شدن صنعت نفت (Nationalization of Oil Industry)", True),
]

# Religious holidays — these are lunar and shift; we use approximate Shamsi positions.
# Marked as approximate.
RELIGIOUS_HOLIDAYS = [
    (1, 9,   "تاسوعای حسینی (Tasua) — approximate", True),
    (1, 10,  "عاشورای حسینی (Ashura) — approximate", True),
    (2, 20,  "اربعین حسینی (Arbaeen) — approximate", True),
    (2, 28,  "رحلت پیامبر اکرم (Demise of Prophet) — approximate", True),
    (2, 29,  "شهادت امام رضا (Martyrdom of Imam Reza) — approximate", True),
    (3, 8,   "میلاد پیامبر و امام صادق (Birth of Prophet) — approximate", True),
    (6, 3,   "شهادت حضرت فاطمه (Martyrdom of Fatima) — approximate", True),
    (7, 13,  "میلاد امام علی (Birth of Imam Ali) — approximate", True),
    (7, 27,  "مبعث پیامبر اکرم (Mab'ath) — approximate", True),
    (8, 15,  "میلاد امام زمان (Birth of Mahdi) — approximate", True),
    (9, 21,  "شهادت امام علی (Martyrdom of Imam Ali) — approximate", True),
    (10, 1,  "عید فطر (Eid al-Fitr) — approximate", True),
    (10, 2,  "تعطیل عید فطر — approximate", True),
    (10, 25, "شهادت امام جعفر صادق (Martyrdom of Imam Sadiq) — approximate", True),
    (12, 10, "عید قربان (Eid al-Adha) — approximate", True),
    (12, 18, "عید غدیر خم (Eid al-Ghadir) — approximate", True),
]


# ---- Color for holiday calendar ----
HOLIDAY_CALENDAR_COLOR = "#A85A5A"   # muted red
BIRTHDAY_CALENDAR_COLOR = "#7A5AA8"  # purple


def create_holiday_calendar() -> Calendar:
    """Create the read-only Persian holidays calendar."""
    return Calendar(
        id="cal-holidays",
        name="Persian Holidays",
        color=HOLIDAY_CALENDAR_COLOR,
        visible=True,
        description="Official Iranian national and religious holidays (Shamsi calendar)",
        is_default=False,
        is_readonly=True,
        owner="system",
    )


def create_holiday_events() -> list[Event]:
    """Create all the recurring holiday events."""
    events: list[Event] = []
    # Fixed national holidays
    for month, day, name, is_national in FIXED_HOLIDAYS:
        # Use year 1400 as seed (will recur yearly)
        try:
            seed_date = ShamsiDate(1400, month, day).to_gregorian()
            start = datetime.combine(seed_date, datetime.min.time())
            end = start + timedelta(days=1)
            events.append(Event(
                id=f"holiday-fixed-{month}-{day}",
                calendar_id="cal-holidays",
                title=name,
                start=start,
                end=end,
                all_day=True,
                event_type=EventType.HOLIDAY,
                availability=Availability.FREE,
                status=EventStatus.CONFIRMED,
                recurrence=RecurrenceRule(freq=RecurrenceFrequency.YEARLY),
            ))
        except (ValueError, IndexError):
            continue
    # Religious holidays (approximate)
    for month, day, name, is_national in RELIGIOUS_HOLIDAYS:
        try:
            seed_date = ShamsiDate(1400, month, day).to_gregorian()
            start = datetime.combine(seed_date, datetime.min.time())
            end = start + timedelta(days=1)
            events.append(Event(
                id=f"holiday-religious-{month}-{day}",
                calendar_id="cal-holidays",
                title=name,
                start=start,
                end=end,
                all_day=True,
                event_type=EventType.HOLIDAY,
                availability=Availability.FREE,
                status=EventStatus.CONFIRMED,
                recurrence=RecurrenceRule(freq=RecurrenceFrequency.YEARLY),
            ))
        except (ValueError, IndexError):
            continue
    return events
