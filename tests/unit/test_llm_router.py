"""Unit tests for LLMRouter: fallback order, circuit breaker, tier routing."""

import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import AllProvidersDownError
from app.services.llm.base import ChatMessage, ChatResult
from app.services.llm.router import _TIER_PROVIDERS, LLMRouter, _CircuitState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(provider: str = "openai", model: str = "gpt-4o-mini") -> ChatResult:
    return ChatResult(
        content="Hello!",
        model=model,
        provider=provider,
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.000001,
        latency_ms=200,
    )


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="ping")]


def _make_router(openai_mock=None, groq_mock=None, ollama_mock=None) -> LLMRouter:
    """Return an LLMRouter whose providers are replaced with mocks."""
    router = LLMRouter.__new__(LLMRouter)
    from app.services.llm.router import _CircuitState

    router._providers = {
        "openai": openai_mock or AsyncMock(),
        "groq": groq_mock or AsyncMock(),
        "ollama": ollama_mock or AsyncMock(),
    }
    router._circuits = {name: _CircuitState() for name in router._providers}
    return router


# ---------------------------------------------------------------------------
# Basic routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_provider_succeeds_returns_immediately():
    openai = AsyncMock()
    openai.chat = AsyncMock(return_value=_make_result("openai"))
    router = _make_router(openai_mock=openai)

    result = await router.chat(_messages(), model_tier="cheap")

    assert result.provider == "openai"
    openai.chat.assert_awaited_once()
    router._providers["groq"].chat.assert_not_awaited()
    router._providers["ollama"].chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_falls_back_to_groq_when_openai_fails():
    openai = AsyncMock()
    openai.chat = AsyncMock(side_effect=RuntimeError("connection refused"))
    groq = AsyncMock()
    groq.chat = AsyncMock(return_value=_make_result("groq", "llama-3.1-8b-instant"))
    router = _make_router(openai_mock=openai, groq_mock=groq)

    result = await router.chat(_messages(), model_tier="cheap")

    assert result.provider == "groq"
    openai.chat.assert_awaited_once()
    groq.chat.assert_awaited_once()
    router._providers["ollama"].chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_falls_back_to_ollama_when_openai_and_groq_fail():
    openai = AsyncMock()
    openai.chat = AsyncMock(side_effect=RuntimeError("openai down"))
    groq = AsyncMock()
    groq.chat = AsyncMock(side_effect=RuntimeError("groq down"))
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value=_make_result("ollama", "llama3:8b"))
    router = _make_router(openai_mock=openai, groq_mock=groq, ollama_mock=ollama)

    result = await router.chat(_messages(), model_tier="cheap")

    assert result.provider == "ollama"


@pytest.mark.asyncio
async def test_raises_all_providers_down_when_all_fail():
    for provider in ["openai", "groq", "ollama"]:
        _ = provider  # noqa
    openai = AsyncMock()
    openai.chat = AsyncMock(side_effect=RuntimeError("openai down"))
    groq = AsyncMock()
    groq.chat = AsyncMock(side_effect=RuntimeError("groq down"))
    ollama = AsyncMock()
    ollama.chat = AsyncMock(side_effect=RuntimeError("ollama down"))
    router = _make_router(openai_mock=openai, groq_mock=groq, ollama_mock=ollama)

    with pytest.raises(AllProvidersDownError):
        await router.chat(_messages(), model_tier="cheap")


# ---------------------------------------------------------------------------
# Tier routing — smart tier must never reach Ollama
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_tier_does_not_use_ollama():
    openai = AsyncMock()
    openai.chat = AsyncMock(side_effect=RuntimeError("openai down"))
    groq = AsyncMock()
    groq.chat = AsyncMock(return_value=_make_result("groq", "llama-3.1-70b-versatile"))
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value=_make_result("ollama", "llama3:8b"))
    router = _make_router(openai_mock=openai, groq_mock=groq, ollama_mock=ollama)

    result = await router.chat(_messages(), model_tier="smart")

    assert result.provider == "groq"
    ollama.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_smart_tier_raises_when_openai_and_groq_fail():
    openai = AsyncMock()
    openai.chat = AsyncMock(side_effect=RuntimeError("openai down"))
    groq = AsyncMock()
    groq.chat = AsyncMock(side_effect=RuntimeError("groq down"))
    ollama = AsyncMock()
    ollama.chat = AsyncMock(return_value=_make_result("ollama"))
    router = _make_router(openai_mock=openai, groq_mock=groq, ollama_mock=ollama)

    with pytest.raises(AllProvidersDownError):
        await router.chat(_messages(), model_tier="smart")

    ollama.chat.assert_not_awaited()


def test_smart_tier_provider_list_excludes_ollama():
    assert "ollama" not in _TIER_PROVIDERS["smart"]


def test_cheap_tier_provider_list_includes_ollama():
    assert "ollama" in _TIER_PROVIDERS["cheap"]


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitState:
    def test_initially_closed(self):
        c = _CircuitState()
        assert not c.is_open(window=60, threshold=3)

    def test_opens_after_threshold_failures(self):
        c = _CircuitState()
        for _ in range(3):
            c.record_failure(window=60, threshold=3, cooldown=300)
        assert c.is_open(window=60, threshold=3)

    def test_does_not_open_below_threshold(self):
        c = _CircuitState()
        for _ in range(2):
            c.record_failure(window=60, threshold=3, cooldown=300)
        assert not c.is_open(window=60, threshold=3)

    def test_success_resets_circuit(self):
        c = _CircuitState()
        for _ in range(3):
            c.record_failure(window=60, threshold=3, cooldown=300)
        assert c.is_open(window=60, threshold=3)
        c.record_success()
        assert not c.is_open(window=60, threshold=3)

    def test_stale_failures_outside_window_are_pruned(self):
        c = _CircuitState()
        # Inject two old failures (outside the window).
        old = time.monotonic() - 120
        c.failure_times = [old, old]
        # Add one recent failure — total in-window is 1, below threshold of 3.
        c.record_failure(window=60, threshold=3, cooldown=300)
        assert not c.is_open(window=60, threshold=3)

    def test_open_until_respected(self):
        c = _CircuitState()
        c.open_until = time.monotonic() + 1000
        assert c.is_open(window=60, threshold=3)


@pytest.mark.asyncio
async def test_circuit_breaker_skips_tripped_provider():
    openai = AsyncMock()
    openai.chat = AsyncMock(side_effect=RuntimeError("down"))
    groq = AsyncMock()
    groq.chat = AsyncMock(return_value=_make_result("groq"))
    router = _make_router(openai_mock=openai, groq_mock=groq)

    # Trip OpenAI circuit by injecting threshold failures directly.
    router._circuits["openai"].open_until = time.monotonic() + 300

    result = await router.chat(_messages(), model_tier="cheap")

    assert result.provider == "groq"
    openai.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_consecutive_failures_trip_circuit_and_skip_on_next_call():
    """After threshold consecutive failures, subsequent calls skip that provider."""
    openai = AsyncMock()
    # Fail 3 times to trip the circuit.
    openai.chat = AsyncMock(side_effect=RuntimeError("openai down"))
    groq = AsyncMock()
    groq.chat = AsyncMock(return_value=_make_result("groq"))
    router = _make_router(openai_mock=openai, groq_mock=groq)

    # Manually record threshold failures to open the circuit.
    settings_patch = MagicMock()
    settings_patch.llm_circuit_breaker_window_seconds = 60
    settings_patch.llm_circuit_breaker_failures = 3
    settings_patch.llm_circuit_breaker_cooldown_seconds = 300

    with patch("app.services.llm.router.get_settings", return_value=settings_patch):
        # First 3 calls trigger failures → circuit opens.
        for _ in range(3):
            with contextlib.suppress(Exception):
                await router.chat(_messages(), model_tier="cheap")

        openai.chat.reset_mock()
        groq.chat.reset_mock()
        groq.chat = AsyncMock(return_value=_make_result("groq"))

        # Now OpenAI circuit should be open; Groq handles the request.
        result = await router.chat(_messages(), model_tier="cheap")
        assert result.provider == "groq"
        openai.chat.assert_not_awaited()


# ---------------------------------------------------------------------------
# circuit_status helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_status_all_closed_initially():
    router = _make_router()
    with patch("app.services.llm.router.get_settings") as mock_settings:
        mock_settings.return_value.llm_circuit_breaker_window_seconds = 60
        mock_settings.return_value.llm_circuit_breaker_failures = 3
        mock_settings.return_value.llm_circuit_breaker_cooldown_seconds = 300
        status = router.circuit_status()

    for name in ["openai", "groq", "ollama"]:
        assert name in status
        assert status[name]["open"] is False
        assert status[name]["recent_failures"] == 0
