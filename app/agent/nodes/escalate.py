"""Node: escalate — marks the conversation as needing a human agent."""

from __future__ import annotations

import time

import structlog

from app.agent.state import AgentState

log = structlog.get_logger(__name__)

_APOLOGY = (
    "We apologize for the inconvenience. Your query requires the attention of one of "
    "our human support specialists. We have added you to the queue and an agent will "
    "reach out to you shortly. Thank you for your patience."
)


async def escalate(state: AgentState) -> dict:
    t0 = time.monotonic()
    intent = state.get("intent") or "unknown"
    reason = "abuse" if intent == "abuse" else (
        "explicit_request" if intent == "escalate_human" else "low_critique_score"
    )

    latency = int((time.monotonic() - t0) * 1000)
    log.info("node_escalate", reason=reason, conversation_id=state.get("conversation_id"))

    return {
        "should_escalate": True,
        "final_response": _APOLOGY,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "escalate",
                "reason": reason,
                "latency_ms": latency,
                "output": _APOLOGY,
            }
        ],
    }
