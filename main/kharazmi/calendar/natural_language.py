"""
Natural-language event parser.

Parses strings like:
  "Lunch with Sarah tomorrow at 1 PM"
  "Meeting every Monday at 10am"
  "Doctor appointment next Friday 3pm"
  "Call mom today at 6pm"
  "Vacation from July 1 to July 14"

Returns a structured dict the UI can use to pre-fill the event editor.

The parser is intentionally lightweight — no ML, just regex patterns
and keyword matching. It handles the common cases Google Calendar's
own NL input handles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from ..core.shamsi import ShamsiDate, days_in_month


# ---- Time-of-day patterns ----

_TIME_PATTERNS = [
    # "1 PM", "1pm", "1:30 PM", "1:30pm"
    (re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE), "_parse_12h"),
    # "13:00", "13:00:00", "0930"
    (re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b"), "_parse_24h"),
    # "1300" (military)
    (re.compile(r"\b(\d{4})\b"), "_parse_military"),
    # "noon"
    (re.compile(r"\bnoon\b", re.IGNORECASE), "_parse_noon"),
    # "midnight"
    (re.compile(r"\bmidnight\b", re.IGNORECASE), "_parse_midnight"),
    # "morning" → 9am, "afternoon" → 2pm, "evening" → 6pm
    (re.compile(r"\bmorning\b", re.IGNORECASE), "_parse_morning"),
    (re.compile(r"\bafternoon\b", re.IGNORECASE), "_parse_afternoon"),
    (re.compile(r"\bevening\b", re.IGNORECASE), "_parse_evening"),
]


# ---- Date patterns ----

_DATE_PATTERNS = [
    # "today", "tomorrow", "tonight"
    (re.compile(r"\btoday\b", re.IGNORECASE), "_date_today"),
    (re.compile(r"\btomorrow\b", re.IGNORECASE), "_date_tomorrow"),
    (re.compile(r"\btonight\b", re.IGNORECASE), "_date_tonight"),
    # "next Monday", "next week", "next month"
    (re.compile(r"\bnext\s+(\w+)\b", re.IGNORECASE), "_date_next"),
    # "this Monday", "this week"
    (re.compile(r"\bthis\s+(\w+)\b", re.IGNORECASE), "_date_this"),
    # "in 3 days", "in 2 weeks", "in 1 month"
    (re.compile(r"\bin\s+(\d+)\s+(day|days|week|weeks|month|months|year|years)\b", re.IGNORECASE), "_date_in"),
    # "Monday", "Tuesday", etc.
    (re.compile(r"\b(saturday|sunday|monday|tuesday|wednesday|thursday|friday)\b", re.IGNORECASE), "_date_weekday"),
    # Shamsi date "1403/05/14"
    (re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b"), "_date_shamsi"),
    # Gregorian date "July 14" or "Jul 14"
    (re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})\b", re.IGNORECASE), "_date_month_day"),
]


# ---- Duration patterns ----

_DURATION_PATTERNS = [
    # "for 2 hours", "for 30 minutes", "for 1 hour"
    (re.compile(r"\bfor\s+(\d+)\s+(hour|hours|hr|hrs|minute|minutes|min|mins)\b", re.IGNORECASE), "_parse_duration"),
    # "2 hours", "30 min"
    (re.compile(r"\b(\d+)\s+(hour|hours|hr|hrs|minute|minutes|min|mins)\b", re.IGNORECASE), "_parse_duration"),
    # "all day"
    (re.compile(r"\ball\s*day\b", re.IGNORECASE), "_parse_all_day"),
]


# ---- Recurrence patterns ----

_RECURRENCE_PATTERNS = [
    (re.compile(r"\bevery\s+day\b", re.IGNORECASE), "daily"),
    (re.compile(r"\bdaily\b", re.IGNORECASE), "daily"),
    (re.compile(r"\bevery\s+weekday\b", re.IGNORECASE), "weekdays"),
    (re.compile(r"\bevery\s+week\b", re.IGNORECASE), "weekly"),
    (re.compile(r"\bweekly\b", re.IGNORECASE), "weekly"),
    (re.compile(r"\bevery\s+month\b", re.IGNORECASE), "monthly"),
    (re.compile(r"\bmonthly\b", re.IGNORECASE), "monthly"),
    (re.compile(r"\bevery\s+year\b", re.IGNORECASE), "yearly"),
    (re.compile(r"\byearly\b", re.IGNORECASE), "yearly"),
    (re.compile(r"\bannually\b", re.IGNORECASE), "yearly"),
    (re.compile(r"\bevery\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE), "weekly_weekday"),
]


# ---- Event-type detection ----

_TYPE_KEYWORDS = [
    (re.compile(r"\b(meeting|standup|sync|call|conference|stand-up)\b", re.IGNORECASE), "meeting"),
    (re.compile(r"\b(appointment|doctor|dentist|interview)\b", re.IGNORECASE), "appointment"),
    (re.compile(r"\b(lunch|dinner|breakfast|coffee|meal)\b", re.IGNORECASE), "normal"),
    (re.compile(r"\b(birthday|bday)\b", re.IGNORECASE), "birthday"),
    (re.compile(r"\b(focus|deep work|coding session|writing session)\b", re.IGNORECASE), "focus_time"),
    (re.compile(r"\b(out of office|ooo|vacation|holiday|leave|away)\b", re.IGNORECASE), "out_of_office"),
    (re.compile(r"\b(task|todo|to-do|remember|remind me)\b", re.IGNORECASE), "task"),
]


# ---- Attendee detection ----

_WITH_PATTERN = re.compile(r"\bwith\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b")
_AND_PATTERN = re.compile(r"\bwith\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+and\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\b")


@dataclass
class ParsedEvent:
    """Result of NL parsing."""
    title: str = ""
    start: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    all_day: bool = False
    recurrence: Optional[str] = None  # one of: daily, weekly, monthly, yearly, weekdays, weekly_weekday
    event_type: str = "normal"
    attendees: list[str] = field(default_factory=list)
    location: str = ""
    confidence: float = 0.0  # 0..1, how confident we are in the parse


def parse(text: str, now: Optional[datetime] = None) -> ParsedEvent:
    """
    Parse a natural-language event description.

    Returns a ParsedEvent with as much info as we could extract.
    """
    if not text or not text.strip():
        return ParsedEvent()
    if now is None:
        now = datetime.now()

    result = ParsedEvent()
    work = text.strip()

    # 1. Extract recurrence FIRST (before date extraction eats weekday names)
    for pattern, key in _RECURRENCE_PATTERNS:
        if pattern.search(work):
            result.recurrence = key
            work = pattern.sub("", work)
            break

    # 2. Extract date
    base_date = ShamsiDate.from_gregorian(now.date())
    found_date = False
    for pattern, handler_name in _DATE_PATTERNS:
        m = pattern.search(work)
        if m:
            handler = globals().get(handler_name)
            if handler:
                try:
                    new_date = handler(m, base_date, now)
                    if new_date is not None:
                        base_date = new_date
                        found_date = True
                        work = work[:m.start()] + " " + work[m.end():]
                        break
                except Exception:
                    continue

    # 3. Extract time
    hour, minute = 9, 0  # default 9am
    found_time = False
    for pattern, handler_name in _TIME_PATTERNS:
        m = pattern.search(work)
        if m:
            handler = globals().get(handler_name)
            if handler:
                try:
                    parsed = handler(m)
                    if parsed is not None:
                        hour, minute = parsed
                        found_time = True
                        work = work[:m.start()] + " " + work[m.end():]
                        break
                except Exception:
                    continue

    # 4. Extract duration
    for pattern, handler_name in _DURATION_PATTERNS:
        m = pattern.search(work)
        if m:
            handler = globals().get(handler_name)
            if handler:
                try:
                    parsed = handler(m)
                    if parsed is not None:
                        if parsed == "all_day":
                            result.all_day = True
                        else:
                            result.duration_minutes = parsed
                        work = work[:m.start()] + " " + work[m.end():]
                        break
                except Exception:
                    continue

    # 5. Extract event type
    for pattern, etype in _TYPE_KEYWORDS:
        if pattern.search(work):
            result.event_type = etype
            break

    # 6. Extract attendees ("with X" or "with X and Y")
    m = _AND_PATTERN.search(text)
    if m:
        result.attendees = [m.group(1).strip(), m.group(2).strip()]
    else:
        m = _WITH_PATTERN.search(text)
        if m:
            result.attendees = [m.group(1).strip()]

    # 7. Build start datetime
    if result.all_day:
        result.start = base_date.to_datetime(0, 0)
    else:
        result.start = base_date.to_datetime(hour, minute)

    # 8. Title = whatever's left after removing patterns (cleaned up)
    title = work.strip()
    # Remove connector words
    title = re.sub(r"\b(at|on|for|to|from)\b", "", title, flags=re.IGNORECASE)
    # Remove "with X" patterns
    title = _WITH_PATTERN.sub("", title)
    title = _AND_PATTERN.sub("", title)
    # Remove "every <word>" patterns (recurrence leftovers)
    title = re.sub(r"\bevery\s+\w+\b", "", title, flags=re.IGNORECASE)
    # Remove standalone recurrence keywords
    title = re.sub(r"\b(daily|weekly|monthly|yearly|annually)\b", "", title, flags=re.IGNORECASE)
    # Remove leftover numbers + units
    title = re.sub(r"\b\d+\s+(day|days|week|weeks|month|months|year|years)\b", "", title, flags=re.IGNORECASE)
    # Clean whitespace
    title = re.sub(r"\s+", " ", title).strip()
    # Strip trailing punctuation
    title = title.rstrip(".!,;:")
    result.title = title if title else "Untitled event"

    # Confidence
    confidence = 0.0
    if found_date:
        confidence += 0.4
    if found_time:
        confidence += 0.3
    if result.duration_minutes is not None or result.all_day:
        confidence += 0.15
    if result.attendees:
        confidence += 0.1
    if result.recurrence:
        confidence += 0.05
    result.confidence = min(1.0, confidence)

    return result


# ---- Time handlers ----

def _parse_12h(m: re.Match) -> tuple[int, int]:
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return hour, minute


def _parse_24h(m: re.Match) -> tuple[int, int]:
    hour = int(m.group(1))
    minute = int(m.group(2))
    return hour, minute


def _parse_military(m: re.Match) -> Optional[tuple[int, int]]:
    val = int(m.group(1))
    if val < 100 or val > 2359:
        return None
    hour = val // 100
    minute = val % 100
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _parse_noon(m: re.Match) -> tuple[int, int]:
    return 12, 0


def _parse_midnight(m: re.Match) -> tuple[int, int]:
    return 0, 0


def _parse_morning(m: re.Match) -> tuple[int, int]:
    return 9, 0


def _parse_afternoon(m: re.Match) -> tuple[int, int]:
    return 14, 0


def _parse_evening(m: re.Match) -> tuple[int, int]:
    return 18, 0


# ---- Date handlers ----

def _date_today(m: re.Match, base: ShamsiDate, now: datetime) -> ShamsiDate:
    return base


def _date_tomorrow(m: re.Match, base: ShamsiDate, now: datetime) -> ShamsiDate:
    return base.add_days(1)


def _date_tonight(m: re.Match, base: ShamsiDate, now: datetime) -> ShamsiDate:
    return base


def _date_next(m: re.Match, base: ShamsiDate, now: datetime) -> Optional[ShamsiDate]:
    word = m.group(1).lower()
    weekdays = {
        "saturday": 0, "sunday": 1, "monday": 2, "tuesday": 3,
        "wednesday": 4, "thursday": 5, "friday": 6,
    }
    if word in weekdays:
        target_wd = weekdays[word]
        today_wd = (base.to_gregorian().weekday() + 2) % 7
        days_ahead = (target_wd - today_wd) % 7
        if days_ahead == 0:
            days_ahead = 7  # "next Monday" = next week's Monday
        return base.add_days(days_ahead)
    if word == "week":
        return base.add_days(7)
    if word == "month":
        return base.add_months(1)
    if word == "year":
        return base.add_years(1)
    return None


def _date_this(m: re.Match, base: ShamsiDate, now: datetime) -> Optional[ShamsiDate]:
    word = m.group(1).lower()
    weekdays = {
        "saturday": 0, "sunday": 1, "monday": 2, "tuesday": 3,
        "wednesday": 4, "thursday": 5, "friday": 6,
    }
    if word in weekdays:
        target_wd = weekdays[word]
        today_wd = (base.to_gregorian().weekday() + 2) % 7
        days_ahead = (target_wd - today_wd) % 7
        return base.add_days(days_ahead)
    return None


def _date_in(m: re.Match, base: ShamsiDate, now: datetime) -> Optional[ShamsiDate]:
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("day"):
        return base.add_days(amount)
    if unit.startswith("week"):
        return base.add_days(amount * 7)
    if unit.startswith("month"):
        return base.add_months(amount)
    if unit.startswith("year"):
        return base.add_years(amount)
    return None


def _date_weekday(m: re.Match, base: ShamsiDate, now: datetime) -> Optional[ShamsiDate]:
    word = m.group(1).lower()
    weekdays = {
        "saturday": 0, "sunday": 1, "monday": 2, "tuesday": 3,
        "wednesday": 4, "thursday": 5, "friday": 6,
    }
    target_wd = weekdays[word]
    today_wd = (base.to_gregorian().weekday() + 2) % 7
    days_ahead = (target_wd - today_wd) % 7
    if days_ahead == 0:
        days_ahead = 7  # "Monday" means next Monday
    return base.add_days(days_ahead)


def _date_shamsi(m: re.Match, base: ShamsiDate, now: datetime) -> Optional[ShamsiDate]:
    try:
        return ShamsiDate(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _date_month_day(m: re.Match, base: ShamsiDate, now: datetime) -> Optional[ShamsiDate]:
    """Parse 'July 14' as a Gregorian month/day; convert to Shamsi."""
    month_names = {
        "january": 1, "jan": 1, "february": 2, "feb": 2,
        "march": 3, "mar": 3, "april": 4, "apr": 4,
        "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sep": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    month_name = m.group(1).lower()
    day = int(m.group(2))
    if month_name not in month_names:
        return None
    g_month = month_names[month_name]
    g_year = now.year
    from datetime import date as g_date
    try:
        target = g_date(g_year, g_month, day)
        if target < now.date():
            target = g_date(g_year + 1, g_month, day)
        return ShamsiDate.from_gregorian(target)
    except ValueError:
        return None


# ---- Duration handlers ----

def _parse_duration(m: re.Match):
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("hour") or unit in ("hr", "hrs"):
        return amount * 60
    if unit.startswith("minute") or unit in ("min", "mins"):
        return amount
    return None


def _parse_all_day(m: re.Match):
    return "all_day"
