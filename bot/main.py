from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from pathlib import Path
import secrets
import shutil
import threading

from telegram import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonCommands,
    Update,
)
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.config import ADMIN_CHAT_IDS, APP_LOG_FILE, BOT_TOKEN
from bot.services.downloader import DownloadBatch, DownloaderError
from bot.services.instagram_service import (
    download_video as download_instagram_media,
    inspect_content as inspect_instagram_content,
)
from bot.services.youtube_service import (
    download_audio as download_youtube_audio,
    download_video as download_youtube_video,
    list_audio_qualities,
    list_video_qualities,
)
from bot.utils.activity_log import log_activity
from bot.utils.helpers import (
    build_admin_callback,
    build_user_callback,
    detect_platform,
    format_duration,
    is_valid_url,
    is_youtube_music_url,
    parse_admin_callback,
    parse_user_callback,
)


logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.ERROR,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(APP_LOG_FILE, encoding="utf-8"),
    ],
)
LOGGER = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("telegram").setLevel(logging.ERROR)
logging.getLogger("telegram.ext").setLevel(logging.ERROR)

SPINNER_FRAMES = [
    "[=      ]",
    "[==     ]",
    "[===    ]",
    "[ ====  ]",
    "[  ==== ]",
    "[   ====]",
    "[  ==== ]",
    "[ ====  ]",
]


@dataclass
class PendingSelection:
    url: str
    platform: str
    user_id: int
    username: str
    selected_mode: str | None = None
    source_kind: str | None = None
    source_summary: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ActiveDownload:
    task_id: str
    user_id: int
    username: str
    platform: str
    mode: str
    quality: str
    url: str
    status: str = "queued"
    progress_text: str = "Queued"
    progress_percent: float | None = None
    progress_message_id: int | None = None
    requested_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancel_event: threading.Event = field(default_factory=threading.Event)
    runner_task: asyncio.Task[None] | None = None


PENDING_DOWNLOADS: dict[str, PendingSelection] = {}
ACTIVE_DOWNLOADS: dict[str, ActiveDownload] = {}
ACTIVE_DOWNLOADS_LOCK = threading.Lock()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is None:
        return
    await update.message.reply_text(
        "Send a YouTube, YouTube Music, or public Instagram link.\n\n"
        "Commands:\n"
        "/start - welcome message\n"
        "/help - usage guide\n"
        "/processes - admin active downloads\n"
        "/todaylogs - admin summary"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is None:
        return
    await update.message.reply_text(_help_text())


async def today_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin access is required for this command.")
        return
    username_filter = context.args[0].strip().lstrip("@") if context.args else None
    await update.message.reply_text(_build_today_logs_text(username_filter))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is None or not update.message.text:
        return

    text = update.message.text.strip()
    user = update.effective_user
    username = user.username if user and user.username else "unknown"

    if not is_valid_url(text):
        await update.message.reply_text(_invalid_message_text())
        log_activity(
            "invalid_url",
            user_id=user.id if user else None,
            username=username,
            text=text,
        )
        return

    platform = detect_platform(text)
    if platform == "unknown":
        await update.message.reply_text(_invalid_message_text())
        log_activity(
            "unsupported_url",
            user_id=user.id if user else None,
            username=username,
            text=text,
        )
        return

    token = secrets.token_urlsafe(8)
    PENDING_DOWNLOADS[token] = PendingSelection(
        url=text,
        platform=platform,
        user_id=user.id if user else 0,
        username=username,
    )
    log_activity(
        "request_received",
        token=token,
        user_id=user.id if user else None,
        username=username,
        platform=platform,
        url=text,
    )

    if platform == "youtube":
        is_music = is_youtube_music_url(text)
        choice_row = [
            InlineKeyboardButton(
                "Audio",
                callback_data=build_user_callback("mode", token, "audio"),
            )
        ]
        if not is_music:
            choice_row.append(
                InlineKeyboardButton(
                    "Video",
                    callback_data=build_user_callback("mode", token, "video"),
                )
            )
        keyboard = InlineKeyboardMarkup(
            [
                choice_row,
                [
                    InlineKeyboardButton(
                        "Cancel",
                        callback_data=build_user_callback("cancel_pending", token, "request"),
                    )
                ],
            ]
        )
        await update.message.reply_text(
            "This is a YouTube Music link, so only audio download is available."
            if is_music
            else "Choose what you want from this YouTube link:",
            reply_markup=keyboard,
        )
        return

    try:
        instagram_info = await asyncio.to_thread(inspect_instagram_content, text)
        pending = PENDING_DOWNLOADS[token]
        pending.source_kind = str(instagram_info.get("type") or "media")
        pending.source_summary = _build_instagram_summary(instagram_info)
    except DownloaderError as exc:
        LOGGER.error("Instagram inspection failed for %s: %s", text, exc)
        pending = PENDING_DOWNLOADS[token]
        pending.source_kind = "media"
        pending.source_summary = "public Instagram media"
        log_activity(
            "instagram_inspect_failed",
            token=token,
            user_id=user.id if user else None,
            username=username,
            reason=str(exc),
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Download",
                    callback_data=build_user_callback("start_instagram", token, "media"),
                )
            ],
            [
                InlineKeyboardButton(
                    "Cancel",
                    callback_data=build_user_callback("cancel_pending", token, "request"),
                )
            ],
        ]
    )
    await update.message.reply_text(
        f"Instagram detected: {pending.source_summary}\n"
        "I will download the original available quality automatically.",
        reply_markup=keyboard,
    )


async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return

    try:
        action, token, value = parse_user_callback(query.data or "")
    except ValueError:
        await query.answer()
        await _safe_edit_message(query, "That action is no longer valid.")
        return

    pending = PENDING_DOWNLOADS.get(token)
    if pending is None:
        await query.answer()
        await _safe_edit_message(
            query,
            "This request expired. Please send the link again."
        )
        return

    if update.effective_user is None or update.effective_user.id != pending.user_id:
        await query.answer("This request belongs to another user.", show_alert=True)
        return

    await query.answer()

    if action == "cancel_pending":
        PENDING_DOWNLOADS.pop(token, None)
        await _safe_edit_message(query, "Request cancelled before download started.")
        log_activity(
            "pending_cancelled",
            token=token,
            user_id=pending.user_id,
            username=pending.username,
        )
        return

    if action == "start_instagram":
        await _start_download(query, context, token, "media", "original")
        return

    if action == "mode":
        pending.selected_mode = value
        try:
            await _show_quality_options(query, token, pending, value)
        except DownloaderError as exc:
            PENDING_DOWNLOADS.pop(token, None)
            await _safe_edit_message(query, _friendly_download_error(str(exc)))
            log_activity(
                "quality_lookup_failed",
                token=token,
                user_id=pending.user_id,
                username=pending.username,
                reason=str(exc),
            )
            return
        log_activity(
            "mode_selected",
            token=token,
            user_id=pending.user_id,
            username=pending.username,
            platform=pending.platform,
            mode=value,
        )
        return

    if action != "quality":
        await _safe_edit_message(query, "That action is no longer valid.")
        return

    try:
        mode, quality = value.split(":", 1)
    except ValueError:
        await _safe_edit_message(query, "That action is no longer valid.")
        return

    await _start_download(query, context, token, mode, quality)


async def _start_download(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    token: str,
    mode: str,
    quality: str,
) -> None:
    pending = PENDING_DOWNLOADS.pop(token, None)
    if pending is None:
        await _safe_edit_message(query, "This request expired. Please send the link again.")
        return

    task = _create_active_download(pending, mode, quality)
    status_message = await _safe_edit_message(
        query,
        _build_status_text(task),
        reply_markup=_build_user_cancel_keyboard(task.task_id),
    )
    if hasattr(status_message, "message_id"):
        task.progress_message_id = status_message.message_id
    log_activity(
        "download_started",
        task_id=task.task_id,
        token=token,
        user_id=task.user_id,
        username=task.username,
        platform=task.platform,
        mode=task.mode,
        quality=task.quality,
        url=task.url,
    )
    task.runner_task = asyncio.create_task(_run_download_flow(query, context, task))


async def _run_download_flow(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    task: ActiveDownload,
) -> None:
    loader_task = asyncio.create_task(_animate_progress_message(query, task.task_id))
    batch: DownloadBatch | None = None
    try:
        batch = await _download_media(task)
        _update_active_download(
            task.task_id,
            status="uploading",
            progress_text=f"Uploading {len(batch.files)} file(s)",
            progress_percent=100.0,
        )
        if task.cancel_event.is_set():
            raise DownloaderError("Download stopped by user.")
        await _send_files(query, context, task, batch)
        _update_active_download(
            task.task_id,
            status="completed",
            progress_text="Upload finished",
            progress_percent=100.0,
        )
        await _safe_edit_message(query, _build_success_message(task))
        log_activity(
            "download_completed",
            task_id=task.task_id,
            user_id=task.user_id,
            username=task.username,
            platform=task.platform,
            mode=task.mode,
            quality=task.quality,
            output_count=len(batch.files),
            duration_seconds=int((datetime.now(UTC) - task.requested_at).total_seconds()),
        )
    except asyncio.CancelledError:
        LOGGER.error("Download task cancelled for task %s", task.task_id)
        await _safe_edit_message(query, "Download cancelled.")
        log_activity(
            "download_cancelled",
            task_id=task.task_id,
            user_id=task.user_id,
            username=task.username,
            duration_seconds=int((datetime.now(UTC) - task.requested_at).total_seconds()),
        )
    except DownloaderError as exc:
        LOGGER.error("Download failed for task %s: %s", task.task_id, exc)
        message = _friendly_download_error(str(exc))
        await _safe_edit_message(query, message)
        log_activity(
            "download_failed",
            task_id=task.task_id,
            user_id=task.user_id,
            username=task.username,
            reason=str(exc),
            duration_seconds=int((datetime.now(UTC) - task.requested_at).total_seconds()),
        )
    except (BadRequest, TelegramError):
        LOGGER.exception("Telegram failed while sending the file.")
        await _safe_edit_message(
            query,
            "Download finished, but Telegram could not send the file. It may be too large.",
        )
        log_activity(
            "upload_failed",
            task_id=task.task_id,
            user_id=task.user_id,
            username=task.username,
            reason="telegram_upload_error",
            duration_seconds=int((datetime.now(UTC) - task.requested_at).total_seconds()),
        )
    finally:
        loader_task.cancel()
        await _safely_wait(loader_task)
        _remove_active_download(task.task_id)
        if batch is not None:
            _cleanup_download(batch.files[0])


async def processes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is None or update.effective_user is None:
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("Admin access is required for this command.")
        return
    await update.message.reply_text(
        _build_active_process_text(),
        reply_markup=_build_admin_keyboard(),
    )


async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    query = update.callback_query
    if query is None or query.message is None or update.effective_user is None:
        return
    if not _is_admin(update.effective_user.id):
        await query.answer("Admin access is required.", show_alert=True)
        return

    try:
        action, task_id = parse_admin_callback(query.data or "")
    except ValueError:
        await query.answer()
        await _safe_edit_message(query, "That admin action is no longer valid.")
        return

    await query.answer()

    if action == "stop":
        stopped = _request_stop(task_id)
        active_task = _get_active_download(task_id)
        await _safe_edit_message(
            query,
            _build_active_process_text(
                footer="Stop requested." if stopped else "Task already finished."
            ),
            reply_markup=_build_admin_keyboard(),
        )
        log_activity(
            "admin_stop_requested",
            admin_user_id=update.effective_user.id,
            task_id=task_id,
            stopped=stopped,
            duration_seconds=int((datetime.now(UTC) - active_task.requested_at).total_seconds()) if stopped and active_task is not None else None,
        )
        return

    if action == "refresh":
        await _safe_edit_message(
            query,
            _build_active_process_text(),
            reply_markup=_build_admin_keyboard(),
        )
        return

    await _safe_edit_message(query, "That admin action is no longer valid.")


async def handle_user_active_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    del context
    query = update.callback_query
    if query is None or query.message is None or update.effective_user is None:
        return
    try:
        action, task_id, value = parse_user_callback(query.data or "")
    except ValueError:
        await query.answer()
        await _safe_edit_message(query, "That action is no longer valid.")
        return

    if action != "cancel_active":
        await query.answer()
        await _safe_edit_message(query, "That action is no longer valid.")
        return

    task = _get_active_download(task_id)
    if task is None:
        await query.answer("This download is no longer active.", show_alert=True)
        return
    if task.user_id != update.effective_user.id:
        await query.answer("You can only stop your own download.", show_alert=True)
        return

    await query.answer("Stopping download...")
    task.cancel_event.set()
    if task.status in {"queued", "uploading"} and task.runner_task is not None:
        task.runner_task.cancel()
    _update_active_download(task_id, status="stopping", progress_text="Stop requested by user")
    await _safe_edit_message(
        query,
        _build_status_text(task),
        reply_markup=_build_user_cancel_keyboard(task.task_id),
    )
    log_activity(
        "user_stop_requested",
        user_id=update.effective_user.id,
        username=task.username,
        task_id=task_id,
        value=value,
        duration_seconds=int((datetime.now(UTC) - task.requested_at).total_seconds()),
    )


async def _download_media(task: ActiveDownload) -> DownloadBatch:
    def progress_callback(progress: dict) -> None:
        percent = _parse_percent(progress.get("_percent_str"))
        _update_active_download(
            task.task_id,
            status="downloading",
            progress_text=_format_progress(progress),
            progress_percent=percent,
        )

    if task.platform == "youtube" and task.mode == "audio":
        return await asyncio.to_thread(
            download_youtube_audio,
            task.url,
            task.quality,
            task.cancel_event,
            progress_callback,
        )
    if task.platform == "youtube" and task.mode == "video":
        return await asyncio.to_thread(
            download_youtube_video,
            task.url,
            task.quality,
            task.cancel_event,
            progress_callback,
        )
    if task.platform == "instagram" and task.mode == "media":
        return await asyncio.to_thread(
            download_instagram_media,
            task.url,
            task.quality,
            task.cancel_event,
            progress_callback,
        )
    raise DownloaderError("Unsupported platform or format selection.")


async def _send_files(
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    task: ActiveDownload,
    batch: DownloadBatch,
) -> None:
    if query.message is None:
        raise TelegramError("Callback message is unavailable.")
    chat_id = query.message.chat_id
    total_files = len(batch.files)

    for index, file_path in enumerate(batch.files, start=1):
        if task.cancel_event.is_set():
            raise DownloaderError("Download stopped by user.")
        _update_active_download(
            task.task_id,
            status="uploading",
            progress_text=f"Uploading file {index}/{total_files}",
            progress_percent=100.0,
        )
        caption = f"{batch.title or 'Download'} ({index}/{total_files})"
        with file_path.open("rb") as media:
            if file_path.suffix.lower() == ".mp3":
                await context.bot.send_audio(chat_id=chat_id, audio=media, caption=caption)
            else:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=media,
                    caption=caption,
                )


def _cleanup_download(file_path: Path) -> None:
    shutil.rmtree(file_path.parent, ignore_errors=True)


async def _show_quality_options(
    query: CallbackQuery, token: str, pending: PendingSelection, mode: str
) -> None:
    if mode == "audio":
        qualities = await asyncio.to_thread(list_audio_qualities, pending.url)
        prompt = "Choose audio quality:"
    else:
        qualities = await asyncio.to_thread(list_video_qualities, pending.url)
        prompt = "Choose video quality from the available stream list:"

    keyboard = []
    row: list[InlineKeyboardButton] = []
    for quality, label in qualities:
        row.append(
            InlineKeyboardButton(
                label,
                callback_data=build_user_callback("quality", token, f"{mode}:{quality}"),
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(
        [
            InlineKeyboardButton(
                "Cancel",
                callback_data=build_user_callback("cancel_pending", token, "request"),
            )
        ]
    )
    await _safe_edit_message(query, prompt, reply_markup=InlineKeyboardMarkup(keyboard))


async def _animate_progress_message(query: CallbackQuery, task_id: str) -> None:
    frame_index = 0
    while True:
        task = _get_active_download(task_id)
        if task is None:
            return
        if task.cancel_event.is_set() and task.status == "uploading":
            task.progress_text = "Stop requested. Upload may finish if Telegram already accepted it."
        await _safe_edit_message(
            query,
            _build_status_text(task, spinner=SPINNER_FRAMES[frame_index % len(SPINNER_FRAMES)]),
            reply_markup=None if task.status == "completed" else _build_user_cancel_keyboard(task.task_id),
        )
        frame_index += 1
        await asyncio.sleep(1.2)


async def _safe_edit_message(
    query: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> object | None:
    try:
        return await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    return None


async def _safely_wait(task: asyncio.Task[None]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return


def _friendly_download_error(raw_error: str) -> str:
    lowered = raw_error.lower()
    if "ffmpeg" in lowered:
        return "Audio conversion needs FFmpeg installed on the host."
    if "there is no video in this post" in lowered:
        return "This Instagram post is not a video. The bot now treats Instagram links as general media."
    if "inspection timed out" in lowered:
        return "Instagram preview lookup timed out, but you can still try downloading the post."
    if "download timed out" in lowered:
        return "Instagram download timed out. Please try again in a moment."
    if "redirect to login page" in lowered or "accounts/login" in lowered:
        return (
            "Instagram asked for login. Configure Instagram cookies for the bot "
            "to access this post."
        )
    if "download stopped." in lowered:
        return "Download cancelled."
    if "stopped by user" in lowered:
        return "Download cancelled."
    if "private" in lowered or "login" in lowered:
        return "That media is not publicly accessible, so I cannot download it in v1."
    return "Download failed for that link. Please try another URL."


def _create_active_download(
    pending: PendingSelection, mode: str, quality: str
) -> ActiveDownload:
    task = ActiveDownload(
        task_id=secrets.token_hex(4),
        user_id=pending.user_id,
        username=pending.username,
        platform=pending.platform,
        mode=mode,
        quality=quality,
        url=pending.url,
    )
    with ACTIVE_DOWNLOADS_LOCK:
        ACTIVE_DOWNLOADS[task.task_id] = task
    return task


def _get_active_download(task_id: str) -> ActiveDownload | None:
    with ACTIVE_DOWNLOADS_LOCK:
        return ACTIVE_DOWNLOADS.get(task_id)


def _update_active_download(task_id: str, **changes: str) -> None:
    with ACTIVE_DOWNLOADS_LOCK:
        task = ACTIVE_DOWNLOADS.get(task_id)
        if task is None:
            return
        for key, value in changes.items():
            setattr(task, key, value)


def _remove_active_download(task_id: str) -> None:
    with ACTIVE_DOWNLOADS_LOCK:
        ACTIVE_DOWNLOADS.pop(task_id, None)


def _request_stop(task_id: str) -> bool:
    with ACTIVE_DOWNLOADS_LOCK:
        task = ACTIVE_DOWNLOADS.get(task_id)
        if task is None:
            return False
        task.cancel_event.set()
        if task.status in {"queued", "uploading"} and task.runner_task is not None:
            task.runner_task.cancel()
        task.status = "stopping"
        task.progress_text = "Stop requested"
        return True


def _build_active_process_text(footer: str | None = None) -> str:
    with ACTIVE_DOWNLOADS_LOCK:
        tasks = list(ACTIVE_DOWNLOADS.values())
    if not tasks:
        text = "No active downloads."
    else:
        lines = ["Active downloads:"]
        for task in tasks:
            elapsed = format_duration((datetime.now(UTC) - task.requested_at).total_seconds())
            lines.append(
                f"{task.task_id} | {task.username} | {task.platform} | "
                f"{task.mode}/{task.quality} | {task.status} | {elapsed} | {task.progress_text}"
            )
        text = "\n".join(lines)
    if footer:
        text = f"{text}\n\n{footer}"
    return text


def _build_today_logs_text(username_filter: str | None = None) -> str:
    import json
    from collections import defaultdict

    today = datetime.now(UTC).date()
    stats: dict[str, dict[str, int | str]] = defaultdict(
        lambda: {
            "requests": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "last_event": "-",
            "last_duration": "-",
        }
    )

    activity_path = APP_LOG_FILE.parent / "activity.jsonl"
    if not activity_path.exists():
        return "No activity log file found for today."

    with activity_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                timestamp = datetime.fromisoformat(record["timestamp"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if timestamp.date() != today:
                continue
            username = str(record.get("username") or f"user_{record.get('user_id', 'unknown')}")
            if username_filter and username_filter.lower() not in username.lower():
                continue
            event = str(record.get("event", "unknown"))
            row = stats[username]
            row["last_event"] = event
            if record.get("duration_seconds") is not None:
                row["last_duration"] = format_duration(float(record["duration_seconds"]))
            if event == "request_received":
                row["requests"] += 1
            elif event == "download_completed":
                row["completed"] += 1
            elif event in {"download_failed", "upload_failed", "quality_lookup_failed"}:
                row["failed"] += 1
            elif event in {
                "pending_cancelled",
                "user_stop_requested",
                "admin_stop_requested",
                "download_cancelled",
            }:
                row["cancelled"] += 1

    if not stats:
        return "No matching user activity found for today."

    lines = ["Today's user activity:"]
    for username, row in sorted(stats.items()):
        lines.append(
            f"{username} | requests={row['requests']} | completed={row['completed']} | "
            f"failed={row['failed']} | cancelled={row['cancelled']} | "
            f"last={row['last_event']} | duration={row['last_duration']}"
        )
    return "\n".join(lines)


def _build_admin_keyboard() -> InlineKeyboardMarkup | None:
    with ACTIVE_DOWNLOADS_LOCK:
        tasks = list(ACTIVE_DOWNLOADS.values())
    if not tasks:
        return None
    buttons = [
        [InlineKeyboardButton(f"Stop {task.task_id}", callback_data=build_admin_callback("stop", task.task_id))]
        for task in tasks
    ]
    buttons.append([InlineKeyboardButton("Refresh", callback_data=build_admin_callback("refresh", "all"))])
    return InlineKeyboardMarkup(buttons)


def _format_progress(progress: dict) -> str:
    status = progress.get("status")
    if status == "finished":
        return "Processing final file"
    if status != "downloading":
        return str(status or "Starting")
    percent = progress.get("_percent_str", "").strip()
    speed = progress.get("_speed_str", "").strip()
    eta = progress.get("_eta_str", "").strip()
    parts = [part for part in [percent, speed, eta and f"ETA {eta}"] if part]
    return " | ".join(parts) if parts else "Downloading"


def _parse_percent(percent_text: object) -> float | None:
    if not isinstance(percent_text, str):
        return None
    cleaned = percent_text.strip().replace("%", "")
    try:
        return max(0.0, min(100.0, float(cleaned)))
    except ValueError:
        return None


def _build_success_message(task: ActiveDownload) -> str:
    duration = format_duration((datetime.now(UTC) - task.requested_at).total_seconds())
    return (
        "Upload completed successfully.\n"
        f"Platform: {task.platform}\n"
        f"Mode: {task.mode}\n"
        f"Quality: {task.quality}\n"
        f"Started: {task.requested_at.astimezone().strftime('%H:%M:%S')}\n"
        f"Duration: {duration}\n"
        "Local temporary file cleaned up."
    )


def _build_status_text(task: ActiveDownload, spinner: str = "•") -> str:
    started = task.requested_at.astimezone().strftime("%H:%M:%S")
    elapsed = format_duration((datetime.now(UTC) - task.requested_at).total_seconds())
    quality_label = "Original / highest available" if task.platform == "instagram" else task.quality
    phase = {
        "queued": "Preparing",
        "downloading": "Downloading",
        "uploading": "Uploading",
        "stopping": "Cancelling",
        "completed": "Completed",
    }.get(task.status, task.status.title())
    progress_bar = _render_progress_bar(task.progress_percent)
    return (
        f"{spinner} {phase}\n"
        f"Platform: {task.platform}\n"
        f"Mode: {task.mode}\n"
        f"Quality: {quality_label}\n"
        f"Started: {started}\n"
        f"Elapsed: {elapsed}\n"
        f"Status: {task.status}\n"
        f"Progress Bar: {progress_bar}\n"
        f"Progress: {task.progress_text}"
    )


def _render_progress_bar(percent: float | None) -> str:
    if percent is None:
        return "[..........]"
    filled = max(0, min(10, int(round(percent / 10))))
    return "[" + "#" * filled + "." * (10 - filled) + f"] {percent:.1f}%"


def _build_instagram_summary(info: dict[str, object]) -> str:
    media_type = str(info.get("type") or "media")
    item_count = int(info.get("item_count") or 1)
    image_count = int(info.get("image_count") or 0)
    video_count = int(info.get("video_count") or 0)
    if media_type == "carousel":
        return (
            f"carousel with {item_count} slides "
            f"({image_count} image(s), {video_count} video(s))"
        )
    if media_type == "image":
        return "single image post"
    return "video or reel post"


def _build_user_cancel_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Cancel Download",
                    callback_data=build_user_callback("cancel_active", task_id, "stop"),
                )
            ]
        ]
    )


def _help_text() -> str:
    return (
        "Send a single supported link and I will guide you.\n\n"
        "Supported:\n"
        "- YouTube / YouTube Music\n"
        "- Public Instagram photo, video, reel, and carousel links\n\n"
        "Commands:\n"
        "/start - welcome message\n"
        "/help - show help\n"
        "/processes - admin active downloads\n"
        "/todaylogs - admin summary of today's user activity\n\n"
        "Tips:\n"
        "- You can cancel before download starts.\n"
        "- You can also cancel your own active download from the progress message."
    )


def _invalid_message_text() -> str:
    return (
        "I could not understand that message.\n\n"
        "Please send one valid YouTube, YouTube Music, or public Instagram photo/video/carousel link.\n\n"
        "Commands:\n"
        "/start\n"
        "/help"
    )


async def _set_bot_metadata(application: Application) -> None:
    await application.bot.set_my_description(
        "Personal assistant bot for YouTube audio/video and public Instagram photo, video, and carousel downloads."
    )
    await application.bot.set_my_short_description(
        "Download media from YouTube and Instagram."
    )
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Show welcome message"),
            BotCommand("help", "Show usage instructions"),
            BotCommand("processes", "Admin: view active downloads"),
            BotCommand("todaylogs", "Admin: show today's user activity"),
        ]
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def _handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Unhandled bot error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "Something went wrong while processing that request. Please try again."
            )
        except TelegramError:
            LOGGER.error("Failed to send error message to user.")


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_CHAT_IDS


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).post_init(_set_bot_metadata).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("processes", processes))
    application.add_handler(CommandHandler("todaylogs", today_logs))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_user_active_action, pattern=r"^u\|cancel_active\|"))
    application.add_handler(CallbackQueryHandler(handle_selection, pattern=r"^u\|"))
    application.add_handler(CallbackQueryHandler(handle_admin_action, pattern=r"^a\|"))
    application.add_error_handler(_handle_error)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
