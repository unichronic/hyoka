import Link from "next/link";
import { getJson, type Trace } from "@/lib/api";

export default async function TracesPage() {
  const traces = await getJson<Trace[]>("/v1/traces?limit=100");
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/">Back to operations</Link>
      <header className="topbar">
        <div>
          <h1>Traces</h1>
          <p>Recent canonical and OTEL-normalized traces.</p>
        </div>
      </header>
      <section className="panel">
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Trace</th>
                <th>Agent</th>
                <th>Env</th>
                <th>Status</th>
                <th>Steps</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((trace) => (
                <tr key={trace.trace_id}>
                  <td><Link className="mono linkCell" href={`/traces/${trace.trace_id}`}>{trace.trace_id}</Link></td>
                  <td>{trace.agent_name}</td>
                  <td>{trace.environment}</td>
                  <td>{trace.summary.status}</td>
                  <td>{trace.steps.length}</td>
                  <td>{trace.summary.latency_ms}ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
