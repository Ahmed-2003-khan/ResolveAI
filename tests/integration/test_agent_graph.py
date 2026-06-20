"""Integration tests for the LangGraph agent graph — 5 end-to-end scenarios.

All LLM calls, tool executions, and retrieval are mocked so the tests run
without real credentials or a live database.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.agent.graph import build_graph
from app.services.llm.base import ChatResult

# ── Shared helpers ────────────────────────────────────────────────────────────

_SAMPLE_CHUNKS = [
    {
        "id": "chunk-1",
        "source_id": "faq-001",
        "source_type": "faq",
        "title": "Refund Policy",
        "content": "Refunds are processed within 3-5 business days.",
        "product_area": "refunds",
    }
]


def _make_chat_result(content: str, tool_calls: list[dict] | None = None) -> ChatResult:
    return ChatResult(
        content=content,
        model="gpt-4o-mini",
        provider="openai",
        input_tokens=50,
        output_tokens=20,
        cost_usd=0.0001,
        latency_ms=300,
        raw={"tool_calls": tool_calls or []},
    )


def _base_input(message: str = "Where is my order?") -> dict:
    return {
        "conversation_id": "conv-test-001",
        "user_id": "user-001",
        "user_message": message,
        "user_profile": {"full_name": "Ali Khan", "plan_tier": "standard"},
        "conversation_history": [],
        "intent": None,
        "cleaned_content": None,
        "pii_map": None,
        "retrieved_chunks": [],
        "tool_plan": [],
        "tool_results": {},
        "draft_response": None,
        "critique_score": None,
        "critique_feedback": None,
        "retry_count": 0,
        "should_escalate": False,
        "final_response": None,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "audit_trail": [],
    }


def _build_test_graph():
    return build_graph(MemorySaver())


# ── Scenario 1: Happy path — order status query ───────────────────────────────


@pytest.mark.asyncio
async def test_order_status_happy_path():
    """Customer asks for order status → tool executed → valid response sent."""
    graph = _build_test_graph()

    order_tool_call = [
        {
            "function": {
                "name": "get_order_status",
                "arguments": json.dumps({"order_id": "ORD-123"}),
            }
        }
    ]

    call_sequence = [
        _make_chat_result("order_status"),  # classify_intent
        _make_chat_result("", tool_calls=order_tool_call),  # plan_tools
        _make_chat_result(
            "Your order ORD-123 has been dispatched and will arrive by Friday."
        ),  # compose
        _make_chat_result(json.dumps({"score": 0.9, "feedback": "Looks good."})),  # critique
    ]
    call_iter = iter(call_sequence)

    async def mock_chat(messages, **kwargs):
        return next(call_iter)

    mock_order_result = {
        "order_id": "ORD-123",
        "status": "dispatched",
        "eta": "2026-06-02",
        "last_update": "2026-05-30",
    }

    with (
        patch("app.agent.nodes.classify_intent.get_llm_router") as mock_router_cls,
        patch("app.agent.nodes.plan_tools.get_llm_router") as mock_router_plan,
        patch("app.agent.nodes.compose_response.get_llm_router") as mock_router_compose,
        patch("app.agent.nodes.critique.get_llm_router") as mock_router_critique,
        patch("app.agent.nodes.retrieve.get_retriever") as mock_retriever_cls,
        patch("app.agent.nodes.execute_tools.get_tool_registry") as mock_registry_cls,
        patch("app.agent.nodes.plan_tools.get_tool_registry") as mock_registry_plan,
    ):
        for mock_r in [
            mock_router_cls,
            mock_router_plan,
            mock_router_compose,
            mock_router_critique,
        ]:
            router = MagicMock()
            router.chat = mock_chat
            mock_r.return_value = router

        retriever = AsyncMock()
        retriever.retrieve.return_value = _SAMPLE_CHUNKS
        mock_retriever_cls.return_value = retriever

        registry = MagicMock()
        registry.openai_schemas.return_value = [
            {
                "type": "function",
                "function": {"name": "get_order_status", "description": "", "parameters": {}},
            }
        ]
        registry.get.return_value = MagicMock()
        registry.execute = AsyncMock(return_value=mock_order_result)
        mock_registry_cls.return_value = registry
        mock_registry_plan.return_value = registry

        result = await graph.ainvoke(
            _base_input("Where is my order ORD-123?"),
            config={"configurable": {"thread_id": "t1"}},
        )

    assert result["final_response"] is not None
    assert len(result["final_response"]) > 0
    assert result["should_escalate"] is False
    assert len(result["audit_trail"]) >= 4
    assert result["intent"] == "order_status"


# ── Scenario 2: Refund request ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_request_tool_called():
    """Customer requests refund → create_refund_request tool executed."""
    graph = _build_test_graph()

    refund_tool_call = [
        {
            "function": {
                "name": "create_refund_request",
                "arguments": json.dumps(
                    {"order_id": "ORD-456", "reason": "damaged", "amount": 1500}
                ),
            }
        }
    ]

    call_sequence = [
        _make_chat_result("refund_request"),
        _make_chat_result("", tool_calls=refund_tool_call),
        _make_chat_result(
            "Your refund request has been submitted. You will receive confirmation within 3-5 business days."
        ),
        _make_chat_result(json.dumps({"score": 0.85, "feedback": "Clear and helpful."})),
    ]
    call_iter = iter(call_sequence)

    async def mock_chat(messages, **kwargs):
        return next(call_iter)

    mock_refund_result = {
        "request_id": "REF-789",
        "order_id": "ORD-456",
        "status": "pending",
        "amount_pkr": 1500.0,
        "message": "Refund request REF-789 submitted.",
    }

    with (
        patch("app.agent.nodes.classify_intent.get_llm_router") as m1,
        patch("app.agent.nodes.plan_tools.get_llm_router") as m2,
        patch("app.agent.nodes.compose_response.get_llm_router") as m3,
        patch("app.agent.nodes.critique.get_llm_router") as m4,
        patch("app.agent.nodes.retrieve.get_retriever") as mr,
        patch("app.agent.nodes.execute_tools.get_tool_registry") as mte,
        patch("app.agent.nodes.plan_tools.get_tool_registry") as mtp,
    ):
        for m in [m1, m2, m3, m4]:
            r = MagicMock()
            r.chat = mock_chat
            m.return_value = r

        retriever = AsyncMock()
        retriever.retrieve.return_value = _SAMPLE_CHUNKS
        mr.return_value = retriever

        registry = MagicMock()
        registry.openai_schemas.return_value = []
        registry.get.return_value = MagicMock()
        registry.execute = AsyncMock(return_value=mock_refund_result)
        mte.return_value = registry
        mtp.return_value = registry

        result = await graph.ainvoke(
            _base_input("I want a refund for my order ORD-456, it arrived damaged."),
            config={"configurable": {"thread_id": "t2"}},
        )

    assert result["intent"] == "refund_request"
    assert result["final_response"] is not None
    assert result["should_escalate"] is False
    assert "create_refund_request" in result["tool_results"]


# ── Scenario 3: Direct escalation request ────────────────────────────────────


@pytest.mark.asyncio
async def test_explicit_escalation_bypasses_rag():
    """Intent == escalate_human → graph routes directly to escalate, skipping RAG."""
    graph = _build_test_graph()

    async def mock_chat(messages, **kwargs):
        return _make_chat_result("escalate_human")

    with (
        patch("app.agent.nodes.classify_intent.get_llm_router") as m1,
        patch("app.agent.nodes.retrieve.get_retriever") as mr,
    ):
        r = MagicMock()
        r.chat = mock_chat
        m1.return_value = r

        retriever = AsyncMock()
        retriever.retrieve.return_value = []
        mr.return_value = retriever

        result = await graph.ainvoke(
            _base_input("I need to talk to a real human agent right now."),
            config={"configurable": {"thread_id": "t3"}},
        )

    assert result["intent"] == "escalate_human"
    assert result["should_escalate"] is True
    assert result["final_response"] is not None
    assert (
        "specialist" in result["final_response"].lower()
        or "agent" in result["final_response"].lower()
    )
    # redact_pii, retrieve, plan_tools, compose should NOT appear in audit trail
    node_names = [e["node"] for e in result["audit_trail"]]
    assert "escalate" in node_names
    assert "compose_response" not in node_names


# ── Scenario 4: Critique retry then escalation ────────────────────────────────


@pytest.mark.asyncio
async def test_critique_retry_then_escalate():
    """Draft repeatedly scores below threshold → after 2 retries graph escalates."""
    graph = _build_test_graph()

    bad_critique = json.dumps({"score": 0.4, "feedback": "Response is vague."})

    call_sequence = [
        _make_chat_result("general_inquiry"),  # classify
        _make_chat_result("", tool_calls=[]),  # plan_tools (no tools)
        _make_chat_result("Here is some info."),  # compose 1
        _make_chat_result(bad_critique),  # critique 1
        _make_chat_result("Here is better info."),  # compose 2 (retry 1)
        _make_chat_result(bad_critique),  # critique 2
        _make_chat_result("Here is even better info."),  # compose 3 (retry 2)
        _make_chat_result(bad_critique),  # critique 3 → escalate
    ]
    call_iter = iter(call_sequence)

    async def mock_chat(messages, **kwargs):
        return next(call_iter)

    with (
        patch("app.agent.nodes.classify_intent.get_llm_router") as m1,
        patch("app.agent.nodes.plan_tools.get_llm_router") as m2,
        patch("app.agent.nodes.compose_response.get_llm_router") as m3,
        patch("app.agent.nodes.critique.get_llm_router") as m4,
        patch("app.agent.nodes.retrieve.get_retriever") as mr,
        patch("app.agent.nodes.plan_tools.get_tool_registry") as mtp,
    ):
        for m in [m1, m2, m3, m4]:
            r = MagicMock()
            r.chat = mock_chat
            m.return_value = r

        retriever = AsyncMock()
        retriever.retrieve.return_value = _SAMPLE_CHUNKS
        mr.return_value = retriever

        registry = MagicMock()
        registry.openai_schemas.return_value = []
        registry.get.return_value = None
        mtp.return_value = registry

        result = await graph.ainvoke(
            _base_input("What is your return policy?"),
            config={"configurable": {"thread_id": "t4"}},
        )

    assert result["should_escalate"] is True
    assert result["retry_count"] == 2
    node_names = [e["node"] for e in result["audit_trail"]]
    assert node_names.count("critique") == 3
    assert node_names.count("compose_response") == 3
    assert "escalate" in node_names


# ── Scenario 5: General inquiry — no tools needed ────────────────────────────


@pytest.mark.asyncio
async def test_general_inquiry_no_tools():
    """Pure FAQ question — no tools planned, response composed from KB context."""
    graph = _build_test_graph()

    call_sequence = [
        _make_chat_result("general_inquiry"),
        _make_chat_result("", tool_calls=[]),  # plan_tools → no tools
        _make_chat_result(
            "Our platform supports payments via JazzCash, EasyPaisa, and bank transfer."
        ),
        _make_chat_result(json.dumps({"score": 0.88, "feedback": "Looks good."})),
    ]
    call_iter = iter(call_sequence)

    async def mock_chat(messages, **kwargs):
        return next(call_iter)

    with (
        patch("app.agent.nodes.classify_intent.get_llm_router") as m1,
        patch("app.agent.nodes.plan_tools.get_llm_router") as m2,
        patch("app.agent.nodes.compose_response.get_llm_router") as m3,
        patch("app.agent.nodes.critique.get_llm_router") as m4,
        patch("app.agent.nodes.retrieve.get_retriever") as mr,
        patch("app.agent.nodes.plan_tools.get_tool_registry") as mtp,
    ):
        for m in [m1, m2, m3, m4]:
            r = MagicMock()
            r.chat = mock_chat
            m.return_value = r

        retriever = AsyncMock()
        retriever.retrieve.return_value = _SAMPLE_CHUNKS
        mr.return_value = retriever

        registry = MagicMock()
        registry.openai_schemas.return_value = []
        registry.get.return_value = None
        mtp.return_value = registry

        result = await graph.ainvoke(
            _base_input("What payment methods do you support?"),
            config={"configurable": {"thread_id": "t5"}},
        )

    assert result["intent"] == "general_inquiry"
    assert result["tool_plan"] == []
    assert result["tool_results"] == {}
    assert result["should_escalate"] is False
    assert result["final_response"] is not None
    node_names = [e["node"] for e in result["audit_trail"]]
    assert "execute_tools" not in node_names
    assert "send_reply" in node_names
