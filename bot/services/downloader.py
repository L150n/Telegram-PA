from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Callable

from yt_dlp import DownloadError, YoutubeDL
from yt_dlp.utils import PostProcessingError

from bot.config import (
    DOWNLOAD_DIR,
    INSTAGRAM_COOKIES_FILE,
    INSTAGRAM_COOKIES_FROM_BROWSER,
)


class DownloaderError(RuntimeError):
    """Raised when a media download cannot be completed."""


class DownloadCancelled(RuntimeError):
    """Raised when a download is stopped before completion."""


ProgressCallback = Callable[[dict], None]


@dataclass
class DownloadBatch:
    files: list[Path]
    title: str | None = None


def _extract_info(url: str) -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise DownloaderError(str(exc)) from exc
    except Exception as exc:
        raise DownloaderError("Could not inspect media details.") from exc
    return info


def inspect_instagram_content(url: str) -> dict[str, object]:
    entries = _gallery_dl_metadata(url)
    image_count = 0
    video_count = 0

    for entry in entries:
        ext = _entry_extension(entry)
        if ext in {"jpg", "jpeg", "png", "webp"}:
            image_count += 1
        else:
            video_count += 1

    if len(entries) > 1:
        media_type = "carousel"
    elif video_count:
        media_type = "video"
    else:
        media_type = "image"

    return {
        "type": media_type,
        "image_count": image_count,
        "video_count": video_count,
        "item_count": len(entries),
        "title": str(entries[0].get("filename") or "") if entries else None,
    }


def _gallery_dl_metadata(url: str) -> list[dict]:
    _ensure_gallery_dl()
    command = [sys.executable, "-m", "gallery_dl", "--dump-json", "--simulate", "-q"]
    command.extend(_gallery_dl_auth_args())
    command.append(url)
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip() or "Instagram inspection failed."
        raise DownloaderError(message) from exc
    except subprocess.TimeoutExpired as exc:
        raise DownloaderError("Instagram inspection timed out.") from exc

    entries: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)

    if not entries:
        raise DownloaderError("Instagram media details could not be extracted.")
    return entries


def _entry_extension(entry: dict) -> str:
    extension = str(entry.get("extension") or entry.get("ext") or "").lower()
    if extension:
        return extension
    filename = str(entry.get("filename") or "")
    if "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return ""


def _ensure_gallery_dl() -> None:
    if importlib.util.find_spec("gallery_dl") is None:
        raise DownloaderError(
            "Instagram image support needs gallery-dl installed. Run pip install -r requirements.txt."
        )


def get_youtube_audio_qualities(url: str) -> list[tuple[str, str]]:
    del url
    return [
        ("128", "128 kbps"),
        ("192", "192 kbps"),
        ("best", "Best audio"),
    ]


def get_youtube_video_qualities(url: str) -> list[tuple[str, str]]:
    info = _extract_info(url)
    formats = info.get("formats") or []
    heights: set[int] = set()

    for item in formats:
        height = item.get("height")
        if not isinstance(height, int):
            continue
        if height < 144:
            continue
        if item.get("vcodec") == "none":
            continue
        heights.add(height)

    ordered_heights = sorted(heights)
    qualities = [(str(height), f"{height}p") for height in ordered_heights]
    if not qualities:
        qualities = [("auto", "Default stream")]
    return qualities


def _build_audio_format(quality: str) -> str:
    return "bestaudio/best"


def _build_video_format(quality: str) -> str:
    if quality.isdigit():
        max_height = quality
        return (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"
        )
    return (
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo+bestaudio/best[ext=mp4]/best"
    )


def _build_options(
    output_dir: Path,
    platform: str,
    mode: str,
    quality: str,
    cancel_event: threading.Event | None,
    progress_callback: ProgressCallback | None,
) -> dict:
    def progress_hook(progress: dict) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled("Download stopped.")
        if progress_callback is not None:
            progress_callback(progress)

    options = {
        "outtmpl": str(output_dir / "%(title).120s.%(ext)s"),
        "restrictfilenames": False,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
    }

    if mode == "audio":
        options.update(
            {
                "format": _build_audio_format(quality),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192" if quality == "best" else quality,
                    }
                ],
            }
        )
    elif platform == "youtube":
        options["merge_output_format"] = "mp4"
        options["format"] = _build_video_format(quality)
    elif platform == "instagram":
        options["format"] = "best"

    return options


def _collect_output_files(output_dir: Path) -> list[Path]:
    files = [path for path in output_dir.iterdir() if path.is_file()]
    if not files:
        raise DownloaderError("No output file was produced.")
    files.sort(key=lambda path: (path.stat().st_mtime, path.name))
    return files


def download(
    url: str,
    mode: str,
    platform: str,
    quality: str,
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DownloadBatch:
    request_dir = DOWNLOAD_DIR / f"{platform}_{mode}_{uuid.uuid4().hex}"
    request_dir.mkdir(parents=True, exist_ok=True)

    try:
        if platform == "instagram":
            return _download_instagram_media(
                url,
                request_dir,
                cancel_event,
                progress_callback,
            )
        with YoutubeDL(
            _build_options(
                request_dir,
                platform,
                mode,
                quality,
                cancel_event,
                progress_callback,
            )
        ) as ydl:
            info = ydl.extract_info(url, download=True)
        return DownloadBatch(
            files=_collect_output_files(request_dir),
            title=str(info.get("title") or "") or None,
        )
    except DownloadCancelled as exc:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloaderError(str(exc)) from exc
    except PostProcessingError as exc:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloaderError(
            "Audio conversion failed. Please make sure FFmpeg is installed."
        ) from exc
    except DownloadError as exc:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloaderError(str(exc)) from exc
    except DownloaderError as exc:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloaderError(str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise DownloaderError(f"Unexpected download failure: {exc}") from exc


def _download_instagram_media(
    url: str,
    output_dir: Path,
    cancel_event: threading.Event | None,
    progress_callback: ProgressCallback | None,
) -> DownloadBatch:
    _ensure_gallery_dl()
    command = [sys.executable, "-m", "gallery_dl", "-q", "-D", str(output_dir)]
    command.extend(_gallery_dl_auth_args())
    command.append(url)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise DownloadCancelled("Download stopped.")
            return_code = process.poll()
            if return_code is not None:
                break
            if progress_callback is not None:
                progress_callback({"status": "downloading", "_percent_str": "50%"})
            time.sleep(0.4)

        stdout, stderr = process.communicate(timeout=10)
        if return_code != 0:
            message = (stderr or stdout or "").strip() or "Instagram download failed."
            raise DownloaderError(message)

        files = _collect_output_files(output_dir)
        if progress_callback is not None:
            progress_callback({"status": "finished"})
        title = files[0].stem if files else None
        return DownloadBatch(files=files, title=title)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise DownloaderError("Instagram download timed out.") from exc
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def _gallery_dl_auth_args() -> list[str]:
    args: list[str] = []
    if INSTAGRAM_COOKIES_FILE:
        args.extend(["--cookies", INSTAGRAM_COOKIES_FILE])
    if INSTAGRAM_COOKIES_FROM_BROWSER:
        args.extend(["--cookies-from-browser", INSTAGRAM_COOKIES_FROM_BROWSER])
    return args
