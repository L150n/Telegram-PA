"""Task manager for scheduling and managing background tasks."""

import asyncio
import sqlite3
import json
import subprocess
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Optional, Callable, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .runner import run_script
from .validator import validate_script


class TaskManager:
    """Manages scheduled tasks with SQLite persistence."""
    
    def __init__(self, base_dir: Path, bot_send_message: Optional[Callable] = None):
        """
        Initialize the TaskManager.
        
        Args:
            base_dir: Base directory for scheduler files
            bot_send_message: Optional async function to send Telegram messages
        """
        self.base_dir = Path(base_dir)
        self.scheduler_dir = self.base_dir / "scheduler"
        self.db_path = self.scheduler_dir / "tasks.db"
        self.scripts_dir = self.scheduler_dir / "scripts"
        
        self.scheduler_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        
        self.scheduler = AsyncIOScheduler()
        self.bot_send_message = bot_send_message
        
        self._init_db()
        self._load_tasks()
    
    def _init_db(self):
        """Initialize SQLite database schema."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_name TEXT UNIQUE NOT NULL,
                interval_seconds INTEGER,
                cron_expression TEXT,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run TIMESTAMP,
                last_status TEXT
            )
        """)
        # Backward-compatible migration for older schema.
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(tasks)").fetchall()}
        if "cron_expression" not in columns:
            cursor.execute("ALTER TABLE tasks ADD COLUMN cron_expression TEXT")
        
        conn.commit()
        conn.close()
    
    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
    
    def _get_script_path(self, script_name: str) -> Path:
        """Get full path to a script."""
        # Ensure script_name doesn't contain path traversal
        script_name = Path(script_name).name
        return self.scripts_dir / script_name
    
    def add_task(self, script_name: str, cron_expression: str, validate: bool = True) -> tuple[bool, str]:
        """
        Add a new scheduled task.
        
        Args:
            script_name: Name of the script file (relative to scripts folder)
            cron_expression: Cron expression (6 fields: sec min hour day month day_of_week)
            validate: Whether to validate the script before adding
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        script_path = self._get_script_path(script_name)
        
        # Check if script exists
        if not script_path.exists():
            return False, f"Script not found: {script_name}"
        
        cron_valid, cron_message = self._validate_cron_expression(cron_expression)
        if not cron_valid:
            return False, cron_message
        
        validation_message = ""
        # Validate script if requested
        if validate:
            success, message = validate_script(str(script_path))
            if not success:
                return False, f"Validation failed: {message}"
            validation_message = f" Validation: {message}."
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO tasks (script_name, interval_seconds, cron_expression, enabled)
                VALUES (?, NULL, ?, 1)
            """, (script_name, cron_expression))
            
            conn.commit()
            conn.close()
            
            # Schedule the task
            self._schedule_task(script_name, cron_expression=cron_expression, interval_seconds=None)
            
            return True, (
                f"Task '{script_name}' scheduled with cron '{cron_expression}'."
                f"{validation_message} Confirmation: task added successfully."
            )
        
        except Exception as e:
            return False, f"Database error: {str(e)}"
    
    def remove_task(self, script_name: str) -> tuple[bool, str]:
        """Remove a scheduled task."""
        try:
            # Remove from scheduler
            if self.scheduler.get_job(script_name):
                self.scheduler.remove_job(script_name)
            
            # Remove from database
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE script_name = ?", (script_name,))
            conn.commit()
            conn.close()
            
            return True, f"Task '{script_name}' removed"
        
        except Exception as e:
            return False, f"Error removing task: {str(e)}"
    
    def pause_task(self, script_name: str) -> tuple[bool, str]:
        """Pause a scheduled task."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET enabled = 0 WHERE script_name = ?", (script_name,))
            conn.commit()
            conn.close()
            
            if self.scheduler.get_job(script_name):
                self.scheduler.pause_job(script_name)
            
            return True, f"Task '{script_name}' paused"
        
        except Exception as e:
            return False, f"Error pausing task: {str(e)}"
    
    def resume_task(self, script_name: str) -> tuple[bool, str]:
        """Resume a paused task."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET enabled = 1 WHERE script_name = ?", (script_name,))
            conn.commit()
            conn.close()
            
            if self.scheduler.get_job(script_name):
                self.scheduler.resume_job(script_name)
            
            return True, f"Task '{script_name}' resumed"
        
        except Exception as e:
            return False, f"Error resuming task: {str(e)}"
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        """Get list of all tasks."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT script_name, interval_seconds, cron_expression, enabled, created_at, last_run, last_status
                FROM tasks
                ORDER BY created_at DESC
            """)
            
            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "script_name": row[0],
                    "interval_seconds": row[1],
                    "cron_expression": row[2],
                    "enabled": bool(row[3]),
                    "created_at": row[4],
                    "last_run": row[5],
                    "last_status": row[6]
                })
            
            conn.close()
            return tasks
        
        except Exception as e:
            return []
    
    def install_library(self, lib_name: str) -> tuple[bool, str]:
        """Install a Python library via pip."""
        try:
            result = subprocess.run(
                ["pip3", "install", lib_name],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return False, f"Installation failed: {result.stderr[:200]}"
            
            return True, f"Library '{lib_name}' installed successfully"
        
        except subprocess.TimeoutExpired:
            return False, f"Installation timeout for {lib_name}"
        except Exception as e:
            return False, f"Installation error: {str(e)}"
    
    def _schedule_task(
        self,
        script_name: str,
        cron_expression: Optional[str],
        interval_seconds: Optional[int],
    ):
        """Add a task to the scheduler."""
        script_path = self._get_script_path(script_name)
        
        # Remove existing job if present
        if self.scheduler.get_job(script_name):
            self.scheduler.remove_job(script_name)
        
        # Add new job
        trigger = None
        if cron_expression:
            fields = cron_expression.strip().split()
            trigger = CronTrigger(
                second=fields[0],
                minute=fields[1],
                hour=fields[2],
                day=fields[3],
                month=fields[4],
                day_of_week=fields[5],
            )
        elif interval_seconds:
            trigger = IntervalTrigger(seconds=interval_seconds)
        else:
            raise ValueError(f"Task '{script_name}' has no valid schedule configuration")

        self.scheduler.add_job(
            self._run_scheduled_task,
            trigger,
            args=[script_name, str(script_path)],
            id=script_name,
            replace_existing=True
        )
    
    async def _run_scheduled_task(self, script_name: str, script_path: str):
        """Execute a scheduled task and log results."""
        try:
            success, result = await run_script(script_path)
            
            # Update database with execution status
            timestamp = datetime.now(UTC).isoformat()
            status = "success" if success else "failed"
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks 
                SET last_run = ?, last_status = ?
                WHERE script_name = ?
            """, (timestamp, status, script_name))
            conn.commit()
            conn.close()
            
            # Send Telegram notification
            if self.bot_send_message:
                message = await self._format_notification(script_name, success, result)
                await self.bot_send_message(message)
        
        except Exception as e:
            # Log but don't crash
            if self.bot_send_message:
                await self.bot_send_message(f"⚠️ Task '{script_name}' error: {str(e)[:100]}")
    
    async def _format_notification(self, script_name: str, success: bool, result: Dict) -> str:
        """Format a notification message."""
        status_emoji = "✅" if success else "❌"
        
        message = f"{status_emoji} Task: `{script_name}`\n"
        
        if success:
            if result.get("output"):
                output_msg = result["output"].get("message", "Executed")
                message += f"Result: {output_msg}\n"
            if result.get("stderr"):
                message += f"Stderr: {result['stderr'][:100]}\n"
        else:
            message += f"Error: {result.get('error', 'Unknown error')}\n"
        
        return message
    
    def _load_tasks(self):
        """Load all tasks from database on startup."""
        if self.scheduler.running:
            return
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT script_name, cron_expression, interval_seconds, enabled
                FROM tasks
            """)
            
            for row in cursor.fetchall():
                script_name, cron_expression, interval_seconds, enabled = row
                if enabled:
                    self._schedule_task(
                        script_name,
                        cron_expression=cron_expression,
                        interval_seconds=interval_seconds,
                    )
            
            conn.close()
        except Exception as e:
            print(f"Error loading tasks: {e}")
    
    def check_task(self, script_name: str) -> Dict[str, Any]:
        """Get detailed information about a task."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT script_name, interval_seconds, cron_expression, enabled, created_at, last_run, last_status
                FROM tasks
                WHERE script_name = ?
            """, (script_name,))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return {"error": f"Task '{script_name}' not found"}
            
            return {
                "script_name": row[0],
                "interval_seconds": row[1],
                "cron_expression": row[2],
                "enabled": bool(row[3]),
                "created_at": row[4],
                "last_run": row[5],
                "last_status": row[6]
            }
        
        except Exception as e:
            return {"error": f"Error checking task: {str(e)}"}

    def _validate_cron_expression(self, cron_expression: str) -> tuple[bool, str]:
        """Validate 6-field cron expression and return clear error messages."""
        fields = cron_expression.strip().split()
        if len(fields) != 6:
            return (
                False,
                "Cron must have 6 fields: second minute hour day month day_of_week "
                "(example: '0 */5 * * * *').",
            )
        try:
            CronTrigger(
                second=fields[0],
                minute=fields[1],
                hour=fields[2],
                day=fields[3],
                month=fields[4],
                day_of_week=fields[5],
            )
        except Exception as e:
            return False, f"Invalid cron expression: {e}"
        return True, "Cron expression valid"
