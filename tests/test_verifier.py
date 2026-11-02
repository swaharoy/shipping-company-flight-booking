"""The verifier on correct, wrong, missing, malformed, tampered and boundary results, built the way the
sandbox builds them (build_output of plain JSON)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import Run, booking, failed, judge, tool_input
from slimconfig import build_output, plain_output

import verifier
from contract import SearchInput, SearchOutput, SolveOutput, TripInput, TripOutput
from plugin import generator
from plugin.rules import advance_ok, departure_date, in_window, out_of_pocket


def seed_where(scenario: str, test, start: int = 0) -> int:
    """The first seed of a scenario whose world passes ``test(world)``."""
    index = generator.SCENARIOS.index(scenario)
    for seed in range(start + index, 10_000, 10):
        if test(generator.make(seed)):
            return seed
    raise LookupError(scenario)


def offer_where(run: Run, test) -> str:
    return next(o.offer_id for o in run.key.offers if test(o))


# Correct --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", generator.SCENARIOS)
def test_the_gold_booking_of_every_scenario_is_valid(tmp_path: Path, scenario: str) -> None:
    run = Run(100 + generator.SCENARIOS.index(scenario), tmp_path)
    verdict = run.judge(run.gold())
    assert verdict["valid"] is True and verdict["score"] == 1.0, verdict["message"]
    assert all(entry["ok"] is True for entry in verdict["details"]["checks"])


def test_exactly_the_correct_offers_pass_over_200_seeds(tmp_path: Path) -> None:
    """Every offer the agent could book from its search is judged: valid if and only if the answer key
    lists it as correct (ties included) with its exact out-of-pocket."""
    for seed in range(200):
        run = Run(seed, tmp_path / str(seed))
        if run.key.refusal.value != "NONE":
            continue
        for offer in run.offers:
            paid = out_of_pocket(run.trip, offer)
            verdict = run.judge(booking(run.run_id, offer.offer_id, oop=paid))
            assert verdict["valid"] is (offer.offer_id in run.key.correct_offer_ids), (seed, offer.offer_id)


def test_a_consultant_refused_without_searching_is_valid(tmp_path: Path) -> None:
    run = Run(4, tmp_path, search=False)
    assert run.judge(booking(run.run_id, booked=False, refusal="CONSULTANT"))["valid"] is True


# Wrong ----------------------------------------------------------------------------------------------


def wrong(tmp_path: Path, seed: int, pick, check_id: str, *, oop=None) -> dict:
    run = Run(seed, tmp_path)
    offer_id = offer_where(run, pick(run))
    offer = run.offer(offer_id)
    # Search widely so any offer of the seed was seen; then only the policy can fail it.
    run.search(run.key.offers[0].segments[0].depart[:10], departure_date(run.key.offers[-1]))
    paid = out_of_pocket(run.trip, offer) if oop is None else oop
    verdict = run.judge(booking(run.run_id, offer_id, oop=paid))
    assert verdict["valid"] is False and failed(verdict)[0] == check_id, verdict["message"]
    assert verdict["score"] == 0.0
    return verdict


def test_a_charter_is_refused(tmp_path: Path) -> None:
    seed = seed_where("domestic-economy", lambda w: any(o.operator.value == "CHARTER" and
                                                         in_window(w.trip, o) for o in w.offers))
    wrong(tmp_path, seed, lambda run: lambda o: o.operator.value == "CHARTER" and in_window(run.trip, o), "commercial")


def test_first_class_is_refused(tmp_path: Path) -> None:
    seed = seed_where("domestic-economy", lambda w: any(o.cabin.value == "FIRST" and in_window(w.trip, o)
                                                         for o in w.offers))
    verdict = wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "FIRST" and in_window(run.trip, o), "cabin")
    assert "never" in verdict["message"]


def test_business_on_a_domestic_trip_is_refused(tmp_path: Path) -> None:
    seed = seed_where("domestic-economy", lambda w: any(o.cabin.value == "BUSINESS" and in_window(w.trip, o)
                                                         for o in w.offers))
    wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "BUSINESS" and in_window(run.trip, o), "cabin")


def test_business_at_exactly_360_minutes_is_refused(tmp_path: Path) -> None:
    seed = seed_where("exactly-360-minutes", lambda w: True)
    wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "BUSINESS" and o.total_air_minutes == 360, "cabin")


def test_economy_when_business_is_wanted_and_allowed_is_refused(tmp_path: Path) -> None:
    seed = seed_where("long-haul-business", lambda w: w.trip.date_mode.value == "FIXED")
    verdict = wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "ECONOMY" and o.operator.value ==
                    "COMMERCIAL" and in_window(run.trip, o), "cabin")
    assert "book business" in verdict["message"]


def test_a_cheaper_business_fare_not_wanted_is_refused(tmp_path: Path) -> None:
    seed = seed_where("business-cheaper", lambda w: not w.trip.wants_business)
    wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "BUSINESS" and in_window(run.trip, o), "cabin")


def test_a_flight_under_7_days_ahead_is_refused_when_a_later_one_exists(tmp_path: Path) -> None:
    seed = seed_where("flexible-later-possible", lambda w: True)
    verdict = wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "ECONOMY" and o.operator.value ==
                    "COMMERCIAL" and in_window(run.trip, o) and not advance_ok(run.trip, o), "dates")
    assert "under 7 days" in verdict["message"]


def test_a_flight_outside_the_window_is_refused(tmp_path: Path) -> None:
    seed = seed_where("domestic-economy", lambda w: True)
    wrong(tmp_path, seed, lambda run: lambda o: o.cabin.value == "ECONOMY" and not in_window(run.trip, o), "dates")


def test_a_fare_one_cent_over_the_margin_is_refused(tmp_path: Path) -> None:
    seed = seed_where("domestic-economy", lambda w: not w.trip.wants_checked_bag)
    run = Run(seed, tmp_path)
    over = run.key.lowest_fare_cents + 10_001
    verdict = wrong(tmp_path / "w", seed, lambda r: lambda o: o.fare_cents == over and in_window(r.trip, o), "fare")
    assert "$100" not in verdict["message"] or "limit" in verdict["message"]


def test_a_dearer_bag_than_needed_is_refused(tmp_path: Path) -> None:
    seed = seed_where("checked-bag-trade-off", lambda w: w.trip.date_mode.value == "FIXED")
    run = Run(seed, tmp_path)
    lowest = run.key.lowest_fare_cents
    wrong(tmp_path / "w", seed, lambda r: lambda o: o.fare_cents == lowest and in_window(r.trip, o)
          and o.cabin is r.key.cabin, "bag")


def test_a_wrong_out_of_pocket_is_refused(tmp_path: Path) -> None:
    seed = seed_where("checked-bag-trade-off", lambda w: True)
    run = Run(seed, tmp_path)
    gold = run.gold()
    verdict = run.judge(gold | {"traveller_out_of_pocket_cents": gold["traveller_out_of_pocket_cents"] + 1})
    assert verdict["valid"] is False and failed(verdict) == ["out-of-pocket"]
    assert verdict["score"] == 0.0


def test_booking_a_consultant_is_refused(tmp_path: Path) -> None:
    run = Run(14, tmp_path)
    offer = run.offers[0]
    verdict = run.judge(booking(run.run_id, offer.offer_id, oop=out_of_pocket(run.trip, offer)))
    assert verdict["valid"] is False and failed(verdict) == ["refusal"] and verdict["score"] == 0.0
    assert "consultant" in verdict["message"]


@pytest.mark.parametrize(("seed", "refusal"), [(10, "NO_COMPLIANT_FLIGHT"), (18, "CONSULTANT")])
def test_a_wrong_refusal_is_refused(tmp_path: Path, seed: int, refusal: str) -> None:
    run = Run(seed, tmp_path)
    verdict = run.judge(booking(run.run_id, booked=False, refusal=refusal))
    assert verdict["valid"] is False and failed(verdict) == ["refusal"]


def test_booking_when_only_charters_fly_is_refused(tmp_path: Path) -> None:
    run = Run(8, tmp_path)
    offer = run.offers[0]
    verdict = run.judge(booking(run.run_id, offer.offer_id))
    assert verdict["valid"] is False and failed(verdict) == ["refusal"]


@pytest.mark.parametrize(
    "changes",
    [
        {"booked": True, "refusal": "CONSULTANT"},
        {"booked": False, "refusal": "NONE"},
        {"booked": False, "refusal": "NO_COMPLIANT_FLIGHT", "offer_id": "F01"},
        {"booked": False, "refusal": "NO_COMPLIANT_FLIGHT", "traveller_out_of_pocket_cents": 5},
    ],
)
def test_an_inconsistent_booking_or_refusal_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(18, tmp_path)
    verdict = run.judge(run.gold() | changes)
    # booked with no offer fails the offer-seen gate first; the others fail the refusal check.
    assert verdict["valid"] is False and failed(verdict)[0] in ("refusal", "offer-seen")


# Missing --------------------------------------------------------------------------------------------


def test_booking_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(10, tmp_path, search=False)
    verdict = run.judge(booking(run.run_id, run.key.correct_offer_ids[0]))
    assert verdict["valid"] is False and failed(verdict) == ["searched"] and verdict["score"] == 0.0


@pytest.mark.parametrize("offer_id", ["F99", "", "f01"])
def test_an_offer_never_returned_is_refused(tmp_path: Path, offer_id: str) -> None:
    run = Run(10, tmp_path)
    verdict = run.judge(booking(run.run_id, offer_id))
    assert verdict["valid"] is False and failed(verdict) == ["offer-seen"] and verdict["score"] == 0.0


def test_an_offer_of_a_day_never_searched_is_refused(tmp_path: Path) -> None:
    run = Run(10, tmp_path)
    unseen = next(o.offer_id for o in run.key.offers if not in_window(run.trip, o))
    verdict = run.judge(booking(run.run_id, unseen))
    assert failed(verdict) == ["offer-seen"]


@pytest.mark.parametrize("run_id", ["0123456789ab", "not-a-run", ""])
def test_a_run_that_does_not_exist_is_refused(tmp_path: Path, run_id: str) -> None:
    run = Run(10, tmp_path)
    verdict = run.judge(run.gold() | {"run_id": run_id})
    assert verdict["valid"] is False and failed(verdict) == ["this-run"]


def test_no_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(10, tmp_path)
    verdict = judge(10, run.gold(), None, run.workspace)
    assert verdict["valid"] is False and failed(verdict) == ["answer-key"]


def test_an_answer_key_for_another_seed_is_refused(tmp_path: Path) -> None:
    run = Run(10, tmp_path)
    verdict = judge(20, run.gold(), run.key, run.workspace)
    assert verdict["valid"] is False and failed(verdict) == ["answer-key"]


# Tampering ------------------------------------------------------------------------------------------


def edit(path: Path, **changes) -> None:
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"offer_ids": []}, {"seed": 11}, {"date_to": "x"}])
def test_a_tampered_search_receipt_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(10, tmp_path)
    edit(run.workspace / "runs" / run.run_id / "search-1.json", **changes)
    verdict = run.judge(run.gold())
    assert verdict["valid"] is False and failed(verdict) == ["receipts-match"] and verdict["score"] == 0.0


def test_a_run_begun_before_the_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(10, tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", started_at="2026-01-01 00:00:00.000000")
    verdict = run.judge(run.gold())
    assert verdict["valid"] is False and failed(verdict) == ["this-run"]
    assert "earlier run" in verdict["message"]


def test_a_run_of_another_seed_is_refused(tmp_path: Path) -> None:
    other = Run(20, tmp_path)
    run = Run(10, tmp_path)
    verdict = run.judge(run.gold() | {"run_id": other.run_id})
    assert verdict["valid"] is False and failed(verdict) == ["this-run"]


def test_a_tampered_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(10, tmp_path)
    run.key.correct_offer_ids = [o.offer_id for o in run.key.offers]
    verdict = run.judge(run.gold())
    assert verdict["valid"] is False and failed(verdict) == ["answer-key"]


# Determinism and the tools' own checks -----------------------------------------------------------------


def test_the_verdict_is_the_same_twice(tmp_path: Path) -> None:
    run = Run(17, tmp_path)
    for output in (run.gold(), booking(run.run_id, run.offers[0].offer_id, oop=12)):
        assert json.dumps(run.judge(output), sort_keys=True) == json.dumps(run.judge(output), sort_keys=True)


def test_tool_inputs_are_checked() -> None:
    assert tool_input("get_trip", {"seed": 0})["valid"] is True
    assert tool_input("get_trip", {"seed": 9999})["valid"] is True
    assert tool_input("get_trip", {"seed": 10_000})["valid"] is False
    assert tool_input("solve_booking", {"seed": -1})["valid"] is False
    good = {"seed": 3, "run_id": "", "origin": "JFK", "destination": "LAX", "date_from": "2027-03-01",
            "date_to": "2027-03-15"}
    assert tool_input("search_flights", good)["valid"] is True
    assert tool_input("search_flights", good | {"run_id": "0123456789ab"})["valid"] is True
    for bad in ({"date_to": "2027-03-16"}, {"date_to": "2027-02-28"}, {"date_from": "2027-02-30"},
                {"run_id": "nope"}, {"seed": 10_000}):
        assert tool_input("search_flights", good | bad)["valid"] is False, bad


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    run = Run(25, tmp_path)
    trip_out = build_output(plain_output(TripOutput(run.run_id, run.trip)), TripOutput)
    assert verifier.verify_output("get_trip", TripInput(25), trip_out, str(run.workspace))["valid"] is True
    assert verifier.verify_output("get_trip", TripInput(26), trip_out, str(run.workspace))["valid"] is False
    query = SearchInput(25, run.run_id, run.trip.origin.code, run.trip.destination.code, run.trip.date_from,
                        run.trip.date_to)
    found = build_output(plain_output(SearchOutput(run.run_id, run.offers)), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is True
    shifted = SearchInput(**(plain_output(query) | {"date_to": run.trip.date_from}))
    assert verifier.verify_output("search_flights", shifted, found, str(run.workspace))["valid"] is False
    key = build_output(plain_output(run.key), SolveOutput)
    assert verifier.verify_output("solve_booking", TripInput(25), key, str(tmp_path))["valid"] is True
    key.out_of_pocket_cents += 1
    assert verifier.verify_output("solve_booking", TripInput(25), key, str(tmp_path))["valid"] is False


def test_tool_tasks_are_judged_as_their_tools(tmp_path: Path) -> None:
    run = Run(30, tmp_path)
    trip_out = build_output(plain_output(TripOutput(run.run_id, run.trip)), TripOutput)
    assert verifier.verify_task("show-trip", TripInput(30), trip_out, None, str(run.workspace))["valid"] is True
    assert verifier.verify_task("show-trip", TripInput(31), trip_out, None, str(run.workspace))["valid"] is False
