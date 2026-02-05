"""Tests for framework/router.py."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from framework.accountant import Accountant, BudgetStatus
from framework.config import ProjectConfig
from framework.exceptions import BudgetExceeded, ModelUnavailable
from framework.router import OPENROUTER_API_URL, OPENROUTER_MODELS_URL, Router


def _mock_openrouter_response(content="Hello!", tokens_in=10, tokens_out=5):
    """Create a mock OpenRouter response payload."""
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": tokens_in,
            "completion_tokens": tokens_out,
        },
    }


class TestRouter:
    def test_chat_success(self, config, accountant):
        """Successful chat call returns content and records spending."""
        router = Router(config, accountant, api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json=_mock_openrouter_response("Hi there!"))
            )

            result = router.chat(messages, tier="cheap")

        assert result["content"] == "Hi there!"
        assert result["model_used"] == "deepseek/deepseek-chat"
        assert result["tokens"]["in"] == 10
        assert result["tokens"]["out"] == 5
        assert result["cost"] > 0
        assert accountant.today_spent() > 0

    def test_model_fallback_on_error(self, config, accountant):
        """When first model returns 503, falls back to next model in tier."""
        router = Router(config, accountant, api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        call_count = 0

        with respx.mock:
            # First model fails with 503
            respx.post(OPENROUTER_API_URL).mock(
                side_effect=[
                    httpx.Response(503, text="Service Unavailable"),
                    httpx.Response(200, json=_mock_openrouter_response("Fallback!")),
                ]
            )

            result = router.chat(messages, tier="cheap")

        assert result["content"] == "Fallback!"
        # Second model in cheap tier
        assert result["model_used"] == "mistralai/mistral-tiny"

    def test_all_models_fail_raises(self, config, accountant):
        """When all models fail, raises ModelUnavailable."""
        router = Router(config, accountant, api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        with respx.mock:
            # All models fail
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(503, text="Down")
            )

            with pytest.raises(ModelUnavailable):
                router.chat(messages, tier="cheap")

    def test_budget_frozen_raises(self, config, accountant):
        """When budget is frozen, chat raises BudgetExceeded."""
        # Exhaust budget
        accountant.record_call("m", 0, 0, 3.00, "w")

        router = Router(config, accountant, api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(BudgetExceeded):
            router.chat(messages, tier="cheap")

    def test_explicit_model_tried_first(self, config, accountant):
        """Explicit model parameter is tried before tier models."""
        router = Router(config, accountant, api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json=_mock_openrouter_response("Custom!"))
            )

            result = router.chat(messages, tier="cheap", model="custom/model")

        assert result["model_used"] == "custom/model"

    def test_caution_prefers_cheap(self, config, accountant):
        """Under CAUTION budget, premium tier is downgraded."""
        # Spend to CAUTION level (60-80%)
        accountant.record_call("m", 0, 0, 2.00, "w")
        assert accountant.pre_check() == BudgetStatus.CAUTION

        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.post(OPENROUTER_API_URL).mock(
                return_value=httpx.Response(200, json=_mock_openrouter_response("Budget mode"))
            )

            # Request premium but should get downgraded
            result = router.chat(
                [{"role": "user", "content": "test"}],
                tier="premium",
            )

        # Should have been downgraded to mid or cheap tier model
        assert result["model_used"] in [
            "anthropic/claude-sonnet-4-20250514",
            "deepseek/deepseek-chat",
            "mistralai/mistral-tiny",
        ]


class _FakeStreamResponse:
    """Fake httpx streaming response for testing Router.stream()."""

    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=MagicMock(), response=MagicMock(status_code=self.status_code)
            )

    def iter_lines(self):
        yield from self._lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _sse_line(content="", usage=None):
    """Build an SSE data line for a streaming chunk."""
    chunk = {"choices": [{"delta": {"content": content}}]}
    if usage:
        chunk["usage"] = usage
    return f"data: {json.dumps(chunk)}"


class TestRouterStreaming:
    def test_stream_success(self, config, accountant):
        """Streaming yields content chunks; final chunk has usage; cost recorded."""
        router = Router(config, accountant, api_key="test-key")
        lines = [
            _sse_line("Hello"),
            _sse_line(" world"),
            _sse_line("", usage={"prompt_tokens": 10, "completion_tokens": 5}),
            "data: [DONE]",
        ]

        with patch("httpx.stream", return_value=_FakeStreamResponse(lines)):
            chunks = list(router.stream([{"role": "user", "content": "hi"}], tier="cheap"))

        # Two content chunks + final done chunk
        content_chunks = [c for c in chunks if not c["done"]]
        assert len(content_chunks) == 2
        assert content_chunks[0]["content"] == "Hello"
        assert content_chunks[1]["content"] == " world"

        final = chunks[-1]
        assert final["done"] is True
        assert final["full_content"] == "Hello world"
        assert final["tokens"]["in"] == 10
        assert final["tokens"]["out"] == 5
        assert final["cost"] > 0
        assert accountant.today_spent() > 0

    def test_stream_budget_frozen(self, config, accountant):
        """When budget is frozen, stream raises BudgetExceeded before any network call."""
        accountant.record_call("m", 0, 0, 3.00, "w")
        router = Router(config, accountant, api_key="test-key")

        with pytest.raises(BudgetExceeded):
            list(router.stream([{"role": "user", "content": "hi"}], tier="cheap"))

    def test_stream_empty_content(self, config, accountant):
        """Chunks with empty deltas are skipped; final chunk still correct."""
        router = Router(config, accountant, api_key="test-key")
        lines = [
            _sse_line(""),  # empty delta
            _sse_line("ok"),
            _sse_line("", usage={"prompt_tokens": 5, "completion_tokens": 2}),
            "data: [DONE]",
        ]

        with patch("httpx.stream", return_value=_FakeStreamResponse(lines)):
            chunks = list(router.stream([{"role": "user", "content": "hi"}], tier="cheap"))

        content_chunks = [c for c in chunks if not c["done"]]
        assert len(content_chunks) == 1
        assert content_chunks[0]["content"] == "ok"
        assert chunks[-1]["full_content"] == "ok"

    def test_stream_malformed_json(self, config, accountant):
        """Malformed JSON lines are skipped; valid chunks still processed."""
        router = Router(config, accountant, api_key="test-key")
        lines = [
            "data: {bad json!!!",
            _sse_line("good"),
            _sse_line("", usage={"prompt_tokens": 1, "completion_tokens": 1}),
            "data: [DONE]",
        ]

        with patch("httpx.stream", return_value=_FakeStreamResponse(lines)):
            chunks = list(router.stream([{"role": "user", "content": "hi"}], tier="cheap"))

        content_chunks = [c for c in chunks if not c["done"]]
        assert len(content_chunks) == 1
        assert content_chunks[0]["content"] == "good"


class TestRouterPricing:
    def test_fetch_pricing_success(self, config, accountant):
        """Parses models endpoint and caches pricing to disk."""
        router = Router(config, accountant, api_key="test-key")
        models_response = {
            "data": [
                {"id": "model-a", "pricing": {"prompt": "0.001", "completion": "0.002"}},
                {"id": "model-b", "pricing": {"prompt": "0.005", "completion": "0.01"}},
            ]
        }

        with respx.mock:
            respx.get(OPENROUTER_MODELS_URL).mock(
                return_value=httpx.Response(200, json=models_response)
            )
            pricing = router.fetch_pricing()

        assert "model-a" in pricing
        assert pricing["model-a"]["prompt"] == 0.001
        assert pricing["model-b"]["completion"] == 0.01

        # Verify disk cache
        cache_path = config.project_dir / "data" / "model_pricing.json"
        assert cache_path.exists()
        cached = json.loads(cache_path.read_text())
        assert "model-a" in cached

    def test_fetch_pricing_network_error(self, config, accountant):
        """Network error falls back to empty dict (no prior cache)."""
        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.get(OPENROUTER_MODELS_URL).mock(side_effect=httpx.ConnectError("fail"))
            pricing = router.fetch_pricing()

        assert pricing == {}

    def test_fetch_pricing_uses_disk_cache(self, config, accountant):
        """When network fails, returns pre-populated disk cache."""
        # Pre-populate cache file
        cache_path = config.project_dir / "data" / "model_pricing.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cached_data = {"cached-model": {"prompt": 0.1, "completion": 0.2}}
        cache_path.write_text(json.dumps(cached_data))

        router = Router(config, accountant, api_key="test-key")

        with respx.mock:
            respx.get(OPENROUTER_MODELS_URL).mock(side_effect=httpx.ConnectError("fail"))
            pricing = router.fetch_pricing()

        assert "cached-model" in pricing
        assert pricing["cached-model"]["prompt"] == 0.1

    def test_fetch_pricing_overwrites_cache(self, config, accountant):
        """Fresh fetch replaces old cached data."""
        # Pre-populate with old data
        cache_path = config.project_dir / "data" / "model_pricing.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"old-model": {"prompt": 0.5, "completion": 0.5}}))

        router = Router(config, accountant, api_key="test-key")
        new_response = {
            "data": [
                {"id": "new-model", "pricing": {"prompt": "0.01", "completion": "0.02"}},
            ]
        }

        with respx.mock:
            respx.get(OPENROUTER_MODELS_URL).mock(
                return_value=httpx.Response(200, json=new_response)
            )
            pricing = router.fetch_pricing()

        assert "new-model" in pricing
        # Old model should be gone from returned pricing
        assert "old-model" not in pricing

        # Verify disk also updated
        on_disk = json.loads(cache_path.read_text())
        assert "new-model" in on_disk
        assert "old-model" not in on_disk
