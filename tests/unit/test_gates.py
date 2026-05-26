from hyoka_schemas.resources import GatePolicy
from hyoka_server.services.gates import evaluate_gate_policy


def test_gate_blocks_on_thresholds_and_labels() -> None:
    decision, reasons = evaluate_gate_policy(
        GatePolicy(min_pass_rate=0.9, max_flaky_rate=0.01, block_on=["unsafe_tool_call"]),
        {"pass_rate": 0.8, "flaky_rate": 0.0},
        [
            {
                "eval_results": [
                    {"passed": False, "labels": ["unsafe_tool_call"]},
                ]
            }
        ],
        has_manifest=True,
    )

    assert decision == "blocked"
    assert any("pass_rate" in reason for reason in reasons)
    assert any("unsafe_tool_call" in reason for reason in reasons)


def test_gate_approves_clean_run() -> None:
    decision, reasons = evaluate_gate_policy(
        GatePolicy(min_pass_rate=0.9, max_flaky_rate=0.1),
        {"pass_rate": 1.0, "flaky_rate": 0.0},
        [{"eval_results": [{"passed": True, "labels": ["final_output"]}]}],
        has_manifest=True,
    )

    assert decision == "approved"
    assert reasons == []

