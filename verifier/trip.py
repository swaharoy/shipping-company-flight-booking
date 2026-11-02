"""get_trip's checks: the trip is the seed's, well formed, and its run was begun."""

from contract import DateMode

from .checks import RUN_ID, date_problem, read_json, result, seed_problem
from .rules import day_number


def verify_input(value):
    problem = seed_problem(value.seed)
    return result(problem is None, problem or "the seed is in range")


def verify_output(input_value, output_value, workspace):
    trip = output_value.trip
    if trip.seed != input_value.seed:
        return result(False, f"the trip is seed {trip.seed}'s, not seed {input_value.seed}'s")
    for name in ("booking_date", "date_from", "date_to"):
        problem = date_problem(name, date_field(trip, name))
        if problem:
            return result(False, problem)
    if day_number(trip.date_to) < day_number(trip.date_from):
        return result(False, "date_to is before date_from")
    if trip.date_mode is DateMode.FIXED and trip.date_to != trip.date_from:
        return result(False, "a FIXED trip departs on one day: date_to must equal date_from")
    if not RUN_ID.fullmatch(output_value.run_id):
        return result(False, f"run_id {output_value.run_id!r} is not a run id")
    receipt = read_json(f"{workspace}/runs/{output_value.run_id}/trip.json")
    if receipt is None or receipt.get("seed") != trip.seed:
        return result(False, f"run {output_value.run_id} has no receipt for seed {trip.seed} in the workspace")
    return result(True, f"seed {trip.seed}'s trip, run {output_value.run_id}")


def date_field(trip, name):
    return {"booking_date": trip.booking_date, "date_from": trip.date_from, "date_to": trip.date_to}[name]
