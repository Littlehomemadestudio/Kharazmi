# نمودار الگوی MVC تقویم RASK! — Calendar MVC Pattern

## توضیحات

زیرسیستم تقویم RASK! بر اساس الگوی **Model-View-Controller (MVC)** طراحی شده است. این الگو جداسازی مسئولیت‌ها را تضمین می‌کند:

- **Model (مدل)**: مدیریت داده‌ها و منطق کسب‌وکار — `CalendarStore` و `CalendarModel`
- **View (نما)**: نمایش اطلاعات به کاربر — نماهای ماه، هفته، روز و سال
- **Controller (کنترل‌کننده)**: هماهنگی بین Model و View — `CalendarController`

ویژگی منحصربه‌فرد این پیاده‌سازی، **پشتیبانی کامل از تقویم شمسی (جلالی)** است. تمام محاسبات تاریخ و ناوبری بر اساس گاه‌شماری هجری خورشیدی انجام می‌شود.

---

## نمودار کلی الگوی MVC

```mermaid
graph TB
    %% کاربر
    User(["👤 کاربر"])

    %% Controller
    subgraph Controller["🎛️ کنترل‌کننده — Controller"]
        CC["CalendarController<br/>───────────────<br/>ناوبری: go_today, go_next, go_prev<br/>نمای переключ: set_view<br/>CRUD: create_event_at, move_event,<br/>resize_event, delete_event<br/>زبان طبیعی: create_event_from_nl<br/>───────────────<br/>Signals:<br/>view_changed · date_changed<br/>events_changed · selection_changed"]
    end

    %% Model
    subgraph Model["📊 مدل — Model"]
        direction TB
        CM["CalendarModel<br/>───────────────<br/>پرس‌وجوی شمسی:<br/>events_on_day, events_in_month,<br/>events_in_week, events_in_shamsi_range<br/>───────────────<br/>چیدمان رویداد:<br/>compute_timed_layout<br/>───────────────<br/>شبکه ماه:<br/>month_grid<br/>───────────────<br/>CRUD:<br/>create_event, update_event,<br/>delete_event, move_event, resize_event"]
        CS["CalendarStore<br/>───────────────<br/>مخزن درون‌حافظه‌ای:<br/>dict calendars, dict events<br/>───────────────<br/>CRUD تقویم:<br/>add_calendar, create_calendar,<br/>update_calendar, delete_calendar<br/>───────────────<br/>CRUD رویداد:<br/>add_event, create_event,<br/>update_event, delete_event<br/>───────────────<br/>پرس‌وجو:<br/>events_in_range, events_on_day,<br/>upcoming_events, search<br/>───────────────<br/>رویدادهای مخزن:<br/>CalendarAdded, EventAdded,<br/>EventUpdated, EventRemoved"]
    end

    %% Views
    subgraph Views["🖼️ نماها — Views"]
        direction TB
        MV["MonthView<br/>نمای ماه شمسی<br/>───────────────<br/>شبکه ۶×۷ روز<br/>شنبه تا جمعه<br/>رویدادهای تمام‌روز و زمان‌دار"]
        WV["WeekView<br/>نمای هفته<br/>───────────────<br/>هفته ایرانی<br/>شنبه تا جمعه<br/>ستون‌های ساعتی"]
        DV["DayView<br/>نمای روز<br/>───────────────<br/>خط زمانی ساعتی<br/>رویدادهای زمان‌دار<br/>چیدمان همپوشانی"]
        YV["YearView<br/>نمای سال<br/>───────────────<br/>۱۲ ماه شمسی<br/>مینی‌تقویم‌ها<br/>تتعاد رویدادها"]
        Sidebar["Sidebar<br/>نوار کناری<br/>───────────────<br/>فهرست تقویم‌ها<br/>مخفی/نمایش تقویم<br/>تعیین رنگ"]
        Timeline["Timeline<br/>خط زمان<br/>───────────────<br/>نوار زمانی بالا<br/>نشانگر تاریخ فعلی"]
    end

    %% Data
    subgraph Data["💾 داده‌ها — Data"]
        Cal["Calendar<br/>────────<br/>id, name, color<br/>description, is_default<br/>visible"]
        Evt["Event<br/>────────<br/>id, calendar_id, title<br/>start, end, all_day<br/>event_type, status<br/>recurrence, attendees<br/>reminders, completed"]
        Recur["RecurrenceRule<br/>────────<br/>frequency, interval<br/>count, until<br/>expand()"]
        Shamsi["ShamsiDate<br/>────────<br/>سال، ماه، روز شمسی<br/>to_gregorian()<br/>add_days(), add_months()<br/>month_name_fa, weekday_fa"]
    end

    %% Persistence
    subgraph Persist["ماندگاری"]
        CalRepo["CalendarRepository<br/>save() / load_latest()"]
        SQLite[("🗄️ SQLite<br/>calendar.sqlite3")]
    end

    %% جریان‌های MVC
    User -->|"تعامل<br/>کلیک، درگ، تایپ"| Controller
    Controller -->|"ناوبری / CRUD"| CM
    CM -->|"خواندن/نوشتن"| CS
    CS -->|"ذخیره اشیاء"| Cal & Evt
    Evt -->|"قوانین تکرار"| Recur
    CM -->|"پرس‌وجوی شمسی"| Shamsi
    Controller -->|"نمایش تغییرات"| Views
    CM -->|"داده‌های رویداد"| Views
    Views -->|"ورودی کاربر<br/>کلیک تاریخ، درگ رویداد"| Controller
    CS -->|"save()"| CalRepo
    CalRepo -->|"SQL"| SQLite
    CalRepo -->|"load_latest()"| CS

    %% سبک‌ها
    style User fill:#2C3E50,stroke:#1A252F,color:#fff
    style Controller fill:#E67E22,stroke:#BA6914,color:#fff
    style Model fill:#E74C3C,stroke:#B03A2E,color:#fff
    style Views fill:#4A90D9,stroke:#2C5F8A,color:#fff
    style Data fill:#E74C3C,stroke:#B03A2E,color:#fff
    style Persist fill:#7F8C8D,stroke:#566573,color:#fff
```

---

## نمودار تعاملات MVC

```mermaid
sequenceDiagram
    actor User as 👤 کاربر
    participant View as 🖼️ CalendarView
    participant Ctrl as 🎛️ CalendarController
    participant Model as 📊 CalendarModel
    participant Store as 📦 CalendarStore
    participant DB as 🗄️ SQLite

    Note over User, DB: سناریو ۱: ناوبری بین ماه‌ها
    User->>View: کلیک دکمه «ماه بعد»
    View->>Ctrl: go_next()
    Ctrl->>Ctrl: _nav_date.add_months(1)
    Ctrl->>View: date_changed.emit()
    View->>Model: events_in_month(year, month)
    Model->>Store: events_in_range(start, end)
    Store-->>Model: list~Event~
    Model-->>View: رویدادهای ماه
    View->>View: بروزرسانی نمایش

    Note over User, DB: سناریو ۲: ایجاد رویداد
    User->>View: کلیک روی روز خالی
    View->>Ctrl: create_event_at(start, end)
    Ctrl->>Model: create_event(cal_id, title, start, end)
    Model->>Store: create_event(cal_id, title, start, end)
    Store->>Store: _emit(EventAdded)
    Store-->>Model: Event
    Model-->>Ctrl: Event
    Ctrl->>View: events_changed.emit()
    View->>View: بروزرسانی نمایش

    Note over User, DB: سناریو ۳: ایجاد رویداد از متن
    User->>View: تایپ «جلسه فردا ساعت ۳»
    View->>Ctrl: create_event_from_nl(text)
    Ctrl->>Ctrl: nl_parse(text)
    Ctrl->>Model: create_event(cal_id, title, start, end)
    Model->>Store: create_event(...)
    Store-->>Model: Event
    Model-->>Ctrl: Event
    Ctrl->>View: events_changed.emit()

    Note over User, DB: سناریو ۴: جابجایی رویداد (Drag & Drop)
    User->>View: درگ رویداد به روز جدید
    View->>Ctrl: move_event(event_id, new_start)
    Ctrl->>Model: move_event(event_id, new_start)
    Model->>Store: get_event(event_id)
    Store-->>Model: Event
    Model->>Model: evt.move_to(new_start)
    Ctrl->>View: events_changed.emit()

    Note over User, DB: سناریو ۵: ذخیره خودکار
    View->>Store: تغییرات رویداد
    Store->>DB: CalendarRepository.save(store, "autosave")
    DB-->>DB: INSERT INTO calendar_snapshots
```

---

## نمودار ساختار داخلی نماها

```mermaid
graph TB
    subgraph CalendarView["CalendarView — نمای اصلی تقویم"]
        direction TB
        Toolbar["Toolbar<br/>دکمه‌های ناوبری<br/>انتخاب نوع نما<br/>دکمه «امروز»"]
        ViewStack["QStackedWidget<br/>تعویض نماها"]
        StatusBar["StatusBar<br/>نمایش تاریخ فعلی<br/>تعداد رویدادها"]
    end

    subgraph MonthViewStruct["MonthView — ساختار داخلی"]
        direction TB
        Header1["Header Row<br/>شنبه · یکشنبه · ... · جمعه"]
        Grid1["6×7 Grid<br/>شبکه روزهای ماه"]
        AllDay1["All-Day Row<br/>رویدادهای تمام‌روز"]
        EventWidgets1["Event Widgets<br/>رویدادهای زمان‌دار"]
    end

    subgraph WeekViewStruct["WeekView — ساختار داخلی"]
        direction TB
        Header2["Header Row<br/>تاریخ هر روز هفته"]
        TimeColumn2["Time Column<br/>ساعت‌های روز"]
        DayColumns2["7 Day Columns<br/>شنبه تا جمعه"]
        EventWidgets2["Event Widgets<br/>رویدادهای زمان‌دار<br/>چیدمان همپوشانی"]
    end

    subgraph DayViewStruct["DayView — ساختار داخلی"]
        direction TB
        Header3["Header<br/>تاریخ و روز هفته"]
        TimeColumn3["Time Column<br/>ساعت‌های ۰۰:۰۰ تا ۲۳:۰۰"]
        AllDay3["All-Day Area<br/>رویدادهای تمام‌روز"]
        DayArea3["Day Area<br/>رویدادهای زمان‌دار"]
        EventWidgets3["Event Widgets<br/>چیدمان دقیق همپوشانی"]
    end

    subgraph YearViewStruct["YearView — ساختار داخلی"]
        direction TB
        Header4["Year Header<br/>تعداد سال"]
        MonthGrids4["12 Mini Calendars<br/>فروردین تا اسفند"]
        EventCounts4["Event Count Badges<br/>تعداد رویداد هر روز"]
    end

    CalendarView --> Toolbar
    CalendarView --> ViewStack
    CalendarView --> StatusBar
    ViewStack --> MonthViewStruct
    ViewStack --> WeekViewStruct
    ViewStack --> DayViewStruct
    ViewStack --> YearViewStruct

    style CalendarView fill:#4A90D9,stroke:#2C5F8A,color:#fff
    style MonthViewStruct fill:#5DADE2,stroke:#2E86C1,color:#fff
    style WeekViewStruct fill:#5DADE2,stroke:#2E86C1,color:#fff
    style DayViewStruct fill:#5DADE2,stroke:#2E86C1,color:#fff
    style YearViewStruct fill:#5DADE2,stroke:#2E86C1,color:#fff
```

---

## نمودار چرخه حیات رویداد تقویم

```mermaid
stateDiagram-v2
    [*] --> Created : کاربر ایجاد می‌کند

    Created --> Confirmed : تأیید خودکار
    Created --> Cancelled : لغو توسط کاربر

    Confirmed --> Updated : ویرایش عنوان/زمان/مکان
    Confirmed --> Rescheduled : جابجایی (Drag & Drop)
    Confirmed --> Resized : تغییر مدت (Resize)
    Confirmed --> Completed : علامت‌گذاری تکمیل
    Confirmed --> Cancelled : لغو

    Rescheduled --> Confirmed : تأیید
    Resized --> Confirmed : تأیید
    Updated --> Confirmed : ادامه

    Completed --> Confirmed : بازگشت از تکمیل
    Cancelled --> [*]

    note right of Created : EventAdded emit می‌شود
    note right of Updated : EventUpdated emit می‌شود
    note right of Completed : event_type = TASK
```

---

## مقایسه نماها

| ویژگی | MonthView | WeekView | DayView | YearView |
|-------|-----------|----------|---------|----------|
| **دوره زمانی** | یک ماه شمسی | هفته ایرانی (شنبه-جمعه) | یک روز | یک سال |
| **رویدادهای تمام‌روز** | ✅ ردیف بالا | ✅ ردیف بالا | ✅ ناحیه جداگانه | ❌ |
| **رویدادهای زمان‌دار** | ✅ فشرده | ✅ چیدمان دقیق | ✅ چیدمان دقیق | ❌ |
| **تشخیص همپوشانی** | محدود | ✅ کامل | ✅ کامل | ❌ |
| **درگ اند دراپ** | ✅ جابجایی | ✅ جابجایی + تغییر مدت | ✅ جابجایی + تغییر مدت | ❌ |
| **نمایش تعداد رویداد** | ✅ | ❌ | ❌ | ✅ نشانگر |
| **ناوبری** | ماه بعد/قبل | هفته بعد/قبل | روز بعد/قبل | سال بعد/قبل |
