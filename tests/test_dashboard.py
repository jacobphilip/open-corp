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


@pytest.fixture
def authed_dashboard_client(tmp_project, config, accountant, router, hr):
    """Create a Flask test client for an auth-protected dashboard."""
    app = create_dashboard_app(config, accountant, router, hr, auth_token="test-token")
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


# --- Auth tests ---

class TestDashboardAuth:
    def test_no_auth_without_token(self, dashboard_client):
        """Dashboard without auth_token allows all requests."""
        resp = dashboard_client.get("/")
        assert resp.status_code == 200

    def test_auth_required_with_token(self, authed_dashboard_client):
        """Dashboard with auth_token returns 401 without credentials."""
        resp = authed_dashboard_client.get("/")
        assert resp.status_code == 401

    def test_auth_via_header(self, authed_dashboard_client):
        """Dashboard accepts valid Authorization Bearer header."""
        resp = authed_dashboard_client.get("/",
                                          headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 200

    def test_auth_via_cookie(self, authed_dashboard_client):
        """Dashboard accepts valid cookie after login."""
        # Login to get cookie
        resp = authed_dashboard_client.get("/login?token=test-token")
        assert resp.status_code == 302  # redirect

        # Follow-up request should use cookie
        resp = authed_dashboard_client.get("/")
        assert resp.status_code == 200

    def test_login_invalid_token(self, authed_dashboard_client):
        """Login with wrong token returns 401."""
        resp = authed_dashboard_client.get("/login?token=wrong")
        assert resp.status_code == 401

    def test_auth_wrong_header(self, authed_dashboard_client):
        """Wrong Bearer token returns 401."""
        resp = authed_dashboard_client.get("/",
                                          headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401

    def test_api_requires_auth(self, authed_dashboard_client):
        """API endpoints also require auth when token is set."""
        resp = authed_dashboard_client.get("/api/status")
        assert resp.status_code == 401

        resp = authed_dashboard_client.get("/api/status",
                                          headers={"Authorization": "Bearer test-token"})
        assert resp.status_code == 200

    def test_worker_detail_validates_name(self, dashboard_client):
        """Worker detail with invalid name returns 400."""
        resp = dashboard_client.get("/workers/../etc/passwd")
        assert resp.status_code in (400, 404)  # invalid name or redirect

    def test_rate_limit(self, tmp_project, config, accountant, router, hr):
        """Dashboard rate limiter triggers 429."""
        config.security.dashboard_rate_limit = 1.0
        config.security.dashboard_rate_burst = 2
        app = create_dashboard_app(config, accountant, router, hr)
        app.config["TESTING"] = True
        client = app.test_client()

        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 429

    def test_login_sets_httponly_cookie(self, authed_dashboard_client):
        """Login cookie has httponly flag."""
        resp = authed_dashboard_client.get("/login?token=test-token")
        cookie_header = resp.headers.get("Set-Cookie", "")
        assert "HttpOnly" in cookie_header
