"""Thread-safe TinyDB wrapper — singleton per file path."""

import threading
from pathlib import Path

from tinydb import TinyDB

_registry: dict[str, tuple[TinyDB, threading.Lock]] = {}
_registry_lock = threading.Lock()


def get_db(db_path: Path) -> tuple[TinyDB, threading.Lock]:
    """Get or create a (TinyDB, Lock) pair. One instance per resolved path."""
    path_str = str(Path(db_path).resolve())
    with _registry_lock:
        if path_str not in _registry:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            _registry[path_str] = (TinyDB(path_str), threading.Lock())
        return _registry[path_str]


def close_all() -> None:
    """Close all TinyDB instances and clear registry."""
    with _registry_lock:
        for db, _ in _registry.values():
            db.close()
        _registry.clear()


def _reset_registry() -> None:
    """For testing only — clear without closing."""
    with _registry_lock:
        _registry.clear()
