"""The shipping company's air-travel rules, shared byte for byte by the tools (src/plugin/rules.py) and the
verifier (verifier/rules.py): dates, what a trip request may be, which offers the policy allows, the booking
it requires, and the canonical form of requests and offers both sides compare.

Exact integer arithmetic only, and no datetime (a verifier may not import it): a date is a day number.
It imports only modules a verifier may use, and contract.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from contract import Cabin, DateMode, Operator, Refusal, TravellerType

DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}):(\d{2})$")
ADVANCE_DAYS = 7  # book at least this many days before departure, when possible
BUSINESS_AIR_MINUTES = 360  # business needs strictly more minutes in the air on an international trip
FARE_MARGIN_CENTS = 10_000  # the fare may be at most $100 above the lowest allowed fare
BAG_CAP_CENTS = 3_000  # one checked bag is reimbursed up to $30 per segment
HOME_COUNTRY = "US"
SEARCH_MAX_DAYS = 14  # a trip's dates, and one search, cover at most this many days after date_from
BOOKING_HORIZON_DAYS = 330  # flights are sold up to this many days after today
NAME_MOST_CHARS = 80


def day_number(date):
    """Days since 1970-01-01 of a YYYY-MM-DD date; ValueError when it is not a real date."""
    match = DATE.fullmatch(date)
    if not match:
        raise ValueError(f"{date!r} is not a YYYY-MM-DD date")
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"{date!r} is not a real date")
    year -= month <= 2
    era = year // 400
    year_of_era = year - era * 400
    day_of_year = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146097 + day_of_era - 719468


def date_of(number):
    """The YYYY-MM-DD date of a day number."""
    number += 719468
    era = number // 146097
    day_of_era = number - era * 146097
    year_of_era = (day_of_era - day_of_era // 1460 + day_of_era // 36524 - day_of_era // 146096) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    shifted = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * shifted + 2) // 5 + 1
    month = shifted + (3 if shifted < 10 else -9)
    year = year_of_era + era * 400 + (month <= 2)
    return f"{year:04d}-{month:02d}-{day:02d}"


def days_in_month(year, month):
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def is_date(text):
    try:
        day_number(text)
    except ValueError:
        return False
    return True


def minute_number(time):
    """Minutes since 1970-01-01 00:00 of a YYYY-MM-DD HH:MM time; ValueError when it is not one."""
    match = TIME.fullmatch(time)
    if not match:
        raise ValueError(f"{time!r} is not a YYYY-MM-DD HH:MM time")
    date, hour, minute = match.group(1), int(match.group(2)), int(match.group(3))
    if hour > 23 or minute > 59:
        raise ValueError(f"{time!r} is not a real time")
    return day_number(date) * 1440 + hour * 60 + minute


def request_problem(request):
    """What is wrong with a trip request on its own (no clock needed), or None."""
    if not request.traveller_name.strip():
        return "traveller_name is blank: give the traveller's name"
    if len(request.traveller_name) > NAME_MOST_CHARS:
        return f"traveller_name is longer than {NAME_MOST_CHARS} characters"
    if request.origin is request.destination:
        return f"origin and destination are both {request.origin.value}: give two different airports"
    for name, value in (("date_from", request.date_from), ("date_to", request.date_to)):
        if not is_date(value):
            return f"{name} {value!r} is not a real YYYY-MM-DD date"
    span = day_number(request.date_to) - day_number(request.date_from)
    if span < 0:
        return f"date_to {request.date_to} is before date_from {request.date_from}"
    if span > SEARCH_MAX_DAYS:
        return f"date_to is {span} days after date_from: a flexible range covers at most {SEARCH_MAX_DAYS} days"
    return None


def booking_date_problem(date_from, date_to, booking_date):
    """What is wrong with departure days booked on ``booking_date`` (today), or None."""
    if day_number(date_from) < day_number(booking_date):
        return f"date_from {date_from} is before today, {booking_date}: flights cannot leave in the past"
    if day_number(date_to) > day_number(booking_date) + BOOKING_HORIZON_DAYS:
        return (f"date_to {date_to} is more than {BOOKING_HORIZON_DAYS} days after today, {booking_date}: "
                "flights are not sold that far ahead")
    return None


def date_mode(date_from, date_to):
    """One day is a FIXED date; a range is FLEXIBLE."""
    return DateMode.FIXED if date_from == date_to else DateMode.FLEXIBLE


def request_plain(request):
    """A trip request as plain JSON values, the form receipts record and the verifier compares."""
    return {
        "traveller_name": request.traveller_name,
        "traveller_type": request.traveller_type.value,
        "origin": request.origin.value,
        "destination": request.destination.value,
        "date_from": request.date_from,
        "date_to": request.date_to,
        "wants_business": request.wants_business,
        "wants_checked_bag": request.wants_checked_bag,
    }


def trip_matches_request(trip, request):
    """Whether a trip states exactly what the request asked for."""
    return (
        trip.traveller_name == request.traveller_name
        and trip.traveller_type is request.traveller_type
        and trip.origin.code == request.origin.value
        and trip.destination.code == request.destination.value
        and trip.date_from == request.date_from
        and trip.date_to == request.date_to
        and trip.date_mode is date_mode(request.date_from, request.date_to)
        and trip.wants_business is request.wants_business
        and trip.wants_checked_bag is request.wants_checked_bag
    )


def departure_date(offer):
    """The day an offer departs: the date of its first segment's departure."""
    return offer.segments[0].depart[:10]


def is_international(trip):
    return trip.origin.country != HOME_COUNTRY or trip.destination.country != HOME_COUNTRY


def is_transatlantic(trip):
    return {trip.origin.continent, trip.destination.continent} == {"NA", "EU"}


def business_allowed(trip, offer):
    """R5: a business offer is allowed only when it is wanted and the trip is transatlantic, or
    international with more than 360 minutes in the air."""
    if offer.cabin is not Cabin.BUSINESS or not trip.wants_business:
        return False
    if is_transatlantic(trip):
        return True
    return is_international(trip) and offer.total_air_minutes > BUSINESS_AIR_MINUTES


def cabin_allowed(trip, offer):
    """R5: ECONOMY always; BUSINESS when business_allowed; FIRST never."""
    if offer.cabin is Cabin.ECONOMY:
        return True
    return business_allowed(trip, offer)


def in_window(trip, offer):
    """R4: departs on a day from date_from to date_to (the same day when FIXED)."""
    day = day_number(departure_date(offer))
    return day_number(trip.date_from) <= day <= day_number(trip.date_to)


def advance_ok(trip, offer):
    """R4: departs at least 7 days after the booking date (exactly 7 is fine)."""
    return day_number(departure_date(offer)) - day_number(trip.booking_date) >= ADVANCE_DAYS


def out_of_pocket(trip, offer):
    """R7: what the traveller pays for the checked bag beyond $30 per segment; 0 when no bag is wanted."""
    if not trip.wants_checked_bag:
        return 0
    return sum(max(0, segment.bag_fee_cents - BAG_CAP_CENTS) for segment in offer.segments)


@dataclass
class Answer:
    """The booking the rules require for a trip and its offers."""

    refusal: Refusal
    cabin: Cabin
    allowed: list  # offer ids the commercial, cabin and date rules allow
    lowest_fare_cents: int
    correct: list  # offer ids that are correct bookings
    out_of_pocket_cents: int


def solve(trip, offers):
    """The rules applied in order: R1 consultant, R3 commercial, R5 cabin permission, R4 dates, R5 cabin
    choice, R6 lowest fare within $100, R7 checked bag, R8 nothing allowed."""
    if trip.traveller_type is TravellerType.CONSULTANT:
        return Answer(Refusal.CONSULTANT, Cabin.ECONOMY, [], 0, [], 0)
    pool = [
        offer
        for offer in offers
        if offer.operator is Operator.COMMERCIAL and cabin_allowed(trip, offer) and in_window(trip, offer)
    ]
    later = [offer for offer in pool if advance_ok(trip, offer)]
    if trip.date_mode is DateMode.FLEXIBLE and later:
        pool = later
    if not pool:
        return Answer(Refusal.NO_COMPLIANT_FLIGHT, Cabin.ECONOMY, [], 0, [], 0)
    cabin = Cabin.BUSINESS if any(offer.cabin is Cabin.BUSINESS for offer in pool) else Cabin.ECONOMY
    allowed = [offer for offer in pool if offer.cabin is cabin]
    lowest = min(offer.fare_cents for offer in allowed)
    within = [offer for offer in allowed if offer.fare_cents <= lowest + FARE_MARGIN_CENTS]
    least = min(out_of_pocket(trip, offer) for offer in within)
    correct = [offer for offer in within if out_of_pocket(trip, offer) == least]
    return Answer(
        Refusal.NONE,
        cabin,
        [offer.offer_id for offer in allowed],
        lowest,
        [offer.offer_id for offer in correct],
        least,
    )


def offer_plain(offer):
    """An offer as plain JSON values, the form both sides hash."""
    return {
        "offer_id": offer.offer_id,
        "carrier": offer.carrier,
        "operator": offer.operator.value,
        "cabin": offer.cabin.value,
        "fare_cents": offer.fare_cents,
        "total_air_minutes": offer.total_air_minutes,
        "segments": [
            {
                "origin": segment.origin,
                "destination": segment.destination,
                "flight_number": segment.flight_number,
                "depart": segment.depart,
                "arrive": segment.arrive,
                "air_minutes": segment.air_minutes,
                "bag_fee_cents": segment.bag_fee_cents,
            }
            for segment in offer.segments
        ],
    }


def offers_digest(offers):
    """The SHA-256 of a list of offers in their canonical JSON form."""
    text = json.dumps([offer_plain(offer) for offer in offers], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_offers(left, right):
    """Whether two lists of offers are the same offers, in the same order."""
    return [offer_plain(offer) for offer in left] == [offer_plain(offer) for offer in right]
