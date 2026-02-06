"""Tests for framework/housekeeping.py — data retention policies."""

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from click.testing import CliRunner

from framework.config import RetentionConfig
from framework.db import get_db
from framework.housekeeping import Housekeeper
from scripts.corp import cli


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _date_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


class TestCleanEvents:
    def test_clean_events_removes_old(self, tmp_project):
        """Events older than cutoff removed."""
        retention = RetentionConfig(events_days=30)
        db, lock = get_db(tmp_project / "data" / "events.json")
        with lock:
            db.insert({"type": "old", "timestamp": _iso_days_ago(60)})
            db.insert({"type": "recent", "timestamp": _iso_days_ago(10)})

        hk = Housekeeper(tmp_project, retention)
        removed = hk.clean_events()
        assert removed == 1
        with lock:
            remaining = db.all()
        assert len(remaining) == 1
        assert remaining[0]["type"] == "recent"

    def test_clean_events_keeps_recent(self, tmp_project):
        """Events within window kept."""
        retention = RetentionConfig(events_days=30)
        db, lock = get_db(tmp_project / "data" / "events.json")
        with lock:
            db.insert({"type": "a", "timestamp": _iso_days_ago(5)})
            db.insert({"type": "b", "timestamp": _iso_days_ago(10)})

        hk = Housekeeper(tmp_project, retention)
        removed = hk.clean_events()
        assert removed == 0

    def test_clean_events_empty(self, tmp_project):
        """No crash on missing DB file."""
        # Don't create events.json
        (tmp_project / "data" / "events.json").unlink(missing_ok=True)
        hk = Housekeeper(tmp_project, RetentionConfig())
        removed = hk.clean_events()
        assert removed == 0


class TestCleanSpending:
    def test_clean_spending_removes_old(self, tmp_project):
        """Spending records cleaned by date."""
        retention = RetentionConfig(spending_days=30)
        db, lock = get_db(tmp_project / "data" / "spending.json")
        table = db.table("spending")
        with lock:
            table.insert({"date": _date_days_ago(60), "cost": 1.0})
            table.insert({"date": _date_days_ago(10), "cost": 0.5})

        hk = Housekeeper(tmp_project, retention)
        removed = hk.clean_spending()
        assert removed == 1

    def test_clean_spending_keeps_recent(self, tmp_project):
        """Recent spending kept."""
        retention = RetentionConfig(spending_days=30)
        db, lock = get_db(tmp_project / "data" / "spending.json")
        table = db.table("spending")
        with lock:
            table.insert({"date": _date_days_ago(5), "cost": 0.5})

        hk = Housekeeper(tmp_project, retention)
        removed = hk.clean_spending()
        assert removed == 0

    def test_clean_spending_empty(self, tmp_project):
        """No crash on missing DB."""
        (tmp_project / "data" / "spending.json").unlink(missing_ok=True)
        hk = Housekeeper(tmp_project, RetentionConfig())
        removed = hk.clean_spending()
        assert removed == 0


class TestCleanWorkflows:
    def test_clean_workflows_removes_old(self, tmp_project):
        """Old workflow runs removed."""
        retention = RetentionConfig(workflows_days=30)
        db, lock = get_db(tmp_project / "data" / "workflows.json")
        with lock:
            db.insert({"id": "old", "started_at": _iso_days_ago(60), "status": "completed"})
            db.insert({"id": "new", "started_at": _iso_days_ago(5), "status": "completed"})

        hk = Housekeeper(tmp_project, retention)
        removed = hk.clean_workflows()
        assert removed == 1

    def test_clean_workflows_keeps_recent(self, tmp_project):
        """Recent runs kept."""
        retention = RetentionConfig(workflows_days=30)
        db, lock = get_db(tmp_project / "data" / "workflows.json")
        with lock:
            db.insert({"id": "a", "started_at": _iso_days_ago(5), "status": "completed"})

        hk = Housekeeper(tmp_project, retention)
        removed = hk.clean_workflows()
        assert removed == 0


class TestCleanPerformance:
    def test_clean_performance_trims(self, tmp_project, create_worker):
        """Trims to max, keeps newest."""
        create_worker("alice")
        perf_path = tmp_project / "workers" / "alice" / "performance.json"
        records = [{"task": f"t{i}", "rating": 3} for i in range(150)]
        perf_path.write_text(json.dumps(records))

        hk = Housekeeper(tmp_project, RetentionConfig(performance_max=100))
        removed = hk.clean_performance()
        assert removed == 50

        remaining = json.loads(perf_path.read_text())
        assert len(remaining) == 100
        # Kept newest (last 100)
        assert remaining[0]["task"] == "t50"

    def test_clean_performance_under_limit(self, tmp_project, create_worker):
        """No trim when under limit."""
        create_worker("bob")
        perf_path = tmp_project / "workers" / "bob" / "performance.json"
        records = [{"task": f"t{i}", "rating": 3} for i in range(50)]
        perf_path.write_text(json.dumps(records))

        hk = Housekeeper(tmp_project, RetentionConfig(performance_max=100))
        removed = hk.clean_performance()
        assert removed == 0

    def test_clean_performance_missing_file(self, tmp_project, create_worker):
        """No crash on missing file."""
        create_worker("carol")
        (tmp_project / "workers" / "carol" / "performance.json").unlink()

        hk = Housekeeper(tmp_project, RetentionConfig(performance_max=100))
        removed = hk.clean_performance()
        assert removed == 0


class TestRunAll:
    def test_run_all_returns_summary(self, tmp_project):
        """Returns dict with all counts."""
        hk = Housekeeper(tmp_project, RetentionConfig())
        results = hk.run_all()
        assert isinstance(results, dict)
        assert "events" in results
        assert "spending" in results
        assert "workflows" in results
        assert "performance" in results

    def test_run_all_logs_total(self, tmp_project, caplog):
        """Logger captures summary message."""
        hk = Housekeeper(tmp_project, RetentionConfig())
        with caplog.at_level(logging.INFO, logger="open-corp"):
            hk.run_all()
        assert any("housekeeping complete" in r.message.lower() for r in caplog.records)


class TestCLIHousekeep:
    def test_cli_housekeep(self, tmp_project):
        """CLI command runs and prints results."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--project-dir", str(tmp_project), "housekeep"])
        assert result.exit_code == 0
        assert "Housekeeping complete" in result.output
