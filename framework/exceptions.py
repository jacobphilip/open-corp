"""Shared exceptions for the open-corp framework."""


class ConfigError(Exception):
    """Raised when project configuration is invalid or missing."""

    def __init__(self, message: str, suggestion: str = ""):
        self.message = message
        self.suggestion = suggestion
        full = message
        if suggestion:
            full += f"\n  Try: {suggestion}"
        super().__init__(full)


class BudgetExceeded(Exception):
    """Raised when daily budget is exhausted."""

    def __init__(self, remaining: float, daily_limit: float, suggestion: str = ""):
        self.remaining = remaining
        self.daily_limit = daily_limit
        self.suggestion = suggestion or "Wait until tomorrow or increase daily_limit in charter.yaml."
        msg = f"Budget frozen: ${remaining:.4f} remaining of ${daily_limit:.2f} daily limit"
        msg += f"\n  Try: {self.suggestion}"
        super().__init__(msg)


class ModelUnavailable(Exception):
    """Raised when no models in any tier are reachable."""

    def __init__(self, model: str, tier: str, tried: list[str], suggestion: str = ""):
        self.model = model
        self.tier = tier
        self.tried = tried
        self.suggestion = suggestion or "Check model tiers in charter.yaml and OPENROUTER_API_KEY in .env."
        msg = f"Model '{model}' unavailable in tier '{tier}'. Tried: {tried}"
        msg += f"\n  Try: {self.suggestion}"
        super().__init__(msg)


class WorkerNotFound(Exception):
    """Raised when a worker directory doesn't exist."""

    def __init__(self, name: str, suggestion: str = ""):
        self.name = name
        self.suggestion = suggestion or "Run 'corp workers' to see available workers, or 'corp hire' to create one."
        msg = f"Worker '{name}' not found in workers/ directory"
        msg += f"\n  Try: {self.suggestion}"
        super().__init__(msg)


class TrainingError(Exception):
    """Raised when worker training fails."""

    def __init__(self, source: str, reason: str, suggestion: str = ""):
        self.source = source
        self.reason = reason
        self.suggestion = suggestion
        msg = f"Training failed for '{source}': {reason}"
        if suggestion:
            msg += f"\n  Try: {suggestion}"
        super().__init__(msg)
