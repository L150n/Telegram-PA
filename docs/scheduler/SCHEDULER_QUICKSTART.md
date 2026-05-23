# Task Scheduler Implementation - Quick Start

## ✅ Implementation Complete

The Telegram bot now has a fully integrated task scheduler system for running Python scripts at regular intervals.

## 📁 What Was Added

### New Files Created
```
bot/scheduler/
├── __init__.py                    # Module exports
├── manager.py                     # Task lifecycle & APScheduler integration
├── runner.py                      # Async script execution with timeouts
├── validator.py                   # Script syntax/import/execution validation
├── scripts/
│   ├── __init__.py
│   └── example.py                 # Example task script (outputs JSON)
└── tasks.db                       # SQLite database (auto-created)

test_scheduler.py                   # Test suite (optional)
SCHEDULER_GUIDE.md                  # Comprehensive documentation
```

### Files Modified
```
requirements.txt                    # Added: apscheduler
bot/config.py                       # Added: SCHEDULER_DIR path
bot/main.py                         # Added: scheduler integration & commands
```

## 🚀 Quick Start

### 1. Install Dependencies
```bash
cd /home/zoro/playground/Telegram-PA
source myenv/bin/activate
pip3 install apscheduler
```

Or update all requirements:
```bash
pip3 install -r requirements.txt
```

### 2. Create Your First Task Script

Create a file in `bot/scheduler/scripts/my_task.py`:

```python
import json
import requests

try:
    response = requests.get("https://api.example.com/status")
    data = response.json()
    
    print(json.dumps({
        "success": True,
        "message": f"API Status: {data['status']}"
    }))
except Exception as e:
    print(json.dumps({
        "success": False,
        "message": f"Error: {str(e)}"
    }))
```

**Important**: All scripts must output valid JSON to stdout!

### 3. Schedule It

Send to bot (as admin):
```
/task add my_task.py 300
```

This runs `my_task.py` every 300 seconds (5 minutes).

### 4. Manage Tasks

```
/tasks                    # List all tasks
/task check my_task.py    # View task details
/task pause my_task.py    # Pause (can resume later)
/task resume my_task.py   # Resume paused task
/task remove my_task.py   # Delete task
/task install requests    # Install libraries needed
```

## 📋 Admin Commands

| Command | Description |
|---------|-------------|
| `/task add <script> <interval>` | Schedule a script |
| `/task remove <script>` | Remove task |
| `/task pause <script>` | Pause task |
| `/task resume <script>` | Resume task |
| `/task check <script>` | View details |
| `/task install <library>` | Install Python package |
| `/tasks` | List all tasks |

## 🔒 Security & Limits

- **Admin Only**: Only users in `ADMIN_CHAT_IDS` can manage tasks
- **Minimum Interval**: 30 seconds (prevents system overload)
- **Max Execution**: 30 seconds per script (prevents hangs)
- **Validation**: Scripts checked before scheduling
- **No Sandbox**: Scripts trusted (verify before adding!)

## 💾 How It Works

1. **Storage**: Tasks saved in SQLite database (`bot/scheduler/tasks.db`)
2. **Scheduling**: APScheduler runs tasks at intervals
3. **Execution**: Async subprocess with timeouts
4. **Notifications**: Admins get Telegram updates on completion
5. **Persistence**: Tasks auto-load on bot restart

## 📊 Database Schema

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

## 📝 Script Format

All scripts must follow this pattern:

```python
import json

# Your code here
result = {
    "success": True,  # or False
    "message": "Human-readable result"
}

print(json.dumps(result))
```

## 🧪 Testing

Run the test suite:
```bash
python3 test_scheduler.py
```

Output:
```
✅ All tests passed!
  - Validator: ✅ PASS
  - Runner:    ✅ PASS
  - Manager:   ✅ PASS
```

## 📈 Resource Usage

| Component | RAM |
|-----------|-----|
| Bot | ~80 MB |
| Scheduler | ~10 MB |
| Per script execution | ~30 MB |
| SQLite database | <1 MB |

**Total**: Fits comfortably on 1GB VPS

## 🔧 Architecture

```
Application (main.py)
    │
    ├── TaskManager (manager.py)
    │   ├── APScheduler (task scheduling)
    │   ├── SQLite (persistence)
    │   ├── Validator (pre-flight checks)
    │   └── Runner (execution)
    │
    └── Bot Commands
        ├── /task add|remove|pause|resume|check|install
        └── /tasks
```

## 📚 Documentation

- [SCHEDULER_GUIDE.md](./SCHEDULER_GUIDE.md) - Full documentation
- [bot/scheduler/manager.py](./bot/scheduler/manager.py) - Task management
- [bot/scheduler/runner.py](./bot/scheduler/runner.py) - Script execution
- [bot/scheduler/validator.py](./bot/scheduler/validator.py) - Validation logic

## ❓ FAQ

**Q: How do I add a task?**
A: `/task add script_name.py 300` (runs every 300 seconds)

**Q: What if my script fails?**
A: Check logs in `logs/bot.log` or use `/task check <name>`

**Q: Can I change interval after scheduling?**
A: Remove and re-add with new interval

**Q: How do I see task output?**
A: Admins get Telegram notifications on each execution

**Q: What if script needs packages?**
A: Use `/task install package_name` to install

**Q: How do I test my script?**
A: Run manually: `python3 bot/scheduler/scripts/my_task.py`

## 🎯 Next Steps

1. **Test**: Run `python3 test_scheduler.py`
2. **Create**: Add your first task script in `bot/scheduler/scripts/`
3. **Schedule**: Use `/task add` command
4. **Monitor**: Check with `/tasks` and `/task check`

## 🐛 Troubleshooting

**Script not running:**
- Verify it's in `bot/scheduler/scripts/`
- Test manually: `python3 bot/scheduler/scripts/my_script.py`
- Check logs: `tail logs/bot.log`

**"Script not found" error:**
- Use exact filename from `bot/scheduler/scripts/`
- Don't include path, just filename: `my_script.py`

**Import errors:**
- Install missing libraries: `/task install requests`
- Check module names (case-sensitive)

**Timeout errors:**
- Optimize script (make it faster)
- Increase timeout in `runner.py` if needed
- Break into multiple smaller tasks

---

**Status**: ✅ Production Ready
**Last Updated**: 2026-05-23
**Minimum VPS**: 1GB RAM
