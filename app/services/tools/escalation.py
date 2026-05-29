"""Tool: escalate_to_human."""

from typing import Any

import structlog
from pydantic import BaseModel

from app.services.mock_crm.crm_service import get_crm
from app.services.tools.base import Tool

log = structlog.get_logger(__name__)


class EscalationResult(BaseModel):
    queued: bool
    escalation_id: str
    position: int
    message: str


class EscalateToHumanTool(Tool):
    name = "escalate_to_human"
    description = (
        "Transfer the conversation to a human support agent. "
        "Use when the customer explicitly requests a human, when the issue is too complex "
        "for automated resolution, or after repeated failed attempts to help."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "conversation_id": {
                "type": "string",
                "description": "The active conversation ID.",
            },
            "reason": {
                "type": "string",
                "description": "Reason for escalation (shown to the human agent).",
            },
        },
        "required": ["conversation_id", "reason"],
    }
    requires_confirmation = True

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        conversation_id: str = kwargs["conversation_id"]
        reason: str = kwargs["reason"]

        crm = get_crm()
        entry = await crm.escalate(
            conversation_id=conversation_id,
            reason=reason,
        )
        result = EscalationResult(
            queued=True,
            escalation_id=entry.escalation_id,
            position=entry.position,
            message=(
                f"You are number {entry.position} in the queue. "
                "A human agent will join this conversation shortly."
            ),
        )
        log.info(
            "escalation_queued",
            escalation_id=entry.escalation_id,
            conversation_id=conversation_id,
            position=entry.position,
        )
        return result.model_dump()
