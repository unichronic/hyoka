# Hyoka 2 Research Notes

Date: 2026-05-23

## Adjacent Tools

- LangSmith focuses on tracing, datasets, evaluators, prompt/playground workflows,
  experiment comparison, and production trace reuse for eval datasets.
  Source: https://docs.langchain.com/langsmith/evaluation
- Langfuse positions itself as an LLM engineering platform across tracing,
  prompt management, evaluations, datasets, experiments, analytics, annotation,
  and self-hosting. Its self-hosted path uses Docker Compose and production data
  infrastructure such as Postgres, ClickHouse, and Redis/Valkey.
  Sources: https://langfuse.com/docs/ and https://langfuse.com/self-hosting
- Arize Phoenix is open-source and emphasizes OpenTelemetry/OpenInference,
  auto-instrumentation, tracing, evals, prompt engineering, datasets, and
  experiments across Python, TypeScript, and Java.
  Source: https://arize.com/docs/phoenix
- Braintrust centers the workflow around datasets, scorers, playground iteration,
  experiments, production monitoring, and immutable experiment snapshots.
  Source: https://www.braintrust.dev/docs/evaluate
- Helicone combines gateway-style LLM traffic capture with observability and
  prompt workflows; its prompt features use the gateway for automatic
  compilation, input tracing, and lower-latency paths.
  Source: https://docs.helicone.ai/features/advanced-usage/prompts/overview
- OpenTelemetry now has GenAI semantic conventions covering inference,
  embeddings, retrievals, tool execution, content capture, and streaming chunks.
  Source: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/

## Product Implications

Most adjacent tools converge on the same core surfaces: trace trees, prompt
management, datasets, evals, experiments, annotation, and production monitoring.
Hyoka should not compete only as another trace viewer. The differentiating loop
from the docs is worth preserving:

```text
trace -> normalize -> replay -> evaluate trajectory -> mine failures
-> generate candidates -> compare -> gate -> manifest -> promote
```

## Stack Decisions

- API and worker: FastAPI, SQLAlchemy, Pydantic, Typer, and a database-backed
  worker boundary. This matches the Python agent ecosystem and avoids adding a
  queue before replay needs durable leases, cancellation, and retries.
- Metadata store: Postgres in Docker Compose, SQLite default for single-process
  local development.
- Artifacts: content-addressed local store for single-node operation and
  S3-compatible storage for production object stores.
- Dashboard: Next.js, TypeScript, React, Lucide icons, and plain CSS. Tailwind
  and TanStack Query are not needed for the current server-rendered operational
  dashboard.
- Observability: structured JSON logs, Prometheus metrics, and OTLP/JSON
  ingestion for GenAI/OpenInference spans. Hyoka can receive OTEL exporter
  payloads without embedding the full OTEL SDK in the server runtime.
- Compatibility: OpenAI-compatible proxy, Python SDK, generic events, scrape,
  and OTLP/JSON ingestion are implemented. Framework adapters remain adoption
  accelerators.

## Explicit Non-Choices For This Slice

- **Dramatiq/Celery/Redis:** deferred. For Hyoka's long-running replay semantics,
  Temporal is likely the stronger production option than a generic task queue,
  but the first slice does not need it.
- **MinIO service dependency:** not bundled by default. Hyoka supports
  S3-compatible storage through boto3; operators can use managed S3/GCS
  compatibility, MinIO, or another compatible object store.
- **OpenTelemetry SDK:** not required in-process for the server. The implemented
  collector path accepts OTLP/JSON and maps GenAI/OpenInference attributes into
  the canonical trace schema.
- **Tailwind/TanStack Query:** deferred because they add surface area without
  improving the current dashboard.
