"""Tool: get_order_status."""

from typing import Any

import structlog
from pydantic import BaseModel

from app.services.mock_crm.crm_service import get_crm
from app.services.tools.base import Tool

log = structlog.get_logger(__name__)


class OrderStatusResult(BaseModel):
    order_id: str
    status: str
    item_name: str
    amount_pkr: float
    eta: str | None
    last_update: str
    tracking_number: str | None = None
    found: bool = True


class GetOrderStatusTool(Tool):
    name = "get_order_status"
    description = (
        "Look up the current status, estimated delivery date, and tracking number "
        "for a customer order. Use when the customer asks about their order."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order ID, e.g. ORD-001.",
            }
        },
        "required": ["order_id"],
    }
    requires_confirmation = False

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        order_id: str = kwargs["order_id"]
        crm = get_crm()
        order = await crm.get_order(order_id)

        if order is None:
            log.warning("order_not_found", order_id=order_id)
            return OrderStatusResult(
                order_id=order_id,
                status="not_found",
                item_name="",
                amount_pkr=0.0,
                eta=None,
                last_update="",
                found=False,
            ).model_dump()

        result = OrderStatusResult(
            order_id=order.order_id,
            status=order.status,
            item_name=order.item_name,
            amount_pkr=order.amount_pkr,
            eta=order.eta.isoformat() if order.eta else None,
            last_update=order.last_update.isoformat(),
            tracking_number=order.tracking_number,
        )
        log.info("order_status_fetched", order_id=order_id, status=order.status)
        return result.model_dump()
