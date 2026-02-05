"""Tests for framework/router.py."""

import json

import httpx
import pytest
import respx

from framework.accountant import Accountant, BudgetStatus
from framework.config import ProjectConfig
from framework.exceptions import BudgetExceeded, ModelUnavailable
from framework.router import OPENROUTER_API_URL, Router


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
