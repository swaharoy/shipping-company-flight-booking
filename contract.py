"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    GET_TRIP = "get_trip"
    SEARCH_FLIGHTS = "search_flights"
    SOLVE_BOOKING = "solve_booking"


class Task(Enum):
    SHOW_TRIP = "show-trip"
    SEARCH_FLIGHTS = "search-flights"
    BOOK_FLIGHT = "shipping-company-flight-booking"


class TravellerType(Enum):
    EMPLOYEE = "EMPLOYEE"
    NON_EMPLOYEE = "NON_EMPLOYEE"
    CONSULTANT = "CONSULTANT"


class DateMode(Enum):
    FIXED = "FIXED"
    FLEXIBLE = "FLEXIBLE"


class Cabin(Enum):
    ECONOMY = "ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"


class Operator(Enum):
    COMMERCIAL = "COMMERCIAL"
    CHARTER = "CHARTER"


class Refusal(Enum):
    NONE = "NONE"
    CONSULTANT = "CONSULTANT"
    NO_COMPLIANT_FLIGHT = "NO_COMPLIANT_FLIGHT"


SEED = "The trip's seed, 0 to 9999: the same seed always gives the same trip and flight offers"
RUN_ID = "This booking run's id, as get_trip returned it"
DATE = "A UTC calendar date, YYYY-MM-DD"
TIME = "A UTC time, YYYY-MM-DD HH:MM"
CODE = "An IATA airport code, e.g. JFK"
CENTS = "An amount in US cents"


@dataclass
class Airport(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code, e.g. US"]
    continent: Annotated[str, "Its continent code: NA, SA, EU, AF, AS or OC"]


@dataclass
class Trip(Output):
    seed: Annotated[int, SEED]
    traveller_name: Annotated[str, "The traveller's name"]
    traveller_type: Annotated[TravellerType, "Who travels: an employee, a non-employee or a consultant"]
    origin: Annotated[Airport, "The airport the trip leaves from"]
    destination: Annotated[Airport, "The airport the trip goes to"]
    booking_date: Annotated[str, "Today, the day the flight is booked, YYYY-MM-DD"]
    date_mode: Annotated[DateMode, "FIXED: depart on date_from; FLEXIBLE: depart any day from date_from to date_to"]
    date_from: Annotated[str, "The first allowed departure day, YYYY-MM-DD"]
    date_to: Annotated[str, "The last allowed departure day, YYYY-MM-DD (date_from when FIXED)"]
    wants_business: Annotated[bool, "Whether the traveller asks for business class"]
    wants_checked_bag: Annotated[bool, "Whether the traveller checks one bag"]


@dataclass
class Segment(Output):
    origin: Annotated[str, CODE]
    destination: Annotated[str, CODE]
    depart: Annotated[str, TIME]
    arrive: Annotated[str, TIME]
    air_minutes: Annotated[int, "Minutes in the air"]
    bag_fee_cents: Annotated[int, "The fee for one checked bag on this segment, in cents; 0 when it is included"]


@dataclass
class Offer(Output):
    offer_id: Annotated[str, "The offer's id"]
    carrier: Annotated[str, "The airline or charter operator"]
    operator: Annotated[Operator, "COMMERCIAL airline or CHARTER service"]
    cabin: Annotated[Cabin, "The cabin class"]
    fare_cents: Annotated[int, "The fare, in cents"]
    total_air_minutes: Annotated[int, "Minutes in the air over all segments"]
    segments: Annotated[list[Segment], "The flights, in order"]


@dataclass
class TripInput(Output):
    seed: Annotated[int, SEED]


@dataclass
class TripOutput(Output):
    run_id: Annotated[str, "This booking run's id: pass it to search_flights and submit it"]
    trip: Annotated[Trip, "The trip to book"]


@dataclass
class SearchInput(Output):
    seed: Annotated[int, SEED]
    run_id: Annotated[str, "This booking run's id, as get_trip returned it; empty to only look, outside a booking"]
    origin: Annotated[str, "The trip's origin airport code"]
    destination: Annotated[str, "The trip's destination airport code"]
    date_from: Annotated[str, "The first departure day to search, YYYY-MM-DD"]
    date_to: Annotated[str, "The last departure day to search, YYYY-MM-DD, at most 14 days after date_from"]


@dataclass
class SearchOutput(Output):
    run_id: Annotated[str, RUN_ID]
    offers: Annotated[list[Offer], "Every one-way offer on the route departing on the searched days, by departure"]


@dataclass
class BookingOutput(Output):
    run_id: Annotated[str, RUN_ID]
    booked: Annotated[bool, "Whether a flight is booked"]
    refusal: Annotated[Refusal, "Why nothing is booked; NONE when a flight is booked"]
    offer_id: Annotated[str, "The booked offer's id; empty when nothing is booked"]
    traveller_out_of_pocket_cents: Annotated[
        int, "What the traveller pays for the checked bag beyond the reimbursed $30 per segment; 0 when not booked"
    ]


@dataclass
class SolveOutput(Output):
    scenario: Annotated[str, "Which kind of case the seed makes"]
    pinned_at: Annotated[str, "When the answer key was pinned, UTC YYYY-MM-DD HH:MM:SS.ffffff"]
    trip: Annotated[Trip, "The trip"]
    offers: Annotated[list[Offer], "Every offer the seed makes, on any day"]
    refusal: Annotated[Refusal, "The correct refusal, NONE when a flight must be booked"]
    cabin: Annotated[Cabin, "The cabin to book; ECONOMY when nothing is booked"]
    allowed_offer_ids: Annotated[list[str], "The offers the commercial, date and cabin rules allow"]
    lowest_fare_cents: Annotated[int, "The lowest allowed fare; 0 when nothing is allowed"]
    correct_offer_ids: Annotated[list[str], "Every offer that is a correct booking"]
    out_of_pocket_cents: Annotated[int, "The traveller's out-of-pocket for a correct booking"]


TOOLS = {
    Tool.GET_TRIP: (TripInput, TripOutput),
    Tool.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Tool.SOLVE_BOOKING: (TripInput, SolveOutput),
}
TASKS = {
    Task.SHOW_TRIP: (TripInput, TripOutput),
    Task.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Task.BOOK_FLIGHT: (TripInput, BookingOutput),
}
