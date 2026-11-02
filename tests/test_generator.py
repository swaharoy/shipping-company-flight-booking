"""The world a seed makes: the same on every machine, every scenario as promised, and an answer key that
agrees with an independent reading of the rules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from oracle import booking_answer
from slimconfig import plain_output

from contract import TripInput
from plugin import generator, solve_booking
from plugin.rules import departure_date, solve

GOLDEN = {
    0: "886a1f8f529fd163", 1: "e7139d4622cef268", 2: "51fb3fd103ce79f0", 3: "5cf07a518683ec78",
    4: "3a27b7dfa4b0de05", 5: "2a1ff8bbd6e93ba0", 6: "ec31bd224045561c", 7: "8b8d44d4d422dafd",
    8: "74f329b00c38c69e", 9: "7e7e4879d649ea78", 1234: "8c1825b35e898539", 9999: "02dea740cf6cf386",
}


def digest(world) -> str:
    text = json.dumps({"trip": plain_output(world.trip), "offers": [plain_output(o) for o in world.offers]},
                      sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize("seed", sorted(GOLDEN))
def test_a_seed_makes_the_same_world_everywhere(seed: int) -> None:
    assert digest(generator.make(seed)) == GOLDEN[seed]
    assert digest(generator.make(seed)) == digest(generator.make(seed))


def test_every_seed_makes_its_scenario() -> None:
    # make() raises when a seed does not make its scenario; every seed a member may type is tried.
    scenarios = {}
    for seed in range(10_000):
        world = generator.make(seed)
        assert world.scenario == generator.SCENARIOS[seed % 10]
        scenarios[world.scenario] = scenarios.get(world.scenario, 0) + 1
    assert set(scenarios) == set(generator.SCENARIOS)


@pytest.mark.parametrize("seed", [-1, 10_000])
def test_a_seed_out_of_range_is_refused(seed: int) -> None:
    with pytest.raises(ValueError):
        generator.make(seed)


def test_the_answer_key_agrees_with_an_independent_reading_for_1000_seeds(tmp_path: Path) -> None:
    for seed in range(1000):
        key = solve_booking(TripInput(seed), tmp_path)
        refusal, correct, paid = booking_answer(key.trip, key.offers)
        assert key.refusal.value == refusal, seed
        assert set(key.correct_offer_ids) == correct, seed
        assert key.out_of_pocket_cents == paid, seed


def test_offers_are_well_formed() -> None:
    for seed in range(0, 10_000, 7):
        world = generator.make(seed)
        ids = [offer.offer_id for offer in world.offers]
        assert len(set(ids)) == len(ids)
        for offer in world.offers:
            assert offer.total_air_minutes == sum(s.air_minutes for s in offer.segments)
            assert offer.segments[0].origin == world.trip.origin.code
            assert offer.segments[-1].destination == world.trip.destination.code
            assert offer.fare_cents > 0
            for first, second in zip(offer.segments, offer.segments[1:]):
                assert first.destination == second.origin and first.arrive < second.depart
        departures = [(departure_date(o), o.segments[0].depart) for o in world.offers]
        assert departures == sorted(departures)


def test_scenarios_plant_their_boundaries() -> None:
    """Across the seeds, each boundary the verifier is tested on actually occurs."""
    seen = set()
    for seed in range(2000):
        world = generator.make(seed)
        answer = solve(world.trip, world.offers)
        fares = {o.fare_cents for o in world.offers if o.offer_id in answer.allowed}
        if answer.refusal.value == "NONE" and answer.lowest_fare_cents + 10_000 in fares:
            seen.add("fare exactly +$100")
        if any(o.total_air_minutes == 360 and o.cabin.value == "BUSINESS" for o in world.offers):
            seen.add("business exactly 360 min")
        if any(o.total_air_minutes == 361 and o.cabin.value == "BUSINESS" for o in world.offers):
            seen.add("business 361 min")
        fees = {s.bag_fee_cents for o in world.offers for s in o.segments}
        seen.update({f"bag fee {fee}" for fee in fees & {3000, 3001}})
        if world.scenario == "flexible-later-possible" and any(
            o.offer_id in answer.correct and departure_date(o) == _plus(world.trip.booking_date, 7) for o in world.offers
        ):
            seen.add("exactly 7 days ahead")
    assert seen == {"fare exactly +$100", "business exactly 360 min", "business 361 min", "bag fee 3000",
                    "bag fee 3001", "exactly 7 days ahead"}


def _plus(date: str, days: int) -> str:
    from plugin.rules import date_of, day_number

    return date_of(day_number(date) + days)
