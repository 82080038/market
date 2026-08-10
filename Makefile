.PHONY: help install dev test lint typecheck migrate migrate-pg api frontend scheduler news strategy run-live run-paper run-research

help:
	@echo "Market App — Local Development"
	@echo ""
	@echo "Commands:"
	@echo "  make install     Install Python dependencies"
	@echo "  make dev         Install frontend dependencies"
	@echo "  make test        Run pytest with coverage"
	@echo "  make lint        Run ruff check"
	@echo "  make typecheck   Run mypy"
	@echo "  make migrate     Run Alembic migrations (SQLite)"
	@echo "  make migrate-pg  Run Alembic migrations (PostgreSQL)"
	@echo "  make api         Start FastAPI server (127.0.0.1:8000)"
	@echo "  make frontend    Start Next.js dev server (127.0.0.1:3000)"
	@echo "  make scheduler   List scheduled tasks"
	@echo "  make news        Scrape RSS news sentiment (daily)"
	@echo "  make strategy    Re-evaluate strategy assignments (weekly)"
	@echo ""
	@echo "Environments:"
	@echo "  make run-research  Start API with ENV=research"
	@echo "  make run-paper     Start API with ENV=paper"
	@echo "  make run-live      Start API with ENV=live"

install:
	uv sync

dev:
	cd frontend && npm install

test:
	uv run pytest -q --cov=src/market --cov-fail-under=70

lint:
	uv run ruff check .

typecheck:
	uv run mypy src/market

migrate:
	uv run alembic upgrade head

migrate-pg:
	DATABASE_URL=postgresql://petrick:market_dev@localhost:5432/market uv run alembic upgrade head

api:
	uv run market api --reload

frontend:
	cd frontend && npm run dev

scheduler:
	uv run market scheduler list

run-research:
	ENV=research uv run market api --reload --host 127.0.0.1 --port 8000

run-paper:
	ENV=paper uv run market api --reload --host 127.0.0.1 --port 8001

run-live:
	ENV=live uv run market api --host 127.0.0.1 --port 8002

news:
	uv run python scripts/scrape_rss_news.py --days 7

strategy:
	uv run python -c "from market.scheduler_tasks import _task_strategy_assignment; _task_strategy_assignment()"
