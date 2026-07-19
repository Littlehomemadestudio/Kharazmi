"""
Recurrence rules — modeled on RFC 5545 RRULE but simplified.

A RecurrenceRule describes how an event repeats. It is parsed into a
series of concrete datetimes by `expand()`.

Supported parts (subset of RRULE):
  FREQ        = DAILY | WEEKLY | MONTHLY | YEARLY
  INTERVAL    = N (default 1)
  COUNT       = N (mutually exclusive with UNTIL)
  UNTIL       = datetime
  BYDAY       = list of weekday tokens (MO, TU, WE, TH, FR, SA, SU)
                with optional ordinal prefix (e.g. 1MO = first Monday,
                -1FR = last Friday)
  BYMONTHDAY  = list of day-of-month numbers (1..31, or -1..-31)

Examples:
  Every weekday:  FREQ=WEEKLY; BYDAY=MO,TU,WE,TH,FR
  Every 2 weeks:  FREQ=WEEKLY; INTERVAL=2
  Monthly on 15th: FREQ=MONTHLY; BYMONTHDAY=15
  Last Friday of month: FREQ=MONTHLY; BYDAY=-1FR
  Yearly (birthday): FREQ=YEARLY
  10 occurrences: FREQ=DAILY; COUNT=10
  Until a date: FREQ=WEEKLY; UNTIL=20260101T000000Z
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Iterator

from .enums import RecurrenceFrequency, Weekday
from ..core.shamsi import ShamsiDate, days_in_month


_WEEKDAY_TOKENS = {
    "SA": Weekday.SATURDAY,
    "SU": Weekday.SUNDAY,
    "MO": Weekday.MONDAY,
    "TU": Weekday.TUESDAY,
    "WE": Weekday.WEDNESDAY,
    "TH": Weekday.THURSDAY,
    "FR": Weekday.FRIDAY,
}


@dataclass(frozen=True)
class ByDay:
    """A single BYDAY entry: a weekday with an optional ordinal."""
    weekday: Weekday
    ordinal: Optional[int] = None  # None=any, 1=first, 2=second, -1=last, etc.

    def __str__(self) -> str:
        if self.ordinal is None:
            return self.weekday.name[:2]
        return f"{self.ordinal}{self.weekday.name[:2]}"


@dataclass(frozen=True)
class RecurrenceRule:
    """A simplified RRULE."""
    freq: RecurrenceFrequency = RecurrenceFrequency.WEEKLY
    interval: int = 1
    count: Optional[int] = None
    until: Optional[datetime] = None
    by_day: tuple[ByDay, ...] = ()
    by_month_day: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError("interval must be >= 1")
        if self.count is not None and self.count < 1:
            raise ValueError("count must be >= 1")
        if self.count is not None and self.until is not None:
            raise ValueError("count and until are mutually exclusive")

    def to_rrule_str(self) -> str:
        parts = [f"FREQ={self.freq.value.upper()}"]
        if self.interval != 1:
            parts.append(f"INTERVAL={self.interval}")
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
        if self.until is not None:
            parts.append(f"UNTIL={self.until.strftime('%Y%m%dT%H%M%SZ')}")
        if self.by_day:
            parts.append(f"BYDAY={','.join(str(b) for b in self.by_day)}")
        if self.by_month_day:
            parts.append(f"BYMONTHDAY={','.join(str(d) for d in self.by_month_day)}")
        return ";".join(parts)

    @classmethod
    def from_rrule_str(cls, s: str) -> "RecurrenceRule":
        parts = {}
        for token in s.split(";"):
            if "=" not in token:
                continue
            k, v = token.split("=", 1)
            parts[k.strip().upper()] = v.strip()
        freq = RecurrenceFrequency(parts.get("FREQ", "WEEKLY").lower())
        interval = int(parts.get("INTERVAL", "1"))
        count = int(parts["COUNT"]) if "COUNT" in parts else None
        until = None
        if "UNTIL" in parts:
            try:
                until = datetime.strptime(parts["UNTIL"], "%Y%m%dT%H%M%SZ")
            except ValueError:
                try:
                    until = datetime.strptime(parts["UNTIL"], "%Y%m%d")
                except ValueError:
                    pass
        by_day: tuple[ByDay, ...] = ()
        if "BYDAY" in parts:
            parsed = []
            for tok in parts["BYDAY"].split(","):
                tok = tok.strip()
                m = re.match(r"^(-?\d+)?([A-Z]{2})$", tok)
                if m:
                    ord_str, wd = m.groups()
                    if wd in _WEEKDAY_TOKENS:
                        ordinal = int(ord_str) if ord_str else None
                        parsed.append(ByDay(_WEEKDAY_TOKENS[wd], ordinal))
            by_day = tuple(parsed)
        by_month_day: tuple[int, ...] = ()
        if "BYMONTHDAY" in parts:
            by_month_day = tuple(
                int(x) for x in parts["BYMONTHDAY"].split(",") if x.strip()
            )
        return cls(
            freq=freq, interval=interval, count=count, until=until,
            by_day=by_day, by_month_day=by_month_day,
        )

    def to_dict(self) -> dict:
        return {
            "rrule": self.to_rrule_str(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecurrenceRule":
        if "rrule" not in data:
            return cls()
        return cls.from_rrule_str(data["rrule"])

    # ---- Expansion ----
    def expand(self, start: datetime,
               window_start: datetime,
               window_end: datetime,
               max_iterations: int = 10000) -> Iterator[datetime]:
        """
        Yield concrete occurrence datetimes within [window_start, window_end).

        `start` is the seed datetime (the first occurrence).
        """
        if start > window_end:
            return
        occurrences_yielded = 0
        # Start from the seed; for each candidate, check if it's in window.
        current = start
        iterations = 0
        while iterations < max_iterations:
            iterations += 1
            # Check termination
            if self.until is not None and current > self.until:
                return
            if self.count is not None and occurrences_yielded >= self.count:
                return
            if current > window_end:
                return

            # Generate candidates at this "step"
            candidates = self._candidates_at_step(start, current)

            for cand in candidates:
                if cand < start:
                    continue
                if self.until is not None and cand > self.until:
                    continue
                if self.count is not None and occurrences_yielded >= self.count:
                    return
                if window_start <= cand <= window_end:
                    yield cand
                    occurrences_yielded += 1
                elif cand > window_end:
                    return

            # Advance to next step
            current = self._advance_step(start, current)
            if current is None:
                return

    def _candidates_at_step(self, seed: datetime, current: datetime) -> list[datetime]:
        """Generate candidate datetimes at the current step."""
        if self.freq == RecurrenceFrequency.DAILY:
            return [current]
        if self.freq == RecurrenceFrequency.WEEKLY:
            if not self.by_day:
                return [current]
            # Yield one occurrence per weekday in by_day, in the week of `current`
            results = []
            week_start = current - timedelta(days=self._iranian_weekday_of(current))
            for bd in self.by_day:
                cand = week_start + timedelta(days=int(bd.weekday))
                cand = cand.replace(
                    hour=seed.hour, minute=seed.minute,
                    second=seed.second, microsecond=seed.microsecond
                )
                if cand >= seed:
                    results.append(cand)
            return sorted(results)
        if self.freq == RecurrenceFrequency.MONTHLY:
            sd = ShamsiDate.from_gregorian(current.date())
            if self.by_month_day:
                results = []
                for md in self.by_month_day:
                    try:
                        if md > 0:
                            day = md
                        else:
                            # Negative = count from end
                            last = days_in_month(sd.year, sd.month)
                            day = last + md + 1
                        if 1 <= day <= days_in_month(sd.year, sd.month):
                            cand_date = ShamsiDate(sd.year, sd.month, day).to_gregorian()
                            cand = datetime.combine(cand_date, seed.time())
                            results.append(cand)
                    except (ValueError, IndexError):
                        continue
                return sorted(results)
            if self.by_day:
                results = []
                for bd in self.by_day:
                    cand = self._nth_weekday_of_month(sd, bd)
                    if cand is not None:
                        cand_dt = datetime.combine(cand.to_gregorian(), seed.time())
                        results.append(cand_dt)
                return sorted(results)
            # Default: same day-of-month as seed
            seed_sd = ShamsiDate.from_gregorian(seed.date())
            try:
                cand_date = ShamsiDate(sd.year, sd.month, seed_sd.day).to_gregorian()
                cand = datetime.combine(cand_date, seed.time())
                return [cand]
            except ValueError:
                return []
        if self.freq == RecurrenceFrequency.YEARLY:
            sd = ShamsiDate.from_gregorian(current.date())
            seed_sd = ShamsiDate.from_gregorian(seed.date())
            try:
                cand_date = ShamsiDate(sd.year, seed_sd.month, seed_sd.day).to_gregorian()
                cand = datetime.combine(cand_date, seed.time())
                return [cand]
            except ValueError:
                return []
        return [current]

    def _advance_step(self, seed: datetime, current: datetime) -> Optional[datetime]:
        """Advance `current` by one interval of the recurrence frequency."""
        if self.freq == RecurrenceFrequency.DAILY:
            return current + timedelta(days=self.interval)
        if self.freq == RecurrenceFrequency.WEEKLY:
            return current + timedelta(weeks=self.interval)
        if self.freq == RecurrenceFrequency.MONTHLY:
            sd = ShamsiDate.from_gregorian(current.date())
            try:
                new_sd = sd.add_months(self.interval)
                return datetime.combine(new_sd.to_gregorian(), current.time())
            except Exception:
                return None
        if self.freq == RecurrenceFrequency.YEARLY:
            sd = ShamsiDate.from_gregorian(current.date())
            try:
                new_sd = sd.add_years(self.interval)
                return datetime.combine(new_sd.to_gregorian(), current.time())
            except Exception:
                return None
        return None

    @staticmethod
    def _iranian_weekday_of(dt: datetime) -> int:
        """Saturday=0 ... Friday=6."""
        py_wd = dt.weekday()  # Mon=0..Sun=6
        return (py_wd + 2) % 7

    @staticmethod
    def _nth_weekday_of_month(sd: ShamsiDate, bd: ByDay) -> Optional[ShamsiDate]:
        """Find the Nth weekday of the month (e.g. 2nd Monday)."""
        first = ShamsiDate(sd.year, sd.month, 1)
        first_wd = (first.to_gregorian().weekday() + 2) % 7
        target_wd = int(bd.weekday)
        offset = (target_wd - first_wd) % 7
        if bd.ordinal is None:
            # First occurrence
            day = 1 + offset
            if day <= days_in_month(sd.year, sd.month):
                return ShamsiDate(sd.year, sd.month, day)
            return None
        elif bd.ordinal > 0:
            day = 1 + offset + (bd.ordinal - 1) * 7
            if day <= days_in_month(sd.year, sd.month):
                return ShamsiDate(sd.year, sd.month, day)
            return None
        else:
            # Negative = count from end
            last_day = days_in_month(sd.year, sd.month)
            last = ShamsiDate(sd.year, sd.month, last_day)
            last_wd = (last.to_gregorian().weekday() + 2) % 7
            back_offset = (last_wd - target_wd) % 7
            day = last_day - back_offset - (-bd.ordinal - 1) * 7
            if day >= 1:
                return ShamsiDate(sd.year, sd.month, day)
            return None


# ---- Preset rules (for the UI) ----

PRESET_RULES = {
    "Every day": RecurrenceRule(freq=RecurrenceFrequency.DAILY),
    "Every weekday": RecurrenceRule(
        freq=RecurrenceFrequency.WEEKLY,
        by_day=(ByDay(Weekday.MONDAY), ByDay(Weekday.TUESDAY),
                 ByDay(Weekday.WEDNESDAY), ByDay(Weekday.THURSDAY),
                 ByDay(Weekday.FRIDAY)),
    ),
    "Every week": RecurrenceRule(freq=RecurrenceFrequency.WEEKLY),
    "Every 2 weeks": RecurrenceRule(freq=RecurrenceFrequency.WEEKLY, interval=2),
    "Every month": RecurrenceRule(freq=RecurrenceFrequency.MONTHLY),
    "Every year": RecurrenceRule(freq=RecurrenceFrequency.YEARLY),
    "Weekends": RecurrenceRule(
        freq=RecurrenceFrequency.WEEKLY,
        by_day=(ByDay(Weekday.FRIDAY),),
    ),
}
