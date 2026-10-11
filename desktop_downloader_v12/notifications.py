from __future__ import annotations


def notify(title: str, message: str) -> None:
    from plyer import notification

    notification.notify(title=title, message=message, app_name="Smart Downloader 12.0")
