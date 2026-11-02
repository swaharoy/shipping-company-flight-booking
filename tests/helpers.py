"""Building values the way NanoAgent's sandbox does, and running the tools and verifier like the host."""

from __future__ import annotations

from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
from contract import TASKS, TOOLS, SearchInput, SolveOutput, Task, Tool, TripInput
from plugin import get_trip, search_flights, solve_booking

BOOK = Task.BOOK_FLIGHT.value


def booking(run_id: str, offer_id: str = "", *, booked: bool = True, refusal: str = "NONE", oop: int = 0) -> dict:
    return {"run_id": run_id, "booked": booked, "refusal": refusal, "offer_id": offer_id,
            "traveller_out_of_pocket_cents": oop}


def judge(seed: int, output: dict, reference: SolveOutput | None, workspace: Path) -> dict:
    """verify_task on plain values built into their contract classes, as the sandbox does."""
    given, made = TASKS[Task.BOOK_FLIGHT]
    key = None if reference is None else build_output(plain_output(reference), SolveOutput)
    return verifier.verify_task(BOOK, build_output({"seed": seed}, given), build_output(output, made), key,
                                str(workspace))


class Run:
    """One booking run: the answer key pinned in a scratch folder, then get_trip and search in the workspace."""

    def __init__(self, seed: int, root: Path, *, search: bool = True) -> None:
        self.seed = seed
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.key = solve_booking(TripInput(seed), scratch)
        started = get_trip(TripInput(seed), self.workspace)
        self.run_id = started.run_id
        self.trip = started.trip
        self.offers = []
        if search:
            self.offers = self.search().offers

    def search(self, date_from: str | None = None, date_to: str | None = None):
        trip = self.trip
        return search_flights(
            SearchInput(self.seed, self.run_id, trip.origin.code, trip.destination.code,
                        date_from or trip.date_from, date_to or trip.date_to),
            self.workspace,
        )

    def offer(self, offer_id: str):
        return next(offer for offer in self.key.offers if offer.offer_id == offer_id)

    def gold(self) -> dict:
        key = self.key
        if key.refusal.value != "NONE":
            return booking(self.run_id, booked=False, refusal=key.refusal.value)
        return booking(self.run_id, key.correct_offer_ids[0], oop=key.out_of_pocket_cents)

    def judge(self, output: dict) -> dict:
        return judge(self.seed, output, self.key, self.workspace)


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def tool_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))
