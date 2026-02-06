"""Tests for framework/exceptions.py — suggestion field."""

from framework.exceptions import (
    BrokerError,
    BudgetExceeded,
    ConfigError,
    ModelUnavailable,
    SchedulerError,
    TrainingError,
    WebhookError,
    WorkerNotFound,
    WorkflowError,
)


class TestExceptionSuggestions:
    def test_config_error_with_suggestion(self):
        """Suggestion text appears in str() output."""
        err = ConfigError("bad config", suggestion="Fix it.")
        assert "Try: Fix it." in str(err)
        assert err.suggestion == "Fix it."

    def test_worker_not_found_has_default_suggestion(self):
        """WorkerNotFound includes a default suggestion."""
        err = WorkerNotFound("ghost")
        assert "corp workers" in str(err)
        assert err.suggestion != ""

    def test_exceptions_backward_compat(self):
        """All exceptions work without explicit suggestion arg."""
        e1 = ConfigError("bad")
        assert "bad" in str(e1)
        assert "Try:" not in str(e1)

        e2 = BudgetExceeded(0.01, 3.00)
        assert "$0.01" in str(e2)
        assert "Try:" in str(e2)  # has default suggestion

        e3 = ModelUnavailable("m1", "cheap", ["m1"])
        assert "m1" in str(e3)
        assert "Try:" in str(e3)  # has default suggestion

        e4 = TrainingError("file.txt", "bad format")
        assert "bad format" in str(e4)
        assert "Try:" not in str(e4)  # no default for TrainingError

    def test_scheduler_error(self):
        """SchedulerError includes task_id and reason."""
        err = SchedulerError("abc123", "worker missing", suggestion="Check workers/")
        assert "abc123" in str(err)
        assert "worker missing" in str(err)
        assert "Try: Check workers/" in str(err)
        assert err.task_id == "abc123"
        assert err.reason == "worker missing"

    def test_workflow_error(self):
        """WorkflowError includes workflow name, optional node, and suggestion."""
        err = WorkflowError("my-pipeline", "cycle detected")
        assert "my-pipeline" in str(err)
        assert "cycle detected" in str(err)
        assert "node" not in str(err)

        err2 = WorkflowError("pipe", "failed", node="step-2", suggestion="Fix step-2")
        assert "at node 'step-2'" in str(err2)
        assert "Try: Fix step-2" in str(err2)
        assert err2.node == "step-2"

    def test_broker_error(self):
        """BrokerError includes reason and optional suggestion."""
        err = BrokerError("insufficient cash", suggestion="Deposit more funds")
        assert "insufficient cash" in str(err)
        assert "Try: Deposit more funds" in str(err)
        assert err.reason == "insufficient cash"

        err2 = BrokerError("no price data")
        assert "no price data" in str(err2)
        assert "Try:" not in str(err2)

    def test_webhook_error(self):
        """WebhookError includes reason and optional suggestion."""
        err = WebhookError("auth failed", suggestion="Check WEBHOOK_API_KEY")
        assert "auth failed" in str(err)
        assert "Try: Check WEBHOOK_API_KEY" in str(err)
        assert err.reason == "auth failed"

        err2 = WebhookError("server error")
        assert "server error" in str(err2)
        assert "Try:" not in str(err2)
