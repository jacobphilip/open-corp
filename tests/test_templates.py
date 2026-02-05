"""Tests for template validation — all templates have required files and valid content."""

import shutil
from pathlib import Path

import pytest
import yaml

from framework.config import ProjectConfig
from framework.hr import HR

# Path to the real templates directory in the project
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
TEMPLATE_NAMES = sorted(d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir())


class TestTemplates:
    def test_all_templates_have_required_files(self):
        """Every template dir must contain profile.md, skills.yaml, config.yaml."""
        required = {"profile.md", "skills.yaml", "config.yaml"}
        for name in TEMPLATE_NAMES:
            tpl_dir = TEMPLATES_DIR / name
            files = {f.name for f in tpl_dir.iterdir()}
            missing = required - files
            assert not missing, f"Template '{name}' missing: {missing}"

    def test_template_config_valid_yaml(self):
        """config.yaml parses and has 'level' key."""
        for name in TEMPLATE_NAMES:
            data = yaml.safe_load((TEMPLATES_DIR / name / "config.yaml").read_text())
            assert isinstance(data, dict), f"Template '{name}' config.yaml is not a dict"
            assert "level" in data, f"Template '{name}' config.yaml missing 'level'"

    def test_template_skills_valid_yaml(self):
        """skills.yaml parses and has 'role' and 'skills' keys."""
        for name in TEMPLATE_NAMES:
            data = yaml.safe_load((TEMPLATES_DIR / name / "skills.yaml").read_text())
            assert isinstance(data, dict), f"Template '{name}' skills.yaml is not a dict"
            assert "role" in data, f"Template '{name}' skills.yaml missing 'role'"
            assert "skills" in data, f"Template '{name}' skills.yaml missing 'skills'"

    def test_template_profile_nonempty(self):
        """profile.md is non-empty."""
        for name in TEMPLATE_NAMES:
            text = (TEMPLATES_DIR / name / "profile.md").read_text()
            assert len(text.strip()) > 0, f"Template '{name}' profile.md is empty"

    def test_hire_from_each_template(self, tmp_project, config):
        """HR can hire a worker from every template."""
        # Copy real templates into temp project
        shutil.copytree(TEMPLATES_DIR, tmp_project / "templates", dirs_exist_ok=True)
        hr = HR(config, tmp_project)

        for name in TEMPLATE_NAMES:
            worker_name = f"test-{name}"
            worker = hr.hire_from_template(name, worker_name)
            assert worker.name == worker_name
            assert (tmp_project / "workers" / worker_name).exists()
