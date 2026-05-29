"""Tool: create_support_ticket."""

from typing import Any

import structlog
from pydantic import BaseModel

from app.services.mock_crm.crm_service import get_crm
from app.services.tools.base import Tool

log = structlog.get_logger(__name__)

_VALID_PRIORITIES = {"low", "medium", "high", "urgent"}


class TicketResult(BaseModel):
    ticket_id: str
    user_id: str
    priority: str
    status: str
    message: str


class CreateSupportTicketTool(Tool):
    name = "create_support_ticket"
    description = (
        "Create a support ticket for a customer issue that requires follow-up. "
        "Use when the problem cannot be resolved immediately or needs human review."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The internal user ID, e.g. user-001.",
            },
            "summary": {
                "type": "string",
                "description": "Brief description of the issue (1–2 sentences).",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
                "description": "Ticket priority. Default to 'medium' unless clearly urgent.",
            },
        },
        "required": ["user_id", "summary", "priority"],
    }
    requires_confirmation = True

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        user_id: str = kwargs["user_id"]
        summary: str = kwargs["summary"]
        priority: str = kwargs.get("priority", "medium")

        if priority not in _VALID_PRIORITIES:
            priority = "medium"

        crm = get_crm()
        ticket = await crm.create_ticket(
            user_id=user_id,
            summary=summary,
            priority=priority,
        )
        result = TicketResult(
            ticket_id=ticket.ticket_id,
            user_id=user_id,
            priority=priority,
            status=ticket.status,
            message=(
                f"Support ticket {ticket.ticket_id} created with {priority} priority. "
                "Our team will get back to you shortly."
            ),
        )
        log.info(
            "support_ticket_created",
            ticket_id=ticket.ticket_id,
            user_id=user_id,
            priority=priority,
        )
        return result.model_dump()
