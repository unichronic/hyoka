# Hyoka System Design Pass

Date: 2026-05-24

## Design North Star

Hyoka is not primarily a trace viewer. It is a reliability control plane for AI
agents. The hardest system properties are reproducibility, safe replay, artifact
lineage, and promotion control. The architecture should optimize for:

- durable state transitions over in-process convenience
- explicit ownership of long-running work
- immutable inputs and artifacts
- replay safety before live execution
- operational clarity over framework cleverness

## System Boundaries

### API Server

Owns validation, authorization, durable metadata, audit logs, and read APIs. It should not
own long-running replay/eval execution in production because request lifecycles
are the wrong failure domain for resumable work.

Current decision:

- `POST /v1/events` and `POST /v1/events/batch` accept generic framework-neutral
  events and normalize them into canonical traces.
- `POST /v1/traces` accepts fully assembled canonical traces.
- `POST /v1/runs` creates a queued run and case records.
- `/v1/api-keys` manages hashed, scoped API keys after bootstrap.
- `/v1/audit-events` exposes project-scoped operator audit history.
- Inline execution is disabled by default and should be treated as a local-only
  escape hatch.

### Integration Contract

Hyoka should integrate like Prometheus: services can either push events or expose
an endpoint that Hyoka scrapes. The SDK and proxy are conveniences, not required
architecture choices.

Supported integration paths now:

- generic event push: `POST /v1/events/batch`
- canonical trace push: `POST /v1/traces/batch`
- OTLP/JSON trace export: `POST /v1/otel/v1/traces`
- pull/scrape: `hyoka scrape http://service/hyoka/traces`
- OpenAI-compatible proxy
- Python SDK decorators and event emitters

The generic event envelope uses labels for low-cardinality dimensions such as
service, environment, version, region, tenant, and agent. This makes Hyoka
usable across web services, workers, serverless functions, CLI agents, browser
agents, and custom orchestrators.

### Worker

Owns run execution. Workers claim runs through database-backed leases:

```text
queued -> claimed by worker lease -> running -> finalizing -> completed
                                          -> failed/cancelled
```

The schema tracks:

- `worker_id`
- `lease_expires_at`
- `execution_attempts`
- bounded worker attempts
- cancellation requests
- per-case error status

This database lease model is production-capable for a small worker pool. Once
live replay fan-out, human approvals, resumability across many activities, and
multi-hour cancellation history become non-trivial, Temporal is the better
upgrade than adding Redis plus a generic queue. Temporal models long-running
workflows, heartbeats, cancellation, retries, and durable history directly.

### Replay And Evaluation

Mock replay is deterministic and uses captured outputs. Live, hybrid, and
sandbox replay use an explicit HTTP callback contract:

```text
worker -> allowed replay endpoint -> agent runtime -> replay output
```

The callback surface is disabled by default and requires
`HYOKA_ENABLE_HTTP_REPLAY=true` plus `HYOKA_HTTP_REPLAY_ALLOWED_HOSTS`. This is
intentional SSRF protection because replay endpoints often sit inside private
networks. HTTP evaluators use the same allowlist.

### Evaluators

The run engine uses an evaluator registry. Built-ins cover final-output
presence, error-free trajectory, required/forbidden tool use, regex output
contracts, latency, cost, JSON schema validation, HTTP evaluator callbacks, and
LLM judge callbacks. Candidate config can use legacy keys or
`config.evaluators` for explicit registry entries.

### Candidate Generation

Failure clusters now generate durable improvement proposals from run evidence.
The generator inspects failed eval labels and representative case evidence, then
builds deterministic, evidence-hashed candidate patches for prompt, tool policy,
output contract, runtime policy, replay policy, and eval-policy targets. It can
also materialize a new candidate from the proposal so the loop is:

```text
run -> failure cluster -> improvement proposal -> candidate -> run
```

Autonomous cycles persist that loop as a first-class control-plane object:

```text
baseline run
  -> mine actionable failure clusters
  -> generate evidence-hashed proposals and adapter patch bundles
  -> materialize candidate configs
  -> launch validation runs on the baseline suite
  -> compare baseline vs candidate
  -> evaluate release gate and manifest
  -> optionally record promotion
```

Patch bundles use a portable `hyoka.patch.v1` envelope with adapter renderings
for generic JSON, LangGraph, CrewAI, AutoGen, LlamaIndex, and OpenAI Agents SDK
runtimes. Agent runtimes can consume the same candidate config over the replay
callback contract, so Hyoka owns the autonomous evaluation and promotion loop
while framework adapters own local code/config application.

### Artifact Store

Artifacts are immutable and content-addressed. Local filesystem storage uses
atomic replacement for single-node operation. The S3-compatible backend writes
objects by content hash and records `s3://bucket/key` URIs. Artifact reads verify
the stored content hash before returning content.

### Database

Postgres is the production metadata store. SQLite is for single-process local
development and tests only. Schema changes are managed by Alembic; startup
auto-migration is disabled by default.

### Dashboard

The dashboard is an operational read surface over API state. It should not
become a second control plane. Server-rendered reads are sufficient for the MVP,
so no client query/cache library is installed yet.

Current dashboard routes cover operations, trace details, run details with cases
and proposals, API-key creation/listing, proposal listing, and gate evaluation.

## Corrections Made

- Disabled API-owned background execution by default.
- Added database-backed worker claims and leases for validation runs and
  autonomous self-improvement cycles.
- Added generic event ingestion and scrape import as the framework-neutral
  integration contract.
- Added worker execution attempts and lease expiry metadata.
- Added scoped API keys, revocation, audit events, and project isolation.
- Added S3-compatible artifact storage and integrity verification.
- Added safe HTTP replay/evaluator callbacks for non-mock replay modes.
- Added OTLP/JSON GenAI/OpenInference ingestion.
- Added evaluator registry, JSON schema evaluator, and LLM judge hooks.
- Added evidence-based candidate proposal generation.
- Added worker-owned self-improvement cycle execution with persisted queue,
  leases, bounded attempts, patch bundles, validation runs, gates, and optional
  promotions.
- Added deeper dashboard routes for traces, runs, proposals, API keys, and
  gates.
- Changed production deployment to run explicit migrations before server/worker
  startup.
- Changed Docker Compose so the worker, not the server, executes runs.
- Isolated test database and artifact paths from local dev state.
- Kept Redis, OpenTelemetry SDK, Tailwind, and TanStack Query out of runtime
  dependencies until their corresponding features exist.
- Made local artifact writes atomic.
- Made CORS explicit instead of wildcard-plus-credentials.

## Current Limits

- Database leases are good enough for small worker pools, but they are not a
  full durable workflow engine.
- Existing SQLite databases created before current migrations may need to be
  reset locally or migrated through Alembic.
- Framework adapters remain adoption targets, not required core dependencies.
- OTLP/JSON ingestion is implemented; protobuf OTLP/gRPC can be added as a
  packaging extension if operators require native collector wire compatibility.

## Next Production Upgrade

The next major system upgrade should be a durable workflow layer:

```text
API creates run intent
-> workflow starts run
-> activities replay cases
-> activities evaluate cases
-> workflow builds artifacts and manifest
-> gate activity records decision
```

Temporal is the preferred candidate when this becomes necessary because Hyoka
needs durable cancellation, long-running replay, retries, heartbeats, and audit
history more than it needs generic background jobs.
