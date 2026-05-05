"""
Database module for Routine Tracker using SQLAlchemy ORM
"""
import os
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, DateTime, Date, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date, timedelta
from typing import List, Dict, Any

Base = declarative_base()

class Activity(Base):
    __tablename__ = 'activities'
    
    id = Column(String(36), primary_key=True)
    date = Column(Date, nullable=False, index=True)                # main date (day)
    activity_date = Column(Date, nullable=True, index=True)        # optional: explicit activity date
    name = Column(String(200), nullable=False)
    planned_minutes = Column(Integer, default=0)
    elapsed_seconds = Column(Integer, default=0)
    category = Column(String(50), default='General')
    priority = Column(Integer, default=1)  # 1-4 scale
    completed = Column(Boolean, default=False)
    activity_time = Column(String(50), nullable=True)              # time slot string, e.g. "20:00-21:00" or "8-9 pm"
    created_at = Column(DateTime, default=datetime.utcnow)

class DaySummary(Base):
    __tablename__ = 'day_summaries'
    
    date = Column(Date, primary_key=True)
    total_planned = Column(Integer, default=0)
    total_elapsed = Column(Integer, default=0)
    completion_rate = Column(Float, default=0.0)
    productivity_score = Column(Float, default=0.0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# -----------------------------
# MySQL Database Configuration  
# ----------------------------
MYSQL_USER = "root"
MYSQL_PASSWORD = "****"
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DB = "routine_tracker"

DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, echo=False)

Session = sessionmaker(bind=engine)

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(engine)

def get_weekly_data(session, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """Get weekly aggregated data"""
    results = []
    current_date = start_date
    
    while current_date <= end_date:
        day_activities = session.query(Activity).filter(Activity.date == current_date).all()
        
        if day_activities:
            total_planned = sum(a.planned_minutes for a in day_activities)
            total_elapsed = sum(a.elapsed_seconds for a in day_activities) // 60
            completed_planned = sum(a.planned_minutes for a in day_activities if a.completed)
            completion_rate = (len([a for a in day_activities if a.completed]) / len(day_activities) * 100) if day_activities else 0
            productivity = (completed_planned / total_planned * 100) if total_planned > 0 else 0
            
            # Category breakdown
            categories = {}
            for act in day_activities:
                if act.category not in categories:
                    categories[act.category] = 0
                categories[act.category] += act.elapsed_seconds // 60
            
            results.append({
                'date': current_date,
                'total_planned': total_planned,
                'total_minutes': total_elapsed,
                'completion_rate': completion_rate,
                'productivity': productivity,
                'categories': categories
            })
        else:
            results.append({
                'date': current_date,
                'total_planned': 0,
                'total_minutes': 0,
                'completion_rate': 0,
                'productivity': 0,
                'categories': {}
            })
        
        current_date += timedelta(days=1)
    
    return results

def get_monthly_data(session, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """Get monthly aggregated data (similar to weekly but with different grouping)"""
    return get_weekly_data(session, start_date, end_date)
