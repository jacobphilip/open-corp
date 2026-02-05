"""Tests for framework/exceptions.py — suggestion field."""

from framework.exceptions import (
    BudgetExceeded,
    ConfigError,
    ModelUnavailable,
    TrainingError,
    WorkerNotFound,
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
