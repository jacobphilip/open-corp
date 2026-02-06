"""Scheduler — APScheduler wrapper with TinyDB task persistence."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tinydb import Query

from framework.db import get_db

from framework.config import ProjectConfig
from framework.events import Event, EventLog
from framework.exceptions import SchedulerError, WorkerNotFound
from framework.router import Router
from framework.worker import Worker


VALID_SCHEDULE_TYPES = ("cron", "interval", "once")


@dataclass
class ScheduledTask:
    id: str = ""
    worker_name: str = ""
    message: str = ""
    schedule_type: str = ""   # "cron" | "interval" | "once"
    schedule_value: str = ""  # cron expr | seconds | ISO datetime
    enabled: bool = True
    description: str = ""
    created_at: str = ""


class Scheduler:
    """Manages scheduled tasks with APScheduler and TinyDB persistence."""

    def __init__(self, config: ProjectConfig, accountant, router: Router,
                 event_log: EventLog, db_path: Path | None = None):
        self.config = config
        self.accountant = accountant
        self.router = router
        self.event_log = event_log
        self.db_path = db_path or config.project_dir / "data" / "scheduler.json"
        self._db, self._db_lock = get_db(self.db_path)
        self._scheduler = None

    def _get_scheduler(self):
        """Lazy-init APScheduler (import deferred to avoid hard dependency)."""
        if self._scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler()
        return self._scheduler

    def add_task(self, task: ScheduledTask) -> ScheduledTask:
        """Add a scheduled task. Validates type and worker existence."""
        if task.schedule_type not in VALID_SCHEDULE_TYPES:
            raise SchedulerError(
                task.id or "new",
                f"Invalid schedule_type '{task.schedule_type}'. Must be one of: {VALID_SCHEDULE_TYPES}",
            )

        # Validate worker exists
        worker_dir = self.config.project_dir / "workers" / task.worker_name
        if not worker_dir.exists():
            raise SchedulerError(
                task.id or "new",
                f"Worker '{task.worker_name}' not found",
                suggestion="Run 'corp workers' to see available workers.",
            )

        if not task.id:
            task.id = uuid.uuid4().hex[:8]
        if not task.created_at:
            task.created_at = datetime.now(timezone.utc).isoformat()

        with self._db_lock:
            self._db.insert({
                "id": task.id,
                "worker_name": task.worker_name,
                "message": task.message,
                "schedule_type": task.schedule_type,
                "schedule_value": task.schedule_value,
                "enabled": task.enabled,
                "description": task.description,
                "created_at": task.created_at,
            })
        return task

    def remove_task(self, task_id: str) -> None:
        """Remove a scheduled task by ID."""
        Q = Query()
        with self._db_lock:
            removed = self._db.remove(Q.id == task_id)
        if not removed:
            raise SchedulerError(task_id, "Task not found")

        # Remove from APScheduler if running
        if self._scheduler and self._scheduler.running:
            try:
                self._scheduler.remove_job(task_id)
            except Exception:
                pass

    def list_tasks(self) -> list[dict]:
        """Return all scheduled tasks."""
        with self._db_lock:
            return self._db.all()

    def get_task(self, task_id: str) -> dict | None:
        """Return a single task by ID, or None."""
        Q = Query()
        with self._db_lock:
            results = self._db.search(Q.id == task_id)
        return results[0] if results else None

    def start(self) -> None:
        """Register all enabled tasks with APScheduler and start."""
        scheduler = self._get_scheduler()
        with self._db_lock:
            all_tasks = self._db.all()
        for task_doc in all_tasks:
            if task_doc.get("enabled", True):
                self._register_job(task_doc)
        scheduler.start()

    def stop(self) -> None:
        """Shutdown APScheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _register_job(self, task_doc: dict) -> None:
        """Register a single task as an APScheduler job."""
        scheduler = self._get_scheduler()
        task_id = task_doc["id"]
        schedule_type = task_doc["schedule_type"]
        schedule_value = task_doc["schedule_value"]

        if schedule_type == "cron":
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(schedule_value)
            scheduler.add_job(self._execute_task, trigger, id=task_id, args=[task_id])
        elif schedule_type == "interval":
            scheduler.add_job(
                self._execute_task, "interval",
                seconds=int(schedule_value), id=task_id, args=[task_id],
            )
        elif schedule_type == "once":
            from apscheduler.triggers.date import DateTrigger
            trigger = DateTrigger(run_date=schedule_value)
            scheduler.add_job(self._execute_task, trigger, id=task_id, args=[task_id])

    def _execute_task(self, task_id: str) -> str | None:
        """Execute a scheduled task: create Worker, call chat(), emit events."""
        task_doc = self.get_task(task_id)
        if not task_doc:
            return None

        worker_name = task_doc["worker_name"]
        message = task_doc["message"]

        self.event_log.emit(Event(
            type="task.started",
            source=f"scheduler:{task_id}",
            data={"worker": worker_name, "message": message},
        ))

        try:
            worker = Worker(worker_name, self.config.project_dir, self.config)
            response, _ = worker.chat(message, self.router)

            self.event_log.emit(Event(
                type="task.completed",
                source=f"scheduler:{task_id}",
                data={"worker": worker_name, "response": response[:500]},
            ))
            return response
        except Exception as e:
            self.event_log.emit(Event(
                type="task.failed",
                source=f"scheduler:{task_id}",
                data={"worker": worker_name, "error": str(e)},
            ))
            return None
