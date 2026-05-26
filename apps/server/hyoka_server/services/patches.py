from __future__ import annotations

from typing import Any

from hyoka_schemas.hashing import content_hash
from hyoka_server.models import CandidateRecord, ImprovementProposalRecord

SUPPORTED_ADAPTERS = ["generic", "langgraph", "crewai", "autogen", "llamaindex", "openai_agents_sdk"]


def _adapter_files(adapter: str, operations: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, str]:
    if adapter == "langgraph":
        return {
            "hyoka_langgraph_patch.json": _json_hint(
                {
                    "configurable": {
                        "system_prompt_patch": config.get("system_prompt_patch"),
                        "tool_policy": config.get("tool_policy"),
                        "output_contract": config.get("output_contract"),
                    }
                }
            )
        }
    if adapter == "crewai":
        return {
            "hyoka_crewai_patch.yaml": "\n".join(
                [
                    "agent:",
                    f"  backstory_patch: {config.get('system_prompt_patch', '')!r}",
                    f"  required_tools: {config.get('required_tools', [])!r}",
                    f"  forbidden_tools: {config.get('forbidden_tools', [])!r}",
                    "task:",
                    f"  output_contract: {config.get('output_contract', {})!r}",
                ]
            )
        }
    if adapter == "autogen":
        return {
            "hyoka_autogen_patch.json": _json_hint(
                {
                    "system_message_patch": config.get("system_prompt_patch"),
                    "tool_policy": config.get("tool_policy"),
                    "runtime_policy": config.get("runtime_policy"),
                }
            )
        }
    if adapter == "llamaindex":
        return {
            "hyoka_llamaindex_patch.json": _json_hint(
                {
                    "prompt_template_patch": config.get("system_prompt_patch"),
                    "output_parser": config.get("output_contract"),
                    "query_engine_policy": config.get("runtime_policy"),
                }
            )
        }
    if adapter == "openai_agents_sdk":
        return {
            "hyoka_openai_agents_patch.json": _json_hint(
                {
                    "instructions_patch": config.get("system_prompt_patch"),
                    "tools": {
                        "required": config.get("required_tools", []),
                        "forbidden": config.get("forbidden_tools", []),
                    },
                    "output_schema": config.get("output_contract"),
                }
            )
        }
    return {
        "hyoka_candidate_config.json": _json_hint(
            {
                "config_overlay": config,
                "patch_operations": operations,
            }
        )
    }


def _json_hint(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True, default=str)


def build_patch_bundle(
    *,
    candidate: CandidateRecord,
    proposal: ImprovementProposalRecord,
    adapter: str = "generic",
) -> dict[str, Any]:
    adapter = adapter if adapter in SUPPORTED_ADAPTERS else "generic"
    proposal_payload = proposal.proposal or {}
    candidate_patch = proposal_payload.get("candidate_patch") or {}
    config = candidate_patch.get("config") or candidate.config or {}
    operations = list(config.get("patch_operations") or [])
    bundle = {
        "schema_version": "hyoka.patch.v1",
        "adapter": adapter,
        "candidate_id": candidate.candidate_id,
        "base_candidate_id": candidate.base_candidate_id,
        "proposal_id": proposal.proposal_id,
        "cluster_id": proposal.cluster_id,
        "targets": candidate.targets,
        "source_evidence_hash": (proposal_payload.get("evidence") or {}).get("source_evidence_hash")
        or (candidate.candidate_metadata or {}).get("source_evidence_hash"),
        "operations": operations,
        "config_overlay": config,
        "validation_plan": proposal_payload.get("validation_plan") or config.get("self_improvement", {}).get("validation_plan", []),
    }
    bundle["files"] = _adapter_files(adapter, operations, config)
    bundle["bundle_hash"] = content_hash({key: value for key, value in bundle.items() if key != "bundle_hash"})
    return bundle
