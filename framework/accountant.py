"""Accountant — budget guardrail that wraps all API calls."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from tinydb import Query

from framework.config import ProjectConfig
from framework.db import get_db
from framework.exceptions import BudgetExceeded


class BudgetStatus(Enum):
    GREEN = "green"
    CAUTION = "caution"
    AUSTERITY = "austerity"
    CRITICAL = "critical"
    FROZEN = "frozen"


class Accountant:
    """Tracks spending against daily budget limits using TinyDB."""

    def __init__(self, config: ProjectConfig, db_path: Path | None = None):
        self.config = config
        self.budget = config.budget
        if db_path is None:
            db_path = config.project_dir / "data" / "spending.json"
        self.db, self._db_lock = get_db(db_path)
        self.table = self.db.table("spending")

    def _today(self) -> str:
        """Today's date string in UTC."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def today_spent(self) -> float:
        """Sum of today's costs."""
        Record = Query()
        with self._db_lock:
            records = self.table.search(Record.date == self._today())
        return sum(r.get("cost", 0.0) for r in records)

    def _usage_ratio(self) -> float:
        """Fraction of daily budget used today."""
        if self.budget.daily_limit <= 0:
            return 1.0
        return self.today_spent() / self.budget.daily_limit

    def pre_check(self) -> BudgetStatus:
        """Check budget status before an API call. Raises BudgetExceeded if FROZEN."""
        ratio = self._usage_ratio()
        thresholds = self.budget.thresholds

        if ratio >= thresholds.get("critical", 1.0):
            status = BudgetStatus.FROZEN
        elif ratio >= thresholds.get("austerity", 0.95):
            status = BudgetStatus.CRITICAL
        elif ratio >= thresholds.get("caution", 0.80):
            status = BudgetStatus.AUSTERITY
        elif ratio >= thresholds.get("normal", 0.60):
            status = BudgetStatus.CAUTION
        else:
            status = BudgetStatus.GREEN

        if status == BudgetStatus.FROZEN:
            remaining = max(0.0, self.budget.daily_limit - self.today_spent())
            raise BudgetExceeded(remaining, self.budget.daily_limit)

        return status

    def can_spend(self) -> bool:
        """True if budget is not frozen."""
        try:
            self.pre_check()
            return True
        except BudgetExceeded:
            return False

    def record_call(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
        worker: str = "system",
    ) -> None:
        """Record an API call to spending ledger."""
        with self._db_lock:
            self.table.insert({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "date": self._today(),
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost": cost,
                "worker": worker,
            })

    def daily_report(self) -> dict:
        """Breakdown of today's spending by worker and model."""
        Record = Query()
        with self._db_lock:
            records = self.table.search(Record.date == self._today())

        by_worker: dict[str, float] = {}
        by_model: dict[str, float] = {}
        total_tokens_in = 0
        total_tokens_out = 0

        for r in records:
            w = r.get("worker", "system")
            m = r.get("model", "unknown")
            c = r.get("cost", 0.0)
            by_worker[w] = by_worker.get(w, 0.0) + c
            by_model[m] = by_model.get(m, 0.0) + c
            total_tokens_in += r.get("tokens_in", 0)
            total_tokens_out += r.get("tokens_out", 0)

        spent = self.today_spent()
        return {
            "date": self._today(),
            "total_spent": spent,
            "daily_limit": self.budget.daily_limit,
            "remaining": max(0.0, self.budget.daily_limit - spent),
            "usage_ratio": self._usage_ratio(),
            "status": self.pre_check().value if self.can_spend() else "frozen",
            "by_worker": by_worker,
            "by_model": by_model,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "call_count": len(records),
        }
