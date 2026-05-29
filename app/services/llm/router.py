"""LLM router with per-provider circuit breakers and tier-based fallback chain."""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.config import get_settings
from app.core.exceptions import AllProvidersDownError
from app.services.llm.base import ChatMessage, ChatResult, LLMProvider, ModelTier
from app.services.llm.groq_provider import GroqProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider

log = structlog.get_logger(__name__)

# Providers available per tier, in priority order.
# Ollama is excluded from "smart" because local Llama 3 8B cannot handle it.
_TIER_PROVIDERS: dict[str, list[str]] = {
    "cheap": ["openai", "groq", "ollama"],
    "smart": ["openai", "groq"],
}


@dataclass
class _CircuitState:
    """Sliding-window circuit breaker state for one provider."""

    failure_times: list[float] = field(default_factory=list)
    open_until: float = 0.0

    def is_open(self, window: int, threshold: int) -> bool:
        now = time.monotonic()
        if now < self.open_until:
            return True
        # Prune failures outside the window.
        self.failure_times = [t for t in self.failure_times if now - t < window]
        return False

    def record_failure(self, window: int, threshold: int, cooldown: int) -> None:
        now = time.monotonic()
        self.failure_times = [t for t in self.failure_times if now - t < window]
        self.failure_times.append(now)
        if len(self.failure_times) >= threshold:
            self.open_until = now + cooldown
            log.warning(
                "circuit_breaker_tripped",
                failures_in_window=len(self.failure_times),
                cooldown_seconds=cooldown,
            )

    def record_success(self) -> None:
        self.failure_times.clear()
        self.open_until = 0.0


class LLMRouter:
    """Routes chat requests across providers with automatic fallback and circuit breaking."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {
            "openai": OpenAIProvider(),
            "groq": GroqProvider(),
            "ollama": OllamaProvider(),
        }
        self._circuits: dict[str, _CircuitState] = {
            name: _CircuitState() for name in self._providers
        }

    async def chat(
        self,
        messages: list[ChatMessage],
        model_tier: ModelTier = "cheap",
        **kwargs: Any,
    ) -> ChatResult:
        settings = get_settings()
        window = settings.llm_circuit_breaker_window_seconds
        threshold = settings.llm_circuit_breaker_failures
        cooldown = settings.llm_circuit_breaker_cooldown_seconds

        provider_order = _TIER_PROVIDERS.get(model_tier, ["openai", "groq"])
        last_error: Exception | None = None

        for name in provider_order:
            circuit = self._circuits[name]
            if circuit.is_open(window, threshold):
                log.info("circuit_open_skip", provider=name, model_tier=model_tier)
                continue

            provider = self._providers[name]
            try:
                result = await provider.chat(messages, model_tier=model_tier, **kwargs)
                circuit.record_success()
                log.info(
                    "llm_call_success",
                    provider=name,
                    model=result.model,
                    latency_ms=result.latency_ms,
                    cost_usd=result.cost_usd,
                )
                return result
            except Exception as exc:
                last_error = exc
                circuit.record_failure(window, threshold, cooldown)
                log.warning(
                    "llm_provider_failure",
                    provider=name,
                    model_tier=model_tier,
                    error=str(exc),
                    exc_info=True,
                )

        raise AllProvidersDownError(
            f"All providers exhausted for tier='{model_tier}'. Last error: {last_error}"
        )

    def circuit_status(self) -> dict[str, dict[str, Any]]:
        """Return health snapshot for all providers (useful for /readyz)."""
        settings = get_settings()
        window = settings.llm_circuit_breaker_window_seconds
        threshold = settings.llm_circuit_breaker_failures
        now = time.monotonic()
        return {
            name: {
                "open": circuit.is_open(window, threshold),
                "open_until_seconds": max(0.0, circuit.open_until - now),
                "recent_failures": len(
                    [t for t in circuit.failure_times if now - t < window]
                ),
            }
            for name, circuit in self._circuits.items()
        }


# Module-level singleton — one router per process.
_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router
