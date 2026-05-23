#!/usr/bin/env python3
"""
Quick test script to verify the scheduler system works.
Run this to test:
  python3 test_scheduler.py
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
project_dir = Path(__file__).parent
sys.path.insert(0, str(project_dir))

from bot.scheduler import TaskManager, validate_script, run_script


async def test_validator():
    """Test script validation."""
    print("=" * 50)
    print("Testing Script Validator")
    print("=" * 50)
    
    example_script = project_dir / "bot/scheduler/scripts/example.py"
    
    success, message = validate_script(str(example_script))
    print(f"Validating {example_script.name}:")
    print(f"  Result: {'✅ PASS' if success else '❌ FAIL'}")
    print(f"  Message: {message}\n")
    
    return success


async def test_runner():
    """Test script execution."""
    print("=" * 50)
    print("Testing Script Runner")
    print("=" * 50)
    
    example_script = project_dir / "bot/scheduler/scripts/example.py"
    
    success, result = await run_script(str(example_script))
    print(f"Executing {example_script.name}:")
    print(f"  Success: {success}")
    print(f"  Stdout: {result.get('stdout', '')[:100]}")
    print(f"  Output: {result.get('output')}\n")
    
    return success


async def test_manager():
    """Test task manager."""
    print("=" * 50)
    print("Testing Task Manager")
    print("=" * 50)
    
    # TaskManager expects the directory containing the 'scheduler' folder
    # Since scheduler is at bot/scheduler, we pass project_dir
    manager = TaskManager(project_dir / "bot")
    
    # Add a task
    success, msg = manager.add_task("example.py", 300, validate=True)
    print(f"Add task: {'✅' if success else '❌'} {msg}")
    
    # List tasks
    tasks = manager.list_tasks()
    print(f"Tasks in database: {len(tasks)}")
    for task in tasks:
        print(f"  - {task['script_name']} ({task['interval_seconds']}s)")
    
    # Check specific task
    info = manager.check_task("example.py")
    if "error" not in info:
        print(f"Task info: {info['script_name']} - {info['enabled']}\n")
    
    # Cleanup
    manager.remove_task("example.py")
    print("Task removed for cleanup\n")
    
    return True


async def main():
    """Run all tests."""
    print("\n🧪 Telegram Bot Scheduler - Test Suite\n")
    
    try:
        # Test 1: Validator
        validator_ok = await test_validator()
        
        # Test 2: Runner
        runner_ok = await test_runner()
        
        # Test 3: Manager
        manager_ok = await test_manager()
        
        # Summary
        print("=" * 50)
        print("Test Summary")
        print("=" * 50)
        print(f"Validator: {'✅ PASS' if validator_ok else '❌ FAIL'}")
        print(f"Runner:    {'✅ PASS' if runner_ok else '❌ FAIL'}")
        print(f"Manager:   {'✅ PASS' if manager_ok else '❌ FAIL'}")
        
        if all([validator_ok, runner_ok, manager_ok]):
            print("\n✅ All tests passed!")
            return 0
        else:
            print("\n❌ Some tests failed")
            return 1
    
    except Exception as e:
        print(f"\n❌ Error during tests: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
