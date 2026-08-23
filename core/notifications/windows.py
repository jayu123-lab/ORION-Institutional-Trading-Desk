"""Best-effort Windows notification adapter; never blocks trading intelligence."""

from __future__ import annotations

import logging
import subprocess
from shutil import which

logger = logging.getLogger("orion.notifications")


def notify_windows(title: str, message: str) -> bool:
    """Send a toast through PowerShell when available, without executing orders."""
    if which("powershell.exe") is None:
        return False
    escaped_title = title.replace("'", "''")[:120]
    escaped_message = message.replace("'", "''")[:500]
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
        "ContentType = WindowsRuntime];"
        "$xml=[Windows.Data.Xml.Dom.XmlDocument]::new();"
        f'$xml.LoadXml(\'<toast><visual><binding template="ToastText02">'
        f"<text>{escaped_title}</text><text>{escaped_message}</text>"
        "</binding></visual></toast>');"
        "$toast=[Windows.UI.Notifications.ToastNotification]::new($xml);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('ORION').Show($toast)"
    )
    try:
        completed = subprocess.run(  # noqa: S603
            [
                which("powershell.exe") or "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        logger.exception("Windows notification failed")
        return False
