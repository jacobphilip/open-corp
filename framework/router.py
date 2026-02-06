"""Model router — routes LLM calls through OpenRouter with budget-aware fallback."""

import json
import os
from pathlib import Path
from typing import Generator

import httpx

from framework.accountant import Accountant, BudgetStatus
from framework.config import ProjectConfig
from framework.exceptions import BudgetExceeded, ModelUnavailable
from framework.log import get_logger

logger = get_logger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Tier priority for fallback (cheapest last)
TIER_FALLBACK_ORDER = ["premium", "mid", "cheap"]


class Router:
    """Routes LLM calls to OpenRouter with tier-based model selection and budget awareness."""

    def __init__(
        self,
        config: ProjectConfig,
        accountant: Accountant,
        api_key: str | None = None,
    ):
        self.config = config
        self.accountant = accountant
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._pricing_cache: dict[str, dict] | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/open-corp",
            "X-Title": "open-corp",
        }

    def _get_models_for_tier(self, tier: str) -> list[str]:
        """Get model list for a tier from config."""
        tier_config = self.config.model_tiers.get(tier)
        if not tier_config:
            return []
        return tier_config.models

    def _select_tier(self, requested_tier: str, budget_status: BudgetStatus) -> list[str]:
        """Return ordered list of tiers to try, adjusting for budget status."""
        # Budget pressure forces cheaper tiers
        if budget_status == BudgetStatus.AUSTERITY:
            return ["cheap"]
        if budget_status == BudgetStatus.CRITICAL:
            return ["cheap"]
        if budget_status == BudgetStatus.CAUTION:
            # Prefer cheap, but allow requested if it's mid
            if requested_tier == "premium":
                return ["mid", "cheap"]
            return [requested_tier, "cheap"] if requested_tier != "cheap" else ["cheap"]

        # GREEN — use requested tier, fall back downward
        tiers = []
        found = False
        for t in TIER_FALLBACK_ORDER:
            if t == requested_tier:
                found = True
            if found:
                tiers.append(t)
        return tiers if tiers else [requested_tier]

    def _estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> float:
        """Estimate cost from cached pricing or use defaults."""
        pricing = self._load_pricing()
        if model in pricing:
            p = pricing[model]
            return (tokens_in * p.get("prompt", 0.0) + tokens_out * p.get("completion", 0.0)) / 1_000_000
        # Default conservative estimate: $1/M input, $2/M output
        return (tokens_in * 1.0 + tokens_out * 2.0) / 1_000_000

    def _load_pricing(self) -> dict[str, dict]:
        """Load cached model pricing."""
        if self._pricing_cache is not None:
            return self._pricing_cache

        cache_path = self.config.project_dir / "data" / "model_pricing.json"
        if cache_path.exists():
            try:
                self._pricing_cache = json.loads(cache_path.read_text())
                return self._pricing_cache
            except (json.JSONDecodeError, OSError):
                pass

        self._pricing_cache = {}
        return self._pricing_cache

    def fetch_pricing(self) -> dict[str, dict]:
        """Fetch model pricing from OpenRouter and cache it."""
        try:
            resp = httpx.get(
                OPENROUTER_MODELS_URL,
                headers=self._headers(),
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            return self._load_pricing()

        pricing: dict[str, dict] = {}
        for model in data.get("data", []):
            model_id = model.get("id", "")
            p = model.get("pricing", {})
            if model_id and p:
                pricing[model_id] = {
                    "prompt": float(p.get("prompt", "0")),
                    "completion": float(p.get("completion", "0")),
                }

        # Cache to disk
        cache_path = self.config.project_dir / "data" / "model_pricing.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(pricing, indent=2))

        self._pricing_cache = pricing
        return pricing

    def chat(
        self,
        messages: list[dict],
        tier: str = "cheap",
        model: str | None = None,
        worker_name: str = "system",
    ) -> dict:
        """Send a chat completion request. Returns {content, model_used, tokens, cost}.

        Checks budget, selects model with fallback, records spending.
        """
        budget_status = self.accountant.pre_check()

        # Build ordered list of models to try
        models_to_try: list[str] = []
        if model:
            models_to_try.append(model)

        tiers_to_try = self._select_tier(tier, budget_status)
        for t in tiers_to_try:
            for m in self._get_models_for_tier(t):
                if m not in models_to_try:
                    models_to_try.append(m)

        if not models_to_try:
            raise ModelUnavailable(
                model=model or tier,
                tier=tier,
                tried=[],
            )

        logger.debug("Model selection: tier=%s, budget=%s, candidates=%s",
                     tier, budget_status.value, models_to_try)

        last_error: Exception | None = None
        for candidate in models_to_try:
            try:
                return self._call_openrouter(candidate, messages, worker_name)
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                logger.info("Tier fallback: %s failed (%s), trying next", candidate, e)
                last_error = e
                continue

        logger.warning("All models exhausted: tried=%s, last_error=%s", models_to_try, last_error)
        raise ModelUnavailable(
            model=model or tier,
            tier=tier,
            tried=models_to_try,
        )

    def _call_openrouter(
        self,
        model: str,
        messages: list[dict],
        worker_name: str,
    ) -> dict:
        """Make the actual API call to OpenRouter."""
        payload = {
            "model": model,
            "messages": messages,
        }

        resp = httpx.post(
            OPENROUTER_API_URL,
            headers=self._headers(),
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract response
        content = ""
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        # Extract usage
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        cost = self._estimate_cost(model, tokens_in, tokens_out)

        # Record spending
        self.accountant.record_call(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            worker=worker_name,
        )

        return {
            "content": content,
            "model_used": model,
            "tokens": {"in": tokens_in, "out": tokens_out},
            "cost": cost,
        }

    def stream(
        self,
        messages: list[dict],
        tier: str = "cheap",
        model: str | None = None,
        worker_name: str = "system",
    ) -> Generator[dict, None, None]:
        """Stream a chat completion. Yields chunks; final chunk has usage info."""
        budget_status = self.accountant.pre_check()

        # Select model (first available)
        models_to_try: list[str] = []
        if model:
            models_to_try.append(model)
        tiers_to_try = self._select_tier(tier, budget_status)
        for t in tiers_to_try:
            models_to_try.extend(self._get_models_for_tier(t))

        if not models_to_try:
            raise ModelUnavailable(model=model or tier, tier=tier, tried=[])

        selected = models_to_try[0]
        payload = {
            "model": selected,
            "messages": messages,
            "stream": True,
        }

        full_content = ""
        tokens_in = 0
        tokens_out = 0

        with httpx.stream(
            "POST",
            OPENROUTER_API_URL,
            headers=self._headers(),
            json=payload,
            timeout=120.0,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Content delta
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content", "")
                if text:
                    full_content += text
                    yield {"content": text, "done": False}

                # Usage in final chunk
                usage = chunk.get("usage")
                if usage:
                    tokens_in = usage.get("prompt_tokens", 0)
                    tokens_out = usage.get("completion_tokens", 0)

        cost = self._estimate_cost(selected, tokens_in, tokens_out)
        self.accountant.record_call(
            model=selected,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            worker=worker_name,
        )

        yield {
            "content": "",
            "done": True,
            "model_used": selected,
            "tokens": {"in": tokens_in, "out": tokens_out},
            "cost": cost,
            "full_content": full_content,
        }
