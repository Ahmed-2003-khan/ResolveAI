# ResolveAI — Complete Build Roadmap for Claude Code

> **How to use this file with Claude Code:**
> 1. Save this as `PROJECT.md` in an empty directory.
> 2. Open Claude Code in that directory.
> 3. Tell Claude Code: *"Read PROJECT.md. We are building this project. Start with Phase 0 and ask me for confirmation before moving to the next phase. Do not skip phases. Follow the file/folder structure exactly."*
> 4. After each phase completes, run the verification commands and only then continue.

---

## 0. Project Identity

- **Name:** ResolveAI
- **One-line:** Multi-channel AI customer-operations platform with RAG + LangGraph agents, built for Pakistani fintech / e-commerce / SaaS use cases.
- **Primary language:** Python 3.11
- **Primary deliverables:** A working FastAPI service + LangGraph agent + admin UI + eval harness + Docker deployment.
- **Total realistic build time (solo, 3–4 hrs/day):** 4 weeks.
- **Target portfolio outcome:** A repo that 90% of Karachi AI Engineer JDs in 2025–2026 will check off.

---

## 1. Hard Rules (Claude Code must follow these throughout)

1. **Python 3.11**, type hints everywhere, `ruff` + `black` formatted.
2. **Async-first.** All I/O via `async def` + `httpx.AsyncClient`. No blocking `requests` library.
3. **Pydantic v2** for all schemas. No raw dicts crossing module boundaries.
4. **Settings via `pydantic-settings`**, loaded from `.env`. Never hardcode keys.
5. **Every external call** (LLM, DB, HTTP) wrapped in retry + timeout via `tenacity`.
6. **Structured logging** via `structlog`. No `print()`. No bare `logging.info`.
7. **Tests required** for every service module (`pytest` + `pytest-asyncio`).
8. **No global state** except settings + DB pool + Redis pool (initialised in `app/core/`).
9. **Folder structure is sacred.** Do not create files outside the defined layout.
10. **Secrets:** Never commit `.env`. Provide `.env.example` only.
11. **Commits:** Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
12. **No premature optimisation.** Build phase-by-phase. Resist refactoring until the phase ends.

---

## 2. Tech Stack (locked — do not substitute)

| Concern | Choice | Pinned version |
|---|---|---|
| Language | Python | 3.11 |
| API framework | FastAPI | ^0.115 |
| Validation | Pydantic | ^2.9 |
| Async DB driver | asyncpg | ^0.30 |
| ORM | SQLAlchemy 2.0 (async) | ^2.0.36 |
| Migrations | Alembic | ^1.14 |
| Vector + DB | PostgreSQL 16 + pgvector 0.7 | docker image `pgvector/pgvector:pg16` |
| Cache / Queue broker | Redis 7 | docker image `redis:7-alpine` |
| Task queue | arq | ^0.26 |
| LLM SDK | openai | ^1.54 |
| Open-source LLM (local) | Ollama (Llama 3.1 8B) | latest |
| Fallback LLM | groq SDK | ^0.13 |
| Agent framework | langgraph | ^0.2.50 |
| Embedding library | sentence-transformers | ^3.3 |
| Reranker | BAAI/bge-reranker-v2-m3 | via sentence-transformers |
| BM25 | Postgres native `tsvector` | n/a |
| HTTP client | httpx | ^0.27 |
| Retry | tenacity | ^9.0 |
| Logging | structlog | ^24.4 |
| Observability | Langfuse (self-hosted) | latest docker |
| Metrics | Prometheus + Grafana | latest docker |
| Testing | pytest, pytest-asyncio, httpx | latest |
| Lint/format | ruff, black, mypy | latest |
| Container | Docker + docker-compose | n/a |
| CI | GitHub Actions | n/a |
| Deploy | Coolify on Hetzner CCX23 (or DigitalOcean) | n/a |

---

## 3. Final Folder Structure (build to this exactly)

```
resolveai/
├── .env.example
├── .gitignore
├── .dockerignore
├── README.md
├── PROJECT.md                    # this file
├── pyproject.toml
├── docker-compose.yml            # full local stack
├── docker-compose.prod.yml       # production overrides
├── Dockerfile
├── Makefile
│
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
│
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI entrypoint
│   ├── config.py                 # Settings (pydantic-settings)
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── db.py                 # async engine, session
│   │   ├── redis.py              # redis client
│   │   ├── logging.py            # structlog setup
│   │   ├── exceptions.py         # custom exceptions
│   │   └── security.py           # webhook signature verification
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py               # FastAPI dependencies
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py         # main v1 router
│   │   │   ├── inbound.py        # POST /messages/inbound (webhooks)
│   │   │   ├── admin.py          # admin endpoints
│   │   │   ├── kb.py             # knowledge base CRUD
│   │   │   ├── conversations.py  # conversation queries
│   │   │   └── health.py         # /healthz, /readyz
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── message.py            # unified Message schema
│   │   ├── conversation.py
│   │   ├── kb.py
│   │   ├── user.py
│   │   └── agent_state.py        # LangGraph state TypedDict
│   │
│   ├── models/                   # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── kb_chunk.py
│   │   ├── user_profile.py
│   │   ├── audit_log.py
│   │   └── eval_run.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── channels/             # channel adapters
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # ChannelAdapter ABC
│   │   │   ├── whatsapp.py       # WhatsApp Cloud API
│   │   │   ├── email.py
│   │   │   └── web.py
│   │   │
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # LLMProvider ABC
│   │   │   ├── openai_provider.py
│   │   │   ├── groq_provider.py
│   │   │   ├── ollama_provider.py
│   │   │   └── router.py         # multi-provider fallback
│   │   │
│   │   ├── rag/
│   │   │   ├── __init__.py
│   │   │   ├── chunker.py        # semantic chunking
│   │   │   ├── embedder.py
│   │   │   ├── retriever.py      # hybrid retrieval (dense + BM25 + RRF)
│   │   │   ├── reranker.py       # bge-reranker
│   │   │   └── ingest.py         # ingestion pipeline
│   │   │
│   │   ├── pii/
│   │   │   ├── __init__.py
│   │   │   ├── regex_rules.py    # CNIC, mobile, IBAN, card patterns
│   │   │   └── redactor.py
│   │   │
│   │   ├── cache/
│   │   │   ├── __init__.py
│   │   │   └── semantic_cache.py # pgvector-based semantic cache
│   │   │
│   │   ├── tools/                # agent tools (function calling)
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # Tool ABC
│   │   │   ├── registry.py       # tool registry
│   │   │   ├── order.py          # get_order_status, etc.
│   │   │   ├── account.py        # get_account_balance
│   │   │   ├── refund.py         # create_refund_request
│   │   │   ├── ticket.py         # create_support_ticket
│   │   │   └── escalation.py     # escalate_to_human
│   │   │
│   │   └── mock_crm/             # fake CRM backend for portfolio demo
│   │       ├── __init__.py
│   │       └── crm_service.py
│   │
│   ├── agent/                    # LangGraph agent
│   │   ├── __init__.py
│   │   ├── graph.py              # the StateGraph definition
│   │   ├── state.py              # AgentState TypedDict
│   │   ├── checkpointer.py       # Postgres checkpointer
│   │   ├── prompts/              # YAML prompt files
│   │   │   ├── classify_intent.yaml
│   │   │   ├── plan_tools.yaml
│   │   │   ├── compose_response.yaml
│   │   │   └── critique.yaml
│   │   └── nodes/
│   │       ├── __init__.py
│   │       ├── classify_intent.py
│   │       ├── redact_pii.py
│   │       ├── retrieve.py
│   │       ├── plan_tools.py
│   │       ├── execute_tools.py
│   │       ├── compose_response.py
│   │       ├── critique.py
│   │       ├── escalate.py
│   │       └── send_reply.py
│   │
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── arq_settings.py       # arq worker config
│   │   └── tasks.py              # process_inbound_message, etc.
│   │
│   └── observability/
│       ├── __init__.py
│       ├── langfuse_client.py
│       ├── metrics.py            # Prometheus counters/histograms
│       └── tracing.py
│
├── admin_ui/                     # FastAPI + HTMX admin dashboard
│   ├── __init__.py
│   ├── router.py
│   └── templates/
│       ├── base.html
│       ├── conversations.html
│       ├── kb_manager.html
│       └── metrics.html
│
├── data/
│   ├── seed/                     # synthetic seed data
│   │   ├── kb_articles.jsonl
│   │   ├── policy_docs/
│   │   ├── synthetic_tickets.jsonl
│   │   └── user_profiles.jsonl
│   └── eval/
│       └── golden_set.jsonl      # 200-case eval set
│
├── scripts/
│   ├── seed_db.py
│   ├── ingest_kb.py
│   ├── generate_synthetic_data.py
│   └── reset_db.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_pii_redactor.py
│   │   ├── test_chunker.py
│   │   ├── test_retriever.py
│   │   ├── test_reranker.py
│   │   ├── test_tools.py
│   │   └── test_llm_router.py
│   ├── integration/
│   │   ├── test_inbound_webhook.py
│   │   ├── test_agent_graph.py
│   │   └── test_rag_pipeline.py
│   └── eval/
│       ├── run_eval.py           # main eval runner
│       ├── llm_judge.py
│       └── metrics.py
│
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
│       └── dashboards/
│           └── resolveai.json
│
└── .github/
    └── workflows/
        ├── ci.yml                # lint + test + eval
        └── deploy.yml            # build + push + deploy
```

---

## 4. Database Schema (Postgres + pgvector)

Run this thinking through Alembic migrations. Below is the *target shape*; Claude Code should produce migrations that reach it.

### Tables

**`users`** — registered customers in the demo system
```
id              UUID PK
phone           VARCHAR(20) UNIQUE NOT NULL    -- E.164 format
email           VARCHAR(255)
full_name       VARCHAR(255)
plan_tier       VARCHAR(50)                    -- free|standard|premium
account_status  VARCHAR(50)                    -- active|frozen|closed
language_pref   VARCHAR(10)                    -- en|ur|roman_ur
created_at      TIMESTAMPTZ
metadata        JSONB
```

**`conversations`**
```
id              UUID PK
user_id         UUID FK -> users
channel         VARCHAR(20)                    -- whatsapp|email|web
status          VARCHAR(20)                    -- active|resolved|escalated
assigned_human  VARCHAR(100) NULL              -- agent id if escalated
started_at      TIMESTAMPTZ
last_activity   TIMESTAMPTZ
metadata        JSONB
INDEX (user_id), INDEX (status), INDEX (last_activity)
```

**`messages`**
```
id              UUID PK
conversation_id UUID FK -> conversations
direction       VARCHAR(10)                    -- inbound|outbound
sender_type     VARCHAR(20)                    -- user|agent|human_agent|system
content         TEXT
content_redacted TEXT                          -- PII-redacted version
channel_msg_id  VARCHAR(255)                   -- e.g. WhatsApp wamid
created_at      TIMESTAMPTZ
metadata        JSONB                          -- intent, tools_used, cost, latency_ms
INDEX (conversation_id, created_at)
```

**`kb_chunks`** — the vector store
```
id              UUID PK
source_id       VARCHAR(255)                   -- original doc id
source_type     VARCHAR(50)                    -- faq|policy|ticket|article
title           VARCHAR(500)
content         TEXT                           -- the chunk text
content_tsv     TSVECTOR                       -- for BM25
embedding       VECTOR(1536)                   -- OpenAI text-embedding-3-small
language        VARCHAR(10)
product_area    VARCHAR(50)                    -- orders|refunds|account|policy|general
confidentiality VARCHAR(20)                    -- public|internal|restricted
last_updated    TIMESTAMPTZ
metadata        JSONB
INDEX ivfflat (embedding vector_cosine_ops)
INDEX gin (content_tsv)
INDEX (source_type), INDEX (product_area)
```

**`semantic_cache`**
```
id              UUID PK
query_normalized TEXT
query_embedding VECTOR(1536)
response        TEXT
hit_count       INTEGER DEFAULT 0
created_at      TIMESTAMPTZ
expires_at      TIMESTAMPTZ
INDEX ivfflat (query_embedding vector_cosine_ops)
```

**`audit_log`** — every agent decision
```
id              UUID PK
conversation_id UUID FK
message_id      UUID FK
node_name       VARCHAR(50)                    -- which LangGraph node
model_used      VARCHAR(100)
prompt_version  VARCHAR(50)
input_tokens    INTEGER
output_tokens   INTEGER
cost_usd        NUMERIC(10,6)
latency_ms      INTEGER
input_redacted  TEXT
output          TEXT
metadata        JSONB
created_at      TIMESTAMPTZ
INDEX (conversation_id, created_at)
```

**`eval_runs`**
```
id              UUID PK
git_sha         VARCHAR(40)
run_at          TIMESTAMPTZ
total_cases     INTEGER
passed          INTEGER
failed          INTEGER
groundedness    NUMERIC(4,3)
helpfulness     NUMERIC(4,3)
policy_score    NUMERIC(4,3)
metadata        JSONB
```

**`eval_results`** — per-case
```
id              UUID PK
run_id          UUID FK
case_id         VARCHAR(100)
passed          BOOLEAN
actual_response TEXT
expected_response TEXT
judge_scores    JSONB
metadata        JSONB
```

---

## 5. Unified Message Schema (the spine)

```python
# app/schemas/message.py
from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, Field

class InboundMessage(BaseModel):
    channel: Literal["whatsapp", "email", "web"]
    channel_msg_id: str
    user_identifier: str           # phone | email | web session id
    content: str
    received_at: datetime = Field(default_factory=datetime.utcnow)
    raw_payload: dict[str, Any]    # original webhook body

class OutboundMessage(BaseModel):
    channel: Literal["whatsapp", "email", "web"]
    to: str
    content: str
    reply_to: str | None = None
    metadata: dict[str, Any] = {}
```

---

## 6. LangGraph Agent — Full Spec

### State

```python
# app/agent/state.py
from typing import TypedDict, Annotated
from operator import add

class AgentState(TypedDict):
    # Inputs
    conversation_id: str
    user_id: str
    user_message: str
    user_profile: dict
    conversation_history: list[dict]   # last 10 messages

    # Pipeline outputs
    intent: str | None
    cleaned_content: str | None
    pii_map: dict | None                # placeholders -> originals
    retrieved_chunks: list[dict]
    tool_plan: list[dict]
    tool_results: dict
    draft_response: str | None
    critique_score: float | None
    critique_feedback: str | None
    retry_count: int
    should_escalate: bool
    final_response: str | None

    # Telemetry
    total_cost_usd: float
    total_latency_ms: int
    audit_trail: Annotated[list[dict], add]
```

### Graph definition (pseudo, but precise)

```
START → classify_intent
classify_intent → redact_pii
redact_pii → retrieve
retrieve → plan_tools
plan_tools → execute_tools          (if tools needed)
plan_tools → compose_response       (if no tools needed)
execute_tools → compose_response
compose_response → critique
critique → send_reply               (score >= 0.7)
critique → compose_response         (score < 0.7 AND retry_count < 2) — INCREMENT retry_count
critique → escalate                 (score < 0.7 AND retry_count >= 2)
classify_intent → escalate          (intent == "escalate_human" OR abuse detected)
escalate → END
send_reply → END
```

### Node contracts (one-line each)

| Node | Reads | Writes | Model | Max tokens |
|---|---|---|---|---|
| classify_intent | user_message | intent | gpt-4o-mini | 50 |
| redact_pii | user_message | cleaned_content, pii_map | regex + local Llama-3 | n/a |
| retrieve | cleaned_content, user_profile.product_area | retrieved_chunks (top 5) | embedding + reranker | n/a |
| plan_tools | cleaned_content, intent, retrieved_chunks | tool_plan | gpt-4o-mini (function calling) | 500 |
| execute_tools | tool_plan | tool_results | n/a (HTTP) | n/a |
| compose_response | retrieved_chunks, tool_results, history, profile | draft_response | gpt-4o-mini | 600 |
| critique | draft_response, retrieved_chunks | critique_score, critique_feedback | gpt-4o-mini | 200 |
| escalate | conversation_id | final_response (apology) | n/a | n/a |
| send_reply | draft_response | final_response | n/a | n/a |

### Checkpointer

Use LangGraph's `AsyncPostgresSaver`. One row per `(thread_id, checkpoint_id)`. `thread_id = conversation_id`. This gives free conversation memory + crash recovery.

---

## 7. RAG Pipeline — Exact Steps

### Ingestion (`scripts/ingest_kb.py`)
1. Read source files from `data/seed/` (markdown, JSONL, PDFs).
2. **Chunk:**
   - Policy / article docs: 512-token sliding window with 64-token overlap, respect paragraph boundaries.
   - Past tickets: one chunk per ticket — `Q: ... \n A: ...`.
   - FAQ: one chunk per Q/A.
3. **Embed:** batch of 100 chunks → `text-embedding-3-small` → 1536-dim vectors.
4. **Compute `tsvector`:** `to_tsvector('english', content)` (and store `simple` variant for Urdu).
5. **Insert** into `kb_chunks` with full metadata.
6. **Build index** (one-time): `CREATE INDEX ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)`.

### Retrieval (`app/services/rag/retriever.py`)
```
async def retrieve(query: str, filters: dict, k: int = 5) -> list[Chunk]:
    1. embed query -> q_vec (1536-dim)
    2. dense_results = SELECT ... ORDER BY embedding <=> q_vec LIMIT 30
       (apply metadata filters in WHERE)
    3. bm25_results  = SELECT ... WHERE content_tsv @@ plainto_tsquery(query) LIMIT 30
    4. merged = reciprocal_rank_fusion(dense_results, bm25_results, k=60)[:20]
    5. reranked = bge_reranker.rerank(query, merged)[:k]
    6. return reranked
```

### Reranker

Load `BAAI/bge-reranker-v2-m3` via sentence-transformers `CrossEncoder`. Wrap in a singleton class with `async` interface (run in threadpool). It's CPU-friendly but takes ~300ms for 20 pairs — acceptable.

### Semantic cache (`app/services/cache/semantic_cache.py`)
1. On agent entry: embed user message, check `semantic_cache` for any row with cosine similarity ≥ 0.97 and not expired.
2. If hit → return cached response, skip agent entirely.
3. After successful resolution → cache `(query_normalised, embedding, response, ttl=24h)`.
4. Target: 30%+ hit rate after seed data warms up.

---

## 8. PII Redaction — Patterns You Must Implement

```python
PATTERNS = {
    "CNIC":   r"\b\d{5}-\d{7}-\d\b|\b\d{13}\b",          # Pakistani CNIC
    "MOBILE": r"\b(?:\+92|0)3\d{2}[-\s]?\d{7}\b",        # PK mobile
    "IBAN":   r"\bPK\d{2}[A-Z]{4}\d{16}\b",              # PK IBAN
    "CARD":   r"\b(?:\d[ -]?){13,19}\b",                 # card PANs
    "EMAIL":  r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
}
```

Pipeline: regex pass first (deterministic, fast), then *optionally* a Llama-3 pass via Ollama to catch context-leaked PII ("my account number is one two three four..." spelled out). Keep a `pii_map` so `escalate` can restore originals for human agents.

---

## 9. Tools (function-calling specs)

Each tool is a class implementing:
```python
class Tool(ABC):
    name: str
    description: str
    parameters_schema: dict           # JSON schema
    requires_confirmation: bool       # write tools = True
    async def execute(self, **kwargs) -> dict: ...
```

Concrete tools to implement:

| Tool | Type | Returns |
|---|---|---|
| `get_order_status(order_id)` | read | `{status, eta, last_update}` |
| `get_account_balance(user_id)` | read | `{balance, currency, last_txn}` |
| `get_recent_transactions(user_id, limit=5)` | read | `[{...}, ...]` |
| `create_refund_request(order_id, reason, amount)` | write | `{request_id, status}` |
| `create_support_ticket(user_id, summary, priority)` | write | `{ticket_id}` |
| `escalate_to_human(conversation_id, reason)` | write | `{queued: true, position}` |

All "write" tools call a **mock CRM service** living at `/api/v1/mock_crm/*` — a small FastAPI sub-router with in-memory SQLite-backed state. This keeps the portfolio runnable by anyone without third-party accounts.

---

## 10. Channel Adapters

Implement `ChannelAdapter` ABC:
```python
class ChannelAdapter(ABC):
    async def parse_inbound(raw: dict) -> InboundMessage: ...
    async def send(msg: OutboundMessage) -> str: ...   # returns provider msg id
    def verify_webhook(headers: dict, body: bytes) -> bool: ...
```

### WhatsApp
- Use Twilio WhatsApp **sandbox** for portfolio (no business verification needed). Document this clearly in README.
- Verify webhook via Twilio signature (`X-Twilio-Signature`).
- Outbound via Twilio REST API.

### Email
- Inbound: AWS SES → SNS → webhook (or local IMAP poller for dev).
- Outbound: SES `send_email`.

### Web widget
- Simple WebSocket endpoint `/ws/chat/{session_id}`.
- Provide a vanilla JS snippet in `admin_ui/static/widget.js`.

---

## 11. LLM Router (multi-provider fallback)

```python
class LLMRouter:
    providers = [openai, groq, ollama]    # in order

    async def chat(messages, model_tier="cheap") -> ChatResult:
        for provider in self.providers:
            try:
                async with timeout(15):
                    result = await provider.chat(messages, model_tier)
                    record_metric(provider.name, "success")
                    return result
            except (RateLimitError, TimeoutError, APIError) as e:
                record_metric(provider.name, "fallback")
                continue
        raise AllProvidersDownError()
```

Tiers:
- `cheap` → gpt-4o-mini, llama-3.1-8b-instant, llama3:8b
- `smart` → gpt-4o, llama-3.1-70b-versatile, (no local fallback — fail closed)

Circuit breaker per provider: if 3 consecutive failures within 60s, mark provider unhealthy for 5 minutes.

---

## 12. Observability

### Langfuse
Self-host via `docker-compose`. Every LangGraph node call wrapped in `@langfuse.observe`. Trace ID == `conversation_id`. Tags: `intent`, `escalated`, `git_sha`.

### Prometheus metrics
```
resolveai_messages_received_total{channel}
resolveai_messages_sent_total{channel}
resolveai_agent_node_duration_seconds{node}  (histogram)
resolveai_llm_cost_usd_total{provider, model}
resolveai_llm_tokens_total{provider, model, direction}
resolveai_escalations_total{reason}
resolveai_cache_hits_total
resolveai_cache_misses_total
resolveai_critique_score (histogram)
resolveai_provider_failures_total{provider}
```

### Grafana
One dashboard `resolveai.json` with: messages/min, p50/p95 latency, cost/day, escalation rate, cache hit rate, top intents.

---

## 13. Eval Harness — The Hire-Winning Feature

### Golden set: `data/eval/golden_set.jsonl`
Aim for **200 cases**. Each case:
```json
{
  "case_id": "ord_001",
  "category": "order_status",
  "user_message": "yaar mera order kahan hai? 3 din ho gaye",
  "user_profile": {"plan_tier": "standard", "language_pref": "roman_ur"},
  "expected_intent": "order_status",
  "expected_tools": ["get_order_status"],
  "must_include": ["dispatch", "ETA"],
  "must_not_include": ["refund", "I don't know"],
  "ground_truth_answer": "Aapka order ORD-... dispatch ho chuka hai..."
}
```

### Runner (`tests/eval/run_eval.py`)
1. For each case: run full agent graph against a test DB seeded with deterministic fixtures.
2. Assertions:
   - intent match
   - required tools were called
   - `must_include` strings present in response
   - `must_not_include` strings absent
3. LLM-as-judge (`tests/eval/llm_judge.py`) on three rubrics: groundedness (0–1), helpfulness (0–1), policy_compliance (0–1).
4. Persist results to `eval_runs` + `eval_results`.
5. **Fail the GitHub Actions job** if pass-rate < 85% or any rubric average < 0.75.

---

## 14. Phased Build Plan (give this to Claude Code one phase at a time)

### Phase 0 — Scaffold (Day 1, ~2h)
- [ ] `pyproject.toml` with all deps pinned
- [ ] `.env.example`, `.gitignore`, `.dockerignore`
- [ ] Folder structure as in §3 (create empty `__init__.py` files)
- [ ] `app/config.py` with full `Settings` class
- [ ] `app/core/logging.py` — structlog JSON renderer
- [ ] `app/main.py` — minimal FastAPI with `/healthz`
- [ ] `Makefile` targets: `up`, `down`, `migrate`, `seed`, `test`, `eval`, `lint`
- [ ] `docker-compose.yml` with postgres+pgvector, redis, langfuse, ollama (commented), api
- [ ] `Dockerfile` (multi-stage, python:3.11-slim, non-root user)
- [ ] First `ruff` + `black` + `mypy` pass

**Verify:** `make up && curl localhost:8000/healthz` returns `{"ok": true}`.

### Phase 1 — Database & Migrations (Day 2, ~3h)
- [ ] `app/core/db.py` async engine + session factory
- [ ] All SQLAlchemy models in `app/models/`
- [ ] Alembic configured for async
- [ ] Initial migration creating all tables + pgvector extension + indexes
- [ ] `scripts/reset_db.py`

**Verify:** `make migrate` runs clean; `\dt` in psql shows all tables; `\d kb_chunks` shows ivfflat index.

### Phase 2 — Synthetic Data & Ingestion (Day 3, ~4h)
- [ ] `scripts/generate_synthetic_data.py` — uses LLM to generate 100 KB articles, 500 fake tickets, 50 policy snippets, 30 user profiles. Output to `data/seed/`.
- [ ] `app/services/rag/chunker.py`
- [ ] `app/services/rag/embedder.py` (with batching + retry)
- [ ] `scripts/ingest_kb.py` — reads `data/seed/`, chunks, embeds, inserts
- [ ] `scripts/seed_db.py` — inserts user profiles, mock orders

**Verify:** `make seed && make ingest` populates `kb_chunks` with ≥ 800 rows.

### Phase 3 — RAG Retrieval (Day 4, ~3h)
- [ ] `app/services/rag/retriever.py` with hybrid + RRF
- [ ] `app/services/rag/reranker.py` (singleton CrossEncoder)
- [ ] `tests/unit/test_retriever.py` — at least 10 query/expected-chunk-id assertions
- [ ] Standalone CLI: `python -m app.services.rag.retriever "kya refund mil sakta hai"` prints top 5

**Verify:** Tests pass; CLI returns sensible chunks for 5 sample queries.

### Phase 4 — PII Redaction (Day 5, ~2h)
- [ ] `app/services/pii/regex_rules.py`
- [ ] `app/services/pii/redactor.py` with reversible `pii_map`
- [ ] `tests/unit/test_pii_redactor.py` — 20+ cases (CNIC, mobile, IBAN, card, spelled-out)

**Verify:** Coverage ≥ 95% on `pii/`.

### Phase 5 — LLM Router & Providers (Day 6, ~3h)
- [ ] `app/services/llm/base.py` ABC + `ChatMessage`, `ChatResult` schemas
- [ ] `openai_provider.py`, `groq_provider.py`, `ollama_provider.py`
- [ ] `router.py` with tiers, fallback, circuit breaker
- [ ] `tests/unit/test_llm_router.py` — mock providers, assert fallback order

**Verify:** Forcing OpenAI to fail → Groq receives the call → metric increments.

### Phase 6 — Tools & Mock CRM (Day 7, ~3h)
- [ ] `app/services/mock_crm/crm_service.py` — in-memory CRM
- [ ] All 6 tools in `app/services/tools/`
- [ ] `tools/registry.py` + OpenAI function-calling schema generator
- [ ] `tests/unit/test_tools.py`

**Verify:** Each tool callable directly and returns valid Pydantic models.

### Phase 7 — LangGraph Agent (Days 8–9, ~6h)
- [ ] `app/agent/state.py`
- [ ] All nodes in `app/agent/nodes/` (start with stubs, fill in)
- [ ] `app/agent/graph.py` wiring nodes + edges + checkpointer
- [ ] `app/agent/prompts/*.yaml` (versioned)
- [ ] `tests/integration/test_agent_graph.py` — 5 end-to-end scenarios

**Verify:** Running graph on a sample message produces a response < 5s with audit trail populated.

### Phase 8 — Semantic Cache (Day 10, ~2h)
- [ ] `app/services/cache/semantic_cache.py`
- [ ] Integrate into agent entry point
- [ ] Metric counters

**Verify:** Sending same query twice → second call has `cache_hit=true` in trace.

### Phase 9 — Channels & Webhooks (Days 11–12, ~5h)
- [ ] `app/services/channels/base.py` + WhatsApp (Twilio), Email, Web
- [ ] `app/api/v1/inbound.py` webhook endpoint (verify signatures, normalise, enqueue)
- [ ] `app/workers/tasks.py` arq worker → agent graph → send reply
- [ ] `app/workers/arq_settings.py` + Makefile target `worker`

**Verify:** Twilio sandbox WhatsApp → send "hello" → receive AI reply within 6s.

### Phase 10 — Admin UI (Day 13, ~3h)
- [ ] FastAPI + Jinja2 + HTMX
- [ ] Pages: conversations list, conversation detail (with full audit trail), KB manager (CRUD), metrics summary
- [ ] Basic HTTP Basic Auth via env var

**Verify:** `/admin` loads; can view a real conversation's node-by-node trace.

### Phase 11 — Observability (Day 14, ~3h)
- [ ] Langfuse self-hosted in docker-compose
- [ ] `@observe` decorators on all nodes
- [ ] Prometheus metrics emitted
- [ ] Grafana dashboard JSON

**Verify:** Send 20 test messages → Grafana shows them all with correct latency/cost.

### Phase 12 — Eval Harness (Days 15–16, ~5h)
- [ ] Generate `data/eval/golden_set.jsonl` (use LLM + manual curation; minimum 100, target 200)
- [ ] `tests/eval/run_eval.py`
- [ ] `tests/eval/llm_judge.py`
- [ ] Makefile target `eval` → produces HTML report

**Verify:** `make eval` runs end-to-end and reports a pass rate. Iterate prompts until ≥ 85%.

### Phase 13 — CI/CD (Day 17, ~2h)
- [ ] `.github/workflows/ci.yml`: lint, unit tests, integration tests with services in containers
- [ ] `.github/workflows/deploy.yml`: build → GHCR → SSH deploy script

**Verify:** PR triggers all workflows green.

### Phase 14 — Production Deploy (Day 18, ~3h)
- [ ] `docker-compose.prod.yml` with Caddy reverse proxy + TLS
- [ ] Provision Hetzner / DO droplet
- [ ] Install Coolify or Dokploy
- [ ] Deploy and verify end-to-end on a live URL

**Verify:** Live URL responds; webhook from Twilio sandbox works in production.

### Phase 15 — README & Demo (Day 19, ~3h)
- [ ] README with: problem statement (Karachi context), architecture diagram, screenshots, results table (resolution rate, cost/ticket, p95 latency, cache hit rate), local setup, deploy instructions.
- [ ] Loom video (5–7 min) walking through the agent on a real query.
- [ ] LinkedIn post draft.

**Verify:** A non-technical friend can read the README and understand what the project does in 60 seconds.

---

## 15. Acceptance Criteria for "Done"

The project is **portfolio-ready** when ALL of these are true:

1. `git clone && make up && make migrate && make seed && make ingest` works on a fresh machine in < 10 minutes.
2. `make eval` produces a passing report at ≥ 85% case-level pass rate and ≥ 0.75 on every rubric.
3. `make test` runs ≥ 60 tests, ≥ 80% line coverage on `app/services/` and `app/agent/`.
4. Live deployment serves a real WhatsApp sandbox conversation end-to-end with p95 latency < 4s.
5. Grafana dashboard shows live cost, latency, and escalation rate.
6. Admin UI can replay any conversation node-by-node.
7. README has measurable numbers and a Loom demo embedded.

---

## 16. Anti-Patterns (do NOT do these even if tempted)

- Do not put business logic inside FastAPI route handlers. Routes are thin; logic lives in `services/` and `agent/`.
- Do not couple the agent to a specific LLM provider — always go through `LLMRouter`.
- Do not store prompts as Python f-strings. They live in YAML in `app/agent/prompts/`.
- Do not skip the eval harness "for now". It is the single most interview-impressive artifact.
- Do not deploy to Kubernetes. A single Hetzner node with Coolify is correct for this scale.
- Do not use Pinecone, Weaviate, or any extra vector DB. pgvector covers it.
- Do not commit synthetic data with real-looking PII. Use clearly fake CNICs like `00000-0000000-0`.
- Do not implement features outside this roadmap before finishing it.

---

## 17. First Message to Claude Code

Paste this exactly into Claude Code after putting `PROJECT.md` in an empty directory:

> Read `PROJECT.md` in this directory completely before doing anything. This document defines the entire project. We will build it phase by phase, starting from Phase 0 in §14. After you finish each phase: (1) summarise what you built, (2) run the phase's verification step, (3) commit with a conventional-commit message, (4) wait for me to say "next" before starting the next phase. Do not skip ahead. Do not deviate from the folder structure in §3 or the tech stack in §2. Begin Phase 0 now.

---

*End of roadmap.*
