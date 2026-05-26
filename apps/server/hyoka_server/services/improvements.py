from __future__ import annotations

import copy
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from hyoka_schemas.hashing import content_hash
from hyoka_server.models import CandidateRecord, FailureClusterRecord, RunCaseRecord, RunRecord

IMPROVEMENT_METHOD = "failure_cluster_rules_v2"


def _failed_eval_results(cases: list[RunCaseRecord]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda item: (item.trace_id, item.case_id)):
        for result in case.eval_results or []:
            if result.get("passed") is not False:
                continue
            failed.append(
                {
                    "case_id": case.case_id,
                    "trace_id": case.trace_id,
                    "evaluator": result.get("evaluator"),
                    "score": result.get("score"),
                    "severity": result.get("severity"),
                    "labels": [str(label) for label in result.get("labels", [])],
                    "reason": result.get("reason"),
                    "metadata": result.get("metadata") or {},
                    "evidence_step_ids": result.get("evidence_step_ids") or [],
                }
            )
    return sorted(failed, key=lambda item: content_hash(item))


def _labels(results: list[dict[str, Any]]) -> list[str]:
    return sorted({label for result in results for label in result.get("labels", [])})


def _counter_dict(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _failure_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "failed_evaluation_count": len(results),
        "labels": _counter_dict([label for result in results for label in result.get("labels", [])]),
        "evaluators": _counter_dict([str(result.get("evaluator") or "unknown") for result in results]),
        "severities": _counter_dict([str(result.get("severity") or "unknown") for result in results]),
    }


def _evidence_hash(
    *,
    cluster: FailureClusterRecord,
    run: RunRecord,
    target: str,
    results: list[dict[str, Any]],
) -> str:
    return content_hash(
        {
            "cluster_id": cluster.cluster_id,
            "run_id": run.run_id,
            "target": target,
            "representative_trace_ids": cluster.representative_trace_ids,
            "failed_eval_results": results,
        }
    )


def _required_tools_from_failures(results: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for result in results:
        metadata = result.get("metadata") or {}
        if tool := metadata.get("tool"):
            tools.append(str(tool))
            continue
        reason = str(result.get("reason") or "")
        if " was not called" in reason:
            tools.append(reason.split(" was not called", 1)[0].strip())
    return sorted({tool for tool in tools if tool})


def _forbidden_tools_from_failures(results: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for result in results:
        if "unsafe_tool_call" not in result.get("labels", []):
            continue
        metadata = result.get("metadata") or {}
        if tool := metadata.get("tool"):
            tools.append(str(tool))
            continue
        reason = str(result.get("reason") or "")
        if " was called" in reason:
            tools.append(reason.split(" was called", 1)[0].strip())
    return sorted({tool for tool in tools if tool})


def _json_schema_patch(results: list[dict[str, Any]]) -> dict[str, Any]:
    schema_failures = [result for result in results if "schema_mismatch" in result.get("labels", [])]
    if not schema_failures:
        return {}
    failed_paths = [
        ".".join(str(part) for part in (result.get("metadata") or {}).get("path", []))
        for result in schema_failures
    ]
    return {
        "output_contract_notes": [
            "Return a response that satisfies the configured JSON schema.",
            *[str(result.get("reason")) for result in schema_failures[:3]],
        ],
        "output_contract": {
            "type": "json_schema",
            "repair_required": True,
            "failed_paths": sorted({path for path in failed_paths if path}),
        },
    }


def _risk_level(labels: list[str], results: list[dict[str, Any]]) -> str:
    severities = {str(result.get("severity") or "") for result in results}
    if "critical" in severities or {"unsafe_tool_call", "execution_error", "configuration_error"} & set(labels):
        return "high"
    if {"missing_required_tool", "schema_mismatch", "final_output"} & set(labels):
        return "medium"
    return "low"


def _operation(op: str, target: str, summary: str, value: Any, *, risk: str) -> dict[str, Any]:
    return {
        "op": op,
        "target": target,
        "summary": summary,
        "value": value,
        "risk": risk,
    }


def _validation_plan(labels: list[str], run: RunRecord) -> list[dict[str, Any]]:
    plan = [
        {
            "type": "replay_suite",
            "source_run_id": run.run_id,
            "mode": run.mode,
            "required": True,
        }
    ]
    if {"missing_required_tool", "unsafe_tool_call"} & set(labels):
        plan.append({"type": "trajectory_assertions", "labels": ["tool_use"], "required": True})
    if {"schema_mismatch", "format", "final_output"} & set(labels):
        plan.append({"type": "output_contract_assertions", "labels": ["json_schema", "final_output"], "required": True})
    if {"latency", "cost"} & set(labels):
        plan.append({"type": "performance_budget", "labels": ["latency", "cost"], "required": False})
    return plan


def _prompt_guidance(
    *,
    cluster: FailureClusterRecord,
    run: RunRecord,
    labels: list[str],
    required_tools: list[str],
    forbidden_tools: list[str],
    output_contract_notes: list[str],
) -> list[str]:
    guidance = [
        f"Address failure cluster '{cluster.name}' from run {run.run_id}.",
        "Use the trace evidence before producing the final answer.",
    ]
    if "missing_required_tool" in labels or cluster.failure_type in {"tool_use", "missing_required_tool"}:
        if required_tools:
            guidance.append(f"Call required tool(s) before final output: {', '.join(required_tools)}.")
        else:
            guidance.append("Verify required tool usage before final output.")
    if "unsafe_tool_call" in labels:
        if forbidden_tools:
            guidance.append(f"Do not call forbidden tool(s): {', '.join(forbidden_tools)}.")
        guidance.append("Block side-effecting or forbidden tools unless policy evidence explicitly permits them.")
    if "schema_mismatch" in labels or "format" in labels or "final_output" in labels:
        guidance.append("Ensure the final output is present and follows the configured output contract.")
    guidance.extend(output_contract_notes[:3])
    if "latency" in labels:
        guidance.append("Prefer shorter decision paths and avoid repeated unnecessary tool calls.")
    if "cost" in labels:
        guidance.append("Prefer lower-token prompts and avoid redundant model/tool calls.")
    if "execution_error" in labels or "replay" in labels:
        guidance.append("Fix replay/runtime integration before candidate promotion.")
    return guidance


def generate_candidate_patch(
    *,
    cluster: FailureClusterRecord,
    run: RunRecord,
    base_candidate: CandidateRecord | None,
    cases: list[RunCaseRecord],
    target: str,
) -> dict[str, Any]:
    base_config = copy.deepcopy((base_candidate.config if base_candidate else {}) or {})
    failed_results = _failed_eval_results(cases)
    labels = _labels(failed_results)
    evidence_hash = _evidence_hash(cluster=cluster, run=run, target=target, results=failed_results)
    risk = _risk_level(labels, failed_results)
    json_patch = _json_schema_patch(failed_results)
    required_tools = sorted(
        {
            *[str(tool) for tool in base_config.get("required_tools", [])],
            *_required_tools_from_failures(failed_results),
        }
    )
    forbidden_tools = sorted(
        {
            *[str(tool) for tool in base_config.get("forbidden_tools", [])],
            *_forbidden_tools_from_failures(failed_results),
        }
    )

    patch_config = dict(base_config)
    patch_config["source_failure_cluster"] = cluster.cluster_id
    patch_config["failure_labels"] = labels

    output_contract_notes = list(json_patch.get("output_contract_notes") or [])
    guidance = _prompt_guidance(
        cluster=cluster,
        run=run,
        labels=labels,
        required_tools=required_tools,
        forbidden_tools=forbidden_tools,
        output_contract_notes=output_contract_notes,
    )
    operations: list[dict[str, Any]] = [
        _operation(
            "append_system_prompt_guidance",
            "prompt",
            "Add failure-specific guidance backed by representative trace evidence.",
            guidance,
            risk=risk,
        )
    ]

    if "missing_required_tool" in labels or cluster.failure_type in {"tool_use", "missing_required_tool"}:
        if required_tools:
            patch_config["required_tools"] = required_tools
        patch_config["tool_policy"] = {
            **dict(patch_config.get("tool_policy") or {}),
            "require_evidence_before_final": True,
            "required_tools": required_tools,
        }
        operations.append(
            _operation(
                "merge_required_tools",
                "tool_policy",
                "Require missing evidence tools before final output.",
                required_tools,
                risk=risk,
            )
        )

    if "unsafe_tool_call" in labels:
        if forbidden_tools:
            patch_config["forbidden_tools"] = forbidden_tools
        patch_config["tool_policy"] = {
            **dict(patch_config.get("tool_policy") or {}),
            "block_forbidden_tools_without_evidence": True,
            "forbidden_tools": forbidden_tools,
        }
        operations.append(
            _operation(
                "merge_forbidden_tools",
                "tool_policy",
                "Block unsafe tool calls unless policy evidence allows them.",
                forbidden_tools,
                risk="high",
            )
        )

    output_repair_labels = {"schema_mismatch", "format", "final_output"} & set(labels)
    if json_patch:
        patch_config.update(json_patch)
    if output_repair_labels and "override_final_output" in patch_config:
        patch_config.pop("override_final_output", None)
        operations.append(
            _operation(
                "remove_mock_output_override",
                "replay_policy",
                "Remove stale mock output override so replay can exercise the patched agent output.",
                {"removed": "override_final_output"},
                risk=risk,
            )
        )
    if json_patch:
        operations.append(
            _operation(
                "add_output_contract",
                "output_contract",
                "Repair schema/format failures with an explicit output contract.",
                json_patch["output_contract"],
                risk=risk,
            )
        )

    if "latency" in labels or "cost" in labels:
        patch_config["runtime_policy"] = {
            **dict(patch_config.get("runtime_policy") or {}),
            "avoid_redundant_tool_calls": True,
            "prefer_short_decision_paths": "latency" in labels,
            "prefer_lower_token_prompts": "cost" in labels,
        }
        operations.append(
            _operation(
                "add_runtime_budget_policy",
                "runtime_policy",
                "Constrain redundant model/tool work that caused cost or latency failures.",
                patch_config["runtime_policy"],
                risk="low",
            )
        )

    if "execution_error" in labels or "replay" in labels:
        patch_config["replay_policy"] = {"block_promotion_on_replay_error": True}
        operations.append(
            _operation(
                "block_promotion_on_replay_error",
                "replay_policy",
                "Prevent promotion while replay/runtime integration is failing.",
                patch_config["replay_policy"],
                risk="high",
            )
        )

    patch_config["system_prompt_patch"] = " ".join(guidance)
    patch_config["patch_operations"] = operations
    patch_config["self_improvement"] = {
        "method": IMPROVEMENT_METHOD,
        "source_cluster_id": cluster.cluster_id,
        "source_run_id": run.run_id,
        "source_evidence_hash": evidence_hash,
        "risk_level": risk,
        "failure_summary": _failure_summary(failed_results),
        "validation_plan": _validation_plan(labels, run),
    }

    targets = {target}
    if {"missing_required_tool", "unsafe_tool_call"} & set(labels):
        targets.add("tool_policy")
    if {"schema_mismatch", "format", "final_output"} & set(labels):
        targets.add("output_contract")
    if {"latency", "cost"} & set(labels):
        targets.add("runtime_policy")
    if {"execution_error", "replay"} & set(labels):
        targets.add("replay_policy")

    return {
        "target": target,
        "method": IMPROVEMENT_METHOD,
        "candidate_patch": {
            "targets": sorted(targets),
            "config": patch_config,
            "metadata": {
                "source_cluster_id": cluster.cluster_id,
                "source_run_id": run.run_id,
                "source_evidence_hash": evidence_hash,
                "base_candidate_id": base_candidate.candidate_id if base_candidate else None,
                "failure_labels": labels,
                "generated_by": IMPROVEMENT_METHOD,
            },
        },
        "evidence": {
            "representative_trace_ids": cluster.representative_trace_ids,
            "failure_summary": _failure_summary(failed_results),
            "source_evidence_hash": evidence_hash,
            "failed_eval_results": failed_results[:10],
        },
        "validation_plan": _validation_plan(labels, run),
        "created_at": datetime.now(UTC).isoformat(),
    }
