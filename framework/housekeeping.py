"""Housekeeping — data retention policies for events, spending, workflows, performance."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tinydb import Query

from framework.config import RetentionConfig
from framework.db import get_db
from framework.log import get_logger

logger = get_logger(__name__)


class Housekeeper:
    """Enforces data retention policies across project data stores."""

    def __init__(self, project_dir: Path, retention: RetentionConfig | None = None):
        self.project_dir = project_dir
        self.retention = retention or RetentionConfig()
        self.data_dir = project_dir / "data"

    def run_all(self) -> dict[str, int]:
        """Run all retention policies. Returns {store: records_removed}."""
        results = {
            "events": self.clean_events(),
            "spending": self.clean_spending(),
            "workflows": self.clean_workflows(),
            "performance": self.clean_performance(),
        }
        total = sum(results.values())
        logger.info("Housekeeping complete: %d records removed (%s)", total, results)
        return results

    def clean_events(self) -> int:
        """Remove events older than retention.events_days."""
        db_path = self.data_dir / "events.json"
        if not db_path.exists():
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention.events_days)).isoformat()
        db, lock = get_db(db_path)
        Q = Query()
        with lock:
            removed = db.remove(Q.timestamp.test(lambda ts: ts < cutoff))
        return len(removed)

    def clean_spending(self) -> int:
        """Remove spending records older than retention.spending_days."""
        db_path = self.data_dir / "spending.json"
        if not db_path.exists():
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention.spending_days)).strftime("%Y-%m-%d")
        db, lock = get_db(db_path)
        table = db.table("spending")
        Q = Query()
        with lock:
            removed = table.remove(Q.date.test(lambda d: d < cutoff))
        return len(removed)

    def clean_workflows(self) -> int:
        """Remove workflow runs older than retention.workflows_days."""
        db_path = self.data_dir / "workflows.json"
        if not db_path.exists():
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention.workflows_days)).isoformat()
        db, lock = get_db(db_path)
        Q = Query()
        with lock:
            removed = db.remove(Q.started_at.test(lambda ts: ts < cutoff))
        return len(removed)

    def clean_performance(self) -> int:
        """Trim each worker's performance.json to retention.performance_max. Keeps newest."""
        workers_dir = self.project_dir / "workers"
        if not workers_dir.exists():
            return 0

        total_removed = 0
        for worker_dir in sorted(workers_dir.iterdir()):
            if not worker_dir.is_dir() or worker_dir.name.startswith("."):
                continue
            perf_path = worker_dir / "performance.json"
            if not perf_path.exists():
                continue
            try:
                records = json.loads(perf_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            if len(records) <= self.retention.performance_max:
                continue

            excess = len(records) - self.retention.performance_max
            # Keep newest entries (end of list)
            trimmed = records[excess:]
            perf_path.write_text(json.dumps(trimmed, indent=2))
            total_removed += excess

        return total_removed
