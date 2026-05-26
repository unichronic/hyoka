export type Summary = {
  traces: number;
  suites: number;
  candidates: number;
  runs: number;
  latest_run: Run | null;
  latest_gate: GateDecision | null;
};

export type Trace = {
  project_id: string;
  trace_id: string;
  agent_name: string;
  session_id?: string | null;
  environment: string;
  input: Record<string, unknown>;
  final_output_preview: string | null;
  metadata: Record<string, unknown>;
  summary: { status: string; latency_ms: number; cost_usd: number; tokens_total: number };
  steps: Array<Record<string, unknown> & { type: string; name?: string; tool_name?: string; status: string; latency_ms?: number }>;
  created_at: string;
};

export type Run = {
  run_id: string;
  project_id: string;
  suite_id: string;
  candidate_id: string;
  mode: string;
  status: string;
  aggregate: {
    case_count?: number;
    pass_rate?: number;
    flaky_rate?: number;
    p95_latency_ms?: number;
    total_cost_usd?: number;
  };
  manifest_id: string | null;
  queued_at: string;
};

export type RunCase = {
  case_id: string;
  run_id: string;
  trace_id: string;
  status: string;
  replay_output: Record<string, unknown>;
  eval_results: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
};

export type Candidate = {
  candidate_id: string;
  project_id: string;
  name: string;
  targets: string[];
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
  candidate_hash: string;
  created_at: string;
};

export type GateDecision = {
  decision_id: string;
  run_id: string;
  candidate_id: string;
  decision: string;
  pass_rate: number;
  flaky_rate: number;
  blocking_reasons: string[];
  manifest_id: string;
  created_at: string;
};

export type FailureCluster = {
  cluster_id: string;
  run_id: string;
  name: string;
  failure_type: string;
  case_count: number;
  representative_trace_ids: string[];
  hypothesis: string;
  suggested_targets: string[];
  created_at: string;
};

export type ImprovementProposal = {
  proposal_id: string;
  cluster_id: string;
  candidate_id: string | null;
  target: string;
  method: string;
  proposal: Record<string, unknown>;
  created_at: string;
};

export type SelfImproveCycle = {
  cycle_id: string;
  project_id: string;
  baseline_run_id: string;
  status: string;
  request: Record<string, unknown>;
  result: Record<string, unknown>;
  worker_id: string | null;
  lease_expires_at: string | null;
  execution_attempts: number;
  error_message: string | null;
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type ApiKey = {
  key_id: string;
  project_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type Manifest = {
  manifest_id: string;
  run_id: string;
  decision: string;
  signature: string;
  payload: Record<string, unknown>;
  created_at: string;
};

const apiBase = process.env.HYOKA_INTERNAL_API_URL || process.env.NEXT_PUBLIC_HYOKA_API_URL || "http://localhost:8686";
const apiKey = process.env.HYOKA_API_KEY;
const projectId = process.env.HYOKA_PROJECT_ID;

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    cache: "no-store",
    headers: apiKey ? { "X-Hyoka-Api-Key": apiKey } : {}
  });
  if (!response.ok) {
    throw new Error(`Hyoka API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      ...(apiKey ? { "X-Hyoka-Api-Key": apiKey } : {})
    },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Hyoka API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function postForm<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    cache: "no-store",
    headers: apiKey ? { "X-Hyoka-Api-Key": apiKey } : {}
  });
  if (!response.ok) {
    throw new Error(`Hyoka API ${response.status}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function getDashboardData() {
  const projectQuery = projectId ? `project_id=${encodeURIComponent(projectId)}` : "";
  const withProject = (path: string) => `${path}${path.includes("?") ? "&" : "?"}${projectQuery}`;
  const [summary, traces, runs, gates] = await Promise.all([
    getJson<Summary>(projectId ? withProject("/v1/dashboard/summary") : "/v1/dashboard/summary"),
    getJson<Trace[]>(projectId ? withProject("/v1/traces?limit=8") : "/v1/traces?limit=8"),
    getJson<Run[]>(projectId ? withProject("/v1/runs") : "/v1/runs"),
    getJson<GateDecision[]>(projectId ? withProject("/v1/gate-decisions") : "/v1/gate-decisions")
  ]);
  return { summary, traces, runs: runs.slice(0, 8), gates: gates.slice(0, 6) };
}

export async function getTrace(traceId: string) {
  return getJson<Trace>(`/v1/traces/${encodeURIComponent(traceId)}${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);
}

export async function getRun(runId: string) {
  return getJson<Run>(`/v1/runs/${encodeURIComponent(runId)}`);
}

export async function getRunCases(runId: string) {
  return getJson<RunCase[]>(`/v1/runs/${encodeURIComponent(runId)}/cases`);
}

export async function getCandidates() {
  return getJson<Candidate[]>(projectId ? `/v1/candidates?project_id=${encodeURIComponent(projectId)}` : "/v1/candidates");
}

export async function getFailureClusters(runId?: string) {
  const query = runId ? `run_id=${encodeURIComponent(runId)}` : projectId ? `project_id=${encodeURIComponent(projectId)}` : "";
  return getJson<FailureCluster[]>(`/v1/failure-clusters${query ? `?${query}` : ""}`);
}

export async function getImprovementProposals(runId?: string) {
  const query = runId ? `run_id=${encodeURIComponent(runId)}` : projectId ? `project_id=${encodeURIComponent(projectId)}` : "";
  return getJson<ImprovementProposal[]>(`/v1/improvement-proposals${query ? `?${query}` : ""}`);
}

export async function getSelfImprovementCycles() {
  return getJson<SelfImproveCycle[]>(
    projectId ? `/v1/self-improvement/cycles?project_id=${encodeURIComponent(projectId)}` : "/v1/self-improvement/cycles"
  );
}

export async function getApiKeys() {
  return getJson<ApiKey[]>(projectId ? `/v1/api-keys?project_id=${encodeURIComponent(projectId)}` : "/v1/api-keys");
}

export async function getRuns() {
  return getJson<Run[]>(projectId ? `/v1/runs?project_id=${encodeURIComponent(projectId)}` : "/v1/runs");
}

export async function getManifest(runId: string) {
  return getJson<Manifest>(`/v1/manifests/${encodeURIComponent(runId)}`);
}
