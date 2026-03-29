from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
LOG_DIR = BASE_DIR / "logs"

load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_IDS = {
    int(chat_id.strip())
    for chat_id in os.getenv("ADMIN_CHAT_IDS", "").split(",")
    if chat_id.strip()
}
INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "").strip()
INSTAGRAM_COOKIES_FROM_BROWSER = os.getenv("INSTAGRAM_COOKIES_FROM_BROWSER", "").strip()
APP_LOG_FILE = LOG_DIR / "bot.log"
ACTIVITY_LOG_FILE = LOG_DIR / "activity.jsonl"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from the environment.")

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
