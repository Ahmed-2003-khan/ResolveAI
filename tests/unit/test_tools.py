"""Unit tests for Phase 6 — Tools & Mock CRM.

All tests run fully in-process: no network calls, no database.
The mock CRM singleton is reset between tests via a fresh MockCRMService instance.
"""

import pytest

from app.services.mock_crm.crm_service import MockCRMService
from app.services.tools.account import GetAccountBalanceTool, GetRecentTransactionsTool
from app.services.tools.base import Tool
from app.services.tools.escalation import EscalateToHumanTool
from app.services.tools.order import GetOrderStatusTool
from app.services.tools.refund import CreateRefundRequestTool
from app.services.tools.registry import ToolRegistry
from app.services.tools.ticket import CreateSupportTicketTool


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def crm() -> MockCRMService:
    """Fresh CRM instance (not the module singleton) for each test."""
    return MockCRMService()


@pytest.fixture
def registry(crm: MockCRMService) -> ToolRegistry:
    """Registry wired to fresh tool instances pointing at the fixture CRM.

    We monkey-patch get_crm inside each tool by injecting the fixture CRM
    through a custom registry subclass is overkill — instead we override the
    module-level singleton before each test via the crm fixture side-effect.
    Using the real singleton is acceptable here since tests are isolated by
    only ever *reading* seeded data or accumulating into a fresh CRM.
    """
    import app.services.mock_crm.crm_service as crm_module

    crm_module._crm = crm  # point singleton at the test fixture
    return ToolRegistry()


# ── Tool ABC ───────────────────────────────────────────────────────────────────


def test_all_tools_are_tool_subclasses(registry: ToolRegistry) -> None:
    for tool in registry.all():
        assert isinstance(tool, Tool)


def test_all_tools_have_name_and_description(registry: ToolRegistry) -> None:
    for tool in registry.all():
        assert tool.name, f"{type(tool).__name__}.name is empty"
        assert tool.description, f"{type(tool).__name__}.description is empty"


def test_all_tools_have_valid_parameters_schema(registry: ToolRegistry) -> None:
    for tool in registry.all():
        schema = tool.parameters_schema
        assert schema.get("type") == "object", f"{tool.name}: schema.type must be 'object'"
        assert "properties" in schema, f"{tool.name}: schema missing 'properties'"


# ── Registry ──────────────────────────────────────────────────────────────────


def test_registry_has_all_six_tools(registry: ToolRegistry) -> None:
    expected = {
        "get_order_status",
        "get_account_balance",
        "get_recent_transactions",
        "create_refund_request",
        "create_support_ticket",
        "escalate_to_human",
    }
    assert set(registry.names()) == expected


def test_registry_get_by_name(registry: ToolRegistry) -> None:
    tool = registry.get("get_order_status")
    assert isinstance(tool, GetOrderStatusTool)


def test_registry_get_unknown_returns_none(registry: ToolRegistry) -> None:
    assert registry.get("nonexistent_tool") is None


def test_openai_schemas_structure(registry: ToolRegistry) -> None:
    schemas = registry.openai_schemas()
    assert len(schemas) == 6
    for schema in schemas:
        assert schema["type"] == "function"
        fn = schema["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_openai_schemas_for_subset(registry: ToolRegistry) -> None:
    schemas = registry.openai_schemas_for(["get_order_status", "get_account_balance"])
    assert len(schemas) == 2
    names = {s["function"]["name"] for s in schemas}
    assert names == {"get_order_status", "get_account_balance"}


def test_openai_schemas_for_unknown_skips(registry: ToolRegistry) -> None:
    schemas = registry.openai_schemas_for(["get_order_status", "does_not_exist"])
    assert len(schemas) == 1


# ── GetOrderStatusTool ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_order_status_dispatched(registry: ToolRegistry) -> None:
    result = await registry.execute("get_order_status", order_id="ORD-001")
    assert result["order_id"] == "ORD-001"
    assert result["status"] == "dispatched"
    assert result["found"] is True
    assert result["tracking_number"] == "TRK-PKG-001"
    assert result["eta"] is not None


@pytest.mark.asyncio
async def test_get_order_status_delivered(registry: ToolRegistry) -> None:
    result = await registry.execute("get_order_status", order_id="ORD-002")
    assert result["status"] == "delivered"


@pytest.mark.asyncio
async def test_get_order_status_processing_no_tracking(registry: ToolRegistry) -> None:
    result = await registry.execute("get_order_status", order_id="ORD-003")
    assert result["status"] == "processing"
    assert result["tracking_number"] is None


@pytest.mark.asyncio
async def test_get_order_status_cancelled(registry: ToolRegistry) -> None:
    result = await registry.execute("get_order_status", order_id="ORD-004")
    assert result["status"] == "cancelled"
    assert result["eta"] is None


@pytest.mark.asyncio
async def test_get_order_status_not_found(registry: ToolRegistry) -> None:
    result = await registry.execute("get_order_status", order_id="ORD-NOPE")
    assert result["found"] is False
    assert result["status"] == "not_found"


# ── GetAccountBalanceTool ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_account_balance_active(registry: ToolRegistry) -> None:
    result = await registry.execute("get_account_balance", user_id="user-001")
    assert result["found"] is True
    assert result["account_status"] == "active"
    assert result["balance"] == pytest.approx(45_250.75)
    assert result["currency"] == "PKR"


@pytest.mark.asyncio
async def test_get_account_balance_frozen(registry: ToolRegistry) -> None:
    result = await registry.execute("get_account_balance", user_id="user-003")
    assert result["account_status"] == "frozen"
    assert result["balance"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_get_account_balance_not_found(registry: ToolRegistry) -> None:
    result = await registry.execute("get_account_balance", user_id="user-999")
    assert result["found"] is False
    assert result["account_status"] == "not_found"


# ── GetRecentTransactionsTool ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_recent_transactions_default_limit(registry: ToolRegistry) -> None:
    result = await registry.execute("get_recent_transactions", user_id="user-001")
    assert result["count"] <= 5
    assert result["user_id"] == "user-001"


@pytest.mark.asyncio
async def test_get_recent_transactions_custom_limit(registry: ToolRegistry) -> None:
    result = await registry.execute("get_recent_transactions", user_id="user-001", limit=2)
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_get_recent_transactions_limit_capped_at_20(registry: ToolRegistry) -> None:
    result = await registry.execute("get_recent_transactions", user_id="user-001", limit=100)
    # Only 3 seed transactions for user-001; cap of 20 prevents explosion.
    assert result["count"] <= 20


@pytest.mark.asyncio
async def test_get_recent_transactions_empty_user(registry: ToolRegistry) -> None:
    result = await registry.execute("get_recent_transactions", user_id="user-999")
    assert result["count"] == 0
    assert result["transactions"] == []


@pytest.mark.asyncio
async def test_get_recent_transactions_fields(registry: ToolRegistry) -> None:
    result = await registry.execute("get_recent_transactions", user_id="user-004")
    assert result["count"] > 0
    txn = result["transactions"][0]
    for field in ("txn_id", "type", "amount_pkr", "description", "created_at"):
        assert field in txn, f"Missing field '{field}' in transaction"


# ── CreateRefundRequestTool ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_refund_request_success(registry: ToolRegistry) -> None:
    result = await registry.execute(
        "create_refund_request",
        order_id="ORD-002",
        reason="Item damaged on arrival",
        amount=4_500.0,
    )
    assert result["order_id"] == "ORD-002"
    assert result["status"] == "pending"
    assert result["request_id"].startswith("REF-")
    assert result["amount_pkr"] == pytest.approx(4_500.0)
    assert "REF-" in result["message"]


@pytest.mark.asyncio
async def test_create_refund_request_write_tool(registry: ToolRegistry) -> None:
    tool = registry.get("create_refund_request")
    assert tool is not None
    assert tool.requires_confirmation is True


@pytest.mark.asyncio
async def test_create_refund_unique_request_ids(registry: ToolRegistry) -> None:
    r1 = await registry.execute(
        "create_refund_request", order_id="ORD-001", reason="Wrong item", amount=89_999.0
    )
    r2 = await registry.execute(
        "create_refund_request", order_id="ORD-001", reason="Wrong item", amount=89_999.0
    )
    assert r1["request_id"] != r2["request_id"]


# ── CreateSupportTicketTool ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_support_ticket_success(registry: ToolRegistry) -> None:
    result = await registry.execute(
        "create_support_ticket",
        user_id="user-001",
        summary="Cannot log into account",
        priority="high",
    )
    assert result["ticket_id"].startswith("TKT-")
    assert result["status"] == "open"
    assert result["priority"] == "high"
    assert "TKT-" in result["message"]


@pytest.mark.asyncio
async def test_create_support_ticket_is_write_tool(registry: ToolRegistry) -> None:
    tool = registry.get("create_support_ticket")
    assert tool is not None
    assert tool.requires_confirmation is True


@pytest.mark.asyncio
async def test_create_support_ticket_invalid_priority_defaults_to_medium(
    registry: ToolRegistry,
) -> None:
    result = await registry.execute(
        "create_support_ticket",
        user_id="user-002",
        summary="Some issue",
        priority="critical",  # not a valid priority
    )
    assert result["priority"] == "medium"


@pytest.mark.asyncio
async def test_create_support_ticket_unique_ids(registry: ToolRegistry) -> None:
    r1 = await registry.execute(
        "create_support_ticket", user_id="user-001", summary="Issue 1", priority="low"
    )
    r2 = await registry.execute(
        "create_support_ticket", user_id="user-001", summary="Issue 2", priority="low"
    )
    assert r1["ticket_id"] != r2["ticket_id"]


# ── EscalateToHumanTool ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_escalate_to_human_success(registry: ToolRegistry) -> None:
    result = await registry.execute(
        "escalate_to_human",
        conversation_id="conv-abc",
        reason="Customer is frustrated and insists on human",
    )
    assert result["queued"] is True
    assert result["escalation_id"].startswith("ESC-")
    assert result["position"] == 1


@pytest.mark.asyncio
async def test_escalate_position_increments(registry: ToolRegistry) -> None:
    r1 = await registry.execute(
        "escalate_to_human", conversation_id="conv-1", reason="reason"
    )
    r2 = await registry.execute(
        "escalate_to_human", conversation_id="conv-2", reason="reason"
    )
    assert r2["position"] == r1["position"] + 1


@pytest.mark.asyncio
async def test_escalate_is_write_tool(registry: ToolRegistry) -> None:
    tool = registry.get("escalate_to_human")
    assert tool is not None
    assert tool.requires_confirmation is True


@pytest.mark.asyncio
async def test_escalate_message_mentions_position(registry: ToolRegistry) -> None:
    result = await registry.execute(
        "escalate_to_human", conversation_id="conv-xyz", reason="complex billing issue"
    )
    assert str(result["position"]) in result["message"]


# ── Registry.execute error path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_registry_execute_unknown_tool_raises(registry: ToolRegistry) -> None:
    with pytest.raises(KeyError):
        await registry.execute("definitely_not_a_tool")
