"""Tests for framework/hr.py."""

import json

import pytest
import yaml

from framework.exceptions import WorkerNotFound
from framework.hr import HR


def _create_template(templates_dir, name="researcher"):
    """Create a minimal template directory."""
    tpl_dir = templates_dir / name
    tpl_dir.mkdir(parents=True, exist_ok=True)
    (tpl_dir / "profile.md").write_text(f"# {name}\nA {name} worker.")
    (tpl_dir / "skills.yaml").write_text(yaml.dump({"role": name, "skills": [name]}))
    (tpl_dir / "config.yaml").write_text(yaml.dump({"level": 1, "max_context_tokens": 2000}))


class TestHR:
    def test_hire_from_template(self, tmp_project, config):
        """Hire from template copies files and creates worker."""
        _create_template(tmp_project / "templates", "researcher")
        hr = HR(config, tmp_project)
        worker = hr.hire_from_template("researcher", "alice")
        assert worker.name == "alice"
        assert (tmp_project / "workers" / "alice" / "profile.md").exists()
        assert (tmp_project / "workers" / "alice" / "memory.json").exists()

    def test_hire_from_template_not_found(self, tmp_project, config):
        """Raises FileNotFoundError for missing template."""
        hr = HR(config, tmp_project)
        with pytest.raises(FileNotFoundError, match="no-such-template"):
            hr.hire_from_template("no-such-template", "bob")

    def test_hire_duplicate_worker(self, tmp_project, config):
        """Raises FileExistsError when worker already exists."""
        _create_template(tmp_project / "templates", "researcher")
        hr = HR(config, tmp_project)
        hr.hire_from_template("researcher", "charlie")
        with pytest.raises(FileExistsError, match="charlie"):
            hr.hire_from_template("researcher", "charlie")

    def test_hire_from_scratch(self, tmp_project, config):
        """Hire from scratch creates all required files."""
        hr = HR(config, tmp_project)
        worker = hr.hire_from_scratch("dave", role="analyst", description="Data analysis")
        assert worker.name == "dave"
        assert (tmp_project / "workers" / "dave" / "profile.md").exists()
        assert (tmp_project / "workers" / "dave" / "skills.yaml").exists()
        assert (tmp_project / "workers" / "dave" / "config.yaml").exists()
        assert (tmp_project / "workers" / "dave" / "memory.json").exists()
        assert (tmp_project / "workers" / "dave" / "performance.json").exists()

        profile = (tmp_project / "workers" / "dave" / "profile.md").read_text()
        assert "analyst" in profile
        assert "Data analysis" in profile

    def test_list_workers(self, tmp_project, config):
        """list_workers returns all workers with metadata."""
        _create_template(tmp_project / "templates", "researcher")
        hr = HR(config, tmp_project)

        assert hr.list_workers() == []

        hr.hire_from_template("researcher", "w1")
        hr.hire_from_scratch("w2", role="writer")

        workers = hr.list_workers()
        assert len(workers) == 2
        names = [w["name"] for w in workers]
        assert "w1" in names
        assert "w2" in names

    def test_fire_worker(self, tmp_project, config):
        """Firing a worker removes their directory."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("victim", role="temp")
        assert (tmp_project / "workers" / "victim").exists()

        # Requires confirmation
        with pytest.raises(ValueError, match="confirm=True"):
            hr.fire("victim")

        hr.fire("victim", confirm=True)
        assert not (tmp_project / "workers" / "victim").exists()

    def test_fire_nonexistent(self, tmp_project, config):
        """Firing a non-existent worker raises WorkerNotFound."""
        hr = HR(config, tmp_project)
        with pytest.raises(WorkerNotFound, match="ghost"):
            hr.fire("ghost", confirm=True)

    def test_promote(self, tmp_project, config):
        """Promote increments level, capped at 5."""
        hr = HR(config, tmp_project)
        hr.hire_from_scratch("promo", role="climber")

        new_level = hr.promote("promo")
        assert new_level == 2

        cfg = yaml.safe_load((tmp_project / "workers" / "promo" / "config.yaml").read_text())
        assert cfg["level"] == 2

        # Promote to max
        for _ in range(10):
            new_level = hr.promote("promo")
        assert new_level == 5
