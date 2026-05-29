import time
from typing import Any

import structlog
from openai import AsyncOpenAI, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.llm.base import ChatMessage, ChatResult, LLMProvider, ModelTier

log = structlog.get_logger(__name__)

_TIER_MODELS: dict[str, str] = {
    "cheap": "gpt-4o-mini",
    "smart": "gpt-4o",
}

# USD per token
_COST_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"input": 0.150e-6, "output": 0.600e-6},
    "gpt-4o": {"input": 2.500e-6, "output": 10.000e-6},
}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=15.0)

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
        log.debug("openai_chat_ok", model=model, in_tok=in_tok, out_tok=out_tok, latency_ms=latency_ms)
        return ChatResult(
            content=response.choices[0].message.content or "",
            model=model,
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
