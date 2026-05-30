"""Tool: get_user_orders — list all orders for the authenticated user."""

from typing import Any

import structlog
from pydantic import BaseModel

from app.services.mock_crm.crm_service import get_crm
from app.services.tools.base import Tool

log = structlog.get_logger(__name__)


class UserOrderSummary(BaseModel):
    order_id: str
    status: str
    item_name: str
    amount_pkr: float
    placed_at: str
    eta: str | None


class GetUserOrdersTool(Tool):
    name = "get_user_orders"
    description = (
        "List all orders placed by the current user, newest first. "
        "Use this when the customer asks about their order(s) but has NOT provided an order ID. "
        "Then call get_order_status with the relevant order_id from the results."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The customer's user ID (available from their profile).",
            }
        },
        "required": ["user_id"],
    }
    requires_confirmation = False

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        user_id: str = kwargs["user_id"]
        crm = get_crm()
        orders = await crm.get_orders_by_user(user_id)

        summaries = [
            UserOrderSummary(
                order_id=o.order_id,
                status=o.status,
                item_name=o.item_name,
                amount_pkr=o.amount_pkr,
                placed_at=o.placed_at.isoformat(),
                eta=o.eta.isoformat() if o.eta else None,
            ).model_dump()
            for o in orders
        ]

        log.info("user_orders_fetched", user_id=user_id, count=len(summaries))
        return {"user_id": user_id, "orders": summaries, "total": len(summaries)}
