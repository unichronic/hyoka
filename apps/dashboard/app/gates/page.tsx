import Link from "next/link";
import { evaluateGateAction } from "@/app/actions";
import { getRuns } from "@/lib/api";

const defaultPolicy = {
  min_pass_rate: 0.95,
  max_flaky_rate: 0,
  block_on: ["missing_required_tool", "unsafe_tool_call"],
  required_artifacts: ["manifest"]
};

export default async function GatesPage() {
  const runs = await getRuns();
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/">Back to operations</Link>
      <header className="topbar">
        <div>
          <h1>Gate Editor</h1>
          <p>Create release gate decisions from explicit policy JSON.</p>
        </div>
      </header>
      <section className="twoCol">
        <div className="panel">
          <div className="panelHead"><h2>Evaluate Gate</h2></div>
          <form className="formGrid" action={evaluateGateAction}>
            <label>Name<input name="name" defaultValue="dashboard-release-gate" /></label>
            <label>Run<select name="run_id" required>{runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id} · {run.status}</option>)}</select></label>
            <label>Policy JSON<textarea name="policy" defaultValue={JSON.stringify(defaultPolicy, null, 2)} /></label>
            <button className="button" type="submit">Evaluate Gate</button>
          </form>
        </div>
        <div className="panel">
          <div className="panelHead"><h2>Recent Runs</h2></div>
          <div className="tableWrap">
            <table>
              <thead><tr><th>Run</th><th>Status</th><th>Pass</th></tr></thead>
              <tbody>
                {runs.slice(0, 12).map((run) => (
                  <tr key={run.run_id}>
                    <td><Link className="mono linkCell" href={`/runs/${run.run_id}`}>{run.run_id}</Link></td>
                    <td>{run.status}</td>
                    <td>{Math.round((run.aggregate.pass_rate ?? 0) * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}
