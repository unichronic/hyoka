import Link from "next/link";
import { createSelfImprovementCycleAction } from "@/app/actions";
import { getRuns, getSelfImprovementCycles } from "@/lib/api";

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="jsonBlock">{JSON.stringify(value, null, 2)}</pre>;
}

function StatusPill({ status }: { status: string }) {
  const tone = status === "completed" || status === "approved" ? "good" : status === "failed" || status === "blocked" ? "bad" : "warn";
  return <span className={`status ${tone}`}>{status}</span>;
}

export default async function SelfImprovementPage({ searchParams }: { searchParams: Promise<{ created?: string }> }) {
  const { created } = await searchParams;
  const [runs, cycles] = await Promise.all([getRuns(), getSelfImprovementCycles()]);
  const completedRuns = runs.filter((run) => run.status === "completed");
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/">Back to operations</Link>
      <header className="topbar">
        <div>
          <h1>Self-Improvement</h1>
          <p>Autonomous failure mining, patch generation, validation runs, gates, and promotion records.</p>
        </div>
      </header>
      {created ? <div className="notice">Started cycle <span className="mono">{created}</span>.</div> : null}

      <section className="panel">
        <div className="panelHead"><h2>Start Cycle</h2></div>
        <form action={createSelfImprovementCycleAction} className="formGrid">
          <label>
            Baseline run
            <select name="run_id" required>
              {completedRuns.map((run) => (
                <option key={run.run_id} value={run.run_id}>{run.run_id} · {Math.round((run.aggregate.pass_rate ?? 0) * 100)}% pass</option>
              ))}
            </select>
          </label>
          <label>
            Target
            <select name="target" defaultValue="prompt">
              <option value="prompt">prompt</option>
              <option value="tool_policy">tool_policy</option>
              <option value="output_contract">output_contract</option>
              <option value="runtime_policy">runtime_policy</option>
              <option value="replay_policy">replay_policy</option>
            </select>
          </label>
          <label>
            Max candidates
            <input name="max_candidates" type="number" min="1" max="10" defaultValue="3" />
          </label>
          <label>
            Gate policy JSON
            <textarea name="gate_policy" rows={5} defaultValue={JSON.stringify({ min_pass_rate: 0.95, max_flaky_rate: 0, required_artifacts: ["manifest"] }, null, 2)} />
          </label>
          <label className="checkLine">
            <input name="promote_on_approval" type="checkbox" />
            Promote approved candidate to staging
          </label>
          <label className="checkLine">
            <input name="execute_inline" type="checkbox" />
            Execute inline instead of worker queue
          </label>
          <button type="submit">Run self-improvement</button>
        </form>
      </section>

      <section className="panel">
        <div className="panelHead"><h2>Cycles</h2><span>{cycles.length} shown</span></div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Cycle</th><th>Status</th><th>Baseline</th><th>Decision</th><th>Best Candidate</th><th>Completed</th></tr>
            </thead>
            <tbody>
              {cycles.map((cycle) => (
                <tr key={cycle.cycle_id}>
                  <td><span className="mono">{cycle.cycle_id}</span></td>
                  <td><StatusPill status={cycle.status} /></td>
                  <td><Link className="mono linkCell" href={`/runs/${cycle.baseline_run_id}`}>{cycle.baseline_run_id}</Link></td>
                  <td>{String(cycle.result?.decision || "pending")}</td>
                  <td><span className="mono">{String(cycle.result?.best_candidate_id || "")}</span></td>
                  <td>{cycle.completed_at ? new Date(cycle.completed_at).toLocaleString() : "running"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panelHead"><h2>Cycle Payloads</h2></div>
        <JsonBlock value={cycles} />
      </section>
    </main>
  );
}
