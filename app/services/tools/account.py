"""Tools: get_account_balance, get_recent_transactions."""

from typing import Any

import structlog
from pydantic import BaseModel

from app.services.mock_crm.crm_service import get_crm
from app.services.tools.base import Tool

log = structlog.get_logger(__name__)


class AccountBalanceResult(BaseModel):
    user_id: str
    balance: float
    currency: str
    last_txn: str | None
    account_status: str
    found: bool = True


class TransactionItem(BaseModel):
    txn_id: str
    type: str
    amount_pkr: float
    description: str
    created_at: str


class RecentTransactionsResult(BaseModel):
    user_id: str
    transactions: list[TransactionItem]
    count: int


class GetAccountBalanceTool(Tool):
    name = "get_account_balance"
    description = (
        "Retrieve the current account balance and status for a customer. "
        "Use when the customer asks about their balance, account status, or funds."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The internal user ID, e.g. user-001.",
            }
        },
        "required": ["user_id"],
    }
    requires_confirmation = False

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        user_id: str = kwargs["user_id"]
        crm = get_crm()
        account = await crm.get_account(user_id)

        if account is None:
            log.warning("account_not_found", user_id=user_id)
            return AccountBalanceResult(
                user_id=user_id,
                balance=0.0,
                currency="PKR",
                last_txn=None,
                account_status="not_found",
                found=False,
            ).model_dump()

        result = AccountBalanceResult(
            user_id=account.user_id,
            balance=account.balance_pkr,
            currency=account.currency,
            last_txn=(
                account.last_transaction_at.isoformat() if account.last_transaction_at else None
            ),
            account_status=account.status,
        )
        log.info("account_balance_fetched", user_id=user_id, status=account.status)
        return result.model_dump()


class GetRecentTransactionsTool(Tool):
    name = "get_recent_transactions"
    description = (
        "Retrieve the most recent transactions for a customer account. "
        "Use when the customer asks about their transaction history or recent activity."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "The internal user ID, e.g. user-001.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of transactions to return (default 5, max 20).",
                "default": 5,
            },
        },
        "required": ["user_id"],
    }
    requires_confirmation = False

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        user_id: str = kwargs["user_id"]
        limit: int = min(int(kwargs.get("limit", 5)), 20)
        crm = get_crm()
        txns = await crm.get_transactions(user_id, limit=limit)

        items = [
            TransactionItem(
                txn_id=t.txn_id,
                type=t.type,
                amount_pkr=t.amount_pkr,
                description=t.description,
                created_at=t.created_at.isoformat(),
            )
            for t in txns
        ]
        result = RecentTransactionsResult(
            user_id=user_id,
            transactions=items,
            count=len(items),
        )
        log.info("transactions_fetched", user_id=user_id, count=len(items))
        return result.model_dump()
