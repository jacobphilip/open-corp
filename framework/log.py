"""Logging configuration — stdlib logging with project-aware defaults."""

import logging
import sys
from pathlib import Path


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
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

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """Get a child logger. Usage: logger = get_logger(__name__)"""
    return logging.getLogger(f"open-corp.{module_name}")
