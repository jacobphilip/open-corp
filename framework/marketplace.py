"""Marketplace — fetch, search, and install templates from a remote registry."""

import shutil
from pathlib import Path

import httpx
import yaml

from framework.exceptions import MarketplaceError


class Marketplace:
    """Client for the open-corp template marketplace."""

    def __init__(self, registry_url: str, templates_dir: Path):
        self.registry_url = registry_url
        self.templates_dir = Path(templates_dir)
        self._cache: list[dict] | None = None

    def _fetch_registry(self) -> list[dict]:
        """Fetch and parse the remote YAML registry. Cached per session."""
        if self._cache is not None:
            return self._cache

        if not self.registry_url:
            raise MarketplaceError("No marketplace registry URL configured",
                                   suggestion="Set marketplace.registry_url in charter.yaml.")

        try:
            response = httpx.get(self.registry_url, follow_redirects=True, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise MarketplaceError(f"Failed to fetch registry: {e}",
                                   suggestion="Check your network connection and registry URL.")

        try:
            data = yaml.safe_load(response.text)
        except yaml.YAMLError as e:
            raise MarketplaceError(f"Invalid registry YAML: {e}")

        if not isinstance(data, dict) or "templates" not in data:
            raise MarketplaceError("Registry YAML must contain a 'templates' list")

        templates = data["templates"]
        if not isinstance(templates, list):
            raise MarketplaceError("Registry 'templates' must be a list")

        self._cache = templates
        return templates

    def list_templates(self) -> list[dict]:
        """List all available templates from the registry."""
        return self._fetch_registry()

    def search(self, query: str) -> list[dict]:
        """Search templates by name, description, or tags (case-insensitive)."""
        query_lower = query.lower()
        results = []
        for tpl in self._fetch_registry():
            name = tpl.get("name", "").lower()
            desc = tpl.get("description", "").lower()
            tags = [t.lower() for t in tpl.get("tags", [])]
            if (query_lower in name or query_lower in desc or
                    any(query_lower in tag for tag in tags)):
                results.append(tpl)
        return results

    def info(self, name: str) -> dict | None:
        """Get info for a specific template by name."""
        for tpl in self._fetch_registry():
            if tpl.get("name") == name:
                return tpl
        return None

    def install(self, name: str) -> Path:
        """Download and install a template to templates_dir.

        Downloads profile.md and skills.yaml (required) and config.yaml (optional).
        Raises MarketplaceError on failure with cleanup.
        """
        tpl = self.info(name)
        if tpl is None:
            raise MarketplaceError(f"Template '{name}' not found in registry")

        target_dir = self.templates_dir / name
        if target_dir.exists():
            raise MarketplaceError(f"Template '{name}' already exists at {target_dir}",
                                   suggestion="Remove it first or choose a different name.")

        base_url = tpl.get("url", "")
        if not base_url:
            raise MarketplaceError(f"Template '{name}' has no download URL")

        target_dir.mkdir(parents=True, exist_ok=True)

        required_files = ["profile.md", "skills.yaml"]
        optional_files = ["config.yaml"]

        try:
            for filename in required_files:
                url = f"{base_url}/{filename}"
                resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                resp.raise_for_status()
                (target_dir / filename).write_text(resp.text)

            for filename in optional_files:
                url = f"{base_url}/{filename}"
                try:
                    resp = httpx.get(url, follow_redirects=True, timeout=15.0)
                    resp.raise_for_status()
                    (target_dir / filename).write_text(resp.text)
                except httpx.HTTPError:
                    pass  # Optional file — skip on failure

        except httpx.HTTPError as e:
            # Cleanup on failure
            shutil.rmtree(target_dir, ignore_errors=True)
            raise MarketplaceError(f"Failed to download template '{name}': {e}",
                                   suggestion="Check network and try again.")

        return target_dir
