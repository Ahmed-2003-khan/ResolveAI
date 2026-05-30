"""Tool registry — central lookup for all agent tools.

Also generates OpenAI function-calling schemas so the agent's plan_tools node
can pass them directly to the Chat Completions API.
"""

from typing import Any

import structlog

from app.services.tools.account import GetAccountBalanceTool, GetRecentTransactionsTool
from app.services.tools.base import Tool
from app.services.tools.escalation import EscalateToHumanTool
from app.services.tools.order import GetOrderStatusTool
from app.services.tools.refund import CreateRefundRequestTool
from app.services.tools.ticket import CreateSupportTicketTool
from app.services.tools.user_orders import GetUserOrdersTool

log = structlog.get_logger(__name__)

# Canonical list of all tools (add new tools here).
_ALL_TOOLS: list[Tool] = [
    GetUserOrdersTool(),
    GetOrderStatusTool(),
    GetAccountBalanceTool(),
    GetRecentTransactionsTool(),
    CreateRefundRequestTool(),
    CreateSupportTicketTool(),
    EscalateToHumanTool(),
]


class ToolRegistry:
    """Singleton registry that maps tool names to Tool instances."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or _ALL_TOOLS:
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def openai_schemas(self) -> list[dict[str, Any]]:
        """Return all tools as OpenAI function-calling schema objects."""
        return [_to_openai_schema(t) for t in self._tools.values()]

    def openai_schemas_for(self, names: list[str]) -> list[dict[str, Any]]:
        """Return OpenAI schemas for a subset of tools by name."""
        schemas = []
        for name in names:
            tool = self._tools.get(name)
            if tool is None:
                log.warning("unknown_tool_in_schema_request", name=name)
                continue
            schemas.append(_to_openai_schema(tool))
        return schemas

    async def execute(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Look up a tool by name and execute it."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"No tool registered under name '{name}'")
        log.info("tool_execute", name=name, kwargs=list(kwargs.keys()))
        return await tool.execute(**kwargs)


def _to_openai_schema(tool: Tool) -> dict[str, Any]:
    """Convert a Tool to an OpenAI Chat Completions function-calling dict."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_schema,
        },
    }


# Module-level singleton.
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
