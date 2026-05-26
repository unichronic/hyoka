# Hyoka 2 Product Design

## 1. Product Definition

**Name:** Hyoka 2

**Category:** AI agent reliability and self-improvement infrastructure

**Positioning:** A pluggable layer that attaches to existing AI agents and
turns production traces into reproducible evals, failure clusters, improvement
candidates, experiments, release gates, and promotion decisions.

**One-line pitch:** Hyoka 2 helps teams safely improve AI agents from their own
behavior by capturing traces, evaluating trajectories, replaying candidates,
and promoting only changes that pass explicit reliability gates.

## 2. Problem

AI agents are hard to ship safely because behavior changes are difficult to
measure and reproduce. A small prompt edit, model switch, retriever tweak, tool
schema change, or memory-policy change can silently break previously working
flows.

Common production problems:

- Agent failures return successful HTTP responses.
- Logs show the final answer but not the trajectory that produced it.
- Evals judge final output but miss bad tool calls or unsafe intermediate steps.
- Failed examples are not converted into reusable regression suites.
- Teams cannot reliably compare prompt, model, retriever, tool, or memory
  changes.
- Agent behavior is flaky across repeated runs.
- Improvements are deployed manually without artifact lineage or release gates.
- Existing tools require teams to rewrite agents around a specific framework.

Hyoka 2 exists to make agent improvement measurable, reproducible, and safe.

## 3. Core Thesis

Agents should improve from their own traces, but not by mutating themselves
blindly in production.

Hyoka turns agent behavior into a controlled improvement loop:

```text
observe -> trace -> evaluate -> mine failures -> propose candidates
-> replay -> compare -> gate -> promote -> monitor
```

Hyoka does not replace agent frameworks. It wraps around them.

## 4. Target Users

### Primary Users

**Backend and infrastructure engineers**

Own agent services, queues, APIs, deployment, observability, CI, and release
processes. They care about reliability, reproducibility, latency, cost, and
operational safety.

**Applied ML engineers**

Own evals, model behavior, prompts, retrieval, memory, and improvement loops.
They care about quality metrics, failure slices, regression detection, and
candidate comparison.

**AI-native startup teams**

Ship agents quickly but need lightweight infrastructure to prevent regressions
as products become more complex.

### Secondary Users

**Research engineers**

Need trajectory datasets, replay infrastructure, reward signals, and controlled
experiments for self-improving agents.

**Forward-deployed engineers**

Deploy customer-specific agents and need a reliable way to diagnose failures,
generate customer-specific improvements, and prove release safety.

## 5. Product Principles

1. **Attach, do not rewrite.** Hyoka should work with existing agent stacks.
2. **Trace the trajectory.** Capture model calls, tool calls, retrieval, memory,
   latency, cost, errors, and environment metadata.
3. **Evaluate behavior, not just answers.** Tool usage, memory operations, and
   final state matter.
4. **Self-improvement must be gated.** Hyoka can propose changes, but promotion
   requires replay, evals, and explicit release policies.
5. **Every result must be reproducible.** Store hashes, manifests, versions,
   configs, datasets, artifacts, and promotion records.
6. **Work in real systems.** Support SDK, proxy, sidecar, OpenTelemetry, batch
   import, framework adapters, and CI.
7. **Make failure useful.** Failed traces should become regression cases,
   failure slices, candidate prompts, memory edits, and training exports.

## 6. Main User Promise

A team using Hyoka should be able to answer:

- What did the agent do?
- Which step caused failure?
- Has the new candidate improved behavior?
- Did the improvement introduce latency, cost, safety, or flakiness regressions?
- Which traces, prompts, model configs, tools, memories, and eval configs were
  used to make the decision?
- Can this candidate be safely promoted?

## 7. Product Surfaces

Hyoka has five primary surfaces.

### CLI

The CLI is the default developer workflow for local use and CI.

Example commands:

```bash
hyoka doctor
hyoka proxy start
hyoka import traces.jsonl --suite support-v1
hyoka suite create support-v1
hyoka run --suite support-v1 --candidate prompt-v3 --mode hybrid
hyoka failures mine --suite support-v1
hyoka propose --target prompt --from-failures
hyoka experiment run --candidate prompt-v3
hyoka compare baseline-run candidate-run
hyoka gate --policy release.yaml --run candidate-run
hyoka promote --candidate prompt-v3 --gate release.yaml
hyoka manifest --run candidate-run
hyoka export training-data --format dpo
```

### API

The API powers programmatic integration, dashboard, CI, and internal platform
workflows.

Primary resource groups:

- traces
- suites
- candidates
- runs
- evals
- failures
- proposals
- experiments
- gates
- promotions
- manifests
- exports

### SDKs

SDKs provide low-overhead instrumentation for Python and JavaScript/TypeScript
agent services.

### Proxy and Sidecar

The proxy captures LLM traffic with minimal changes. The sidecar supports
containerized production deployments with buffering, retries, and local
collection.

### Dashboard

The dashboard is an operational interface for trace inspection, eval results,
failure clusters, experiment comparison, flakiness reports, release gates, and
promotion history.

## 8. Integration Modes

Hyoka supports seven integration modes.

### 8.1 Proxy Mode

Lowest-friction mode for agents using OpenAI-compatible APIs.

```bash
export OPENAI_BASE_URL=http://localhost:8686/v1
export OPENAI_API_KEY=...
```

Flow:

```text
Agent App -> Hyoka Proxy -> OpenAI/Anthropic/Ollama/vLLM
```

Captures:

- provider
- model
- request parameters
- messages
- response
- streaming chunks
- latency
- token usage
- estimated cost
- errors

Limitations:

- Cannot fully capture internal tool calls unless tools are also wrapped or
  instrumented.
- Cannot infer high-level agent state without SDK, adapter, or OTEL events.

### 8.2 SDK Mode

For custom Python and TypeScript agents.

Python example:

```python
from hyoka import trace, tool, memory_event, observe_openai

observe_openai()

@tool
def lookup_order(order_id: str) -> dict:
    return {"status": "delivered"}

@trace(agent="refund-agent", suite="support-v1")
async def run_agent(message: str):
    ...
```

Captures:

- LLM calls
- tool calls
- memory reads/writes
- retrieval events
- exceptions
- custom metadata
- agent/session/run identifiers

### 8.3 Framework Adapter Mode

Native hooks for popular frameworks.

Initial adapter targets:

- LangChain
- LangGraph
- LlamaIndex
- CrewAI
- AutoGen
- OpenAI Agents SDK
- Vercel AI SDK
- Semantic Kernel
- PydanticAI

Example:

```python
from hyoka.integrations.langchain import HyokaCallbackHandler

result = agent.invoke(
    {"input": user_message},
    config={"callbacks": [HyokaCallbackHandler(agent="refund-agent")]}
)
```

### 8.4 OpenTelemetry Mode

Hyoka accepts OTEL spans and maps them to canonical agent traces.

Flow:

```text
Agent App -> OpenTelemetry SDK -> Hyoka Collector -> Trace Normalizer
```

Useful for teams that already instrument services with distributed tracing.

### 8.5 Sidecar Mode

Hyoka runs as a deployment companion.

Flow:

```text
agent-container
hyoka-sidecar
```

Responsibilities:

- capture local proxy traffic
- receive SDK events
- buffer traces when server is unavailable
- retry uploads
- redact secrets
- export local health metrics

### 8.6 Batch Import Mode

For teams with existing logs or exports.

Supported import formats:

- Hyoka JSONL
- OpenAI-style request logs
- LangSmith-style traces
- OpenTelemetry span JSON
- custom mapped JSON

### 8.7 CI/CD Mode

Runs agent regression suites before deployment.

Example GitHub Actions step:

```yaml
- name: Run Hyoka release gate
  run: hyoka gate --suite support-v1 --candidate candidate.yaml --policy release.yaml
```

## 9. Core Concepts

### Trace

A structured record of one agent execution, including user input, intermediate
steps, model calls, tool calls, retrieval, memory events, final output, timing,
cost, errors, and environment metadata.

### Suite

A versioned set of trace cases used for replay and regression testing.

### Candidate

A proposed agent configuration to evaluate. A candidate may include prompt
changes, model changes, retriever settings, memory policy, tool schemas, routing
policy, or retry/fallback rules.

### Run

Execution of a suite against a candidate in a replay mode.

### Eval

A scoring or verification function applied to final outputs, intermediate
trajectory, state changes, latency, cost, safety, or flakiness.

### Failure Cluster

A group of failed traces that share a likely root cause.

### Proposal

A candidate improvement generated from failed traces, manually authored, or
imported from code/config.

### Experiment

A comparison of one or more candidates against a baseline over one or more
suites.

### Gate

A release policy that decides whether a candidate can be promoted.

### Promotion

The act of marking a candidate as the approved configuration for an environment.

### Manifest

A content-addressed, signed artifact that records what was tested, with which
configs, datasets, evals, results, and versions.

## 10. Self-Improvement System

Hyoka's self-improvement system improves the agent's surrounding configuration
by default, not the base model weights.

Supported improvement targets:

- prompt instructions
- tool descriptions
- tool schemas
- retrieval configuration
- memory policy
- model routing policy
- retry and fallback policy
- human-review policy
- training-data exports

Pipeline:

```text
Trace Store
-> Eval Engine
-> Failure Miner
-> Slice Builder
-> Candidate Generator
-> Experiment Runner
-> Replay/Eval
-> Policy Selector
-> Promotion Gate
-> Config Registry
```

### 10.1 Failure Miner

Identifies patterns in failed traces.

Failure categories:

- wrong tool selected
- invalid tool arguments
- required tool missing
- repeated useless tool call
- hallucinated fact
- unsafe action
- stale memory
- bad memory write
- retrieval miss
- irrelevant retrieval context
- latency regression
- cost regression
- flaky behavior
- final-state mismatch

Outputs:

- failure clusters
- representative traces
- root-cause hypotheses
- affected slices
- recommended improvement targets

### 10.2 Slice Builder

Converts failure clusters into reusable regression slices.

Example slices:

- `refund_without_delivery_check`
- `stale_customer_memory`
- `irrelevant_retrieval_context`
- `invalid_tool_argument_order_id`
- `cheap_model_failed_policy_reasoning`

### 10.3 Candidate Generator

Creates candidate changes from failure slices.

Candidate sources:

- LLM-assisted generation
- deterministic rule-based templates
- human-authored config
- Git branch/config import

Example candidates:

```text
prompt_patch_v3
retriever_top_k_8
strict_tool_schema_v2
memory_policy_no_stale_writes
router_hard_cases_to_large_model
fallback_after_tool_parse_error
```

### 10.4 Experiment Runner

Runs candidates against:

- failed traces
- held-out successful traces
- adversarial cases
- full regression suites
- repeated flaky runs

### 10.5 Policy Selector

Ranks candidates using weighted objectives:

- pass rate
- trajectory score
- safety violations
- flaky rate
- p95 latency
- cost
- token usage
- regression count

### 10.6 Promotion Gate

Promotion requires a policy decision, not just a score improvement.

Example:

```yaml
suite: support-v1
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

## 11. Replay Modes

### Mock Replay

Replays recorded model and tool outputs exactly.

Use cases:

- deterministic regression tests
- parser and state-machine validation
- tool orchestration validation
- evaluator debugging

### Live Replay

Re-executes model and tool calls.

Use cases:

- real quality measurement
- latency/cost measurement
- nondeterminism detection
- final pre-release validation

### Hybrid Replay

Live model calls with mocked external tools, or mocked model calls with live
local tool execution.

Use cases:

- practical pre-release testing
- cost control
- safe evaluation without side effects

### Sandbox Replay

Runs side-effecting tools in isolated environments.

Use cases:

- code agents
- browser agents
- database agents
- terminal agents
- workflows with external state

## 12. Evaluation System

### Final-Output Evals

- exact match
- regex checks
- JSON schema validation
- semantic similarity
- LLM-as-judge
- human review

### Trajectory Evals

- required tool called
- forbidden tool not called
- tool arguments valid
- tool response handled correctly
- no repeated useless tool calls
- memory operation valid
- retrieval context relevant
- correct final state reached

### Reliability Evals

- pass rate
- pass@k
- flaky rate
- output variance
- judge variance
- latency variance
- cost variance
- timeout rate

### Safety Evals

- unsafe tool call
- secret leakage
- PII leakage
- policy violation
- irreversible action without confirmation
- hallucinated authority

## 13. Dashboard Design

The dashboard is operational and diagnostic.

Primary views:

- **Traces:** searchable trace list with filters by agent, suite, status,
  environment, model, tool, failure type, and cost.
- **Trace Timeline:** chronological LLM calls, tools, retrieval, memory events,
  outputs, errors, and timings.
- **Eval Runs:** run status, suite coverage, pass rate, failures, p95 latency,
  cost, and artifacts.
- **Failure Clusters:** grouped failures, representative traces, root-cause
  hypotheses, suggested candidates.
- **Experiments:** baseline vs candidate comparisons and objective tradeoffs.
- **Flakiness:** repeated-run variance and unstable cases.
- **Release Gates:** decision, blocking reasons, policy, and required artifacts.
- **Promotions:** history of approved configs and rollback points.
- **Manifests:** signed artifact lineage for each run.

## 14. Key User Journeys

### Journey 1: Attach Hyoka to an Existing Agent

1. User starts Hyoka locally.
2. User configures OpenAI-compatible base URL or installs SDK callback.
3. Agent runs normally.
4. Hyoka captures traces.
5. User verifies trace capture in CLI or dashboard.

Success: traces appear without rewriting the agent.

### Journey 2: Turn Production Failures Into a Regression Suite

1. User filters failed traces from production.
2. Hyoka mines failure clusters.
3. User approves slices for a new suite.
4. Hyoka creates a versioned regression suite.

Success: failures become reusable eval cases.

### Journey 3: Improve a Prompt Safely

1. Hyoka identifies a prompt-related failure cluster.
2. Hyoka proposes candidate prompt patches.
3. User runs candidates against failed and held-out traces.
4. Hyoka compares quality, latency, cost, and flaky rate.
5. Release gate approves or blocks promotion.

Success: prompt improvement ships only if it passes policy.

### Journey 4: Validate Memory Policy

1. Agent writes memory during sessions.
2. Hyoka captures memory events with provenance.
3. Hyoka detects stale or harmful memories.
4. Candidate memory policy changes are replayed.
5. Gate blocks policies that improve short-term scores but harm held-out cases.

Success: memory becomes measurable and reversible.

### Journey 5: CI Release Gate

1. Developer opens a PR changing prompt/model/tool config.
2. CI runs Hyoka regression suite.
3. Hyoka blocks deploy if required thresholds fail.
4. Manifest is attached to CI artifact.

Success: unsafe agent changes are stopped before production.

## 15. Success Metrics

Product success:

- Time to first trace under 10 minutes for proxy mode.
- Time to first regression suite under 30 minutes from imported traces.
- At least 90% of common agent steps represented in canonical schema.
- Release gate output is understandable without reading raw logs.
- Users can reproduce a run from its manifest.

Technical success:

- Import 100,000 traces through batch importer.
- Run 1,000 replay cases asynchronously with resumable progress.
- Support repeated runs for flakiness detection.
- Keep ingestion overhead under 50 ms p95 in SDK mode for non-streaming events.
- Persist all run artifacts with content hashes.

## 16. Non-Goals

Hyoka 2 is not:

- a complete agent framework
- a generic chatbot builder
- a full observability platform replacement
- a model training platform
- a vector database
- a hosted-only SaaS
- an automatic production self-modification system

## 17. Competitive Differentiation

Hyoka is distinct because it combines:

- low-friction attachment to existing agents
- canonical trace normalization
- deterministic replay
- trajectory-level evals
- failure mining
- candidate generation
- self-improvement experiments
- flakiness detection
- signed artifact lineage
- release gates

Most tools cover tracing, evals, or observability separately. Hyoka connects
them into a safe improvement loop.

## 18. Roadmap

### Phase 1: Core Reliability Layer

- proxy mode
- Python SDK
- trace ingestion
- canonical trace schema
- suites
- replay engine
- eval engine
- CLI
- local Docker deployment

### Phase 2: Release Infrastructure

- async worker pool
- content-addressed artifacts
- signed manifests
- release gate policies
- CI integration
- flakiness detection
- dashboard basics

### Phase 3: Self-Improvement

- failure mining
- slice builder
- candidate generator
- experiment runner
- policy selector
- promotion registry
- training-data export

### Phase 4: Production Integrations

- JS/TS SDK
- framework adapters
- OpenTelemetry collector
- sidecar mode
- Kubernetes deployment
- RBAC and tenant isolation

### Phase 5: Advanced Agent Domains

- sandboxed tool replay
- browser-agent support
- terminal-agent support
- database-state verification
- memory-policy optimization
- model-routing optimization

## 19. Open Product Questions

- Should Hyoka initially optimize for local/open-source deployment or hosted
  team workflows?
- Should candidate generation be enabled by default or require explicit user
  approval?
- How opinionated should the canonical trace schema be for framework-specific
  agent concepts?
- Should Hyoka provide built-in LLM judges or require users to define their own?
- What is the minimum useful dashboard before CLI/API workflows are complete?

