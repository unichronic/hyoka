# Hyoka 2 Engineering Design

## 1. Overview

Hyoka 2 is an attachable reliability and self-improvement layer for AI agents.
It captures traces from existing agent systems, normalizes them into a canonical
schema, stores them durably, evaluates behavior, replays candidate
configurations, mines failures, proposes improvements, and enforces release
gates through reproducible artifacts.

The system must support local development, CI, and production-style deployment.
It should be modular enough to support multiple integration paths without
coupling the core replay/eval/improvement system to any single agent framework.

## 2. High-Level Architecture

```text
Existing Agent
   |
   |-- Proxy
   |-- SDK
   |-- Framework Adapter
   |-- OTEL Collector
   |-- Sidecar
   |-- Batch Import
   |
Hyoka Ingestion Layer
   |
Trace Normalizer
   |
Canonical Trace Store
   |
---------------------------------------------------------
| Replay Engine | Eval Engine | Failure Miner            |
| Flaky Runner  | Candidate Generator | Experiment Runner |
| Gate Engine   | Manifest Builder    | Exporter          |
---------------------------------------------------------
   |
Metadata Store + Artifact Store + Config Registry
   |
CLI / API / Dashboard / CI
```

## 3. Runtime Components

### 3.1 hyoka-server

FastAPI service that exposes the public API.

Responsibilities:

- trace ingestion
- API-key authentication and project authorization
- suite management
- candidate registration
- run creation
- run status reads
- eval config management
- failure mining requests
- experiment orchestration
- release gate evaluation
- promotion decisions
- manifest reads
- audit event reads

### 3.2 hyoka-worker

Worker process that executes long-running jobs through database-backed run
leases.

Responsibilities:

- replay cases
- execute evals
- compute flakiness reports
- mine failures
- run experiments
- build artifacts and manifests
- export training data

Current execution backend:

- Postgres/SQLite-backed run claims, leases, attempt limits, and cancellation.
- Temporal is the preferred upgrade when replay needs durable multi-activity
  workflows, heartbeats, retries, and long-running cancellation history.

### 3.3 hyoka-proxy

OpenAI-compatible HTTP proxy for low-friction LLM call capture.

Responsibilities:

- accept OpenAI-compatible chat/completions/responses requests
- forward requests to configured provider
- capture request and response metadata
- preserve streaming provider responses
- redact configured fields
- emit trace events to server or sidecar buffer

Provider targets:

- OpenAI-compatible APIs
- Anthropic through adapter mapping
- Ollama
- vLLM
- local OpenAI-compatible endpoints

### 3.4 hyoka-sdk-py

Python instrumentation package.

Responsibilities:

- decorators for traces, tools, retrieval, and memory events
- framework-neutral event emitters
- context propagation across async calls
- proxy-compatible capture for common LLM SDKs that support base URL overrides
- local buffering and retry
- explicit flush on process shutdown

### 3.5 hyoka-sdk-js

JavaScript/TypeScript instrumentation package.

Responsibilities:

- wrappers for fetch/OpenAI SDK/Vercel AI SDK
- tool and trace event helpers
- browser/server compatibility where possible
- streaming event capture

### 3.6 hyoka-collector

Receives OpenTelemetry spans, webhooks, and sidecar events.

Responsibilities:

- OTEL span ingestion
- span-to-trace mapping
- webhook normalization
- batch event validation
- event deduplication

### 3.7 hyoka-sidecar

Deployment companion for Docker/Kubernetes.

Responsibilities:

- local proxy endpoint
- local trace buffer
- upload retries
- health endpoints
- redaction at edge
- optional disk-backed queue

### 3.8 hyoka-cli

Developer and CI interface.

Responsibilities:

- local setup and diagnostics
- Alembic migration commands
- API key administration
- trace import
- suite creation
- run and compare workflows
- release gate evaluation
- manifest retrieval
- audit log reads
- training export

### 3.9 hyoka-dashboard

Operational UI.

Responsibilities:

- trace inspection
- timeline view
- eval run status
- failure clusters
- experiment comparison
- release gates
- promotion history
- manifest browser

## 4. Recommended Tech Stack

```text
API server: FastAPI, Pydantic, SQLAlchemy
Database: Postgres
Migrations: Alembic
Worker execution: database-backed leases, Temporal later for durable workflows
Artifact store: local content-addressed store, S3-compatible backend
CLI: Typer
SDK Python: Pydantic, httpx, contextvars
SDK JS/TS: TypeScript, undici/fetch wrappers
Proxy: FastAPI/httpx or Go if performance becomes critical
Dashboard: Next.js, TypeScript, React, plain CSS
Observability: OpenTelemetry, structured JSON logs, Prometheus metrics
Testing: pytest, testcontainers, respx, k6
Deployment: Docker Compose, Kubernetes manifests later
```

## 5. Suggested Monorepo Structure

```text
hyoka/
  apps/
    server/
      hyoka_server/
    worker/
      hyoka_worker/
    proxy/
      hyoka_proxy/
    collector/
      hyoka_collector/
    dashboard/
  packages/
    sdk-py/
      hyoka/
    sdk-js/
    cli/
      hyoka_cli/
    adapters/
      langchain/
      langgraph/
      llamaindex/
      autogen/
    schemas/
  deploy/
    docker-compose.yml
    k8s/
  examples/
    refund-agent/
    openai-proxy/
    langgraph-agent/
  tests/
    integration/
    load/
```

## 6. Data Architecture

### 6.1 Stores

**Postgres**

Stores metadata, normalized traces, state machines, run status, eval summaries,
gates, promotions, and artifact references.

**Object Store**

Stores large immutable payloads:

- raw trace imports
- normalized trace snapshots
- run logs
- replay outputs
- eval reports
- comparison reports
- manifests
- training exports

**Worker Lease State**

Run ownership, lease expiry, attempts, cancellation, and status transitions live
in the metadata database. Redis is not required for the production core.

### 6.2 Core Tables

```text
projects
agents
environments
integrations
api_keys
traces
trace_steps
trace_events_raw
suites
suite_cases
candidates
candidate_artifacts
runs
run_cases
eval_configs
eval_results
failure_clusters
failure_cluster_members
improvement_proposals
experiments
experiment_arms
release_gates
gate_decisions
promotions
artifacts
manifests
memory_events
training_exports
worker_heartbeats
audit_events
```

### 6.3 Canonical Trace Schema

All integration sources normalize into this internal shape.

```json
{
  "trace_id": "tr_123",
  "project_id": "proj_123",
  "agent_name": "refund-agent",
  "session_id": "sess_456",
  "environment": "prod",
  "git_sha": "abc123",
  "started_at": "2026-05-23T10:00:00Z",
  "ended_at": "2026-05-23T10:00:03Z",
  "input": {
    "role": "user",
    "content": "Refund my order"
  },
  "steps": [
    {
      "step_id": "step_1",
      "parent_step_id": null,
      "type": "llm_call",
      "name": "planner",
      "provider": "openai",
      "model": "gpt-4.1-mini",
      "input_hash": "sha256:...",
      "output_hash": "sha256:...",
      "output_preview": "I need to look up the order.",
      "latency_ms": 912,
      "tokens_input": 300,
      "tokens_output": 90,
      "cost_usd": 0.002,
      "status": "ok"
    },
    {
      "step_id": "step_2",
      "parent_step_id": "step_1",
      "type": "tool_call",
      "tool_name": "lookup_order",
      "arguments_hash": "sha256:...",
      "arguments_preview": {"order_id": "A123"},
      "response_hash": "sha256:...",
      "response_preview": {"status": "delivered"},
      "latency_ms": 120,
      "status": "ok"
    }
  ],
  "final_output_hash": "sha256:...",
  "final_output_preview": "Your refund has been issued.",
  "summary": {
    "latency_ms": 3012,
    "tokens_total": 842,
    "cost_usd": 0.0031,
    "status": "ok"
  },
  "metadata": {
    "user_segment": "support",
    "region": "us"
  }
}
```

### 6.4 Step Types

Supported step types:

```text
llm_call
tool_call
tool_result
retrieval
memory_read
memory_write
memory_update
memory_delete
router_decision
human_review
error
custom_event
```

### 6.5 Candidate Schema

```json
{
  "candidate_id": "cand_123",
  "name": "prompt_patch_v3",
  "base_candidate_id": "cand_base",
  "targets": ["prompt"],
  "config": {
    "system_prompt": "You are a refund assistant. Always verify delivery..."
  },
  "metadata": {
    "created_by": "hyoka_failure_miner",
    "source_cluster_id": "fc_789"
  }
}
```

### 6.6 Run State Machine

```text
queued -> running -> finalizing -> completed
                    -> failed
                    -> cancelled
                    -> timed_out
```

Case state machine:

```text
pending -> running -> replayed -> evaluated -> passed
                                      -> failed
                                      -> flaky
                                      -> error
                                      -> skipped
```

## 7. Ingestion Design

### 7.1 Event Flow

```text
integration event
-> ingestion endpoint
-> auth and validation
-> raw event persistence
-> deduplication
-> normalization
-> trace assembly
-> canonical trace persistence
-> artifact snapshot
```

### 7.2 Idempotency

Each ingestion request should support an idempotency key.

Recommended key:

```text
source + trace_id + step_id + event_sequence
```

The server must safely handle duplicate SDK retries and sidecar replays.

### 7.3 Streaming Capture

Streaming LLM calls should be captured as:

- raw chunk events in artifact store if configured
- final assembled text in canonical trace
- timing metadata for first token and total completion

Metrics:

- time to first token
- total stream duration
- chunk count
- stream error status

### 7.4 Redaction Pipeline

Redaction should occur before durable persistence when configured.

Stages:

```text
raw payload
-> field allowlist/denylist
-> secret detector
-> PII detector
-> user-defined redactors
-> persisted event
```

## 8. Replay Engine

### 8.1 Responsibilities

- reconstruct trace context
- load candidate config
- select replay mode
- execute or mock LLM/tool/retrieval/memory steps
- capture replay output
- emit replay trace
- store artifacts

### 8.2 Replay Modes

**Mock**

Uses recorded model and tool outputs.

**Live**

Re-executes model and tool calls.

**Hybrid**

Common modes:

- live model, mocked external tools
- mocked model, live local tools
- live retriever, mocked tools

**Sandbox**

Runs side-effecting tools in isolated environments.

### 8.3 Tool Isolation

Tool replay should support:

- dry-run wrappers
- side-effect blocking
- mocked responses
- sandbox containers
- timeouts
- network allowlists
- fixture injection

### 8.4 Replay Determinism

Record:

- model name
- provider
- temperature
- seed when supported
- prompt hash
- tool schema hash
- retriever config hash
- memory state hash
- environment variables allowlist
- package/version metadata when available

## 9. Evaluation Engine

### 9.1 Eval Interface

Every evaluator should implement:

```python
class Evaluator:
    name: str
    version: str

    async def evaluate(self, case_context, replay_result) -> EvalResult:
        ...
```

### 9.2 Eval Result Shape

```json
{
  "evaluator": "required_tool_called",
  "version": "1.0.0",
  "score": 1.0,
  "passed": true,
  "severity": "none",
  "labels": ["tool_use"],
  "reason": "lookup_order was called before issue_refund",
  "evidence_step_ids": ["step_2", "step_3"]
}
```

### 9.3 Built-In Evaluators

Final-output:

- exact match
- regex
- JSON schema
- semantic similarity
- LLM judge
- human review marker

Trajectory:

- required tool called
- forbidden tool not called
- tool arguments valid
- no repeated useless tool calls
- memory operation allowed
- retrieval context relevant
- final state correct

Performance:

- max latency
- max p95 latency
- max cost
- max token usage
- timeout rate

Safety:

- unsafe tool call
- secret leakage
- PII leakage
- irreversible action without confirmation
- policy violation

### 9.4 LLM Judge Controls

LLM-as-judge must store:

- judge model
- judge prompt hash
- rubric hash
- input trace hash
- output
- score
- rationale
- token usage
- cost

LLM judges should support repeated judging to detect judge variance.

## 10. Flakiness Engine

### 10.1 Purpose

Detect cases whose pass/fail outcome or behavior varies across repeated runs.

### 10.2 Metrics

- pass rate over N runs
- output similarity variance
- tool-path variance
- judge-score variance
- latency variance
- token/cost variance
- timeout frequency

### 10.3 Output

```json
{
  "case_id": "case_123",
  "repeats": 5,
  "pass_rate": 0.6,
  "flaky": true,
  "tool_path_variants": 3,
  "score_stddev": 0.22,
  "latency_p95_ms": 4200
}
```

## 11. Failure Mining

### 11.1 Inputs

- eval results
- trace steps
- error labels
- judge rationales
- final-state mismatches
- latency/cost outliers
- human review labels

### 11.2 Algorithm Options

Initial:

- rule-based grouping by failure labels and evaluator names
- embeddings over failure rationale and trace summaries
- clustering with configurable threshold

Later:

- supervised root-cause classifier
- causal analysis over step features
- LLM-assisted cluster naming

### 11.3 Output

```json
{
  "cluster_id": "fc_123",
  "name": "refund_without_delivery_check",
  "failure_type": "unsafe_tool_call",
  "case_count": 37,
  "representative_trace_ids": ["tr_1", "tr_8"],
  "hypothesis": "Agent issues refund before verifying delivery status.",
  "suggested_targets": ["prompt", "tool_precondition", "eval_rule"]
}
```

## 12. Candidate Generation

### 12.1 Candidate Targets

- prompt
- tool description
- tool schema
- retriever config
- memory policy
- router policy
- retry/fallback policy
- human-review threshold

### 12.2 Candidate Sources

- generated by Hyoka
- authored by user
- imported from config file
- imported from Git branch or artifact

### 12.3 Generation Constraints

Candidate generation must:

- preserve base config lineage
- explain target failure cluster
- avoid direct promotion
- require experiment validation
- store prompt/model used to generate candidate when LLM-assisted

## 13. Experiment Runner

### 13.1 Experiment Structure

An experiment compares one or more candidate arms against a baseline.

```json
{
  "experiment_id": "exp_123",
  "baseline_candidate_id": "cand_base",
  "arms": ["cand_prompt_v3", "cand_router_v2"],
  "suite_ids": ["suite_support_v1"],
  "mode": "hybrid",
  "repeats": 3
}
```

### 13.2 Ranking

Default ranking:

```text
hard blockers first
-> pass rate
-> safety score
-> flaky rate
-> latency
-> cost
-> token usage
```

Weights should be configurable per gate policy.

## 14. Release Gate Engine

### 14.1 Policy Schema

```yaml
suite: support-v1
mode: hybrid
min_pass_rate: 0.94
max_flaky_rate: 0.04
max_cost_increase_pct: 12
max_p95_latency_ms: 3500
must_improve:
  - tool_success_rate
  - final_answer_score
block_on:
  - unsafe_tool_call
  - state_corruption
  - hallucinated_fact
required_artifacts:
  - eval_report
  - comparison_report
  - manifest
```

### 14.2 Decision Shape

```json
{
  "decision": "blocked",
  "candidate_id": "cand_prompt_v3",
  "run_id": "run_123",
  "pass_rate": 0.91,
  "flaky_rate": 0.02,
  "blocking_reasons": [
    "pass_rate below required threshold 0.94",
    "unsafe_tool_call found in 2 cases"
  ],
  "manifest_id": "man_123"
}
```

## 15. Artifact Lineage and Manifests

### 15.1 Content Addressing

Hash all durable experiment inputs and outputs:

- trace set
- suite definition
- candidate config
- tool schema
- prompt config
- model config
- eval config
- replay output
- eval report
- comparison report
- gate policy

### 15.2 Manifest Shape

```json
{
  "manifest_id": "man_123",
  "run_id": "run_789",
  "suite_hash": "sha256:...",
  "candidate_hash": "sha256:...",
  "trace_set_hash": "sha256:...",
  "eval_config_hash": "sha256:...",
  "replay_output_hash": "sha256:...",
  "result_hash": "sha256:...",
  "gate_policy_hash": "sha256:...",
  "decision": "blocked",
  "created_at": "2026-05-23T10:00:00Z",
  "signature": "..."
}
```

### 15.3 Signing

Support HMAC signing initially. Later support asymmetric signatures for
team/org verification.

## 16. API Design

### 16.1 Traces

```text
POST /v1/traces
POST /v1/traces/batch
POST /v1/traces/import
GET  /v1/traces/{trace_id}
GET  /v1/traces
```

### 16.2 Suites

```text
POST /v1/suites
GET  /v1/suites
GET  /v1/suites/{suite_id}
POST /v1/suites/{suite_id}/cases
```

### 16.3 Candidates

```text
POST /v1/candidates
GET  /v1/candidates/{candidate_id}
GET  /v1/candidates
```

### 16.4 Runs

```text
POST /v1/runs
GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/cases
POST /v1/runs/{run_id}/cancel
POST /v1/runs/compare
```

### 16.5 Failures and Improvements

```text
POST /v1/failures/mine
GET  /v1/failure-clusters
POST /v1/improvements/propose
GET  /v1/proposals
```

### 16.6 Experiments

```text
POST /v1/experiments
GET  /v1/experiments/{experiment_id}
POST /v1/experiments/{experiment_id}/run
```

### 16.7 Gates and Promotions

```text
POST /v1/gates
POST /v1/gates/evaluate
GET  /v1/gates/{gate_id}/decisions
POST /v1/promotions
GET  /v1/promotions
```

### 16.8 Artifacts

```text
GET /v1/artifacts/{artifact_id}
GET /v1/manifests/{run_id}
```

## 17. CLI Design

```bash
hyoka doctor
hyoka login
hyoka proxy start
hyoka import traces.jsonl --format hyoka
hyoka suite create support-v1
hyoka suite add-cases support-v1 --from-query "agent=refund status=failed"
hyoka run --suite support-v1 --candidate candidate.yaml --mode hybrid
hyoka run status run_123
hyoka failures mine --run run_123
hyoka propose --target prompt --cluster fc_123
hyoka experiment create --baseline base.yaml --candidate prompt-v3.yaml
hyoka experiment run exp_123
hyoka compare run_base run_candidate
hyoka gate --run run_candidate --policy release.yaml
hyoka promote --candidate cand_123 --gate gate_123
hyoka manifest --run run_123
hyoka export training-data --run run_123 --format dpo
```

## 18. Observability

### 18.1 Metrics

API metrics:

- request count
- request latency
- error rate
- ingestion throughput
- trace normalization failures

Worker metrics:

- queue depth
- job duration
- job retries
- job failures
- active workers
- worker heartbeat age

Replay/eval metrics:

- cases per minute
- replay success rate
- eval success rate
- average cost per run
- p50/p95/p99 latency

### 18.2 Logs

Use structured JSON logs with:

- request id
- project id
- run id
- case id
- worker id
- trace id
- job type
- error code

### 18.3 Tracing

Instrument Hyoka itself with OpenTelemetry:

- ingestion request
- normalization
- queue enqueue
- worker execution
- replay step
- evaluator step
- artifact write
- gate decision

## 19. Security and Privacy

### 19.1 Authentication

Initial:

- project API keys
- local dev mode without auth

Production:

- scoped API keys
- service tokens
- user auth for dashboard
- RBAC later

### 19.2 Data Protection

Requirements:

- configurable PII redaction
- configurable secret redaction
- field-level capture controls
- encrypted object storage where supported
- audit log for promotions and gate overrides

### 19.3 Tool Replay Safety

Side-effecting tools must not run live without explicit configuration.

Safety controls:

- dry-run mode
- mock mode default
- sandbox execution
- network allowlists
- timeout limits
- dangerous tool blocklist

## 20. Deployment Architecture

### 20.1 Local Docker Compose

Services:

- hyoka-server
- hyoka-worker
- hyoka-proxy
- postgres
- redis
- minio
- dashboard

### 20.2 Production

Services:

- API server replicas
- worker pool
- proxy service or sidecars
- collector
- Postgres
- Redis
- S3-compatible object store
- dashboard
- metrics/logging stack

### 20.3 Scaling Strategy

Scale independently:

- API server by request traffic
- workers by replay/eval queue depth
- proxy by LLM call throughput
- collector by event ingestion throughput

Partitioning:

- project-level partitioning for trace queries
- time-based partitioning for high-volume trace tables
- object store for large payloads

## 21. Testing Strategy

### 21.1 Unit Tests

- schema validation
- trace normalization
- evaluator logic
- policy evaluation
- hash generation
- redaction rules

### 21.2 Integration Tests

- trace ingestion to DB
- run creation to worker execution
- artifact write/read
- replay mode behavior
- gate decision
- CLI/API integration

### 21.3 Contract Tests

- SDK event payloads
- proxy OpenAI compatibility
- framework adapter mappings
- OTEL span mapping

### 21.4 Load Tests

Use k6 or Locust for:

- trace ingestion throughput
- run creation concurrency
- dashboard trace queries
- proxy overhead

### 21.5 Replay Safety Tests

- tool side effects blocked in mock mode
- live mode requires explicit allowlist
- sandbox timeouts enforced
- secrets redacted before persistence

## 22. Performance Targets

Initial targets:

- SDK event enqueue under 10 ms p95 locally.
- Ingestion API under 100 ms p95 for single events.
- Proxy overhead under 50 ms p95 excluding provider latency.
- Batch import of 100,000 traces without manual intervention.
- 1,000-case replay run with resumable progress.
- Dashboard trace query under 1 second p95 for recent traces with indexes.

## 23. Failure Modes and Mitigations

**Duplicate trace events**

- idempotency keys and unique constraints.

**Worker dies during run**

- job leases, retries, case-level state, resumable runs.

**Provider outage**

- retry policy, live replay failure labels, partial run status.

**Eval judge nondeterminism**

- repeated judging, judge variance metrics, mockable judge outputs.

**Artifact write failure**

- transactional metadata update only after artifact write success.

**PII leakage**

- redaction before persistence, field capture controls, audit logs.

**Unsafe tool execution**

- mock default, sandbox mode, explicit live tool allowlist.

## 24. Engineering Milestones

### Milestone 1: Foundations

- monorepo setup
- canonical schemas
- FastAPI server
- Postgres migrations
- trace ingestion
- CLI doctor/import
- local Docker Compose

### Milestone 2: Replay and Evals

- suite creation
- candidate config
- async worker
- mock replay
- built-in evaluators
- run status
- artifact storage

### Milestone 3: Release Gates

- comparison reports
- release policy parser
- gate evaluator
- signed manifests
- CI command
- flakiness engine

### Milestone 4: Low-Friction Integrations

- proxy mode
- Python SDK
- one framework adapter
- batch import mappings
- sidecar buffer

### Milestone 5: Self-Improvement

- failure miner
- slice builder
- candidate generator
- experiment runner
- policy selector
- promotion registry

### Milestone 6: Production Hardening

- dashboard
- RBAC/API key scopes
- OTEL collector
- Kubernetes manifests
- load testing
- security review

## 25. Open Engineering Questions

- Should proxy be implemented in Python initially or Go from the beginning?
- Should raw trace payloads be stored in Postgres JSONB, object storage, or both?
- How much of the eval framework should be plugin-based in v1?
- What is the best abstraction for replaying arbitrary user-defined tools?
- How should Hyoka represent multi-agent workflows in the canonical schema?
- Should promotion update a Hyoka config registry only, or also open PRs against
  the user's config repository?
