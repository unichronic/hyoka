import {
  Activity,
  Braces,
  CheckCircle2,
  Database,
  FlaskConical,
  GitBranch,
  ShieldCheck,
  Timer,
  TriangleAlert
} from "lucide-react";
import Link from "next/link";
import { getDashboardData, type GateDecision, type Run, type Trace } from "@/lib/api";

function percent(value?: number) {
  if (value === undefined || Number.isNaN(value)) return "0%";
  return `${Math.round(value * 100)}%`;
}

function money(value?: number) {
  return `$${(value ?? 0).toFixed(4)}`;
}

function StatusPill({ status }: { status: string }) {
  const tone = status === "completed" || status === "ok" || status === "approved" ? "good" : status === "blocked" || status === "failed" || status === "error" ? "bad" : "warn";
  return <span className={`status ${tone}`}>{status}</span>;
}

function Metric({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof Activity }) {
  return (
    <div className="metric">
      <div className="metricIcon">
        <Icon size={18} strokeWidth={2} />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function TraceRow({ trace }: { trace: Trace }) {
  return (
    <tr>
      <td>
        <Link className="mono linkCell" href={`/traces/${trace.trace_id}`}>{trace.trace_id}</Link>
      </td>
      <td>{trace.agent_name}</td>
      <td>{trace.environment}</td>
      <td>
        <StatusPill status={trace.summary.status} />
      </td>
      <td>{trace.steps.length}</td>
      <td>{trace.summary.latency_ms}ms</td>
      <td className="clip">{trace.final_output_preview || "No final output"}</td>
    </tr>
  );
}

function RunRow({ run }: { run: Run }) {
  return (
    <tr>
      <td>
        <Link className="mono linkCell" href={`/runs/${run.run_id}`}>{run.run_id}</Link>
      </td>
      <td>
        <StatusPill status={run.status} />
      </td>
      <td>{run.mode}</td>
      <td>{run.aggregate.case_count ?? 0}</td>
      <td>{percent(run.aggregate.pass_rate)}</td>
      <td>{percent(run.aggregate.flaky_rate)}</td>
      <td>{run.aggregate.p95_latency_ms ?? 0}ms</td>
      <td>{run.manifest_id ? <span className="mono">{run.manifest_id}</span> : "pending"}</td>
    </tr>
  );
}

function GateItem({ gate }: { gate: GateDecision }) {
  return (
    <article className="gateItem">
      <div>
        <div className="gateTitle">
          <StatusPill status={gate.decision} />
          <span className="mono">{gate.run_id}</span>
        </div>
        <p>{gate.blocking_reasons.length ? gate.blocking_reasons.join("; ") : "No blocking reasons"}</p>
      </div>
      <div className="gateStats">
        <span>{percent(gate.pass_rate)} pass</span>
        <span>{percent(gate.flaky_rate)} flaky</span>
      </div>
    </article>
  );
}

export default async function DashboardPage() {
  const { summary, traces, runs, gates } = await getDashboardData();
  const latestRun = summary.latest_run;

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="mark">
            <ShieldCheck size={22} />
          </div>
          <div>
            <strong>Hyoka</strong>
            <span>Reliability control plane</span>
          </div>
        </div>
        <nav>
          <Link className="active" href="/">
            <Activity size={17} /> Operations
          </Link>
          <Link href="/traces">
            <Database size={17} /> Traces
          </Link>
          <Link href="/proposals">
            <FlaskConical size={17} /> Experiments
          </Link>
          <Link href="/self-improvement">
            <CheckCircle2 size={17} /> Self-Improve
          </Link>
          <Link href="/gates">
            <GitBranch size={17} /> Gates
          </Link>
          <Link href="/api-keys">
            <Braces size={17} /> Manifests
          </Link>
        </nav>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <h1>Agent Reliability</h1>
            <p>Trace capture, replay results, release gates, and manifest lineage.</p>
          </div>
          <div className="topStatus">
            <Timer size={17} />
            <span>Live API</span>
          </div>
        </header>

        <section className="metricsGrid">
          <Metric label="Traces" value={summary.traces} icon={Database} />
          <Metric label="Suites" value={summary.suites} icon={Braces} />
          <Metric label="Candidates" value={summary.candidates} icon={GitBranch} />
          <Metric label="Runs" value={summary.runs} icon={FlaskConical} />
          <Metric label="Latest Pass Rate" value={percent(latestRun?.aggregate.pass_rate)} icon={CheckCircle2} />
          <Metric label="Latest Cost" value={money(latestRun?.aggregate.total_cost_usd)} icon={Activity} />
        </section>

        <section className="split">
          <div className="panel">
            <div className="panelHead">
              <h2>Recent Traces</h2>
              <span>{traces.length} shown</span>
            </div>
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
                    <th>Output</th>
                  </tr>
                </thead>
                <tbody>
                  {traces.map((trace) => (
                    <TraceRow trace={trace} key={trace.trace_id} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel narrow">
            <div className="panelHead">
              <h2>Release Gates</h2>
              <TriangleAlert size={18} />
            </div>
            <div className="gateList">
              {gates.length ? gates.map((gate) => <GateItem gate={gate} key={gate.decision_id} />) : <p className="empty">No gate decisions yet.</p>}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panelHead">
            <h2>Runs</h2>
            <span>{runs.length} shown</span>
          </div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Mode</th>
                  <th>Cases</th>
                  <th>Pass</th>
                  <th>Flaky</th>
                  <th>P95</th>
                  <th>Manifest</th>
                </tr>
              </thead>
              <tbody>{runs.map((run) => <RunRow run={run} key={run.run_id} />)}</tbody>
            </table>
          </div>
        </section>
      </section>
    </main>
  );
}
