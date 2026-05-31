.PHONY: up down restart logs migrate seed ingest test eval eval-smoke eval-no-judge lint fmt typecheck worker shell psql redis-cli help

# ── Docker ───────────────────────────────────────────────────────────────────
up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose restart api

logs:
	docker compose logs -f api

# ── Database ─────────────────────────────────────────────────────────────────
migrate:
	docker compose exec api alembic upgrade head

migrate-down:
	docker compose exec api alembic downgrade -1

migrate-history:
	docker compose exec api alembic history --verbose

seed:
	docker compose exec api python scripts/seed_db.py

ingest:
	docker compose exec api python scripts/ingest_kb.py

reset-db:
	docker compose exec api python scripts/reset_db.py

# ── Workers ──────────────────────────────────────────────────────────────────
worker:
	docker compose exec api python -m arq app.workers.arq_settings.WorkerSettings

# ── Testing ──────────────────────────────────────────────────────────────────
test:
	docker compose exec api pytest tests/unit tests/integration -v --cov=app --cov-report=term-missing

test-unit:
	docker compose exec api pytest tests/unit -v

test-integration:
	docker compose exec api pytest tests/integration -v

eval:
	docker compose exec api python tests/eval/run_eval.py --html reports/eval_report.html
	@echo "Report saved to reports/eval_report.html"

eval-smoke:
	docker compose exec api python tests/eval/run_eval.py --limit 10 --html reports/eval_smoke.html
	@echo "Smoke report saved to reports/eval_smoke.html"

eval-no-judge:
	docker compose exec api python tests/eval/run_eval.py --no-judge --html reports/eval_report.html

# ── Lint / format / type-check ───────────────────────────────────────────────
lint:
	ruff check app tests scripts
	black --check app tests scripts

fmt:
	ruff check --fix app tests scripts
	black app tests scripts

typecheck:
	mypy app --ignore-missing-imports

# ── Convenience shells ───────────────────────────────────────────────────────
shell:
	docker compose exec api bash

psql:
	docker compose exec db psql -U resolveai -d resolveai

redis-cli:
	docker compose exec redis redis-cli

help:
	@echo "Available targets:"
	@echo "  up            - Start all services"
	@echo "  down          - Stop all services"
	@echo "  migrate       - Run Alembic migrations"
	@echo "  seed          - Seed user/order data"
	@echo "  ingest        - Ingest KB articles into pgvector"
	@echo "  test          - Run unit + integration tests with coverage"
	@echo "  eval          - Run the full eval harness (writes reports/eval_report.html)"
	@echo "  eval-smoke    - Run first 10 cases only (fast smoke test)"
	@echo "  eval-no-judge - Run without LLM judge (no rubric scores, faster)"
	@echo "  lint          - Run ruff + black checks"
	@echo "  fmt           - Auto-fix lint + format"
	@echo "  typecheck     - Run mypy"
	@echo "  worker        - Start arq worker"
	@echo "  shell         - Bash shell inside api container"
	@echo "  psql          - psql shell"
	@echo "  redis-cli     - redis-cli shell"
