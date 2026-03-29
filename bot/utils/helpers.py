from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse


Platform = Literal["youtube", "instagram", "unknown"]
Mode = Literal["audio", "video"]
Quality = str

_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._ -]+")


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def detect_platform(url: str) -> Platform:
    if not is_valid_url(url):
        return "unknown"

    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host in {"youtube.com", "youtu.be", "music.youtube.com"}:
        return "youtube"
    if host.endswith("instagram.com"):
        return "instagram"
    return "unknown"


def is_youtube_music_url(url: str) -> bool:
    if not is_valid_url(url):
        return False
    host = urlparse(url).netloc.lower()
    return host == "music.youtube.com" or host == "www.music.youtube.com"


def sanitize_filename(name: str) -> str:
    cleaned = _FILENAME_PATTERN.sub("", name).strip().strip(".")
    return cleaned or "download"


def build_user_callback(action: str, token: str, value: str) -> str:
    return f"u|{action}|{token}|{value}"


def parse_user_callback(payload: str) -> tuple[str, str, str]:
    parts = payload.split("|", 3)
    if len(parts) != 4 or parts[0] != "u":
        raise ValueError("Invalid callback payload.")
    _, action, token, value = parts
    return action, token, value


def build_admin_callback(action: str, task_id: str) -> str:
    return f"a|{action}|{task_id}"


def parse_admin_callback(payload: str) -> tuple[str, str]:
    parts = payload.split("|", 2)
    if len(parts) != 3 or parts[0] != "a":
        raise ValueError("Invalid admin callback payload.")
    _, action, task_id = parts
    return action, task_id


def format_duration(seconds: float) -> str:
    total_seconds = max(int(seconds), 0)
    minutes, seconds_value = divmod(total_seconds, 60)
    hours, minutes_value = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes_value:02d}:{seconds_value:02d}"
    return f"{minutes_value:02d}:{seconds_value:02d}"
