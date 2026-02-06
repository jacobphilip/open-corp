"""Logging configuration — stdlib logging with project-aware defaults."""

import logging
import re
import sys
from pathlib import Path

# Patterns that look like secrets
_SECRET_PATTERNS = [
    re.compile(r"sk-or-[a-zA-Z0-9_-]{20,}"),           # OpenRouter API keys
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),               # Generic API keys
    re.compile(r"Bearer\s+[a-zA-Z0-9_.-]{10,}"),        # Bearer tokens
    re.compile(r"(?:API_KEY|SECRET|TOKEN|PASSWORD)\s*=\s*\S+", re.IGNORECASE),  # Env var assignments
]


class SecretFilter(logging.Filter):
    """Logging filter that redacts API keys and secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in _SECRET_PATTERNS:
                record.msg = pattern.sub("***REDACTED***", record.msg)
        # Also handle %-formatted args
        if record.args:
            args = record.args if isinstance(record.args, tuple) else (record.args,)
            new_args = []
            for arg in args:
                if isinstance(arg, str):
                    for pattern in _SECRET_PATTERNS:
                        arg = pattern.sub("***REDACTED***", arg)
                new_args.append(arg)
            record.args = tuple(new_args)
        return True


def setup_logging(level: str = "INFO", log_file: Path | None = None,
                  redact_secrets: bool = True) -> logging.Logger:
    """Configure the root open-corp logger. Returns configured logger."""
    logger = logging.getLogger("open-corp")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not logger.handlers:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(str(log_file))
            fh.setFormatter(formatter)
            logger.addHandler(fh)

    # Add secret filter (idempotent — check if already added)
    if redact_secrets and not any(isinstance(f, SecretFilter) for f in logger.filters):
        logger.addFilter(SecretFilter())

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """Get a child logger. Usage: logger = get_logger(__name__)"""
    return logging.getLogger(f"open-corp.{module_name}")
