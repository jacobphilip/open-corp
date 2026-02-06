"""Tests for framework/config.py."""

import pytest
import yaml

from framework.config import ProjectConfig
from framework.exceptions import ConfigError


class TestProjectConfig:
    def test_load_valid_charter(self, tmp_project, config):
        """Loading a valid charter.yaml produces correct config."""
        assert config.name == "Test Project"
        assert config.owner == "Test Owner"
        assert config.mission == "Testing the framework"
        assert config.budget.daily_limit == 3.00
        assert config.budget.currency == "USD"
        assert "cheap" in config.model_tiers
        assert "mid" in config.model_tiers
        assert "premium" in config.model_tiers
        assert config.model_tiers["cheap"].models[0] == "deepseek/deepseek-chat"
        assert config.worker_defaults.starting_level == 1
        assert config.worker_defaults.honest_ai is True
        assert config.git.auto_commit is False

    def test_missing_charter_file(self, tmp_path):
        """Raises ConfigError when charter.yaml doesn't exist."""
        with pytest.raises(ConfigError, match="charter.yaml not found"):
            ProjectConfig.load(tmp_path)

    def test_missing_project_section(self, tmp_path):
        """Raises ConfigError when 'project' section is missing."""
        (tmp_path / "charter.yaml").write_text(yaml.dump({"budget": {"daily_limit": 1.0}}))
        with pytest.raises(ConfigError, match="missing 'project' section"):
            ProjectConfig.load(tmp_path)

    def test_missing_budget_section(self, tmp_path):
        """Raises ConfigError when 'budget' section is missing."""
        charter = {"project": {"name": "X", "owner": "Y", "mission": "Z"}}
        (tmp_path / "charter.yaml").write_text(yaml.dump(charter))
        with pytest.raises(ConfigError, match="missing 'budget' section"):
            ProjectConfig.load(tmp_path)

    def test_missing_required_project_field(self, tmp_path):
        """Raises ConfigError when a required project field is missing."""
        charter = {
            "project": {"name": "X", "owner": "Y"},  # missing 'mission'
            "budget": {"daily_limit": 1.0},
        }
        (tmp_path / "charter.yaml").write_text(yaml.dump(charter))
        with pytest.raises(ConfigError, match="project.mission is required"):
            ProjectConfig.load(tmp_path)

    def test_bad_yaml(self, tmp_path):
        """Raises ConfigError for unparseable YAML."""
        (tmp_path / "charter.yaml").write_text(": bad: yaml: [")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            ProjectConfig.load(tmp_path)

    def test_defaults_when_optional_sections_missing(self, tmp_path):
        """Optional sections get sensible defaults."""
        charter = {
            "project": {"name": "X", "owner": "Y", "mission": "Z"},
            "budget": {"daily_limit": 5.0},
        }
        (tmp_path / "charter.yaml").write_text(yaml.dump(charter))
        config = ProjectConfig.load(tmp_path)
        assert config.git.auto_commit is True
        assert config.worker_defaults.starting_level == 1
        assert config.board_enabled is False
        assert len(config.model_tiers) == 0

    def test_max_history_messages_from_charter(self, tmp_path):
        """max_history_messages is parsed from charter.yaml."""
        charter = {
            "project": {"name": "X", "owner": "Y", "mission": "Z"},
            "budget": {"daily_limit": 5.0},
            "worker_defaults": {"max_history_messages": 20},
        }
        (tmp_path / "charter.yaml").write_text(yaml.dump(charter))
        config = ProjectConfig.load(tmp_path)
        assert config.worker_defaults.max_history_messages == 20

    def test_promotion_rules_from_charter(self, tmp_path):
        """PromotionRules parsed from charter.yaml promotion_rules section."""
        charter = {
            "project": {"name": "X", "owner": "Y", "mission": "Z"},
            "budget": {"daily_limit": 5.0},
            "promotion_rules": {
                "min_tasks": 10,
                "promote_threshold": 4.5,
                "demote_threshold": 1.5,
                "review_window": 30,
            },
        }
        (tmp_path / "charter.yaml").write_text(yaml.dump(charter))
        config = ProjectConfig.load(tmp_path)
        assert config.promotion_rules.min_tasks == 10
        assert config.promotion_rules.promote_threshold == 4.5
        assert config.promotion_rules.demote_threshold == 1.5
        assert config.promotion_rules.review_window == 30

    def test_marketplace_url_from_charter(self, tmp_path):
        """marketplace.registry_url parsed from charter.yaml."""
        charter = {
            "project": {"name": "X", "owner": "Y", "mission": "Z"},
            "budget": {"daily_limit": 5.0},
            "marketplace": {
                "registry_url": "https://example.com/registry.yaml",
            },
        }
        (tmp_path / "charter.yaml").write_text(yaml.dump(charter))
        config = ProjectConfig.load(tmp_path)
        assert config.marketplace_url == "https://example.com/registry.yaml"
