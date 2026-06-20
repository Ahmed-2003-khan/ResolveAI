"""Node: execute_tools — runs each planned tool call and collects results."""

from __future__ import annotations

import time

import structlog

from app.agent.state import AgentState
from app.observability.metrics import NODE_DURATION
from app.services.tools.registry import get_tool_registry

log = structlog.get_logger(__name__)


async def execute_tools(state: AgentState) -> dict:
    t0 = time.monotonic()
    tool_plan = state.get("tool_plan") or []
    registry = get_tool_registry()

    tool_results: dict = {}
    for call in tool_plan:
        name = call.get("name", "")
        arguments = call.get("arguments", {})
        try:
            result = await registry.execute(name, **arguments)
            tool_results[name] = result
            log.info("tool_executed", name=name, success=True)
        except Exception as exc:
            log.warning("tool_execution_failed", name=name, error=str(exc))
            tool_results[name] = {"error": str(exc)}

    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="execute_tools").observe(latency / 1000.0)
    log.info(
        "node_execute_tools",
        tools_executed=len(tool_results),
        latency_ms=latency,
    )

    return {
        "tool_results": tool_results,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "execute_tools",
                "tools_executed": list(tool_results.keys()),
                "latency_ms": latency,
                "output": {
                    k: "ok" if "error" not in v else "error" for k, v in tool_results.items()
                },
            }
        ],
    }
