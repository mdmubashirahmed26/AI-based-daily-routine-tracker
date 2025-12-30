#!/usr/bin/env python3
"""
Enhanced Personal Daily Routine Tracker (Tkinter GUI)
Features added:
 - MySQL-backed DB (via database.py)
 - Activity time slot and date support
 - Notifications for completed and pending activities (plyer)
 - Dynamic AI insights via AIAnalyzer
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext
import uuid
import time
import threading
from datetime import datetime, date, timedelta, time as dtime
from typing import List, Dict, Any
import math
import webbrowser
import json
import re
from dateutil import parser as dateparser

# Database
from database import Session, Activity, DaySummary, get_weekly_data, get_monthly_data

# AI Module
from ai_module import AIAnalyzer, generate_weekly_report, generate_productivity_insights

# Utils
from utils import minutes_to_hhmm, seconds_to_hhmmss, format_timedelta

# Notifications (cross-platform)
try:
    from plyer import notification as plyer_notification
    HAS_PLYER = True
except Exception:
    HAS_PLYER = False

# Optional plotting
try:
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    import pandas as pd
    HAS_MPL = True
except Exception:
    HAS_MPL = False

SAVE_INTERVAL = 10  # seconds between autosaves
NOTIFY_CHECK_INTERVAL_MS = 60 * 1000  # 60 seconds

def send_notification(title: str, message: str):
    """Send a desktop notification if plyer is available"""
    if HAS_PLYER:
        try:
            plyer_notification.notify(title=title, message=message, timeout=6)
        except Exception as e:
            print("Notification failed:", e)
    else:
        print("Notification:", title, message)

def parse_time_range(slot: str):
    """
    Parse many flexible formats to (start_time, end_time)
    Returns tuple of datetime.time or (None, None) if parsing fails.
    Examples accepted:
      - "8-9 pm"
      - "20:00-21:00"
      - "8:00pm-9:00pm"
      - "08:00-09:00"
    """
    if not slot:
        return (None, None)
    slot = slot.strip()
    # normalize dash characters
    slot = slot.replace("–", "-").replace("—", "-")
    parts = slot.split("-")
    if len(parts) != 2:
        # maybe single time like "20:00"
        try:
            t = dateparser.parse(slot).time()
            return (t, t)
        except Exception:
            return (None, None)
    left, right = parts[0].strip(), parts[1].strip()

    # try parse with dateutil (handles am/pm and many formats)
    try:
        now = datetime.now()
        start_dt = dateparser.parse(left, default=now)
        end_dt = dateparser.parse(right, default=now)
        return (start_dt.time(), end_dt.time())
    except Exception:
        # last resort, match digits
        m1 = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', left, re.I)
        m2 = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', right, re.I)
        if not m1 or not m2:
            return (None, None)
        def to_time(m):
            h = int(m.group(1))
            mm = int(m.group(2) or 0)
            ampm = m.group(3)
            if ampm:
                ampm = ampm.lower()
                if ampm == "pm" and h < 12:
                    h += 12
                if ampm == "am" and h == 12:
                    h = 0
            return dtime(hour=h, minute=mm)
        try:
            return (to_time(m1), to_time(m2))
        except Exception:
            return (None, None)

class EnhancedActivity:
    def __init__(self, name: str, planned_minutes: int, category: str = "General", priority: int = 1,
                 activity_date: date = None, activity_time: str = None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.planned_minutes = int(planned_minutes)
        self.category = category
        self.priority = priority
        self.elapsed_seconds = 0
        self.running = False
        self.last_started_at = None
        self.completed = False
        self.created_at = datetime.utcnow().isoformat()
        self.tags = []
        # new fields
        self.activity_time = activity_time  # free text slot
        self.activity_date = activity_date or date.today()

    def start(self):
        if self.completed:
            return
        if not self.running:
            self.running = True
            self.last_started_at = time.time()

    def pause(self):
        if self.running:
            now = time.time()
            self.elapsed_seconds += int(now - (self.last_started_at or now))
            self.running = False
            self.last_started_at = None

    def stop_and_complete(self):
        self.pause()
        self.completed = True

    def tick_update(self):
        if self.running and self.last_started_at:
            now = time.time()
            return int(self.elapsed_seconds + (now - self.last_started_at))
        return int(self.elapsed_seconds)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "planned_minutes": self.planned_minutes,
            "category": self.category,
            "priority": self.priority,
            "elapsed_seconds": int(self.elapsed_seconds),
            "running": bool(self.running),
            "last_started_at": float(self.last_started_at) if self.last_started_at else None,
            "completed": bool(self.completed),
            "created_at": self.created_at,
            "tags": self.tags,
            "activity_time": self.activity_time,
            "activity_date": self.activity_date.isoformat() if self.activity_date else None
        }

    def to_db_model(self, day_date: date):
        # store both 'date' (day record) and activity_date (explicit)
        from datetime import datetime as _dt
        return Activity(
            id=self.id,
            date=day_date,
            activity_date=self.activity_date,
            name=self.name,
            planned_minutes=self.planned_minutes,
            elapsed_seconds=self.elapsed_seconds,
            category=self.category,
            priority=self.priority,
            completed=self.completed,
            activity_time=self.activity_time,
            created_at=_dt.fromisoformat(self.created_at)
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        a = cls(
            d.get("name", "Untitled"),
            int(d.get("planned_minutes", 0)),
            d.get("category", "General"),
            d.get("priority", 1),
            dateparser.parse(d.get("activity_date")).date() if d.get("activity_date") else date.today(),
            d.get("activity_time")
        )
        a.id = d.get("id", a.id)
        a.elapsed_seconds = int(d.get("elapsed_seconds", 0))
        a.running = bool(d.get("running", False))
        a.last_started_at = d.get("last_started_at", None)
        a.completed = bool(d.get("completed", False))
        a.created_at = d.get("created_at", a.created_at)
        a.tags = d.get("tags", [])
        return a

    @classmethod
    def from_db_model(cls, db_activity: Activity):
        a = cls(
            db_activity.name,
            db_activity.planned_minutes or 0,
            db_activity.category or "General",
            db_activity.priority or 1,
            db_activity.activity_date or db_activity.date,
            db_activity.activity_time
        )
        a.id = db_activity.id
        a.elapsed_seconds = db_activity.elapsed_seconds or 0
        a.completed = db_activity.completed or False
        a.created_at = db_activity.created_at.isoformat() if db_activity.created_at else datetime.utcnow().isoformat()
        return a

class EnhancedRoutineApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Enhanced Daily Routine Tracker")
        self.geometry("1100x700")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Data
        self.today = date.today()
        self.session = Session()
        self.activities: List[EnhancedActivity] = self.load_activities_from_db()
        self.ai_analyzer = AIAnalyzer()
        
        # Analytics tab variables
        self.current_analytics_canvas = None
        self.current_analytics_figure = None

        # UI
        self.create_notebook_interface()
        self.populate_activities()

        # Start periodic update and notifier
        self._stop_event = threading.Event()
        self._updater = threading.Thread(target=self._background_save_loop, daemon=True)
        self._updater.start()
        self._ui_update()
        # schedule notifications checker on main thread (Tkinter after)
        self.after(5 * 1000, self._check_notifications_loop)  # start after 5s

    def create_notebook_interface(self):
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Activities Tab
        self.activities_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.activities_frame, text="Activities")
        self.create_activities_tab()

        # Analytics Tab
        self.analytics_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.analytics_frame, text="Analytics")
        self.create_analytics_tab()

        # AI Insights Tab
        self.ai_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.ai_frame, text="AI Insights")
        self.create_ai_tab()
        
        # Bind tab change event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, event):
        """Handle tab change events"""
        selected_tab = self.notebook.index(self.notebook.select())
        
        # Tab names in order: Activities (0), Analytics (1), AI Insights (2)
        if selected_tab == 1:  # Analytics tab
            self.on_analytics_tab_selected()

    def on_analytics_tab_selected(self, event=None):
        """Called when analytics tab is selected"""
        # Clear previous canvas if it exists
        for widget in self.analytics_canvas_frame.winfo_children():
            widget.destroy()
        
        # Add a label prompting user to generate a report
        prompt_label = ttk.Label(self.analytics_canvas_frame, 
                                text="Select options and click 'Generate Report' to view analytics",
                                font=("TkDefaultFont", 11))
        prompt_label.pack(expand=True, pady=50)
        
        # Reset statistics
        self.avg_productivity_var.set(f"Avg Productivity: --")
        self.total_time_var.set(f"Total Tracked Time: --")
        self.completion_rate_var.set(f"Completion Rate: --")
        self.busiest_day_var.set(f"Busiest Day: --")

    def create_activities_tab(self):
        # Top frame: add activity
        top = ttk.Frame(self.activities_frame)
        top.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(top, text="Activity name:").pack(side=tk.LEFT)
        self.entry_name = ttk.Entry(top, width=20)
        self.entry_name.pack(side=tk.LEFT, padx=(4,10))
        
        ttk.Label(top, text="Planned (min):").pack(side=tk.LEFT)
        self.entry_minutes = ttk.Entry(top, width=8)
        self.entry_minutes.pack(side=tk.LEFT, padx=(4,10))
        
        ttk.Label(top, text="Category:").pack(side=tk.LEFT)
        self.category_var = tk.StringVar(value="General")
        category_combo = ttk.Combobox(top, textvariable=self.category_var, width=12)
        category_combo['values'] = ('Work', 'Study', 'Exercise', 'Personal', 'Chores', 'Leisure', 'General')
        category_combo.pack(side=tk.LEFT, padx=(4,10))
        
        ttk.Label(top, text="Priority:").pack(side=tk.LEFT)
        self.priority_var = tk.StringVar(value="Medium")
        priority_combo = ttk.Combobox(top, textvariable=self.priority_var, width=10)
        priority_combo['values'] = ('Low', 'Medium', 'High', 'Critical')
        priority_combo.pack(side=tk.LEFT, padx=(4,10))

        # New fields: date and time slot
        ttk.Label(top, text="Date (YYYY-MM-DD):").pack(side=tk.LEFT)
        self.entry_date = ttk.Entry(top, width=12)
        self.entry_date.insert(0, date.today().isoformat())
        self.entry_date.pack(side=tk.LEFT, padx=(4,10))

        ttk.Label(top, text="Time Slot:").pack(side=tk.LEFT)
        self.entry_time_slot = ttk.Entry(top, width=14)
        self.entry_time_slot.pack(side=tk.LEFT, padx=(4,10))
        ttk.Label(top, text="(e.g. 8-9 pm or 20:00-21:00)").pack(side=tk.LEFT)

        ttk.Button(top, text="Add Activity", command=self.add_activity).pack(side=tk.LEFT, padx=(8,0))

        ttk.Button(top, text="Quick Report", command=self.generate_quick_report).pack(side=tk.RIGHT, padx=4)

        # Middle: activities list + controls
        mid = ttk.Frame(self.activities_frame)
        mid.pack(fill=tk.BOTH, expand=True, padx=8)

        # left: tree list (add Date and Time Slot columns)
        left = ttk.Frame(mid)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cols = ("Name", "Category", "Priority", "Planned", "Elapsed", "Date", "Time Slot", "Status")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c)
            if c == "Name":
                self.tree.column(c, width=200, anchor=tk.W)
            elif c in ["Planned", "Elapsed", "Date", "Time Slot"]:
                self.tree.column(c, width=100, anchor=tk.CENTER)
            else:
                self.tree.column(c, width=100, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        scrollbar = ttk.Scrollbar(left, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # right: control panel
        right = ttk.Frame(mid, width=320)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(8,0))

        self.selected_label = ttk.Label(right, text="No activity selected", font=("TkDefaultFont", 11, "bold"))
        self.selected_label.pack(anchor=tk.W, pady=(6,8))
        self.start_btn = ttk.Button(right, text="Start", command=self.start_selected, state=tk.DISABLED)
        self.start_btn.pack(fill=tk.X, pady=4)
        self.pause_btn = ttk.Button(right, text="Pause", command=self.pause_selected, state=tk.DISABLED)
        self.pause_btn.pack(fill=tk.X, pady=4)
        self.complete_btn = ttk.Button(right, text="Complete", command=self.complete_selected, state=tk.DISABLED)
        self.complete_btn.pack(fill=tk.X, pady=4)
        ttk.Separator(right).pack(fill=tk.X, pady=6)
        self.delete_btn = ttk.Button(right, text="Delete Activity", command=self.delete_selected, state=tk.DISABLED)
        self.delete_btn.pack(fill=tk.X, pady=4)

        ttk.Separator(right).pack(fill=tk.X, pady=6)
        ttk.Label(right, text="Summary", font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(4,2))
        self.sum_planned_var = tk.StringVar(value="Planned: 0 min")
        self.sum_elapsed_var = tk.StringVar(value="Elapsed: 0 min")
        self.sum_remaining_var = tk.StringVar(value="Remaining (24h): 24:00")
        self.sum_productivity_var = tk.StringVar(value="Productivity: 0%")
        ttk.Label(right, textvariable=self.sum_planned_var).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.sum_elapsed_var).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.sum_remaining_var).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.sum_productivity_var).pack(anchor=tk.W, pady=2)

        ttk.Button(right, text="Show Daily Chart", command=self.show_daily_chart).pack(fill=tk.X, pady=(12,4))
        ttk.Button(right, text="Weekly Overview", command=self.show_weekly_overview).pack(fill=tk.X, pady=4)

        # bottom status
        bottom = ttk.Frame(self.activities_frame)
        bottom.pack(fill=tk.X, padx=8, pady=6)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.status_var).pack(side=tk.LEFT)

    def create_analytics_tab(self):
        main_frame = ttk.Frame(self.analytics_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        
        controls = ttk.Frame(main_frame)
        controls.pack(fill=tk.X, pady=(0,8))
        
        ttk.Label(controls, text="Time Range:").pack(side=tk.LEFT)
        self.range_var = tk.StringVar(value="week")
        ttk.Combobox(controls, textvariable=self.range_var, values=["week", "month"], state="readonly", width=10).pack(side=tk.LEFT, padx=(4,12))
        
        ttk.Label(controls, text="Chart Type:").pack(side=tk.LEFT)
        self.chart_type_var = tk.StringVar(value="time_spent")
        chart_combo = ttk.Combobox(controls, textvariable=self.chart_type_var, 
                                 values=["time_spent", "completion_rate", "productivity_trend", "category_breakdown"], 
                                 state="readonly", width=15)
        chart_combo.pack(side=tk.LEFT, padx=(4,12))
        
        ttk.Button(controls, text="Generate Report", command=self.update_analytics).pack(side=tk.LEFT)

        self.analytics_canvas_frame = ttk.Frame(main_frame)
        self.analytics_canvas_frame.pack(fill=tk.BOTH, expand=True)

        # Stats frame
        stats_frame = ttk.LabelFrame(main_frame, text="Statistics")
        stats_frame.pack(fill=tk.X, pady=(8,0))
        stats_inner = ttk.Frame(stats_frame)
        stats_inner.pack(fill=tk.X, padx=8, pady=8)
        
        self.avg_productivity_var = tk.StringVar(value="Avg Productivity: --")
        self.total_time_var = tk.StringVar(value="Total Tracked Time: --")
        self.completion_rate_var = tk.StringVar(value="Completion Rate: --")
        self.busiest_day_var = tk.StringVar(value="Busiest Day: --")
        
        ttk.Label(stats_inner, textvariable=self.avg_productivity_var).grid(row=0, column=0, sticky=tk.W, padx=(0,20))
        ttk.Label(stats_inner, textvariable=self.total_time_var).grid(row=0, column=1, sticky=tk.W, padx=(0,20))
        ttk.Label(stats_inner, textvariable=self.completion_rate_var).grid(row=1, column=0, sticky=tk.W, padx=(0,20))
        ttk.Label(stats_inner, textvariable=self.busiest_day_var).grid(row=1, column=1, sticky=tk.W, padx=(0,20))
        
        stats_inner.columnconfigure(0, weight=1)
        stats_inner.columnconfigure(1, weight=1)

    def create_ai_tab(self):
        main_frame = ttk.Frame(self.ai_frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        controls = ttk.Frame(main_frame)
        controls.pack(fill=tk.X, pady=(0,8))
        ttk.Button(controls, text="Generate Daily Insights", command=self.generate_daily_insights).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(controls, text="Weekly Summary", command=self.generate_weekly_summary).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(controls, text="Productivity Tips", command=self.generate_productivity_tips).pack(side=tk.LEFT)
        ttk.Button(controls, text="Clear", command=self.clear_ai_output).pack(side=tk.RIGHT)
        output_frame = ttk.LabelFrame(main_frame, text="AI Insights")
        output_frame.pack(fill=tk.BOTH, expand=True)
        self.ai_output = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, width=80, height=20)
        self.ai_output.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ai_output.config(state=tk.DISABLED)

    def load_activities_from_db(self) -> List[EnhancedActivity]:
        activities = []
        try:
            db_activities = (
                self.session.query(Activity)
                .filter(Activity.activity_date == self.today)
                .all()
            )

            for db_act in db_activities:
                activities.append(EnhancedActivity.from_db_model(db_act))
        except Exception as e:
            print(f"Error loading from DB: {e}")
        return activities

    def save_activities_to_db(self):
        try:
            self.session.query(Activity).filter(Activity.activity_date == self.today).delete()

            # Add current activities
            for act in self.activities:
                db_activity = act.to_db_model(self.today)
                self.session.add(db_activity)
            
            self.session.commit()
        except Exception as e:
            print(f"Error saving to DB: {e}")
            self.session.rollback()

    def add_activity(self):
        name = self.entry_name.get().strip()
        mins = self.entry_minutes.get().strip()
        category = self.category_var.get()
        priority_map = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
        priority = priority_map.get(self.priority_var.get(), 2)
        date_text = self.entry_date.get().strip()
        time_slot_text = self.entry_time_slot.get().strip()
        
        if not name:
            messagebox.showwarning("Missing name", "Please enter activity name.")
            return
        try:
            mins_i = int(mins) if mins else 0
        except Exception:
            messagebox.showwarning("Invalid minutes", "Planned minutes must be an integer.")
            return

        # parse date
        try:
            activity_date = dateparser.parse(date_text).date() if date_text else self.today
        except Exception:
            messagebox.showwarning("Invalid date", "Please enter date in a valid format (YYYY-MM-DD).")
            return
        
        act = EnhancedActivity(name, mins_i, category, priority, activity_date, time_slot_text)
        self.activities.append(act)
        self._insert_activity_row(act)
        self.entry_name.delete(0, tk.END)
        self.entry_minutes.delete(0, tk.END)
        # reset time slot? keep as is
        self.save_data()
        self.status_var.set(f"Added '{name}'")
        # check immediately if reminder needed
        self._check_pending_for_activity(act, notify_soon=True)

    def _insert_activity_row(self, act: EnhancedActivity):
        planned = f"{act.planned_minutes} min"
        elapsed = seconds_to_hhmmss(act.tick_update())
        status = "Running" if act.running else ("Completed" if act.completed else "Paused")
        priority_text = ["Low", "Medium", "High", "Critical"][min(act.priority-1, 3)]
        date_str = act.activity_date.isoformat() if act.activity_date else ""
        time_slot = act.activity_time or ""
        
        self.tree.insert("", tk.END, iid=act.id, 
                        values=(act.name, act.category, priority_text, planned, elapsed, date_str, time_slot, status))

    def populate_activities(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for act in self.activities:
            self._insert_activity_row(act)
        self.update_summary()

    def find_activity(self, aid: str) -> EnhancedActivity:
        for a in self.activities:
            if a.id == aid:
                return a
        return None

    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self.selected_label.config(text="No activity selected")
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.DISABLED)
            self.complete_btn.config(state=tk.DISABLED)
            self.delete_btn.config(state=tk.DISABLED)
            return
        aid = sel[0]
        act = self.find_activity(aid)
        if not act:
            return
        self.selected_label.config(text=f"{act.name} ({act.category}) - Planned: {act.planned_minutes} min")
        self.start_btn.config(state=(tk.NORMAL if not act.running and not act.completed else tk.DISABLED))
        self.pause_btn.config(state=(tk.NORMAL if act.running else tk.DISABLED))
        self.complete_btn.config(state=(tk.NORMAL if not act.completed else tk.DISABLED))
        self.delete_btn.config(state=tk.NORMAL)

    def start_selected(self):
        sel = self.tree.selection()
        if not sel: return
        act = self.find_activity(sel[0])
        if not act: return
        # Pause any other running activities
        for a in self.activities:
            if a.running and a.id != act.id:
                a.pause()
        act.start()
        self.status_var.set(f"Started '{act.name}'")
        self.save_data()

    def pause_selected(self):
        sel = self.tree.selection()
        if not sel: return
        act = self.find_activity(sel[0])
        if not act: return
        act.pause()
        self.status_var.set(f"Paused '{act.name}'")
        self.save_data()

    def complete_selected(self):
        sel = self.tree.selection()
        if not sel: return
        act = self.find_activity(sel[0])
        if not act: return
        act.stop_and_complete()
        self.status_var.set(f"Completed '{act.name}'")
        self.save_data()
        # send notification
        send_notification("Activity Completed", f"You finished: {act.name}")

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel: return
        aid = sel[0]
        act = self.find_activity(aid)
        if not act: return
        if messagebox.askyesno("Delete", f"Delete activity '{act.name}'?"):
            self.activities = [a for a in self.activities if a.id != aid]
            self.tree.delete(aid)
            self.save_data()
            self.status_var.set(f"Deleted '{act.name}'")
            self.update_summary()

    def update_summary(self):
        total_planned = sum(a.planned_minutes for a in self.activities)
        total_elapsed = sum(a.tick_update() for a in self.activities) // 60
        completed_planned = sum(a.planned_minutes for a in self.activities if a.completed)
        
        productivity = (completed_planned / total_planned * 100) if total_planned > 0 else 0
        remaining_day_minutes = 24*60 - total_elapsed
        
        self.sum_planned_var.set(f"Planned: {total_planned} min")
        self.sum_elapsed_var.set(f"Elapsed: {total_elapsed} min")
        self.sum_remaining_var.set(f"Remaining (24h): {minutes_to_hhmm(remaining_day_minutes)}")
        self.sum_productivity_var.set(f"Productivity: {productivity:.1f}%")

    def _ui_update(self):
        for act in self.activities:
            if act.id in self.tree.get_children():
                elapsed = seconds_to_hhmmss(act.tick_update())
                status = "Running" if act.running else ("Completed" if act.completed else "Paused")
                planned = f"{act.planned_minutes} min"
                priority_text = ["Low", "Medium", "High", "Critical"][min(act.priority-1, 3)]
                date_str = act.activity_date.isoformat() if act.activity_date else ""
                time_slot = act.activity_time or ""
                
                try:
                    self.tree.item(act.id, values=(act.name, act.category, priority_text, planned, elapsed, date_str, time_slot, status))
                except Exception:
                    pass
                
                if act.planned_minutes > 0 and (act.tick_update() // 60) > act.planned_minutes and not act.completed:
                    self.tree.item(act.id, values=(act.name, act.category, priority_text, planned, elapsed, date_str, time_slot, f"{status} (Overrun)"))
        
        self.update_summary()
        self.after(1000, self._ui_update)

    def save_data(self):
        self.save_activities_to_db()

    def _background_save_loop(self):
        while not self._stop_event.wait(SAVE_INTERVAL):
            for a in self.activities:
                if a.running:
                    now = time.time()
                    a.elapsed_seconds = int(a.elapsed_seconds + (now - (a.last_started_at or now)))
                    a.last_started_at = now
            self.save_data()

    def on_close(self):
        for a in self.activities:
            if a.running:
                a.pause()
        self.save_data()
        self.session.close()
        self._stop_event.set()
        self.destroy()

    def show_daily_chart(self):
        if not HAS_MPL:
            messagebox.showinfo("Matplotlib missing", "matplotlib is required for charts. Install with `pip install matplotlib`.")
            return
        
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        planned = sum(a.planned_minutes for a in self.activities)
        spent = sum(a.tick_update() for a in self.activities) / 60.0
        remaining_day = 24*60 - spent
        remaining_day = max(0, remaining_day)
        
        labels = ["Planned", "Spent", "Remaining Day"]
        sizes = [planned, spent, remaining_day]
        
        ax1.pie([x for x in sizes if x > 0], 
                labels=[l for i, l in enumerate(labels) if sizes[i] > 0], 
                autopct=lambda p: f"{p:.1f}%\n({int(p/100*sum(sizes))}m)", 
                startangle=90)
        ax1.set_title("Daily Time Distribution")
        
        categories = {}
        for act in self.activities:
            cat = act.category
            if cat not in categories:
                categories[cat] = {"planned": 0, "actual": 0}
            categories[cat]["planned"] += act.planned_minutes
            categories[cat]["actual"] += act.tick_update() / 60
            
        if categories:
            cat_names = list(categories.keys())
            planned_vals = [categories[cat]["planned"] for cat in cat_names]
            actual_vals = [categories[cat]["actual"] for cat in cat_names]
            x = range(len(cat_names))
            width = 0.35
            ax2.bar([i - width/2 for i in x], planned_vals, width, label='Planned')
            ax2.bar([i + width/2 for i in x], actual_vals, width, label='Actual')
            ax2.set_xlabel('Categories')
            ax2.set_ylabel('Minutes')
            ax2.set_title('Planned vs Actual by Category')
            ax2.set_xticks(x)
            ax2.set_xticklabels(cat_names, rotation=45)
            ax2.legend()
            
        plt.tight_layout()
        plt.show()

    def show_weekly_overview(self):
        if not HAS_MPL:
            messagebox.showinfo("Matplotlib missing", "matplotlib is required for charts.")
            return
        
        end_date = self.today
        start_date = end_date - timedelta(days=6)
        weekly_data = get_weekly_data(self.session, start_date, end_date)
        
        if not weekly_data:
            messagebox.showinfo("No Data", "No data available for the past week.")
            return
        
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
        
        dates = [data['date'] for data in weekly_data]
        productivity = [data['productivity'] for data in weekly_data]
        ax1.plot(dates, productivity, marker='o', linewidth=2)
        ax1.set_title('Weekly Productivity Trend')
        ax1.set_ylabel('Productivity (%)')
        ax1.grid(True, alpha=0.3)
        
        total_minutes = [data['total_minutes'] for data in weekly_data]
        ax2.bar(dates, total_minutes, alpha=0.7)
        ax2.set_title('Total Time Tracked per Day')
        ax2.set_ylabel('Minutes')
        ax2.set_xlabel('Date')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()

    def update_analytics(self):
        if not HAS_MPL:
            messagebox.showinfo("Matplotlib missing", "matplotlib is required for analytics.")
            return
        
        # Clear previous canvas if it exists
        for widget in self.analytics_canvas_frame.winfo_children():
            widget.destroy()
        
        time_range = self.range_var.get()
        if time_range == "week":
            end_date = self.today
            start_date = end_date - timedelta(days=6)
            data = get_weekly_data(self.session, start_date, end_date)
        else:
            end_date = self.today
            start_date = end_date - timedelta(days=29)
            data = get_monthly_data(self.session, start_date, end_date)
        
        # Check if we have data
        if not data:
            no_data_label = ttk.Label(self.analytics_canvas_frame, 
                                      text="No data available for the selected time range.", 
                                      font=("TkDefaultFont", 12))
            no_data_label.pack(expand=True, pady=20)
            self.update_analytics_stats(data)
            return
        
        # Create new figure
        from matplotlib.figure import Figure
        fig = Figure(figsize=(10, 6), dpi=100)
        ax = fig.add_subplot(111)
        
        chart_type = self.chart_type_var.get()
        
        if chart_type == "time_spent":
            dates = [d['date'].strftime('%m/%d') for d in data]
            minutes = [d['total_minutes'] for d in data]
            bars = ax.bar(dates, minutes, alpha=0.7, color='skyblue')
            ax.set_title('Time Spent per Day', fontsize=14, fontweight='bold')
            ax.set_ylabel('Minutes', fontsize=12)
            ax.set_xlabel('Date', fontsize=12)
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3, linestyle='--')
            
            # Add value labels on top of bars
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{int(height)}', ha='center', va='bottom', fontsize=9)
        
        elif chart_type == "completion_rate":
            dates = [d['date'].strftime('%m/%d') for d in data]
            completion = [d['completion_rate'] for d in data]
            line = ax.plot(dates, completion, marker='o', linewidth=2, color='green', markersize=8)[0]
            ax.set_title('Completion Rate Trend', fontsize=14, fontweight='bold')
            ax.set_ylabel('Completion Rate (%)', fontsize=12)
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylim(0, 100)
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3, linestyle='--')
            
            # Add value labels near points
            for x, y in zip(dates, completion):
                ax.text(x, y + 2, f'{y:.1f}%', ha='center', va='bottom', fontsize=9)
        
        elif chart_type == "productivity_trend":
            dates = [d['date'].strftime('%m/%d') for d in data]
            productivity = [d['productivity'] for d in data]
            line = ax.plot(dates, productivity, marker='s', linewidth=2, color='orange', markersize=8)[0]
            ax.set_title('Productivity Trend', fontsize=14, fontweight='bold')
            ax.set_ylabel('Productivity (%)', fontsize=12)
            ax.set_xlabel('Date', fontsize=12)
            ax.set_ylim(0, 100)
            ax.tick_params(axis='x', rotation=45)
            ax.grid(True, alpha=0.3, linestyle='--')
            
            # Add value labels near points
            for x, y in zip(dates, productivity):
                ax.text(x, y + 2, f'{y:.1f}%', ha='center', va='bottom', fontsize=9)
        
        elif chart_type == "category_breakdown":
            # Aggregate category data across all days
            category_totals = {}
            for day_data in data:
                categories_dict = day_data.get('categories', {})
                for category, minutes in categories_dict.items():
                    category_totals[category] = category_totals.get(category, 0) + minutes
            
            if category_totals:
                categories = list(category_totals.keys())
                minutes = list(category_totals.values())
                
                # Create a color palette
                colors = plt.cm.Set3.colors[:len(categories)]
                
                wedges, texts, autotexts = ax.pie(minutes, 
                                                 labels=categories, 
                                                 autopct='%1.1f%%', 
                                                 startangle=90,
                                                 colors=colors,
                                                 textprops=dict(fontsize=10))
                ax.set_title('Category Breakdown (Total Time)', fontsize=14, fontweight='bold')
                
                # Make the percentage text bold
                for autotext in autotexts:
                    autotext.set_fontweight('bold')
            else:
                # If no category data, show a message
                ax.text(0.5, 0.5, 'No category data available', 
                       ha='center', va='center', transform=ax.transAxes, fontsize=12)
                ax.set_axis_off()
        
        # Adjust layout
        fig.tight_layout()
        
        # Create and pack the canvas
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        canvas = FigureCanvasTkAgg(fig, self.analytics_canvas_frame)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True)
        
        # Add a toolbar for interaction (optional)
        if HAS_MPL:
            try:
                from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
                toolbar = NavigationToolbar2Tk(canvas, self.analytics_canvas_frame)
                toolbar.update()
                canvas_widget.pack(fill=tk.BOTH, expand=True)
            except Exception:
                pass  # Toolbar optional
        
        # Update statistics
        self.update_analytics_stats(data)
        
        # Store reference to current canvas to prevent garbage collection
        self.current_analytics_canvas = canvas
        self.current_analytics_figure = fig

    def update_analytics_stats(self, data):
        if not data:
            self.avg_productivity_var.set(f"Avg Productivity: --")
            self.total_time_var.set(f"Total Tracked Time: --")
            self.completion_rate_var.set(f"Completion Rate: --")
            self.busiest_day_var.set(f"Busiest Day: --")
            return
        
        total_minutes = sum(d.get('total_minutes', 0) for d in data)
        avg_productivity = sum(d.get('productivity', 0) for d in data) / len(data) if data else 0
        completion_rate = sum(d.get('completion_rate', 0) for d in data) / len(data) if data else 0
        
        # Find busiest day
        if data and any(d.get('total_minutes', 0) > 0 for d in data):
            busiest_day = max(data, key=lambda x: x.get('total_minutes', 0))
            busiest_date = busiest_day['date'].strftime('%Y-%m-%d')
        else:
            busiest_date = "--"
        
        self.avg_productivity_var.set(f"Avg Productivity: {avg_productivity:.1f}%")
        self.total_time_var.set(f"Total Tracked Time: {total_minutes} min")
        self.completion_rate_var.set(f"Completion Rate: {completion_rate:.1f}%")
        self.busiest_day_var.set(f"Busiest Day: {busiest_date}")

    def generate_daily_insights(self):
        if not self.activities:
            messagebox.showinfo("No Data", "No activities to analyze.")
            return
        insights = self.ai_analyzer.generate_daily_insights(self.activities)
        self.display_ai_output(insights)

    def generate_weekly_summary(self):
        end_date = self.today
        start_date = end_date - timedelta(days=6)
        weekly_data = get_weekly_data(self.session, start_date, end_date)
        if not weekly_data:
            messagebox.showinfo("No Data", "No weekly data available.")
            return
        summary = generate_weekly_report(weekly_data)
        self.display_ai_output(summary)

    def generate_productivity_tips(self):
        tips = generate_productivity_insights(self.activities)
        self.display_ai_output(tips)

    def generate_quick_report(self):
        if not self.activities:
            messagebox.showinfo("No Data", "No activities to report.")
            return
        completed = sum(1 for a in self.activities if a.completed)
        total = len(self.activities)
        total_time = sum(a.tick_update() for a in self.activities) // 60
        productivity = (sum(a.planned_minutes for a in self.activities if a.completed) / 
                       sum(a.planned_minutes for a in self.activities) * 100) if any(a.planned_minutes for a in self.activities) else 0
        report = f"""
QUICK DAILY REPORT - {self.today}
--------------------------------
Activities: {completed}/{total} completed ({completed/total*100:.1f}%)
Total Time Tracked: {total_time} minutes
Productivity Score: {productivity:.1f}%
        """.strip()
        messagebox.showinfo("Quick Report", report)

    def display_ai_output(self, text):
        self.ai_output.config(state=tk.NORMAL)
        self.ai_output.delete(1.0, tk.END)
        self.ai_output.insert(tk.END, text)
        self.ai_output.config(state=tk.DISABLED)

    def clear_ai_output(self):
        self.ai_output.config(state=tk.NORMAL)
        self.ai_output.delete(1.0, tk.END)
        self.ai_output.config(state=tk.DISABLED)

    # -----------------------
    # Notification logic
    # -----------------------
    def _check_notifications_loop(self):
        try:
            # run check
            now = datetime.now()
            for act in list(self.activities):
                # only consider tasks for today or matching activity_date
                act_date = act.activity_date or self.today
                if act_date != now.date():
                    continue
                self._check_pending_for_activity(act)
            # schedule next check
            self.after(NOTIFY_CHECK_INTERVAL_MS, self._check_notifications_loop)
        except Exception as e:
            print("Notification loop error:", e)
            self.after(NOTIFY_CHECK_INTERVAL_MS, self._check_notifications_loop)

    def _check_pending_for_activity(self, act: EnhancedActivity, notify_soon=False):
        """Send notification when activity is pending and time slot is active or near."""
        if act.completed:
            return
        if not act.activity_time:
            return
        start_t, end_t = parse_time_range(act.activity_time)
        if not start_t:
            return
        now = datetime.now().time()
        # If 'notify_soon' True (just added), notify if the slot is within next 15 minutes
        if notify_soon:
            today_start = start_t
            # compute difference in minutes until start
            start_dt = datetime.combine(datetime.today(), start_t)
            diff = (start_dt - datetime.now()).total_seconds() / 60.0
            if -5 <= diff <= 15:
                send_notification("Upcoming Activity", f"'{act.name}' starts around {act.activity_time}. Please prepare.")
            return

        # Normal check: if now within [start, end] or within 5 minutes before start -> notify
        in_slot = False
        try:
            # handle overnight slots where end < start (e.g., 23:00-01:00)
            if end_t and end_t >= start_t:
                in_slot = (start_t <= now <= end_t)
            else:
                # crosses midnight
                in_slot = (now >= start_t or (end_t and now <= end_t))
        except Exception:
            in_slot = False

        # compute minutes to start if needed
        start_dt = datetime.combine(datetime.today(), start_t)
        minutes_to_start = (start_dt - datetime.now()).total_seconds() / 60.0
        # if in slot or starting soon
        if in_slot or (-5 <= minutes_to_start <= 5) or (0 <= minutes_to_start <= 15):
            # avoid spamming: we will attach a small flag to act to indicate we've notified recently
            last_notified = getattr(act, "_last_notified_at", None)
            now_ts = time.time()
            if last_notified and (now_ts - last_notified) < 60 * 10:  # 10 minutes cooldown
                return
            act._last_notified_at = now_ts
            if in_slot:
                send_notification("Pending Activity", f"'{act.name}' is scheduled right now ({act.activity_time}). Please complete it.")
            else:
                send_notification("Upcoming Activity", f"'{act.name}' will start soon ({act.activity_time}).")

if __name__ == "__main__":
    # Initialize database
    from database import init_db
    init_db()
    
    app = EnhancedRoutineApp()
    app.mainloop()