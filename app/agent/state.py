"""AgentState TypedDict — the single source of truth flowing through the LangGraph pipeline."""

from operator import add
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    # ── Inputs ──────────────────────────────────────────────────────────────
    conversation_id: str
    user_id: str
    user_message: str
    user_profile: dict
    conversation_history: list[dict]  # last 10 messages

    # ── Pipeline outputs ─────────────────────────────────────────────────────
    intent: str | None
    cleaned_content: str | None
    pii_map: dict | None  # placeholder -> original PII value
    retrieved_chunks: list[dict]
    tool_plan: list[dict]  # [{"name": "...", "arguments": {...}}]
    tool_results: dict  # tool_name -> result dict
    draft_response: str | None
    critique_score: float | None
    critique_feedback: str | None
    retry_count: int
    should_escalate: bool
    final_response: str | None

    # ── Telemetry ────────────────────────────────────────────────────────────
    total_cost_usd: float
    total_latency_ms: int
    audit_trail: Annotated[list[dict], add]  # reducer: append each node's entry
