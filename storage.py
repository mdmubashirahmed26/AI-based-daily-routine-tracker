import json
from pathlib import Path
from datetime import date
from typing import List, Dict, Any

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def default_filename(for_date: date = None) -> Path:
    if for_date is None:
        for_date = date.today()
    return DATA_DIR / f"{for_date.isoformat()}_activities.json"

def load_day(for_date: date = None) -> Dict[str, Any]:
    """
    Load the day's activities. Returns a dict with keys:
      - date (iso)
      - activities (list)
    If file not found returns empty structure.
    """
    p = default_filename(for_date)
    if not p.exists():
        return {"date": (for_date or date.today()).isoformat(), "activities": []}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_day(data: Dict[str, Any], for_date: date = None) -> None:
    p = default_filename(for_date)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)