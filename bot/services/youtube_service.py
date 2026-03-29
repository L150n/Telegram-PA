import threading

from bot.services.downloader import (
    DownloadBatch,
    download,
    get_youtube_audio_qualities,
    get_youtube_video_qualities,
)


def download_audio(
    url: str,
    quality: str,
    cancel_event: threading.Event | None = None,
    progress_callback=None,
) -> DownloadBatch:
    return download(url, "audio", "youtube", quality, cancel_event, progress_callback)


def download_video(
    url: str,
    quality: str,
    cancel_event: threading.Event | None = None,
    progress_callback=None,
) -> DownloadBatch:
    return download(url, "video", "youtube", quality, cancel_event, progress_callback)


def list_audio_qualities(url: str) -> list[tuple[str, str]]:
    return get_youtube_audio_qualities(url)


def list_video_qualities(url: str) -> list[tuple[str, str]]:
    return get_youtube_video_qualities(url)
