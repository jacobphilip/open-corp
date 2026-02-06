"""Tests for framework/marketplace.py — template marketplace client."""

import httpx
import pytest
import respx
import yaml

from framework.exceptions import MarketplaceError
from framework.marketplace import Marketplace


REGISTRY_URL = "https://example.com/registry.yaml"
TEMPLATE_BASE = "https://raw.githubusercontent.com/open-corp/marketplace/main/templates"

SAMPLE_REGISTRY = {
    "templates": [
        {
            "name": "researcher",
            "description": "Research specialist for information gathering",
            "author": "open-corp",
            "tags": ["research", "analysis", "data"],
            "url": f"{TEMPLATE_BASE}/researcher",
        },
        {
            "name": "trader",
            "description": "Trading specialist for market analysis",
            "author": "open-corp",
            "tags": ["trading", "finance", "market"],
            "url": f"{TEMPLATE_BASE}/trader",
        },
    ],
}


@pytest.fixture
def mock_registry():
    """Context manager that mocks the registry fetch."""
    with respx.mock:
        respx.get(REGISTRY_URL).mock(
            return_value=httpx.Response(200, text=yaml.dump(SAMPLE_REGISTRY))
        )
        yield


class TestMarketplace:
    def test_list_templates(self, tmp_path, mock_registry):
        """Parsed from YAML registry."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        templates = mp.list_templates()
        assert len(templates) == 2
        assert templates[0]["name"] == "researcher"

    def test_search_by_name(self, tmp_path, mock_registry):
        """Name match."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        results = mp.search("researcher")
        assert len(results) == 1
        assert results[0]["name"] == "researcher"

    def test_search_by_tag(self, tmp_path, mock_registry):
        """Tag match."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        results = mp.search("trading")
        assert len(results) == 1
        assert results[0]["name"] == "trader"

    def test_search_case_insensitive(self, tmp_path, mock_registry):
        """Case doesn't matter."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        results = mp.search("RESEARCH")
        assert len(results) == 1

    def test_search_no_results(self, tmp_path, mock_registry):
        """Empty list for no match."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        results = mp.search("nonexistent")
        assert results == []

    def test_info_found(self, tmp_path, mock_registry):
        """Returns template dict."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        info = mp.info("researcher")
        assert info is not None
        assert info["name"] == "researcher"
        assert "research" in info["tags"]

    def test_info_not_found(self, tmp_path, mock_registry):
        """Returns None for unknown template."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        assert mp.info("ghost") is None

    def test_install_success(self, tmp_path, mock_registry):
        """Files downloaded to templates/."""
        with respx.mock:
            respx.get(REGISTRY_URL).mock(
                return_value=httpx.Response(200, text=yaml.dump(SAMPLE_REGISTRY))
            )
            respx.get(f"{TEMPLATE_BASE}/researcher/profile.md").mock(
                return_value=httpx.Response(200, text="# Researcher\nA research worker.")
            )
            respx.get(f"{TEMPLATE_BASE}/researcher/skills.yaml").mock(
                return_value=httpx.Response(200, text=yaml.dump({"role": "researcher", "skills": ["research"]}))
            )
            respx.get(f"{TEMPLATE_BASE}/researcher/config.yaml").mock(
                return_value=httpx.Response(200, text=yaml.dump({"level": 1}))
            )

            mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
            path = mp.install("researcher")

        assert path.exists()
        assert (path / "profile.md").exists()
        assert (path / "skills.yaml").exists()
        assert (path / "config.yaml").exists()

    def test_install_already_exists(self, tmp_path, mock_registry):
        """MarketplaceError raised when template dir exists."""
        (tmp_path / "templates" / "researcher").mkdir(parents=True)
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        with pytest.raises(MarketplaceError, match="already exists"):
            mp.install("researcher")

    def test_install_not_in_registry(self, tmp_path, mock_registry):
        """MarketplaceError raised for unknown template."""
        mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
        with pytest.raises(MarketplaceError, match="not found"):
            mp.install("ghost")

    def test_install_network_error(self, tmp_path):
        """MarketplaceError raised on network error + cleanup."""
        with respx.mock:
            respx.get(REGISTRY_URL).mock(
                return_value=httpx.Response(200, text=yaml.dump(SAMPLE_REGISTRY))
            )
            respx.get(f"{TEMPLATE_BASE}/researcher/profile.md").mock(
                side_effect=httpx.ConnectError("refused")
            )

            mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
            with pytest.raises(MarketplaceError, match="Failed to download"):
                mp.install("researcher")

        # Cleanup should have removed the directory
        assert not (tmp_path / "templates" / "researcher").exists()

    def test_corrupt_registry_yaml(self, tmp_path):
        """MarketplaceError raised for corrupt YAML."""
        with respx.mock:
            respx.get(REGISTRY_URL).mock(
                return_value=httpx.Response(200, text="just a string, not a mapping")
            )
            mp = Marketplace(REGISTRY_URL, tmp_path / "templates")
            with pytest.raises(MarketplaceError, match="must contain"):
                mp.list_templates()
