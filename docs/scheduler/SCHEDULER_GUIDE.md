# Task Scheduler Implementation

This document describes the task scheduler system added to the Telegram bot.

## Overview

The scheduler allows admins to schedule Python scripts to run at regular intervals. Scripts must output JSON format and are validated before execution.

## Architecture

```
Telegram Bot (existing)
├── Downloader
├── Assistant  
└── Scheduler (NEW)
    ├── SQLite DB (tasks.db)
    ├── Manager (manager.py)
    ├── Runner (runner.py)
    ├── Validator (validator.py)
    └── Scripts Folder (scripts/)
```

## Directory Structure

```
bot/
├── scheduler/
│   ├── __init__.py
│   ├── manager.py      - Task lifecycle management
│   ├── runner.py       - Async script execution
│   ├── validator.py    - Script validation
│   ├── tasks.db        - SQLite database (auto-created)
│   └── scripts/
│       ├── __init__.py
│       └── example.py  - Example task script
└── main.py             - Integrated scheduler commands
```

## Admin Commands

### /task add <script_name> <interval_seconds>
Add and schedule a Python script to run at regular intervals.

```
/task add example.py 300
```

- Minimum interval: 30 seconds
- Script is validated before adding
- Stored in SQLite database

### /task remove <script_name>
Remove a scheduled task.

```
/task remove example.py
```

### /task pause <script_name>
Pause a task (can be resumed later).

```
/task pause example.py
```

### /task resume <script_name>
Resume a paused task.

```
/task resume example.py
```

### /task check <script_name>
Get detailed information about a specific task.

```
/task check example.py
```

Response includes:
- Interval (seconds)
- Status (Enabled/Paused)
- Created timestamp
- Last run time
- Last execution result

### /task install <library_name>
Install Python libraries required by scripts.

```
/task install requests
```

### /tasks or /task list
List all scheduled tasks with their status.

```
/tasks
```

## Script Format

All scripts **must output valid JSON** to stdout:

```python
import json

result = {
    "success": True,
    "message": "Task completed successfully"
}

print(json.dumps(result))
```

### Example: Check API and Alert

```python
import json
import requests

try:
    response = requests.get("https://api.example.com/status")
    data = response.json()
    
    if data.get("status") == "error":
        print(json.dumps({
            "success": False,
            "message": f"API Error: {data.get('message')}"
        }))
    else:
        print(json.dumps({
            "success": True,
            "message": f"API Status: {data.get('status')}"
        }))
except Exception as e:
    print(json.dumps({
        "success": False,
        "message": f"Exception: {str(e)}"
    }))
```

## Validation

Scripts are validated in three stages:

1. **Syntax Check**: Compile Python code
2. **Import Check**: Verify all imports are available
3. **Dry Run**: Execute script with 20-second timeout to verify JSON output

Failed validation prevents task scheduling.

## Execution

When scheduled:

1. Script runs asynchronously with 30-second timeout
2. Output is captured and parsed as JSON
3. Result logged to database
4. Admin receives Telegram notification
5. Status stored (success/failed)

## Database Schema

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_name TEXT UNIQUE NOT NULL,
    interval_seconds INTEGER NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_run TIMESTAMP,
    last_status TEXT
);
```

## Resource Usage

Component | RAM (approx)
----------|-------------
Bot       | ~80 MB
Scheduler | ~10 MB
Script runtime | ~30 MB per execution
SQLite DB | <1 MB

## Safety Features

- **Admin Only**: Only users in `ADMIN_CHAT_IDS` can manage tasks
- **Minimum Interval**: 30 seconds minimum to prevent system overload
- **Timeouts**: Scripts have 30-second execution limit
- **Validation**: Scripts validated before scheduling
- **Database**: Persistent task storage with SQLite
- **No Sandbox**: Scripts run in same environment (use trusted scripts only)

## Integration

The scheduler integrates with the existing bot:

- Started on bot initialization
- Stopped on bot shutdown
- Lives in same process (no separate services)
- Notifications sent via Telegram
- Admin-only access control

## Dependencies

- `apscheduler` - Task scheduling
- `python-telegram-bot` - Already required
- `sqlite3` - Built-in

## Files Modified

- `bot/config.py` - Added `SCHEDULER_DIR`
- `bot/main.py` - Added scheduler commands and lifecycle management
- `requirements.txt` - Added `apscheduler`

## Files Created

- `bot/scheduler/__init__.py`
- `bot/scheduler/manager.py`
- `bot/scheduler/runner.py`
- `bot/scheduler/validator.py`
- `bot/scheduler/scripts/__init__.py`
- `bot/scheduler/scripts/example.py`

## Usage Examples

### Add a monitoring script

```
/task add monitor_api.py 300
✅ Task 'monitor_api.py' scheduled every 300s
```

### View all tasks

```
/tasks
📋 All Scheduled Tasks:
✅ monitor_api.py - Every 300s - Last run: 2026-05-23 14:30:45
✅ check_db.py - Every 600s - Last run: Never
```

### Install required library

```
/task install requests
⏳ Installing requests...
✅ Library 'requests' installed successfully
```

### Pause a task

```
/task pause monitor_api.py
✅ Task 'monitor_api.py' paused
```

### Check task details

```
/task check monitor_api.py
📋 Task: monitor_api.py
Interval: 300s
Status: Enabled
Created: 2026-05-23 10:00:00
Last Run: 2026-05-23 14:30:45
Last Result: success
```

## Future Enhancements

- Cron expression support
- Auto-remove on success
- Retry logic
- Enhanced logging
- Script lifecycle hooks
- Task dependencies
- Performance metrics

## Troubleshooting

**Script not running:**
- Check if task is enabled (`/task check <name>`)
- Verify script syntax with `/task add` (validates automatically)
- Check logs in `logs/bot.log`

**"Script not found" error:**
- Ensure script file is in `bot/scheduler/scripts/`
- Use filename exactly as it appears in the folder

**Import errors during validation:**
- Install required libraries: `/task install <library>`
- Check library names are correct

**Timeout errors:**
- Increase timeouts in `runner.py` (default 30s)
- Optimize script performance
- Break into multiple tasks

## Notifications

When a task executes, admins receive notifications:

```
✅ Task: `example.py`
Result: Random value 75 exceeded threshold
```

Or on failure:

```
❌ Task: `monitor_api.py`
Error: Connection timeout
```
