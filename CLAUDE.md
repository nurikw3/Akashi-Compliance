# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Akashi Compliance — automated counterparty (контрагент) compliance screening for Kazakhstan. Upload a list of BINs/IINs → the system enriches each via **Adata** (KZ registries) and **LSEG World-Check One** (international sanctions/PEP/adverse-media), LLM-classifies court cases, computes a unified 0–100 risk score, and generates an AI conclusion + PDF report. A **Next.js** app is the primary UI; a legacy **Streamlit** app drives the older "audits" flow.

## Commands

Python is managed with **uv** (Python 3.11). Backend lives in `app/`, frontend in `frontend/`.

```bash
# Backend (terminal 1)
uv sync
uv run python main.py                       # FastAPI on :8000 (app.api:app)
uv run python -c "from app.api import app"   # import smoke-check

# TaskIQ worker (terminal 2) — required for queued heavy jobs
uv run akashicompliance-worker

# Redis (queue backend)
docker run -d --name akashi-redis -p 6379:6379 redis:7-alpine

# Frontend
cd frontend && npm install && npm run dev    # Next.js dev on :3000
npm run build    # production build
npm run lint     # eslint

# Legacy Streamlit UI
uv run streamlit run streamlit_app.py

# Everything at once (api, worker, redis, postgres, frontend)
docker compose up --build
```

### Tests

Tests require a **running PostgreSQL**. `tests/conftest.py` creates/uses an isolated `akashicompliance_test` database (derived from `DATABASE_URL`) and forces `AUTH_ENABLED=false`. Async tests use explicit `@pytest.mark.asyncio`.

```bash
docker compose up -d postgres                       # or any local Postgres
uv run pytest                                        # all tests
uv run pytest tests/test_risk_scoring.py             # one file
uv run pytest tests/test_risk_scoring.py::test_sanctions_metric_zero_when_lseg_clean
```

## Architecture

### Provider abstraction (the core design principle)

The system does **not** know about Adata specifically — it knows about a **Provider** interface. Adding a data source = write one class + register it.

- `app/services/enrichment/base.py` — `CompanyData` (single source-agnostic Pydantic model) and `BaseProvider` ABC (`check(iin)`, `is_available()`).
- `app/services/enrichment/registry.py` — singleton `registry`; providers registered at startup (`app/api/__init__.py` lifespan and `app/workers/tasks.py::_ensure_worker_context`).
- `app/services/enrichment/providers/` — `adata.py`, `kompra.py` (stub).
- `app/services/enrichment/service.py` — `EnrichmentService.enrich()` runs all available providers in parallel and `merge()`s their `CompanyData` (first non-empty field wins; lists/`raw` are combined). Returns `(CompanyData, sources, section_sources)`.

Downstream services (`risk/`, `lseg/`, `ai/`) consume `CompanyData`/enrichment dicts and never call providers directly.

### The pipeline (`app/services/pipeline.py`)

`process_case(case_id)` is the heart of the system. Roughly: enrich via providers → LLM-classify court cases (`ai/court_analyzer.py`) → LSEG screen company+director → 7-metric `RiskScorer` → parallel extended Adata fetches (trustworthy-plus, beneficiary, non-residents, relation) → fetch director/affiliate/individual profiles → LSEG **extended** batch screening for all non-resident affiliate targets → write everything into `cases.enriched_data`. `rescreen_case_lseg` / `rescreen_lseg_extended` re-apply LSEG to already-enriched cases.

**Everything a case knows lives in one JSON blob:** `cases.enriched_data` (a TEXT column holding JSON). Keys include `enrichment`, `assessment`, `lseg`, `lsegExtended`, `scoreBreakdown`, `totalScore`, `affiliateTree`, `companyCourtCases`, `individualCourts`, `directorProfile`, `affiliateProfiles`, `verificationLog`, `fullReport`. When editing the pipeline, **preserve existing keys** on re-run (see how `fullReport`/`verificationLog` are carried forward) — a naive overwrite erases prior work.

### Task queue (`app/services/queue.py` + `app/workers/`)

Heavy work runs in a separate TaskIQ worker (Redis broker, `app/workers/broker.py`). `resolve_queue_backend()` picks `taskiq` vs `inline` at runtime by pinging Redis and checking the worker **heartbeat** (`app/workers/heartbeat.py`). If Redis/worker is unavailable or `TASK_QUEUE_ENABLED=false`, it falls back to running the same coroutine **inline** via `asyncio.create_task` in the API process — so the app works with no worker, just synchronously. `GET /health` reports `queue.redisOk/workerOk/activeBackend`.

Job chain: `case_pipeline` (enrichment) → on success queues `affiliate_tree` + `ai_conclusion`. Also `chat_reply`. Each `enqueue_*` in `queue.py` has a matching `@broker.task` in `app/workers/tasks.py`.

### Risk scoring (`app/services/risk/scoring.py`)

`RiskScorer.calculate()` → 0–100 across 7 weighted metrics (sanctions 30, court 20, tax 15, PEP 10, legal status 10, adverse media 5, affiliate 10). Each contribution carries a `reason` + `source` for an auditable breakdown. The module docstring documents the exact weights and rationale — read it before changing weights.

### Other services

- `app/services/lseg/` — LSEG World-Check One v3 (OAuth client, screening, mapper, service). `is_available()` gates it on configured credentials.
- `app/services/ai/` — OpenAI-compatible (`service.py`), court classification, full-report generation, conclusion/chat jobs (`jobs.py`), Langfuse tracing (`langfuse_setup.py`).
- `app/services/adata/client.py` — the **new** case-aware Adata client used by the pipeline (logs to `verificationLog`). Distinct from `app/legacy/adata.py`, used by the Streamlit audits flow.
- `app/services/affiliate_tree.py` — depth-2 affiliate graph built in **plain Python** (no Neo4j).

### API & persistence

- `app/api/__init__.py` builds the FastAPI `app`; auth is a **global** dependency (`require_auth`). Routes in `app/api/routes/`: `cases` (main UI), `providers`, `health`, `audits` (Streamlit). OpenAPI/docs are disabled.
- `app/core/auth.py` — HTTP Basic against a `users` table (bcrypt). Toggle with `AUTH_ENABLED`.
- `app/models/db.py` — **PostgreSQL via raw psycopg3** (`dict_row`), not an ORM. `init_db()` creates `audits`, `cases`, `documents`, `chat_messages`, `users`. JSON fields are stored as serialized TEXT.
- `app/core/config.py` — `settings` dataclass reads everything from `.env` (copy `.env.example`). Also holds Adata base-URL normalization helpers.

## Gotchas

- **Docs describe an aspirational stack, not the current one.** `README.md`, `PRODUCT.md`, and `project.md` mention SQLite / Neo4j / Celery. The actual implementation uses **PostgreSQL** (psycopg3), **TaskIQ** (not Celery), and **no Neo4j** (affiliate tree is in-Python). `SQLITE_PATH` in config is vestigial (one-time migration lives in `scripts/migrate_sqlite_to_postgres.py`). Trust the code over those docs.
- Without `ADATA_TOKEN` / `OPENAI_API_KEY` / LSEG creds, the corresponding service is simply unavailable/degraded rather than crashing (`is_available()` checks, `SUPPRESS_ENRICHMENT_ERRORS`/`USE_STUB_ON_API_FAILURE`).
- The frontend talks to the API via `NEXT_PUBLIC_API_URL` (dev) or, in Docker, a Next rewrite `/backend-api` → `http://api:8000`. In production Docker only the **frontend port (8000)** is published; the API has no host port.
