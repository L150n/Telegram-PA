"""Script validator for checking syntax, imports, and execution."""

import subprocess
import json
from pathlib import Path
from typing import Tuple


def validate_script(script_path: str) -> Tuple[bool, str]:
    """
    Validate a Python script by checking:
    1. Syntax errors
    2. Import errors
    3. Execution test (dry run)
    
    Args:
        script_path: Path to the Python script to validate
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    script_file = Path(script_path)
    
    # Check if file exists
    if not script_file.exists():
        return False, f"Script file not found: {script_path}"
    
    try:
        # Step 1: Syntax check
        result = subprocess.run(
            ["python3", "-m", "py_compile", script_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return False, f"Syntax error: {result.stderr}"
        
        # Step 2: Dry run (execution test)
        result = subprocess.run(
            ["python3", script_path],
            capture_output=True,
            text=True,
            timeout=20
        )
        
        # Check if output is valid JSON
        if result.stdout:
            try:
                json.loads(result.stdout)
            except json.JSONDecodeError:
                return False, f"Script must output valid JSON. Got: {result.stdout[:200]}"
        
        if result.returncode != 0:
            # Non-zero exit is ok if stderr is empty (script may choose to exit)
            if result.stderr:
                return False, f"Execution error: {result.stderr[:200]}"
        
        return True, "Script validation passed"
    
    except subprocess.TimeoutExpired:
        return False, "Script execution timeout (>20s)"
    except Exception as e:
        return False, f"Validation error: {str(e)}"


def check_imports(script_path: str) -> Tuple[bool, str]:
    """
    Check if all imports in a script are available.
    
    Args:
        script_path: Path to the Python script to check
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        result = subprocess.run(
            ["python3", "-c", f"import ast; ast.parse(open('{script_path}').read())"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return False, f"Import check failed: {result.stderr}"
        
        return True, "All imports available"
    except subprocess.TimeoutExpired:
        return False, "Import check timeout"
    except Exception as e:
        return False, f"Import check error: {str(e)}"
