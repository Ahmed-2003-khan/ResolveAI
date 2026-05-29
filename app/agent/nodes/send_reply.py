"""Node: send_reply — promotes draft_response to final_response."""

from __future__ import annotations

import time

import structlog

from app.agent.state import AgentState

log = structlog.get_logger(__name__)


async def send_reply(state: AgentState) -> dict:
    t0 = time.monotonic()
    final = state.get("draft_response") or ""
    latency = int((time.monotonic() - t0) * 1000)
    log.info("node_send_reply", latency_ms=latency, response_len=len(final))

    return {
        "final_response": final,
        "should_escalate": False,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "send_reply",
                "latency_ms": latency,
                "output": final,
            }
        ],
    }
