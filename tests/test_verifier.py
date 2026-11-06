"""The verifier on correct, wrong, missing, malformed, tampered and boundary results, built the way the
sandbox builds them (build_output of plain JSON). Real simulated offers where they show the case, and
hand-built offers (in the tools and the verifier alike) for exact boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from helpers import Run, booking, failed, hand_built, judge, offer, request, requests, tool_input
from slimconfig import build_output, plain_output

import verifier
from contract import (
    AirportCode,
    RequirementsInput,
    RequirementsOutput,
    SearchInput,
    SearchOutput,
    SolveOutput,
    Topic,
    TripOutput,
)
from plugin import booking_requirements
from plugin.rules import out_of_pocket


def valid(verdict: dict) -> bool:
    return verdict["valid"] is True and verdict["score"] == 1.0


def refused(verdict: dict, *check_ids: str) -> bool:
    return verdict["valid"] is False and verdict["score"] == 0.0 and failed(verdict) == list(check_ids)


# Correct --------------------------------------------------------------------------------------------


def test_the_gold_booking_is_valid_for_varied_requests(tmp_path: Path) -> None:
    for index, value in enumerate(requests(60, "gold")):
        run = Run(value, tmp_path / str(index))
        verdict = run.judge(run.gold())
        assert valid(verdict), (plain_output(value), verdict["message"])
        assert all(entry["ok"] is True for entry in verdict["details"]["checks"])


def test_exactly_the_correct_offers_pass(tmp_path: Path) -> None:
    """Every offer the agent could book from its search is judged: valid if and only if the answer key
    lists it as correct (ties included) with its exact out-of-pocket."""
    judged = 0
    for index, value in enumerate(requests(80, "every-offer")):
        run = Run(value, tmp_path / str(index))
        if run.key.refusal.value != "NONE":
            continue
        for found in run.offers:
            verdict = run.judge(booking(run.run_id, found.offer_id, oop=out_of_pocket(run.trip, found)))
            assert verdict["valid"] is (found.offer_id in run.key.correct_offer_ids), (index, found.offer_id)
            judged += 1
    assert judged > 500


def test_a_consultant_refused_without_searching_is_valid(tmp_path: Path) -> None:
    run = Run(request(traveller_type="CONSULTANT"), tmp_path, search=False)
    assert valid(run.judge(booking(run.run_id, booked=False, refusal="CONSULTANT")))


def test_a_non_employee_is_booked_like_an_employee(tmp_path: Path) -> None:
    employee = Run(request(wants_checked_bag=True), tmp_path / "e")
    guest = Run(request(traveller_type="NON_EMPLOYEE", wants_checked_bag=True), tmp_path / "g")
    assert guest.key.correct_offer_ids == employee.key.correct_offer_ids
    assert valid(guest.judge(guest.gold()))


# Wrong, on real simulated offers -----------------------------------------------------------------------


def first_request(test, salt: str):
    """The first varied request whose answer key passes ``test(key)``."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        for index, value in enumerate(requests(3000, salt)):
            from plugin import solve_booking

            key = solve_booking(value, Path(folder))
            if test(key):
                return value
            if index > 3000:
                break
    raise LookupError(salt)


def wrong(run: Run, pick, check_id: str) -> dict:
    chosen = next(o for o in run.offers if pick(o))
    verdict = run.judge(booking(run.run_id, chosen.offer_id, oop=out_of_pocket(run.trip, chosen)))
    assert refused(verdict, check_id), verdict["message"]
    return verdict


def domestic(key) -> bool:
    return key.trip.origin.country == key.trip.destination.country == "US"


def test_a_charter_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.refusal.value == "NONE" and k.trip.traveller_type.value != "CONSULTANT"
                          and any(o.operator.value == "CHARTER" for o in k.offers), "charter")
    verdict = wrong(Run(value, tmp_path), lambda o: o.operator.value == "CHARTER", "commercial")
    assert "charter" in verdict["message"]


def test_domestic_first_class_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.refusal.value == "NONE" and domestic(k)
                          and any(o.cabin.value == "FIRST" for o in k.offers), "first")
    verdict = wrong(Run(value, tmp_path), lambda o: o.cabin.value == "FIRST", "cabin")
    assert "never" in verdict["message"]


def test_business_on_a_domestic_trip_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.refusal.value == "NONE" and domestic(k) and k.trip.wants_business
                          and any(o.cabin.value == "BUSINESS" for o in k.offers), "domestic-business")
    verdict = wrong(Run(value, tmp_path), lambda o: o.cabin.value == "BUSINESS", "cabin")
    assert "domestic" in verdict["message"]


def test_economy_when_business_is_wanted_and_allowed_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.cabin.value == "BUSINESS" and k.trip.date_mode.value == "FIXED", "business")
    verdict = wrong(Run(value, tmp_path), lambda o: o.cabin.value == "ECONOMY" and o.operator.value == "COMMERCIAL",
                    "cabin")
    assert "book business" in verdict["message"]


def test_business_not_wanted_is_refused(tmp_path: Path) -> None:
    run = Run(request(wants_business=False), tmp_path)
    verdict = wrong(run, lambda o: o.cabin.value == "BUSINESS", "cabin")
    assert "did not ask" in verdict["message"]


def test_a_dearer_bag_than_needed_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.refusal.value == "NONE" and k.trip.wants_checked_bag and any(
        o.offer_id in k.allowed_offer_ids and o.offer_id not in k.correct_offer_ids
        and o.fare_cents <= k.lowest_fare_cents + 10_000 for o in k.offers), "bag")
    run = Run(value, tmp_path)
    key = run.key
    wrong(run, lambda o: o.offer_id in key.allowed_offer_ids and o.offer_id not in key.correct_offer_ids
          and o.fare_cents <= key.lowest_fare_cents + 10_000, "bag")


def test_a_fare_over_the_margin_is_refused(tmp_path: Path) -> None:
    value = first_request(lambda k: k.refusal.value == "NONE" and any(
        o.offer_id in k.allowed_offer_ids and o.fare_cents > k.lowest_fare_cents + 10_000 for o in k.offers), "fare")
    run = Run(value, tmp_path)
    wrong(run, lambda o: o.offer_id in run.key.allowed_offer_ids and o.fare_cents > run.key.lowest_fare_cents + 10_000,
          "fare")


def test_a_wrong_out_of_pocket_is_refused(tmp_path: Path) -> None:
    run = Run(request(wants_checked_bag=True), tmp_path)
    gold = run.gold()
    verdict = run.judge(gold | {"traveller_out_of_pocket_cents": gold["traveller_out_of_pocket_cents"] + 1})
    assert refused(verdict, "out-of-pocket")


def test_booking_a_consultant_is_refused(tmp_path: Path) -> None:
    run = Run(request(traveller_type="CONSULTANT"), tmp_path)
    verdict = run.judge(booking(run.run_id, run.offers[0].offer_id, oop=out_of_pocket(run.trip, run.offers[0])))
    assert refused(verdict, "refusal") and "consultant" in verdict["message"]


@pytest.mark.parametrize("refusal", ["NO_COMPLIANT_FLIGHT", "CONSULTANT"])
def test_refusing_a_bookable_trip_is_refused(tmp_path: Path, refusal: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run.run_id, booked=False, refusal=refusal)), "refusal")


@pytest.mark.parametrize(
    "changes",
    [
        {"booked": True, "refusal": "CONSULTANT"},
        {"booked": False, "refusal": "NONE"},
        {"booked": False, "refusal": "NO_COMPLIANT_FLIGHT", "offer_id": "20261203-01"},
        {"booked": False, "refusal": "NO_COMPLIANT_FLIGHT", "traveller_out_of_pocket_cents": 5},
    ],
)
def test_an_inconsistent_booking_or_refusal_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    verdict = run.judge(run.gold() | changes)
    assert verdict["valid"] is False and failed(verdict)[0] == "refusal"


def test_an_offer_on_another_day_than_the_trip_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    later = run.search("2026-12-04", "2026-12-04").offers[0]
    verdict = run.judge(booking(run.run_id, later.offer_id, oop=out_of_pocket(run.trip, later)))
    assert refused(verdict, "dates")


def test_an_offer_on_another_route_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    elsewhere = run.search(origin="JFK").offers[0]
    verdict = run.judge(booking(run.run_id, elsewhere.offer_id))
    assert refused(verdict, "offer-seen") and "not the trip's route" in verdict["message"]


# Exact boundaries, on hand-built offers -----------------------------------------------------------------

DAY = "2026-12-03"


def boundary(tmp_path: Path, offers: list[dict], value, offer_id: str, *, oop: int = 0, day: str = DAY) -> dict:
    by_day: dict[str, list[dict]] = {}
    for one in offers:
        by_day.setdefault(one["segments"][0]["depart"][:10], []).append(one)
    route = value.origin.value, value.destination.value
    with hand_built(by_day, *route):
        run = Run(value, tmp_path)
        return run.judge(booking(run.run_id, offer_id, oop=oop))


def test_business_at_exactly_360_minutes_is_refused_and_361_is_booked(tmp_path: Path) -> None:
    value = request(origin="JFK", destination="BOG", wants_business=True)  # international, not transatlantic
    offers = [offer("20261203-01", 40_000, origin="JFK", destination="BOG"),
              offer("20261203-02", 150_000, cabin="BUSINESS", minutes=(360,), origin="JFK", destination="BOG")]
    assert refused(boundary(tmp_path / "a", offers, value, "20261203-02"), "cabin")
    assert valid(boundary(tmp_path / "b", offers, value, "20261203-01"))
    offers[1]["segments"][0]["air_minutes"] = offers[1]["total_air_minutes"] = 361
    assert valid(boundary(tmp_path / "c", offers, value, "20261203-02"))
    assert refused(boundary(tmp_path / "d", offers, value, "20261203-01"), "cabin")


def test_transatlantic_business_under_six_hours_is_booked(tmp_path: Path) -> None:
    value = request(wants_business=True)
    offers = [offer("20261203-01", 40_000), offer("20261203-02", 150_000, cabin="BUSINESS", minutes=(340,))]
    assert valid(boundary(tmp_path, offers, value, "20261203-02"))


@pytest.mark.parametrize(("extra", "ok"), [(10_000, True), (10_001, False)])
def test_a_fare_exactly_100_dollars_over_passes_and_one_cent_more_fails(tmp_path: Path, extra: int, ok: bool) -> None:
    offers = [offer("20261203-01", 50_000), offer("20261203-02", 50_000 + extra)]
    verdict = boundary(tmp_path, offers, request(), "20261203-02")
    assert valid(verdict) if ok else refused(verdict, "fare")


@pytest.mark.parametrize(("fee", "paid"), [(3_000, 0), (3_001, 1)])
def test_a_bag_fee_of_exactly_30_dollars_costs_the_traveller_nothing(tmp_path: Path, fee: int, paid: int) -> None:
    offers = [offer("20261203-01", 50_000, fees=(fee,))]
    assert valid(boundary(tmp_path, offers, request(wants_checked_bag=True), "20261203-01", oop=paid))


def test_a_pricier_fare_including_the_bag_must_be_booked(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 50_000, fees=(4_500,)), offer("20261203-02", 59_000, fees=(0,))]
    value = request(wants_checked_bag=True)
    assert refused(boundary(tmp_path / "a", offers, value, "20261203-01", oop=1_500), "bag")
    assert valid(boundary(tmp_path / "b", offers, value, "20261203-02"))


def test_exactly_7_days_ahead_counts_and_6_does_not(tmp_path: Path) -> None:
    value = request(date_from="2026-11-10", date_to="2026-11-14")  # booked 2026-11-05
    offers = [offer("20261111-01", 30_000, depart="2026-11-11 14:00"),
              offer("20261112-01", 45_000, depart="2026-11-12 14:00")]
    assert refused(boundary(tmp_path / "a", offers, value, "20261111-01"), "dates")
    assert valid(boundary(tmp_path / "b", offers, value, "20261112-01"))


def test_a_window_entirely_under_7_days_takes_any_day(tmp_path: Path) -> None:
    value = request(date_from="2026-11-06", date_to="2026-11-08")
    offers = [offer("20261106-01", 30_000, depart="2026-11-06 14:00"),
              offer("20261108-01", 45_000, depart="2026-11-08 14:00")]
    assert valid(boundary(tmp_path / "a", offers, value, "20261106-01"))
    assert refused(boundary(tmp_path / "b", offers, value, "20261108-01"), "fare")


def test_a_fixed_date_under_7_days_is_kept(tmp_path: Path) -> None:
    value = request(date_from="2026-11-07", date_to="2026-11-07")
    offers = [offer("20261107-01", 30_000, depart="2026-11-07 14:00")]
    assert valid(boundary(tmp_path, offers, value, "20261107-01"))


def test_only_charters_and_first_class_means_no_compliant_flight(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 30_000, operator="CHARTER", carrier="VistaJet"),
              offer("20261203-02", 90_000, cabin="FIRST")]
    by_day = {DAY: offers}
    with hand_built(by_day):
        run = Run(request(), tmp_path)
        assert run.key.refusal.value == "NO_COMPLIANT_FLIGHT"
        assert valid(run.judge(booking(run.run_id, booked=False, refusal="NO_COMPLIANT_FLIGHT")))
        assert refused(run.judge(booking(run.run_id, "20261203-01")), "refusal")


def test_a_business_fare_below_economy_not_wanted_is_refused(tmp_path: Path) -> None:
    offers = [offer("20261203-01", 50_000), offer("20261203-02", 45_000, cabin="BUSINESS")]
    assert refused(boundary(tmp_path, offers, request(), "20261203-02"), "cabin")


# Missing --------------------------------------------------------------------------------------------


def test_booking_without_a_search_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path, search=False)
    assert refused(run.judge(booking(run.run_id, run.key.correct_offer_ids[0])), "searched")


@pytest.mark.parametrize("offer_id", ["20261203-99", "", "F01"])
def test_an_offer_never_returned_is_refused(tmp_path: Path, offer_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run.run_id, offer_id)), "offer-seen")


def test_an_offer_of_a_day_never_searched_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(booking(run.run_id, "20261204-01")), "offer-seen")


@pytest.mark.parametrize("run_id", ["0123456789ab", "not-a-run", ""])
def test_a_run_that_does_not_exist_is_refused(tmp_path: Path, run_id: str) -> None:
    run = Run(request(), tmp_path)
    assert refused(run.judge(run.gold() | {"run_id": run_id}), "this-run")


def test_no_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(run.request, run.gold(), None, run.workspace), "answer-key")


def test_an_answer_key_for_another_request_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    assert refused(judge(request(wants_checked_bag=True), run.gold(), run.key, run.workspace), "answer-key")


# Tampering ------------------------------------------------------------------------------------------


def edit(path: Path, **changes) -> None:
    value = json.loads(path.read_text())
    value.update(changes)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("changes", [{"digest": "0" * 64}, {"offer_ids": []}, {"origin": "XXX"}, {"date_to": "x"},
                                     {"date_from": "2026-12-04"}])
def test_a_tampered_search_receipt_is_refused(tmp_path: Path, changes: dict) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "search-1.json", **changes)
    assert refused(run.judge(run.gold()), "receipts-match")


def test_a_run_begun_before_the_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", started_at="2026-11-05 00:00:00.000000")
    verdict = run.judge(run.gold())
    assert refused(verdict, "this-run") and "earlier run" in verdict["message"]


def test_a_run_booked_on_another_day_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    edit(run.workspace / "runs" / run.run_id / "trip.json", booking_date="2026-11-04")
    assert refused(run.judge(run.gold()), "this-run")


def test_a_run_of_another_request_is_refused(tmp_path: Path) -> None:
    other = Run(request(wants_business=True), tmp_path / "other")
    run = Run(request(), tmp_path)
    edit(other.workspace / "runs" / other.run_id / "trip.json")
    verdict = judge(run.request, run.gold() | {"run_id": other.run_id}, run.key, other.workspace)
    assert refused(verdict, "this-run")


def test_a_tampered_answer_key_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.correct_offer_ids = [o.offer_id for o in run.key.offers]
    assert refused(run.judge(run.gold()), "answer-key")


def test_an_answer_key_with_edited_offers_is_refused(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    run.key.offers[0].fare_cents += 1
    assert refused(run.judge(run.gold()), "answer-key")


# Determinism and the tools' own checks -----------------------------------------------------------------


def test_the_verdict_is_the_same_twice(tmp_path: Path) -> None:
    run = Run(request(wants_checked_bag=True), tmp_path)
    for output in (run.gold(), booking(run.run_id, run.offers[0].offer_id, oop=12)):
        assert json.dumps(run.judge(output), sort_keys=True) == json.dumps(run.judge(output), sort_keys=True)


def test_tool_inputs_are_checked() -> None:
    good = plain_output(request())
    assert tool_input("get_trip", good)["valid"] is True
    assert tool_input("solve_booking", good | {"date_to": "2026-12-17"})["valid"] is True
    for bad in ({"destination": "BOS"}, {"date_to": "2026-12-02"}, {"date_to": "2026-12-18"},
                {"date_from": "2026-02-30"}, {"traveller_name": " "}):
        assert tool_input("get_trip", good | bad)["valid"] is False, bad
        assert tool_input("solve_booking", good | bad)["valid"] is False, bad
    query = {"run_id": "", "origin": "JFK", "destination": "LAX", "date_from": "2027-03-01", "date_to": "2027-03-15"}
    assert tool_input("search_flights", query)["valid"] is True
    assert tool_input("search_flights", query | {"run_id": "0123456789ab"})["valid"] is True
    for bad in ({"date_to": "2027-03-16"}, {"date_to": "2027-02-28"}, {"date_from": "2027-02-30"},
                {"run_id": "nope"}, {"destination": "JFK"}):
        assert tool_input("search_flights", query | bad)["valid"] is False, bad
    for topic in Topic:
        assert tool_input("booking_requirements", {"topic": topic.value})["valid"] is True


def test_tool_outputs_are_checked(tmp_path: Path) -> None:
    run = Run(request(), tmp_path)
    trip_out = build_output(plain_output(TripOutput(run.run_id, run.trip)), TripOutput)
    assert verifier.verify_output("get_trip", run.request, trip_out, str(run.workspace))["valid"] is True
    assert verifier.verify_output("get_trip", request(wants_business=True), trip_out,
                                  str(run.workspace))["valid"] is False
    moved = build_output(plain_output(trip_out) | {"trip": plain_output(run.trip) | {"booking_date": "2026-12-04"}},
                         TripOutput)
    assert verifier.verify_output("get_trip", run.request, moved, str(run.workspace))["valid"] is False
    query = SearchInput(run.run_id, AirportCode.BOS, AirportCode.LHR, run.trip.date_from, run.trip.date_to)
    found = build_output(plain_output(SearchOutput(run.run_id, "Simulated fares and schedules; airline names are "
                                                   "used for realism only.", run.offers)), SearchOutput)
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is True
    shifted = SearchInput(**(plain_output(query) | {"date_to": "2026-12-04", "origin": AirportCode.BOS,
                                                    "destination": AirportCode.LHR}))
    assert verifier.verify_output("search_flights", shifted, found, str(run.workspace))["valid"] is False
    found.offers[0].fare_cents -= 100
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    found.offers[0].fare_cents += 100
    found.note = "Real fares."
    assert verifier.verify_output("search_flights", query, found, str(run.workspace))["valid"] is False
    key = build_output(plain_output(run.key), SolveOutput)
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is True
    key.out_of_pocket_cents += 1
    assert verifier.verify_output("solve_booking", run.request, key, str(tmp_path))["valid"] is False


@pytest.mark.parametrize("topic", list(Topic))
def test_the_requirements_are_checked(tmp_path: Path, topic: Topic) -> None:
    given = RequirementsInput(topic)
    made = build_output(plain_output(booking_requirements(given, tmp_path)), RequirementsOutput)
    assert verifier.verify_output("booking_requirements", given, made, str(tmp_path))["valid"] is True
    assert verifier.verify_task("booking-requirements", given, made, None, str(tmp_path))["valid"] is True
    for change in ({"today": "2026-13-01"}, {"example_request": "Book anything."},
                   {"airports": [] if topic is not Topic.FIELDS else [{"code": "BOS", "name": "x", "city": "y",
                                                                         "country": "US"}]}):
        altered = build_output(plain_output(made) | change, RequirementsOutput)
        assert verifier.verify_output("booking_requirements", given, altered, str(tmp_path))["valid"] is False, change


def test_tool_tasks_are_judged_as_their_tools(tmp_path: Path) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-01", "2026-12-02")
    from plugin import search_flights

    found = build_output(plain_output(search_flights(query, tmp_path)), SearchOutput)
    assert verifier.verify_task("search-flights", query, found, None, str(tmp_path))["valid"] is True
    other = SearchInput("", AirportCode.JFK, AirportCode.SFO, "2026-12-01", "2026-12-02")
    assert verifier.verify_task("search-flights", other, found, None, str(tmp_path))["valid"] is False


def test_tools_refuse_past_and_far_dates(tmp_path: Path) -> None:
    from plugin import get_trip, search_flights

    with pytest.raises(ValueError, match="before today"):
        get_trip(request(date_from="2026-11-04", date_to="2026-11-04"), tmp_path)
    with pytest.raises(ValueError, match="330 days"):
        get_trip(request(date_from="2027-10-02", date_to="2027-10-02"), tmp_path)
    with pytest.raises(ValueError, match="before today"):
        search_flights(SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-11-01", "2026-11-02"), tmp_path)
    with pytest.raises(ValueError, match="get_trip first"):
        search_flights(SearchInput("0123456789ab", AirportCode.JFK, AirportCode.LAX, "2026-12-01", "2026-12-02"),
                       tmp_path)
