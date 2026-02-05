"""Shared exceptions for the open-corp framework."""


class ConfigError(Exception):
    """Raised when project configuration is invalid or missing."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class BudgetExceeded(Exception):
    """Raised when daily budget is exhausted."""

    def __init__(self, remaining: float, daily_limit: float):
        self.remaining = remaining
        self.daily_limit = daily_limit
        super().__init__(
            f"Budget frozen: ${remaining:.4f} remaining of ${daily_limit:.2f} daily limit"
        )


class ModelUnavailable(Exception):
    """Raised when no models in any tier are reachable."""

    def __init__(self, model: str, tier: str, tried: list[str]):
        self.model = model
        self.tier = tier
        self.tried = tried
        super().__init__(
            f"Model '{model}' unavailable in tier '{tier}'. Tried: {tried}"
        )


class WorkerNotFound(Exception):
    """Raised when a worker directory doesn't exist."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Worker '{name}' not found in workers/ directory")


class TrainingError(Exception):
    """Raised when worker training fails."""

    def __init__(self, source: str, reason: str):
        self.source = source
        self.reason = reason
        super().__init__(f"Training failed for '{source}': {reason}")
