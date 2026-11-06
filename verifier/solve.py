"""solve_booking's checks: the pinned trip is the request's, its offers are the simulated world's, and its
answer is what the rules give for them."""

from .checks import result
from .rules import (
    booking_date_problem,
    is_date,
    request_problem,
    same_offers,
    solve,
    trip_matches_request,
)
from .world import airport, offers_between


def verify_input(value):
    problem = request_problem(value)
    return result(problem is None, problem or "a well-formed trip request")


def verify_output(input_value, output_value, workspace):
    problem = answer_key_problem(input_value, output_value)
    return result(problem is None, problem or "the answer key follows the rules")


def answer_key_problem(request, key):
    """What is wrong with a pinned answer key for ``request``, or None."""
    trip = key.trip
    if not trip_matches_request(trip, request):
        return "the answer key's trip is not the one the request asked for"
    if trip.origin != airport(trip.origin.code) or trip.destination != airport(trip.destination.code):
        return "the answer key's airports are not the airport list's"
    if not is_date(trip.booking_date) or not key.pinned_at.startswith(trip.booking_date + " "):
        return "the answer key's booking date is not the day it was pinned"
    problem = booking_date_problem(trip.date_from, trip.date_to, trip.booking_date)
    if problem:
        return f"the answer key's trip cannot be booked: {problem}"
    if not same_offers(key.offers, offers_between(trip.origin.code, trip.destination.code, trip.date_from,
                                                  trip.date_to)):
        return "the answer key's offers are not the route's offers in the trip's dates"
    answer = solve(trip, key.offers)
    pinned = (
        key.refusal, key.cabin, key.allowed_offer_ids, key.lowest_fare_cents, key.correct_offer_ids,
        key.out_of_pocket_cents,
    )
    computed = (
        answer.refusal, answer.cabin, answer.allowed, answer.lowest_fare_cents, answer.correct,
        answer.out_of_pocket_cents,
    )
    if pinned != computed:
        return "the answer key's booking is not what the rules give for its trip and offers"
    return None
