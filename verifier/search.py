"""search_flights' checks: a well-formed query, and only offers that match it, in departure order."""

from .checks import RUN_ID, date_problem, result, seed_problem
from .rules import SEARCH_MAX_DAYS, day_number, matches_search, minute_number


def verify_input(value):
    problem = seed_problem(value.seed)
    for name, date in (("date_from", value.date_from), ("date_to", value.date_to)):
        problem = problem or date_problem(name, date)
    if problem:
        return result(False, problem)
    span = day_number(value.date_to) - day_number(value.date_from)
    if not 0 <= span <= SEARCH_MAX_DAYS:
        return result(False, f"date_to must be 0 to {SEARCH_MAX_DAYS} days after date_from")
    if value.run_id and not RUN_ID.fullmatch(value.run_id):
        return result(False, f"run_id {value.run_id!r} is not one get_trip returned")
    return result(True, "a well-formed search")


def verify_output(input_value, output_value, workspace):
    if output_value.run_id != input_value.run_id:
        return result(False, "the result names another run")
    ids = [offer.offer_id for offer in output_value.offers]
    if len(set(ids)) != len(ids):
        return result(False, "an offer is listed twice")
    q = input_value
    previous = None
    for offer in output_value.offers:
        if not offer.segments:
            return result(False, f"offer {offer.offer_id} has no segments")
        if not matches_search(offer, q.origin, q.destination, q.date_from, q.date_to):
            return result(False, f"offer {offer.offer_id} does not match the search")
        if offer.total_air_minutes != sum(segment.air_minutes for segment in offer.segments):
            return result(False, f"offer {offer.offer_id}'s total_air_minutes is not its segments' sum")
        depart = minute_number(offer.segments[0].depart)
        if previous is not None and depart < previous:
            return result(False, "offers are not in departure order")
        previous = depart
    return result(True, f"{len(ids)} offers match the search")
