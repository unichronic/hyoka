from __future__ import annotations

import time

import typer
from hyoka_server.database import SessionLocal, engine
from hyoka_server.models import Base
from hyoka_server.services.autonomous import (
    claim_next_self_improvement_cycle,
    execute_self_improvement_cycle,
)
from hyoka_server.services.runs import execute_run
from hyoka_server.services.workers import claim_next_run, claim_run, default_worker_id
from hyoka_server.settings import get_settings
from rich.console import Console

app = typer.Typer(help="Hyoka worker commands.")
console = Console()


@app.command()
def once(run_id: str | None = None) -> None:
    """Execute one queued self-improvement cycle or run, or a specific run id."""
    settings = get_settings()
    worker_id = default_worker_id()
    if settings.auto_migrate:
        Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if not run_id:
            cycle = claim_next_self_improvement_cycle(
                session,
                worker_id=worker_id,
                lease_seconds=settings.self_improvement_lease_seconds,
            )
            if cycle:
                console.print(f"Executing self-improvement cycle {cycle.cycle_id} as {worker_id}...")
                execute_self_improvement_cycle(
                    session,
                    cycle.cycle_id,
                    worker_id=worker_id,
                    already_claimed=True,
                )
                console.print(f"Completed self-improvement cycle {cycle.cycle_id}.")
                return
        if run_id:
            run = claim_run(
                session,
                run_id=run_id,
                worker_id=worker_id,
                lease_seconds=settings.worker_lease_seconds,
            )
        else:
            run = claim_next_run(
                session,
                worker_id=worker_id,
                lease_seconds=settings.worker_lease_seconds,
            )
        if not run:
            console.print("No queued run found.")
            return
        console.print(f"Executing {run.run_id} as {worker_id}...")
        execute_run(session, run.run_id, worker_id=worker_id, already_claimed=True)
        console.print(f"Completed {run.run_id}.")


@app.command()
def serve(poll_seconds: float = 2.0) -> None:
    """Poll the database for queued self-improvement cycles and runs."""
    settings = get_settings()
    worker_id = default_worker_id()
    if settings.auto_migrate:
        Base.metadata.create_all(bind=engine)
    console.print(f"Hyoka worker {worker_id} polling for queued self-improvement cycles and runs.")
    while True:
        with SessionLocal() as session:
            cycle = claim_next_self_improvement_cycle(
                session,
                worker_id=worker_id,
                lease_seconds=settings.self_improvement_lease_seconds,
            )
            if cycle:
                console.print(f"Executing self-improvement cycle {cycle.cycle_id}...")
                execute_self_improvement_cycle(
                    session,
                    cycle.cycle_id,
                    worker_id=worker_id,
                    already_claimed=True,
                )
                console.print(f"Completed self-improvement cycle {cycle.cycle_id}.")
                time.sleep(poll_seconds)
                continue
            run = claim_next_run(
                session,
                worker_id=worker_id,
                lease_seconds=settings.worker_lease_seconds,
            )
            if run:
                console.print(f"Executing {run.run_id}...")
                execute_run(session, run.run_id, worker_id=worker_id, already_claimed=True)
                console.print(f"Completed {run.run_id}.")
        time.sleep(poll_seconds)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
