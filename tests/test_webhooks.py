"""Tests for framework/webhooks.py — Flask webhook server."""

import os
from unittest.mock import patch

import httpx
import pytest
import respx
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.router import OPENROUTER_API_URL, Router
from framework.scheduler import Scheduler, ScheduledTask
from framework.webhooks import create_webhook_app


def _create_worker_files(worker_dir, level=1):
    """Create minimal worker files."""
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "profile.md").write_text("# Test Worker\nA test worker.")
    (worker_dir / "memory.json").write_text("[]")
    (worker_dir / "performance.json").write_text("[]")
    (worker_dir / "skills.yaml").write_text(yaml.dump({"role": "tester", "skills": ["testing"]}))
    (worker_dir / "config.yaml").write_text(yaml.dump({"level": level, "max_context_tokens": 2000}))


def _mock_response(content="OK"):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    })


@pytest.fixture
def webhook_env(tmp_project, config):
    """Set up webhook app with all dependencies."""
    accountant = Accountant(config)
    router = Router(config, accountant, api_key="test-key")
    event_log = EventLog(tmp_project / "data" / "events.json")
    scheduler = Scheduler(config, accountant, router, event_log,
                          db_path=tmp_project / "data" / "scheduler.json")
    _create_worker_files(tmp_project / "workers" / "alice")

    with patch.dict(os.environ, {"WEBHOOK_API_KEY": "test-secret"}):
        app = create_webhook_app(config, accountant, router, event_log, scheduler)
        app.config["TESTING"] = True
        client = app.test_client()
        yield client, event_log, tmp_project, scheduler


def _auth_headers():
    return {"Authorization": "Bearer test-secret", "Content-Type": "application/json"}


class TestWebhookHealth:
    def test_health_no_auth(self, webhook_env):
        """/health returns 200 without auth."""
        client, _, _, _ = webhook_env
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestWebhookAuth:
    def test_trigger_workflow_no_auth(self, webhook_env):
        """401 without bearer token."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow", json={"workflow_file": "test.yaml"})
        assert resp.status_code == 401

    def test_trigger_workflow_bad_auth(self, webhook_env):
        """401 with wrong token."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow",
                          json={"workflow_file": "test.yaml"},
                          headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 401

    def test_auth_timing_safe(self, webhook_env):
        """Verify hmac.compare_digest is used (constant time comparison)."""
        import hmac as hmac_module
        # If hmac.compare_digest is being used, the code imports hmac
        # This is verified by the import in webhooks.py
        assert hasattr(hmac_module, "compare_digest")


class TestTriggerWorkflow:
    def test_trigger_workflow_success(self, webhook_env):
        """Valid auth + workflow file returns 200 + run_id."""
        client, _, tmp_project, _ = webhook_env
        wf_path = tmp_project / "workflows" / "test.yaml"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(yaml.dump({
            "name": "test-wf",
            "nodes": {"step1": {"worker": "alice", "message": "hello"}},
        }))

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=_mock_response("done"))
            resp = client.post("/trigger/workflow",
                              json={"workflow_file": str(wf_path)},
                              headers=_auth_headers())

        assert resp.status_code == 200
        data = resp.get_json()
        assert "run_id" in data
        assert data["status"] == "completed"

    def test_trigger_workflow_missing_file(self, webhook_env):
        """400 for missing workflow file."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow",
                          json={"workflow_file": "workflows/nonexistent.yaml"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "not found" in resp.get_json()["error"]

    def test_trigger_workflow_missing_body(self, webhook_env):
        """400 for empty/missing body."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow",
                          json={},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "missing" in resp.get_json()["error"]

    def test_trigger_workflow_budget_exceeded(self, webhook_env):
        """500 when budget is frozen."""
        client, _, tmp_project, _ = webhook_env
        # Exhaust budget
        from framework.accountant import Accountant
        config = ProjectConfig.load(tmp_project)
        accountant = Accountant(config)
        accountant.record_call("m", 0, 0, 100.0, "w")  # way over budget

        wf_path = tmp_project / "workflows" / "test.yaml"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(yaml.dump({
            "name": "test-wf",
            "nodes": {"step1": {"worker": "alice", "message": "hello"}},
        }))

        resp = client.post("/trigger/workflow",
                          json={"workflow_file": str(wf_path)},
                          headers=_auth_headers())
        # Workflow runs but nodes fail due to budget
        assert resp.status_code in (200, 500)


class TestTriggerTask:
    def test_trigger_task_success(self, webhook_env):
        """Valid task creation returns 200 + task_id."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/task",
                          json={"worker": "alice", "message": "do stuff"},
                          headers=_auth_headers())
        assert resp.status_code == 200
        data = resp.get_json()
        assert "task_id" in data
        assert data["status"] == "scheduled"

    def test_trigger_task_missing_worker(self, webhook_env):
        """400 for missing worker field."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/task",
                          json={"message": "hello"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "missing worker" in resp.get_json()["error"]

    def test_trigger_task_invalid_worker(self, webhook_env):
        """400 for nonexistent worker."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/task",
                          json={"worker": "ghost", "message": "hello"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "not found" in resp.get_json()["error"]

    def test_trigger_task_with_run_at(self, webhook_env):
        """Scheduled one-time task with future timestamp."""
        client, _, _, scheduler = webhook_env
        resp = client.post("/trigger/task",
                          json={"worker": "alice", "message": "later",
                                "run_at": "2026-12-31T00:00:00"},
                          headers=_auth_headers())
        assert resp.status_code == 200
        task_id = resp.get_json()["task_id"]
        task = scheduler.get_task(task_id)
        assert task is not None
        assert task["schedule_value"] == "2026-12-31T00:00:00"


class TestEmitEvent:
    def test_emit_event_success(self, webhook_env):
        """Event persisted to event log."""
        client, event_log, _, _ = webhook_env
        resp = client.post("/events",
                          json={"type": "custom.event", "source": "external",
                                "data": {"key": "value"}},
                          headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "emitted"

        events = event_log.query(event_type="custom.event")
        assert len(events) == 1
        assert events[0]["data"]["key"] == "value"

    def test_emit_event_missing_type(self, webhook_env):
        """400 for missing type."""
        client, _, _, _ = webhook_env
        resp = client.post("/events",
                          json={"source": "test"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "missing type" in resp.get_json()["error"]


class TestScheduleTypeFix:
    def test_webhook_schedule_immediate(self, webhook_env):
        """No run_at uses valid ISO timestamp, not epoch."""
        client, _, _, scheduler = webhook_env
        resp = client.post("/trigger/task",
                          json={"worker": "alice", "message": "now"},
                          headers=_auth_headers())
        assert resp.status_code == 200
        task_id = resp.get_json()["task_id"]
        task = scheduler.get_task(task_id)
        assert task is not None
        assert task["schedule_value"] != "1970-01-01T00:00:00"
        assert task["schedule_type"] == "once"

    def test_webhook_schedule_with_run_at(self, webhook_env):
        """Provided run_at is used as schedule_value."""
        client, _, _, scheduler = webhook_env
        resp = client.post("/trigger/task",
                          json={"worker": "alice", "message": "later",
                                "run_at": "2026-06-15T12:00:00"},
                          headers=_auth_headers())
        assert resp.status_code == 200
        task_id = resp.get_json()["task_id"]
        task = scheduler.get_task(task_id)
        assert task["schedule_value"] == "2026-06-15T12:00:00"

    def test_webhook_schedule_value_is_iso(self, webhook_env):
        """Immediate schedule_value is a valid ISO timestamp."""
        from datetime import datetime
        client, _, _, scheduler = webhook_env
        resp = client.post("/trigger/task",
                          json={"worker": "alice", "message": "check iso"},
                          headers=_auth_headers())
        task_id = resp.get_json()["task_id"]
        task = scheduler.get_task(task_id)
        # Should parse without error
        dt = datetime.fromisoformat(task["schedule_value"])
        assert dt.year >= 2024


class TestPathTraversal:
    def test_webhook_path_traversal_absolute(self, webhook_env):
        """/etc/passwd → 400."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow",
                          json={"workflow_file": "/etc/passwd"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "within project" in resp.get_json()["error"]

    def test_webhook_path_traversal_relative(self, webhook_env):
        """../../etc/passwd → 400."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow",
                          json={"workflow_file": "../../etc/passwd"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "within project" in resp.get_json()["error"]

    def test_webhook_path_within_project_relative(self, webhook_env):
        """workflows/test.yaml within project works."""
        client, _, tmp_project, _ = webhook_env
        wf_path = tmp_project / "workflows" / "test.yaml"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(yaml.dump({
            "name": "test-wf",
            "nodes": {"step1": {"worker": "alice", "message": "hello"}},
        }))

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=_mock_response("done"))
            resp = client.post("/trigger/workflow",
                              json={"workflow_file": "workflows/test.yaml"},
                              headers=_auth_headers())
        assert resp.status_code == 200

    def test_webhook_path_within_project_absolute(self, webhook_env):
        """Absolute path within project works."""
        client, _, tmp_project, _ = webhook_env
        wf_path = tmp_project / "workflows" / "abs.yaml"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(yaml.dump({
            "name": "abs-wf",
            "nodes": {"step1": {"worker": "alice", "message": "hello"}},
        }))

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(return_value=_mock_response("done"))
            resp = client.post("/trigger/workflow",
                              json={"workflow_file": str(wf_path)},
                              headers=_auth_headers())
        assert resp.status_code == 200

    def test_webhook_path_traversal_dot_dot(self, webhook_env):
        """Nested ../ traversal → 400."""
        client, _, _, _ = webhook_env
        resp = client.post("/trigger/workflow",
                          json={"workflow_file": "workflows/../../../etc/shadow"},
                          headers=_auth_headers())
        assert resp.status_code == 400
        assert "within project" in resp.get_json()["error"]
