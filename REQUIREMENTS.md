# Hyoka 2 Requirements

## 1. Scope

This document defines product, engineering, functional, non-functional,
integration, security, observability, and acceptance requirements for Hyoka 2.

Hyoka 2 is a pluggable reliability and self-improvement layer for AI agents. It
must attach to existing agents, capture traces, evaluate behavior, mine
failures, propose improvements, replay candidates, detect regressions, and gate
promotion decisions.

## 2. Requirement Keywords

- **MUST:** required for the product to satisfy the design.
- **SHOULD:** important but may be staged if explicitly deferred.
- **MAY:** optional or future capability.

## 3. Functional Requirements

### 3.1 Integration

FR-001: Hyoka MUST support at least one low-friction integration path that does
not require rewriting the user's agent.

FR-002: Hyoka MUST support OpenAI-compatible proxy mode.

FR-003: Proxy mode MUST capture request messages, model, parameters, response,
latency, token usage when available, provider errors, and streaming metadata.

FR-004: Hyoka MUST provide a Python SDK for explicit trace, tool, retrieval, and
memory instrumentation.

FR-005: SDK instrumentation MUST support async Python functions.

FR-006: SDK instrumentation MUST preserve trace context across nested calls.

FR-007: Hyoka SHOULD provide a JavaScript/TypeScript SDK.

FR-008: Hyoka SHOULD support framework adapters for LangChain and LangGraph.

FR-009: Hyoka SHOULD support OpenTelemetry ingestion.

FR-010: Hyoka SHOULD support sidecar deployment with local buffering and retry.

FR-011: Hyoka MUST support batch import from Hyoka JSONL.

FR-012: Hyoka SHOULD support imports from OpenTelemetry span JSON and
LangSmith-style trace exports.

### 3.2 Trace Capture

FR-013: Hyoka MUST normalize all inputs into a canonical trace schema.

FR-014: A trace MUST include agent identity, session identity when available,
environment, input, steps, final output, timing metadata, and status.

FR-015: Trace steps MUST support LLM calls, tool calls, retrieval, memory events,
router decisions, errors, and custom events.

FR-016: Hyoka MUST persist raw ingestion events or raw event artifacts when
configured.

FR-017: Hyoka MUST support idempotent ingestion.

FR-018: Hyoka MUST deduplicate retried SDK, sidecar, and batch-import events.

FR-019: Hyoka MUST support configurable redaction before durable persistence.

FR-020: Hyoka SHOULD capture time to first token for streaming model calls.

### 3.3 Suites

FR-021: Hyoka MUST allow users to create versioned suites from traces.

FR-022: A suite MUST contain one or more trace cases.

FR-023: A suite SHOULD support slices based on failure labels, metadata, agent,
tool, model, environment, or custom query.

FR-024: Hyoka MUST preserve the trace-set hash for each suite version.

### 3.4 Candidates

FR-025: Hyoka MUST support candidate configurations.

FR-026: A candidate MUST be able to represent prompt changes.

FR-027: A candidate SHOULD be able to represent model, retriever, tool schema,
memory policy, router policy, and retry/fallback changes.

FR-028: Candidate configs MUST be content-addressed.

FR-029: Candidate lineage MUST be stored.

### 3.5 Replay

FR-030: Hyoka MUST support mock replay.

FR-031: Mock replay MUST avoid live side effects by default.

FR-032: Hyoka MUST support live replay for configured model/tool providers.

FR-033: Hyoka SHOULD support hybrid replay.

FR-034: Hyoka SHOULD support sandbox replay for side-effecting tools.

FR-035: Replay jobs MUST be asynchronous.

FR-036: Replay jobs MUST track per-case status.

FR-037: Replay jobs MUST support cancellation.

FR-038: Replay jobs SHOULD support resumability after worker failure.

FR-039: Replay output MUST be stored as an artifact.

### 3.6 Evaluation

FR-040: Hyoka MUST support final-output evaluators.

FR-041: Hyoka MUST support trajectory evaluators.

FR-042: Hyoka MUST support performance evaluators for latency, tokens, and cost.

FR-043: Hyoka SHOULD support safety evaluators.

FR-044: Hyoka MUST support user-defined evaluators.

FR-045: Hyoka MUST store evaluator name, version, score, pass/fail status,
labels, reason, and evidence references.

FR-046: LLM-as-judge evaluators MUST record judge model, rubric, prompt hash,
score, rationale, token usage, and cost when available.

FR-047: Hyoka SHOULD support repeated LLM judging to detect judge variance.

### 3.7 Flakiness Detection

FR-048: Hyoka MUST support repeated replay for flakiness detection.

FR-049: Hyoka MUST compute pass rate over repeated runs.

FR-050: Hyoka SHOULD compute output variance, tool-path variance, judge-score
variance, latency variance, and cost variance.

FR-051: Hyoka MUST label cases as flaky when configured thresholds are exceeded.

### 3.8 Failure Mining

FR-052: Hyoka MUST mine failed runs into failure clusters.

FR-053: Failure clusters MUST include failure type, case count, representative
trace ids, and root-cause hypothesis.

FR-054: Failure mining MUST support rule-based grouping.

FR-055: Failure mining SHOULD support embedding-based clustering.

FR-056: Failure mining MAY support LLM-assisted cluster naming and explanation.

### 3.9 Self-Improvement

FR-057: Hyoka MUST support improvement proposals.

FR-058: Improvement proposals MUST be separate from promotion decisions.

FR-059: Hyoka MUST support prompt improvement candidates.

FR-060: Hyoka SHOULD support candidates for tool schemas, retriever config,
memory policy, routing policy, and retry/fallback policy.

FR-061: Candidate generation MUST store source failure cluster and generation
method.

FR-062: LLM-generated candidates MUST store generator model, generator prompt
hash, and source inputs.

FR-063: Hyoka MUST prevent automatic production promotion without a gate
decision.

### 3.10 Experiments

FR-064: Hyoka MUST support experiments comparing baseline and candidate runs.

FR-065: Experiments MUST support multiple candidate arms.

FR-066: Experiments MUST support one or more suites.

FR-067: Experiments SHOULD support repeated runs per arm.

FR-068: Experiment reports MUST include quality, safety, flakiness, latency,
cost, and regression summaries.

### 3.11 Release Gates

FR-069: Hyoka MUST support YAML or JSON release gate policies.

FR-070: Release gates MUST support minimum pass rate.

FR-071: Release gates MUST support maximum flaky rate.

FR-072: Release gates MUST support latency and cost thresholds.

FR-073: Release gates MUST support blocking labels.

FR-074: Release gates MUST output approved, blocked, or needs_review.

FR-075: Gate decisions MUST include blocking reasons.

FR-076: Gate decisions MUST reference a manifest.

### 3.12 Promotion

FR-077: Hyoka MUST record promotion decisions.

FR-078: Promotions MUST reference candidate, gate decision, manifest, actor, and
timestamp.

FR-079: Promotion overrides MUST be audit logged.

FR-080: Hyoka SHOULD support rollback to previous promoted candidate.

### 3.13 Artifacts and Manifests

FR-081: Hyoka MUST store immutable artifacts for replay output, eval report,
comparison report, gate decision, and manifest.

FR-082: Artifacts MUST be content-addressed.

FR-083: Run manifests MUST include hashes for suite, trace set, candidate, eval
config, replay output, result, and gate policy.

FR-084: Manifests MUST be signed.

FR-085: Manifests MUST be retrievable through API and CLI.

### 3.14 Training Data Export

FR-086: Hyoka SHOULD export traces and eval outcomes for SFT-style datasets.

FR-087: Hyoka SHOULD export accepted/rejected candidate outputs for
preference-training formats.

FR-088: Training exports MUST include provenance back to source traces and runs.

## 4. API Requirements

AR-001: The API MUST expose endpoints for traces, suites, candidates, runs,
failures, proposals, experiments, gates, promotions, artifacts, and manifests.

AR-002: API responses MUST use stable JSON schemas.

AR-003: API errors MUST include machine-readable error codes.

AR-004: Mutating endpoints SHOULD support idempotency keys.

AR-005: Long-running operations MUST return job or run identifiers.

AR-006: The API MUST expose run and case status.

AR-007: The API SHOULD support pagination for list endpoints.

AR-008: The API SHOULD support filtering traces by agent, environment, status,
model, tool, failure label, suite, and time range.

## 5. CLI Requirements

CR-001: CLI MUST support `doctor`.

CR-002: CLI MUST support trace import.

CR-003: CLI MUST support suite creation.

CR-004: CLI MUST support run creation and status.

CR-005: CLI MUST support run comparison.

CR-006: CLI MUST support release gate execution.

CR-007: CLI MUST support manifest retrieval.

CR-008: CLI SHOULD support proxy startup.

CR-009: CLI SHOULD support failure mining and candidate proposal workflows.

CR-010: CLI SHOULD support training-data export.

## 6. Dashboard Requirements

DR-001: Dashboard MUST show trace list and trace detail.

DR-002: Trace detail MUST show a timeline of LLM calls, tool calls, retrieval,
memory events, errors, and final output.

DR-003: Dashboard MUST show run status and per-case results.

DR-004: Dashboard SHOULD show failure clusters.

DR-005: Dashboard SHOULD show baseline vs candidate comparisons.

DR-006: Dashboard SHOULD show flakiness reports.

DR-007: Dashboard MUST show release gate decisions.

DR-008: Dashboard MUST show manifest details.

DR-009: Dashboard SHOULD show promotion history.

## 7. Non-Functional Requirements

### 7.1 Performance

NFR-001: SDK local event enqueue SHOULD be under 10 ms p95.

NFR-002: Single-event ingestion API latency SHOULD be under 100 ms p95 excluding
network latency.

NFR-003: Proxy overhead SHOULD be under 50 ms p95 excluding provider latency.

NFR-004: Batch importer MUST handle 100,000 traces without manual intervention.

NFR-005: Worker system MUST support 1,000-case replay runs with resumable
progress.

NFR-006: Recent trace queries SHOULD return under 1 second p95 with appropriate
indexes.

### 7.2 Reliability

NFR-007: Ingestion MUST be idempotent.

NFR-008: Worker jobs MUST retry transient failures.

NFR-009: Worker jobs MUST record terminal failure states after retry exhaustion.

NFR-010: Run state MUST remain consistent if a worker crashes.

NFR-011: Artifact metadata MUST not be committed unless artifact write succeeds.

NFR-012: Sidecar mode SHOULD buffer events during server downtime.

### 7.3 Scalability

NFR-013: API, worker, proxy, and collector components MUST be independently
scalable.

NFR-014: Trace storage SHOULD support project-level and time-range query
patterns.

NFR-015: Large payloads SHOULD be stored in object storage rather than only in
Postgres.

### 7.4 Portability

NFR-016: Hyoka MUST run locally through Docker Compose.

NFR-017: Hyoka SHOULD support S3-compatible object stores.

NFR-018: Hyoka SHOULD support Kubernetes deployment.

### 7.5 Maintainability

NFR-019: Canonical schemas MUST be versioned.

NFR-020: Evaluators SHOULD be plugin-like and versioned.

NFR-021: Framework adapters MUST be isolated from core replay/eval logic.

NFR-022: Database migrations MUST be managed through Alembic or equivalent.

## 8. Security and Privacy Requirements

SR-001: Hyoka MUST support API-key authentication for non-local deployments.

SR-002: API keys MUST be scoped to a project or tenant.

SR-003: Hyoka MUST support configurable secret redaction.

SR-004: Hyoka MUST support configurable PII redaction.

SR-005: Redaction MUST occur before durable persistence when enabled.

SR-006: Hyoka MUST support field-level capture controls.

SR-007: Promotion decisions MUST be audit logged.

SR-008: Gate override decisions MUST be audit logged.

SR-009: Side-effecting live tool replay MUST require explicit allowlist
configuration.

SR-010: Sandbox replay MUST enforce timeouts.

SR-011: Sandbox replay SHOULD support network allowlists.

SR-012: Stored artifacts SHOULD be encrypted at rest when the backing store
supports it.

## 9. Observability Requirements

OR-001: Hyoka MUST emit structured JSON logs.

OR-002: Logs MUST include request id, run id, case id, trace id, project id when
available, and error code when applicable.

OR-003: Hyoka MUST expose API request count, latency, and error rate metrics.

OR-004: Hyoka MUST expose ingestion throughput and normalization failure
metrics.

OR-005: Hyoka MUST expose queue depth, worker heartbeat, job duration, retry,
and failure metrics.

OR-006: Hyoka SHOULD instrument internal operations with OpenTelemetry.

OR-007: Hyoka SHOULD expose replay and eval metrics, including cases per minute,
eval failures, and average cost per run.

## 10. Data Requirements

DAR-001: All canonical traces MUST include schema version.

DAR-002: Trace steps MUST be ordered.

DAR-003: Trace steps SHOULD support parent-child relationships.

DAR-004: Large raw inputs and outputs SHOULD be stored by hash reference.

DAR-005: Metadata fields MUST support user-defined key-value pairs.

DAR-006: Eval results MUST reference evidence step ids when applicable.

DAR-007: Memory events MUST include operation type and provenance.

DAR-008: Candidate configs MUST be immutable after creation.

DAR-009: Suites MUST be immutable once used in a completed run.

DAR-010: Manifests MUST be immutable.

## 11. Testing Requirements

TR-001: Unit tests MUST cover schema validation.

TR-002: Unit tests MUST cover redaction.

TR-003: Unit tests MUST cover gate policy evaluation.

TR-004: Unit tests MUST cover hash and manifest generation.

TR-005: Integration tests MUST cover trace ingestion to persistence.

TR-006: Integration tests MUST cover run creation to worker completion.

TR-007: Integration tests MUST cover artifact write/read.

TR-008: Integration tests MUST cover mock replay safety.

TR-009: Contract tests SHOULD cover OpenAI-compatible proxy behavior.

TR-010: Contract tests SHOULD cover SDK event payloads.

TR-011: Load tests SHOULD cover batch import and proxy overhead.

TR-012: Security tests MUST verify secrets are redacted before persistence when
redaction is enabled.

## 12. Acceptance Criteria

AC-001: A developer can run Hyoka locally with one Docker Compose command.

AC-002: A developer can capture an LLM call through proxy mode without changing
agent code beyond base URL configuration.

AC-003: A developer can instrument a custom Python agent with the SDK and see
LLM, tool, retrieval, and memory events in a canonical trace.

AC-004: A developer can import a JSONL file of traces and create a suite.

AC-005: A developer can run a suite against a candidate in mock replay mode.

AC-006: A developer can run a suite against a candidate in live or hybrid replay
mode with explicit provider configuration.

AC-007: A run produces per-case eval results and aggregate metrics.

AC-008: Repeated replay identifies flaky cases when outcomes vary above policy
thresholds.

AC-009: Failed runs can be mined into failure clusters.

AC-010: Hyoka can generate or register at least one prompt improvement
candidate from a failure cluster.

AC-011: Hyoka can compare a baseline and candidate run.

AC-012: A release gate can approve or block a candidate based on pass rate,
flaky rate, latency, cost, and blocking failure labels.

AC-013: Every completed run produces a signed manifest with content hashes.

AC-014: The manifest is retrievable through CLI and API.

AC-015: A promotion decision records candidate, gate decision, manifest, actor,
and timestamp.

## 13. Out-of-Scope Requirements

OOS-001: Hyoka does not need to train model weights directly.

OOS-002: Hyoka does not need to replace agent frameworks.

OOS-003: Hyoka does not need to provide a vector database.

OOS-004: Hyoka does not need to provide full production RBAC in the first
implementation phase.

OOS-005: Hyoka must not automatically mutate production agent behavior without
an explicit promotion path.

## 14. Risks

R-001: Framework adapters may become maintenance-heavy.

Mitigation: keep adapters thin and normalize into a stable internal schema.

R-002: LLM-as-judge results may be noisy.

Mitigation: store judge configs, support repeated judging, and combine with
rule-based trajectory evals.

R-003: Live replay can trigger side effects.

Mitigation: mock default, explicit live allowlists, sandbox mode, dry-run tools.

R-004: Captured traces may contain sensitive data.

Mitigation: redaction before persistence, field capture controls, object-store
encryption, audit logs.

R-005: Candidate generation may propose unsafe changes.

Mitigation: never auto-promote, require experiment validation and release gate.

R-006: Canonical trace schema may be too rigid for complex multi-agent systems.

Mitigation: versioned schema, custom events, metadata, parent-child step graph.

## 15. Definition of Done for a Production-Quality v1

- Proxy mode, Python SDK, and batch import work end to end.
- Canonical trace schema is versioned and documented.
- Suites, candidates, runs, evals, gates, promotions, and manifests are
  implemented.
- Mock and hybrid replay are supported.
- Worker jobs are asynchronous, retryable, cancellable, and resumable at the
  case level.
- Built-in final-output, trajectory, performance, and safety evaluators exist.
- Flakiness detection exists.
- Failure mining and prompt candidate proposals exist.
- Release gates block unsafe candidates.
- Signed manifests are produced for completed runs.
- CLI supports the core workflow.
- API is documented with OpenAPI.
- Docker Compose runs the stack locally.
- Tests cover ingestion, replay, evals, gates, manifests, redaction, and worker
  recovery.

