from __future__ import annotations

import json
from datetime import UTC, datetime

from bot.config import ACTIVITY_LOG_FILE


def log_activity(event: str, **details: object) -> None:
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **details,
    }
    with ACTIVITY_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
