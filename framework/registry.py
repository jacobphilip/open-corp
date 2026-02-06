"""Operation registry — manages multiple open-corp projects via ~/.open-corp/."""

import json
from pathlib import Path

from framework.exceptions import RegistryError


class OperationRegistry:
    """JSON-backed name→path mapping for multi-project management."""

    def __init__(self, registry_dir: Path | None = None):
        self.registry_dir = Path(registry_dir) if registry_dir else Path.home() / ".open-corp"
        self._registry_file = self.registry_dir / "registry.json"
        self._active_file = self.registry_dir / "active"

    def _load(self) -> dict[str, str]:
        """Load registry from JSON. Returns empty dict on missing/corrupt file."""
        if not self._registry_file.exists():
            return {}
        try:
            data = json.loads(self._registry_file.read_text())
            if isinstance(data, dict):
                return data
            return {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        """Write registry to JSON, creating parent dirs if needed."""
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self._registry_file.write_text(json.dumps(data, indent=2))

    def register(self, name: str, path: str | Path) -> None:
        """Add an operation to the registry."""
        data = self._load()
        data[name] = str(Path(path).resolve())
        self._save(data)

    def unregister(self, name: str) -> None:
        """Remove an operation. Clears active if it was the active one."""
        data = self._load()
        if name not in data:
            raise RegistryError(f"Operation '{name}' not found in registry",
                                suggestion="Run 'corp ops list' to see registered operations.")
        del data[name]
        self._save(data)
        # Clear active if it was this operation
        if self.get_active() == name:
            self._active_file.unlink(missing_ok=True)

    def list_operations(self) -> dict[str, str]:
        """Return all registered operations as {name: path}."""
        return self._load()

    def get_path(self, name: str) -> Path | None:
        """Get the resolved path for an operation, or None if not found."""
        data = self._load()
        path_str = data.get(name)
        return Path(path_str) if path_str else None

    def set_active(self, name: str) -> None:
        """Set the active operation. Raises RegistryError if not registered."""
        data = self._load()
        if name not in data:
            raise RegistryError(f"Operation '{name}' not registered",
                                suggestion="Register it first with 'corp ops create'.")
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self._active_file.write_text(name)

    def get_active(self) -> str | None:
        """Get the name of the active operation, or None."""
        if not self._active_file.exists():
            return None
        try:
            name = self._active_file.read_text().strip()
            return name if name else None
        except OSError:
            return None

    def get_active_path(self) -> Path | None:
        """Get the path of the active operation, or None."""
        name = self.get_active()
        if name is None:
            return None
        return self.get_path(name)
