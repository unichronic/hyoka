# Hyoka Integration Contract

Hyoka should integrate like infrastructure, not like an agent framework. The
model is similar to Prometheus:

- a stable wire format
- lightweight client libraries as optional convenience
- push ingestion for short-lived jobs and serverless workloads
- pull/scrape ingestion for long-running services
- labels for service, environment, version, region, tenant, and agent identity
- no requirement to use a specific model provider, queue, web framework, or
  agent library

## Push Integration

Any service can push generic events:

```bash
curl -X POST http://localhost:8686/v1/events/batch \
  -H "content-type: application/json" \
  -H "X-Hyoka-Api-Key: $HYOKA_API_KEY" \
  -d @examples/generic-service/hyoka-events.json
```

Each event uses this envelope:

```json
{
  "event_id": "evt_lookup_order",
  "trace_id": "tr_123",
  "type": "tool_call",
  "source": "custom-service",
  "service_name": "checkout-api",
  "agent_name": "refund-agent",
  "environment": "prod",
  "name": "lookup_order",
  "duration_ms": 42,
  "input": {"order_id": "A123"},
  "output": {"status": "delivered"},
  "attributes": {"tool_name": "lookup_order"},
  "labels": {
    "service": "checkout-api",
    "version": "2026.05.23",
    "region": "us-east-1"
  }
}
```

Supported event types:

```text
trace_start
trace_end
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

Hyoka normalizes these events into canonical traces. Event IDs are idempotent, so
retries do not duplicate steps.

## Pull/Scrape Integration

A service can expose a `GET /hyoka/traces` endpoint with either:

- `application/json` Hyoka exposition
- `application/x-ndjson` where each line is a canonical trace or event

Example exposition:

```json
{
  "schema_version": "hyoka.exposition.v1",
  "labels": {"service": "checkout-api"},
  "events": [
    {
      "event_id": "evt_start",
      "trace_id": "tr_123",
      "type": "trace_start",
      "agent_name": "refund-agent",
      "input": {"role": "user", "content": "Refund order A123"}
    }
  ]
}
```

Scrape it:

```bash
uv run hyoka scrape http://localhost:9108/hyoka/traces --suite support-v1
```

This is the Prometheus-style path: instrumented services expose a simple
endpoint, and Hyoka pulls the data without needing to link against the service's
runtime.

## Canonical Trace Integration

If an application can already assemble a full trace, it can push the canonical
schema directly:

```bash
curl -X POST http://localhost:8686/v1/traces \
  -H "content-type: application/json" \
  -H "X-Hyoka-Api-Key: $HYOKA_API_KEY" \
  -d @trace.json
```

Batch import is available at `POST /v1/traces/batch`.

## OpenTelemetry Integration

Hyoka accepts OTLP/HTTP JSON trace exports at:

```bash
curl -X POST http://localhost:8686/v1/otel/v1/traces \
  -H "content-type: application/json" \
  -H "X-Hyoka-Api-Key: $HYOKA_API_KEY" \
  -d @otlp-traces.json
```

The collector path maps OpenTelemetry GenAI spans and OpenInference-style spans
into Hyoka events. It recognizes common attributes including:

- `gen_ai.operation.name`
- `gen_ai.provider.name`
- `gen_ai.request.model`
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `openinference.span.kind`
- `input.value`
- `output.value`
- `tool.name`

Resource attributes such as `service.name`, `deployment.environment.name`,
`service.version`, and `cloud.region` become low-cardinality Hyoka labels.

## OpenAI-Compatible Proxy

For LLM clients that support `OPENAI_BASE_URL`, point traffic at the Hyoka proxy:

```bash
export OPENAI_BASE_URL=http://localhost:8687/v1
export OPENAI_API_KEY=...
export HYOKA_API_KEY=...
```

Proxy mode is useful for low-friction LLM capture. It cannot infer internal
agent state, tool calls, retrieval, or memory unless those are also emitted as
events or canonical traces.

## Python SDK

The SDK is optional convenience. It should never be the only integration path.
Use it when Python decorators or direct event emitters are acceptable; use
events, scrape, or proxy when they are not.

```python
from hyoka import emit_event, flush, tool, trace

@trace(agent="refund-agent")
def handle_refund(request):
    emit_event("router_decision", name="refund-flow", labels={"service": "support"})
    return issue_refund(request)

flush()
```

## Replay Callback Integration

For live, hybrid, or sandbox replay, Hyoka calls an HTTP endpoint owned by the
agent runtime. This keeps Hyoka framework-neutral while allowing any agent
architecture to implement its own execution.

Candidate config:

```yaml
name: refund-live
targets: ["prompt"]
config:
  replay:
    url: "https://agent-runtime.internal/hyoka/replay"
    method: "POST"
```

Worker safety settings:

```bash
export HYOKA_ENABLE_HTTP_REPLAY=true
export HYOKA_HTTP_REPLAY_ALLOWED_HOSTS=agent-runtime.internal,evals.internal
```

The replay endpoint receives the source trace input, source steps, candidate
config, mode, and attempt number. It should return JSON with one of
`final_output`, `output`, `response`, `content`, or `text`.

## Autonomous Self-Improvement

Once a baseline run is completed, Hyoka can run the full improvement loop:

```bash
curl -X POST http://localhost:8686/v1/self-improvement/cycles \
  -H "content-type: application/json" \
  -H "X-Hyoka-Api-Key: $HYOKA_API_KEY" \
  -d '{
    "run_id": "run_...",
    "target": "prompt",
    "execute_inline": false,
    "execute_validation": true,
    "promote_on_approval": false,
    "gate_policy": {
      "min_pass_rate": 0.95,
      "max_flaky_rate": 0,
      "required_artifacts": ["manifest"]
    }
  }'
```

The cycle mines failure clusters, generates evidence-hashed candidate patches,
creates patch bundle artifacts, materializes candidates, launches validation
runs, compares against the baseline, evaluates a release gate, and can record a
promotion when `promote_on_approval=true`.

For production use, run `hyoka-worker serve` and set `execute_inline=false`.
The cycle is persisted as `queued`, claimed by the worker with a lease, retried
under bounded attempts, and completed independently of the API request. Inline
execution remains available for small local smoke tests.

Patch bundles use the `hyoka.patch.v1` envelope and include adapter renderings
for generic JSON, LangGraph, CrewAI, AutoGen, LlamaIndex, and the OpenAI Agents
SDK. Agent runtimes consume the candidate config through the replay callback;
the adapter-specific files are the portable handoff for applying approved
changes inside a project.

## Evaluator Registry

Candidates can configure evaluators through legacy top-level keys or through
`config.evaluators`.

```yaml
config:
  evaluators:
    - type: json_schema
      target: final_output
      schema:
        type: object
        required: ["answer"]
    - type: llm_judge
      url: "https://eval-runtime.internal/judge"
      model: "judge-model"
      rubric: "Score factuality and policy compliance."
```

Available evaluator names are exposed at:

```bash
curl -H "X-Hyoka-Api-Key: $HYOKA_API_KEY" http://localhost:8686/v1/evaluators
```

## Labels

Labels should be low-cardinality identifiers used for slicing and filtering:

- `service`
- `agent`
- `environment`
- `version`
- `region`
- `tenant`
- `team`

High-cardinality values such as request bodies, user messages, and raw documents
belong in event input/output or attributes, not labels.

## Discovery

The server exposes the machine-readable integration surface at:

```bash
curl http://localhost:8686/v1/integrations/spec
```
