"""Node: critique — LLM-as-judge that scores the draft response 0–1."""

from __future__ import annotations

import json
import time
from pathlib import Path

import structlog
import yaml

from app.agent.state import AgentState
from app.observability.metrics import CRITIQUE_SCORE, NODE_DURATION
from app.services.llm.base import ChatMessage
from app.services.llm.router import get_llm_router

log = structlog.get_logger(__name__)
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _kb_context_text(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant knowledge base articles found."
    return "\n\n".join(
        f"[{i}] {c.get('title') or c.get('source_id', '')}\n{c.get('content', '')}"
        for i, c in enumerate(chunks, 1)
    )


async def critique(state: AgentState) -> dict:
    t0 = time.monotonic()
    with open(_PROMPTS_DIR / "critique.yaml") as fh:
        prompt = yaml.safe_load(fh)

    kb_context = _kb_context_text(state.get("retrieved_chunks") or [])
    tool_results_text = json.dumps(state.get("tool_results") or {})

    messages = [
        ChatMessage(role="system", content=prompt["system"].strip()),
        ChatMessage(
            role="user",
            content=prompt["user"]
            .format(
                user_message=state.get("cleaned_content") or state["user_message"],
                kb_context=kb_context,
                tool_results=tool_results_text,
                draft_response=state.get("draft_response") or "",
            )
            .strip(),
        ),
    ]

    router = get_llm_router()
    result = await router.chat(messages, model_tier="cheap", max_tokens=200)

    score = 0.0
    feedback = "Unable to parse critique."
    try:
        raw = result.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        score = float(parsed.get("score", 0.0))
        feedback = str(parsed.get("feedback", ""))
    except Exception as exc:
        log.warning("critique_parse_failed", error=str(exc), raw=result.content[:200])

    latency = int((time.monotonic() - t0) * 1000)
    NODE_DURATION.labels(node="critique").observe(latency / 1000.0)
    CRITIQUE_SCORE.observe(score)
    log.info("node_critique", score=score, latency_ms=latency)

    return {
        "critique_score": score,
        "critique_feedback": feedback,
        "total_cost_usd": state.get("total_cost_usd", 0.0) + result.cost_usd,
        "total_latency_ms": state.get("total_latency_ms", 0) + latency,
        "audit_trail": [
            {
                "node": "critique",
                "model": result.model,
                "provider": result.provider,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "cost_usd": result.cost_usd,
                "latency_ms": latency,
                "score": score,
                "feedback": feedback,
            }
        ],
    }
