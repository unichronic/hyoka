from __future__ import annotations

from hyoka_server.models import CandidateRecord, FailureClusterRecord, RunCaseRecord, RunRecord
from hyoka_server.services.improvements import generate_candidate_patch


def _run() -> RunRecord:
    return RunRecord(
        run_id="run_self_improve",
        project_id="default",
        suite_id="suite_support",
        candidate_id="cand_base",
        mode="mock",
        repeats=1,
        status="completed",
        aggregate={},
    )


def _base_candidate() -> CandidateRecord:
    return CandidateRecord(
        candidate_id="cand_base",
        project_id="default",
        name="base",
        targets=["prompt"],
        config={"required_tools": ["lookup_order"], "expected_output_regex": "refund"},
        candidate_metadata={},
        candidate_hash="sha256:base",
    )


def _cluster() -> FailureClusterRecord:
    return FailureClusterRecord(
        cluster_id="fc_tool_schema",
        run_id="run_self_improve",
        name="tool_schema_failures",
        failure_type="missing_required_tool",
        case_count=2,
        representative_trace_ids=["tr_missing_tool", "tr_bad_schema"],
        hypothesis="tool and schema failures",
        suggested_targets=["prompt", "tool_schema"],
    )


def _cases() -> list[RunCaseRecord]:
    return [
        RunCaseRecord(
            case_id="case_missing_tool",
            run_id="run_self_improve",
            trace_id="tr_missing_tool",
            status="failed",
            attempt=1,
            replay_output={},
            eval_results=[
                {
                    "evaluator": "required_tool_called",
                    "passed": False,
                    "score": 0.0,
                    "severity": "major",
                    "labels": ["tool_use", "missing_required_tool"],
                    "reason": "check_delivery was not called",
                    "metadata": {"tool": "check_delivery"},
                }
            ],
            metrics={},
        ),
        RunCaseRecord(
            case_id="case_bad_schema",
            run_id="run_self_improve",
            trace_id="tr_bad_schema",
            status="failed",
            attempt=1,
            replay_output={},
            eval_results=[
                {
                    "evaluator": "json_schema",
                    "passed": False,
                    "score": 0.0,
                    "severity": "major",
                    "labels": ["json_schema", "schema_mismatch"],
                    "reason": "'action' is a required property",
                    "metadata": {"path": ["action"]},
                }
            ],
            metrics={},
        ),
    ]


def test_generate_candidate_patch_is_structured_and_deterministic() -> None:
    first = generate_candidate_patch(
        cluster=_cluster(),
        run=_run(),
        base_candidate=_base_candidate(),
        cases=_cases(),
        target="prompt",
    )
    second = generate_candidate_patch(
        cluster=_cluster(),
        run=_run(),
        base_candidate=_base_candidate(),
        cases=list(reversed(_cases())),
        target="prompt",
    )

    assert first["method"] == "failure_cluster_rules_v2"
    assert first["candidate_patch"] == second["candidate_patch"]
    config = first["candidate_patch"]["config"]
    assert config["required_tools"] == ["check_delivery", "lookup_order"]
    assert config["output_contract"]["repair_required"] is True
    assert config["self_improvement"]["source_evidence_hash"].startswith("sha256:")
    assert config["self_improvement"]["risk_level"] == "medium"
    assert {operation["op"] for operation in config["patch_operations"]} >= {
        "append_system_prompt_guidance",
        "merge_required_tools",
        "add_output_contract",
    }
    assert "generated_at" not in first["candidate_patch"]["metadata"]
    assert first["evidence"]["failure_summary"]["labels"]["missing_required_tool"] == 1
    assert first["validation_plan"][0]["type"] == "replay_suite"


def test_generate_candidate_patch_handles_unsafe_tool_failures() -> None:
    cluster = _cluster()
    cluster.failure_type = "unsafe_tool_call"
    case = RunCaseRecord(
        case_id="case_unsafe_tool",
        run_id="run_self_improve",
        trace_id="tr_unsafe_tool",
        status="failed",
        attempt=1,
        replay_output={},
        eval_results=[
            {
                "evaluator": "forbidden_tool_not_called",
                "passed": False,
                "score": 0.0,
                "severity": "critical",
                "labels": ["tool_use", "unsafe_tool_call"],
                "reason": "issue_refund was called",
                "metadata": {"tool": "issue_refund"},
            }
        ],
        metrics={},
    )

    proposal = generate_candidate_patch(
        cluster=cluster,
        run=_run(),
        base_candidate=_base_candidate(),
        cases=[case],
        target="tool_schema",
    )

    config = proposal["candidate_patch"]["config"]
    assert config["forbidden_tools"] == ["issue_refund"]
    assert config["tool_policy"]["block_forbidden_tools_without_evidence"] is True
    assert config["self_improvement"]["risk_level"] == "high"
    assert "tool_policy" in proposal["candidate_patch"]["targets"]
