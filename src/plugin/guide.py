"""What a booking request must give, shared byte for byte by the booking_requirements tool
(src/plugin/guide.py) and the verifier (verifier/guide.py): every field of the booking task's input, read
from the contract, with an example; the date rules; and the airports. No policy: applying the policy is
the agent's job, not the traveller's. It imports only modules a verifier may use, contract, and its
package's shared modules.
"""

import dataclasses
import enum
import typing

from contract import AirportCode, AirportHelp, FieldHelp, RequirementsOutput, Topic, TripInput

from .rules import BOOKING_HORIZON_DAYS, SEARCH_MAX_DAYS, date_of, day_number
from .world import AIRPORTS

EXAMPLE_DEPARTURE_DAYS = 30  # the example request leaves this many days after today
EXAMPLE_SPAN_DAYS = 2


def example_dates(today):
    first = day_number(today) + EXAMPLE_DEPARTURE_DAYS
    return date_of(first), date_of(first + EXAMPLE_SPAN_DAYS)


def examples(today):
    date_from, date_to = example_dates(today)
    return {
        "traveller_name": "Maya Chen",
        "traveller_type": "EMPLOYEE",
        "origin": "BOS",
        "destination": "LHR",
        "date_from": date_from,
        "date_to": date_to,
        "wants_business": "true",
        "wants_checked_bag": "true",
    }


def kind_of(name, kind):
    """What kind of value a field takes, in words."""
    if kind is bool:
        return "yes or no (true or false)"
    if isinstance(kind, type) and issubclass(kind, AirportCode):
        return f"an airport code from the airport list ({len(AIRPORTS)} airports)"
    if isinstance(kind, type) and issubclass(kind, enum.Enum):
        return "one of " + ", ".join(member.value for member in kind)
    if name.startswith("date_"):
        return "a date, YYYY-MM-DD"
    return "text"


def fields(today):
    """Every field of the booking task's input, in the contract's order."""
    hints = typing.get_type_hints(TripInput, include_extras=True)
    example = examples(today)
    found = []
    for field in dataclasses.fields(TripInput):
        kind, description = typing.get_args(hints[field.name])
        found.append(FieldHelp(name=field.name, kind=kind_of(field.name, kind), required=True,
                               example=example[field.name], description=description))
    return found


def date_rules(today):
    last = date_of(day_number(today) + BOOKING_HORIZON_DAYS)
    return [
        f"Today is {today} (UTC): a request made today is booked as of today.",
        "Dates are YYYY-MM-DD.",
        (
            "For a fixed date, give the same day as date_from and date_to; for flexible dates, give a range: the "
            "flight may leave on any day in it."
        ),
        f"date_to is at most {SEARCH_MAX_DAYS} days after date_from.",
        (
            f"Flights are sold from today up to {BOOKING_HORIZON_DAYS} days ahead: date_from is {today} or later, "
            f"and date_to is {last} or earlier."
        ),
    ]


def airports():
    return [AirportHelp(code=row[0], name=row[1], city=row[2], country=row[3]) for row in AIRPORTS]


def example_request(today):
    date_from, date_to = example_dates(today)
    return (
        f"Book a flight for Maya Chen, an employee, from Boston (BOS) to London Heathrow (LHR), leaving any "
        f"day from {date_from} to {date_to}, with business class requested and one checked bag."
    )


def build(topic, today):
    """The requirements for ``topic`` as of ``today``."""
    wants_fields = topic in (Topic.ALL, Topic.FIELDS)
    wants_airports = topic in (Topic.ALL, Topic.AIRPORTS)
    return RequirementsOutput(
        today=today,
        fields=fields(today) if wants_fields else [],
        date_rules=date_rules(today) if wants_fields else [],
        airports=airports() if wants_airports else [],
        example_request=example_request(today),
    )
