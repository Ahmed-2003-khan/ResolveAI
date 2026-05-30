"""Node: classify_intent — maps raw user message to one of seven intent labels."""

from __future__ import annotations

import time
from pathlib import Path

import yaml
import structlog

from app.agent.state import AgentState
from app.observability.metrics import NODE_DURATION
from app.services.llm.base import ChatMessage
from app.services.llm.router import get_llm_router

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_VALID_INTENTS = {
    "order_status",
    "refund_request",
    "account_inquiry",
    "technical_support",
    "general_inquiry",
    "escalate_human",
    "abuse",
    "session_end",
}


def _load_prompt(name: str) -> dict:
    with open(_PROMPTS_DIR / f"{name}.yaml") as fh:
        return yaml.safe_load(fh)


async def classify_intent(state: AgentState) -> dict:
    t0 = time.monotonic()
    prompt = _load_prompt("classify_intent")

    messages = [
        ChatMessage(role="system", content=prompt["system"].strip()),
        ChatMessage(
            role="user",
            content=prompt["user"].format(user_message=state["user_message"]).strip(),
        ),
    ]

    router = get_llm_router()
    result = await router.chat(messages, model_tier="cheap", max_tokens=50)

    raw = result.content.strip().lower().split()[0] if result.content.strip() else ""
    intent = raw if raw in _VALID_INTENTS else "general_inquiry"

    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="classify_intent").observe(latency / 1000.0)
    log.info("node_classify_intent", intent=intent, latency_ms=latency)

    return {
        "intent": intent,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.cost_usd,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "classify_intent",
                "model": result.model,
                "provider": result.provider,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "latency_ms": latency,
                "output": intent,
            }
        ],
    }
