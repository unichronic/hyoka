# Hyoka 2

Hyoka 2 is a pluggable reliability and self-improvement layer for AI agents.
It attaches to existing agent systems, captures execution traces, evaluates
behavior, mines failures, proposes candidate improvements, replays candidates,
and promotes safer configurations through release gates.

The core thesis is simple: agents should improve from their own traces, but
only through controlled evaluation, reproducible replay, and explicit promotion
policies.

## Documents

- [Product Design](./PRODUCT_DESIGN.md): product goals, users, workflows,
  surfaces, non-goals, and roadmap.
- [Engineering Design](./ENGINEERING_DESIGN.md): architecture, services,
  schemas, APIs, workers, replay, evals, manifests, deployment, and security.
- [Requirements](./REQUIREMENTS.md): functional, non-functional, integration,
  observability, security, and acceptance requirements.
- [Integration Contract](./INTEGRATION.md): Prometheus-style push, pull/scrape,
  proxy, SDK, and label conventions for any agent architecture.
- [System Design](./SYSTEM_DESIGN.md): execution ownership, worker leases,
  artifact boundaries, and production upgrade path.

## One-Line Pitch

Hyoka 2 lets teams attach a reliability layer to any AI agent through a proxy,
SDK, framework adapter, OpenTelemetry collector, sidecar, batch import, or CI
job, then use captured traces to evaluate, replay, improve, and safely promote
agent behavior.

## Core Loop

```text
observe
-> trace
-> evaluate
-> mine failures
-> generate candidates
-> replay candidates
-> compare results
-> gate release
-> promote config
-> monitor again
```

## Primary Capabilities

- Low-friction integration with existing agents.
- Canonical trace capture across LLM calls, tool calls, retrieval, memory,
  latency, cost, errors, and metadata.
- Deterministic replay in mock, live, hybrid, and sandbox modes.
- Trajectory-level evaluation, not just final-answer scoring.
- Failure mining and regression slice generation.
- Candidate generation for prompts, memory policy, tool schemas, retrievers,
  routing policies, and retry/fallback behavior.
- Experiment execution across baseline and candidate agent configurations.
- Flakiness detection through repeated replay.
- Content-addressed artifacts and signed run manifests.
- CI-style release gates for safe promotion.

## Suggested Repository Shape

```text
hyoka/
  README.md
  PRODUCT_DESIGN.md
  ENGINEERING_DESIGN.md
  REQUIREMENTS.md
  apps/
    server/
    dashboard/
    proxy/
    worker/
    collector/
  packages/
    sdk-py/
    sdk-js/
    cli/
    adapters/
    schemas/
  deploy/
    docker-compose.yml
    k8s/
  examples/
    refund-agent/
    langgraph-agent/
    openai-proxy/
  tests/
    integration/
    load/
```

## Current Implementation

This repository now contains a production-grade core service:

- FastAPI API server with authenticated trace/event ingestion, suites,
  candidates, runs, gate decisions, promotions, artifacts, manifests, API key
  administration, and audit logs.
- Project-scoped API keys with hashed storage, revocation, static bootstrap
  keys, request-size limits, explicit CORS, and project isolation on every
  read/write path.
- SQLAlchemy/Alembic metadata model with SQLite for local single-process
  development and Postgres for production.
- Content-addressed artifact storage with local and S3-compatible backends,
  artifact integrity checks, and HMAC-signed manifests.
- Worker-owned replay/eval execution and self-improvement cycles with database
  leases, bounded attempts, cancellation, case-level error isolation, and final
  artifacts/manifests.
- Mock replay plus safe HTTP replay/evaluator extension points for live,
  hybrid, and sandbox integration with arbitrary agent runtimes.
- Evaluator registry with built-in trajectory, regex, latency, cost, JSON schema,
  HTTP evaluator, and LLM judge hook support.
- Failure-cluster candidate generation that produces deterministic, evidence
  hashed proposals and can materialize candidate configs from run evidence.
- Autonomous self-improvement cycles that mine failures, generate patch bundles,
  create candidates, run validation suites, compare against the baseline, apply
  release gates, and optionally record promotions through either inline smoke
  execution or the durable worker queue.
- Typer CLI for migrations, import/scrape, API keys, suites, candidates, runs,
  comparison, failure mining, gates, manifests, promotions, and audit reads.
- OpenAI-compatible proxy with streaming-preserving forwarding and authenticated
  trace capture.
- Generic event ingestion and scrape import for Prometheus-style,
  framework-neutral integration.
- OTLP/JSON ingestion for OpenTelemetry GenAI and OpenInference-style spans at
  `/v1/otel/v1/traces`.
- Python SDK decorators plus framework-neutral event emitters.
- Next.js dashboard with operations, trace detail, run detail, proposal, API-key,
  self-improvement, and gate editor views.
- Docker Compose stack with explicit migration service, healthchecks, API auth,
  server, worker, proxy, dashboard, and Postgres.

## Tech Stack Discipline

The implementation keeps runtime dependencies limited to what is currently
used:

- **API:** FastAPI, Pydantic, SQLAlchemy, Alembic.
- **Database:** SQLite for single-process local development, Postgres in Docker
  Compose.
- **Worker:** database-backed leases are implemented for the production core.
  Temporal remains the right upgrade when workflows need durable heartbeats,
  resumability across many activities, and long-running cancellation history.
- **Artifacts:** content-addressed local filesystem storage for single-node
  operation and S3-compatible storage for production object stores.
- **CLI:** Typer and Rich.
- **Dashboard:** Next.js, React, TypeScript, and plain CSS. No Tailwind or client
  query library is included because the current dashboard uses server-rendered
  API reads and custom operational styling.
- **Observability:** structured JSON logs, Prometheus metrics, and OTLP/JSON
  ingestion for GenAI/OpenInference spans. Hyoka does not require linking the
  OpenTelemetry SDK into the server to receive exporter payloads.

## Local Quickstart

Install Python dependencies:

```bash
uv sync --extra dev
```

Start the API locally:

```bash
uv run hyoka db upgrade head
uv run hyoka-server
```

In another shell, start the worker:

```bash
uv run hyoka-worker serve
```

In a third shell, import the example traces and run the loop:

```bash
uv run hyoka import examples/refund-agent/traces.jsonl --suite support-v1
uv run hyoka candidate create examples/refund-agent/candidate.yaml
uv run hyoka run create support-v1 refund_prompt_guardrail_v1 --wait
uv run hyoka gate <run_id> examples/refund-agent/release.yaml
uv run hyoka manifest <run_id>
```

For Prometheus-style pull integration, expose Hyoka exposition JSON from any
service and scrape it:

```bash
python -m http.server 9108 --directory examples/generic-service
uv run hyoka scrape http://localhost:9108/hyoka-exposition.json --suite scraped-support
```

For OTEL-native integration, point an OTLP/HTTP JSON exporter or bridge at:

```text
POST /v1/otel/v1/traces
```

The mapper handles OpenTelemetry GenAI attributes such as `gen_ai.*` and
OpenInference attributes such as `openinference.span.kind`, `input.value`, and
`output.value`.

Run tests:

```bash
uv run pytest
uv run ruff check apps packages tests
```

Start the full local stack:

```bash
cp .env.example .env
# edit .env values before using the stack outside local development
docker compose up --build
```

Default service ports:

- API: http://localhost:8686
- Proxy: http://localhost:8687
- Dashboard: http://localhost:3000

## Production Operation

Minimum production settings:

```bash
export HYOKA_DATABASE_URL=postgresql+psycopg://...
export HYOKA_REQUIRE_API_KEY=true
export HYOKA_API_KEYS='<bootstrap-admin-key>'
export HYOKA_MANIFEST_SECRET='<32+ chars of random secret material>'
export HYOKA_AUTO_MIGRATE=false
```

Run migrations explicitly:

```bash
uv run hyoka db upgrade head
```

Create scoped keys and stop using the bootstrap key for CI/agents:

```bash
uv run hyoka api-key create ci-agent --project default --scope read --scope write
uv run hyoka api-key list --project default
uv run hyoka audit list --project default
```

For live, hybrid, or sandbox replay, configure candidate `config.replay.url` and
enable callback hosts explicitly:

```bash
export HYOKA_ENABLE_HTTP_REPLAY=true
export HYOKA_HTTP_REPLAY_ALLOWED_HOSTS=agent-runtime.internal,evals.internal
```

For production artifacts, set `HYOKA_ARTIFACT_BACKEND=s3` and configure the S3
bucket, prefix, region, and optional endpoint URL.

## Research

See [Research Notes](./RESEARCH_NOTES.md) for the competitor/tooling research
used to choose the initial stack and product wedge.

See [System Design](./SYSTEM_DESIGN.md) for the architecture pass and the
worker/lease execution model.
