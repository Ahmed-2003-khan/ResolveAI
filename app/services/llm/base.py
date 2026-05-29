from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel

ModelTier = Literal["cheap", "smart"]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatResult(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    raw: dict[str, Any] = {}


class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        model_tier: ModelTier = "cheap",
        **kwargs: Any,
    ) -> ChatResult: ...
