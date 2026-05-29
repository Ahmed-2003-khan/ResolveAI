import time
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.services.llm.base import ChatMessage, ChatResult, LLMProvider, ModelTier

log = structlog.get_logger(__name__)

_TIER_MODELS: dict[str, str] = {
    "cheap": "llama3:8b",
    # smart tier is not supported locally — fail closed
}


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)

    @retry(
        retry=retry_if_exception_type(httpx.TimeoutException),
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
        if model_tier not in _TIER_MODELS:
            raise ValueError(f"OllamaProvider does not support model_tier='{model_tier}'")
        model = _TIER_MODELS[model_tier]
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
        }
        t0 = time.monotonic()
        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        latency_ms = int((time.monotonic() - t0) * 1000)
        data = response.json()
        content = data.get("message", {}).get("content", "")
        in_tok = data.get("prompt_eval_count", 0)
        out_tok = data.get("eval_count", 0)
        log.debug("ollama_chat_ok", model=model, in_tok=in_tok, out_tok=out_tok, latency_ms=latency_ms)
        return ChatResult(
            content=content,
            model=model,
            provider=self.name,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
