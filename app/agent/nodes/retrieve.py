"""Node: retrieve — hybrid dense + BM25 retrieval with RRF fusion and BGE reranking."""

from __future__ import annotations

import time

import structlog

from app.agent.state import AgentState
from app.observability.metrics import NODE_DURATION
from app.services.rag.retriever import get_retriever

log = structlog.get_logger(__name__)


async def retrieve(state: AgentState) -> dict:
    t0 = time.monotonic()

    query = state.get("cleaned_content") or state["user_message"]
    profile = state.get("user_profile") or {}
    filters: dict = {}
    if product_area := profile.get("product_area"):
        filters["product_area"] = product_area

    retriever = get_retriever()
    chunks = await retriever.retrieve(query, filters=filters, k=5)

    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="retrieve").observe(latency / 1000.0)
    log.info("node_retrieve", chunks_returned=len(chunks), latency_ms=latency)

    return {
        "retrieved_chunks": chunks,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "retrieve",
                "chunks_returned": len(chunks),
                "latency_ms": latency,
                "output": [c.get("source_id") for c in chunks],
            }
        ],
    }
