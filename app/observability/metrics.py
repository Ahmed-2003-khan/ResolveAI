"""Prometheus metrics for ResolveAI.

Import the counter/histogram you need and call .inc() / .observe() at the
relevant call-site.  All metrics are module-level singletons — safe to import
from anywhere without double-registration.
"""

from prometheus_client import Counter, Histogram

# ── Semantic cache ────────────────────────────────────────────────────────────

CACHE_HITS = Counter(
    "resolveai_cache_hits_total",
    "Number of semantic cache hits that bypassed the agent graph",
)
CACHE_MISSES = Counter(
    "resolveai_cache_misses_total",
    "Number of cache misses that required a full agent graph run",
)

# ── Messaging ─────────────────────────────────────────────────────────────────

MESSAGES_RECEIVED = Counter(
    "resolveai_messages_received_total",
    "Inbound messages received by channel",
    ["channel"],
)
MESSAGES_SENT = Counter(
    "resolveai_messages_sent_total",
    "Outbound messages sent by channel",
    ["channel"],
)

# ── Agent nodes ───────────────────────────────────────────────────────────────

NODE_DURATION = Histogram(
    "resolveai_agent_node_duration_seconds",
    "LangGraph node execution duration in seconds",
    ["node"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── LLM cost / token tracking ─────────────────────────────────────────────────

LLM_COST = Counter(
    "resolveai_llm_cost_usd_total",
    "Cumulative LLM spend in USD",
    ["provider", "model"],
)
LLM_TOKENS = Counter(
    "resolveai_llm_tokens_total",
    "LLM tokens consumed",
    ["provider", "model", "direction"],  # direction: input | output
)

# ── Escalations ───────────────────────────────────────────────────────────────

ESCALATIONS = Counter(
    "resolveai_escalations_total",
    "Number of conversations escalated to a human agent",
    ["reason"],
)

# ── Critique quality ──────────────────────────────────────────────────────────

CRITIQUE_SCORE = Histogram(
    "resolveai_critique_score",
    "Distribution of critique node quality scores (0–1)",
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

# ── Provider health ───────────────────────────────────────────────────────────

PROVIDER_FAILURES = Counter(
    "resolveai_provider_failures_total",
    "LLM provider failures (rate-limit, timeout, API error)",
    ["provider"],
)
