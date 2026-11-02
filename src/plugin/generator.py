"""Seed -> one trip and its flight offers. The seed's last digit picks the scenario, so every rule and
boundary is exercised by a known kind of seed; the rest of the seed varies the route, dates and fares.

Every scenario is checked against the rules after it is built: a seed that does not make its scenario
raises, it never returns some other case.
"""

from dataclasses import dataclass

from contract import Cabin, DateMode, Offer, Operator, Refusal, Segment, TravellerType, Trip
from plugin import airports
from plugin.prng import Rng
from plugin.rules import (
    BAG_CAP_CENTS,
    BUSINESS_AIR_MINUTES,
    FARE_MARGIN_CENTS,
    date_of,
    day_number,
    departure_date,
    is_international,
    is_transatlantic,
    solve,
)

SCENARIOS = (
    "domestic-economy",  # 0: coach within the U.S., traps: first class, a cheaper charter, fares at +$100.00/+$100.01
    "long-haul-business",  # 1: international, over 6 h in the air, business wanted: book business
    "short-transatlantic",  # 2: transatlantic under 6 h, business wanted: business allowed anyway
    "exactly-360-minutes",  # 3: an international business fare flying exactly 360 min (not allowed)
    "consultant",  # 4: a consultant: never book
    "flexible-later-possible",  # 5: a flexible window that reaches 7 days ahead: cheaper earlier flights are out
    "flexible-all-soon",  # 6: a flexible window entirely under 7 days ahead: any day in it
    "checked-bag-trade-off",  # 7: a bag wanted: a pricier fare including the bag beats the cheapest
    "charter-only",  # 8: only charter and first-class flights in the window: no compliant flight
    "business-cheaper",  # 9: a business fare below economy that is still not allowed
)
FIRST_BOOKING_DAY = day_number("2027-01-04")
NAMES = (
    "Avery Chen", "Jordan Patel", "Riley Okafor", "Morgan Silva", "Casey Novak", "Taylor Haddad",
    "Quinn Larsen", "Jamie Moreau", "Rowan Ito", "Skyler Mensah", "Drew Kowalski", "Emerson Reyes",
)
AIRLINES = ("Northwind Air", "Bluecrest Airways", "Meridian Airlines", "Polar Jet", "Coastline Air", "Atlas Wings")
CHARTERS = ("SkyCharter Group", "Elite Private Jets")
BAG_FEES = (0, 2500, 3000, 3500, 4000, 4500)
ROUTES: dict[str, list[tuple[str, str]]] = {}  # each route kind's airport pairs, computed once


@dataclass
class World:
    seed: int
    scenario: str
    trip: Trip
    offers: list[Offer]


def make(seed: int) -> World:
    if not 0 <= seed <= 9999:
        raise ValueError(f"seed {seed} is not between 0 and 9999")
    rng = Rng(seed)
    scenario = SCENARIOS[seed % 10]
    builder = Builder(rng, scenario)
    trip, offers = builder.build(seed)
    check_scenario(scenario, trip, offers)
    return World(seed, scenario, trip, offers)


def time_text(minute: int) -> str:
    return f"{date_of(minute // 1440)} {minute % 1440 // 60:02d}:{minute % 60:02d}"


class Builder:
    def __init__(self, rng: Rng, scenario: str) -> None:
        self.rng = rng
        self.scenario = scenario
        self.drafts: list[dict] = []

    # Routes -----------------------------------------------------------------------------------------

    def pairs(self, keep) -> list[tuple[str, str]]:
        codes = airports.codes()
        return [(a, b) for a in codes for b in codes if a != b and keep(a, b)]

    def route(self) -> tuple[str, str]:
        snap = airports.snapshot()

        def country(code):
            return snap[code]["country"]

        def continent(code):
            return snap[code]["continent"]

        def domestic(a, b):
            return country(a) == "US" and country(b) == "US"

        def transatlantic(a, b):
            return {continent(a), continent(b)} == {"NA", "EU"}

        def international(a, b):
            return not domestic(a, b)

        minutes = airports.air_minutes
        kinds = {
            "domestic": lambda a, b: domestic(a, b),
            "long-haul": lambda a, b: international(a, b) and not transatlantic(a, b) and minutes(a, b) >= 450,
            "short-transatlantic": lambda a, b: transatlantic(a, b) and minutes(a, b) <= 350,
            "near-360": lambda a, b: international(a, b) and not transatlantic(a, b) and 300 <= minutes(a, b) <= 420,
            "short-international": lambda a, b: (
                international(a, b) and not transatlantic(a, b) and minutes(a, b) <= 330
            ),
        }
        kind = {
            "domestic-economy": "domestic",
            "long-haul-business": "long-haul",
            "short-transatlantic": "short-transatlantic",
            "exactly-360-minutes": "near-360",
        }.get(self.scenario)
        if kind is None:
            kind = self.rng.choice(("domestic", "domestic", "long-haul", "short-international"))
        if kind not in ROUTES:
            ROUTES[kind] = self.pairs(kinds[kind])
        return self.rng.choice(ROUTES[kind])

    # Offers -----------------------------------------------------------------------------------------

    def hub(self, origin: str, destination: str) -> str | None:
        direct = airports.distance_km(origin, destination)
        hubs = [
            code
            for code in airports.codes()
            if code not in (origin, destination)
            and airports.distance_km(origin, code) >= 300
            and airports.distance_km(code, destination) >= 300
            and airports.distance_km(origin, code) + airports.distance_km(code, destination) <= 1.3 * direct
        ]
        return self.rng.choice(hubs) if hubs else None

    def economy_fare(self, origin: str, destination: str) -> int:
        base = 4_000 + round(airports.distance_km(origin, destination) * 9)
        return base * self.rng.randint(80, 125) // 100

    def draft(self, day: int, origin: str, destination: str, *, cabin: Cabin, operator: Operator, fare: int,
              stops: int = 0, bag_fees: tuple | None = None, minutes: tuple | None = None) -> dict:
        """One offer departing on ``day``: nonstop, or through a hub when stops is 1 and a hub exists."""
        hub = self.hub(origin, destination) if stops else None
        legs = [(origin, hub), (hub, destination)] if hub else [(origin, destination)]
        legs_minutes = minutes or tuple(airports.air_minutes(a, b) for a, b in legs)
        if len(legs_minutes) != len(legs):
            raise ValueError("minutes must give one value per segment")
        if bag_fees is None:
            fee = 0 if cabin is not Cabin.ECONOMY else self.rng.choice(BAG_FEES)
            bag_fees = tuple(fee for _ in legs)
        start = day * 1440 + self.rng.randint(6 * 4, 21 * 4) * 15
        segments = []
        for (a, b), air, fee in zip(legs, legs_minutes, bag_fees, strict=True):
            segments.append(Segment(a, b, time_text(start), time_text(start + air), air, fee))
            start += air + self.rng.randint(4, 10) * 15
        carrier = self.rng.choice(CHARTERS if operator is Operator.CHARTER else AIRLINES)
        draft = {"carrier": carrier, "operator": operator, "cabin": cabin, "fare": fare, "segments": segments}
        self.drafts.append(draft)
        return draft

    def regular_day(self, day: int, origin: str, destination: str, *, business: bool, extras: bool) -> None:
        """A day's usual offers: economy nonstop and one-stop, business if asked, first class or a charter."""
        fare = self.economy_fare(origin, destination)
        self.draft(day, origin, destination, cabin=Cabin.ECONOMY, operator=Operator.COMMERCIAL, fare=fare)
        self.draft(day, origin, destination, cabin=Cabin.ECONOMY, operator=Operator.COMMERCIAL,
                   fare=fare * self.rng.randint(75, 95) // 100, stops=1)
        if business:
            self.draft(day, origin, destination, cabin=Cabin.BUSINESS, operator=Operator.COMMERCIAL,
                       fare=fare * self.rng.randint(300, 450) // 100)
        if extras and self.rng.chance(50):
            self.draft(day, origin, destination, cabin=Cabin.FIRST, operator=Operator.COMMERCIAL,
                       fare=fare * self.rng.randint(550, 700) // 100)
        if extras and self.rng.chance(40):
            self.draft(day, origin, destination, cabin=Cabin.ECONOMY, operator=Operator.CHARTER,
                       fare=fare * self.rng.randint(60, 90) // 100)

    def offers(self) -> list[Offer]:
        """The drafts as offers, ordered by departure, numbered F01, F02, ..."""
        ordered = sorted(self.drafts, key=lambda d: (d["segments"][0].depart, d["fare"], d["cabin"].value))
        return [
            Offer(
                offer_id=f"F{index:02d}",
                carrier=d["carrier"],
                operator=d["operator"],
                cabin=d["cabin"],
                fare_cents=d["fare"],
                total_air_minutes=sum(segment.air_minutes for segment in d["segments"]),
                segments=d["segments"],
            )
            for index, d in enumerate(ordered, start=1)
        ]

    # The trip ---------------------------------------------------------------------------------------

    def build(self, seed: int) -> tuple[Trip, list[Offer]]:
        rng, scenario = self.rng, self.scenario
        origin, destination = self.route()
        booking = FIRST_BOOKING_DAY + rng.randint(0, 330)
        flexible = scenario in ("flexible-later-possible", "flexible-all-soon") or (
            scenario in ("domestic-economy", "long-haul-business", "checked-bag-trade-off") and rng.chance(30)
        )
        if scenario == "flexible-later-possible":
            start = booking + rng.randint(4, 6)
            end = booking + rng.randint(7, 9)
        elif scenario == "flexible-all-soon":
            start = booking + rng.randint(1, 3)
            end = booking + rng.randint(max(4, start - booking), 6)
        elif flexible:
            start = booking + rng.randint(8, 30)
            end = start + rng.randint(1, 3)
        else:
            start = end = booking + rng.randint(1, 45)
        traveller = TravellerType.CONSULTANT if scenario == "consultant" else rng.choice(
            (TravellerType.EMPLOYEE, TravellerType.EMPLOYEE, TravellerType.NON_EMPLOYEE)
        )
        wants_business = {
            "long-haul-business": True,
            "short-transatlantic": True,
            "exactly-360-minutes": True,
            "checked-bag-trade-off": False,
        }.get(scenario, rng.chance(50))
        wants_bag = True if scenario == "checked-bag-trade-off" else rng.chance(50)
        if scenario == "business-cheaper" and is_long_eligible(origin, destination):
            wants_business = False
        trip = Trip(
            seed=seed,
            traveller_name=rng.choice(NAMES),
            traveller_type=traveller,
            origin=airports.airport(origin),
            destination=airports.airport(destination),
            booking_date=date_of(booking),
            date_mode=DateMode.FLEXIBLE if flexible else DateMode.FIXED,
            date_from=date_of(start),
            date_to=date_of(end),
            wants_business=wants_business,
            wants_checked_bag=wants_bag,
        )
        self.populate(trip, origin, destination, booking, start, end)
        return trip, self.offers()

    def populate(self, trip: Trip, origin: str, destination: str, booking: int, start: int, end: int) -> None:
        rng, scenario = self.rng, self.scenario
        business = trip.wants_business or rng.chance(50)
        # Distractors on the days around the window: only a search wider than the trip's dates sees them.
        for day in (start - 1, end + 1):
            self.regular_day(day, origin, destination, business=business, extras=False)
        if scenario == "charter-only":
            for day in range(start, end + 1):
                fare = self.economy_fare(origin, destination)
                self.draft(day, origin, destination, cabin=Cabin.ECONOMY, operator=Operator.CHARTER, fare=fare)
                if rng.chance(60):
                    self.draft(day, origin, destination, cabin=Cabin.FIRST, operator=Operator.COMMERCIAL,
                               fare=fare * rng.randint(550, 700) // 100)
            return
        for day in range(start, end + 1):
            self.regular_day(day, origin, destination, business=business, extras=True)
        if scenario == "flexible-later-possible":
            # The cheapest flights of the window leave under 7 days ahead; one later flight leaves exactly 7.
            cheapest = min(d["fare"] for d in self.drafts if d["cabin"] is Cabin.ECONOMY)
            for day in range(start, booking + 7):
                self.draft(day, origin, destination, cabin=Cabin.ECONOMY, operator=Operator.COMMERCIAL,
                           fare=cheapest * rng.randint(55, 70) // 100)
            self.draft(booking + 7, origin, destination, cabin=Cabin.ECONOMY, operator=Operator.COMMERCIAL,
                       fare=self.economy_fare(origin, destination))
        if scenario == "exactly-360-minutes":
            self.plant_360(trip, origin, destination, start)
        if scenario == "business-cheaper":
            lowest = min(d["fare"] for d in self.drafts if d["cabin"] is Cabin.ECONOMY)
            self.draft(rng.randint(start, end), origin, destination, cabin=Cabin.BUSINESS,
                       operator=Operator.COMMERCIAL, fare=lowest * rng.randint(70, 95) // 100)
        if scenario in ("domestic-economy", "checked-bag-trade-off", "long-haul-business"):
            self.plant_margin(trip, origin, destination, start, end)

    def plant_360(self, trip: Trip, origin: str, destination: str, day: int) -> None:
        """Business flying exactly 360 min is not allowed; with a 361-minute connection, that one is."""
        rng = self.rng
        self.drafts = [d for d in self.drafts if d["cabin"] is not Cabin.BUSINESS]
        fare = self.economy_fare(origin, destination)
        self.draft(day, origin, destination, cabin=Cabin.BUSINESS, operator=Operator.COMMERCIAL,
                   fare=fare * rng.randint(300, 400) // 100, minutes=(BUSINESS_AIR_MINUTES,))
        if rng.chance(50):
            hub = self.hub(origin, destination)
            if hub is not None:
                first = rng.randint(120, 240)
                self.draft(day, origin, destination, cabin=Cabin.BUSINESS, operator=Operator.COMMERCIAL,
                           fare=fare * rng.randint(300, 400) // 100, stops=1,
                           minutes=(first, BUSINESS_AIR_MINUTES + 1 - first))

    def plant_margin(self, trip: Trip, origin: str, destination: str, start: int, end: int) -> None:
        """Fares at exactly the lowest + $100 and + $100.01 in the booked cabin, and for a checked bag, a
        cheapest fare with a dear bag against pricier fares that include it."""
        rng = self.rng
        world_offers = self.offers()
        answer = solve(trip, world_offers)
        if answer.refusal is not Refusal.NONE:
            return
        lowest = answer.lowest_fare_cents
        cheapest = next(o for o in world_offers if o.offer_id in answer.allowed and o.fare_cents == lowest)
        day = day_number(departure_date(cheapest))
        cabin = answer.cabin
        if trip.wants_checked_bag:
            # The cheapest allowed flight charges $45 a bag on every segment.
            for draft in self.drafts:
                if draft["segments"] == cheapest.segments and draft["fare"] == lowest:
                    draft["segments"] = [
                        Segment(s.origin, s.destination, s.depart, s.arrive, s.air_minutes, 4500)
                        for s in draft["segments"]
                    ]
            # Raise every other allowed fare's bag fee too, so only the planted offers can win.
            for draft in self.drafts:
                if draft["cabin"] is cabin and draft["fare"] != lowest:
                    draft["segments"] = [
                        Segment(s.origin, s.destination, s.depart, s.arrive, s.air_minutes,
                                max(s.bag_fee_cents, BAG_CAP_CENTS + 500))
                        for s in draft["segments"]
                    ]
            included = rng.choice((0, BAG_CAP_CENTS, BAG_CAP_CENTS + 1))
            self.draft(day, origin, destination, cabin=cabin, operator=Operator.COMMERCIAL,
                       fare=lowest + FARE_MARGIN_CENTS, bag_fees=(included,))
            self.draft(day, origin, destination, cabin=cabin, operator=Operator.COMMERCIAL,
                       fare=lowest + FARE_MARGIN_CENTS + 1, bag_fees=(0,))
        else:
            self.draft(day, origin, destination, cabin=cabin, operator=Operator.COMMERCIAL,
                       fare=lowest + FARE_MARGIN_CENTS)
            self.draft(day, origin, destination, cabin=cabin, operator=Operator.COMMERCIAL,
                       fare=lowest + FARE_MARGIN_CENTS + 1)


def is_long_eligible(origin: str, destination: str) -> bool:
    snap = airports.snapshot()
    international = snap[origin]["country"] != "US" or snap[destination]["country"] != "US"
    transatlantic = {snap[origin]["continent"], snap[destination]["continent"]} == {"NA", "EU"}
    return transatlantic or (international and airports.air_minutes(origin, destination) > BUSINESS_AIR_MINUTES)


def check_scenario(scenario: str, trip: Trip, offers: list[Offer]) -> None:
    """Raise unless the trip and offers make the scenario they were built for."""
    answer = solve(trip, offers)
    by_id = {offer.offer_id: offer for offer in offers}
    correct = [by_id[offer_id] for offer_id in answer.correct]
    in_window = [
        o for o in offers if day_number(trip.date_from) <= day_number(departure_date(o)) <= day_number(trip.date_to)
    ]
    checks = {
        "domestic-economy": lambda: not is_international(trip) and answer.cabin is Cabin.ECONOMY and bool(correct),
        "long-haul-business": lambda: answer.cabin is Cabin.BUSINESS and not is_transatlantic(trip),
        "short-transatlantic": lambda: answer.cabin is Cabin.BUSINESS and is_transatlantic(trip)
        and all(o.total_air_minutes <= BUSINESS_AIR_MINUTES for o in correct),
        "exactly-360-minutes": lambda: any(
            o.cabin is Cabin.BUSINESS and o.total_air_minutes == BUSINESS_AIR_MINUTES for o in in_window
        ) and bool(correct),
        "consultant": lambda: answer.refusal is Refusal.CONSULTANT,
        "flexible-later-possible": lambda: bool(correct)
        and all(day_number(departure_date(o)) - day_number(trip.booking_date) >= 7 for o in correct)
        and any(
            o.operator is Operator.COMMERCIAL and o.cabin is not Cabin.FIRST
            and day_number(departure_date(o)) - day_number(trip.booking_date) < 7
            and o.fare_cents < answer.lowest_fare_cents
            for o in in_window
        ),
        "flexible-all-soon": lambda: bool(correct)
        and day_number(trip.date_to) - day_number(trip.booking_date) < 7,
        "checked-bag-trade-off": lambda: bool(correct)
        and all(o.fare_cents > answer.lowest_fare_cents for o in correct),
        "charter-only": lambda: answer.refusal is Refusal.NO_COMPLIANT_FLIGHT,
        "business-cheaper": lambda: answer.cabin is Cabin.ECONOMY and any(
            o.cabin is Cabin.BUSINESS and o.fare_cents < answer.lowest_fare_cents for o in in_window
        ),
    }
    if not checks[scenario]():
        raise RuntimeError(f"seed {trip.seed} did not make its scenario {scenario}")
