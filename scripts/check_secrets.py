#!/usr/bin/env python3
"""Secret scanner: fails (exit 1) if tracked files contain credential-like strings.

Used by CI and recommended as a local pre-commit hook. Patterns are tuned to
catch common API keys, private keys and seed phrases while avoiding false
positives on .env.example placeholders.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{22,}")),
    ("private_key_block", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "seed_phrase",
        re.compile(
            r"\b(abandon|squirrel|defense)[ \w]{20,}\b(ability|about)[\s\S]{0,200}", re.IGNORECASE
        ),
    ),
    (
        "api_key_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?secret|client[_-]?secret)\b\s*[:=]\s*['\"]?[A-Za-z0-9+/_-]{24,}"
        ),
    ),
    ("bearer_token_literal", re.compile(r"(?i)bearer\s+[a-z0-9._-]{30,}")),
    ("hex_private_key", re.compile(r"\b0x[a-fA-F0-9]{64}\b")),
]

ALLOWED_FILES = {".env.example"}
ALLOWED_DIRS = {"tests", ".venv", "node_modules"}

PLACEHOLDER_HINTS = re.compile(r"(<|\$\{|your[-_]|example|changeme|xxx|dummy)", re.IGNORECASE)


def git_tracked_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    return [Path(f) for f in result.stdout.splitlines() if f]


def scan() -> int:
    findings = 0
    for path in git_tracked_files():
        spath = str(path)
        if spath in ALLOWED_FILES:
            continue
        if any(spath.startswith(d) for d in ALLOWED_DIRS):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in PATTERNS:
            for match in pattern.finditer(content):
                snippet = match.group(0)[:40]
                if PLACEHOLDER_HINTS.search(snippet):
                    continue
                line_no = content[: match.start()].count("\n") + 1
                print(f"[SECRETS] {spath}:{line_no} pattern={name}")
                findings += 1
    if findings:
        print(f"\n{findings} potential secret(s) found. Remove them and rotate credentials.")
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    sys.exit(scan())
