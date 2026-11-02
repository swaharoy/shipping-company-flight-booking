"""get_trip: the trip a seed makes, and a new run to book it in."""

from pathlib import Path

from contract import TripInput, TripOutput
from plugin import generator, receipts


def get_trip(value: TripInput, workspace: Path) -> TripOutput:
    world = generator.make(value.seed)
    run_id = receipts.new_run(workspace, value.seed)
    return TripOutput(run_id=run_id, trip=world.trip)
