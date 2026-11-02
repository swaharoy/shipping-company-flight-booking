"""solve_booking's checks: the pinned answer is what the rules give for the pinned trip and offers."""

from .checks import result, seed_problem
from .rules import solve


def verify_input(value):
    problem = seed_problem(value.seed)
    return result(problem is None, problem or "the seed is in range")


def verify_output(input_value, output_value, workspace):
    problem = answer_key_problem(input_value.seed, output_value)
    return result(problem is None, problem or "the answer key follows the rules")


def answer_key_problem(seed, key):
    """What is wrong with a pinned answer key for ``seed``, or None."""
    if key.trip.seed != seed:
        return f"the answer key is seed {key.trip.seed}'s, not seed {seed}'s"
    ids = [offer.offer_id for offer in key.offers]
    if len(set(ids)) != len(ids):
        return "the answer key lists an offer twice"
    answer = solve(key.trip, key.offers)
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
