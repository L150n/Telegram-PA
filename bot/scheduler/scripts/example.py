"""
Example scheduled task script.

All scripts must output JSON to stdout with structure:
{
    "success": true/false,
    "message": "Human-readable result"
}
"""

import json
import random
from datetime import datetime


def main():
    """Example task that checks a random condition."""
    
    # Your logic here
    random_value = random.randint(1, 100)
    
    # Simulate checking a condition
    if random_value > 50:
        result = {
            "success": True,
            "message": f"Random value {random_value} exceeded threshold"
        }
    else:
        result = {
            "success": False,
            "message": f"Random value {random_value} below threshold"
        }
    
    # IMPORTANT: Always output JSON
    print(json.dumps(result))


if __name__ == "__main__":
    main()
