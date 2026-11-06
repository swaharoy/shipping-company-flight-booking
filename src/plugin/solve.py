"""solve_booking, the reference tool: the trip booked as of today, every offer in its dates and the booking
the rules require, pinned before the agent starts and never shown to it."""

from pathlib import Path

from contract import SolveOutput, TripInput
from plugin import receipts, world
from plugin.rules import solve
from plugin.trip import make_trip


def solve_booking(value: TripInput, workspace: Path) -> SolveOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    offers = world.offers_between(trip.origin.code, trip.destination.code, trip.date_from, trip.date_to)
    answer = solve(trip, offers)
    return SolveOutput(
        pinned_at=stamp,
        trip=trip,
        offers=offers,
        refusal=answer.refusal,
        cabin=answer.cabin,
        allowed_offer_ids=answer.allowed,
        lowest_fare_cents=answer.lowest_fare_cents,
        correct_offer_ids=answer.correct,
        out_of_pocket_cents=answer.out_of_pocket_cents,
    )
