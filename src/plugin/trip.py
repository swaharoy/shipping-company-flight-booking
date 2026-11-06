"""get_trip: the trip a request describes, booked as of today, and a new run to book it in."""

from pathlib import Path

from contract import Trip, TripInput, TripOutput
from plugin import receipts, world
from plugin.rules import booking_date_problem, date_mode, request_plain, request_problem


def make_trip(value: TripInput, booking_date: str) -> Trip:
    """The trip of a request on ``booking_date``; raises when the request cannot be booked that day."""
    problem = request_problem(value) or booking_date_problem(value.date_from, value.date_to, booking_date)
    if problem:
        raise ValueError(problem)
    return Trip(
        traveller_name=value.traveller_name,
        traveller_type=value.traveller_type,
        origin=world.airport(value.origin.value),
        destination=world.airport(value.destination.value),
        booking_date=booking_date,
        date_mode=date_mode(value.date_from, value.date_to),
        date_from=value.date_from,
        date_to=value.date_to,
        wants_business=value.wants_business,
        wants_checked_bag=value.wants_checked_bag,
    )


def get_trip(value: TripInput, workspace: Path) -> TripOutput:
    stamp = receipts.CLOCK()
    trip = make_trip(value, stamp[:10])
    run_id = receipts.new_run(workspace, request_plain(value), trip.booking_date, stamp)
    return TripOutput(run_id=run_id, trip=trip)
