"use server";

import { redirect } from "next/navigation";
import { postForm, postJson, type ApiKey, type GateDecision, type ImprovementProposal, type SelfImproveCycle } from "@/lib/api";

export async function evaluateGateAction(formData: FormData) {
  const runId = String(formData.get("run_id") || "");
  const name = String(formData.get("name") || "dashboard-gate");
  const policyText = String(formData.get("policy") || "{}");
  const policy = JSON.parse(policyText);
  await postJson<GateDecision>("/v1/gates/evaluate", { run_id: runId, name, policy });
  redirect(`/runs/${encodeURIComponent(runId)}`);
}

export async function proposeImprovementAction(formData: FormData) {
  const clusterId = String(formData.get("cluster_id") || "");
  const target = String(formData.get("target") || "prompt");
  const createCandidate = formData.get("create_candidate") === "on";
  const query = new URLSearchParams({
    cluster_id: clusterId,
    target,
    create_candidate: String(createCandidate)
  });
  const proposal = await postForm<ImprovementProposal>(`/v1/improvements/propose?${query.toString()}`);
  redirect(`/proposals?created=${encodeURIComponent(proposal.proposal_id)}`);
}

export async function createApiKeyAction(formData: FormData) {
  const name = String(formData.get("name") || "");
  const projectId = String(formData.get("project_id") || "default");
  const scopes = String(formData.get("scopes") || "read,write")
    .split(",")
    .map((scope) => scope.trim())
    .filter(Boolean);
  const key = await postJson<ApiKey & { secret: string }>("/v1/api-keys", {
    name,
    project_id: projectId,
    scopes
  });
  redirect(`/api-keys?created=${encodeURIComponent(key.key_id)}&secret=${encodeURIComponent(key.secret)}`);
}

export async function createSelfImprovementCycleAction(formData: FormData) {
  const runId = String(formData.get("run_id") || "");
  const target = String(formData.get("target") || "prompt");
  const maxCandidates = Number(formData.get("max_candidates") || 3);
  const executeInline = formData.get("execute_inline") === "on";
  const promoteOnApproval = formData.get("promote_on_approval") === "on";
  const gatePolicyText = String(formData.get("gate_policy") || "{}");
  const gatePolicy = gatePolicyText.trim() ? JSON.parse(gatePolicyText) : undefined;
  const cycle = await postJson<SelfImproveCycle>("/v1/self-improvement/cycles", {
    run_id: runId,
    target,
    max_candidates: maxCandidates,
    execute_inline: executeInline,
    execute_validation: true,
    promote_on_approval: promoteOnApproval,
    ...(gatePolicy ? { gate_policy: gatePolicy } : {})
  });
  redirect(`/self-improvement?created=${encodeURIComponent(cycle.cycle_id)}`);
}
