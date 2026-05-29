"""LangGraph StateGraph — wires all nodes together with conditional routing."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

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
