import time
from typing import Any

import structlog
from groq import APITimeoutError, AsyncGroq, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.llm.base import ChatMessage, ChatResult, LLMProvider, ModelTier

log = structlog.get_logger(__name__)

_TIER_MODELS: dict[str, str] = {
    "cheap": "llama-3.1-8b-instant",
    "smart": "llama-3.1-70b-versatile",
}

# USD per token
_COST_TABLE: dict[str, dict[str, float]] = {
    "llama-3.1-8b-instant": {"input": 0.05e-6, "output": 0.08e-6},
    "llama-3.1-70b-versatile": {"input": 0.59e-6, "output": 0.79e-6},
}


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncGroq(api_key=settings.groq_api_key, timeout=15.0)

    @retry(
        retry=retry_if_exception_type((APITimeoutError, RateLimitError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[ChatMessage],
        model_tier: ModelTier = "cheap",
        **kwargs: Any,
    ) -> ChatResult:
        model = _TIER_MODELS[model_tier]
        t0 = time.monotonic()
        response = await self._client.chat.completions.create(
            model=model,
            messages=[m.model_dump() for m in messages],
            **kwargs,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = response.usage
        in_tok = usage.prompt_tokens if usage else 0
        out_tok = usage.completion_tokens if usage else 0
        rates = _COST_TABLE[model]
        cost = in_tok * rates["input"] + out_tok * rates["output"]
        log.debug(
            "groq_chat_ok", model=model, in_tok=in_tok, out_tok=out_tok, latency_ms=latency_ms
        )
        return ChatResult(
            content=response.choices[0].message.content or "",
            model=model,
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
