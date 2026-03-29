import threading

from bot.services.downloader import DownloadBatch, download, inspect_instagram_content


def download_video(
    url: str,
    quality: str,
    cancel_event: threading.Event | None = None,
    progress_callback=None,
) -> DownloadBatch:
    return download(url, "video", "instagram", quality, cancel_event, progress_callback)


def inspect_content(url: str) -> dict[str, object]:
    return inspect_instagram_content(url)
