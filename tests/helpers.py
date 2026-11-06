"""Building values the way NanoAgent's sandbox does, and running the tools and verifier like the host."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path

from slimconfig import build_output, plain_output

import verifier
import verifier.world
from contract import TASKS, TOOLS, AirportCode, Offer, SearchInput, SolveOutput, Task, Tool, TripInput
from plugin import get_trip, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, minute_number

BOOK = Task.BOOK_FLIGHT.value
CODES = [member.value for member in AirportCode]


def request(**changes) -> TripInput:
    """A trip request: by default an employee flying BOS-LHR on 2026-12-03, nothing extra wanted."""
    value = {
        "traveller_name": "Maya Chen", "traveller_type": "EMPLOYEE", "origin": "BOS", "destination": "LHR",
        "date_from": "2026-12-03", "date_to": "2026-12-03", "wants_business": False, "wants_checked_bag": False,
    } | changes
    return build_output(value, TripInput)


def requests(count: int, salt: str = "requests"):
    """``count`` varied trip requests, chosen by SHA-256 so they are the same on every machine: any route,
    one to fifteen days from 0 to 60 days after today, every traveller type, business and bag wishes."""
    for index in range(count):
        digest = hashlib.sha256(f"{salt}:{index}".encode()).digest()
        origin = CODES[digest[0] % len(CODES)]
        destination = CODES[digest[1] % len(CODES)]
        if origin == destination:
            continue
        start = day_number("2026-11-05") + digest[2] % 60
        span = 0 if digest[3] % 2 else digest[4] % 15
        kind = ("EMPLOYEE", "EMPLOYEE", "NON_EMPLOYEE", "EMPLOYEE", "EMPLOYEE", "CONSULTANT")[digest[5] % 6]
        yield request(origin=origin, destination=destination, date_from=date_of(start),
                      date_to=date_of(start + span), traveller_type=kind, wants_business=bool(digest[6] % 2),
                      wants_checked_bag=bool(digest[7] % 2))


def booking(run_id: str, offer_id: str = "", *, booked: bool = True, refusal: str = "NONE", oop: int = 0) -> dict:
    return {"run_id": run_id, "booked": booked, "refusal": refusal, "offer_id": offer_id,
            "traveller_out_of_pocket_cents": oop}


def judge(arguments: TripInput, output: dict, reference: SolveOutput | None, workspace: Path) -> dict:
    """verify_task on plain values built into their contract classes, as the sandbox does."""
    given, made = TASKS[Task.BOOK_FLIGHT]
    key = None if reference is None else build_output(plain_output(reference), SolveOutput)
    return verifier.verify_task(BOOK, build_output(plain_output(arguments), given), build_output(output, made), key,
                                str(workspace))


class Run:
    """One booking run: the answer key pinned in a scratch folder, then get_trip and a search in the workspace."""

    def __init__(self, value: TripInput, root: Path, *, search: bool = True) -> None:
        self.request = value
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        scratch = root / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.key = solve_booking(value, scratch)
        started = get_trip(value, self.workspace)
        self.run_id = started.run_id
        self.trip = started.trip
        self.offers = []
        if search:
            self.offers = self.search().offers

    def search(self, date_from: str | None = None, date_to: str | None = None, *, origin=None, destination=None):
        trip = self.trip
        return search_flights(
            SearchInput(self.run_id, AirportCode(origin or trip.origin.code),
                        AirportCode(destination or trip.destination.code), date_from or trip.date_from,
                        date_to or trip.date_to),
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
        return judge(self.request, output, self.key, self.workspace)


def failed(verdict: dict) -> list[str]:
    return [entry["id"] for entry in verdict["details"]["checks"] if entry["ok"] is False]


def tool_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


@contextmanager
def hand_built(offers: dict[str, list[dict]], origin: str = "BOS", destination: str = "LHR"):
    """The world replaced, in the tools and the verifier alike, by hand-built offers: {local date: [plain offers]}
    on one route, and no offers on any other route or day. Used for exact boundaries real fares rarely hit."""
    days = {day_number(date): tuple(build_output(offer, Offer) for offer in day) for date, day in offers.items()}

    def day_offers(o, d, day):
        return days.get(day, ()) if (o, d) == (origin, destination) else ()

    saved = world.day_offers, verifier.world.day_offers
    world.day_offers = verifier.world.day_offers = day_offers
    try:
        yield
    finally:
        world.day_offers, verifier.world.day_offers = saved


def offer(offer_id: str, fare: int, *, cabin: str = "ECONOMY", operator: str = "COMMERCIAL", depart: str = "2026-12-03 14:00",
          minutes: tuple = (400,), fees: tuple | None = None, origin: str = "BOS", destination: str = "LHR",
          carrier: str = "British Airways") -> dict:
    """A plain hand-built offer: nonstop, or through a hub when ``minutes`` has two values, leaving at ``depart``,
    local time at the origin (its segments' times are UTC, as the world's are)."""
    fees = fees or tuple(0 for _ in minutes)
    points = [origin, *["DUB"] * (len(minutes) - 1), destination]
    start = minute_number(depart) - world.utc_offset(origin)
    segments = []
    for index, (air, fee) in enumerate(zip(minutes, fees, strict=True)):
        segments.append({
            "origin": points[index], "destination": points[index + 1],
            "flight_number": "CHARTER" if operator == "CHARTER" else f"BA {100 + index}",
            "depart": world.time_text(start), "arrive": world.time_text(start + air), "air_minutes": air,
            "bag_fee_cents": fee,
        })
        start += air + 90
    return {"offer_id": offer_id, "carrier": carrier, "operator": operator, "cabin": cabin, "fare_cents": fare,
            "total_air_minutes": sum(minutes), "depart_date": depart[:10], "depart_local": depart, "segments": segments}
