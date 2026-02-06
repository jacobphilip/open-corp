"""Tests for framework/registry.py — operation registry."""

import json

import pytest

from framework.exceptions import RegistryError
from framework.registry import OperationRegistry


@pytest.fixture
def registry(tmp_path):
    """Create a registry using a temp directory."""
    return OperationRegistry(registry_dir=tmp_path / ".open-corp")


class TestOperationRegistry:
    def test_register_creates_entry(self, registry, tmp_path):
        """Name→path stored in JSON."""
        registry.register("proj1", tmp_path / "proj1")
        ops = registry.list_operations()
        assert "proj1" in ops
        assert str((tmp_path / "proj1").resolve()) == ops["proj1"]

    def test_register_multiple(self, registry, tmp_path):
        """Multiple operations coexist."""
        registry.register("a", tmp_path / "a")
        registry.register("b", tmp_path / "b")
        ops = registry.list_operations()
        assert len(ops) == 2
        assert "a" in ops
        assert "b" in ops

    def test_unregister_removes_entry(self, registry, tmp_path):
        """Entry removed from JSON."""
        registry.register("proj", tmp_path / "proj")
        registry.unregister("proj")
        assert "proj" not in registry.list_operations()

    def test_unregister_not_found(self, registry):
        """RegistryError raised for unknown name."""
        with pytest.raises(RegistryError, match="not found"):
            registry.unregister("ghost")

    def test_unregister_clears_active(self, registry, tmp_path):
        """If active was unregistered, active is cleared."""
        registry.register("proj", tmp_path / "proj")
        registry.set_active("proj")
        assert registry.get_active() == "proj"
        registry.unregister("proj")
        assert registry.get_active() is None

    def test_list_operations_empty(self, registry):
        """Empty dict when no registry file exists."""
        assert registry.list_operations() == {}

    def test_list_operations_with_data(self, registry, tmp_path):
        """Returns all registered operations."""
        registry.register("x", tmp_path / "x")
        registry.register("y", tmp_path / "y")
        ops = registry.list_operations()
        assert set(ops.keys()) == {"x", "y"}

    def test_get_path_exists(self, registry, tmp_path):
        """Returns resolved Path for registered operation."""
        registry.register("proj", tmp_path / "proj")
        path = registry.get_path("proj")
        assert path == (tmp_path / "proj").resolve()

    def test_get_path_not_found(self, registry):
        """Returns None for unregistered operation."""
        assert registry.get_path("missing") is None

    def test_set_active_success(self, registry, tmp_path):
        """Active file written correctly."""
        registry.register("proj", tmp_path / "proj")
        registry.set_active("proj")
        assert registry.get_active() == "proj"

    def test_set_active_not_registered(self, registry):
        """RegistryError raised for unregistered operation."""
        with pytest.raises(RegistryError, match="not registered"):
            registry.set_active("ghost")

    def test_get_active_none(self, registry):
        """None when no active file exists."""
        assert registry.get_active() is None

    def test_get_active_path_round_trip(self, registry, tmp_path):
        """set_active → get_active_path returns correct path."""
        registry.register("proj", tmp_path / "proj")
        registry.set_active("proj")
        path = registry.get_active_path()
        assert path == (tmp_path / "proj").resolve()

    def test_corrupt_registry_json(self, registry):
        """Returns empty dict gracefully on corrupt JSON."""
        registry.registry_dir.mkdir(parents=True, exist_ok=True)
        (registry.registry_dir / "registry.json").write_text("not valid json{{{")
        assert registry.list_operations() == {}

    def test_registry_dir_created_on_write(self, tmp_path):
        """Parent dirs auto-created when writing."""
        deep_dir = tmp_path / "a" / "b" / "c"
        reg = OperationRegistry(registry_dir=deep_dir)
        reg.register("proj", tmp_path / "proj")
        assert deep_dir.exists()
        assert "proj" in reg.list_operations()
