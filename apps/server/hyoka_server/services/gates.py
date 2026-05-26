from __future__ import annotations

from typing import Any

from hyoka_schemas.resources import GatePolicy


def evaluate_gate_policy(
    policy: GatePolicy,
    aggregate: dict[str, Any],
    case_results: list[dict[str, Any]],
    *,
    has_manifest: bool,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    pass_rate = float(aggregate.get("pass_rate", 0.0))
    flaky_rate = float(aggregate.get("flaky_rate", 0.0))

    if pass_rate < policy.min_pass_rate:
        reasons.append(f"pass_rate {pass_rate:.3f} below required threshold {policy.min_pass_rate:.3f}")
    if flaky_rate > policy.max_flaky_rate:
        reasons.append(f"flaky_rate {flaky_rate:.3f} above allowed threshold {policy.max_flaky_rate:.3f}")

    if policy.max_p95_latency_ms is not None:
        p95_latency = aggregate.get("p95_latency_ms")
        if p95_latency is None:
            reasons.append("p95 latency missing from run aggregate")
        elif float(p95_latency) > policy.max_p95_latency_ms:
            reasons.append(
                f"p95_latency_ms {float(p95_latency):.0f} above allowed threshold {policy.max_p95_latency_ms}"
            )

    labels = {
        label
        for case in case_results
        for result in case.get("eval_results", [])
        for label in result.get("labels", [])
        if result.get("passed") is False
    }
    for label in policy.block_on:
        if label in labels:
            reasons.append(f"blocking label present: {label}")

    if "manifest" in policy.required_artifacts and not has_manifest:
        reasons.append("required artifact missing: manifest")

    if aggregate.get("status") not in {None, "completed"}:
        reasons.append(f"run status is not completed: {aggregate.get('status')}")

    if reasons:
        return "blocked", reasons
    return "approved", []

