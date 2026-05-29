"""Node: redact_pii — strips PII from user_message and builds a reversible pii_map."""

from __future__ import annotations

import time

import structlog

from app.agent.state import AgentState
from app.services.pii.redactor import PIIRedactor

log = structlog.get_logger(__name__)

_redactor = PIIRedactor()


async def redact_pii(state: AgentState) -> dict:
    t0 = time.monotonic()

    result = _redactor.redact(state["user_message"])

    latency = int((time.monotonic() - t0) * 1000)
    log.info(
        "node_redact_pii",
        pii_tokens_found=len(result.pii_map),
        latency_ms=latency,
    )

    return {
        "cleaned_content": result.redacted_text,
        "pii_map": result.pii_map,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "redact_pii",
                "pii_tokens_found": len(result.pii_map),
                "latency_ms": latency,
                "output": result.redacted_text,
            }
        ],
    }
