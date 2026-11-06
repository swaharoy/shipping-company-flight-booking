"""The simulated world: real airports and airlines on plausible routes, synthetic but realistic fares,
schedules and bag fees, the same on every machine, and an answer key that agrees with an independent reading
of the rules."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from helpers import CODES, requests
from oracle import booking_answer
from slimconfig import plain_output

from contract import AirportCode, SearchInput
from plugin import receipts, search_flights, solve_booking, world
from plugin.rules import date_of, day_number, minute_number

DAY = day_number("2026-12-03")
GOLDEN = {
    ("BOS", "LHR"): "ed6ae84fdc300e66",
    ("JFK", "LAX"): "e2eeec56ef8a830a",
    ("ATL", "ORD"): "901e22a87e6e2b14",
    ("SFO", "NRT"): "8378ff3a1418b2b1",
    ("LHR", "CDG"): "e7d85a490aa502be",
    ("SYD", "JNB"): "efbfae8e9b394acf",
}
US_AIRLINES = {row[1] for row in world.AIRLINES if row[2] == "US"}
CHARTERS = {row[0] for row in world.CHARTERS}
FLIGHT_NUMBER = re.compile(r"^[A-Z0-9]{2} [1-9]\d{0,3}$")
LARGEST_SEARCH_CHARS = 60_000  # a 15-day search must stay well inside the hosted model's 65,536-token budget
LARGEST_DAY_CHARS = 6_000


def routes(step: int = 5):
    """Every ``step``-th route of all 68 x 67."""
    pairs = [(a, b) for a in CODES for b in CODES if a != b]
    return pairs[::step]


def digest(offers) -> str:
    text = json.dumps([plain_output(offer) for offer in offers], sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@pytest.mark.parametrize("route", sorted(GOLDEN))
def test_a_route_and_day_make_the_same_offers_everywhere(route) -> None:
    assert digest(world.day_offers(*route, DAY)) == GOLDEN[route]


def test_the_airports_are_the_contract_codes() -> None:
    assert [row[0] for row in world.AIRPORTS] == [member.value for member in AirportCode]
    assert len(world.AIRPORTS) == 68
    assert all(-720 <= row[7] <= 720 and row[7] % 30 == 0 for row in world.AIRPORTS)


def test_the_airlines_are_real_names_with_hubs_among_the_airports() -> None:
    assert "Delta Air Lines" in US_AIRLINES and "British Airways" in {row[1] for row in world.AIRLINES}
    for code, _name, _country, kind, reach, hubs, cabins in world.AIRLINES:
        assert re.fullmatch(r"[A-Z0-9]{2}", code) and kind in ("us", "low", "intl") and reach > 0
        assert hubs and all(world.is_airport(hub) for hub in hubs), code
        assert cabins in ("Y", "YJ", "YJF")
    assert CHARTERS == {"NetJets", "Wheels Up", "VistaJet"}


def local_minute(time: str, code: str) -> int:
    return (minute_number(time) + world.airport_table()[code][7]) % 1440


def test_offers_are_well_formed_and_plausible() -> None:
    airline_of = {row[1]: row for row in world.AIRLINES}
    for origin, destination in routes():
        domestic = world.country(origin) == world.country(destination) == "US"
        for day in (DAY, DAY + 40):
            offers = world.day_offers(origin, destination, day)
            ids = [offer.offer_id for offer in offers]
            assert ids == [f"{date_of(day).replace('-', '')}-{n:02d}" for n in range(1, len(ids) + 1)]
            assert [o.segments[0].depart for o in offers] == sorted(o.segments[0].depart for o in offers)
            for offer in offers:
                first, last = offer.segments[0], offer.segments[-1]
                assert first.origin == origin and last.destination == destination
                assert offer.depart_date == date_of(day), "departs on its local day at the origin"
                assert offer.depart_local == world.time_text(minute_number(first.depart) + world.utc_offset(origin))
                assert offer.depart_local[:10] == offer.depart_date
                assert offer.total_air_minutes == sum(s.air_minutes for s in offer.segments)
                assert offer.fare_cents > 0
                assert 6 * 60 <= local_minute(first.depart, origin) < 22 * 60, "leaves in local daytime"
                for one, two in zip(offer.segments, offer.segments[1:]):
                    assert one.destination == two.origin
                    wait = minute_number(two.depart) - minute_number(one.arrive)
                    assert 45 <= wait <= 240
                if offer.operator.value == "CHARTER":
                    assert offer.carrier in CHARTERS and offer.cabin.value == "ECONOMY"
                    assert [s.flight_number for s in offer.segments] == ["CHARTER"]
                    continue
                airline = airline_of[offer.carrier]
                if domestic:
                    assert offer.carrier in US_AIRLINES, (origin, destination, offer.carrier)
                for segment in offer.segments:
                    assert FLIGHT_NUMBER.fullmatch(segment.flight_number)
                    assert segment.flight_number.startswith(airline[0] + " ")
                    inside = world.country(segment.origin) == world.country(segment.destination)
                    assert not inside or world.country(segment.origin) == airline[2], "no cabotage"
                if len(offer.segments) == 2:
                    assert offer.segments[0].destination in airline[5], "connects at the airline's hub"
                else:
                    assert origin in airline[5] or destination in airline[5]
                assert all(s.bag_fee_cents == 0 for s in offer.segments[1:]), "one bag fee per ticket"
                if offer.cabin.value != "ECONOMY":
                    assert first.bag_fee_cents == 0
                if offer.cabin.value == "FIRST":
                    assert "F" in airline[6]


def local_departures(origins, days=range(DAY, DAY + 7)) -> dict[str, list[int]]:
    """{origin: every first departure's local minute of the day} from each origin to every other airport."""
    found = {}
    for origin in origins:
        found[origin] = [
            local_minute(offer.segments[0].depart, origin)
            for destination in CODES if destination != origin
            for day in days
            for offer in world.day_offers(origin, destination, day)
        ]
    return found


def test_west_coast_flights_leave_in_the_evening_too() -> None:
    """UTC-8: a departure after 16:00 local is on the next UTC date, which 0.2.0 never generated."""
    for origin, minutes in local_departures(("SFO", "LAX", "SEA")).items():
        assert sum(minute >= 16 * 60 for minute in minutes) >= 50, origin
        assert max(minutes) >= 21 * 60, origin


def test_asian_flights_leave_in_the_early_morning_too() -> None:
    """UTC+8/+9: a departure before 09:00 local is on the previous UTC date, which 0.2.0 never generated."""
    for origin, minutes in local_departures(("NRT", "ICN", "HKG", "SIN")).items():
        assert sum(minute < 9 * 60 for minute in minutes) >= 20, origin
        assert min(minutes) < 7 * 60, origin


def test_every_departure_leaves_from_06_00_to_21_55_local() -> None:
    minutes = [minute for found in local_departures(CODES, (DAY, DAY + 1)).values() for minute in found]
    assert len(minutes) > 10_000
    assert min(minutes) == 6 * 60 and max(minutes) == 21 * 60 + 55
    assert all(minute % 5 == 0 for minute in minutes)


def test_a_late_departure_west_of_utc_is_numbered_by_its_local_date() -> None:
    offers = [o for d in CODES if d != "SFO" for o in world.day_offers("SFO", d, DAY)]
    late = next(o for o in offers if o.depart_local[11:] >= "16:00")
    assert late.depart_date == "2026-12-03" and late.offer_id.startswith("20261203-")
    assert late.segments[0].depart[:10] == "2026-12-04", "the UTC date is the next day"


def test_live_searches_hold_the_realistic_traps() -> None:
    """Across routes, the traps the policy is about turn up without being planted."""
    seen = set()
    for origin, destination in routes(7):
        offers = world.day_offers(origin, destination, DAY)
        economy = sorted(o.fare_cents for o in offers if o.cabin.value == "ECONOMY" and o.operator.value == "COMMERCIAL")
        if any(o.operator.value == "CHARTER" for o in offers):
            seen.add("a charter")
        if any(o.operator.value == "CHARTER" and economy and o.fare_cents < economy[0] for o in offers):
            seen.add("a charter cheaper than every airline")
        if any(o.cabin.value == "BUSINESS" and economy and o.fare_cents < 2 * economy[0] for o in offers):
            seen.add("business under twice economy")
        if any(o.cabin.value == "FIRST" for o in offers):
            seen.add("first class")
        if len(economy) >= 2 and economy[1] - economy[0] <= 10_000:
            seen.add("two economy fares within $100")
        fees = {o.segments[0].bag_fee_cents for o in offers}
        seen.update({"a bag fee over $30" for fee in fees if fee > 3_000})
        seen.update({"a bag fee of exactly $30" for fee in fees if fee == 3_000})
        if any(o.total_air_minutes > 360 for o in offers) and any(o.total_air_minutes <= 360 for o in offers):
            seen.add("both sides of 6 hours")
    assert seen == {"a charter", "a charter cheaper than every airline", "business under twice economy",
                    "first class", "two economy fares within $100", "a bag fee over $30",
                    "a bag fee of exactly $30", "both sides of 6 hours"}


def test_searches_fit_the_hosted_context() -> None:
    largest_day = largest = 0
    for origin, destination in routes(11):
        offers = world.offers_between(origin, destination, date_of(DAY), date_of(DAY + 14))
        largest = max(largest, len(json.dumps([plain_output(offer) for offer in offers])))
        day = world.day_offers(origin, destination, DAY)
        largest_day = max(largest_day, len(json.dumps([plain_output(offer) for offer in day])))
    print(f"largest 15-day search: {largest} characters; largest day: {largest_day}")
    assert largest <= LARGEST_SEARCH_CHARS, largest
    assert largest_day <= LARGEST_DAY_CHARS, largest_day


def test_offers_do_not_depend_on_the_booking_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    query = SearchInput("", AirportCode.JFK, AirportCode.LAX, "2026-12-20", "2026-12-22")
    early = search_flights(query, tmp_path)
    monkeypatch.setattr(receipts, "CLOCK", lambda: "2026-12-19 08:00:00.000000")
    assert plain_output(search_flights(query, tmp_path)) == plain_output(early)


def test_unknown_or_equal_airports_are_refused() -> None:
    with pytest.raises(ValueError):
        world.day_offers("XXX", "LHR", DAY)
    with pytest.raises(ValueError):
        world.day_offers("BOS", "BOS", DAY)
    with pytest.raises(ValueError):
        world.offers_between("BOS", "LHR", "2026-12-03", "2026-12-18")


def test_the_answer_key_agrees_with_an_independent_reading_for_400_requests(tmp_path: Path) -> None:
    outcomes = set()
    for value in requests(400, "oracle"):
        key = solve_booking(value, tmp_path)
        refusal, correct, paid = booking_answer(key.trip, key.offers)
        assert key.refusal.value == refusal, plain_output(value)
        assert set(key.correct_offer_ids) == correct, plain_output(value)
        assert key.out_of_pocket_cents == paid, plain_output(value)
        outcomes.add((key.refusal.value, key.cabin.value, key.out_of_pocket_cents > 0))
    assert {("NONE", "ECONOMY", False), ("NONE", "BUSINESS", False), ("NONE", "ECONOMY", True),
            ("CONSULTANT", "ECONOMY", False)} <= outcomes
