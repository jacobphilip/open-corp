"""Project configuration loader — reads charter.yaml + .env."""

import warnings
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from framework.exceptions import ConfigError


@dataclass
class BudgetConfig:
    daily_limit: float
    currency: str = "USD"
    thresholds: dict[str, float] = field(default_factory=lambda: {
        "normal": 0.60,
        "caution": 0.80,
        "austerity": 0.95,
        "critical": 1.00,
    })


@dataclass
class ModelTier:
    name: str
    models: list[str]
    description: str = ""


@dataclass
class WorkerDefaults:
    starting_level: int = 1
    max_context_tokens: int = 2000
    model: str = "deepseek/deepseek-chat"
    honest_ai: bool = True
    max_history_messages: int = 50
    default_max_tokens: int | None = None


@dataclass
class PromotionRules:
    min_tasks: int = 5
    promote_threshold: float = 4.0
    demote_threshold: float = 2.0
    review_window: int = 20


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = ""  # empty = stderr only


@dataclass
class RetentionConfig:
    events_days: int = 90
    spending_days: int = 90
    workflows_days: int = 90
    performance_max: int = 100


@dataclass
class SecurityConfig:
    webhook_rate_limit: float = 10.0
    webhook_rate_burst: int = 20
    dashboard_rate_limit: float = 30.0
    dashboard_rate_burst: int = 60


_DEFAULT_BLOCKED_HOSTS = [
    "169.254.169.254",
    "metadata.google.internal",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]


@dataclass
class ToolsConfig:
    enabled: bool = True
    max_tool_iterations: int = 10
    tool_result_max_chars: int = 4000
    shell_timeout: int = 30
    http_timeout: int = 15
    blocked_hosts: list[str] = field(default_factory=lambda: list(_DEFAULT_BLOCKED_HOSTS))


@dataclass
class GitConfig:
    auto_commit: bool = True
    auto_push: bool = True
    remote: str = "origin"
    branch: str = "main"


@dataclass
class ProjectConfig:
    name: str
    owner: str
    mission: str
    project_dir: Path
    budget: BudgetConfig
    model_tiers: dict[str, ModelTier] = field(default_factory=dict)
    git: GitConfig = field(default_factory=GitConfig)
    worker_defaults: WorkerDefaults = field(default_factory=WorkerDefaults)
    promotion_rules: PromotionRules = field(default_factory=PromotionRules)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    marketplace_url: str = ""
    board_enabled: bool = False

    @staticmethod
    def load(project_dir: Path) -> "ProjectConfig":
        """Load project configuration from charter.yaml and .env in project_dir."""
        project_dir = Path(project_dir)

        # Load .env if present
        env_file = project_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            # Warn if .env is group/other readable
            try:
                mode = env_file.stat().st_mode
                if mode & 0o077:
                    warnings.warn(
                        f".env file at {env_file} is group/other readable (mode {oct(mode)}). "
                        "Run: chmod 600 .env",
                        stacklevel=2,
                    )
            except OSError:
                pass

        # Load charter.yaml
        charter_path = project_dir / "charter.yaml"
        if not charter_path.exists():
            raise ConfigError(
                f"charter.yaml not found in {project_dir}",
                suggestion="Run 'corp init' to create a new project.",
            )

        try:
            raw = yaml.safe_load(charter_path.read_text())
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in charter.yaml: {e}")

        if not isinstance(raw, dict):
            raise ConfigError("charter.yaml must be a YAML mapping")

        # Parse project section
        project = raw.get("project")
        if not project:
            raise ConfigError(
                "charter.yaml missing 'project' section",
                suggestion="Add a 'project' section with name, owner, and mission to charter.yaml.",
            )

        for req in ("name", "owner", "mission"):
            if req not in project:
                raise ConfigError(
                    f"charter.yaml project.{req} is required",
                    suggestion=f"Add '{req}' to the project section in charter.yaml.",
                )

        # Parse budget
        budget_raw = raw.get("budget")
        if not budget_raw:
            raise ConfigError(
                "charter.yaml missing 'budget' section",
                suggestion="Add a 'budget' section with daily_limit to charter.yaml.",
            )
        if "daily_limit" not in budget_raw:
            raise ConfigError(
                "charter.yaml budget.daily_limit is required",
                suggestion="Add 'daily_limit' to the budget section in charter.yaml.",
            )

        budget = BudgetConfig(
            daily_limit=float(budget_raw["daily_limit"]),
            currency=budget_raw.get("currency", "USD"),
            thresholds=budget_raw.get("thresholds", {
                "normal": 0.60,
                "caution": 0.80,
                "austerity": 0.95,
                "critical": 1.00,
            }),
        )

        # Parse model tiers
        model_tiers: dict[str, ModelTier] = {}
        models_raw = raw.get("models", {}).get("tiers", {})
        for tier_name, tier_data in models_raw.items():
            model_tiers[tier_name] = ModelTier(
                name=tier_name,
                models=tier_data.get("models", []),
                description=tier_data.get("for", ""),
            )

        # Parse git config
        git_raw = raw.get("git", {})
        git = GitConfig(
            auto_commit=git_raw.get("auto_commit", True),
            auto_push=git_raw.get("auto_push", True),
            remote=git_raw.get("remote", "origin"),
            branch=git_raw.get("branch", "main"),
        )

        # Parse worker defaults
        wd_raw = raw.get("worker_defaults", {})
        default_max_tokens_raw = wd_raw.get("default_max_tokens")
        default_max_tokens = int(default_max_tokens_raw) if default_max_tokens_raw is not None else None
        worker_defaults = WorkerDefaults(
            starting_level=wd_raw.get("starting_level", 1),
            max_context_tokens=wd_raw.get("max_context_tokens", 2000),
            model=wd_raw.get("model", "deepseek/deepseek-chat"),
            honest_ai=wd_raw.get("honest_ai", True),
            max_history_messages=wd_raw.get("max_history_messages", 50),
            default_max_tokens=default_max_tokens,
        )

        # Promotion rules
        pr_raw = raw.get("promotion_rules", {})
        promotion_rules = PromotionRules(
            min_tasks=pr_raw.get("min_tasks", 5),
            promote_threshold=float(pr_raw.get("promote_threshold", 4.0)),
            demote_threshold=float(pr_raw.get("demote_threshold", 2.0)),
            review_window=pr_raw.get("review_window", 20),
        )

        # Logging config
        log_raw = raw.get("logging", {})
        logging_config = LoggingConfig(
            level=log_raw.get("level", "INFO"),
            file=log_raw.get("file", ""),
        )

        # Retention config
        ret_raw = raw.get("retention", {})
        retention = RetentionConfig(
            events_days=ret_raw.get("events_days", 90),
            spending_days=ret_raw.get("spending_days", 90),
            workflows_days=ret_raw.get("workflows_days", 90),
            performance_max=ret_raw.get("performance_max", 100),
        )

        # Marketplace
        marketplace_url = raw.get("marketplace", {}).get("registry_url", "")

        # Security config
        sec_raw = raw.get("security", {})
        security = SecurityConfig(
            webhook_rate_limit=float(sec_raw.get("webhook_rate_limit", 10.0)),
            webhook_rate_burst=int(sec_raw.get("webhook_rate_burst", 20)),
            dashboard_rate_limit=float(sec_raw.get("dashboard_rate_limit", 30.0)),
            dashboard_rate_burst=int(sec_raw.get("dashboard_rate_burst", 60)),
        )

        # Tools config
        tools_raw = raw.get("tools", {})
        tools_blocked = tools_raw.get("blocked_hosts", list(_DEFAULT_BLOCKED_HOSTS))
        tools = ToolsConfig(
            enabled=tools_raw.get("enabled", True),
            max_tool_iterations=int(tools_raw.get("max_tool_iterations", 10)),
            tool_result_max_chars=int(tools_raw.get("tool_result_max_chars", 4000)),
            shell_timeout=int(tools_raw.get("shell_timeout", 30)),
            http_timeout=int(tools_raw.get("http_timeout", 15)),
            blocked_hosts=tools_blocked,
        )

        # Board
        board_enabled = raw.get("board", {}).get("enabled", False)

        return ProjectConfig(
            name=project["name"],
            owner=project["owner"],
            mission=project["mission"],
            project_dir=project_dir,
            budget=budget,
            model_tiers=model_tiers,
            git=git,
            worker_defaults=worker_defaults,
            promotion_rules=promotion_rules,
            logging=logging_config,
            retention=retention,
            security=security,
            tools=tools,
            marketplace_url=marketplace_url,
            board_enabled=board_enabled,
        )
