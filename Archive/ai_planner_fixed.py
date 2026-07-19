#!/usr/bin/env python3

import customtkinter as ctk  # type: ignore
from datetime import datetime, timedelta # type: ignore
from typing import Callable, Optional, List, Dict, Any
import calendar # type: ignore
import threading # type: ignore
import json # type: ignore  
import re # type: ignore
import os # type: ignore
from pathlib import Path # type: ignore
from gpt4all import GPT4All  # pip install gpt4all # type: ignore
import requests
import queue
import subprocess
import time
import sys   

# --- LANGUAGE SUPPORT ---
TRANSLATIONS = {
    "en": {
        "app_title": "Planner - Premium Task Management with AI",
        "tagline": "Organize your day with elegance",
        "tasks": "Tasks",
        "add_task": "＋ Add Task",
        "edit": "✎ Edit",
        "delete": "🗑 Delete",
        "ai_assistant": "🤖 AI Assistant",
        "settings": "⚙️ Settings",
        "month": "Month",
        "week": "Week", 
        "day": "Day",
        "theme": "Theme",
        "new_conversation": "🔄 New Conversation",
        "close": "✕",
        "send": "➤",
        "connecting": "🔄 Connecting to AI model...",
        "ensure_ollama": "⏳ Please ensure Ollama is running on localhost:11434",
        "welcome": "👋 Hello! I'm here to help you plan tasks or just have a conversation. What would you like to do?",
        "thinking": "💭 Thinking...",
        "task_count": "0",
        "no_tasks": "No tasks for this day"
    },
    "fa": {
        "app_title": "برنامه ريز - مديريت وظايف Premium با هوش مصنوعي",
        "tagline": "روز خود را با زيبائي سازماندهي کنيد",
        "tasks": "وظايف",
        "add_task": "＋ افزودن وظيفه",
        "edit": "✎ ويرايش",
        "delete": "🗑 حذف",
        "ai_assistant": "🤖 دستيار هوش مصنوعي",
        "settings": "⚙️ تنظيمات",
        "month": "ماه",
        "week": "هفته",
        "day": "روز", 
        "theme": "پوسته",
        "new_conversation": "🔄 گفتگوي جديد",
        "close": "✕",
        "send": "➤ ارسال",
        "connecting": "🔄 در حال اتصال به مدل هوش مصنوعي...",
        "ensure_ollama": "⏳ لطفا مطمئن شويد Ollama روي localhost:11434 در حال اجراست",
        "welcome": "👋 سلام! من اينجا هستم تا به شما در برنامه ريزي وظايف يا فقط گفتگو کمک کنم. دوست داريد چه کاري انجام دهيد؟",
        "thinking": "💭 در حال فکر کردن...",
        "task_count": "۰",
        "no_tasks": "وظيفه اي براي امروز وجود ندارد"
    }
}

# --- THEME DEFINITIONS --- 
THEMES = {
    "Midnight Dev": {  # GitHub Dark inspired
        'mode': 'Dark',
        'bg_primary': '#0D1117',
        'bg_secondary': '#161B22',
        'bg_hover': '#21262D',
        'accent_primary': '#58A6FF',
        'accent_secondary': '#8957E5',
        'accent_tertiary': '#FF7B72',
        'text_primary': '#C9D1D9',
        'text_secondary': '#8B949E',
        'text_tertiary': '#484F58',
        'border': '#30363D',
        'success': '#3FB950',
        'warning': '#D29922',
        'error': '#F85149',
        'today': '#22272E',
        'selected': '#1F6FEB',
        'task_dot': '#8957E5',
        'transparent': '#0D1117',
    }
}

class PlannerUI:
    """
    Premium Planner Application UI with AI Assistant
    """
    
    def __init__(
        self,
        root: ctk.CTk,
        on_day_select: Optional[Callable] = None,
        on_add_task: Optional[Callable] = None,
        on_edit_task: Optional[Callable] = None,
        on_delete_task: Optional[Callable] = None,
        on_ai_schedule: Optional[Callable] = None,
        on_task_toggle: Optional[Callable] = None
    ):
        self.root = root
        
        # Callbacks
        self.on_day_select = on_day_select or (lambda date: None)
        self.on_add_task = on_add_task or (lambda: None)
        self.on_edit_task = on_edit_task or (lambda task: None)
        self.on_delete_task = on_delete_task or (lambda task: None)
        self.on_ai_schedule = on_ai_schedule or (lambda: None)
        self.on_task_toggle = on_task_toggle or (lambda task: None)
        
        # State
        self.current_date = datetime.now().replace(day=1)
        self.selected_date = datetime.now()
        self.tasks_by_date: Dict[str, List[Dict]] = {}
        self.day_buttons = {}
        self.task_cards = []
        self.selected_task = None
        self.main_container = None 
        
        # View State
        self.current_view = "Month"
        self.view_container = None 
        self.week_header_frame = None
        self.week_time_grid = None
        self.day_header_frame = None
        self.day_time_grid = None
        self.cal_grid_container = None
        self.view_buttons = {}
        
        # Settings State
        self.settings_panel = None
        self.settings_panel_visible = False
        self.settings = {
            'notifications_enabled': True,
            'notification_sound': True,
            'auto_save': True,
            'save_interval': 30,
            'startup_view': 'Month',
            'default_duration': '1 hour',
            'reminder_before': 15,
            'theme': 'Midnight Dev',
            'compact_mode': False,
            'show_completed_tasks': True,
            'language': 'en'
        }
        
        # Language support
        self.current_language = self.settings.get('language', 'en')
        self.rtl_mode = self.current_language == 'fa'
        
        # Save/Load paths
        self.data_dir = Path.home() / '.planner_app'
        self.data_dir.mkdir(exist_ok=True)
        self.tasks_file = self.data_dir / 'tasks.json'
        self.settings_file = self.data_dir / 'settings.json'
        
        # Load saved data first (before applying theme)
        self._load_settings()
        self._load_tasks()
        
        # Initialize Theme (use saved theme if available)
        self.current_theme_key = self.settings.get('theme', "Midnight Dev")
        if self.current_theme_key not in THEMES:
            self.current_theme_key = "Midnight Dev"
        self.colors = THEMES[self.current_theme_key]
        
        # Apply startup view
        if 'startup_view' in self.settings:
            self.current_view = self.settings['startup_view']
        
        # Configure CustomTkinter default
        ctk.set_default_color_theme("blue")
        self._apply_theme_settings()
        
        # Setup UI
        self._setup_window()
        self._create_layout()
        
        # Start auto-save
        if self.settings.get('auto_save', True):
            interval = self.settings.get('save_interval', 30) * 1000
            self.root.after(interval, self._auto_save_tasks)
    
    def t(self, key: str) -> str:
        """Translation helper method"""
        return TRANSLATIONS.get(self.current_language, {}).get(key, key)
    
    def switch_language(self, language: str):
        """Switch application language and rebuild UI"""
        if language in TRANSLATIONS:
            self.current_language = language
            self.rtl_mode = (language == 'fa')
            self.settings['language'] = language
            self._save_settings()
            
            # Rebuild UI with new language
            if self.main_container:
                self.main_container.destroy()
            
            self.day_buttons = {}
            self.task_cards = []
            self.selected_task = None
            
            self._create_layout()
            self._change_view(self.current_view)
            self._update_header()
            self._refresh_tasks()
    
    def _apply_theme_settings(self):
        """Apply the global appearance mode based on current theme"""
        ctk.set_appearance_mode(self.colors['mode'])
        if self.main_container:
            self.main_container.configure(fg_color=self.colors['bg_primary'])
        self.root.configure(fg_color=self.colors['bg_primary'])

    def _setup_window(self):
        """Configure main window properties"""
        self.root.title(self.t("app_title"))
        self.root.geometry("1400x900")
        self.root.configure(fg_color=self.colors['bg_primary'])
        
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_layout(self):
        """Create the main application layout"""
        self.main_container = ctk.CTkFrame(
            self.root,
            fg_color=self.colors['bg_primary'],
            corner_radius=0
        )
        self.main_container.pack(fill='both', expand=True, padx=30, pady=30)
        
        self._create_header(self.main_container)
        
        content_frame = ctk.CTkFrame(
            self.main_container,
            fg_color='transparent'
        )
        content_frame.pack(fill='both', expand=True, pady=(20, 0))
        
        self.view_container = ctk.CTkFrame(
            content_frame,
            fg_color=self.colors['bg_secondary'],
            corner_radius=20,
            border_width=1,
            border_color=self.colors['border']
        )
        self.view_container.pack(side='left', fill='both', expand=True, padx=(0, 15))
        
        self._create_tasks_panel(content_frame)
        
        self._create_action_bar(self.main_container)
        
        self._change_view(self.current_view)
    
    def _create_header(self, parent):
        """Create elegant header with date display"""
        header_frame = ctk.CTkFrame(parent, fg_color='transparent', height=80)
        header_frame.pack(fill='x', pady=(0, 10))
        header_frame.pack_propagate(False)
        
        date_str = self.selected_date.strftime("%A, %B %d, %Y")
        self.header_label = ctk.CTkLabel(
            header_frame, text=date_str,
            font=ctk.CTkFont(family="SF Pro Display", size=36, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        )
        self.header_label.pack(side='left', fill='x', expand=True)
        
        tagline = ctk.CTkLabel(
            header_frame, text=self.t("tagline"),
            font=ctk.CTkFont(family="SF Pro Text", size=14),
            text_color=self.colors['text_tertiary'], anchor='w'
        )
        tagline.pack(side='left', padx=(20, 0))
    
    def _create_tasks_panel(self, parent):
        """Create elegant tasks panel"""
        tasks_container = ctk.CTkFrame(
            parent, fg_color=self.colors['bg_secondary'], corner_radius=20,
            border_width=1, border_color=self.colors['border'], width=500
        )
        tasks_container.pack(side='right', fill='both', expand=True)
        tasks_container.pack_propagate(False)
        
        tasks_header = ctk.CTkFrame(tasks_container, fg_color='transparent', height=70)
        tasks_header.pack(fill='x', padx=25, pady=(25, 15))
        tasks_header.pack_propagate(False)
        
        tasks_title = ctk.CTkLabel(
            tasks_header, text=self.t("tasks"),
            font=ctk.CTkFont(family="SF Pro Display", size=22, weight="bold"),
            text_color=self.colors['text_primary'], anchor='w'
        )
        tasks_title.pack(side='left', fill='x', expand=True)
        
        self.task_count_label = ctk.CTkLabel(
            tasks_header, text=self.t("task_count"),
            font=ctk.CTkFont(family="SF Pro Text", size=14, weight="bold"),
            text_color='#FFFFFF', fg_color=self.colors['accent_primary'],
            corner_radius=12, width=50, height=30
        )
        self.task_count_label.pack(side='right')
        
        self.tasks_scroll = ctk.CTkScrollableFrame(
            tasks_container, fg_color='transparent',
            scrollbar_button_color=self.colors['border'],
            scrollbar_button_hover_color=self.colors['text_tertiary']
        )
        self.tasks_scroll.pack(fill='both', expand=True, padx=25, pady=(0, 25))
    
    def _create_action_bar(self, parent):
        """Create bottom action bar with premium buttons and AI assistant"""
        action_frame = ctk.CTkFrame(parent, fg_color='transparent', height=70)
        action_frame.pack(fill='x', pady=(20, 0))
        action_frame.pack_propagate(False)
        
        left_buttons = ctk.CTkFrame(action_frame, fg_color='transparent')
        left_buttons.pack(side='left', fill='y')
        
        add_btn = ctk.CTkButton(left_buttons, text=self.t("add_task"), command=self.on_add_task)
        add_btn.pack(side='left', padx=(0, 10))
        
        self.edit_btn = ctk.CTkButton(left_buttons, text=self.t("edit"), command=self._handle_edit_task)
        self.edit_btn.pack(side='left', padx=(0, 10))
        self.edit_btn.configure(state='disabled')
        
        self.delete_btn = ctk.CTkButton(
            left_buttons, text=self.t("delete"), command=self._handle_delete_task,
            fg_color=self.colors['error'], hover_color=self.colors['accent_tertiary'], text_color='#FFFFFF'
        )
        self.delete_btn.pack(side='left')
        self.delete_btn.configure(state='disabled')
        
        right_frame = ctk.CTkFrame(action_frame, fg_color='transparent')
        right_frame.pack(side='right', fill='y')

        view_button_frame = ctk.CTkFrame(right_frame, fg_color=self.colors['bg_hover'], corner_radius=14)
        view_button_frame.pack(side='left', padx=(0, 15), pady=12)
        
        for view in ["Month", "Week", "Day"]:
            btn = ctk.CTkButton(
                view_button_frame,
                text=view,
                command=lambda v=view: self._change_view(v),
                font=ctk.CTkFont(family="SF Pro Text", size=14, weight="bold"),
                corner_radius=12,
                height=35,
                width=80
            )
            btn.pack(side='left', padx=3, pady=3)
            self.view_buttons[view] = btn

        theme_var = ctk.StringVar(value=self.current_theme_key)
        theme_switch = ctk.CTkOptionMenu(
            right_frame, values=list(THEMES.keys()), command=self._change_theme,
            variable=theme_var, width=140, fg_color=self.colors['bg_secondary'],
            text_color=self.colors['text_primary'], button_color=self.colors['bg_hover'],
            button_hover_color=self.colors['border'], dropdown_fg_color=self.colors['bg_secondary'],
            dropdown_text_color=self.colors['text_primary'], dropdown_hover_color=self.colors['bg_hover']
        )
        theme_switch.pack(side='left', padx=(0, 15), pady=12)
        
        # Language toggle
        lang_var = ctk.StringVar(value=self.current_language)
        lang_switch = ctk.CTkOptionMenu(
            right_frame, 
            values=["en", "fa"], 
            command=self.switch_language,
            variable=lang_var, 
            width=80, 
            fg_color=self.colors['bg_secondary'],
            text_color=self.colors['text_primary'], 
            button_color=self.colors['bg_hover'],
            button_hover_color=self.colors['border'], 
            dropdown_fg_color=self.colors['bg_secondary'],
            dropdown_text_color=self.colors['text_primary'], 
            dropdown_hover_color=self.colors['bg_hover']
        )
        lang_switch.pack(side='left', padx=(15, 0), pady=12)
        
        self._update_view_selector_style()
    
    def _change_theme(self, new_theme_name):
        """Callback to switch theme and rebuild UI"""
        if new_theme_name in THEMES:
            view_to_restore = self.current_view
            
            self.current_theme_key = new_theme_name
            self.colors = THEMES[new_theme_name]
            self._apply_theme_settings()
            
            if self.main_container:
                self.main_container.destroy()
            
            self.day_buttons = {}
            self.task_cards = []
            self.selected_task = None
            
            self._create_layout()
            
            self.current_view = view_to_restore 
            self._change_view(self.current_view)
            self._update_header()
            self._refresh_tasks()
    
    def _update_view_selector_style(self):
        """Highlights the currently active view button."""
        for view, btn in self.view_buttons.items():
            if view == self.current_view:
                btn.configure(
                    fg_color=self.colors['accent_primary'],
                    text_color='#FFFFFF',
                    hover_color=self.colors['accent_secondary']
                )
            else:
                btn.configure(
                    fg_color=self.colors['bg_hover'],
                    text_color=self.colors['text_primary'],
                    hover_color=self.colors['border']
                )
    
    def _change_view(self, view_name):
        """Switches between Month, Week, and Day views."""
        self.current_view = view_name
        self._update_view_selector_style()
        
        for widget in self.view_container.winfo_children():
            widget.destroy()
        
        if view_name == "Month":
            self._create_month_view(self.view_container)
        elif view_name == "Week":
            self._create_week_view(self.view_container)
        elif view_name == "Day":
            self._create_day_view(self.view_container)
        
        self._refresh_tasks()
    
    def _create_month_view(self, parent):
        """Builds the Month View UI elements."""
        cal_header = ctk.CTkFrame(parent, fg_color='transparent', height=70)
        cal_header.pack(fill='x', padx=25, pady=(25, 15))
        cal_header.pack_propagate(False)
        
        prev_btn = ctk.CTkButton(cal_header, text="◀", command=lambda: self._change_month(-1), width=40)
        prev_btn.pack(side='left')
        
        month_year = self.current_date.strftime("%B %Y")
        self.month_label = ctk.CTkLabel(
            cal_header, text=month_year,
            font=ctk.CTkFont(family="SF Pro Display", size=22, weight="bold"),
            text_color=self.colors['text_primary']
        )
        self.month_label.pack(side='left', expand=True)
        
        next_btn = ctk.CTkButton(cal_header, text="◀", command=lambda: self._change_month(1), width=40)
        next_btn.pack(side='left')
        
        self.cal_grid_container = ctk.CTkFrame(parent, fg_color='transparent')
        self.cal_grid_container.pack(fill='both', expand=True, padx=25, pady=(0, 25))
    
    def _update_calendar_grid(self):
        """Update calendar grid with current month data"""
        if hasattr(self, 'cal_grid_container'):
            for widget in self.cal_grid_container.winfo_children():
                widget.destroy()
            
        cal = calendar.Calendar(self.current_date.year, self.current_date.month)
        weeks = cal.monthdayscalendar()
        
        for week in weeks:
            week_frame = ctk.CTkFrame(self.cal_grid_container, fg_color='transparent')
            week_frame.pack(fill='x', pady=2)
            
            for day in week:
                if day == 0:
                    day_btn = ctk.CTkLabel(week_frame, text="", width=35, height=35)
                else:
                    day_date = self.current_date.replace(day=day)
                    date_str = day_date.strftime("%Y-%m-%d")
                    is_today = (date_str == self.selected_date.strftime("%Y-%m-%d"))
                    
                    bg_color = self.colors['today'] if is_today else self.colors['bg_primary']
                    text_color = self.colors['accent_primary'] if date_str in self.tasks_by_date else self.colors['text_primary']
                    
                    day_btn = ctk.CTkButton(
                        week_frame,
                        text=str(day),
                        width=35,
                        height=35,
                        font=ctk.CTkFont(size=14, weight="bold"),
                        fg_color=bg_color,
                        text_color=text_color,
                        hover_color=self.colors['accent_secondary'],
                        command=lambda d=day_date: self.on_day_select(d)
                    )
                    
                    if date_str in self.tasks_by_date:
                        # Show task indicator dot
                        task_count = len(self.tasks_by_date[date_str])
                        if task_count > 0:
                            indicator = ctk.CTkLabel(
                                week_frame,
                                text="●",
                                font=ctk.CTkFont(size=12),
                                text_color=self.colors['task_dot']
                            )
                            indicator.place(relx=0.7, rely=0.3)
                
                day_btn.pack(side='left', padx=2, pady=2)
                
                if day and (date_str == self.selected_date.strftime("%Y-%m-%d")):
                    self.day_buttons[date_str] = day_btn
    
    def _create_week_view(self, parent):
        """Create week view placeholder"""
        placeholder = ctk.CTkLabel(parent, text="Week View Coming Soon", font=ctk.CTkFont(size=18))
        placeholder.pack(expand=True, pady=50)
    
    def _create_day_view(self, parent):
        """Create day view placeholder"""
        placeholder = ctk.CTkLabel(parent, text="Day View Coming Soon", font=ctk.CTkFont(size=18))
        placeholder.pack(expand=True, pady=50)
    
    def _change_month(self, direction):
        """Navigate between months"""
        import calendar
        year = self.current_date.year
        month = self.current_date.month + direction
        
        if month > 12:
            month = 1
            year += 1
        elif month < 1:
            month = 12
            year -= 1
            
        self.current_date = self.current_date.replace(year=year, month=month, day=1)
        self._update_header()
        self._update_calendar_grid()
    
    def _handle_edit_task(self):
        """Handle edit task button click"""
        if self.selected_task:
            self.on_edit_task(self.selected_task)
    
    def _handle_delete_task(self):
        """Handle delete task button click"""
        if self.selected_task:
            self.on_delete_task(self.selected_task)
    
    def _update_header(self):
        """Update header with current selected date"""
        date_str = self.selected_date.strftime("%A, %B %d, %Y")
        self.header_label.configure(text=date_str)
        self.month_label.configure(text=self.selected_date.strftime("%B %Y"))
    
    def _refresh_tasks(self):
        """Refresh task display for selected date"""
        if not hasattr(self, 'tasks_scroll'):
            return
            
        for card in self.task_cards: card.destroy()
        self.task_cards.clear()
        self.selected_task = None
        
        if hasattr(self, 'edit_btn'): self.edit_btn.configure(state='disabled')
        if hasattr(self, 'delete_btn'): self.delete_btn.configure(state='disabled')
        
        date_key = self.selected_date.strftime("%Y-%m-%d")
        tasks = self.tasks_by_date.get(date_key, [])
        
        if hasattr(self, 'task_count_label'): self.task_count_label.configure(text=str(len(tasks)))
        
        if not tasks:
            empty_label = ctk.CTkLabel(self.tasks_scroll, text=self.t("no_tasks"), font=ctk.CTkFont(family="SF Pro Text", size=15), text_color=self.colors['text_tertiary'], justify='center')
            empty_label.pack(expand=True, pady=40)
            self.task_cards.append(empty_label)
    
    def _auto_save_tasks(self):
        """Auto-save tasks to file"""
        try:
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks_by_date, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving tasks: {e}")
    
    def _load_tasks(self):
        """Load tasks from file"""
        try:
            if self.tasks_file.exists():
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    self.tasks_by_date = json.load(f)
        except Exception as e:
            print(f"Error loading tasks: {e}")
    
    def _save_settings(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving settings: {e}")
    
    def _load_settings(self):
        """Load settings from file"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings.update(loaded_settings)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def set_tasks(self, tasks_dict):
        """Set tasks from external source"""
        self.tasks_by_date = tasks_dict
        self._refresh_tasks()


if __name__ == "__main__":
    from datetime import date
    
    # --- 1. Setup Sample Data ---
    today_str = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    sample_tasks = {
        today_str: [
            {'title': 'Team Meeting', 'completed': False, 'date_str': today_str},
            {'title': 'Finish Project Proposal', 'completed': False, 'date_str': today_str},
            {'title': 'Lunch Break', 'completed': False, 'date_str': today_str},
            {'title': 'Gym Session', 'completed': True, 'date_str': today_str}
        ],
        tomorrow_str: [
            {'title': 'Client Presentation', 'completed': False, 'date_str': tomorrow_str}
        ]
    }
    
    # --- 2. Create Root Window and UI Instance ---
    root = ctk.CTk()
    
    ui = PlannerUI(
        root=root,
        on_day_select=lambda d: print(f"Selected date: {d.strftime('%Y-%m-%d')}"),
        on_add_task=lambda: print("Add task clicked"),
        on_edit_task=lambda task: print(f"Edit task: {task}"),
        on_delete_task=lambda task: print(f"Delete task: {task}"),
        on_ai_schedule=lambda: print("AI schedule clicked"),
        on_task_toggle=lambda task: print(f"Toggle task: {task}")
    )
    
    # --- 3. Load Sample Data and Initial State ---
    ui.set_tasks(sample_tasks)
    
    # --- 4. Start the Application Event Loop ---
    root.mainloop()