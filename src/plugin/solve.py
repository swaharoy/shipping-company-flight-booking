"""solve_booking, the reference tool: the trip, every offer and the booking the rules require, pinned
before the agent starts and never shown to it."""

from pathlib import Path

from contract import SolveOutput, TripInput
from plugin import generator, receipts
from plugin.rules import solve


def solve_booking(value: TripInput, workspace: Path) -> SolveOutput:
    world = generator.make(value.seed)
    answer = solve(world.trip, world.offers)
    return SolveOutput(
        scenario=world.scenario,
        pinned_at=receipts.CLOCK(),
        trip=world.trip,
        offers=world.offers,
        refusal=answer.refusal,
        cabin=answer.cabin,
        allowed_offer_ids=answer.allowed,
        lowest_fare_cents=answer.lowest_fare_cents,
        correct_offer_ids=answer.correct,
        out_of_pocket_cents=answer.out_of_pocket_cents,
    )
