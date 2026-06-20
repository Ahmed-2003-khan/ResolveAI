"""Langfuse observability client — wraps LangGraph nodes in distributed traces.

Usage in graph.py:
    from app.observability.langfuse_client import wrap_node
    workflow.add_node("classify_intent", wrap_node("classify_intent", classify_intent))

When LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set the wrappers are
transparent no-ops, so observability never breaks the application.
"""

from __future__ import annotations

import functools
import subprocess
from collections.abc import Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_client: Any | None = None
_client_initialized: bool = False
_git_sha: str | None = None


def _get_git_sha() -> str:
    global _git_sha
    if _git_sha is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            _git_sha = result.stdout.strip() or "unknown"
        except Exception:
            _git_sha = "unknown"
    return _git_sha


def get_langfuse() -> Any | None:
    """Return the singleton Langfuse client, or None if not configured."""
    global _client, _client_initialized
    if _client_initialized:
        return _client
    _client_initialized = True
    try:
        from app.config import get_settings

        settings = get_settings()
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            log.info("langfuse_disabled", reason="keys_not_configured")
            return None
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        log.info("langfuse_initialized", host=settings.langfuse_host)
    except Exception as exc:
        log.warning("langfuse_init_failed", error=str(exc))
    return _client


def wrap_node(node_name: str, fn: Callable) -> Callable:
    """Wrap a LangGraph node with a Langfuse span.

    The wrapper is transparent when Langfuse is not configured so nodes never
    fail because of observability issues.  Each call creates (or continues) a
    trace keyed by ``conversation_id`` and appends a child span for the node.
    """

    @functools.wraps(fn)
    async def wrapper(state: dict) -> dict:
        lf = get_langfuse()
        span = None
        trace = None

        if lf is not None:
            try:
                trace_id = state.get("conversation_id") or None
                user_message = (state.get("user_message") or "")[:500]
                trace = lf.trace(
                    id=trace_id,
                    name="agent_run",
                    # Set trace-level input once (first node sets it, later nodes just update)
                    input={"user_message": user_message},
                    metadata={
                        "user_id": state.get("user_id"),
                        "channel": (state.get("user_profile") or {}).get("channel", "web"),
                    },
                )
                span = trace.span(
                    name=node_name,
                    input={"user_message": user_message},
                )
            except Exception as exc:
                log.debug("langfuse_span_start_failed", node=node_name, error=str(exc))
                span = None
                trace = None

        result: dict = await fn(state)

        if span is not None:
            try:
                audit = result.get("audit_trail") or [{}]
                output_summary = str(audit[0].get("output", ""))[:1000] if audit else ""
                span.end(output=output_summary)

                # Update trace: tags + output (final_response if this is the last node)
                tags = [f"git_sha:{_get_git_sha()}"]
                intent = result.get("intent") or state.get("intent")
                if intent:
                    tags.append(f"intent:{intent}")
                if result.get("should_escalate"):
                    tags.append("escalated:true")

                trace_update: dict = {"tags": tags}
                # send_reply and escalate are terminal nodes — set the trace output here
                if node_name in ("send_reply", "escalate"):
                    final = result.get("final_response") or output_summary
                    trace_update["output"] = final[:1000] if final else None

                if trace is not None:
                    trace.update(**trace_update)
            except Exception as exc:
                log.debug("langfuse_span_end_failed", node=node_name, error=str(exc))

        return result

    return wrapper
