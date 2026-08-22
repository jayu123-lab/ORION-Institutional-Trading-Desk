"""Logging setup with secret redaction. Never log credentials."""

import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(api[_-]?secret\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(authorization\s*:\s*bearer\s+)\S+", re.IGNORECASE),
    re.compile(r"(token\s*[=:]\s*)\S+", re.IGNORECASE),
    re.compile(r"(passphrase\s*[=:]\s*)\S+", re.IGNORECASE),
]


class SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pat in _SECRET_PATTERNS:
            msg = pat.sub(lambda m: m.group(1) + "[REDACTED]", msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactingFilter())
    fmt = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%SZ"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    try:
        root.setLevel(getattr(logging, level.upper()))
    except AttributeError:
        root.setLevel(logging.INFO)
