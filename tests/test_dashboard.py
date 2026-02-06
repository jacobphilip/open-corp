"""Tests for framework/dashboard.py web dashboard."""

import json

import pytest

from framework.dashboard import create_dashboard_app
from framework.events import Event, EventLog
from framework.scheduler import Scheduler, ScheduledTask
from framework.workflow import WorkflowEngine


@pytest.fixture
def dashboard_client(tmp_project, config, accountant, router, hr):
    """Create a Flask test client for the dashboard."""
    app = create_dashboard_app(config, accountant, router, hr)
    app.config["TESTING"] = True
    return app.test_client()


# --- HTML pages ---

class TestDashboardHome:
    def test_home_returns_200(self, dashboard_client):
        resp = dashboard_client.get("/")
        assert resp.status_code == 200

    def test_home_contains_project_name(self, dashboard_client):
        resp = dashboard_client.get("/")
        assert b"Test Project" in resp.data

    def test_home_shows_budget(self, dashboard_client):
        resp = dashboard_client.get("/")
        assert b"$3.00" in resp.data


class TestDashboardWorkers:
    def test_workers_page_200(self, dashboard_client):
        resp = dashboard_client.get("/workers")
        assert resp.status_code == 200

    def test_workers_lists_names(self, dashboard_client, create_worker):
        create_worker("alice")
        resp = dashboard_client.get("/workers")
        assert b"alice" in resp.data

    def test_worker_detail_200(self, dashboard_client, create_worker):
        create_worker("bob")
        resp = dashboard_client.get("/workers/bob")
        assert resp.status_code == 200
        assert b"bob" in resp.data

    def test_worker_detail_404(self, dashboard_client):
        resp = dashboard_client.get("/workers/nonexistent")
        assert resp.status_code == 404


class TestDashboardBudget:
    def test_budget_page_200(self, dashboard_client):
        resp = dashboard_client.get("/budget")
        assert resp.status_code == 200

    def test_budget_shows_limit(self, dashboard_client):
        resp = dashboard_client.get("/budget")
        assert b"3.00" in resp.data


class TestDashboardEvents:
    def test_events_page_200(self, dashboard_client):
        resp = dashboard_client.get("/events")
        assert resp.status_code == 200

    def test_events_with_type_filter(self, dashboard_client, tmp_project):
        event_log = EventLog(tmp_project / "data" / "events.json")
        event_log.emit(Event(type="test.ping", source="test"))
        resp = dashboard_client.get("/events?type=test.ping")
        assert resp.status_code == 200
        assert b"test.ping" in resp.data


class TestDashboardWorkflows:
    def test_workflows_page_200(self, dashboard_client):
        resp = dashboard_client.get("/workflows")
        assert resp.status_code == 200


class TestDashboardSchedule:
    def test_schedule_page_200(self, dashboard_client):
        resp = dashboard_client.get("/schedule")
        assert resp.status_code == 200


# --- JSON API ---

class TestDashboardAPI:
    def test_api_status_json(self, dashboard_client):
        resp = dashboard_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["project"] == "Test Project"
        assert "budget" in data

    def test_api_budget_json(self, dashboard_client):
        resp = dashboard_client.get("/api/budget")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "daily_limit" in data
        assert "total_spent" in data

    def test_api_workers_json(self, dashboard_client, create_worker):
        create_worker("alice")
        resp = dashboard_client.get("/api/workers")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert data[0]["name"] == "alice"

    def test_api_events_json(self, dashboard_client):
        resp = dashboard_client.get("/api/events")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_api_events_with_filter(self, dashboard_client, tmp_project):
        event_log = EventLog(tmp_project / "data" / "events.json")
        event_log.emit(Event(type="api.test", source="test"))
        event_log.emit(Event(type="other.event", source="test"))
        resp = dashboard_client.get("/api/events?type=api.test")
        data = resp.get_json()
        assert all(e["type"] == "api.test" for e in data)

    def test_api_workflows_json(self, dashboard_client):
        resp = dashboard_client.get("/api/workflows")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_api_schedule_json(self, dashboard_client):
        resp = dashboard_client.get("/api/schedule")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
