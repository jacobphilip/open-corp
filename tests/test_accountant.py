"""Tests for framework/accountant.py."""

import pytest

from framework.accountant import Accountant, BudgetStatus
from framework.exceptions import BudgetExceeded


class TestAccountant:
    def test_initial_state_green(self, accountant):
        """Fresh accountant with no spending is GREEN."""
        status = accountant.pre_check()
        assert status == BudgetStatus.GREEN
        assert accountant.today_spent() == 0.0
        assert accountant.can_spend() is True

    def test_record_call(self, accountant):
        """Recording a call increases today_spent."""
        accountant.record_call("test-model", 100, 50, 0.001, "test-worker")
        assert accountant.today_spent() == pytest.approx(0.001)

    def test_multiple_calls_accumulate(self, accountant):
        """Multiple calls sum correctly."""
        accountant.record_call("m1", 100, 50, 0.50, "w1")
        accountant.record_call("m2", 200, 100, 0.30, "w2")
        assert accountant.today_spent() == pytest.approx(0.80)

    def test_caution_threshold(self, accountant):
        """Spending 60-80% of budget triggers CAUTION."""
        # daily_limit = 3.00, caution at 60% = $1.80
        accountant.record_call("m", 0, 0, 2.00, "w")
        status = accountant.pre_check()
        assert status == BudgetStatus.CAUTION

    def test_austerity_threshold(self, accountant):
        """Spending 80-95% of budget triggers AUSTERITY."""
        # daily_limit = 3.00, austerity at 80% = $2.40
        accountant.record_call("m", 0, 0, 2.60, "w")
        status = accountant.pre_check()
        assert status == BudgetStatus.AUSTERITY

    def test_critical_threshold(self, accountant):
        """Spending 95-100% triggers CRITICAL."""
        # daily_limit = 3.00, critical at 95% = $2.85
        accountant.record_call("m", 0, 0, 2.90, "w")
        status = accountant.pre_check()
        assert status == BudgetStatus.CRITICAL

    def test_frozen_at_limit(self, accountant):
        """Spending 100% raises BudgetExceeded (FROZEN)."""
        accountant.record_call("m", 0, 0, 3.00, "w")
        with pytest.raises(BudgetExceeded):
            accountant.pre_check()
        assert accountant.can_spend() is False

    def test_frozen_over_limit(self, accountant):
        """Spending over limit raises BudgetExceeded."""
        accountant.record_call("m", 0, 0, 5.00, "w")
        with pytest.raises(BudgetExceeded):
            accountant.pre_check()

    def test_daily_report(self, accountant):
        """Daily report contains expected fields and breakdown."""
        accountant.record_call("model-a", 100, 50, 0.10, "worker-1")
        accountant.record_call("model-b", 200, 100, 0.20, "worker-2")
        accountant.record_call("model-a", 150, 75, 0.05, "worker-1")

        report = accountant.daily_report()
        assert report["total_spent"] == pytest.approx(0.35)
        assert report["daily_limit"] == 3.00
        assert report["remaining"] == pytest.approx(2.65)
        assert report["call_count"] == 3
        assert report["by_worker"]["worker-1"] == pytest.approx(0.15)
        assert report["by_worker"]["worker-2"] == pytest.approx(0.20)
        assert report["by_model"]["model-a"] == pytest.approx(0.15)
        assert report["by_model"]["model-b"] == pytest.approx(0.20)
        assert report["total_tokens_in"] == 450
        assert report["total_tokens_out"] == 225
