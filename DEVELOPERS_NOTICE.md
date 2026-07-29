# RASK! Developer's Notice — Complete Code Reference

> **Kharazmi AI Planning System** — Version 3.0  
> A unified planning workspace: Calendar (Shamsi) · AI Planner · Journal · Enterprise Task OS

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Module-by-Module Deep Dive](#2-module-by-module-deep-dive)
   - 2.1 [Core Module](#21-core-module-kharazmicore)
   - 2.2 [Calendar Module](#22-calendar-module-kharazmicalendar)
   - 2.3 [AI Module](#23-ai-module-kharazmiai)
   - 2.4 [Algorithms Module](#24-algorithms-module-kharazmialgorithms)
   - 2.5 [Services Module](#25-services-module-kharazmiservices)
   - 2.6 [Commands Module](#26-commands-module-kharazmicommands)
   - 2.7 [Persistence Module](#27-persistence-module-kharazmipersistence)
   - 2.8 [UI Module](#28-ui-module-kharazmiui)
3. [How-To Guides](#3-how-to-guides)
4. [Common Pitfalls](#4-common-pitfalls)
5. [Signal Map](#5-signal-map)
6. [Data Flow](#6-data-flow)
7. [File Index](#7-file-index)

---

## 1. Architecture Overview

### Domain-Driven Design

RASK! follows a strict **Domain-Driven Design (DDD)** layered architecture:

```
┌─────────────────────────────────────────────────────┐
│  UI Layer (PySide6/Qt)                              │
│  Views · Widgets · Dialogs · Theme · Icons           │
├─────────────────────────────────────────────────────┤
│  Services Layer                                      │
│  TaskService · SchedulingService · Advisor · Export   │
├─────────────────────────────────────────────────────┤
│  Commands Layer (Undo/Redo)                          │
│  Command · UndoStack · Concrete Commands             │
├─────────────────────────────────────────────────────┤
│  Algorithms Layer (Pure Functions)                   │
│  CPM · PERT · Monte Carlo · Topological Sort         │
│  Cycle Detection · Resource Leveling                  │
├─────────────────────────────────────────────────────┤
│  Core Domain Layer (Zero Dependencies)               │
│  Task · Project · Dependency · Enums · Value Objects  │
│  Domain Events · Shamsi Calendar                     │
├─────────────────────────────────────────────────────┤
│  Persistence Layer                                   │
│  SQLiteRepository · CalendarRepository · Serializers  │
└─────────────────────────────────────────────────────┘
```

**Dependency direction is strictly top-down.** Core never imports from any other module. Algorithms import only from Core. Services import from Algorithms, Commands, and Core. UI imports from everything.

### Module Dependency Graph

```
core  →  (no dependencies — pure domain)
  ↑
algorithms  →  core
  ↑
commands  →  core
  ↑
services  →  core, algorithms, commands, persistence, ai
  ↑
persistence  →  core, calendar
  ↑
ai  →  core
  ↑
ui  →  core, calendar, ai, algorithms, services, commands, persistence
```

### Event-Driven Architecture

The `Project` aggregate root emits **domain events** (frozen dataclasses) that the UI subscribes to. This decouples the domain from the presentation:

- `TaskCreated`, `TaskDeleted`, `TaskUpdated`, `TaskStatusChanged`
- `DependencyAdded`, `DependencyRemoved`
- `CycleDetected`, `ProjectReset`, `ProjectLoaded`
- `ScheduleRecalculated`

The `CalendarStore` similarly emits store events:
- `CalendarAdded`, `CalendarRemoved`, `CalendarUpdated`, `CalendarVisibilityChanged`
- `EventAdded`, `EventUpdated`, `EventRemoved`

Listener failures are silently swallowed — a broken UI listener must never corrupt the domain.

### Command Pattern (Undo/Redo)

Every mutating operation on the project goes through the **Command pattern**:

1. A `Command` object captures all data needed for do/undo
2. `Command.execute(project)` applies the change
3. `Command.undo(project)` reverses it
4. `UndoStack` stores commands with a bounded history (default 200)
5. UI triggers `UndoStack.undo(project)` / `UndoStack.redo(project)`

### MVC in Calendar Subsystem

The calendar module uses **Model-View-Controller**:
- **Model**: `CalendarStore` (owns Calendar and Event entities)
- **View**: `CalendarView`, `MonthView`, `WeekView`, `DayView`, `YearView`
- **Controller**: `CalendarController` (handles navigation, event mutations)

### Signal/Slot Connections

Qt signals/slots connect UI components. Key connections:
- `Project._listeners` → UI refresh callbacks (domain events)
- `CalendarStore._listeners` → UI refresh callbacks (calendar events)
- `UndoStack._listeners` → undo/redo button state updates
- Various Qt widget signals (clicked, changed, etc.) → service method calls

---

## 2. Module-by-Module Deep Dive

### 2.1 Core Module (`kharazmi/core/`)

The heart of the system. Zero external dependencies. Pure Python dataclasses and enums.

#### `task.py` — Task Entity

The central domain object. A unit of work in the project graph.

**Class: `Task`** (mutable dataclass)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | `TaskId` | required | Unique identity |
| `title` | `str` | required | Human-readable name |
| `description` | `str` | `""` | Detailed description |
| `duration` | `Duration` | `Duration(60)` | Plain duration in minutes |
| `priority` | `Priority` | `MEDIUM` | Numeric priority 0-4 |
| `status` | `TaskStatus` | `DRAFT` | Lifecycle state (FSM) |
| `risk` | `RiskLevel` | `LOW` | Qualitative risk for Monte Carlo |
| `progress` | `Progress` | `Progress(0)` | Completion 0-100% |
| `tags` | `set[Tag]` | `set()` | Labels for filtering |
| `resources` | `list[ResourceAllocation]` | `[]` | Assigned resources |
| `pert` | `Optional[PertEstimate]` | `None` | Three-point estimate |
| `earliest_start` | `Optional[datetime]` | `None` | External constraint: earliest start |
| `latest_finish` | `Optional[datetime]` | `None` | External constraint: latest finish |
| `x`, `y` | `float` | `0.0` | Node-graph position (UI) |
| `early_start` | `Optional[datetime]` | `None` | **Computed by CPM** |
| `early_finish` | `Optional[datetime]` | `None` | **Computed by CPM** |
| `late_start` | `Optional[datetime]` | `None` | **Computed by CPM** |
| `late_finish` | `Optional[datetime]` | `None` | **Computed by CPM** |
| `slack` | `Optional[Slack]` | `None` | **Computed by CPM** |

**Methods:**

| Method | Signature | Behavior |
|--------|-----------|----------|
| `advance` | `(new_status: TaskStatus) → None` | FSM transition. Raises `ValueError` if illegal. |
| `set_progress` | `(percent: int) → None` | Updates progress. Auto-flips to DONE if 100% and status is ACTIVE/READY. |
| `set_duration` | `(amount: float, unit: DurationUnit) → None` | Replaces duration using the unit converter. |
| `add_tag` | `(tag: Tag) → None` | Adds tag to set. |
| `remove_tag` | `(tag: Tag) → None` | Discards tag from set. |
| `assign_resource` | `(alloc: ResourceAllocation) → None` | Adds/replaces allocation for same resource name. |
| `unassign_resource` | `(resource_name: str) → None` | Removes allocation by resource name. |
| `touch` | `() → None` | Updates `updated_at` to `datetime.utcnow()`. |

**Properties:**

| Property | Type | Behavior |
|----------|------|----------|
| `is_critical` | `bool` | True if `slack.is_critical` (total_slack == 0) |
| `is_terminal` | `bool` | True if status is DONE or CANCELLED |
| `is_active` | `bool` | True if status is ACTIVE |
| `effective_duration` | `Duration` | PERT expected if available, else plain duration |
| `remaining_duration` | `Duration` | `duration * progress.remaining_fraction` |

**Serialization:** `to_dict()` → JSON dict, `from_dict(data)` → Task. Scheduling metadata (early_start, etc.) is serialized but only valid after CPM.

**FSM (Legal Transitions):** See `enums.py` → `LEGAL_TRANSITIONS`. Terminal states: `DONE`, `CANCELLED` (no outgoing transitions).

#### `project.py` — Project Aggregate Root

The graph of Tasks + Dependencies. **The only object that may create/delete tasks and dependencies** — all external code goes through Project's methods.

**Class: `Project`** (mutable dataclass)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `name` | `str` | `"Untitled Project"` | Project name |
| `description` | `str` | `""` | Description |
| `created_at` | `datetime` | `utcnow()` | Creation time |
| `_tasks` | `dict[str, Task]` | `{}` | Internal task storage (O(1) lookup) |
| `_deps` | `dict[tuple, Dependency]` | `{}` | Internal dependency storage |
| `_listeners` | `list[EventListener]` | `[]` | Domain event subscribers |

**Task Lifecycle Methods:**

| Method | Signature | Emits | Behavior |
|--------|-----------|-------|----------|
| `add_task` | `(task: Task) → Task` | `TaskCreated` | Adds task; raises if duplicate ID |
| `create_task` | `(title, **kwargs) → Task` | `TaskCreated` | Convenience: generates fresh TaskId |
| `get_task` | `(task_id) → Optional[Task]` | — | Lookup by TaskId |
| `require_task` | `(task_id) → Task` | — | Lookup; raises KeyError if missing |
| `delete_task` | `(task_id) → None` | `DependencyRemoved` × N, `TaskDeleted` | Deletes task + all referencing deps |
| `update_task` | `(task_id, **changes) → None` | `TaskUpdated` | Patches fields; raises on unknown key |
| `change_status` | `(task_id, new_status) → None` | `TaskStatusChanged` | Uses `Task.advance()` (FSM) |

**Dependency Methods:**

| Method | Signature | Emits | Behavior |
|--------|-----------|-------|----------|
| `add_dependency` | `(dep: Dependency) → Dependency` | `DependencyAdded` or `CycleDetected` | Adds edge; rejects if cycle created |
| `remove_dependency` | `(pred_id, succ_id, dep_type) → None` | `DependencyRemoved` | Removes edge by key |

**Graph Query Methods:**

| Method | Signature | Returns |
|--------|-----------|---------|
| `dependencies_of` | `(task_id) → list[Dependency]` | Edges where task_id is **successor** |
| `dependents_of` | `(task_id) → list[Dependency]` | Edges where task_id is **predecessor** |
| `roots` | `() → list[Task]` | Tasks with no predecessors |
| `leaves` | `() → list[Task]` | Tasks with no successors |
| `tasks` | `() → Iterator[Task]` | All tasks (**method**, not property!) |
| `dependencies` | `() → Iterator[Dependency]` | All dependencies |
| `task_count` | `→ int` | Number of tasks (**property**) |
| `dependency_count` | `→ int` | Number of dependencies (**property**) |

**Cycle Detection:** Uses BFS reachability check (`_can_reach`) before adding a dependency. If a path already exists from successor to predecessor, adding predecessor→successor would close a cycle.

**Serialization:** `to_dict()` → JSON, `from_dict(data)` → Project. During load, events are NOT re-emitted. Malformed tasks/deps are silently skipped. `snapshot()` returns a `copy.deepcopy` for undo/redo.

#### `dependency.py` — Dependency (Edge) Entity

**Class: `Dependency`** (frozen dataclass — immutable)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `predecessor_id` | `TaskId` | required | Source task |
| `successor_id` | `TaskId` | required | Target task |
| `type` | `DependencyType` | `FINISH_START` | FS/FF/SS/SF |
| `lag` | `Duration` | `Duration(0)` | Positive=delay, negative=lead |

**Post-init:** Raises `ValueError` if predecessor == successor (self-dependency).

**Property `key`:** Returns `(predecessor_id.value, successor_id.value, type.value)` — used for dedup and dict key.

#### `enums.py` — All Enumerations

| Enum | Values | Purpose |
|------|--------|---------|
| `TaskStatus` | `DRAFT`, `READY`, `ACTIVE`, `BLOCKED`, `DONE`, `CANCELLED`, `DEFERRED` | Task lifecycle FSM |
| `Priority` | `TRIVIAL=0`, `LOW=1`, `MEDIUM=2`, `HIGH=3`, `CRITICAL=4` | Numeric priority (IntEnum) |
| `DependencyType` | `FINISH_START="FS"`, `FINISH_FINISH="FF"`, `START_START="SS"`, `START_FINISH="SF"` | Precedence relation |
| `RiskLevel` | `NEGLIGIBLE`, `LOW`, `MEDIUM`, `HIGH`, `SEVERE` | Monte Carlo risk |
| `DurationUnit` | `MINUTE`, `HOUR`, `DAY`, `WEEK` | Unit conversion |
| `ViewKind` | `GRAPH`, `GANTT`, `KANBAN`, `TIMELINE`, `STATS` | Workspace views |

**`LEGAL_TRANSITIONS` dict** maps each `TaskStatus` to the `frozenset` of statuses it may transition to. Terminal states (`DONE`, `CANCELLED`) map to empty frozensets.

#### `value_objects.py` — All Value Objects

All are **frozen dataclasses** (immutable, identity-less).

| Class | Key Fields | Validation | Key Methods |
|-------|-----------|------------|-------------|
| `TaskId` | `value: str` | Must match `^[A-Za-z0-9_\-]+$` | `generate(prefix="T")` creates `T` + 8-hex-chars |
| `Duration` | `minutes: int` | Must be ≥ 0 | `of(amount, unit)` factory; `hours`, `days`, `weeks` properties; `humanize()`; `as_timedelta()`; `+`, `-` operators |
| `TimeWindow` | `start: datetime`, `end: datetime` | end ≥ start | `duration`, `overlaps()`, `contains()` |
| `Slack` | `total_slack: Duration`, `free_slack: Duration` | — | `is_critical` (total==0), `is_near_critical` (≤1 day) |
| `PertEstimate` | `optimistic`, `most_likely`, `pessimistic` (all Duration) | Must be ordered o ≤ m ≤ p | `expected` = (o+4m+p)/6; `std_dev` = (p-o)/6; `variance` = std_dev² |
| `Tag` | `name: str` | Must match `^[A-Za-z0-9_\-]+$` | — |
| `Resource` | `name: str`, `capacity_per_day: float` | capacity in (0, 1.0] | — |
| `ResourceAllocation` | `resource: Resource`, `load: float` | load in (0, capacity] | — |
| `Progress` | `percent: int` | Must be 0..100 | `is_complete`, `remaining_fraction` |

**Duration conversion constants:** 1 day = 8 hours, 1 week = 5 days = 40 hours.

#### `events.py` — Domain Events

All events are **frozen dataclasses** inheriting from `DomainEvent`, which provides `occurred_at: datetime`.

| Event | Extra Fields | When Emitted |
|-------|-------------|--------------|
| `TaskCreated` | `task_id`, `title` | `Project.add_task()` |
| `TaskUpdated` | `task_id`, `field`, `old`, `new` | `Project.update_task()` |
| `TaskDeleted` | `task_id` | `Project.delete_task()` |
| `TaskStatusChanged` | `task_id`, `old`, `new` | `Project.change_status()` |
| `DependencyAdded` | `predecessor_id`, `successor_id`, `dep_type` | `Project.add_dependency()` |
| `DependencyRemoved` | `predecessor_id`, `successor_id` | `Project.remove_dependency()` or cascade delete |
| `CycleDetected` | `attempted_edge`, `cycle` | `Project.add_dependency()` rejects cycle |
| `ProjectReset` | — | `Project.clear()` |
| `ProjectLoaded` | `source`, `task_count` | After loading from persistence |
| `ScheduleRecalculated` | `project_duration_minutes`, `critical_path` | After CPM/PERT runs |

#### `shamsi.py` — Persian (Jalali) Calendar

Complete Shamsi calendar implementation with bidirectional Gregorian↔Jalali conversion.

**Algorithm:** Uses the standard widely-cited conversion algorithm accurate for years 979-3000. The Jalali leap-year cycle uses a 33-year pattern with specific break years.

**Class: `ShamsiDate`** (frozen dataclass)

| Field | Type | Validation |
|-------|------|------------|
| `year` | `int` | — |
| `month` | `int` | 1..12 |
| `day` | `int` | 1..days_in_month(year, month) |

**Factory Methods:**
- `from_gregorian(d: date|datetime)` — Convert any Gregorian date
- `today()` — Current Shamsi date
- `from_datetime(dt: datetime)` — Alias for from_gregorian

**Conversion:**
- `to_gregorian()` → `date`
- `to_datetime(hour=0, minute=0)` → `datetime`

**Arithmetic:**
- `add_days(n)` — Add/subtract days (rounds through Gregorian)
- `add_months(n)` — Add months; clamps day to month max
- `add_years(n)` — Add years; clamps day to month max

**Formatting:** `format(fmt="yyyy/mm/dd", use_persian_digits=False)` supports:
- `yyyy`, `yy` — Year
- `MMMM` — Persian month name (فروردین)
- `MMM` — English month name (Farvardin)
- `mm`, `m` — Month number
- `dd`, `d` — Day number
- `EEEE` — Persian weekday (شنبه)
- `EEE` — English short weekday (Sat)
- `SS` — Persian season name

**Properties:** `month_name_fa`, `month_name_en`, `weekday_fa`, `weekday_en`, `weekday_short_en`, `is_friday` (Iranian weekend), `season_index`, `season_fa`, `season_en`

**Helper Functions:**
- `format_shamsi(dt, fmt, include_time, use_persian_digits)` — Format a Gregorian datetime as Shamsi string
- `shamsi_month_grid(year, month)` → 6×7 grid of `Optional[ShamsiDate]` (Saturday..Friday layout)
- `iterate_week(start)` → 7 ShamsiDates of the Iranian week containing `start`
- `parse_shamsi(s)` → `Optional[ShamsiDate]` from "1403/05/14" or "1403-5-14"
- `to_persian_digits(s)` — Replace ASCII digits with ۰۱۲۳۴۵۶۷۸۹
- `to_ascii_digits(s)` — Reverse conversion
- `is_leap(jy)` — Jalali leap year check
- `days_in_month(jy, jm)` — Returns 31 (months 1-6), 30 (months 7-11), 29/30 (month 12)

**Iranian weekday mapping:** Saturday=0, Sunday=1, ..., Friday=6. The conversion from Python's `date.weekday()` (Mon=0) is `(py_wd + 2) % 7`.

---

### 2.2 Calendar Module (`kharazmi/calendar/`)

A complete Google-Calendar-style subsystem with Shamsi dates, multiple calendars, recurring events, and natural-language parsing.

#### `calendar.py` — Calendar Entity

**Class: `Calendar`** (mutable dataclass)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | `str` | auto-generated | Unique ID (`cal-` + 8 hex chars) |
| `name` | `str` | required | Display name |
| `color` | `str` | `"#D4AF37"` | Hex color for events |
| `visible` | `bool` | `True` | Show/hide toggle |
| `description` | `str` | `""` | |
| `is_default` | `bool` | `False` | Cannot be deleted if default |
| `is_readonly` | `bool` | `False` | True for built-in holiday calendar |
| `owner` | `str` | `"me"` | |

Factory: `Calendar.create(name, color, description)` auto-generates ID.

`CALENDAR_COLORS` — 10 preset hex colors for new calendars.

#### `event.py` — Event Entity

**Class: `Event`** (mutable dataclass)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | `str` | auto (`evt-` + 12 hex) | Unique ID |
| `calendar_id` | `str` | required | Owning calendar |
| `title` | `str` | required | |
| `start`, `end` | `datetime` | now / now+1h | Time window |
| `all_day` | `bool` | `False` | |
| `event_type` | `EventType` | `NORMAL` | |
| `availability` | `Availability` | `BUSY` | |
| `status` | `EventStatus` | `CONFIRMED` | |
| `color` | `Optional[str]` | `None` | Override calendar color |
| `recurrence` | `Optional[RecurrenceRule]` | `None` | |
| `attendees` | `list[Attendee]` | `[]` | |
| `reminders` | `list[Reminder]` | `[]` | |
| `completed` | `bool` | `False` | For TASK-type events |
| `meeting_link` | `str` | `""` | Video call URL |

**Key Methods:**
- `set_time(start, end)` — Validates end ≥ start
- `move_to(new_start)` — Preserves duration
- `set_duration(minutes)` — Adjusts end time
- `add_attendee(attendee)` — Replaces by email
- `remove_attendee(email_or_name)`
- `add_reminder(reminder)` — Replaces by minutes_before
- `complete()` — Marks TASK-type as completed
- `overlaps(other_start, other_end)` → `bool`

**Properties:** `duration`, `duration_minutes`, `is_recurring`, `is_task`, `is_all_day`, `is_meeting`, `effective_color(calendar_color)`

#### `recurrence.py` — Recurrence Rules

Simplified RFC 5545 RRULE implementation. Shamsi-aware for monthly/yearly expansion.

**Class: `RecurrenceRule`** (frozen dataclass)

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `freq` | `RecurrenceFrequency` | `WEEKLY` | DAILY/WEEKLY/MONTHLY/YEARLY |
| `interval` | `int` | `1` | Every N periods |
| `count` | `Optional[int]` | `None` | Max occurrences (mutually exclusive with until) |
| `until` | `Optional[datetime]` | `None` | End date |
| `by_day` | `tuple[ByDay, ...]` | `()` | Weekday constraints |
| `by_month_day` | `tuple[int, ...]` | `()` | Day-of-month constraints |

**`ByDay`** — weekday + optional ordinal (e.g., `2MO` = second Monday, `-1FR` = last Friday).

**`expand(start, window_start, window_end)`** → `Iterator[datetime]` — Generates all occurrence datetimes within the window. Monthly/yearly expansion uses **Shamsi calendar arithmetic** so that "every month on the 15th" means the 15th of every Shamsi month.

**`PRESET_RULES`** — Dictionary of common rules: "Every day", "Every weekday", "Every week", etc.

#### `store.py` — CalendarStore

The aggregate root of the calendar subsystem. Owns Calendar and Event objects.

**Class: `CalendarStore`**

- Seeds a default "Personal" calendar on construction.
- All mutations go through this class.
- Thread-unsafe (everything runs on Qt main thread).

**Calendar CRUD:** `add_calendar`, `create_calendar`, `get_calendar`, `require_calendar`, `update_calendar`, `set_calendar_visible`, `delete_calendar` (cascades to events, can't delete default).

**Event CRUD:** `add_event`, `create_event`, `get_event`, `require_event`, `update_event`, `delete_event`.

**Query Methods:**
- `events_in_range(start, end, include_invisible=False)` — **Expands recurring events on-the-fly.** Each occurrence becomes a cloned Event with `recurrence=None`.
- `upcoming_events(days=7)` — Events in next N days, sorted by start.
- `events_on_day(day)` — Events on a specific date.
- `search(query)` — Full-text search on title, description, location, attendees.

**Store Events Emitted:** `CalendarAdded`, `CalendarRemoved`, `CalendarUpdated`, `CalendarVisibilityChanged`, `EventAdded`, `EventUpdated`, `EventRemoved`.

#### `natural_language.py` — NL Event Parser

Regex-based parser for natural-language event descriptions. No ML — just patterns.

**`parse(text, now=None)` → `ParsedEvent`**

Extracts: title, start datetime, duration, all_day flag, recurrence, event_type, attendees, confidence score (0..1).

**Supported patterns:**
- Dates: "today", "tomorrow", "next Monday", "in 3 days", Shamsi dates (1403/05/14), Gregorian month/day ("July 14")
- Times: "1 PM", "13:00", "1300" (military), "noon", "morning" (9am), "afternoon" (2pm), "evening" (6pm)
- Durations: "for 2 hours", "30 min", "all day"
- Recurrence: "every day", "weekly", "every Monday"
- Event types: "meeting" → MEETING, "focus time" → FOCUS_TIME, "birthday" → BIRTHDAY, etc.
- Attendees: "with Sarah", "with Sarah and John"

**Processing order:** Recurrence → Date → Time → Duration → Event type → Attendees → Title (leftover text).

#### `attendees.py` — Reminder and Attendee Value Objects

**`Reminder`** (frozen): `minutes_before: int`, `method: ReminderMethod` (POPUP/EMAIL).  
**`Attendee`** (frozen): `name: str`, `email: str`, `status: AttendeeStatus`, `is_organizer: bool`.

#### `enums.py` — Calendar Enums

| Enum | Values |
|------|--------|
| `EventType` | `NORMAL`, `MEETING`, `APPOINTMENT`, `BIRTHDAY`, `HOLIDAY`, `FOCUS_TIME`, `OUT_OF_OFFICE`, `WORKING_LOCATION`, `TASK`, `REMINDER` |
| `Availability` | `BUSY`, `FREE`, `TENTATIVE`, `WORKING_ELSEWHERE` |
| `RecurrenceFrequency` | `DAILY`, `WEEKLY`, `MONTHLY`, `YEARLY` |
| `ReminderMethod` | `POPUP`, `EMAIL` |
| `AttendeeStatus` | `NEEDS_ACTION`, `ACCEPTED`, `DECLINED`, `TENTATIVE` |
| `EventStatus` | `CONFIRMED`, `TENTATIVE`, `CANCELLED` |
| `CalendarViewKind` | `DAY`, `WEEK`, `MONTH`, `YEAR`, `SCHEDULE`, `CUSTOM` |
| `Weekday` | `SATURDAY=0`, `SUNDAY=1`, ..., `FRIDAY=6` (Iranian week) |

#### `persian_holidays.py` — Built-in Holiday Calendar

Provides `create_holiday_calendar()` and `create_holiday_events()` that return a read-only "Persian Holidays" calendar with yearly recurring events for all Iranian national and religious holidays.

**Fixed holidays:** Nowruz (1/1-4), Republic Day (1/12), Sizdah Bedar (1/13), Khordad 15 (3/14-15), Revolution Day (11/22), Oil Nationalization (12/29).

**Religious holidays:** Marked as approximate (lunar Hijri shifts each year; positions are Shamsi approximations).

---

### 2.3 AI Module (`kharazmi/ai/`)

Connects to z.ai GLM-4.5-flash API for natural-language route planning with streaming.

#### Data Classes

**`RouteStep`** — A single step in an AI-generated route:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `id` | `str` | required | Step identifier |
| `title` | `str` | required | Display name |
| `duration_minutes` | `int` | required | Estimated duration |
| `success_probability` | `float` | required | 0..1 |
| `location` | `str` | required | Physical/contextual location |
| `description` | `str` | required | What this step involves |
| `fallback` | `str` | required | Plan B if step fails |
| `depends_on` | `list[str]` | `[]` | IDs of prerequisite steps |
| `sub_goals` | `list[str]` | `[]` | Sub-objectives |
| `cost_estimate` | `str` | `""` | |
| `risk_level` | `str` | `"low"` | low/medium/high/severe |
| `branch` | `str` | `"main"` | Branch name (main, alt-1, fallback-1) |
| `kind` | `str` | `"action"` | action/decision/milestone/wait/checkpoint/research/review/deliver/collaborate |
| `x_hint`, `y_hint` | `float` | `0.0` | AI-suggested layout position |

**`RouteEdge`** — Connection between steps:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `source_id` | `str` | required | Source step |
| `target_id` | `str` | required | Target step |
| `kind` | `str` | `"primary"` | primary/alternative/fallback/merge |
| `label` | `str` | `""` | Display label |

**`Insight`** — Floating insight box:

| Field | Type | Purpose |
|-------|------|---------|
| `kind` | `str` | improvement/alternative/breakthrough/skip/loop/question/warning |
| `title` | `str` | |
| `body` | `str` | |
| `anchor_step_id` | `Optional[str]` | Attached to which step |
| `x_hint`, `y_hint` | `float` | Position (0..1) |

**`MultipleChoiceQuestion`** — Clarifying question: `question`, `options`, `allow_custom`, `hint`.

**`Route`** — Complete AI-generated route graph:

| Field | Type | Purpose |
|-------|------|---------|
| `goal` | `str` | User's original goal |
| `steps` | `list[RouteStep]` | All steps |
| `edges` | `list[RouteEdge]` | All edges (explicit) |
| `overall_success_probability` | `float` | |
| `total_duration_minutes` | `int` | |
| `improvements` | `list[str]` | |
| `follow_up_questions` | `list[str]` | |
| `summary` | `str` | |
| `insights` | `list[Insight]` | |
| `layout_style` | `str` | AI-chosen layout (organic/spiral/tree/constellation) |

**`JournalEntry`** — Persisted record: `id`, `timestamp`, `user_goal`, `clarifying_questions_asked`, `user_answers`, `route`, `notes`.

**`SimulationResult`** — Monte Carlo simulation of a Route: `n_simulations`, `p50/p75/p90/p99_minutes`, `min/max/mean_minutes`, `failure_rate`, `step_failure_counts`, `completion_time_distribution`, `histogram` property.

**`RouteHealthReport`** — Health assessment: `overall_score` (0-100), `grade` (A+/A/B/C/D/F), `metrics` dict, `bottlenecks`, `orphans`, `recommendations`.

#### `AIService` — API Client

**Threading model:** All API calls run in daemon threads via `_run_async(fn, callback)`. Callback fires with `(success: bool, result_or_error: Any)` on the worker thread — the UI must use `QMetaObject.invokeMethod` or `QTimer.singleShot` to get back to the main thread.

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `generate_clarifying_questions_streaming(goal, on_status, callback, request_id)` | Step 1: Ask clarifying questions as multiple-choice. Fires `on_status` with human-readable messages. |
| `generate_route_streaming(goal, answers, on_status, callback, request_id)` | Step 2: Generate the full Route graph. Streams status, returns Route on completion. |
| `cancel_request(request_id)` | Cancel an in-flight streaming request. |
| `update_settings(**changes)` | Update API key, model, temperature, etc. Persists to disk. |

**Streaming behavior:** Instead of forwarding raw JSON chunks to the UI, the service periodically emits meaningful status phrases like "Building fallback branches…" every ~50 chunks. The full JSON is accumulated and parsed only after the stream completes.

**Error handling:** JSON repair (`_repair_json`) attempts to fix truncated/corrupted responses. Partial extraction (`_extract_partial`) salvages whatever data it can from malformed responses.

#### `MonteCarloSimulator` — Route Simulation

Simulates a Route N times (default 5000). Each iteration:
1. For each step, randomly decide success/failure based on `success_probability`
2. Failed steps with fallbacks use 1.5× duration as penalty
3. Failed steps without fallbacks block dependent steps
4. Compute topological earliest-finish times

Returns `SimulationResult` with percentiles, failure rate, per-step failure counts, and a histogram distribution.

#### `RouteHealthEngine` — Health Scoring

Computes a 0-100 health score for a Route based on:
- Average success probability (up to 40 points)
- Fallback coverage (up to 15 points)
- Risk level distribution (up to 15 points)
- Branch complexity (up to 12 points)
- Step kind variety (up to 10 points)
- Dependency health (up to 10 points)

Identifies bottleneck steps (low probability + high fan-out) and orphan steps (no edges).

#### `journal_store.py` — Journal Persistence

**Class: `JournalStore`** — File-backed store at `~/.rask/journal.json`.

Uses atomic writes (write to `.tmp`, then `replace()`) to prevent corruption. Methods: `add()`, `update_notes()`, `update_route()`, `save()`, `delete()`, `get()`, `all()` (newest first), `search()`.

---

### 2.4 Algorithms Module (`kharazmi/algorithms/`)

Pure functions with no side effects except mutating Task scheduling fields. All take a `Project` as input.

#### `critical_path.py` — CPM (Critical Path Method)

**`run_cpm(project, start_anchor=None)` → `CPMResult`**

Step-by-step algorithm:
1. **Topological sort** — Kahn's algorithm. Raises `CycleError` if graph has cycles.
2. **Reset** — Clear all scheduling fields on every task.
3. **Forward pass** — Walk topological order. For each task, compute `early_start` as the maximum of all predecessor-driven constraints (FS → pred.early_finish + lag; SS → pred.early_start + lag; FF → pred.early_finish + lag - own_duration; SF → pred.early_start + lag - own_duration). Compute `early_finish = early_start + duration`.
4. **Project end** — `max(early_finish)` across all tasks.
5. **Backward pass** — Walk reversed topological order. For each task, compute `late_finish` as the minimum of all successor-driven constraints. Compute `late_start = late_finish - duration`.
6. **Slack** — `total_slack = late_start - early_start`. `free_slack` = how much this task can slip without delaying any successor's `early_start`.
7. **Critical path** — All tasks with `total_slack == 0`.

**Working calendar:** 09:00-17:00 Mon-Fri. `_add_minutes(start, minutes)` correctly rolls across weekends and non-work hours. `_snap_to_work_hours()` snaps forward; `_snap_to_work_hours_backward()` snaps backward.

**⚠️ Important:** The working calendar uses **Western Mon-Fri**, not Iranian Sat-Thu. This is a known simplification.

**`CPMResult`**: `project_start`, `project_end`, `project_duration`, `critical_path: list[TaskId]`, `cycle_error: Optional[CycleError]`.

#### `pert.py` — PERT (Program Evaluation and Review Technique)

**`ensure_pert_estimates(project)`** — For every task lacking a PERT estimate, synthesizes one using ±20% of the plain duration.

**`run_pert(project, start_anchor=None)` → `PERTSummary`**

Runs CPM using `Task.effective_duration` (which returns PERT expected when PERT is set). Sums variance along the critical path. Returns `expected_duration`, `variance`, `std_dev`, `critical_path`.

**`PERTSummary.probability_by(target_minutes)`** — Uses Z-score: `Z = (target - expected) / std_dev`, then `P = Φ(Z)` via `math.erf`.

#### `monte_carlo.py` — Monte Carlo Simulation

**`run_monte_carlo(project, iterations=1000, target_minutes=None, start_anchor=None, seed=None)` → `MonteCarloResult`**

For each iteration:
1. Sample each task's duration from its triangular distribution (PERT optimistic/most-likely/pessimistic)
2. Install degenerate `PertEstimate` (all three = sampled value) so `Task.effective_duration` returns the sample
3. Run CPM
4. Record project duration

**Cleanup:** After all iterations, restores original PERT estimates and re-runs CPM for consistent visible state.

Returns `MonteCarloResult` with mean, median, P10/P50/P90/P95, min/max, histogram (30 buckets), and `probability_within_target`.

#### `resource_leveling.py` — Resource Leveling Heuristic

**`run_resource_leveling(project, start_anchor=None)` → `LevelingResult`**

Greedy priority-rule-based serial schedule generation:
1. Run CPM for initial schedule
2. Build per-day resource load map
3. Find first day with over-allocation
4. Defer the lowest-priority task on that day (set `earliest_start` to next work day)
5. Re-run CPM. Repeat up to 10 passes.

Returns `conflicts_resolved`, `conflicts_remaining`, `shifted_tasks`, `cpm`.

#### `topological_sort.py` — Kahn's Algorithm

**`topological_sort(project)` → `list[TaskId]`**

Standard Kahn's algorithm with sorted queue for determinism. Raises `CycleError` if not all nodes are visited; then falls back to DFS (`_find_cycle`) to produce a helpful cycle path for the error message.

#### `cycle_detection.py` — DFS 3-Color Cycle Detection

**`has_cycle(project)` → `bool`** — Quick boolean check.  
**`find_any_cycle(project)` → `Optional[list[TaskId]]`** — Returns one cycle path, or None if acyclic.

Uses standard 3-color DFS: WHITE (unvisited), GRAY (in progress), BLACK (done). A GRAY→GRAY edge indicates a back edge (cycle).

---

### 2.5 Services Module (`kharazmi/services/`)

Application services that orchestrate domain operations.

#### `TaskService` — Task Operations + Undo Stack

**Constructor:** `TaskService(project, undo_stack, scheduling)`

Every mutating method:
1. Creates a Command object
2. Executes it against the project
3. Pushes it to the UndoStack
4. Optionally recalculates the schedule

| Method | Command Used | Default Recalc |
|--------|-------------|---------------|
| `create_task(title, ...)` | `CreateTaskCommand` | Yes |
| `delete_task(task_id)` | `DeleteTaskCommand` | Yes |
| `update_task(task_id, **changes)` | `UpdateTaskCommand` | Yes |
| `move_task(task_id, x, y)` | `MoveTaskCommand` | No |
| `change_status(task_id, new_status)` | `ChangeStatusCommand` | Yes |
| `add_dependency(...)` | `AddDependencyCommand` | Yes (returns bool: False if cycle) |
| `remove_dependency(...)` | `RemoveDependencyCommand` | Yes |

**Query helpers:** `tasks_sorted_by(key)`, `search(query)`, `statistics()`.

#### `SchedulingService` — CPM/PERT/Monte Carlo Orchestration

**Constructor:** `SchedulingService(project)`

The single entry point for scheduling calculations. UI never calls algorithm modules directly.

| Method | Emits `ScheduleRecalculated`? |
|--------|------|
| `recalculate(start_anchor)` | Yes |
| `run_pert(start_anchor)` | Yes |
| `run_monte_carlo(iterations, ...)` | No (side-effect free; returns result) |
| `level_resources(start_anchor)` | Yes |

Caches `_last_cpm` and `_last_pert` results.

#### `LocalAdvisor` — Rule-Based Recommendations

**`analyze(project)` → `list[Advice]`**

Deterministic, no external dependencies. Four analysis passes:

1. **Breakdown suggestions** — Tasks >5 days with composite verbs (implement, build, design, etc.) should be split.
2. **Dependency inference** — Tasks sharing tags might need a dependency link.
3. **Conflict detection** — Active critical tasks <50% done; BLOCKED tasks.
4. **Priority recommendations** — Critical-path tasks below HIGH priority should be raised.

**`Advice`**: `kind` (breakdown/dependency/conflict/priority), `severity` (info/warning/critical), `title`, `detail`, `related_tasks`.

#### `ExportService` — JSON/CSV/Mermaid Export

Thin wrapper around persistence serializers:

| Method | Format |
|--------|--------|
| `to_json(path)` | Full project as JSON |
| `from_json(path)` | Import project from JSON |
| `to_csv_tasks(path)` | Tasks only as CSV |
| `to_csv_deps(path)` | Dependencies as CSV |
| `to_mermaid(path)` | Mermaid flowchart (critical tasks in hexagonal shape) |

#### `RouteExport` — CSV/Excel/HTML Route Export

| Function | Format |
|----------|--------|
| `export_route_csv(route, path)` | Steps to CSV (UTF-8-BOM) |
| `export_route_xlsx(route, path)` | Multi-sheet Excel (Steps, Edges, Summary) with styled headers and risk-colored cells |
| `export_route_html(route, path)` | Self-contained dark-themed HTML page with RTL support |

---

### 2.6 Commands Module (`kharazmi/commands/`)

#### `base.py` — Command ABC

**`Command`** (abstract dataclass):
- `name: str` — Human-readable name for undo menu
- `description: str` — Optional detail
- `execute(project)` — Apply the command
- `undo(project)` — Reverse it
- `redo(project)` — Re-apply (default: calls `execute()`)

Commands must be **self-contained** — they carry all data for both do and undo. They must NOT hold references to UI widgets.

#### `task_commands.py` — Concrete Commands

| Command | Execute | Undo |
|---------|---------|------|
| `CreateTaskCommand` | Creates Task with generated ID; stores `_created_id` | Deletes task by `_created_id` |
| `DeleteTaskCommand` | Snapshots task dict + deps to `_snapshot`/`_deps` | Restores task + deps directly to internal dicts (bypasses events) |
| `UpdateTaskCommand` | Patches fields; captures old values in `_old_values` | Restores old values |
| `MoveTaskCommand` | Updates x, y; captures old position | Restores old position |
| `ChangeStatusCommand` | Calls `task.advance()`; captures `_old_status` | **Bypasses FSM legality check** — directly sets `task.status = _old_status` |
| `AddDependencyCommand` | Calls `project.add_dependency()`; sets `_executed` flag | Removes dependency if `_executed` |
| `RemoveDependencyCommand` | Removes dep; sets `_existed` flag | Re-adds dependency with original lag |

**⚠️ Critical:** `ChangeStatusCommand.undo()` bypasses the FSM legality check. This is intentional — we know the prior state was legal.

#### `undo_stack.py` — UndoStack

**Class: `UndoStack(limit=200)`**

- `_stack: list[Command]` — All commands
- `_index: int` — Position of next command to execute
- `_listeners: list[Callable]` — Notified on push/undo/redo

| Method | Behavior |
|--------|----------|
| `push(command)` | Appends, truncates any redo history beyond `_index`, trims to `limit` |
| `execute(command, project)` | Execute then push |
| `undo(project)` → `bool` | Decrements `_index`, calls `cmd.undo()` |
| `redo(project)` → `bool` | Calls `cmd.redo()`, increments `_index` |
| `can_undo()` / `can_redo()` | Boolean checks |
| `next_undo_name()` / `next_redo_name()` | For UI display |
| `clear()` | Resets stack and index |
| `subscribe(listener)` | Register for change notifications |

---

### 2.7 Persistence Module (`kharazmi/persistence/`)

#### `sqlite_store.py` — SQLiteRepository

Thread-safe SQLite repository for Project snapshots.

**Schema:**
```sql
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   TEXT NOT NULL,
    saved_at     TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    kind         TEXT NOT NULL,  -- "manual" | "autosave" | "undo"
    FOREIGN KEY(project_id) REFERENCES projects(id)
);
```

**Thread safety:** Uses `threading.RLock()` around all database operations. Single connection with `check_same_thread=False`.

**Key Methods:**
- `upsert_project(project)` → project ID (slug-based)
- `save_snapshot(project, kind="manual")` → snapshot ID
- `load_latest(project_id)` → `Optional[Project]`
- `load_snapshot(snapshot_id)` → `Optional[Project]`
- `list_snapshots(project_id, limit=50)` → `list[SnapshotInfo]`
- `list_projects()` → `list[dict]`
- `delete_project(project_id)` — Cascades to snapshots

**Default DB path:** `~/.rask/kharazmi.sqlite3`

#### `calendar_repository.py` — CalendarRepository

Mirror of SQLiteRepository for the CalendarStore.

**Schema:**
```sql
CREATE TABLE calendar_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_at     TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    kind         TEXT NOT NULL
);
```

**Key Methods:**
- `save(store, kind="manual")` → snapshot ID. Auto-prunes: keeps latest 5 autosaves + all manual saves.
- `load_latest()` → `Optional[CalendarStore]`
- `has_snapshot()` → `bool`

**Default DB path:** `~/.rask/calendar.sqlite3`

#### `serializers.py` — JSON/CSV/Mermaid Serializers

| Function | Input | Output |
|----------|-------|--------|
| `export_to_json(project, path)` | Project | JSON file (indented, UTF-8) |
| `import_from_json(path)` | JSON file | Project |
| `export_to_csv_tasks(project, path)` | Project | CSV with id, title, duration, priority, status, CPM fields |
| `export_to_csv_deps(project, path)` | Project | CSV with predecessor, successor, type, lag |
| `export_to_mermaid(project, path)` | Project | Mermaid `flowchart LR` — critical tasks use `([ ])` shape, normal use `( )` |

---

### 2.8 UI Module (`kharazmi/ui/`)

#### Theme System (`theme.py`)

**Gold-on-Dark design language.** No theme switching — the look IS the product.

**`Palette`** class — Static color constants:
- **Surfaces:** `BG_DEEPEST` (#08080A) → `BG_PRIMARY` (#0A0A0B) → `BG_SECONDARY` (#111114) → `BG_TERTIARY` (#16161A) → `BG_ELEVATED` (#1C1C22) → `BG_HOVER` (#22222A)
- **Gold family:** `GOLD_BRIGHT` (#F5C842), `GOLD_PRIMARY` (#D4AF37), `GOLD_DEEP` (#8C7012), `GOLD_MUTED` (#5C4A0E)
- **Text:** `TEXT_PRIMARY` (#F5F0DC), `TEXT_SECONDARY` (#A8A294), `TEXT_TERTIARY` (#5C5749), `TEXT_ON_GOLD` (#1A1505)
- **Status:** `STATUS_DONE` (#5A8A5A), `STATUS_ACTIVE` (#5A7FA8), `STATUS_BLOCKED` (#A85A5A), etc.
- **Risk:** `RISK_NEGLIGIBLE` through `RISK_SEVERE`

**Helper functions:** `status_color(value)`, `risk_color(value)`, `priority_weight(p)`, `with_alpha(hex_str, alpha)`

**`QSS`** — Complete Qt stylesheet (~520 lines) covering all widget types.

**`build_qpalette()`** — Returns a `QPalette` matching the QSS for native dialogs.

**`default_font()`** — Inter 10pt. **`mono_font()`** — JetBrains Mono → Menlo → Consolas fallback chain.

#### Icon System (`icons.py`)

**All icons are vector (QPainterPath), no image files.** Each function returns a `QIcon` drawn on a 24×24 transparent pixmap with antialiasing.

**Available icons:** plus, minus, trash, play, pause, check, block, link, unlink, undo, redo, graph, gantt, kanban, stats, timeline, console, search, save, open, settings, warning, command.

**Lookup:** `get_icon(name)` → `QIcon`. Returns empty QIcon for unknown names.

#### Main Window Architecture

**Three window classes:**

| Class | Purpose | Views |
|-------|---------|-------|
| `RaskMainWindow` | Unified tabbed interface | Calendar + AI Planner + Journal + Tasks (all views) |
| `BasicMainWindow` | Calendar-only mode | Calendar (Day/Week/Month/Year/Schedule) |
| `MainWindow` | Enterprise task OS | Graph + Gantt + Kanban + Timeline + Statistics |

**`RaskMainWindow`** (in `rask_window.py`) is the primary window with 4 tabs:
1. **Calendar** — Full Google-Calendar-style planner with Shamsi dates
2. **AI Planner** — Type goal → clarifying questions → generated route graph
3. **Journal** — History of all AI-generated routes
4. **Tasks** — Enterprise node-graph task OS

**Layout (Enterprise/MainWindow):**
```
┌────────────────────────────────────────────────────┐
│ MenuBar                                             │
├────────────────────────────────────────────────────┤
│ MainToolbar                                         │
├──────────┬──────────────────────────┬──────────────┤
│ Sidebar  │  Central widget          │  Inspector   │
│ (tree)   │  (current view)          │  Panel       │
│          │  + Console (bottom)      │              │
├──────────┴──────────────────────────┴──────────────┤
│ StatusBar                                           │
└────────────────────────────────────────────────────┘
```

#### Views (`ui/views/`)

| File | View | Purpose |
|------|------|---------|
| `node_graph_view.py` | `NodeGraphView` | Main node-graph with draggable tasks and edges |
| `unified_graph_view.py` | `UnifiedGraphView` | Combined graph (tasks + routes) |
| `gantt_view.py` | `GanttView` | Time-scaled bar chart |
| `kanban_view.py` | `KanbanView` | Status-based columns (Draft/Ready/Active/Done) |
| `timeline_view.py` | `TimelineView` | Chronological list |
| `statistics_view.py` | `StatisticsView` | Analytics dashboard |
| `simulation_view.py` | `SimulationView` | Monte Carlo histogram + PERT chart |
| `dashboard_view.py` | `DashboardView` | Project overview |
| `ai_planner_view.py` | `AIPlannerView` | AI route generation UI |
| `journal_view.py` | `JournalView` | Route history browser |
| `graphs_view.py` | `GraphsView` | CPM/PERT graphs |
| `route_graph_view.py` | `RouteGraphView` | AI route visualization |

#### Calendar UI (`ui/calendar/`)

| File | Class | Purpose |
|------|-------|---------|
| `calendar_view.py` | `CalendarView` | Top-level calendar widget with view switching |
| `month_view.py` | `MonthView` | Month grid (6×7, Saturday..Friday) |
| `week_view.py` | `WeekView` | 7-day time grid |
| `day_view.py` | `DayView` | Single day time grid |
| `year_view.py` | `YearView` | 12-month mini-calendar |
| `timeline.py` | `TimelineWidget` | Hour markers |
| `sidebar.py` | `CalendarSidebar` | Calendar list + mini month picker |
| `model.py` | `CalendarModel` | Qt model for calendar data |
| `controller.py` | `CalendarController` | Navigation + mutation logic |
| `theme.py` | Calendar theme constants | Colors and metrics |
| `event_widget.py` | `EventWidget` | Single event block |
| `event_renderer.py` | `EventRenderer` | Paints events on time grids |
| `animation.py` | Calendar animations | Transitions between views |
| `selection.py` | `SelectionModel` | Selected date/event tracking |

#### Widgets (`ui/widgets/`)

| File | Purpose |
|------|---------|
| `task_node_item.py` | QGraphicsItem for a task node in the graph |
| `edge_item.py` | QGraphicsItem for a dependency arrow |
| `special_edge_item.py` | Alternative/fallback/merge edges for route graphs |
| `route_node_item.py` | QGraphicsItem for a route step |
| `inspector_panel.py` | Right-side task property editor |
| `console_panel.py` | Command-line interface |
| `command_palette.py` | Ctrl+K quick command palette |
| `ai_chat_panel.py` | AI conversation interface |
| `minimap.py` | Mini overview of the graph |
| `toolbar.py` | Main toolbar widget |
| `status_bar.py` | Custom status bar with project info |
| `glass_title_bar.py` | Transparent title bar for frameless windows |
| `particle_background.py` | Animated particle effect |
| `splash_screen.py` | Startup splash with progress |
| `tour_overlay.py` | First-run guided tour |
| `insight_bubble.py` | Floating insight widget for route graphs |
| `route_annotation.py` | Annotation overlay on route graphs |
| `route_health_dashboard.py` | Route health score display |
| `step_details_panel.py` | Route step details sidebar |
| `step_details_popup.py` | Route step details popup |
| `planner_landing.py` | AI planner landing page |
| `schedule_questions.py` | Multiple-choice question widget |
| `multiple_choice_question.py` | Single question widget |
| `feedback_dialog.py` | User feedback dialog |
| `credits_panel.py` | Credits/about panel |
| `calendar_ai_panel.py` | AI-powered calendar suggestions |

#### Dialogs (`ui/dialogs/`)

| File | Purpose |
|------|---------|
| `task_editor_dialog.py` | Create/edit task properties |
| `new_node_dialog.py` | Quick task creation |
| `node_edit_dialog.py` | Edit task node on graph |
| `advisor_dialog.py` | Show advisor recommendations |
| `ai_schedule_dialog.py` | AI route generation dialog |
| `ai_settings_dialog.py` | Configure AI API key/model |
| `event_editor_dialog.py` | Create/edit calendar events |
| `calendar_settings_dialog.py` | Manage calendars |
| `plan_selection_dialog.py` | Choose Basic vs Enterprise |
| `project_settings_dialog.py` | Project name/description |

---

## 3. How-To Guides

### 3.1 How to Add a New View

1. Create `kharazmi/ui/views/my_view.py` with a class inheriting `QWidget`
2. Accept `project`, `task_service`, and `scheduling` in `__init__`
3. Subscribe to `project.subscribe(self._on_domain_event)` for reactive updates
4. Add the view to `ViewKind` enum in `core/enums.py`
5. Add the view creation in `MainWindow._build_central_widget()`
6. Add a toolbar button and menu entry
7. Add an icon in `icons.py` using `QPainterPath`
8. Add the import in `ui/views/__init__.py`

**Template:**
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout

class MyView(QWidget):
    def __init__(self, project, task_service, scheduling, parent=None):
        super().__init__(parent)
        self.project = project
        self.task_service = task_service
        self.scheduling = scheduling
        self.project.subscribe(self._on_domain_event)
        layout = QVBoxLayout(self)
        # ... build your UI

    def _on_domain_event(self, event):
        # Refresh your view based on event type
        pass

    def refresh(self):
        # Full refresh
        pass
```

### 3.2 How to Add a New AI Feature

1. Add the method to `AIService` in `ai/ai_service.py`
2. Use `_run_async(fn, callback)` for threading
3. Define a system prompt that requests strict JSON output
4. Use `_call_api_streaming()` for progress reporting, or `_call_api()` for simple calls
5. Define data classes for the response (with `to_dict`/`from_dict`)
6. Add UI in `ui/views/` or `ui/widgets/`
7. Use `QTimer.singleShot(0, lambda: ...)` to get back to the Qt main thread from callbacks

### 3.3 How to Add a New Algorithm

1. Create `kharazmi/algorithms/my_algorithm.py`
2. Import only from `kharazmi.core` (no UI, no services)
3. Write a pure function: `def run_my_algorithm(project, **kwargs) -> MyResult`
4. Define a `@dataclass MyResult` with `.ok` property and `to_dict()`
5. Export from `algorithms/__init__.py`
6. Add a method in `SchedulingService` that calls your algorithm and emits `ScheduleRecalculated`
7. Add a button in the toolbar and wire it to the service method

### 3.4 How to Add a New Export Format

1. Add a function in `persistence/serializers.py` (for project data) or `services/route_export.py` (for routes)
2. Follow the pattern: accept `(project_or_route, path)`, return `Path`
3. Add a method to `ExportService` that calls your function
4. Add a menu entry in the File menu of the relevant window
5. Export from the `__init__.py`

### 3.5 How to Add a New Calendar Feature

1. Add entity/value-object changes in `calendar/` module (event.py, calendar.py, enums.py)
2. Add CRUD methods to `CalendarStore` — emit the appropriate store event
3. Add a store event dataclass in `store.py` if needed
4. Update `to_dict`/`from_dict` for serialization
5. Add UI in `ui/calendar/` or `ui/dialogs/`
6. Subscribe to `CalendarStore` events for reactive UI updates

### 3.6 How to Debug paintEvent Issues

**Common mistakes and fixes:**

- **Never call `self.update()` inside `paintEvent`** — This causes infinite recursion. Use `self.update()` from outside (e.g., from event handlers or timers).
- **Never create `QGraphicsEffect` inside `paintEvent`** — Effects are parented to widgets; creating them in paint creates orphans and memory leaks.
- **Never create `QPainter` without checking** — Always create QPainter at the top of paintEvent and call `.begin(self)` if not using the `QPainter(widget)` constructor.
- **Use `with_alpha(hex_str, alpha)` instead of `QColor(str, int)`** — `QColor("#D4AF37", 128)` is INVALID. Use `c = QColor("#D4AF37"); c.setAlpha(128)`.
- **Wrap animation access in try/except RuntimeError** — QPropertyAnimation C++ objects may be deleted before Python garbage collection. Always: `try: anim.start() except RuntimeError: pass`.
- **Use `QStyleOptionViewItem` properly** — When custom painting in item delegates, initialize the option with `initStyleOption()`.

### 3.7 How to Work with Shamsi Dates

```python
from kharazmi.core import ShamsiDate, format_shamsi, to_persian_digits

# Create from Gregorian
today = ShamsiDate.today()
from_greg = ShamsiDate.from_gregorian(some_datetime)

# Display
print(today.format("d MMMM yyyy", use_persian_digits=True))
# → ۱۴ مهر ۱۴۰۳

# Format a datetime as Shamsi
formatted = format_shamsi(some_datetime, "yyyy/mm/dd", include_time=True)

# Arithmetic
next_week = today.add_days(7)
next_month = today.add_months(1)

# Parse from string
parsed = ShamsiDate.from_gregorian(date(2024, 10, 5))
# Or: parsed = parse_shamsi("1403/07/14")

# Month grid for calendar UI
grid = shamsi_month_grid(1403, 7)  # 6×7 grid of Optional[ShamsiDate]
```

**Important:** Internal storage and CPM calculations use Gregorian `datetime`. Only the display layer converts to Shamsi via `format_shamsi()`.

### 3.8 How to Add Keyboard Shortcuts

1. In the window's `_build_menu()` method, create a `QAction` with `setShortcut(QKeySequence("Ctrl+K"))`
2. For shortcuts without menu entries, create `QShortcut(QKeySequence("Ctrl+K"), self)` and connect `activated` signal
3. Avoid overriding Qt built-in shortcuts (Ctrl+C, Ctrl+V, etc.) unless intentionally replacing them
4. Document shortcuts in the Help → Keyboard Shortcuts dialog

### 3.9 How to Create New Dialog Boxes

1. Create `kharazmi/ui/dialogs/my_dialog.py`
2. Inherit from `QDialog`
3. Set `self.setStyleSheet(QSS)` in `__init__` if needed
4. Use `QVBoxLayout` or `QFormLayout` as the main layout
5. Add buttons with `QPushButton` — use `setProperty("variant", "primary")` for gold primary buttons
6. Call `self.exec()` to show modally (blocks until closed)
7. Add import in `ui/dialogs/__init__.py`

### 3.10 How to Persist Data Properly

**Project data:**
```python
repository = SQLiteRepository()
repository.save_snapshot(project, kind="manual")  # or "autosave"
loaded = repository.load_latest(project_id)
```

**Calendar data:**
```python
cal_repo = CalendarRepository()
cal_repo.save(calendar_store, kind="manual")
loaded = cal_repo.load_latest()
```

**AI journal:**
```python
journal = JournalStore()
journal.add(goal, qa_pairs, route, notes)
journal.save()  # Explicit save after in-memory modifications
```

**Best practices:**
- Use `kind="autosave"` for timer-triggered saves; `kind="manual"` for user saves
- The CalendarRepository auto-prunes old autosaves (keeps 5)
- JournalStore uses atomic writes (`.tmp` → `replace()`)
- Always wrap persistence calls in try/except — never let save failures crash the UI

---

## 4. Common Pitfalls

### `QColor(str, int)` is INVALID

```python
# WRONG — crashes at runtime
color = QColor("#D4AF37", 128)

# CORRECT
color = QColor("#D4AF37")
color.setAlpha(128)

# OR use the helper
color = with_alpha("#D4AF37", 128)
```

### QPropertyAnimation C++ objects may be deleted

Qt's C++ layer may delete animation objects before Python's garbage collector runs. Always wrap:

```python
try:
    self._animation.start()
except RuntimeError:
    self._animation = None  # Recreate if needed
```

The app's `sys.excepthook` silently swallows `RuntimeError: "already deleted"` errors, but it's better to handle them explicitly.

### Never call `self.update()` inside `paintEvent`

This causes infinite recursion. Call `self.update()` from outside — from event handlers, timers, or signal callbacks.

### Never create `QGraphicsEffect` inside `paintEvent`

Graphics effects are parented to widgets and persist. Creating them in paint produces orphans and memory leaks. Create them in `__init__` or event handlers.

### `Task.tasks()` is a METHOD; `task_count` IS a property

```python
# WRONG
for task in project.tasks:  # This gets the method object, not an iterator!
    ...

# CORRECT
for task in project.tasks():  # Call the method
    ...

# Property vs method
count = project.task_count    # Property — no parentheses
count = project.dependency_count  # Property — no parentheses
```

### Working hours use Western Mon-Fri, not Iranian Sat-Thu

The CPM algorithm's `_snap_to_work_hours()` and `_add_minutes()` use Python's `weekday()` where Mon=0, Fri=4, Sat=5, Sun=6. The weekend is treated as Saturday+Sunday (Western convention), **not** Friday (Iranian convention). This is a known simplification in the scheduling engine.

### Command undo bypasses FSM legality check

`ChangeStatusCommand.undo()` directly sets `task.status = self._old_status` instead of calling `task.advance()`. This is intentional — the prior state was known to be legal, and the FSM might not allow the reverse transition (e.g., DONE → ACTIVE is not in `LEGAL_TRANSITIONS`).

### RTL/LTR control characters in AI responses

The AI sometimes inserts Unicode control characters (U+200E, U+200F, U+202A-202E) in Persian text. `RouteStep.from_dict()` strips these via `_ctrl_pat = re.compile(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069]')`.

### AI responses may contain non-list values for list fields

The AI sometimes returns a plain string instead of a list for `depends_on` or `sub_goals`. `RouteStep.from_dict()` uses `_ensure_list()` to handle this, splitting by comma or wrapping in a list.

---

## 5. Signal Map

### Core Domain Events (Project → UI)

| Event | Emitted By | Consumed By |
|-------|-----------|-------------|
| `TaskCreated` | `Project.add_task()` | MainWindow (sidebar refresh, graph update) |
| `TaskUpdated` | `Project.update_task()` | InspectorPanel (field refresh), graph (node repaint) |
| `TaskDeleted` | `Project.delete_task()` | MainWindow (sidebar, graph, inspector) |
| `TaskStatusChanged` | `Project.change_status()` | KanbanView (column move), graph (color change) |
| `DependencyAdded` | `Project.add_dependency()` | Graph (edge added), schedule recalc |
| `DependencyRemoved` | `Project.remove_dependency()` | Graph (edge removed), schedule recalc |
| `CycleDetected` | `Project.add_dependency()` | MainWindow (status bar warning) |
| `ProjectReset` | `Project.clear()` | All views (full refresh) |
| `ScheduleRecalculated` | `SchedulingService` | StatusBar (duration display), Gantt, Statistics |

### Calendar Store Events (CalendarStore → UI)

| Event | Emitted By | Consumed By |
|-------|-----------|-------------|
| `CalendarAdded` | `CalendarStore.add_calendar()` | Sidebar (calendar list) |
| `CalendarRemoved` | `CalendarStore.delete_calendar()` | Sidebar, view refresh |
| `CalendarUpdated` | `CalendarStore.update_calendar()` | Sidebar (name/color change) |
| `CalendarVisibilityChanged` | `CalendarStore.set_calendar_visible()` | View (show/hide events) |
| `EventAdded` | `CalendarStore.add_event()` | View (render new event) |
| `EventUpdated` | `CalendarStore.update_event()` | View (repaint event) |
| `EventRemoved` | `CalendarStore.delete_event()` | View (remove event) |

### UndoStack Events

| Signal | When | Consumed By |
|--------|------|-------------|
| `_notify()` listeners | After push/undo/redo | Toolbar (enable/disable undo/redo buttons), StatusBar (action name) |

### Qt Widget Signals (Key Connections)

| Widget Signal | Connected To |
|---------------|-------------|
| `QAction.triggered` | Service method calls (create_task, delete_task, etc.) |
| `QShortcut.activated` | Keyboard shortcut handlers |
| `QTimer.timeout` | Autosave (60s), splash screen |
| `QSplitter.splitterMoved` | Layout persistence |
| `QTreeWidget.itemClicked` | Task selection → Inspector update |
| `QGraphicsScene.selectionChanged` | Node selection → Inspector update |

---

## 6. Data Flow

### AI → Route → Journal → Calendar

```
User types goal
    │
    ▼
AIService.generate_clarifying_questions_streaming()
    │  (on_status: "Analysing your goal…")
    ▼
User answers multiple-choice questions
    │
    ▼
AIService.generate_route_streaming()
    │  (on_status: "Building fallback branches…")
    ▼
Route object (steps + edges + insights)
    │
    ├──→ RouteGraphView (visualize as interactive node graph)
    ├──→ JournalStore.add() (persist to ~/.rask/journal.json)
    ├──→ RouteHealthEngine.compute() → RouteHealthReport
    └──→ MonteCarloSimulator(route).run() → SimulationResult
         │
         └──→ Route steps can be exported as CSV/Excel/HTML
```

### Project → Task → Graph → Inspector

```
User creates task via TaskService
    │
    ▼
CreateTaskCommand.execute(project)
    │
    ├──→ Project.add_task(task) → emits TaskCreated
    │
    ▼
UndoStack.push(cmd)
    │
    ▼
SchedulingService.recalculate()
    │
    ├──→ topological_sort(project)
    ├──→ run_cpm(project) → injects early_start, late_start, slack
    └──→ emits ScheduleRecalculated
         │
         ▼
MainWindow._on_domain_event(event)
    │
    ├──→ Sidebar tree: add task node
    ├──→ NodeGraphView: add TaskNodeItem
    ├──→ InspectorPanel: show task fields
    └──→ StatusBar: update project duration + critical path count
```

### CalendarStore → View → Dialog → Persistence

```
CalendarStore (in-memory)
    │
    ├──→ CalendarView subscribes to store events
    │       │
    │       ├──→ MonthView / WeekView / DayView renders events
    │       └──→ EventWidget paints individual events
    │
    ├──→ EventEditorDialog creates/edits events
    │       └──→ CalendarStore.add_event() / update_event()
    │
    ├──→ CalendarRepository.save(store) → SQLite
    │       └──→ Auto-prunes old autosaves
    │
    └──→ QTimer(60s) → autosave
```

---

## 7. File Index

Every file in the project with its purpose (one line each).

### Root
| File | Purpose |
|------|---------|
| `README.md` | Project overview and documentation |
| `requirements.txt` | Python package dependencies |

### `main/`
| File | Purpose |
|------|---------|
| `main/main.py` | Legacy entry point (delegates to kharazmi.app) |

### `main/kharazmi/`
| File | Purpose |
|------|---------|
| `__init__.py` | Package marker |
| `__main__.py` | Entry point for `python -m kharazmi` |
| `app.py` | Application bootstrap: splash screen, DB init, window creation |

### `main/kharazmi/core/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports all core domain types |
| `task.py` | Task entity with FSM, progress, resources, PERT estimates |
| `project.py` | Project aggregate root: task/dependency CRUD, event emission, cycle detection |
| `dependency.py` | Dependency (edge) entity: FS/FF/SS/SF + lag |
| `enums.py` | All enumerations: TaskStatus, Priority, DependencyType, RiskLevel, DurationUnit, ViewKind, LEGAL_TRANSITIONS |
| `value_objects.py` | Immutable value objects: TaskId, Duration, TimeWindow, Slack, PertEstimate, Tag, Resource, ResourceAllocation, Progress |
| `events.py` | Domain events: TaskCreated/Updated/Deleted, DependencyAdded/Removed, CycleDetected, ScheduleRecalculated, etc. |
| `shamsi.py` | Complete Persian Shamsi calendar: bidirectional conversion, formatting, month grids, leap year calculation |

### `main/kharazmi/calendar/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports calendar types |
| `calendar.py` | Calendar entity: named, colored, visible, readonly |
| `event.py` | Event entity: time, recurrence, attendees, reminders, meeting links |
| `store.py` | CalendarStore: aggregate root for calendars + events, CRUD, queries, recurring event expansion |
| `recurrence.py` | RecurrenceRule: simplified RRULE with Shamsi-aware expansion |
| `natural_language.py` | NL event parser: regex-based extraction of dates, times, durations, recurrence from free text |
| `enums.py` | Calendar enums: EventType, Availability, RecurrenceFrequency, Weekday, etc. |
| `attendees.py` | Reminder and Attendee value objects |
| `persian_holidays.py` | Built-in Persian holidays calendar (fixed + approximate religious) |

### `main/kharazmi/ai/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports AI types and services |
| `ai_service.py` | AIService: GLM-4.5 API client, streaming, route generation, clarifying questions, MonteCarloSimulator, RouteHealthEngine |
| `journal_store.py` | JournalStore: file-backed persistence of AI-generated routes |

### `main/kharazmi/algorithms/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports all algorithms |
| `critical_path.py` | CPM: forward/backward pass with working-hour calendar |
| `pert.py` | PERT: three-point estimation, variance aggregation, Z-score probability |
| `monte_carlo.py` | Monte Carlo: triangular sampling, percentile estimates, histogram |
| `resource_leveling.py` | Greedy resource leveling: priority-based conflict resolution |
| `topological_sort.py` | Kahn's algorithm with deterministic ordering and cycle error reporting |
| `cycle_detection.py` | DFS 3-color cycle detection and cycle path finding |

### `main/kharazmi/services/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports all services |
| `task_service.py` | TaskService: command-based task operations with auto-recalculation |
| `scheduling_service.py` | SchedulingService: CPM/PERT/Monte Carlo/leveling orchestration with event emission |
| `advisor.py` | LocalAdvisor: deterministic rule-based project analysis (breakdowns, dependencies, conflicts, priorities) |
| `export_service.py` | ExportService: JSON/CSV/Mermaid project export wrapper |
| `route_export.py` | Route export: CSV, Excel (openpyxl), HTML (dark-themed, RTL) |

### `main/kharazmi/commands/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports Command, all concrete commands, UndoStack |
| `base.py` | Command ABC: execute/undo/redo interface |
| `task_commands.py` | Concrete commands: Create/Delete/Update/Move/ChangeStatus task, Add/Remove dependency |
| `undo_stack.py` | UndoStack: bounded command history with undo/redo and listener notifications |

### `main/kharazmi/persistence/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports repository and serializer types |
| `sqlite_store.py` | SQLiteRepository: thread-safe project snapshot storage |
| `calendar_repository.py` | CalendarRepository: SQLite-backed calendar store with auto-pruning |
| `serializers.py` | JSON/CSV/Mermaid serialization functions |

### `main/kharazmi/ui/`
| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports main window classes |
| `theme.py` | Palette, QSS stylesheet, QPalette builder, font factories, color helpers |
| `icons.py` | Vector icon factory: all icons drawn with QPainterPath |
| `main_window.py` | MainWindow: Enterprise task OS with graph/gantt/kanban/timeline/stats views |
| `rask_window.py` | RaskMainWindow: unified tabbed interface (Calendar + AI + Journal + Tasks) |
| `basic_window.py` | BasicMainWindow: calendar-only mode |

### `main/kharazmi/ui/views/`
| File | Purpose |
|------|---------|
| `__init__.py` | View exports |
| `node_graph_view.py` | Node graph: draggable task nodes with dependency edges |
| `unified_graph_view.py` | Unified graph: combined task + route visualization |
| `route_graph_view.py` | Route graph: AI route with alternative/fallback edges |
| `gantt_view.py` | Gantt chart: time-scaled horizontal bars |
| `kanban_view.py` | Kanban board: status-based columns |
| `timeline_view.py` | Timeline: chronological task list |
| `statistics_view.py` | Statistics dashboard: charts and metrics |
| `simulation_view.py` | Monte Carlo simulation: histogram + PERT chart |
| `dashboard_view.py` | Project dashboard: overview cards |
| `ai_planner_view.py` | AI planner: goal input → route generation |
| `journal_view.py` | Journal: route history browser |
| `graphs_view.py` | CPM/PERT graph visualization |

### `main/kharazmi/ui/calendar/`
| File | Purpose |
|------|---------|
| `__init__.py` | Calendar UI exports |
| `calendar_view.py` | Top-level calendar widget with view switching |
| `month_view.py` | Month grid view (6×7, Sat..Fri) |
| `week_view.py` | 7-day time grid view |
| `day_view.py` | Single-day time grid view |
| `year_view.py` | 12-month mini-calendar view |
| `timeline.py` | Hour-of-day timeline markers |
| `sidebar.py` | Calendar list + date picker sidebar |
| `model.py` | Qt model for calendar data |
| `controller.py` | Navigation + event mutation controller |
| `theme.py` | Calendar-specific theme constants |
| `event_widget.py` | Single event rendering widget |
| `event_renderer.py` | Event painting on time grids |
| `animation.py` | View transition animations |
| `selection.py` | Date/event selection model |

### `main/kharazmi/ui/widgets/`
| File | Purpose |
|------|---------|
| `__init__.py` | Widget exports |
| `task_node_item.py` | QGraphicsItem for task nodes |
| `edge_item.py` | QGraphicsItem for dependency arrows |
| `special_edge_item.py` | QGraphicsItem for alternative/fallback/merge edges |
| `route_node_item.py` | QGraphicsItem for route step nodes |
| `inspector_panel.py` | Right-side task property editor |
| `console_panel.py` | Command-line interface panel |
| `command_palette.py` | Ctrl+K quick command palette |
| `ai_chat_panel.py` | AI conversation interface |
| `minimap.py` | Mini graph overview |
| `toolbar.py` | Main toolbar |
| `status_bar.py` | Custom status bar |
| `glass_title_bar.py` | Transparent frameless title bar |
| `particle_background.py` | Animated particle background effect |
| `splash_screen.py` | Startup splash screen with progress |
| `tour_overlay.py` | First-run guided tour |
| `insight_bubble.py` | Floating insight widget for routes |
| `route_annotation.py` | Route annotation overlay |
| `route_health_dashboard.py` | Route health score display |
| `step_details_panel.py` | Route step details sidebar |
| `step_details_popup.py` | Route step details popup |
| `planner_landing.py` | AI planner landing page |
| `schedule_questions.py` | Multiple-choice question container |
| `multiple_choice_question.py` | Single MC question widget |
| `feedback_dialog.py` | User feedback dialog |
| `credits_panel.py` | Credits/about panel |
| `calendar_ai_panel.py` | AI-powered calendar suggestions |

### `main/kharazmi/ui/dialogs/`
| File | Purpose |
|------|---------|
| `__init__.py` | Dialog exports |
| `task_editor_dialog.py` | Create/edit task properties |
| `new_node_dialog.py` | Quick task creation |
| `node_edit_dialog.py` | Edit task node on graph |
| `advisor_dialog.py` | Show advisor recommendations |
| `ai_schedule_dialog.py` | AI route generation dialog |
| `ai_settings_dialog.py` | Configure AI API key/model |
| `event_editor_dialog.py` | Create/edit calendar events |
| `calendar_settings_dialog.py` | Manage calendars |
| `plan_selection_dialog.py` | Choose Basic vs Enterprise |
| `project_settings_dialog.py` | Project name/description |

### `assets/`
| File | Purpose |
|------|---------|
| `logo.svg` | Vector logo |
| `logo.png` | Raster logo |
| `banner.png` | Project banner image |
