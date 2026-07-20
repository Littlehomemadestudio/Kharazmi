"""
Persian Shamsi (Jalali) calendar utilities.

Provides bidirectional conversion between Gregorian and Jalali dates,
formatting in Persian style, and helper functions used throughout
the UI.

All display dates in Rask go through `format_shamsi` so the entire
application speaks Shamsi — the Gregorian calendar is only used for
internal storage and CPM math (which is timezone-naive UTC).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional


# ---- Persian names ----

SHAMSI_MONTHS_FA = [
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
]

SHAMSI_MONTHS_EN = [
    "Farvardin", "Ordibehesht", "Khordad",
    "Tir", "Mordad", "Shahrivar",
    "Mehr", "Aban", "Azar",
    "Dey", "Bahman", "Esfand",
]

SHAMSI_WEEKDAYS_FA = [
    "دوشنبه",   # Monday (0)
    "سه‌شنبه",  # Tuesday (1)
    "چهارشنبه", # Wednesday (2)
    "پنجشنبه",  # Thursday (3)
    "جمعه",     # Friday (4) — weekend in Iran
    "شنبه",     # Saturday (5)
    "یکشنبه",   # Sunday (6)
]

SHAMSI_WEEKDAYS_EN = [
    "Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
]

SHAMSI_WEEKDAYS_SHORT_EN = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]

SHAMSI_SEASONS_FA = ["بهار", "تابستان", "پاییز", "زمستان"]
SHAMSI_SEASONS_EN = ["Spring", "Summer", "Autumn", "Winter"]


# ---- Core conversion algorithm ----
# Reference algorithm (widely used; matches known Nowruz dates 979-3000).

def _gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert a Gregorian Y/M/D to Jalali Y/M/D."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = (365 * gy2
                + (gy2 + 3) // 4
                - (gy2 + 99) // 100
                + (gy2 + 399) // 400)
    g_day_no += g_d_m[gm2]
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    g_day_no += gd2

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    # In leap years, Esfand has 30 days
    if is_leap(jy):
        j_days_in_month[11] = 30
    i = 0
    while i < 11 and j_day_no >= j_days_in_month[i]:
        j_day_no -= j_days_in_month[i]
        i += 1
    jm = i + 1
    jd = j_day_no + 1
    return jy, jm, jd


def _jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Convert a Jalali Y/M/D to Gregorian Y/M/D."""
    jy2 = jy - 979
    j_day_no = 365 * jy2 + (jy2 // 33) * 8 + ((jy2 % 33 + 3) // 4)
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    if is_leap(jy):
        j_days_in_month[11] = 30
    for i in range(jm - 1):
        j_day_no += j_days_in_month[i]
    j_day_no += jd - 1

    g_day_no = j_day_no + 79
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gy = 1600 + 400 * (g_day_no // 146097)
    g_day_no %= 146097

    leap = True
    if g_day_no >= 36525:
        g_day_no -= 1
        gy += 100 * (g_day_no // 36524)
        g_day_no %= 36524
        if g_day_no >= 365:
            g_day_no += 1
        else:
            leap = False
    if g_day_no >= 1461:
        gy += 4 * ((g_day_no - 1) // 1461)
        g_day_no = (g_day_no - 1) % 1461
    if g_day_no >= 366:
        leap = False
        g_day_no -= 1
        gy += g_day_no // 365
        g_day_no %= 365

    i = 0
    while i < 11 and (g_day_no >= g_days_in_month[i] or (i == 1 and leap and g_day_no >= 29)):
        if i == 1 and leap:
            if g_day_no >= 29:
                g_day_no -= 29
            else:
                break
        else:
            g_day_no -= g_days_in_month[i]
        i += 1
    gm = i + 1
    gd = g_day_no + 1
    return gy, gm, gd


def is_leap(jy: int) -> bool:
    """True if the Jalali year `jy` is a leap year (Esfand has 30 days)."""
    # The Jalali leap-year cycle is 33 years long. The standard algorithm:
    breaks = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
              1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394,
              2456, 3178]
    jp = breaks[0]
    jump = 0
    for jm in breaks[1:]:
        jump = jm - jp
        if jy < jm:
            break
        jp = jm
    n = jy - jp
    if n < jump:
        if jump - n < 6:
            n = n - jump + ((jump + 4) // 33 * 33)
        leap = ((n + 1) % 33 - 1) % 4
        if leap == -1:
            leap = 4
        return leap == 0
    return False


def days_in_month(jy: int, jm: int) -> int:
    """Number of days in a Shamsi month."""
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if is_leap(jy) else 29


# ---- Public API ----

@dataclass(frozen=True)
class ShamsiDate:
    """A Shamsi (Jalali) calendar date."""
    year: int
    month: int   # 1..12
    day: int     # 1..31

    def __post_init__(self) -> None:
        if not (1 <= self.month <= 12):
            raise ValueError(f"Shamsi month must be 1..12, got {self.month}")
        max_day = days_in_month(self.year, self.month)
        if not (1 <= self.day <= max_day):
            raise ValueError(
                f"Shamsi day must be 1..{max_day} for {self.year}/{self.month}, "
                f"got {self.day}"
            )

    @classmethod
    def from_gregorian(cls, d: date | datetime) -> "ShamsiDate":
        if isinstance(d, datetime):
            d = d.date()
        jy, jm, jd = _gregorian_to_jalali(d.year, d.month, d.day)
        return cls(jy, jm, jd)

    @classmethod
    def today(cls) -> "ShamsiDate":
        return cls.from_gregorian(date.today())

    @classmethod
    def from_datetime(cls, dt: datetime) -> "ShamsiDate":
        return cls.from_gregorian(dt.date())

    def to_gregorian(self) -> date:
        gy, gm, gd = _jalali_to_gregorian(self.year, self.month, self.day)
        return date(gy, gm, gd)

    def to_datetime(self, hour: int = 0, minute: int = 0) -> datetime:
        g = self.to_gregorian()
        return datetime(g.year, g.month, g.day, hour, minute)

    @property
    def month_name_fa(self) -> str:
        return SHAMSI_MONTHS_FA[self.month - 1]

    @property
    def month_name_en(self) -> str:
        return SHAMSI_MONTHS_EN[self.month - 1]

    @property
    def weekday_fa(self) -> str:
        """Persian weekday name. Saturday=0 ... Friday=6 (Iranian week)."""
        g = self.to_gregorian()
        # Python date.weekday(): Mon=0..Sun=6
        # Iranian week: Sat=0, Sun=1, Mon=2, Tue=3, Wed=4, Thu=5, Fri=6
        py_wd = g.weekday()
        # Mon(0)->2, Tue(1)->3, Wed(2)->4, Thu(3)->5, Fri(4)->6, Sat(5)->0, Sun(6)->1
        iranian = (py_wd + 2) % 7
        return SHAMSI_WEEKDAYS_FA[iranian]

    @property
    def weekday_en(self) -> str:
        """English weekday name (Saturday..Friday)."""
        g = self.to_gregorian()
        py_wd = g.weekday()
        iranian = (py_wd + 2) % 7
        return SHAMSI_WEEKDAYS_EN[iranian]

    @property
    def weekday_short_en(self) -> str:
        g = self.to_gregorian()
        py_wd = g.weekday()
        iranian = (py_wd + 2) % 7
        return SHAMSI_WEEKDAYS_SHORT_EN[iranian]

    @property
    def is_friday(self) -> bool:
        """Friday is the Iranian weekend."""
        return self.to_gregorian().weekday() == 4

    @property
    def season_index(self) -> int:
        """0=Spring, 1=Summer, 2=Autumn, 3=Winter."""
        if self.month <= 3:
            return 0
        if self.month <= 6:
            return 1
        if self.month <= 9:
            return 2
        return 3

    @property
    def season_fa(self) -> str:
        return SHAMSI_SEASONS_FA[self.season_index]

    @property
    def season_en(self) -> str:
        return SHAMSI_SEASONS_EN[self.season_index]

    def add_days(self, n: int) -> "ShamsiDate":
        g = self.to_gregorian() + timedelta(days=n)
        return ShamsiDate.from_gregorian(g)

    def add_months(self, n: int) -> "ShamsiDate":
        total = self.month - 1 + n
        new_year = self.year + total // 12
        new_month = total % 12 + 1
        max_day = days_in_month(new_year, new_month)
        new_day = min(self.day, max_day)
        return ShamsiDate(new_year, new_month, new_day)

    def add_years(self, n: int) -> "ShamsiDate":
        new_year = self.year + n
        max_day = days_in_month(new_year, self.month)
        new_day = min(self.day, max_day)
        return ShamsiDate(new_year, self.month, new_day)

    # ---- Formatting ----
    def format(self, fmt: str = "yyyy/mm/dd",
               use_persian_digits: bool = False) -> str:
        """
        Format codes:
          yyyy  -> 4-digit year
          yy    -> 2-digit year
          mm    -> 2-digit month
          m     -> 1-2 digit month
          dd    -> 2-digit day
          d     -> 1-2 digit day
          MMM   -> English month name
          MMMM  -> Persian month name
          EEE   -> English weekday short
          EEEE  -> Persian weekday name
          SS    -> Persian season
        """
        s = fmt
        s = s.replace("yyyy", str(self.year))
        s = s.replace("yy", str(self.year)[-2:])
        s = s.replace("MMMM", self.month_name_fa)
        s = s.replace("MMM", self.month_name_en)
        s = s.replace("mm", f"{self.month:02d}")
        s = s.replace("m", str(self.month))
        s = s.replace("EEEE", self.weekday_fa)
        s = s.replace("EEE", self.weekday_short_en)
        s = s.replace("dd", f"{self.day:02d}")
        s = s.replace("d", str(self.day))
        s = s.replace("SS", self.season_fa)
        if use_persian_digits:
            s = to_persian_digits(s)
        return s

    def __str__(self) -> str:
        return self.format("yyyy/mm/dd")

    def __lt__(self, other: "ShamsiDate") -> bool:
        return (self.year, self.month, self.day) < (other.year, other.month, other.day)

    def __le__(self, other: "ShamsiDate") -> bool:
        return (self.year, self.month, self.day) <= (other.year, other.month, other.day)

    def __gt__(self, other: "ShamsiDate") -> bool:
        return (self.year, self.month, self.day) > (other.year, other.month, other.day)

    def __ge__(self, other: "ShamsiDate") -> bool:
        return (self.year, self.month, self.day) >= (other.year, other.month, other.day)


# ---- Helpers ----

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_persian_digits(s: str) -> str:
    """Replace ASCII digits with Persian digits."""
    return "".join(_PERSIAN_DIGITS[int(c)] if c.isdigit() else c for c in s)


def to_ascii_digits(s: str) -> str:
    """Replace Persian digits with ASCII digits."""
    out = []
    for c in s:
        idx = _PERSIAN_DIGITS.find(c)
        out.append(str(idx) if idx >= 0 else c)
    return "".join(out)


def format_shamsi(dt: Optional[datetime], fmt: str = "yyyy/mm/dd",
                  include_time: bool = False,
                  use_persian_digits: bool = False) -> str:
    """Format a Gregorian datetime as Shamsi."""
    if dt is None:
        return "—"
    s = ShamsiDate.from_datetime(dt).format(fmt, use_persian_digits)
    if include_time:
        time_str = f"{dt.hour:02d}:{dt.minute:02d}"
        if use_persian_digits:
            time_str = to_persian_digits(time_str)
        s += f"  {time_str}"
    return s


def shamsi_month_grid(year: int, month: int) -> list[list[Optional[ShamsiDate]]]:
    """
    Return a 6x7 grid of ShamsiDates for the given month.

    The grid is laid out Saturday..Friday (Iranian week). Cells before
    the 1st of the month or after its last day are None.

    Used by the calendar/planner view.
    """
    first = ShamsiDate(year, month, 1)
    # Python weekday: Mon=0..Sun=6
    # Iranian weekday: Sat=0..Fri=6
    py_wd = first.to_gregorian().weekday()
    iranian_first_wd = (py_wd + 2) % 7

    last_day = days_in_month(year, month)
    grid: list[list[Optional[ShamsiDate]]] = []
    week: list[Optional[ShamsiDate]] = [None] * iranian_first_wd
    for day in range(1, last_day + 1):
        week.append(ShamsiDate(year, month, day))
        if len(week) == 7:
            grid.append(week)
            week = []
    if week:
        while len(week) < 7:
            week.append(None)
        grid.append(week)
    # Pad to 6 weeks for consistent rendering
    while len(grid) < 6:
        grid.append([None] * 7)
    return grid


def iterate_week(start: ShamsiDate) -> list[ShamsiDate]:
    """Return the 7 days of the Iranian week containing `start`."""
    g = start.to_gregorian()
    py_wd = g.weekday()
    iranian_wd = (py_wd + 2) % 7
    saturday = g - timedelta(days=iranian_wd)
    return [ShamsiDate.from_gregorian(saturday + timedelta(days=i)) for i in range(7)]


def parse_shamsi(s: str) -> Optional[ShamsiDate]:
    """Parse a string like '1403/05/14' or '1403-5-14' into a ShamsiDate."""
    s = to_ascii_digits(s).strip()
    parts = s.replace("-", "/").split("/")
    if len(parts) != 3:
        return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return ShamsiDate(y, m, d)
    except (ValueError, IndexError):
        return None
