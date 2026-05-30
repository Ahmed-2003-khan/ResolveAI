"""Node: escalate — handles human escalations, abuse blocks, and session goodbyes."""

from __future__ import annotations

import time

import structlog

from app.agent.state import AgentState
from app.observability.metrics import ESCALATIONS, NODE_DURATION

log = structlog.get_logger(__name__)

_APOLOGY = (
    "We apologize for the inconvenience. Your query requires the attention of one of "
    "our human support specialists. We have added you to the queue and an agent will "
    "reach out to you shortly. Thank you for your patience."
)

_FAREWELL = (
    "Shukriya hamse contact karne ke liye! Umeed hai aapka masla hal ho gaya. "
    "Agar dobara koi madad chahiye toh hum hamesha yahan hain. Allah Hafiz! 🙏"
)


async def escalate(state: AgentState) -> dict:
    t0 = time.monotonic()
    intent = state.get("intent") or "unknown"

    if intent == "session_end":
        latency = int((time.monotonic() - t0) * 1000)
        NODE_DURATION.labels(node="escalate").observe(latency / 1000.0)
        log.info("node_escalate_session_end", conversation_id=state.get("conversation_id"))
        return {
            "should_escalate": False,
            "final_response": _FAREWELL,
            "total_latency_ms": state.get("total_latency_ms", 0) + latency,
            "audit_trail": [
                {
                    "node": "escalate",
                    "reason": "session_end",
                    "latency_ms": latency,
                    "output": _FAREWELL,
                }
            ],
        }

    reason = (
        "abuse" if intent == "abuse"
        else "explicit_request" if intent == "escalate_human"
        else "low_critique_score"
    )

    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="escalate").observe(latency / 1000.0)
    ESCALATIONS.labels(reason=reason).inc()
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
