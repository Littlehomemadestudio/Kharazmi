<div align="center">


# RASK! راسک — AI-Powered Persian Project Planner

### تقویم شمسی · مدیریت پروژه · برنامه‌ریزی هوش مصنوعی

*Named after **Muhammad ibn Musa al-Khwarizmi** (محمد بن موسی خوارزمی) — the legendary Persian polymath whose name gave us the word "algorithm"*

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/PySide6-6.6+-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![License](https://img.shields.io/badge/License-MIT-D4AF37?style=for-the-badge)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-0A0A0B?style=for-the-badge&logoColor=D4AF37)
[![AI](https://img.shields.io/badge/AI-GLM--4.5--Flash-D4AF37?style=for-the-badge)](https://z.ai)

<br/>

**RASK! (راسک)** is a professional desktop application that unifies a **Persian (Shamsi/Jalali) calendar**, **enterprise-grade project management**, and **AI-powered route planning** into a single, beautifully designed workspace. Built with the luxury Dark + Gold theme and inspired by the golden age of Persian mathematics, RASK! bridges centuries of intellectual tradition with cutting-edge AI technology.

<br/>

<img src="assets/logo.svg" alt="RASK! Logo" width="200" />

<br/><br/>

</div>

---

## Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Screenshots](#-screenshots)
- [Architecture](#-architecture)
- [Installation](#-installation)
- [Usage](#-usage)
- [Keyboard Shortcuts](#-keyboard-shortcuts)
- [AI Features](#-ai-features)
- [Calendar System](#-calendar-system)
- [Project Management](#-project-management)
- [Export Formats](#-export-formats)
- [Configuration](#-configuration)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Contributing](#-contributing)
- [License](#-license)
- [Credits](#-credits)

---

## 🌟 Overview

**RASK!** — pronounced /ræsk/, from the Persian راسک — is a unified planning workspace inspired by **Al-Khwarizmi** (خوارزمی), the 9th-century Persian mathematician, astronomer, and geographer whose works laid the foundations for modern algebra and algorithms. His name is the etymological root of the word *"algorithm"* — and RASK! honors that legacy by bringing algorithmic intelligence to project planning.

### Why RASK!?

| Problem | RASK! Solution |
|---------|---------------|
| Most project tools ignore the Persian calendar | 🗓️ Full Shamsi/Jalali calendar with automatic conversion |
| AI schedulers are opaque black boxes | 🤖 Interactive AI that *asks questions* before planning |
| Enterprise PM tools are bloated and expensive | ⚡ Lightweight desktop app with CPM, PERT, Monte Carlo |
| Calendar + tasks + AI live in separate apps | 🏠 Unified workspace: Calendar · AI Planner · Journal · Tasks |

> *"The word 'algorithm' comes from Al-Khwarizmi — we think it's time project planning lived up to that name."*

---

## ✨ Features

### 📅 Persian (Shamsi/Jalali) Calendar

- **Full Shamsi calendar** with automatic Gregorian ↔ Jalali conversion
- **Iranian national & religious holidays** — automatically marked (تعطیلات رسمی ایران)
- **Multiple views** — Monthly, Yearly, Weekly, Timeline, and Day grid
- **Recurring events** with advanced rules (daily, weekly, monthly, yearly)
- **Natural language event creation** — type *"Meeting with Ali tomorrow at 3pm"* and it just works
- **Shamsi date input** — type `1403/05/14` directly
- **Attendees & reminders** — manage invitees and configurable notifications
- **Google Calendar sync** — integration with your existing calendars

### 🤖 AI-Powered Route Planning

- **Interactive AI scheduling** — not a rigid algorithm; the AI *asks clarifying questions* to understand your goal
- **Complex route graph generation** — multi-branch plans with parallel paths, alternatives, and fallbacks
- **Streaming responses** — watch the AI build your plan in real-time
- **Multi-turn conversation** — refine plans through natural dialogue
- **Route Health Dashboard** — 6-component scoring (probability, alternatives, risk, branching, diversity, dependency)
- **Monte Carlo simulation** — 5,000 iterations with P10/P50/P90/P95 estimates
- **Task decomposition** — break large steps into actionable sub-steps
- **Smart replanning** — automatic adjustment when conditions change
- **Risk analysis** — bottleneck detection and critical path warnings

### 📊 Enterprise Project Management

- **Critical Path Method (CPM)** — identify the longest path through your project
- **PERT Analysis** — optimistic, most-likely, and pessimistic duration estimates
- **Monte Carlo Simulation** — probabilistic risk analysis with histogram visualization
- **Resource leveling** — optimize resource allocation across tasks
- **Dependency types** — FS, FF, SS, SF (the four standard precedence relations)
- **Cycle detection** — prevent circular dependencies
- **Topological sorting** — correct execution order for tasks

### 🎨 Rich Visualization & UI

- **Kanban board** — status columns: Draft → Ready → Active → Done
- **Gantt chart** — time-scaled bar chart with dependency links
- **Node graph view** — interactive network visualization of tasks
- **Timeline view** — chronological task listing
- **Statistics dashboard** — analytics and project metrics
- **Journal system** — save, browse, and revisit AI-generated routes
- **Dark + Gold luxury theme** — a sophisticated visual identity
- **Inspector panel** — contextual property editing
- **Command Palette** — quick-access search for any action
- **Minimap** — birds-eye navigation for large graphs
- **Interactive product tour** — guided walkthrough on first launch
- **Console & log panel** — real-time application logs
- **Glass title bar** — frameless window with custom chrome
- **Particle background** — subtle animated gold particles

### 🔧 Power User Features

- **Undo/Redo** — Command pattern with full operation history
- **Keyboard shortcuts** — efficient navigation and editing
- **CSV/Excel/HTML/Mermaid/JSON export** — share data in any format
- **Dock widget flexibility** — rearrange panels to suit your workflow
- **Auto-save** — 60-second interval with SQLite persistence

---

## 📸 Screenshots

> Screenshots coming soon — the UI is evolving rapidly!

| Calendar View | AI Planner |
|:---:|:---:|
| ![Calendar](assets/logo.png) | *AI route graph with health dashboard* |

| Gantt Chart | Kanban Board |
|:---:|:---:|
| *Time-scaled bar chart with dependencies* | *Status columns: Draft → Ready → Active → Done* |

| Monte Carlo Simulation | Route Health Dashboard |
|:---:|:---:|
| *5,000-iteration histogram with P50/P90/P95* | *6-component circular score + breakdown bars* |

---

## 🏗 Architecture

RASK! follows a **layered domain-driven architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                     UI Layer (PySide6)                  │
│  Views · Widgets · Dialogs · Theme · Icons              │
├─────────────────────────────────────────────────────────┤
│                    Service Layer                         │
│  TaskService · SchedulingService · ExportService · Advisor│
├─────────────────────────────────────────────────────────┤
│                     AI Layer                             │
│  AIService (GLM-4.5-Flash) · JournalStore               │
├─────────────────────────────────────────────────────────┤
│                  Algorithm Layer                         │
│  CPM · PERT · Monte Carlo · Resource Leveling           │
│  Cycle Detection · Topological Sort                     │
├─────────────────────────────────────────────────────────┤
│                  Domain Model (Core)                     │
│  Project · Task · Dependency · Duration · ShamsiDate    │
│  Enums · Value Objects · Domain Events                  │
├─────────────────────────────────────────────────────────┤
│                  Persistence Layer                       │
│  SQLiteRepository · CalendarRepository · Serializers    │
├─────────────────────────────────────────────────────────┤
│                  Calendar System                         │
│  CalendarStore · Event · Recurrence · NaturalLanguage   │
│  PersianHolidays · Attendees · Enums                    │
├─────────────────────────────────────────────────────────┤
│                  Command Layer                           │
│  UndoStack · TaskCommands (Command Pattern)              │
└─────────────────────────────────────────────────────────┘
```

### Dependency Flow

```
UI ──→ Services ──→ Core (Domain Model)
 │         │              │
 │         ├──→ AI         ├──→ Algorithms
 │         └──→ Persistence└──→ Calendar
 │                              │
 └──→ Commands ──→ Core         └──→ NaturalLanguage
```

Key design decisions:
- **Domain events** (`TaskCreated`, `DependencyAdded`, etc.) decouple UI from business logic
- **Command pattern** enables non-destructive editing with full undo/redo
- **Repository pattern** abstracts persistence (currently SQLite, swappable)
- **Streaming AI** uses background threads with callback-based UI updates

---

## 📦 Installation

### Prerequisites

- 🐍 **Python 3.11+** (required for modern type hints and performance)
- 📦 **pip** (Python package manager)
- 🖥 **OS**: Linux, macOS, or Windows

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/Littlehomemadestudio/Kharazmi.git
cd Kharazmi

# 2. Create a virtual environment (recommended)
python -m venv venv

# Activate on Linux/macOS
source venv/bin/activate

# Activate on Windows
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
python -m kharazmi.app
```

### Run Modes

```bash
# Default — loads last project or demo project
python -m kharazmi.app

# Load with demo data
python -m kharazmi.app --demo

# Start with an empty project
python -m kharazmi.app --empty

# Start with a fresh new project
python -m kharazmi.app --new
```

---

## 🚀 Usage

### Quick Start: Create Your First Project

1. **Launch RASK!**
   ```bash
   python -m kharazmi.app
   ```

2. **Create a task** — Click **"New Task"** in the toolbar (or `Ctrl+T`)

3. **Fill in details** — Title, duration, priority, risk level

4. **Add dependencies** — Drag from one node to another to create dependency edges

5. **Visualize** — Switch between **Graph**, **Gantt**, **Kanban**, **Timeline**, or **Statistics** views

### Use the AI Planner

1. Switch to the **AI Planner** tab (`Ctrl+2`)

2. Type your project goal in Persian or English:
   ```
   I want to launch a SaaS startup for online education
   ```

3. The AI will **ask clarifying questions** — answer them to refine the plan

4. Review the generated **route graph** with parallel branches, alternatives, and fallbacks

5. Check the **Route Health Dashboard** for quality scoring

6. Run **Monte Carlo simulation** for probabilistic risk assessment

### Create Calendar Events with Natural Language

1. Switch to the **Calendar** tab (`Ctrl+1`)

2. Type naturally in the input bar:
   ```
   Meeting with Sarah tomorrow at 2pm
   ```
   ```
   جلسه فردا ساعت ۳ تا ۵
   ```
   ```
   Doctor appointment next Friday 3pm for 30 minutes
   ```

3. The event is created automatically with parsed date, time, duration, and attendees!

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+T` | New Task |
| `Ctrl+E` | New Event |
| `Ctrl+S` | Save Project |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+R` | Recalculate CPM |
| `Ctrl+0` | Go to Home |
| `Ctrl+1` | Go to Calendar |
| `Ctrl+2` | Go to AI Planner |
| `Ctrl+3` | Go to Graphs |
| `Ctrl+4` | Go to Simulation |
| `Ctrl+5` | Go to Journal |
| `F11` | Toggle Fullscreen |
| `F1` | Take the Tour |
| `Ctrl+Q` | Quit |
| `Ctrl+K` | Command Palette |

---

## 🤖 AI Features

### How AI Planning Works

RASK!'s AI planner is fundamentally different from algorithmic schedulers. Instead of mechanically applying rules, it **engages in a conversation** with you:

```
You: "I want to build a mobile app for food delivery"

AI: "Great goal! Before I plan the route, a few questions:
     1. What platform? (iOS, Android, or both?)
     2. Do you have a team already or hiring from scratch?
     3. What's your target launch timeline?
     4. Any existing backend infrastructure?"

You: "Both platforms, hiring, 6 months, no existing backend"

AI: [Generates complex route graph with parallel branches,
     alternatives, fallback steps, and time estimates]
```

### Route Graph Structure

AI-generated routes are **not simple linear chains**. They produce rich, interconnected graphs:

- 🟢 **Main branch** — the primary sequence of steps
- 🔵 **Parallel branches** — steps that can run simultaneously
- 🟡 **Alternative steps** — connected with dashed edges (try this OR that)
- 🔴 **Fallback steps** — connected with dotted edges (if the main step fails, do this)
- ⚡ **Merge points** — where branches converge

### Route Health Dashboard

Each generated route is scored on **6 dimensions**:

| Component | What It Measures |
|-----------|-----------------|
| 🎯 Probability | How likely is each step to succeed? |
| 🔄 Alternatives | Are there fallback options for risky steps? |
| ⚠️ Risk | What's the overall risk exposure? |
| 🔀 Branching | Is the plan appropriately parallelized? |
| 🎨 Diversity | Does the plan cover different types of activities? |
| 🔗 Dependency | Are dependencies well-managed? |

### Monte Carlo Simulation

For any project or route, run a **5,000-iteration Monte Carlo simulation**:

- Triangular distribution sampling from PERT estimates (optimistic/most-likely/pessimistic)
- Histogram of completion times
- Percentile estimates: **P10, P50 (median), P90, P95**
- Probability of meeting a target deadline

### Streaming & Multi-Turn

- **Streaming**: AI responses arrive token-by-token, displayed in real-time in the chat panel
- **Multi-turn**: Continue the conversation to refine, adjust, or replan
- **Background threads**: AI calls run off the main thread to keep the UI responsive

---

## 📅 Calendar System

### Shamsi (Jalali) Calendar

RASK! includes a complete, native Persian calendar system — not a wrapper around Gregorian dates.

| Feature | Details |
|---------|---------|
| 🗓️ Jalali dates | Full Shamsi calendar with accurate conversion (1410–1500 SH) |
| 🏷️ Iranian holidays | National and religious holidays auto-populated (تعطیلات رسمی) |
| 📅 Multi-view | Monthly, Yearly, Weekly, Timeline, Day grid |
| 🔄 Recurring events | Daily, weekly, monthly, yearly, weekday-only |
| 👥 Attendees | Manage invitees per event |
| 🔔 Reminders | Configurable notification settings |
| 🌐 Google Calendar | Sync with your existing Google calendars |
| 🎨 Color-coded | Multiple calendars with distinct colors |

### Natural Language Parsing

RASK! parses natural language into structured events — no ML required, just smart regex and keyword matching:

| Input | Parsed Result |
|-------|--------------|
| `Lunch with Sarah tomorrow at 1 PM` | Title: "Lunch with Sarah", Date: +1 day, Time: 13:00, Attendees: [Sarah] |
| `Meeting every Monday at 10am` | Title: "Meeting", Recurrence: weekly (Monday), Time: 10:00 |
| `Doctor appointment next Friday 3pm` | Title: "Doctor appointment", Date: next Friday, Time: 15:00 |
| `Vacation from July 1 to July 14` | Title: "Vacation", All-day event spanning 14 days |
| `1403/05/14 جلسه` | Shamsi date: 1403/05/14, Title: "جلسه" |
| `Call mom today at 6pm for 30 minutes` | Title: "Call mom", Date: today, Time: 18:00, Duration: 30min |

Supported patterns:
- **Time**: `1pm`, `1:30 PM`, `13:00`, `1300`, `noon`, `midnight`, `morning`, `afternoon`, `evening`
- **Date**: `today`, `tomorrow`, `next Monday`, `in 3 days`, `1403/05/14`, `July 14`
- **Duration**: `for 2 hours`, `30 min`, `all day`
- **Recurrence**: `every day`, `weekly`, `every Monday`, `monthly`, `yearly`
- **Event type**: meeting, appointment, birthday, focus time, out of office, task

---

## 📊 Project Management

### Critical Path Method (CPM)

RASK! computes the critical path using forward and backward pass algorithms:

- **Early Start / Early Finish** — earliest possible times
- **Late Start / Late Finish** — latest allowable times
- **Total Slack** — float time for each task
- **Critical tasks** — zero-slack tasks on the longest path

### PERT Analysis

Each task supports **three-point estimation**:

| Estimate | Symbol | Meaning |
|----------|--------|---------|
| Optimistic | O | Best-case scenario |
| Most Likely | M | Most probable duration |
| Pessimistic | P | Worst-case scenario |

Expected duration = `(O + 4M + P) / 6`

### Monte Carlo Simulation

Runs **5,000 iterations** of the project schedule:

1. For each iteration, sample each task's duration from a **triangular distribution** (bounded by PERT estimates)
2. Run CPM on the sampled durations
3. Record the project completion time
4. Build a histogram and compute percentiles

Output includes:
- **Mean** and **median** completion time
- **P10, P50, P90, P95** percentile estimates
- **Probability of meeting target** deadline
- **Histogram** visualization

### Dependency Types

All four standard project management precedence relations:

| Type | Code | Meaning |
|------|------|---------|
| Finish-to-Start | FS | Successor starts after predecessor finishes |
| Finish-to-Finish | FF | Successor finishes after predecessor finishes |
| Start-to-Start | SS | Successor starts after predecessor starts |
| Start-to-Finish | SF | Successor finishes after predecessor starts |

### Task Lifecycle

Tasks follow a constrained state machine — only legal transitions are allowed:

```
DRAFT ──→ READY ──→ ACTIVE ──→ DONE
  │         │    ↘     │
  │         │   BLOCKED─┘
  │         │         │
  └→ CANCELLED ←─── DEFERRED ──→ READY
```

### Resource Leveling

Optimizes resource allocation by rescheduling tasks to eliminate over-allocation while respecting dependencies and constraints.

---

## 📤 Export Formats

RASK! supports multiple export formats for maximum interoperability:

| Format | Extension | Content | Use Case |
|--------|-----------|---------|----------|
| **JSON** | `.json` | Full project (tasks + dependencies + metadata) | Backup, import into RASK! |
| **CSV (Tasks)** | `.csv` | Task list with all fields | Spreadsheet analysis |
| **CSV (Dependencies)** | `.csv` | Dependency list (source → target, type) | Dependency audit |
| **Mermaid** | `.mmd` | Graph diagram in Mermaid syntax | Documentation, wikis |
| **HTML** | `.html` | Rendered Gantt/chart view | Sharing, presentations |
| **Excel** | `.xlsx` | Formatted spreadsheet | Reporting, stakeholder reviews |

---

## ⚙️ Configuration

### AI Settings

AI configuration is stored at `~/.rask/ai_settings.json`:

```json
{
  "api_key": "your-api-key",
  "model": "glm-4.5-flash",
  "base_url": "https://api.z.ai/api/paas/v4/chat/completions",
  "temperature": 0.7,
  "max_tokens": 16384
}
```

Configure via **File → AI Settings...** or edit the file directly.

Available models:
- `glm-4.5-flash` — fast, efficient (default)
- `glm-4.5` — more capable, for complex planning tasks

### Data Storage

| Path | Contents |
|------|----------|
| `~/.rask/` | Application data root |
| `~/.rask/ai_settings.json` | AI configuration |
| `~/.rask/kharazmi.db` | SQLite database (projects, tasks, dependencies) |
| `~/.rask/calendar.db` | Calendar and event data |
| `~/.rask/journal/` | Saved AI route journal entries |

### Color Palette

RASK!'s luxury Dark + Gold theme:

| Color | Hex | Usage |
|-------|-----|-------|
| 🟡 Gold Primary | `#D4AF37` | Primary accent, highlights, branding |
| 🟡 Gold Bright | `#F5D76E` | Hover states, active elements |
| ⚫ Background | `#0A0A0B` | Main background |
| ⚫ Surface | `#1A1A1E` | Cards, panels |
| 🔵 Blue | `#2563EB` | Links, interactive elements |
| 🟢 Green | `#16A34A` | Success states |
| 🔴 Red | `#DC2626` | Errors, warnings, critical path |
| ⚪ Light | `#FAFAFA` | Primary text |

---

## 🛠 Tech Stack

| Technology | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.11+ | Core language |
| **PySide6** | 6.6+ | Qt6 bindings for desktop UI |
| **SQLite** | built-in | Local persistence layer |
| **ZhipuAI GLM API** | v4 | AI-powered planning (GLM-4.5-Flash) |
| **urllib** | stdlib | HTTP client for AI API calls |

No heavy frameworks — just Python, Qt, and SQLite. Fast, self-contained, and portable.

---

## 📁 Project Structure

```
main/kharazmi/
├── 📂 ai/                          # AI service layer
│   ├── ai_service.py               # GLM-4.5-Flash connection with streaming
│   └── journal_store.py            # Route journal persistence
│
├── 📂 algorithms/                   # Project management algorithms
│   ├── critical_path.py            # CPM — Critical Path Method
│   ├── pert.py                     # PERT — Program Evaluation and Review Technique
│   ├── monte_carlo.py              # Monte Carlo risk simulation (5K iterations)
│   ├── resource_leveling.py        # Resource optimization
│   ├── cycle_detection.py          # Circular dependency prevention
│   └── topological_sort.py         # Correct execution ordering
│
├── 📂 calendar/                     # Persian calendar system
│   ├── calendar.py                 # Calendar management
│   ├── event.py                    # Event data model
│   ├── recurrence.py               # Recurrence rule engine
│   ├── natural_language.py         # NL event parser (regex-based)
│   ├── persian_holidays.py         # Iranian holiday database
│   ├── attendees.py                # Attendee management
│   ├── enums.py                    # Calendar enumerations
│   └── store.py                    # Event store with CRUD
│
├── 📂 commands/                     # Command pattern (Undo/Redo)
│   ├── base.py                     # Command interface
│   ├── undo_stack.py               # Undo/Redo stack with event notifications
│   └── task_commands.py            # Task operation commands
│
├── 📂 core/                         # Domain model (business logic)
│   ├── project.py                  # Project entity
│   ├── task.py                     # Task entity with lifecycle
│   ├── dependency.py               # Dependency relationships (FS/FF/SS/SF)
│   ├── enums.py                    # Status, Priority, RiskLevel, etc.
│   ├── value_objects.py            # Duration, PertEstimate, Progress, Slack
│   ├── events.py                   # Domain events (TaskCreated, etc.)
│   └── shamsi.py                   # Shamsi (Jalali) date implementation
│
├── 📂 persistence/                  # Data persistence layer
│   ├── sqlite_store.py             # SQLite repository
│   ├── serializers.py              # JSON/CSV/Mermaid exporters & importers
│   └── calendar_repository.py      # Calendar persistence
│
├── 📂 services/                     # Application services
│   ├── task_service.py             # Task CRUD operations
│   ├── scheduling_service.py       # CPM/PERT scheduling orchestration
│   ├── advisor.py                  # Local project advisor
│   ├── export_service.py           # Export orchestration
│   └── route_export.py             # Route-specific export
│
├── 📂 ui/                           # PySide6 user interface
│   ├── main_window.py              # Unified window (RaskMainWindow)
│   ├── rask_window.py              # Main window with all integrations
│   ├── basic_window.py             # Base window class
│   ├── theme.py                    # Dark+Gold QSS stylesheet & palette
│   ├── icons.py                    # SVG icon provider
│   │
│   ├── 📂 views/                   # Tab views
│   │   ├── ai_planner_view.py     # AI Planner tab
│   │   ├── unified_graph_view.py  # Main task graph
│   │   ├── gantt_view.py          # Gantt chart
│   │   ├── kanban_view.py         # Kanban board
│   │   ├── timeline_view.py       # Timeline listing
│   │   ├── statistics_view.py     # Analytics dashboard
│   │   ├── journal_view.py        # Route journal browser
│   │   ├── simulation_view.py     # Monte Carlo visualization
│   │   ├── dashboard_view.py      # Project dashboard
│   │   ├── graphs_view.py         # Graph view container
│   │   ├── node_graph_view.py     # Task node graph
│   │   └── route_graph_view.py    # AI route graph
│   │
│   ├── 📂 widgets/                 # Reusable UI components
│   │   ├── route_node_item.py     # AI route node (custom QGraphicsItem)
│   │   ├── task_node_item.py      # Task node (interactive)
│   │   ├── route_health_dashboard.py # Route health scoring
│   │   ├── ai_chat_panel.py       # AI chat with streaming
│   │   ├── inspector_panel.py     # Property inspector
│   │   ├── command_palette.py     # Quick-action search (Ctrl+K)
│   │   ├── minimap.py             # Graph minimap overlay
│   │   ├── toolbar.py             # Main toolbar
│   │   ├── status_bar.py          # Status information
│   │   ├── console_panel.py       # Log console
│   │   ├── tour_overlay.py        # Guided product tour
│   │   ├── splash_screen.py       # Loading splash
│   │   ├── glass_title_bar.py     # Frameless window title bar
│   │   ├── particle_background.py # Animated gold particles
│   │   ├── schedule_questions.py  # AI question cards
│   │   ├── multiple_choice_question.py # MC question widget
│   │   ├── step_details_panel.py  # Route step details
│   │   ├── step_details_popup.py  # Step popup overlay
│   │   ├── planner_landing.py     # AI planner welcome screen
│   │   ├── calendar_ai_panel.py   # Calendar AI integration
│   │   ├── edge_item.py           # Dependency edge (graph)
│   │   ├── special_edge_item.py   # Alternative/fallback edge
│   │   ├── route_annotation.py    # Route annotations
│   │   ├── insight_bubble.py      # AI insight tooltips
│   │   ├── credits_panel.py       # Credits display
│   │   ├── feedback_dialog.py     # User feedback dialog
│   │   └── status_bar.py          # Bottom status bar
│   │
│   ├── 📂 calendar/               # Calendar UI components
│   │   ├── calendar_view.py       # Main calendar tab
│   │   ├── month_view.py          # Monthly grid view
│   │   ├── year_view.py           # Annual overview
│   │   ├── week_view.py           # Weekly schedule
│   │   ├── day_view.py            # Daily agenda
│   │   ├── timeline.py            # Timeline view
│   │   ├── sidebar.py             # Calendar sidebar
│   │   ├── event_widget.py        # Event card widget
│   │   ├── event_renderer.py      # Event rendering
│   │   ├── controller.py          # Calendar logic controller
│   │   ├── model.py               # Calendar data model
│   │   ├── selection.py           # Date selection handling
│   │   ├── animation.py           # Transition animations
│   │   └── theme.py               # Calendar-specific styles
│   │
│   └── 📂 dialogs/                # Modal dialogs
│       ├── task_editor_dialog.py  # Task create/edit
│       ├── event_editor_dialog.py # Event create/edit
│       ├── node_edit_dialog.py    # Route node editor
│       ├── new_node_dialog.py     # New node creation
│       ├── ai_settings_dialog.py  # AI configuration
│       ├── ai_schedule_dialog.py  # AI schedule options
│       ├── plan_selection_dialog.py # Route plan picker
│       ├── advisor_dialog.py      # Advisor report
│       ├── project_settings_dialog.py # Project settings
│       └── calendar_settings_dialog.py # Calendar management
│
├── __init__.py                     # Package init
├── __main__.py                     # Entry point (python -m kharazmi)
└── app.py                          # Application bootstrap with splash screen
```

---

## 🤝 Contributing

We welcome contributions to RASK! 🎉

### How to Contribute

1. **Fork** the repository

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Make your changes** and commit with conventional format:
   ```bash
   git commit -m "feat: add amazing feature"
   ```

4. **Push** to your branch:
   ```bash
   git push origin feature/amazing-feature
   ```

5. **Open a Pull Request** on GitHub

### Commit Convention

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation changes |
| `style:` | Visual/formatting changes |
| `refactor:` | Code refactoring |
| `test:` | Adding tests |
| `chore:` | Maintenance tasks |

### Development Guidelines

- Follow the existing layered architecture (UI → Services → Core → Persistence)
- Use domain events for cross-component communication
- Keep algorithms in the `algorithms/` package, not in services or UI
- All task mutations should go through `TaskService` and the Command pattern
- Maintain the Dark + Gold theme consistency

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

## 🏆 Credits

### Littlehomemadestudio

Built with ❤️ by [Littlehomemadestudio](https://github.com/Littlehomemadestudio) for the Persian-speaking community.

### Inspiration

**Muhammad ibn Musa al-Khwarizmi** (محمد بن موسی خوارزمی, c. 780–850 CE) — Persian polymath whose works on algebra and arithmetic introduced the decimal positional number system to the Western world. His name, Latinized as *Algoritmi*, is the origin of the word **algorithm**. His book *Al-Kitāb al-Mukhtaṣar fī Ḥisāb al-Jabr wal-Muqābalah* (الکتاب المختصر فی حساب الجبر والمقابلة) gave us the word **algebra**.

RASK! (راسک) honors his legacy by bringing algorithmic intelligence to project planning — exactly as the name suggests.

---

<div align="center">

<br/>

[![GitHub](https://img.shields.io/badge/GitHub-RASK!-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/Littlehomemadestudio/Kharazmi)

<br/>

*RASK! — A legacy of pure Persian knowledge, from the golden age of mathematics* ✨

*راسک — یادگاری از دانش ناب ایرانیان در عصر طلایی ریاضیات*

</div>
