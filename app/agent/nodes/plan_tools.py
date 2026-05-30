"""Node: plan_tools — OpenAI function-calling pass to decide which tools to invoke."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import yaml
import structlog

from app.agent.state import AgentState
from app.observability.metrics import NODE_DURATION
from app.services.llm.base import ChatMessage
from app.services.llm.router import get_llm_router
from app.services.tools.registry import get_tool_registry

log = structlog.get_logger(__name__)
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Order IDs always look like ORD-123 or similar patterns
_ORDER_ID_RE = re.compile(r"\bORD-\d+\b", re.IGNORECASE)


def _kb_context_text(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant knowledge base articles found."
    parts = []
    for i, c in enumerate(chunks, 1):
        title = c.get("title") or c.get("source_id", f"Chunk {i}")
        parts.append(f"[{i}] {title}\n{c.get('content', '')}")
    return "\n\n".join(parts)


def _filter_tools(tool_schemas: list[dict], state: AgentState) -> list[dict]:
    """Remove tools whose required parameters cannot be satisfied from the message.

    Specifically: hide get_order_status when no order ID is present in the
    message.  This prevents the LLM from hallucinating an order ID.
    """
    message = (state.get("cleaned_content") or state.get("user_message") or "")
    has_order_id = bool(_ORDER_ID_RE.search(message))
    if has_order_id:
        return tool_schemas
    # Strip get_order_status so the LLM can't even attempt to call it
    filtered = [t for t in tool_schemas if t.get("function", {}).get("name") != "get_order_status"]
    if len(filtered) < len(tool_schemas):
        log.info("plan_tools_hiding_get_order_status_no_id_in_message")
    return filtered


async def plan_tools(state: AgentState) -> dict:
    t0 = time.monotonic()
    with open(_PROMPTS_DIR / "plan_tools.yaml") as fh:
        prompt = yaml.safe_load(fh)

    kb_context = _kb_context_text(state.get("retrieved_chunks") or [])
    messages = [
        ChatMessage(role="system", content=prompt["system"].strip()),
        ChatMessage(
            role="user",
            content=prompt["user"]
            .format(
                intent=state.get("intent") or "general_inquiry",
                user_message=state.get("cleaned_content") or state["user_message"],
                kb_context=kb_context,
            )
            .strip(),
        ),
    ]

    registry = get_tool_registry()
    tool_schemas = _filter_tools(registry.openai_schemas(), state)

    router = get_llm_router()
    result = await router.chat(
        messages,
        model_tier="cheap",
        max_tokens=500,
        tools=tool_schemas,
        tool_choice="auto",
    )

    tool_plan: list[dict] = []
    raw_calls = result.raw.get("tool_calls") or []
    for call in raw_calls:
        fn = call.get("function") or {}
        name = fn.get("name", "")
        try:
            arguments = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        if name and registry.get(name):
            tool_plan.append({"name": name, "arguments": arguments})

    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="plan_tools").observe(latency / 1000.0)
    log.info("node_plan_tools", tools_planned=len(tool_plan), latency_ms=latency)

    return {
        "tool_plan": tool_plan,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.cost_usd,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "plan_tools",
                "model": result.model,
                "provider": result.provider,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "latency_ms": latency,
                "output": [t["name"] for t in tool_plan],
            }
        ],
    }
