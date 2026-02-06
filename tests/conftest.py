"""Shared test fixtures."""

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig
from framework.events import EventLog
from framework.hr import HR
from framework.router import Router


CHARTER_YAML = {
    "project": {
        "name": "Test Project",
        "owner": "Test Owner",
        "mission": "Testing the framework",
    },
    "budget": {
        "daily_limit": 3.00,
        "currency": "USD",
        "thresholds": {
            "normal": 0.60,
            "caution": 0.80,
            "austerity": 0.95,
            "critical": 1.00,
        },
    },
    "models": {
        "tiers": {
            "cheap": {
                "models": ["deepseek/deepseek-chat", "mistralai/mistral-tiny"],
                "for": "Simple tasks",
            },
            "mid": {
                "models": ["anthropic/claude-sonnet-4-20250514"],
                "for": "Complex tasks",
            },
            "premium": {
                "models": ["anthropic/claude-opus-4-5-20251101"],
                "for": "Board-level decisions",
            },
        },
    },
    "git": {"auto_commit": False, "auto_push": False},
    "worker_defaults": {
        "starting_level": 1,
        "max_context_tokens": 2000,
        "model": "deepseek/deepseek-chat",
        "honest_ai": True,
    },
    "promotion_rules": {
        "min_tasks": 5,
        "promote_threshold": 4.0,
        "demote_threshold": 2.0,
        "review_window": 20,
    },
}


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with charter.yaml."""
    charter_path = tmp_path / "charter.yaml"
    charter_path.write_text(yaml.dump(CHARTER_YAML))
    (tmp_path / "data").mkdir()
    (tmp_path / "workers").mkdir()
    (tmp_path / "templates").mkdir()
    return tmp_path


@pytest.fixture
def config(tmp_project):
    """Load a ProjectConfig from the temp project."""
    return ProjectConfig.load(tmp_project)


@pytest.fixture
def accountant(config):
    """Create an Accountant with the test config."""
    return Accountant(config)


@pytest.fixture
def router(config, accountant):
    """Create a Router with a dummy API key."""
    return Router(config, accountant, api_key="test-key")


@pytest.fixture
def hr(config, tmp_project):
    """Create an HR instance."""
    return HR(config, tmp_project)


@pytest.fixture
def event_log(tmp_project):
    """Create an EventLog in the temp project."""
    return EventLog(tmp_project / "data" / "events.json")


@pytest.fixture
def create_template(tmp_project):
    """Factory fixture to create template directories."""
    def _create(name="researcher"):
        tpl_dir = tmp_project / "templates" / name
        tpl_dir.mkdir(parents=True, exist_ok=True)
        (tpl_dir / "profile.md").write_text(f"# {name}\nA {name} worker.")
        (tpl_dir / "skills.yaml").write_text(yaml.dump({"role": name, "skills": [name]}))
        (tpl_dir / "config.yaml").write_text(yaml.dump({"level": 1, "max_context_tokens": 2000}))
        return tpl_dir
    return _create


@pytest.fixture
def create_worker(tmp_project):
    """Factory fixture to create worker directories."""
    def _create(name="alice", level=1, role="tester"):
        worker_dir = tmp_project / "workers" / name
        worker_dir.mkdir(parents=True, exist_ok=True)
        (worker_dir / "profile.md").write_text(f"# {name}\nA {role} worker.")
        (worker_dir / "memory.json").write_text("[]")
        (worker_dir / "performance.json").write_text("[]")
        (worker_dir / "skills.yaml").write_text(yaml.dump({"role": role, "skills": [role]}))
        (worker_dir / "config.yaml").write_text(yaml.dump({"level": level, "max_context_tokens": 2000}))
        return worker_dir
    return _create
