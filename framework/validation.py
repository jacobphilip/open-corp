"""Input validation — worker names, paths, payloads, rate limiting, safe JSON I/O."""

import json
import re
import tempfile
import threading
import time
import warnings
from pathlib import Path

from framework.exceptions import ValidationError
from framework.log import get_logger

logger = get_logger(__name__)

# Worker name: alphanumeric start, then alphanumeric/underscore/hyphen, 1-64 chars
_WORKER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def validate_worker_name(name: str) -> str:
    """Validate a worker name. Returns the name if valid, raises ValidationError otherwise."""
    if not name or not isinstance(name, str):
        raise ValidationError(
            "Worker name must be a non-empty string.",
            suggestion="Use only letters, numbers, hyphens, and underscores.",
        )
    if not _WORKER_NAME_RE.match(name):
        raise ValidationError(
            f"Invalid worker name '{name}'. Must match [a-zA-Z0-9][a-zA-Z0-9_-]{{0,63}}.",
            suggestion="Use only letters, numbers, hyphens, and underscores (1-64 chars, start with alphanumeric).",
        )
    return name


def validate_path_within(path: Path, root: Path) -> Path:
    """Validate that a resolved path is within the root directory.

    Returns the resolved path. Raises ValidationError if it escapes root.
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not str(resolved).startswith(str(root_resolved) + "/"):
        raise ValidationError(
            f"Path '{path}' resolves outside project directory.",
            suggestion="Use a relative path within the project.",
        )
    return resolved


def validate_payload_size(data: bytes | str, max_bytes: int = 1_048_576) -> None:
    """Validate that payload size is within limit. Raises ValidationError if too large."""
    size = len(data) if isinstance(data, bytes) else len(data.encode("utf-8", errors="replace"))
    if size > max_bytes:
        raise ValidationError(
            f"Payload too large: {size} bytes (max {max_bytes}).",
            suggestion="Reduce the payload size.",
        )


class RateLimiter:
    """In-process token bucket rate limiter, keyed by string (e.g. IP address).

    Thread-safe. Each key gets its own bucket with `rate` tokens/sec and `burst` capacity.
    """

    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self._buckets: dict[str, list] = {}  # key -> [tokens, last_refill_time]
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Check if a request from `key` is allowed. Returns True if allowed."""
        now = time.monotonic()
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = [self.burst - 1, now]
                return True

            tokens, last = self._buckets[key]
            elapsed = now - last
            tokens = min(self.burst, tokens + elapsed * self.rate)
            self._buckets[key][1] = now

            if tokens >= 1:
                self._buckets[key][0] = tokens - 1
                return True
            else:
                self._buckets[key][0] = tokens
                return False

    def cleanup(self, max_age: float = 3600.0) -> int:
        """Evict entries older than max_age seconds. Returns count evicted."""
        now = time.monotonic()
        with self._lock:
            stale = [k for k, (_, last) in self._buckets.items() if now - last > max_age]
            for k in stale:
                del self._buckets[k]
            return len(stale)


def safe_load_json(path: Path, default=None, warn: bool = True):
    """Load JSON from path with corruption detection.

    If the file is missing, returns default (or [] if default is None).
    If the file is corrupted, backs it up as .corrupt and returns default.
    """
    if default is None:
        default = []

    if not path.exists():
        return default

    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return default
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # Back up corrupted file
        corrupt_path = path.with_suffix(path.suffix + ".corrupt")
        try:
            path.rename(corrupt_path)
        except OSError:
            pass
        if warn:
            msg = f"Corrupted JSON at {path}: {e}. Backed up to {corrupt_path.name}."
            logger.warning(msg)
            warnings.warn(msg, stacklevel=2)
        return default
    except OSError:
        return default


def safe_write_json(path: Path, data) -> None:
    """Write JSON atomically: write to tempfile, then rename.

    Uses POSIX Path.replace for atomic rename within same filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2)

    # Write to temp file in same directory (same filesystem for atomic rename)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
