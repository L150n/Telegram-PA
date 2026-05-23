"""Script runner for executing scheduled tasks asynchronously."""

import asyncio
import json
from typing import Tuple, Dict, Any
from pathlib import Path


async def run_script(script_path: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Execute a Python script asynchronously with timeout protection.
    
    Args:
        script_path: Path to the Python script to execute
        
    Returns:
        Tuple of (success: bool, output: dict)
        where output contains:
        - 'stdout': Script output
        - 'stderr': Error output
        - 'returncode': Exit code
        - 'error': Human-readable error message
    """
    script_file = Path(script_path)
    
    if not script_file.exists():
        return False, {"error": f"Script not found: {script_path}"}
    
    try:
        # Create subprocess
        proc = await asyncio.create_subprocess_exec(
            "python3",
            str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=30
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return False, {
                "error": "Script execution timeout (>30s)",
                "stdout": "",
                "stderr": ""
            }
        
        stdout_str = stdout.decode('utf-8', errors='replace')
        stderr_str = stderr.decode('utf-8', errors='replace')
        
        # Try to parse JSON output
        script_output = None
        if stdout_str:
            try:
                script_output = json.loads(stdout_str)
            except json.JSONDecodeError:
                pass
        
        return True, {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "returncode": proc.returncode,
            "output": script_output
        }
    
    except Exception as e:
        return False, {
            "error": f"Execution error: {str(e)}"
        }


async def run_script_with_logging(script_path: str, logger_func=None) -> Dict[str, Any]:
    """
    Execute a script and log the results.
    
    Args:
        script_path: Path to the Python script
        logger_func: Optional async function to call with results
        
    Returns:
        Dictionary with execution results
    """
    success, result = await run_script(script_path)
    
    result["success"] = success
    result["script"] = str(script_path)
    
    if logger_func:
        await logger_func(result)
    
    return result
