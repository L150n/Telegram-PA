#!/bin/bash
# Integration Verification Checklist
# Run this to verify the scheduler implementation

echo "🔍 Telegram Bot Task Scheduler - Verification Checklist"
echo "======================================================"
echo ""

# Check 1: Dependencies installed
echo "1️⃣  Checking dependencies..."
if $PYTHON -c "import apscheduler" 2>/dev/null; then
    echo "   ✅ apscheduler installed"
else
    echo "   ❌ apscheduler NOT installed"
    echo "   💡 Run: source myenv/bin/activate && pip install apscheduler"
fi

# Check 2: Module files exist
echo ""
echo "2️⃣  Checking scheduler module files..."
files=(
    "bot/scheduler/__init__.py"
    "bot/scheduler/manager.py"
    "bot/scheduler/runner.py"
    "bot/scheduler/validator.py"
    "bot/scheduler/scripts/__init__.py"
    "bot/scheduler/scripts/example.py"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file"
    else
        echo "   ❌ $file MISSING"
    fi
done

# Check 3: Config updated
echo ""
echo "3️⃣  Checking configuration..."
if grep -q "SCHEDULER_DIR" bot/config.py; then
    echo "   ✅ SCHEDULER_DIR in config.py"
else
    echo "   ❌ SCHEDULER_DIR NOT in config.py"
fi

# Check 4: Main.py integration
echo ""
echo "4️⃣  Checking main.py integration..."
checks=(
    "from bot.scheduler import TaskManager"
    "async def task_command"
    "CommandHandler(\"task\", task_command)"
)

for check in "${checks[@]}"; do
    if grep -q "$check" bot/main.py; then
        echo "   ✅ Found: $check"
    else
        echo "   ❌ Missing: $check"
    fi
done

# Check 5: Requirements updated
echo ""
echo "5️⃣  Checking requirements.txt..."
if grep -q "apscheduler" requirements.txt; then
    echo "   ✅ apscheduler in requirements.txt"
else
    echo "   ❌ apscheduler NOT in requirements.txt"
fi

# Check 6: Module imports
echo ""
echo "6️⃣  Checking module imports..."
if $PYTHON -c "from bot.scheduler import TaskManager; from bot import main" 2>/dev/null; then
    echo "   ✅ All modules import successfully"
else
    echo "   ❌ Module import failed"
fi

# Check 7: Test suite
echo ""
echo "7️⃣  Checking test suite..."
if [ -f "test_scheduler.py" ]; then
    echo "   ✅ test_scheduler.py exists"
    echo "   💡 Run: python3 test_scheduler.py"
else
    echo "   ❌ test_scheduler.py MISSING"
fi

# Check 8: Documentation
echo ""
echo "8️⃣  Checking documentation..."
docs=(
    "docs/scheduler/SCHEDULER_GUIDE.md"
    "docs/scheduler/SCHEDULER_QUICKSTART.md"
    "docs/agent-tracking/IMPLEMENTATION.md"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        echo "   ✅ $doc"
    else
        echo "   ❌ $doc MISSING"
    fi
done

# Summary
echo ""
echo "======================================================"
echo "✅ Verification Complete!"
echo ""
echo "📖 Next Steps:"
echo "   1. Read docs/scheduler/SCHEDULER_QUICKSTART.md for quick start"
echo "   2. Run: python3 test_scheduler.py"
echo "   3. Create scripts in bot/scheduler/scripts/"
echo "   4. Use /task commands in Telegram bot"
echo ""
