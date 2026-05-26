import Link from "next/link";
import { proposeImprovementAction } from "@/app/actions";
import { getFailureClusters, getImprovementProposals, getManifest, getRun, getRunCases } from "@/lib/api";

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="jsonBlock">{JSON.stringify(value, null, 2)}</pre>;
}

export default async function RunDetailPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  const [run, cases, clusters, proposals, manifestResult] = await Promise.all([
    getRun(runId),
    getRunCases(runId),
    getFailureClusters(runId),
    getImprovementProposals(runId),
    getManifest(runId).catch(() => null)
  ]);
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/">Back to operations</Link>
      <header className="topbar">
        <div>
          <h1>Run Detail</h1>
          <p><span className="mono">{run.run_id}</span> · {run.status} · {run.mode}</p>
        </div>
      </header>

      <section className="metricsGrid">
        <div className="metric"><div><p>Cases</p><strong>{run.aggregate.case_count ?? 0}</strong></div></div>
        <div className="metric"><div><p>Pass Rate</p><strong>{Math.round((run.aggregate.pass_rate ?? 0) * 100)}%</strong></div></div>
        <div className="metric"><div><p>Flaky Rate</p><strong>{Math.round((run.aggregate.flaky_rate ?? 0) * 100)}%</strong></div></div>
        <div className="metric"><div><p>P95</p><strong>{run.aggregate.p95_latency_ms ?? 0}ms</strong></div></div>
      </section>

      <section className="panel">
        <div className="panelHead"><h2>Cases</h2><span>{cases.length}</span></div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Case</th><th>Trace</th><th>Status</th><th>Pass</th><th>Labels</th></tr>
            </thead>
            <tbody>
              {cases.map((caseRecord) => {
                const labels = caseRecord.eval_results.flatMap((result) => Array.isArray(result.labels) ? result.labels : []);
                return (
                  <tr key={caseRecord.case_id}>
                    <td><span className="mono">{caseRecord.case_id}</span></td>
                    <td><Link className="mono linkCell" href={`/traces/${caseRecord.trace_id}`}>{caseRecord.trace_id}</Link></td>
                    <td>{caseRecord.status}</td>
                    <td>{String(caseRecord.metrics.pass_rate ?? "n/a")}</td>
                    <td>{labels.join(", ") || "none"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="twoCol">
        <div className="panel">
          <div className="panelHead"><h2>Failure Clusters</h2><span>{clusters.length}</span></div>
          <div className="gateList">
            {clusters.length ? clusters.map((cluster) => (
              <article className="gateItem" key={cluster.cluster_id}>
                <div>
                  <div className="gateTitle"><strong>{cluster.name}</strong><span className="mono">{cluster.cluster_id}</span></div>
                  <p>{cluster.hypothesis}</p>
                </div>
                <form className="formGrid" action={proposeImprovementAction}>
                  <input type="hidden" name="cluster_id" value={cluster.cluster_id} />
                  <label>Target<select name="target" defaultValue={cluster.suggested_targets[0] || "prompt"}>{cluster.suggested_targets.map((target) => <option key={target}>{target}</option>)}</select></label>
                  <label><span>Create candidate</span><input type="checkbox" name="create_candidate" defaultChecked /></label>
                  <button className="button" type="submit">Generate Proposal</button>
                </form>
              </article>
            )) : <p className="empty">No failure clusters mined yet.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panelHead"><h2>Manifest</h2></div>
          <JsonBlock value={manifestResult ?? { status: "not_ready" }} />
        </div>
      </section>

      <section className="panel">
        <div className="panelHead"><h2>Improvement Proposals</h2><span>{proposals.length}</span></div>
        <JsonBlock value={proposals} />
      </section>
    </main>
  );
}
