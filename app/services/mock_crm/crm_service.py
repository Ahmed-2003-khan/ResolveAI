"""In-memory mock CRM service — deterministic seed data for portfolio demo.

All state lives in module-level dicts and is reset on process restart.
Write operations (refunds, tickets, escalations) accumulate new entries
without touching the seed rows so tests stay reproducible.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from pydantic import BaseModel

log = structlog.get_logger(__name__)

# ── Timezone-aware "now" for seed offsets ──────────────────────────────────────

_EPOCH = datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc)


def _dt(days: int = 0, hours: int = 0) -> datetime:
    """Return a datetime relative to the fixed epoch (positive = future)."""
    return _EPOCH + timedelta(days=days, hours=hours)


# ── Pydantic data models ───────────────────────────────────────────────────────


class Order(BaseModel):
    order_id: str
    user_id: str
    status: str  # pending|processing|dispatched|delivered|cancelled
    item_name: str
    amount_pkr: float
    placed_at: datetime
    eta: datetime | None = None
    last_update: datetime
    tracking_number: str | None = None


class Account(BaseModel):
    user_id: str
    balance_pkr: float
    currency: str = "PKR"
    last_transaction_at: datetime | None = None
    status: str  # active|frozen|closed


class Transaction(BaseModel):
    txn_id: str
    user_id: str
    type: str  # credit|debit
    amount_pkr: float
    description: str
    created_at: datetime


class RefundRequest(BaseModel):
    request_id: str
    order_id: str
    user_id: str
    reason: str
    amount_pkr: float
    status: str = "pending"
    created_at: datetime


class SupportTicket(BaseModel):
    ticket_id: str
    user_id: str
    summary: str
    priority: str  # low|medium|high|urgent
    status: str = "open"
    created_at: datetime


class EscalationEntry(BaseModel):
    escalation_id: str
    conversation_id: str
    reason: str
    position: int
    status: str = "queued"
    created_at: datetime


# ── Seed data ──────────────────────────────────────────────────────────────────

_SEED_ORDERS: list[dict[str, Any]] = [
    {
        "order_id": "ORD-001",
        "user_id": "user-001",
        "status": "dispatched",
        "item_name": "Samsung Galaxy A55",
        "amount_pkr": 89_999.0,
        "placed_at": _dt(-3),
        "eta": _dt(2),
        "last_update": _dt(0, -6),
        "tracking_number": "TRK-PKG-001",
    },
    {
        "order_id": "ORD-002",
        "user_id": "user-001",
        "status": "delivered",
        "item_name": "Wireless Earbuds",
        "amount_pkr": 4_500.0,
        "placed_at": _dt(-10),
        "eta": _dt(-7),
        "last_update": _dt(-7),
        "tracking_number": "TRK-PKG-002",
    },
    {
        "order_id": "ORD-003",
        "user_id": "user-002",
        "status": "processing",
        "item_name": "Laptop Stand",
        "amount_pkr": 3_200.0,
        "placed_at": _dt(-1),
        "eta": _dt(4),
        "last_update": _dt(-1),
        "tracking_number": None,
    },
    {
        "order_id": "ORD-004",
        "user_id": "user-002",
        "status": "cancelled",
        "item_name": "USB-C Hub",
        "amount_pkr": 2_800.0,
        "placed_at": _dt(-5),
        "eta": None,
        "last_update": _dt(-4),
        "tracking_number": None,
    },
    {
        "order_id": "ORD-005",
        "user_id": "user-003",
        "status": "pending",
        "item_name": "Mechanical Keyboard",
        "amount_pkr": 12_500.0,
        "placed_at": _dt(0, -2),
        "eta": _dt(5),
        "last_update": _dt(0, -2),
        "tracking_number": None,
    },
    {
        "order_id": "ORD-006",
        "user_id": "user-004",
        "status": "delivered",
        "item_name": "Power Bank 20000mAh",
        "amount_pkr": 6_999.0,
        "placed_at": _dt(-14),
        "eta": _dt(-11),
        "last_update": _dt(-11),
        "tracking_number": "TRK-PKG-006",
    },
    {
        "order_id": "ORD-007",
        "user_id": "user-005",
        "status": "dispatched",
        "item_name": "Smart Watch",
        "amount_pkr": 29_999.0,
        "placed_at": _dt(-2),
        "eta": _dt(1),
        "last_update": _dt(0, -12),
        "tracking_number": "TRK-PKG-007",
    },
]

_SEED_ACCOUNTS: list[dict[str, Any]] = [
    {
        "user_id": "user-001",
        "balance_pkr": 45_250.75,
        "currency": "PKR",
        "last_transaction_at": _dt(-1),
        "status": "active",
    },
    {
        "user_id": "user-002",
        "balance_pkr": 12_000.00,
        "currency": "PKR",
        "last_transaction_at": _dt(-3),
        "status": "active",
    },
    {
        "user_id": "user-003",
        "balance_pkr": 0.00,
        "currency": "PKR",
        "last_transaction_at": _dt(-30),
        "status": "frozen",
    },
    {
        "user_id": "user-004",
        "balance_pkr": 125_800.50,
        "currency": "PKR",
        "last_transaction_at": _dt(0, -3),
        "status": "active",
    },
    {
        "user_id": "user-005",
        "balance_pkr": 7_340.00,
        "currency": "PKR",
        "last_transaction_at": _dt(-2),
        "status": "active",
    },
]

_SEED_TRANSACTIONS: list[dict[str, Any]] = [
    # user-001
    {
        "txn_id": "TXN-001",
        "user_id": "user-001",
        "type": "debit",
        "amount_pkr": 89_999.0,
        "description": "Purchase: Samsung Galaxy A55 (ORD-001)",
        "created_at": _dt(-3),
    },
    {
        "txn_id": "TXN-002",
        "user_id": "user-001",
        "type": "credit",
        "amount_pkr": 50_000.0,
        "description": "Top-up via Easypaisa",
        "created_at": _dt(-2),
    },
    {
        "txn_id": "TXN-003",
        "user_id": "user-001",
        "type": "debit",
        "amount_pkr": 4_500.0,
        "description": "Purchase: Wireless Earbuds (ORD-002)",
        "created_at": _dt(-10),
    },
    # user-002
    {
        "txn_id": "TXN-004",
        "user_id": "user-002",
        "type": "debit",
        "amount_pkr": 3_200.0,
        "description": "Purchase: Laptop Stand (ORD-003)",
        "created_at": _dt(-1),
    },
    {
        "txn_id": "TXN-005",
        "user_id": "user-002",
        "type": "credit",
        "amount_pkr": 2_800.0,
        "description": "Refund: USB-C Hub (ORD-004)",
        "created_at": _dt(-4),
    },
    # user-004
    {
        "txn_id": "TXN-006",
        "user_id": "user-004",
        "type": "credit",
        "amount_pkr": 200_000.0,
        "description": "Salary credit",
        "created_at": _dt(0, -3),
    },
    {
        "txn_id": "TXN-007",
        "user_id": "user-004",
        "type": "debit",
        "amount_pkr": 6_999.0,
        "description": "Purchase: Power Bank (ORD-006)",
        "created_at": _dt(-14),
    },
    {
        "txn_id": "TXN-008",
        "user_id": "user-004",
        "type": "debit",
        "amount_pkr": 67_200.50,
        "description": "Bill payment: SNGPL",
        "created_at": _dt(-7),
    },
    # user-005
    {
        "txn_id": "TXN-009",
        "user_id": "user-005",
        "type": "debit",
        "amount_pkr": 29_999.0,
        "description": "Purchase: Smart Watch (ORD-007)",
        "created_at": _dt(-2),
    },
    {
        "txn_id": "TXN-010",
        "user_id": "user-005",
        "type": "credit",
        "amount_pkr": 37_339.0,
        "description": "Transfer from JazzCash",
        "created_at": _dt(-5),
    },
]


# ── In-memory store ────────────────────────────────────────────────────────────


def _build_order_store() -> dict[str, Order]:
    return {d["order_id"]: Order(**d) for d in _SEED_ORDERS}


def _build_account_store() -> dict[str, Account]:
    return {d["user_id"]: Account(**d) for d in _SEED_ACCOUNTS}


def _build_txn_store() -> dict[str, list[Transaction]]:
    store: dict[str, list[Transaction]] = {}
    for d in _SEED_TRANSACTIONS:
        store.setdefault(d["user_id"], []).append(Transaction(**d))
    # Sort each user's transactions newest-first.
    for txns in store.values():
        txns.sort(key=lambda t: t.created_at, reverse=True)
    return store


class MockCRMService:
    """Singleton in-memory CRM.  All state is process-scoped."""

    def __init__(self) -> None:
        self._orders: dict[str, Order] = _build_order_store()
        self._accounts: dict[str, Account] = _build_account_store()
        self._transactions: dict[str, list[Transaction]] = _build_txn_store()
        self._refunds: dict[str, RefundRequest] = {}
        self._tickets: dict[str, SupportTicket] = {}
        self._escalations: list[EscalationEntry] = []

    # ── Read operations ──────────────────────────────────────────────────────

    async def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    async def get_orders_by_user(self, user_id: str) -> list[Order]:
        """Return all orders for a user, newest first."""
        orders = [o for o in self._orders.values() if o.user_id == user_id]
        return sorted(orders, key=lambda o: o.placed_at, reverse=True)

    async def get_account(self, user_id: str) -> Account | None:
        return self._accounts.get(user_id)

    async def get_transactions(
        self, user_id: str, limit: int = 5
    ) -> list[Transaction]:
        txns = self._transactions.get(user_id, [])
        return txns[:limit]

    # ── Write operations ─────────────────────────────────────────────────────

    async def create_refund(
        self,
        order_id: str,
        reason: str,
        amount_pkr: float,
    ) -> RefundRequest:
        order = self._orders.get(order_id)
        user_id = order.user_id if order else "unknown"
        req = RefundRequest(
            request_id=f"REF-{uuid.uuid4().hex[:8].upper()}",
            order_id=order_id,
            user_id=user_id,
            reason=reason,
            amount_pkr=amount_pkr,
            created_at=datetime.now(timezone.utc),
        )
        self._refunds[req.request_id] = req
        log.info("crm_refund_created", request_id=req.request_id, order_id=order_id)
        return req

    async def create_ticket(
        self,
        user_id: str,
        summary: str,
        priority: str,
    ) -> SupportTicket:
        ticket = SupportTicket(
            ticket_id=f"TKT-{uuid.uuid4().hex[:8].upper()}",
            user_id=user_id,
            summary=summary,
            priority=priority,
            created_at=datetime.now(timezone.utc),
        )
        self._tickets[ticket.ticket_id] = ticket
        log.info("crm_ticket_created", ticket_id=ticket.ticket_id, user_id=user_id)
        return ticket

    async def escalate(
        self,
        conversation_id: str,
        reason: str,
    ) -> EscalationEntry:
        position = len(self._escalations) + 1
        entry = EscalationEntry(
            escalation_id=f"ESC-{uuid.uuid4().hex[:8].upper()}",
            conversation_id=conversation_id,
            reason=reason,
            position=position,
            created_at=datetime.now(timezone.utc),
        )
        self._escalations.append(entry)
        log.info(
            "crm_escalation_queued",
            escalation_id=entry.escalation_id,
            position=position,
        )
        return entry

    # ── Inspection helpers (tests / admin) ───────────────────────────────────

    def all_refunds(self) -> list[RefundRequest]:
        return list(self._refunds.values())

    def all_tickets(self) -> list[SupportTicket]:
        return list(self._tickets.values())

    def all_escalations(self) -> list[EscalationEntry]:
        return list(self._escalations)


# Module-level singleton.
_crm: MockCRMService | None = None


def get_crm() -> MockCRMService:
    global _crm
    if _crm is None:
        _crm = MockCRMService()
    return _crm
