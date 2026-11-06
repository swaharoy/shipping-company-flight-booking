"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    BOOKING_REQUIREMENTS = "booking_requirements"
    GET_TRIP = "get_trip"
    SEARCH_FLIGHTS = "search_flights"
    SOLVE_BOOKING = "solve_booking"


class Task(Enum):
    BOOKING_REQUIREMENTS = "booking-requirements"
    SEARCH_FLIGHTS = "search-flights"
    BOOK_FLIGHT = "shipping-company-flight-booking"


class TravellerType(Enum):
    EMPLOYEE = "EMPLOYEE"
    NON_EMPLOYEE = "NON_EMPLOYEE"
    CONSULTANT = "CONSULTANT"


class AirportCode(Enum):
    """The airports this plugin knows, by IATA code (booking_requirements lists their names and cities)."""

    ATL = "ATL"
    LAX = "LAX"
    ORD = "ORD"
    DFW = "DFW"
    DEN = "DEN"
    JFK = "JFK"
    SFO = "SFO"
    SEA = "SEA"
    LAS = "LAS"
    MCO = "MCO"
    EWR = "EWR"
    MIA = "MIA"
    CLT = "CLT"
    PHX = "PHX"
    IAH = "IAH"
    BOS = "BOS"
    MSP = "MSP"
    DTW = "DTW"
    PHL = "PHL"
    LGA = "LGA"
    BWI = "BWI"
    SLC = "SLC"
    SAN = "SAN"
    IAD = "IAD"
    DCA = "DCA"
    TPA = "TPA"
    AUS = "AUS"
    BNA = "BNA"
    HNL = "HNL"
    ANC = "ANC"
    STL = "STL"
    YYZ = "YYZ"
    YVR = "YVR"
    YUL = "YUL"
    YHZ = "YHZ"
    MEX = "MEX"
    CUN = "CUN"
    LHR = "LHR"
    CDG = "CDG"
    FRA = "FRA"
    AMS = "AMS"
    MAD = "MAD"
    FCO = "FCO"
    MUC = "MUC"
    ZRH = "ZRH"
    DUB = "DUB"
    LIS = "LIS"
    CPH = "CPH"
    BCN = "BCN"
    VIE = "VIE"
    BRU = "BRU"
    OSL = "OSL"
    ARN = "ARN"
    KEF = "KEF"
    MAN = "MAN"
    EDI = "EDI"
    SNN = "SNN"
    NRT = "NRT"
    ICN = "ICN"
    SIN = "SIN"
    HKG = "HKG"
    DXB = "DXB"
    DEL = "DEL"
    BOM = "BOM"
    SYD = "SYD"
    GRU = "GRU"
    BOG = "BOG"
    JNB = "JNB"


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


class Topic(Enum):
    ALL = "ALL"
    FIELDS = "FIELDS"
    AIRPORTS = "AIRPORTS"


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
    traveller_name: Annotated[str, "The traveller's name"]
    traveller_type: Annotated[TravellerType, "Who travels: an employee, a non-employee or a consultant"]
    origin: Annotated[Airport, "The airport the trip leaves from"]
    destination: Annotated[Airport, "The airport the trip goes to"]
    booking_date: Annotated[str, "Today, the day the flight is booked, YYYY-MM-DD (UTC)"]
    date_mode: Annotated[DateMode, "FIXED: depart on date_from; FLEXIBLE: depart any day from date_from to date_to"]
    date_from: Annotated[str, "The first allowed departure day, YYYY-MM-DD"]
    date_to: Annotated[str, "The last allowed departure day, YYYY-MM-DD (date_from when FIXED)"]
    wants_business: Annotated[bool, "Whether the traveller asks for business class"]
    wants_checked_bag: Annotated[bool, "Whether the traveller checks one bag"]


@dataclass
class Segment(Output):
    origin: Annotated[str, CODE]
    destination: Annotated[str, CODE]
    flight_number: Annotated[str, "The airline's flight number, e.g. DL 1482; CHARTER for a private jet"]
    depart: Annotated[str, TIME]
    arrive: Annotated[str, TIME]
    air_minutes: Annotated[int, "Minutes in the air"]
    bag_fee_cents: Annotated[int, "The fee for one checked bag charged on this flight, in cents; 0 when included"]


@dataclass
class Offer(Output):
    offer_id: Annotated[str, "The offer's id: its departure date and number, e.g. 20261203-04"]
    carrier: Annotated[str, "The airline or charter operator"]
    operator: Annotated[Operator, "COMMERCIAL airline or CHARTER service"]
    cabin: Annotated[Cabin, "The cabin class"]
    fare_cents: Annotated[int, "The fare, in cents"]
    total_air_minutes: Annotated[int, "Minutes in the air over all segments"]
    segments: Annotated[list[Segment], "The flights, in order"]


@dataclass
class TripInput(Output):
    traveller_name: Annotated[str, "The traveller's full name, as on the ticket"]
    traveller_type: Annotated[
        TravellerType, "EMPLOYEE, NON_EMPLOYEE (a guest the company pays for) or CONSULTANT (never booked by us)"
    ]
    origin: Annotated[AirportCode, "The airport to leave from, by IATA code (e.g. BOS for Boston)"]
    destination: Annotated[AirportCode, "The airport to fly to, by IATA code (e.g. LHR for London Heathrow)"]
    date_from: Annotated[str, "The first day the traveller can leave, YYYY-MM-DD, today or later"]
    date_to: Annotated[
        str, "The last day the traveller can leave, YYYY-MM-DD: date_from for a fixed date, up to 14 days later"
    ]
    wants_business: Annotated[bool, "Whether the traveller asks for business class (the policy decides if it is allowed)"]
    wants_checked_bag: Annotated[bool, "Whether the traveller checks one bag"]


@dataclass
class TripOutput(Output):
    run_id: Annotated[str, "This booking run's id: pass it to search_flights and submit it"]
    trip: Annotated[Trip, "The trip to book"]


@dataclass
class SearchInput(Output):
    run_id: Annotated[str, "This booking run's id, as get_trip returned it; empty to only look, outside a booking"]
    origin: Annotated[AirportCode, "The airport to leave from"]
    destination: Annotated[AirportCode, "The airport to fly to"]
    date_from: Annotated[str, "The first departure day to search, YYYY-MM-DD, today or later"]
    date_to: Annotated[str, "The last departure day to search, YYYY-MM-DD, at most 14 days after date_from"]


@dataclass
class SearchOutput(Output):
    run_id: Annotated[str, RUN_ID]
    note: Annotated[str, "Where the offers come from: simulated fares and schedules"]
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
    pinned_at: Annotated[str, "When the answer key was pinned, UTC YYYY-MM-DD HH:MM:SS.ffffff"]
    trip: Annotated[Trip, "The trip, with today as its booking date"]
    offers: Annotated[list[Offer], "Every offer on the route departing in the trip's dates"]
    refusal: Annotated[Refusal, "The correct refusal, NONE when a flight must be booked"]
    cabin: Annotated[Cabin, "The cabin to book; ECONOMY when nothing is booked"]
    allowed_offer_ids: Annotated[list[str], "The offers the commercial, date and cabin rules allow"]
    lowest_fare_cents: Annotated[int, "The lowest allowed fare; 0 when nothing is allowed"]
    correct_offer_ids: Annotated[list[str], "Every offer that is a correct booking"]
    out_of_pocket_cents: Annotated[int, "The traveller's out-of-pocket for a correct booking"]


@dataclass
class RequirementsInput(Output):
    topic: Annotated[Topic, "ALL for everything, FIELDS for what to tell us, AIRPORTS for the airport list"]


@dataclass
class FieldHelp(Output):
    name: Annotated[str, "The field's name"]
    kind: Annotated[str, "What kind of value it takes"]
    required: Annotated[bool, "Whether every booking request must give it"]
    example: Annotated[str, "An example value"]
    description: Annotated[str, "What it means"]


@dataclass
class AirportHelp(Output):
    code: Annotated[str, CODE]
    name: Annotated[str, "The airport's name"]
    city: Annotated[str, "The city it serves"]
    country: Annotated[str, "Its ISO 3166 country code"]


@dataclass
class RequirementsOutput(Output):
    today: Annotated[str, "Today, the booking date, YYYY-MM-DD (UTC)"]
    fields: Annotated[list[FieldHelp], "What a booking request gives, field by field; empty for AIRPORTS"]
    date_rules: Annotated[list[str], "How the travel dates work; empty for AIRPORTS"]
    airports: Annotated[list[AirportHelp], "The airports a trip may use; empty for FIELDS"]
    example_request: Annotated[str, "A complete booking request in plain words"]


TOOLS = {
    Tool.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Tool.GET_TRIP: (TripInput, TripOutput),
    Tool.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Tool.SOLVE_BOOKING: (TripInput, SolveOutput),
}
TASKS = {
    Task.BOOKING_REQUIREMENTS: (RequirementsInput, RequirementsOutput),
    Task.SEARCH_FLIGHTS: (SearchInput, SearchOutput),
    Task.BOOK_FLIGHT: (TripInput, BookingOutput),
}
