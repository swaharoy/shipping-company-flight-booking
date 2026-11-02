"""Receipts: what each tool call did, written to the workspace so the verifier can check a submission
against them. Each run of the booking task (one get_trip call) gets its own folder, runs/<run id>/."""

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

RUNS = "runs"
RUN_ID = re.compile(r"^[0-9a-f]{12}$")


def now() -> str:
    """The current UTC time, YYYY-MM-DD HH:MM:SS.ffffff (tests replace this clock)."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


CLOCK = now


def new_run(workspace: Path, seed: int) -> str:
    """A new run folder holding trip.json: the seed and when the run began. Returns its id."""
    run_id = secrets.token_hex(6)
    folder = workspace / RUNS / run_id
    folder.mkdir(parents=True, exist_ok=False)
    write(folder / "trip.json", {"run_id": run_id, "seed": seed, "started_at": CLOCK()})
    return run_id


def run_folder(workspace: Path, run_id: str, seed: int) -> Path:
    """The folder of a run get_trip began for ``seed``; raises when there is none."""
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(f"run_id {run_id!r} is not one get_trip returned")
    folder = workspace / RUNS / run_id
    path = folder / "trip.json"
    if not path.is_file():
        raise ValueError(f"no run {run_id}: call get_trip first and pass the run_id it returns")
    if json.loads(path.read_text(encoding="utf-8"))["seed"] != seed:
        raise ValueError(f"run {run_id} is for another seed")
    return folder


def add_search(folder: Path, receipt: dict) -> None:
    """search-<n>.json, numbered in call order."""
    number = len(list(folder.glob("search-*.json"))) + 1
    write(folder / f"search-{number}.json", receipt)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")
