import Link from "next/link";
import { getTrace } from "@/lib/api";

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="jsonBlock">{JSON.stringify(value, null, 2)}</pre>;
}

export default async function TraceDetailPage({ params }: { params: Promise<{ traceId: string }> }) {
  const { traceId } = await params;
  const trace = await getTrace(traceId);
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/traces">Back to traces</Link>
      <header className="topbar">
        <div>
          <h1>{trace.agent_name}</h1>
          <p><span className="mono">{trace.trace_id}</span> · {trace.environment} · {trace.summary.status}</p>
        </div>
      </header>

      <section className="metricsGrid">
        <div className="metric"><div><p>Latency</p><strong>{trace.summary.latency_ms}ms</strong></div></div>
        <div className="metric"><div><p>Tokens</p><strong>{trace.summary.tokens_total}</strong></div></div>
        <div className="metric"><div><p>Cost</p><strong>${trace.summary.cost_usd.toFixed(4)}</strong></div></div>
        <div className="metric"><div><p>Steps</p><strong>{trace.steps.length}</strong></div></div>
      </section>

      <section className="twoCol">
        <div className="panel">
          <div className="panelHead"><h2>Steps</h2><span>{trace.steps.length}</span></div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr><th>Type</th><th>Name</th><th>Status</th><th>Latency</th></tr>
              </thead>
              <tbody>
                {trace.steps.map((step, index) => (
                  <tr key={String(step.step_id || index)}>
                    <td>{step.type}</td>
                    <td>{String(step.tool_name || step.name || "step")}</td>
                    <td>{step.status}</td>
                    <td>{step.latency_ms ? `${step.latency_ms}ms` : "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panelHead"><h2>Input</h2></div>
          <JsonBlock value={trace.input} />
        </div>
      </section>

      <section className="panel">
        <div className="panelHead"><h2>Metadata</h2></div>
        <JsonBlock value={{ metadata: trace.metadata, output: trace.final_output_preview }} />
      </section>
    </main>
  );
}
