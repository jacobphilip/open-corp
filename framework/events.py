"""Event system — TinyDB-backed log with in-memory pub/sub."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tinydb import Query

from framework.db import get_db
from framework.log import get_logger

logger = get_logger(__name__)


@dataclass
class Event:
    type: str       # e.g. "task.completed", "workflow.started"
    source: str     # e.g. "scheduler:abc123", "workflow:my-pipeline"
    data: dict = field(default_factory=dict)
    timestamp: str = ""  # auto-filled if empty


class EventLog:
    """Persistent event log with pub/sub dispatch."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._db, self._db_lock = get_db(self.db_path)
        self._handlers: dict[str, list[Callable]] = {}

    def emit(self, event: Event) -> None:
        """Persist an event and dispatch to registered handlers."""
        if not event.timestamp:
            event.timestamp = datetime.now(timezone.utc).isoformat()

        record = {
            "type": event.type,
            "source": event.source,
            "data": event.data,
            "timestamp": event.timestamp,
        }
        with self._db_lock:
            self._db.insert(record)

        # Dispatch to type-specific handlers
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception:
                logger.warning("Event handler exception swallowed: event=%s, handler=%s",
                               event.type, getattr(handler, "__name__", repr(handler)))

        # Dispatch to wildcard handlers
        for handler in self._handlers.get("*", []):
            try:
                handler(event)
            except Exception:
                logger.warning("Event handler exception swallowed: event=%s, handler=%s",
                               event.type, getattr(handler, "__name__", repr(handler)))

    def on(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type. Use '*' for all events."""
        self._handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def query(self, event_type: str | None = None, source: str | None = None,
              limit: int = 50) -> list[dict]:
        """Query events, newest first. Supports type and source filters."""
        Q = Query()
        conditions = []
        if event_type:
            conditions.append(Q.type == event_type)
        if source:
            conditions.append(Q.source == source)

        with self._db_lock:
            if conditions:
                combined = conditions[0]
                for c in conditions[1:]:
                    combined = combined & c
                results = self._db.search(combined)
            else:
                results = self._db.all()

        # Sort newest first by timestamp
        results.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return results[:limit]

    def clear(self) -> None:
        """Remove all events (for testing)."""
        with self._db_lock:
            self._db.truncate()
