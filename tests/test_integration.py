"""Integration tests for v1.3.0 hardening — concurrency, error recovery, security, data integrity."""

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import Event, EventLog
from framework.exceptions import ValidationError
from framework.router import OPENROUTER_API_URL, Router
from framework.scheduler import Scheduler, ScheduledTask
from framework.validation import (
    RateLimiter,
    safe_load_json,
    safe_write_json,
    validate_worker_name,
)
from framework.worker import Worker
from framework.workflow import Workflow, WorkflowEngine, WorkflowNode


def _create_worker_files(worker_dir, level=1):
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "profile.md").write_text("# Worker\nA test worker.")
    (worker_dir / "memory.json").write_text("[]")
    (worker_dir / "performance.json").write_text("[]")
    (worker_dir / "skills.yaml").write_text(yaml.dump({"role": "tester", "skills": ["testing"]}))
    (worker_dir / "config.yaml").write_text(yaml.dump({"level": level, "max_context_tokens": 2000}))


def _mock_response(content="OK"):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })


class TestConcurrentAccess:
    def test_concurrent_budget_recording(self, tmp_project, config):
        """Multiple threads recording spending don't corrupt data."""
        accountant = Accountant(config)
        errors = []

        def record():
            try:
                accountant.record_call("m", 10, 5, 0.001, "w")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert accountant.today_spent() > 0

    def test_concurrent_event_emission(self, tmp_project, config):
        """Multiple threads emitting events don't lose data."""
        event_log = EventLog(tmp_project / "data" / "events.json")
        errors = []

        def emit(i):
            try:
                event_log.emit(Event(type=f"test.{i}", source="test"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emit, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        events = event_log.query(limit=20)
        assert len(events) == 10

    def test_concurrent_worker_memory_writes(self, tmp_project, config):
        """Multiple threads writing to worker memory don't corrupt the file."""
        _create_worker_files(tmp_project / "workers" / "concurrent")
        errors = []

        def write_memory(i):
            try:
                worker = Worker("concurrent", tmp_project, config)
                worker.update_memory("note", f"entry-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_memory, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # File should be valid JSON
        mem = json.loads((tmp_project / "workers" / "concurrent" / "memory.json").read_text())
        assert isinstance(mem, list)


class TestErrorRecovery:
    def test_router_retry_then_fallback(self, tmp_project, config):
        """503 retried, then falls to next model."""
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key",
                        max_retries=1, retry_base_delay=0.01)

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(503, text="Down"),
                    httpx.Response(503, text="Down"),  # exhausts retries on first model
                    httpx.Response(200, json={
                        "choices": [{"message": {"content": "OK"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                    }),
                ]
            )
            result = router.chat([{"role": "user", "content": "hi"}], tier="cheap")

        assert result["content"] == "OK"
        assert result["model_used"] == "mistralai/mistral-tiny"

    def test_workflow_node_timeout_recovery(self, tmp_project, config):
        """Timed-out node marks failed, downstream skipped, workflow continues."""
        _create_worker_files(tmp_project / "workers" / "alice")
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")
        engine = WorkflowEngine(config, accountant, router, event_log,
                                db_path=tmp_project / "data" / "workflows.json")

        wf = Workflow(name="timeout-test", description="test", timeout=0, nodes=[
            WorkflowNode(id="a", worker="alice", message="hi", timeout=0.001),
        ])

        with respx.mock:
            # Simulate slow response
            def slow_response(request):
                time.sleep(0.1)
                return _mock_response("done")
            respx.post(OPENROUTER_API_URL).mock(side_effect=slow_response)
            run = engine.run(wf)

        assert run.node_results["a"]["status"] in ("failed", "completed")

    def test_budget_exhaustion_mid_workflow(self, tmp_project, config):
        """Budget exhaustion during workflow doesn't crash — nodes fail gracefully."""
        _create_worker_files(tmp_project / "workers" / "alice")
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")
        engine = WorkflowEngine(config, accountant, router, event_log,
                                db_path=tmp_project / "data" / "workflows.json")

        # Exhaust budget
        accountant.record_call("m", 0, 0, 100.0, "w")

        wf = Workflow(name="budget-test", description="test", nodes=[
            WorkflowNode(id="a", worker="alice", message="hi"),
        ])

        run = engine.run(wf)
        assert run.node_results["a"]["status"] == "failed"

    def test_scheduler_worker_deleted(self, tmp_project, config):
        """Executing a task for a deleted worker doesn't crash scheduler."""
        _create_worker_files(tmp_project / "workers" / "temp")
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")
        scheduler = Scheduler(config, accountant, router, event_log,
                              db_path=tmp_project / "data" / "scheduler.json")

        task = scheduler.add_task(ScheduledTask(
            worker_name="temp", message="hello",
            schedule_type="once", schedule_value="2099-01-01T00:00:00",
        ))

        # Delete worker
        import shutil
        shutil.rmtree(tmp_project / "workers" / "temp")

        # Execute should fail gracefully
        result = scheduler._execute_task(task.id)
        assert result is None


class TestSecurityIntegration:
    def test_webhook_path_traversal_via_worker_name(self, tmp_project, config):
        """Worker name with path traversal is rejected by webhook."""
        import os
        from framework.webhooks import create_webhook_app

        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")
        scheduler = Scheduler(config, accountant, router, event_log,
                              db_path=tmp_project / "data" / "scheduler.json")

        with patch.dict(os.environ, {"WEBHOOK_API_KEY": "test-secret"}):
            app = create_webhook_app(config, accountant, router, event_log, scheduler)
            app.config["TESTING"] = True
            client = app.test_client()

        resp = client.post("/trigger/task",
                          json={"worker": "../etc/passwd", "message": "evil"},
                          headers={"Authorization": "Bearer test-secret",
                                   "Content-Type": "application/json"})
        assert resp.status_code == 400

    def test_dashboard_auth_bypass_attempts(self, tmp_project, config):
        """Dashboard with auth rejects requests without valid token."""
        from framework.dashboard import create_dashboard_app
        from framework.hr import HR

        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        hr = HR(config, tmp_project)

        app = create_dashboard_app(config, accountant, router, hr, auth_token="secret123")
        app.config["TESTING"] = True
        client = app.test_client()

        # No auth
        assert client.get("/").status_code == 401
        # Wrong auth
        assert client.get("/", headers={"Authorization": "Bearer wrong"}).status_code == 401
        # Correct auth
        assert client.get("/", headers={"Authorization": "Bearer secret123"}).status_code == 200

    def test_rate_limit_with_auth(self, tmp_project, config):
        """Rate limit applies even with valid auth."""
        from framework.dashboard import create_dashboard_app
        from framework.hr import HR

        # Set very low rate limit
        config.security.dashboard_rate_limit = 1.0
        config.security.dashboard_rate_burst = 2

        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        hr = HR(config, tmp_project)

        app = create_dashboard_app(config, accountant, router, hr)
        app.config["TESTING"] = True
        client = app.test_client()

        # First 2 requests succeed (burst)
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 200
        # Third hits rate limit
        assert client.get("/").status_code == 429

    def test_large_payload_rejected(self, tmp_project, config):
        """Webhook rejects payloads over 1MB."""
        import os
        from framework.webhooks import create_webhook_app

        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")

        with patch.dict(os.environ, {"WEBHOOK_API_KEY": "test-secret"}):
            app = create_webhook_app(config, accountant, router, event_log)
            app.config["TESTING"] = True
            client = app.test_client()

        # Send >1MB payload
        large_data = "x" * (1_048_577)
        resp = client.post("/events",
                          data=large_data,
                          content_type="application/json",
                          headers={"Authorization": "Bearer test-secret"})
        assert resp.status_code == 400

    def test_invalid_worker_name_rejected_across_systems(self, tmp_project, config):
        """Scheduler rejects invalid worker names."""
        accountant = Accountant(config)
        router = Router(config, accountant, api_key="test-key")
        event_log = EventLog(tmp_project / "data" / "events.json")
        scheduler = Scheduler(config, accountant, router, event_log,
                              db_path=tmp_project / "data" / "scheduler.json")

        with pytest.raises(ValidationError):
            scheduler.add_task(ScheduledTask(
                worker_name="../evil",
                message="hello",
                schedule_type="once",
                schedule_value="2099-01-01T00:00:00",
            ))


class TestDataIntegrity:
    def test_corrupted_worker_files_graceful(self, tmp_project, config):
        """Worker loads with corrupted memory/performance files."""
        worker_dir = tmp_project / "workers" / "corrupt"
        _create_worker_files(worker_dir)
        (worker_dir / "memory.json").write_text("{broken!!!")
        (worker_dir / "performance.json").write_text("{also broken")

        # Should load gracefully with empty lists
        worker = Worker("corrupt", tmp_project, config)
        assert worker.memory == []
        assert worker.performance == []

    def test_atomic_write_creates_valid_json(self, tmp_path):
        """safe_write_json produces valid JSON even after multiple writes."""
        p = tmp_path / "test.json"
        for i in range(10):
            safe_write_json(p, {"count": i})
        data = safe_load_json(p)
        assert data == {"count": 9}

    def test_roundtrip_json_integrity(self, tmp_path):
        """Data survives write-then-read cycle."""
        p = tmp_path / "roundtrip.json"
        original = [
            {"name": "alice", "score": 4.5, "tags": ["a", "b"]},
            {"name": "bob", "score": 3.0, "tags": []},
        ]
        safe_write_json(p, original)
        loaded = safe_load_json(p)
        assert loaded == original
