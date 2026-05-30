"""Node: compose_response — drafts the customer-facing reply from all pipeline outputs."""

from __future__ import annotations

import json
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


def _kb_context_text(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant knowledge base articles found."
    parts = []
    for i, c in enumerate(chunks, 1):
        title = c.get("title") or c.get("source_id", f"Chunk {i}")
        parts.append(f"[{i}] {title}\n{c.get('content', '')}")
    return "\n\n".join(parts)


def _history_text(history: list[dict]) -> str:
    if not history:
        return "No prior conversation."
    lines = []
    for msg in history[-10:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


async def compose_response(state: AgentState) -> dict:
    t0 = time.monotonic()
    with open(_PROMPTS_DIR / "compose_response.yaml") as fh:
        prompt = yaml.safe_load(fh)

    tool_results_text = json.dumps(state.get("tool_results") or {}, indent=2) or "{}"
    kb_context = _kb_context_text(state.get("retrieved_chunks") or [])
    history_text = _history_text(state.get("conversation_history") or [])
    profile = state.get("user_profile") or {}
    critique_feedback = state.get("critique_feedback") or ""

    messages = [
        ChatMessage(role="system", content=prompt["system"].strip()),
        ChatMessage(
            role="user",
            content=prompt["user"]
            .format(
                user_profile=json.dumps(profile),
                conversation_history=history_text,
                user_message=state.get("cleaned_content") or state["user_message"],
                intent=state.get("intent") or "general_inquiry",
                kb_context=kb_context,
                tool_results=tool_results_text,
                critique_feedback=critique_feedback,
            )
            .strip(),
        ),
    ]

    router = get_llm_router()
    result = await router.chat(messages, model_tier="cheap", max_tokens=600)

    is_retry = state.get("draft_response") is not None
    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="compose_response").observe(latency / 1000.0)
    log.info("node_compose_response", is_retry=is_retry, latency_ms=latency)

    updates: dict = {
        "draft_response": result.content.strip(),
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.cost_usd,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "compose_response",
                "model": result.model,
                "provider": result.provider,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "latency_ms": latency,
                "is_retry": is_retry,
            }
        ],
    }
    if is_retry:
        updates["retry_count"] = state.get("retry_count", 0) + 1
    return updates
