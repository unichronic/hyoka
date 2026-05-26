from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml
from alembic.config import Config
from rich.console import Console
from rich.table import Table

from alembic import command

app = typer.Typer(help="Hyoka developer and CI workflow CLI.", no_args_is_help=True)
db_app = typer.Typer(help="Database migration commands.", no_args_is_help=True)
api_key_app = typer.Typer(help="API key administration commands.", no_args_is_help=True)
suite_app = typer.Typer(help="Suite commands.", no_args_is_help=True)
candidate_app = typer.Typer(help="Candidate commands.", no_args_is_help=True)
run_app = typer.Typer(help="Run commands.", no_args_is_help=True)
failures_app = typer.Typer(help="Failure mining commands.", no_args_is_help=True)
audit_app = typer.Typer(help="Audit log commands.", no_args_is_help=True)
improvements_app = typer.Typer(help="Improvement proposal commands.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(api_key_app, name="api-key")
app.add_typer(suite_app, name="suite")
app.add_typer(candidate_app, name="candidate")
app.add_typer(run_app, name="run")
app.add_typer(failures_app, name="failures")
app.add_typer(audit_app, name="audit")
app.add_typer(improvements_app, name="improvements")

console = Console()


def _client(api_url: str, api_key: str | None = None) -> httpx.Client:
    headers = {}
    if api_key:
        headers["X-Hyoka-Api-Key"] = api_key
    return httpx.Client(base_url=api_url.rstrip("/"), headers=headers, timeout=60.0)


def _api_url(value: str | None) -> str:
    return value or os.getenv("HYOKA_API_URL", "http://localhost:8686")


def _api_key(value: str | None) -> str | None:
    return value or os.getenv("HYOKA_API_KEY")


def _project_id(value: str | None) -> str | None:
    return value or os.getenv("HYOKA_PROJECT_ID")


def _alembic_config() -> Config:
    cwd_config = Path("alembic.ini")
    if cwd_config.exists():
        return Config(str(cwd_config))
    return Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))


def _raise_for_status(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        console.print(f"API error {exc.response.status_code}: {detail}", style="red")
        raise typer.Exit(1) from exc


def _read_data(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(text)
    return json.loads(text)


def _parse_headers(values: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values or []:
        if ":" not in value:
            raise typer.BadParameter("headers must use 'Name: value' format")
        name, header_value = value.split(":", 1)
        headers[name.strip()] = header_value.strip()
    return headers


def _parse_json_or_jsonl(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        return []
    if stripped[0] in "[{":
        return json.loads(stripped)
    return [json.loads(line) for line in stripped.splitlines() if line.strip()]


def _split_exposition_payload(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(payload, dict):
        if "events" in payload or "traces" in payload:
            labels = dict(payload.get("labels") or {})
            resource = dict(payload.get("resource") or {})
            traces = []
            for trace in list(payload.get("traces") or []):
                if not isinstance(trace, dict):
                    continue
                merged_trace = dict(trace)
                metadata = dict(merged_trace.get("metadata") or {})
                metadata["labels"] = {**labels, **dict(metadata.get("labels") or {})}
                metadata["resource"] = {**resource, **dict(metadata.get("resource") or {})}
                merged_trace["metadata"] = metadata
                traces.append(merged_trace)
            events = []
            for event in list(payload.get("events") or []):
                if not isinstance(event, dict):
                    continue
                merged_event = dict(event)
                merged_event["labels"] = {**labels, **dict(event.get("labels") or {})}
                merged_event["attributes"] = {
                    "resource": resource,
                    **dict(event.get("attributes") or {}),
                }
                events.append(merged_event)
            return traces, events
        if "type" in payload and "trace_id" in payload:
            return [], [payload]
        return [payload], []
    if isinstance(payload, list):
        traces: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict) and "type" in item and "trace_id" in item:
                events.append(item)
            elif isinstance(item, dict):
                traces.append(item)
        return traces, events
    raise typer.BadParameter("Scrape target must return JSON, JSONL, or Hyoka exposition JSON")


def _print_json(value: Any) -> None:
    console.print_json(json.dumps(value, indent=2, sort_keys=True))


def _resolve_suite(client: httpx.Client, suite: str) -> str:
    if suite.startswith("suite_"):
        return suite
    response = client.get("/v1/suites")
    _raise_for_status(response)
    matches = [item for item in response.json() if item["name"] == suite]
    if not matches:
        return suite
    matches.sort(key=lambda item: item["version"], reverse=True)
    return matches[0]["suite_id"]


def _resolve_candidate(client: httpx.Client, candidate: str) -> str:
    if candidate.startswith("cand_"):
        return candidate
    path = Path(candidate)
    if path.exists():
        data = _read_data(path) or {}
        if "name" not in data:
            data = {"name": path.stem, "targets": ["prompt"], "config": data}
        response = client.post("/v1/candidates", json=data)
        _raise_for_status(response)
        return response.json()["candidate_id"]
    response = client.get("/v1/candidates")
    _raise_for_status(response)
    matches = [item for item in response.json() if item["name"] == candidate]
    if matches:
        matches.sort(key=lambda item: item["created_at"], reverse=True)
        return matches[0]["candidate_id"]
    return candidate


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head")) -> None:
    """Apply Alembic migrations."""
    command.upgrade(_alembic_config(), revision)
    console.print(f"Database upgraded to {revision}.")


@db_app.command("current")
def db_current() -> None:
    """Print the current Alembic migration revision."""
    command.current(_alembic_config())


@api_key_app.command("create")
def api_key_create(
    name: str,
    project_id: str = typer.Option("default", "--project"),
    scope: list[str] | None = typer.Option(None, "--scope"),
    expires_at: str | None = typer.Option(None, "--expires-at"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    """Create a hashed, scoped API key. The returned secret is shown once."""
    payload = {
        "name": name,
        "project_id": project_id,
        "scopes": scope or ["read", "write"],
        "expires_at": expires_at,
    }
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post("/v1/api-keys", json=payload)
        _raise_for_status(response)
        _print_json(response.json())


@api_key_app.command("list")
def api_key_list(
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    params = {"project_id": project_id} if project_id else {}
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get("/v1/api-keys", params=params)
        _raise_for_status(response)
        table = Table(title="API keys")
        table.add_column("ID")
        table.add_column("Project")
        table.add_column("Name")
        table.add_column("Prefix")
        table.add_column("Scopes")
        table.add_column("Revoked")
        for key in response.json():
            table.add_row(
                key["key_id"],
                key["project_id"],
                key["name"],
                key["key_prefix"],
                ",".join(key["scopes"]),
                str(bool(key.get("revoked_at"))),
            )
        console.print(table)


@api_key_app.command("revoke")
def api_key_revoke(
    key_id: str,
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.delete(f"/v1/api-keys/{key_id}")
        _raise_for_status(response)
        _print_json(response.json())


@app.command()
def doctor(
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    """Check local CLI and API connectivity."""
    url = _api_url(api_url)
    table = Table(title="Hyoka Doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("CLI", "ok")
    try:
        with _client(url, _api_key(api_key)) as client:
            response = client.get("/healthz")
            response.raise_for_status()
        table.add_row("API", f"ok ({url})")
    except Exception as exc:
        table.add_row("API", f"unreachable ({url}): {exc}")
    console.print(table)


@app.command("import")
def import_traces(
    path: Path,
    suite: str | None = typer.Option(None, "--suite"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    """Import Hyoka JSON or JSONL traces."""
    traces: list[dict[str, Any]] = []
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                traces.append(json.loads(line))
    else:
        data = _read_data(path)
        traces = data if isinstance(data, list) else [data]
    if scoped := _project_id(project_id):
        for trace in traces:
            trace["project_id"] = scoped
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post("/v1/traces/batch", json=traces)
        _raise_for_status(response)
        imported = response.json()
        console.print(f"Imported {len(imported)} trace(s).")
        if suite:
            suite_response = client.post(
                "/v1/suites",
                json={"name": suite, "project_id": scoped or "default", "trace_ids": [trace["trace_id"] for trace in imported]},
            )
            _raise_for_status(suite_response)
            console.print(f"Created suite {suite_response.json()['suite_id']}.")


@app.command()
def scrape(
    target_url: str,
    suite: str | None = typer.Option(None, "--suite"),
    target_header: list[str] | None = typer.Option(None, "--target-header"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    """Pull Hyoka exposition JSON/JSONL from any service and ingest it."""
    with httpx.Client(timeout=60.0) as fetch_client:
        response = fetch_client.get(
            target_url,
            headers={
                "Accept": "application/json, application/x-ndjson, text/plain;q=0.9",
                **_parse_headers(target_header),
            },
        )
        response.raise_for_status()
        traces, events = _split_exposition_payload(_parse_json_or_jsonl(response.text))
    if scoped := _project_id(project_id):
        for trace in traces:
            trace["project_id"] = scoped
        for event in events:
            event["project_id"] = scoped

    imported_trace_ids: list[str] = []
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        if traces:
            response = client.post("/v1/traces/batch", json=traces)
            _raise_for_status(response)
            imported_trace_ids.extend(trace["trace_id"] for trace in response.json())
        if events:
            response = client.post("/v1/events/batch", json=events)
            _raise_for_status(response)
            imported_trace_ids.extend(trace["trace_id"] for trace in response.json())

        unique_trace_ids = sorted(set(imported_trace_ids))
        console.print(
            f"Scraped {len(traces)} canonical trace(s), "
            f"{len(events)} event(s), {len(unique_trace_ids)} resulting trace(s)."
        )
        if suite and unique_trace_ids:
            suite_response = client.post(
                "/v1/suites",
                json={"name": suite, "project_id": scoped or "default", "trace_ids": unique_trace_ids},
            )
            _raise_for_status(suite_response)
            console.print(f"Created suite {suite_response.json()['suite_id']}.")


@suite_app.command("create")
def suite_create(
    name: str,
    trace_id: list[str] | None = typer.Option(None, "--trace-id"),
    agent: str | None = typer.Option(None, "--agent"),
    status: str | None = typer.Option(None, "--status"),
    environment: str | None = typer.Option(None, "--environment"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    query = {key: value for key, value in {"agent": agent, "status": status, "environment": environment}.items() if value}
    payload = {"name": name, "project_id": _project_id(project_id) or "default", "trace_ids": trace_id or [], "query": query}
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post("/v1/suites", json=payload)
        _raise_for_status(response)
        _print_json(response.json())


@suite_app.command("list")
def suite_list(
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get("/v1/suites", params={"project_id": _project_id(project_id)} if _project_id(project_id) else {})
        _raise_for_status(response)
        table = Table(title="Suites")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Cases")
        for suite in response.json():
            table.add_row(suite["suite_id"], suite["name"], str(suite["version"]), str(len(suite["trace_ids"])))
        console.print(table)


@candidate_app.command("create")
def candidate_create(
    path: Path,
    name: str | None = typer.Option(None, "--name"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    data = _read_data(path) or {}
    if "config" not in data:
        data = {"name": name or path.stem, "targets": ["prompt"], "config": data}
    if name:
        data["name"] = name
    data["project_id"] = _project_id(project_id) or data.get("project_id", "default")
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post("/v1/candidates", json=data)
        _raise_for_status(response)
        _print_json(response.json())


@candidate_app.command("list")
def candidate_list(
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get("/v1/candidates", params={"project_id": _project_id(project_id)} if _project_id(project_id) else {})
        _raise_for_status(response)
        table = Table(title="Candidates")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Targets")
        for candidate in response.json():
            table.add_row(candidate["candidate_id"], candidate["name"], ",".join(candidate["targets"]))
        console.print(table)


@run_app.command("create")
def run_create(
    suite: str,
    candidate: str,
    mode: str = typer.Option("mock", "--mode"),
    repeats: int = typer.Option(1, "--repeats"),
    wait: bool = typer.Option(False, "--wait"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        suite_id = _resolve_suite(client, suite)
        candidate_id = _resolve_candidate(client, candidate)
        response = client.post(
            "/v1/runs",
            json={
                "project_id": _project_id(project_id) or "default",
                "suite_id": suite_id,
                "candidate_id": candidate_id,
                "mode": mode,
                "repeats": repeats,
            },
        )
        _raise_for_status(response)
        run = response.json()
        console.print(f"Created run {run['run_id']}.")
        if wait:
            run = _wait_for_run(client, run["run_id"])
        _print_json(run)


def _wait_for_run(client: httpx.Client, run_id: str) -> dict[str, Any]:
    while True:
        response = client.get(f"/v1/runs/{run_id}")
        _raise_for_status(response)
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled", "timed_out"}:
            return run
        time.sleep(1)


@run_app.command("status")
def run_status(
    run_id: str,
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get(f"/v1/runs/{run_id}")
        _raise_for_status(response)
        _print_json(response.json())


@app.command()
def compare(
    baseline_run_id: str,
    candidate_run_id: str,
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post(
            "/v1/runs/compare",
            json={"baseline_run_id": baseline_run_id, "candidate_run_id": candidate_run_id},
        )
        _raise_for_status(response)
        _print_json(response.json())


@failures_app.command("mine")
def failures_mine(
    run_id: str,
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post("/v1/failures/mine", params={"run_id": run_id})
        _raise_for_status(response)
        _print_json(response.json())


@audit_app.command("list")
def audit_list(
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    limit: int = typer.Option(100, "--limit"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    params: dict[str, Any] = {"limit": limit}
    if scoped := _project_id(project_id):
        params["project_id"] = scoped
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get("/v1/audit-events", params=params)
        _raise_for_status(response)
        _print_json(response.json())


@improvements_app.command("propose")
def improvement_propose(
    cluster_id: str,
    target: str = typer.Option("prompt", "--target"),
    create_candidate: bool = typer.Option(False, "--create-candidate"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post(
            "/v1/improvements/propose",
            params={"cluster_id": cluster_id, "target": target, "create_candidate": create_candidate},
        )
        _raise_for_status(response)
        _print_json(response.json())


@improvements_app.command("list")
def improvement_list(
    run_id: str | None = typer.Option(None, "--run-id"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    params: dict[str, Any] = {}
    if run_id:
        params["run_id"] = run_id
    if scoped := _project_id(project_id):
        params["project_id"] = scoped
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get("/v1/improvement-proposals", params=params)
        _raise_for_status(response)
        _print_json(response.json())


@app.command()
def gate(
    run_id: str,
    policy: Path,
    name: str = typer.Option("release-gate", "--name"),
    project_id: str | None = typer.Option(None, "--project", envvar="HYOKA_PROJECT_ID"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    policy_data = _read_data(policy)
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post(
            "/v1/gates/evaluate",
            json={"name": name, "project_id": _project_id(project_id) or "default", "run_id": run_id, "policy": policy_data},
        )
        _raise_for_status(response)
        _print_json(response.json())


@app.command()
def manifest(
    run_id: str,
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.get(f"/v1/manifests/{run_id}")
        _raise_for_status(response)
        _print_json(response.json())


@app.command()
def promote(
    candidate_id: str,
    gate_decision_id: str,
    manifest_id: str,
    environment: str = typer.Option("prod", "--environment"),
    actor: str = typer.Option("local", "--actor"),
    override: bool = typer.Option(False, "--override"),
    api_url: str | None = typer.Option(None, envvar="HYOKA_API_URL"),
    api_key: str | None = typer.Option(None, envvar="HYOKA_API_KEY"),
) -> None:
    payload = {
        "candidate_id": candidate_id,
        "gate_decision_id": gate_decision_id,
        "manifest_id": manifest_id,
        "environment": environment,
        "actor": actor,
        "override": override,
    }
    with _client(_api_url(api_url), _api_key(api_key)) as client:
        response = client.post("/v1/promotions", json=payload)
        _raise_for_status(response)
        _print_json(response.json())


if __name__ == "__main__":
    app()
