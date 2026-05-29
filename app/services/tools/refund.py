"""Tool: create_refund_request."""

from typing import Any

import structlog
from pydantic import BaseModel

from app.services.mock_crm.crm_service import get_crm
from app.services.tools.base import Tool

log = structlog.get_logger(__name__)


class RefundResult(BaseModel):
    request_id: str
    order_id: str
    status: str
    amount_pkr: float
    message: str


class CreateRefundRequestTool(Tool):
    name = "create_refund_request"
    description = (
        "Submit a refund request for a customer order. "
        "Use when the customer explicitly asks for a refund and provides an order ID."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID to refund, e.g. ORD-001.",
            },
            "reason": {
                "type": "string",
                "description": "Customer-provided reason for the refund.",
            },
            "amount": {
                "type": "number",
                "description": "Refund amount in PKR.",
            },
        },
        "required": ["order_id", "reason", "amount"],
    }
    requires_confirmation = True

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        order_id: str = kwargs["order_id"]
        reason: str = kwargs["reason"]
        amount: float = float(kwargs["amount"])

        crm = get_crm()
        refund = await crm.create_refund(
            order_id=order_id,
            reason=reason,
            amount_pkr=amount,
        )
        result = RefundResult(
            request_id=refund.request_id,
            order_id=order_id,
            status=refund.status,
            amount_pkr=amount,
            message=(
                f"Refund request {refund.request_id} submitted successfully. "
                "It will be reviewed within 3–5 business days."
            ),
        )
        log.info(
            "refund_request_created",
            request_id=refund.request_id,
            order_id=order_id,
            amount=amount,
        )
        return result.model_dump()
