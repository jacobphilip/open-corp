"""Tests for framework/task_router.py — smart task routing."""

import json

import pytest
import yaml

from framework.config import ProjectConfig
from framework.hr import HR
from framework.task_router import TaskRouter
from framework.worker import Worker


def _create_worker(workers_dir, name, role, skills, level=1):
    """Create a worker directory with specific skills."""
    worker_dir = workers_dir / name
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "profile.md").write_text(f"# {name}\nA {role} worker.")
    (worker_dir / "memory.json").write_text("[]")
    (worker_dir / "performance.json").write_text("[]")
    (worker_dir / "skills.yaml").write_text(yaml.dump({"role": role, "skills": skills}))
    (worker_dir / "config.yaml").write_text(yaml.dump({"level": level, "max_context_tokens": 2000}))


class TestTaskRouter:
    def test_select_best_skill_match(self, tmp_project, config):
        """Worker with matching skills wins."""
        _create_worker(tmp_project / "workers", "analyst", "data-analyst",
                        ["data", "analysis", "statistics"])
        _create_worker(tmp_project / "workers", "writer", "content-writer",
                        ["writing", "content", "marketing"])

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best = router.select_worker("analyze data trends")
        assert best == "analyst"

    def test_select_no_workers(self, tmp_project, config):
        """Returns None when no workers exist."""
        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        assert router.select_worker("do something") is None

    def test_select_performance_factor(self, tmp_project, config):
        """Higher-rated worker preferred when skills are equal."""
        _create_worker(tmp_project / "workers", "w1", "general", ["general"])
        _create_worker(tmp_project / "workers", "w2", "general", ["general"])

        # Give w2 higher ratings
        w2 = Worker("w2", tmp_project, config)
        for i in range(5):
            w2.record_performance(f"t{i}", "completed", rating=5)

        w1 = Worker("w1", tmp_project, config)
        for i in range(5):
            w1.record_performance(f"t{i}", "completed", rating=2)

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best = router.select_worker("general task")
        assert best == "w2"

    def test_select_seniority_factor(self, tmp_project, config):
        """Higher-level worker gets bonus."""
        _create_worker(tmp_project / "workers", "junior", "dev", ["dev"], level=1)
        _create_worker(tmp_project / "workers", "senior", "dev", ["dev"], level=5)

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best = router.select_worker("dev task")
        assert best == "senior"

    def test_select_specified_workers(self, tmp_project, config):
        """Only considers given worker list."""
        _create_worker(tmp_project / "workers", "a", "analyst", ["analysis"])
        _create_worker(tmp_project / "workers", "b", "writer", ["writing"])

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best = router.select_worker("analysis task", workers=["b"])
        assert best == "b"

    def test_select_handles_worker_error(self, tmp_project, config):
        """Gracefully skips broken worker."""
        _create_worker(tmp_project / "workers", "good", "analyst", ["analysis"])
        # Create broken worker (missing profile)
        bad_dir = tmp_project / "workers" / "bad"
        bad_dir.mkdir(parents=True)
        # Missing required files — Worker() will still load (profile defaults)
        (bad_dir / "profile.md").write_text("# bad")
        (bad_dir / "memory.json").write_text("[]")
        (bad_dir / "performance.json").write_text("[]")
        (bad_dir / "skills.yaml").write_text("invalid: yaml: [broken")
        (bad_dir / "config.yaml").write_text(yaml.dump({"level": 1}))

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best = router.select_worker("analysis work")
        assert best is not None  # Should still find a worker

    def test_select_empty_description(self, tmp_project, config):
        """Returns a worker even with empty description (doesn't crash)."""
        _create_worker(tmp_project / "workers", "w1", "general", ["general"])

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best = router.select_worker("")
        assert best == "w1"

    def test_select_equal_workers(self, tmp_project, config):
        """Deterministic pick when workers are equal."""
        _create_worker(tmp_project / "workers", "a", "general", ["general"])
        _create_worker(tmp_project / "workers", "b", "general", ["general"])

        hr = HR(config, tmp_project)
        router = TaskRouter(config, hr)
        best1 = router.select_worker("general task")
        best2 = router.select_worker("general task")
        assert best1 == best2  # Same result both times
