"""Tests for framework/scheduler.py — scheduled task CRUD and execution."""

import json
import threading

import httpx
import pytest
import respx
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.exceptions import SchedulerError
from framework.router import OPENROUTER_API_URL, Router
from framework.scheduler import Scheduler, ScheduledTask


def _create_worker_files(worker_dir, level=1):
    """Create minimal worker files."""
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "profile.md").write_text("# Test Worker\nA test worker.")
    (worker_dir / "memory.json").write_text("[]")
    (worker_dir / "performance.json").write_text("[]")
    (worker_dir / "skills.yaml").write_text(yaml.dump({"role": "tester", "skills": ["testing"]}))
    (worker_dir / "config.yaml").write_text(yaml.dump({"level": level, "max_context_tokens": 2000}))


@pytest.fixture
def scheduler_env(tmp_project, config):
    """Set up scheduler with all dependencies."""
    accountant = Accountant(config)
    router = Router(config, accountant, api_key="test-key")
    event_log = EventLog(tmp_project / "data" / "events.json")
    scheduler = Scheduler(config, accountant, router, event_log,
                          db_path=tmp_project / "data" / "scheduler.json")
    _create_worker_files(tmp_project / "workers" / "alice")
    return scheduler, event_log, router


class TestScheduler:
    def test_add_task(self, scheduler_env):
        """Task is persisted to TinyDB with an ID."""
        scheduler, _, _ = scheduler_env
        task = ScheduledTask(worker_name="alice", message="hello",
                             schedule_type="interval", schedule_value="60")
        result = scheduler.add_task(task)
        assert result.id != ""
        assert len(result.id) == 8
        assert scheduler.get_task(result.id) is not None

    def test_add_task_invalid_type(self, scheduler_env):
        """Invalid schedule_type raises SchedulerError."""
        scheduler, _, _ = scheduler_env
        task = ScheduledTask(worker_name="alice", message="hello",
                             schedule_type="weekly", schedule_value="mon")
        with pytest.raises(SchedulerError, match="Invalid schedule_type"):
            scheduler.add_task(task)

    def test_add_task_worker_not_found(self, scheduler_env):
        """Missing worker raises SchedulerError."""
        scheduler, _, _ = scheduler_env
        task = ScheduledTask(worker_name="ghost", message="hello",
                             schedule_type="interval", schedule_value="60")
        with pytest.raises(SchedulerError, match="not found"):
            scheduler.add_task(task)

    def test_remove_task(self, scheduler_env):
        """Task is removed from TinyDB."""
        scheduler, _, _ = scheduler_env
        task = scheduler.add_task(ScheduledTask(
            worker_name="alice", message="hi",
            schedule_type="interval", schedule_value="60",
        ))
        scheduler.remove_task(task.id)
        assert scheduler.get_task(task.id) is None

    def test_remove_task_not_found(self, scheduler_env):
        """Missing task_id raises SchedulerError."""
        scheduler, _, _ = scheduler_env
        with pytest.raises(SchedulerError, match="not found"):
            scheduler.remove_task("nonexistent")

    def test_list_tasks(self, scheduler_env):
        """list_tasks returns all tasks."""
        scheduler, _, _ = scheduler_env
        scheduler.add_task(ScheduledTask(
            worker_name="alice", message="a",
            schedule_type="interval", schedule_value="60",
        ))
        scheduler.add_task(ScheduledTask(
            worker_name="alice", message="b",
            schedule_type="cron", schedule_value="*/5 * * * *",
        ))
        tasks = scheduler.list_tasks()
        assert len(tasks) == 2

    def test_get_task(self, scheduler_env):
        """get_task returns a single task by ID."""
        scheduler, _, _ = scheduler_env
        task = scheduler.add_task(ScheduledTask(
            worker_name="alice", message="test",
            schedule_type="once", schedule_value="2026-02-10T09:00:00",
        ))
        result = scheduler.get_task(task.id)
        assert result is not None
        assert result["worker_name"] == "alice"
        assert result["schedule_type"] == "once"

    def test_execute_task(self, scheduler_env):
        """_execute_task calls worker.chat() and emits events."""
        scheduler, event_log, _ = scheduler_env
        task = scheduler.add_task(ScheduledTask(
            worker_name="alice", message="do work",
            schedule_type="interval", schedule_value="60",
        ))

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json={
                    "choices": [{"message": {"content": "Done!"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                })
            )
            result = scheduler._execute_task(task.id)

        assert result == "Done!"
        events = event_log.query()
        types = [e["type"] for e in events]
        assert "task.started" in types
        assert "task.completed" in types

    def test_execute_task_failure(self, scheduler_env):
        """Chat error emits task.failed event and returns None."""
        scheduler, event_log, _ = scheduler_env
        task = scheduler.add_task(ScheduledTask(
            worker_name="alice", message="fail",
            schedule_type="interval", schedule_value="60",
        ))

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(500, json={"error": "server error"})
            )
            result = scheduler._execute_task(task.id)

        assert result is None
        events = event_log.query(event_type="task.failed")
        assert len(events) == 1

    def test_execute_task_not_found(self, scheduler_env):
        """Missing task returns None."""
        scheduler, _, _ = scheduler_env
        result = scheduler._execute_task("nonexistent")
        assert result is None


class TestSchedulerThreadSafety:
    def test_concurrent_writes(self, scheduler_env):
        """10 threads adding tasks simultaneously — no corruption."""
        scheduler, _, _ = scheduler_env
        errors = []

        def add_task(i):
            try:
                scheduler.add_task(ScheduledTask(
                    worker_name="alice", message=f"task-{i}",
                    schedule_type="interval", schedule_value="60",
                ))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_task, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(scheduler.list_tasks()) == 10

    def test_concurrent_reads_during_writes(self, scheduler_env):
        """Readers get consistent data while writers are active."""
        scheduler, _, _ = scheduler_env
        scheduler.add_task(ScheduledTask(
            worker_name="alice", message="seed",
            schedule_type="interval", schedule_value="60",
        ))
        errors = []

        def reader():
            try:
                tasks = scheduler.list_tasks()
                assert len(tasks) >= 1
            except Exception as e:
                errors.append(e)

        def writer(i):
            try:
                scheduler.add_task(ScheduledTask(
                    worker_name="alice", message=f"task-{i}",
                    schedule_type="interval", schedule_value="60",
                ))
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=reader) for _ in range(5)]
            + [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_lock_prevents_corruption(self, scheduler_env):
        """After concurrent ops, task count matches expected."""
        scheduler, _, _ = scheduler_env

        def add_task(i):
            scheduler.add_task(ScheduledTask(
                worker_name="alice", message=f"task-{i}",
                schedule_type="interval", schedule_value="60",
            ))

        threads = [threading.Thread(target=add_task, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(scheduler.list_tasks()) == 20
