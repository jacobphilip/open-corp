"""Project configuration loader — reads charter.yaml + .env."""

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
    board_enabled: bool = False

    @staticmethod
    def load(project_dir: Path) -> "ProjectConfig":
        """Load project configuration from charter.yaml and .env in project_dir."""
        project_dir = Path(project_dir)

        # Load .env if present
        env_file = project_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)

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
        worker_defaults = WorkerDefaults(
            starting_level=wd_raw.get("starting_level", 1),
            max_context_tokens=wd_raw.get("max_context_tokens", 2000),
            model=wd_raw.get("model", "deepseek/deepseek-chat"),
            honest_ai=wd_raw.get("honest_ai", True),
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
            board_enabled=board_enabled,
        )
