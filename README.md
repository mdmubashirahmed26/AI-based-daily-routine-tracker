## Project name

Personal Daily Routine Tracker Application.

## Short description

A Tkinter desktop app to plan, track and analyze daily activities. Stores activities in a MySQL database, offers charts (matplotlib), desktop notifications (plyer), and AI-powered insights (local rule-based fallback plus optional OpenAI LLM integration).

## Features

- Add activities with planned minutes, category, priority, date and time slot.
- Start/pause/complete tasks with elapsed time tracking.
- Persistent storage using SQLAlchemy + MySQL (see `database.py`).
- Daily and weekly analytics with charts (matplotlib + pandas optional).
- Desktop notifications for upcoming or active tasks (plyer).
- AI insights: rule-based fallback insights and (optionally) richer insights via OpenAI API.
- Simple local JSON storage utilities also included (`storage.py`) for per-day files.

## Repository structure (what each file does)

- `app.py` — Main Tkinter GUI application and app logic.
- `ai_module.py` — AI and insights generation (rule-based + OpenAI LLM wrapper).
- `database.py` — SQLAlchemy models, DB setup and aggregation functions.
- `storage.py` — Simple JSON-based per-day load/save helpers.
- `utils.py` — Small helper functions (time formatting, productivity calc).
- `test.py` — Small script to check whether `OPENAI_API_KEY` environment variable is present.

## Prerequisites

- Python 3.8+ recommended.
- MySQL server (or compatible) running locally or reachable from the app.
- On Debian/Ubuntu, to get Tkinter (if missing):

```bash
sudo apt update
sudo apt install python3-tk
```

## Install dependencies

1. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate   # on Windows use: .venv\Scripts\activate
```

2. Install Python packages:

```bash
pip install -r requirements.txt
```

## Database setup

The project currently uses MySQL connection settings in `database.py`:

```py
MYSQL_USER = "root"
MYSQL_PASSWORD = "****"
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DB = "routine_tracker"
```

**Recommended:** create a dedicated database and user for the app. Example SQL commands (run as a MySQL admin user):

```sql
CREATE DATABASE routine_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'rt_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON routine_tracker.* TO 'rt_user'@'localhost';
FLUSH PRIVILEGES;
```

Then update `database.py` with your user/password or modify the code to read DB credentials from environment variables (safer).

To initialize the DB tables, run:

```bash
python -c "from database import init_db; init_db()"
```

(Or just run `python app.py` — `app.py` already calls `init_db()` when executed as `__main__`.)

## OpenAI integration (optional)

- If you want richer AI insights, set the `OPENAI_API_KEY` environment variable before running the app.

```bash
export OPENAI_API_KEY="sk-..."
# Windows PowerShell: $env:OPENAI_API_KEY = 'sk-...'
```

- The app will attempt to instantiate the `LLMInsightModel`. If no API key is found or the client initialization fails, it will fall back to the built-in rule-based insights.

## Run the application

```bash
# Activate venv first if used
python app.py
```

## Quick checks

- `python test.py` — verifies if `OPENAI_API_KEY` is present in your environment.
- If charts do not appear or you get `matplotlib` errors, ensure `matplotlib` and `pandas` are installed.
- If desktop notifications don't appear, confirm `plyer` is installed and your OS supports the notification backend. When `plyer` is missing the app will print notifications to console.

## Troubleshooting

- **MySQL connection errors:** verify host/port, credentials, and that the MySQL server accepts TCP connections. Also ensure the `pymysql` package is installed.
- ``** missing:** install the system package (e.g., `python3-tk` on Debian/Ubuntu).
- **OpenAI errors:** check `OPENAI_API_KEY` and network access. If you don't want OpenAI at all, simply remove or ignore the API key — the app still works with rule-based insights.
- **Permission issues writing **``** files:** the app uses a `data/` directory for local JSON storage. Make sure the user running the app has write permission in the project folder.

## Development notes / suggestions

- Move DB credentials into environment variables (or a `.env` file read by `python-dotenv`) instead of hardcoding in `database.py`.
- Consider adding a CLI or small REST API wrapper for headless usage.
- Add unit tests for analytics functions (`generate_weekly_report`, `get_weekly_data`) and the AI fallback logic.

## License

Add your preferred license (MIT, Apache-2.0, etc.) to the project root if you plan to share the code publicly.


