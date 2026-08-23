"""Small, dependency-free helpers for the Windows ORION launcher."""

from __future__ import annotations

import shutil
import socket
import sys
import urllib.request


def healthy(url: str = "http://127.0.0.1:8000/health", timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return 200 <= response.status < 300
    except (OSError, ValueError):
        return False


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def browser_command(url: str) -> list[str] | None:
    for browser in ("msedge.exe", "chrome.exe", "msedge", "chrome"):
        executable = shutil.which(browser)
        if executable:
            return [executable, f"--app={url}", "--new-window"]
    return None


if __name__ == "__main__":
    command = browser_command(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3000/command")
    print(" ".join(command) if command else "NO_BROWSER_FOUND")
