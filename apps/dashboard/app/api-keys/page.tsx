import Link from "next/link";
import { createApiKeyAction } from "@/app/actions";
import { getApiKeys } from "@/lib/api";

export default async function ApiKeysPage({ searchParams }: { searchParams: Promise<{ created?: string; secret?: string }> }) {
  const [{ created, secret }, keys] = await Promise.all([searchParams, getApiKeys()]);
  return (
    <main className="detailShell stack">
      <Link className="crumb" href="/">Back to operations</Link>
      <header className="topbar">
        <div>
          <h1>API Keys</h1>
          <p>Scoped ingestion and automation credentials.</p>
        </div>
      </header>
      {secret ? <div className="notice">Created <span className="mono">{created}</span>. Secret shown once: <span className="mono">{secret}</span></div> : null}
      <section className="twoCol">
        <div className="panel">
          <div className="panelHead"><h2>Keys</h2><span>{keys.length}</span></div>
          <div className="tableWrap">
            <table>
              <thead>
                <tr><th>Name</th><th>Project</th><th>Prefix</th><th>Scopes</th><th>Revoked</th></tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.key_id}>
                    <td>{key.name}</td>
                    <td>{key.project_id}</td>
                    <td><span className="mono">{key.key_prefix}</span></td>
                    <td>{key.scopes.join(", ")}</td>
                    <td>{key.revoked_at ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panelHead"><h2>Create Key</h2></div>
          <form className="formGrid" action={createApiKeyAction}>
            <label>Name<input name="name" required placeholder="ci-agent" /></label>
            <label>Project<input name="project_id" defaultValue={process.env.HYOKA_PROJECT_ID || "default"} /></label>
            <label>Scopes<input name="scopes" defaultValue="read,write" /></label>
            <button className="button" type="submit">Create API Key</button>
          </form>
        </div>
      </section>
    </main>
  );
}
