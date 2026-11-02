"""Rules R1-R8 on hand-built trips and offers, every boundary included."""

from __future__ import annotations

import pytest

from contract import Airport, Cabin, DateMode, Offer, Operator, Refusal, Segment, TravellerType, Trip
from plugin.rules import date_of, day_number, minute_number, out_of_pocket, solve

AIRPORTS = {
    "JFK": Airport("JFK", "John F Kennedy", "New York", "US", "NA"),
    "LAX": Airport("LAX", "Los Angeles", "Los Angeles", "US", "NA"),
    "DUB": Airport("DUB", "Dublin", "Dublin", "IE", "EU"),
    "BOG": Airport("BOG", "El Dorado", "Bogota", "CO", "SA"),
}


def trip(origin="JFK", destination="LAX", *, kind=TravellerType.EMPLOYEE, mode=DateMode.FIXED, booking="2027-03-01",
         start="2027-03-20", end=None, business=False, bag=False) -> Trip:
    return Trip(1, "Test Traveller", kind, AIRPORTS[origin], AIRPORTS[destination], booking, mode, start,
                end or start, business, bag)


def offer(offer_id, fare, *, cabin=Cabin.ECONOMY, operator=Operator.COMMERCIAL, day="2027-03-20", minutes=(300,),
          fees=None, origin="JFK", destination="LAX") -> Offer:
    fees = fees or tuple(0 for _ in minutes)
    stops = ["HUB"] * (len(minutes) - 1)
    points = [origin, *stops, destination]
    segments = [
        Segment(points[i], points[i + 1], f"{day} 10:00", f"{day} 15:00", air, fee)
        for i, (air, fee) in enumerate(zip(minutes, fees, strict=True))
    ]
    return Offer(offer_id, "Test Air", operator, cabin, fare, sum(minutes), segments)


def test_dates_round_trip_and_reject_impossible_days() -> None:
    for text in ("1970-01-01", "2000-02-29", "2027-12-31", "2028-02-29", "2100-03-01"):
        assert date_of(day_number(text)) == text
    assert day_number("2027-03-01") - day_number("2027-02-28") == 1
    assert day_number("2028-03-01") - day_number("2028-02-28") == 2
    for bad in ("2027-02-29", "2027-13-01", "2027-1-01", "tomorrow", "2100-02-29"):
        with pytest.raises(ValueError):
            day_number(bad)
    assert minute_number("2027-01-01 23:59") - minute_number("2027-01-01 00:00") == 1439
    with pytest.raises(ValueError):
        minute_number("2027-01-01 24:00")


def test_consultant_is_refused_whatever_the_offers() -> None:
    answer = solve(trip(kind=TravellerType.CONSULTANT), [offer("A", 100)])
    assert answer.refusal is Refusal.CONSULTANT and answer.correct == []


def test_non_employee_follows_the_employee_rules() -> None:
    offers = [offer("A", 20_000), offer("B", 30_001)]
    assert solve(trip(kind=TravellerType.NON_EMPLOYEE), offers).correct == solve(trip(), offers).correct == ["A"]


def test_charter_and_first_are_never_allowed() -> None:
    offers = [offer("C", 100, operator=Operator.CHARTER), offer("F", 200, cabin=Cabin.FIRST), offer("E", 50_000)]
    answer = solve(trip(business=True), offers)
    assert answer.correct == ["E"] and answer.allowed == ["E"]


def test_only_charters_and_first_class_means_no_compliant_flight() -> None:
    offers = [offer("C", 100, operator=Operator.CHARTER), offer("F", 200, cabin=Cabin.FIRST)]
    assert solve(trip(), offers).refusal is Refusal.NO_COMPLIANT_FLIGHT


@pytest.mark.parametrize(("minutes", "cabin"), [((360,), Cabin.ECONOMY), ((361,), Cabin.BUSINESS),
                                                 ((200, 161), Cabin.BUSINESS), ((200, 160), Cabin.ECONOMY)])
def test_international_business_needs_more_than_360_minutes(minutes, cabin) -> None:
    t = trip("JFK", "BOG", business=True)
    offers = [offer("E", 40_000, origin="JFK", destination="BOG"),
              offer("B", 150_000, cabin=Cabin.BUSINESS, minutes=minutes, origin="JFK", destination="BOG")]
    assert solve(t, offers).cabin is cabin


def test_transatlantic_business_is_allowed_under_six_hours() -> None:
    t = trip("JFK", "DUB", business=True)
    offers = [offer("E", 40_000, origin="JFK", destination="DUB"),
              offer("B", 150_000, cabin=Cabin.BUSINESS, minutes=(340,), origin="JFK", destination="DUB")]
    answer = solve(t, offers)
    assert answer.cabin is Cabin.BUSINESS and answer.correct == ["B"]


def test_business_needs_to_be_wanted_even_when_cheaper() -> None:
    t = trip("JFK", "DUB", business=False)
    offers = [offer("E", 40_000, origin="JFK", destination="DUB"),
              offer("B", 30_000, cabin=Cabin.BUSINESS, minutes=(400,), origin="JFK", destination="DUB")]
    assert solve(t, offers).correct == ["E"]


def test_domestic_is_always_economy() -> None:
    offers = [offer("E", 40_000), offer("B", 30_000, cabin=Cabin.BUSINESS, minutes=(600,))]
    assert solve(trip(business=True), offers).correct == ["E"]


@pytest.mark.parametrize(("extra", "within"), [(10_000, True), (10_001, False)])
def test_fare_within_100_dollars_of_the_lowest(extra, within) -> None:
    offers = [offer("A", 25_000), offer("B", 25_000 + extra)]
    assert ("B" in solve(trip(), offers).correct) is within


@pytest.mark.parametrize(("fee", "paid"), [(3000, 0), (3001, 1), (0, 0), (4500, 1500)])
def test_bag_out_of_pocket_is_the_fee_above_30_dollars_per_segment(fee, paid) -> None:
    assert out_of_pocket(trip(bag=True), offer("A", 1, fees=(fee,))) == paid
    assert out_of_pocket(trip(bag=False), offer("A", 1, fees=(fee,))) == 0
    assert out_of_pocket(trip(bag=True), offer("A", 1, minutes=(100, 100), fees=(fee, fee))) == 2 * paid


def test_a_wanted_bag_makes_a_pricier_included_fare_the_only_choice() -> None:
    offers = [offer("A", 20_000, fees=(4500,)), offer("B", 30_000, fees=(0,)), offer("C", 30_001, fees=(0,))]
    answer = solve(trip(bag=True), offers)
    assert answer.correct == ["B"] and answer.out_of_pocket_cents == 0
    assert solve(trip(bag=False), offers).correct == ["A", "B"]


def test_a_flexible_window_prefers_7_or_more_days_ahead_exactly_7_included() -> None:
    t = trip(mode=DateMode.FLEXIBLE, booking="2027-03-01", start="2027-03-05", end="2027-03-09")
    offers = [offer("SOON", 10_000, day="2027-03-07"), offer("SEVEN", 30_000, day="2027-03-08")]
    assert solve(t, offers).correct == ["SEVEN"]


def test_a_flexible_window_all_under_7_days_takes_any_day() -> None:
    t = trip(mode=DateMode.FLEXIBLE, booking="2027-03-01", start="2027-03-02", end="2027-03-06")
    offers = [offer("A", 10_000, day="2027-03-02"), offer("B", 15_000, day="2027-03-06"),
              offer("OUT", 1_000, day="2027-03-07")]
    assert solve(t, offers).correct == ["A", "B"]


def test_a_fixed_date_is_kept_even_under_7_days() -> None:
    t = trip(booking="2027-03-01", start="2027-03-03")
    offers = [offer("A", 10_000, day="2027-03-03"), offer("LATER", 1_000, day="2027-03-10")]
    assert solve(t, offers).correct == ["A"]
