"""Shared test fixtures."""

import shutil
import tempfile
from pathlib import Path

import pytest
import yaml

from framework.accountant import Accountant
from framework.config import ProjectConfig


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
