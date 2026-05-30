"""LangGraph StateGraph — wires all nodes together with conditional routing."""

from __future__ import annotations

import structlog
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.observability.metrics import CACHE_HITS, CACHE_MISSES
from app.services.cache.semantic_cache import get_semantic_cache

log = structlog.get_logger(__name__)

from app.agent.nodes import (
    classify_intent,
    compose_response,
    critique,
    escalate,
    execute_tools,
    plan_tools,
    redact_pii,
    retrieve,
    send_reply,
)
from app.agent.state import AgentState


# ── Routing functions ────────────────────────────────────────────────────────


def _route_after_classify(state: AgentState) -> str:
    """Immediately escalate on explicit escalation request or abusive content."""
    intent = state.get("intent") or ""
    if intent in ("escalate_human", "abuse"):
        return "escalate"
    return "redact_pii"


def _route_after_plan_tools(state: AgentState) -> str:
    """If the planner chose tools, execute them; otherwise go straight to compose."""
    if state.get("tool_plan"):
        return "execute_tools"
    return "compose_response"


def _route_after_critique(state: AgentState) -> str:
    """Pass → send_reply; fail with retries left → compose; fail exhausted → escalate."""
    score = state.get("critique_score") or 0.0
    retry_count = state.get("retry_count", 0)
    if score >= 0.7:
        return "send_reply"
    if retry_count < 2:
        return "compose_response"
    return "escalate"


# ── Graph builder ────────────────────────────────────────────────────────────


def build_graph(checkpointer=None):
    """Build and compile the ResolveAI agent graph.

    Args:
        checkpointer: LangGraph checkpointer instance.  Pass ``None`` to skip
                      persistence (useful in unit tests).
    """
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("redact_pii", redact_pii)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("plan_tools", plan_tools)
    workflow.add_node("execute_tools", execute_tools)
    workflow.add_node("compose_response", compose_response)
    workflow.add_node("critique", critique)
    workflow.add_node("escalate", escalate)
    workflow.add_node("send_reply", send_reply)

    # Entry point
    workflow.add_edge(START, "classify_intent")

    # classify_intent → (escalate | redact_pii)
    workflow.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {"escalate": "escalate", "redact_pii": "redact_pii"},
    )

    # Linear: redact_pii → retrieve → plan_tools
    workflow.add_edge("redact_pii", "retrieve")
    workflow.add_edge("retrieve", "plan_tools")

    # plan_tools → (execute_tools | compose_response)
    workflow.add_conditional_edges(
        "plan_tools",
        _route_after_plan_tools,
        {"execute_tools": "execute_tools", "compose_response": "compose_response"},
    )

    # execute_tools → compose_response
    workflow.add_edge("execute_tools", "compose_response")

    # compose_response → critique
    workflow.add_edge("compose_response", "critique")

    # critique → (send_reply | compose_response | escalate)
    workflow.add_conditional_edges(
        "critique",
        _route_after_critique,
        {
            "send_reply": "send_reply",
            "compose_response": "compose_response",
            "escalate": "escalate",
        },
    )

    # Terminal nodes
    workflow.add_edge("send_reply", END)
    workflow.add_edge("escalate", END)

    kwargs: dict = {}
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer

    return workflow.compile(**kwargs)


# Module-level default graph (no persistence — swap in tests or override at startup)
_default_graph = None


def get_graph(checkpointer=None):
    """Return the compiled graph, building it once with a MemorySaver if not provided."""
    global _default_graph
    if checkpointer is not None:
        return build_graph(checkpointer)
    if _default_graph is None:
        _default_graph = build_graph(MemorySaver())
    return _default_graph


# Friendly alias used in scripts and notebooks
create_agent_graph = get_graph


# ── Cache-aware entry point ───────────────────────────────────────────────────


async def run_with_cache(
    state: dict,
    config: dict | None = None,
    *,
    checkpointer=None,
) -> dict:
    """Run the agent graph with a semantic cache layer.

    1. Look up the user message in the semantic cache.
    2. Cache hit  → return immediately with ``cache_hit=True`` in the audit trail.
    3. Cache miss → invoke the full graph, then store the final response.

    The cache service swallows its own errors so this function never raises due
    to cache failures — it degrades gracefully to a plain graph run.
    """
    cache = get_semantic_cache()
    user_message = state.get("user_message", "")
    conversation_id = state.get("conversation_id", "")

    cached_response = await cache.get(user_message)

    if cached_response is not None:
        CACHE_HITS.inc()
        log.info("cache_hit", conversation_id=conversation_id)
        return {
            **state,
            "final_response": cached_response,
            "audit_trail": [
                {
                    "node": "semantic_cache",
                    "cache_hit": True,
                    "conversation_id": conversation_id,
                }
            ],
        }

    CACHE_MISSES.inc()
    log.info("cache_miss", conversation_id=conversation_id)

    graph = get_graph(checkpointer)
    # MemorySaver requires a thread_id; default to conversation_id so callers
    # don't need to wire configurable manually.
    if config is None:
        config = {"configurable": {"thread_id": conversation_id or "default"}}
    elif "configurable" not in config:
        config = {**config, "configurable": {"thread_id": conversation_id or "default"}}
    result: dict = await graph.ainvoke(state, config)

    final_response = result.get("final_response")
    # Only cache responses that required NO tool calls.
    # Tool results contain personal data (order status, account balance, etc.)
    # tied to a specific user — caching them would return one user's private
    # information to a different user who asks a similar-sounding question.
    # Generic KB/FAQ answers (no tools used) are safe to cache for everyone.
    tools_were_called = bool(result.get("tool_results"))
    if final_response and not tools_were_called:
        await cache.set(user_message, final_response)
    elif final_response and tools_were_called:
        log.info(
            "cache_skip_personalized",
            conversation_id=conversation_id,
            tools_used=list(result.get("tool_results", {}).keys()),
        )

    return result
