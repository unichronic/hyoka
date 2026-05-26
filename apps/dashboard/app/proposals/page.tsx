import Link from "next/link";
import { getImprovementProposals } from "@/lib/api";

function JsonBlock({ value }: { value: unknown }) {
  return <pre className="jsonBlock">{JSON.stringify(value, null, 2)}</pre>;
}

export default async function ProposalsPage({ searchParams }: { searchParams: Promise<{ created?: string }> }) {
  const { created } = await searchParams;
  const proposals = await getImprovementProposals();
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/">Back to operations</Link>
      <header className="topbar">
        <div>
          <h1>Improvement Proposals</h1>
          <p>Durable candidate patches generated from failure evidence.</p>
        </div>
      </header>
      {created ? <div className="notice">Created proposal <span className="mono">{created}</span>.</div> : null}
      <section className="panel">
        <div className="tableWrap">
          <table>
            <thead>
              <tr><th>Proposal</th><th>Cluster</th><th>Target</th><th>Method</th><th>Candidate</th></tr>
            </thead>
            <tbody>
              {proposals.map((proposal) => (
                <tr key={proposal.proposal_id}>
                  <td><span className="mono">{proposal.proposal_id}</span></td>
                  <td><span className="mono">{proposal.cluster_id}</span></td>
                  <td>{proposal.target}</td>
                  <td>{proposal.method}</td>
                  <td>{proposal.candidate_id ? <span className="mono">{proposal.candidate_id}</span> : "not created"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <div className="panelHead"><h2>Proposal Payloads</h2></div>
        <JsonBlock value={proposals} />
      </section>
    </main>
  );
}
