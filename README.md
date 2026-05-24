# ResolveAI

Multi-channel AI customer-operations platform with RAG + LangGraph agents, built for Pakistani fintech / e-commerce / SaaS use cases.

## Quick Start

```bash
cp .env.example .env   # fill in your API keys
make up                # start all Docker services
make migrate           # run DB migrations
make seed              # seed demo data
make ingest            # ingest KB articles into pgvector
curl localhost:8000/healthz
```

## Tech Stack

- **FastAPI** + **LangGraph** agent (classify → redact → retrieve → plan → execute → compose → critique → reply)
- **PostgreSQL 16 + pgvector** — vector store + BM25 hybrid retrieval
- **Redis 7** — arq task queue + cache
- **Multi-provider LLM** — OpenAI → Groq → Ollama with circuit breaker fallback
- **Langfuse** — self-hosted observability

See [PROJECT.md](PROJECT.md) for the full build roadmap.
