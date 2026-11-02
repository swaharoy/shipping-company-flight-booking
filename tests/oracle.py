"""An independent reading of the task instructions, written without the plugin's rules module (its own
date arithmetic, its own order of tests), to cross-check the answer key offer by offer."""

from __future__ import annotations

from datetime import date


def day(text: str) -> date:
    return date.fromisoformat(text[:10])


def booking_answer(trip, offers) -> tuple[str, set[str], int]:
    """(refusal, the correct offer ids, the traveller's out-of-pocket for them)."""
    if trip.traveller_type.value == "CONSULTANT":
        return "CONSULTANT", set(), 0
    international = trip.origin.country != "US" or trip.destination.country != "US"
    transatlantic = sorted([trip.origin.continent, trip.destination.continent]) == ["EU", "NA"]

    def permitted(offer) -> bool:
        if offer.operator.value == "CHARTER" or offer.cabin.value == "FIRST":
            return False
        if not day(trip.date_from) <= day(offer.segments[0].depart) <= day(trip.date_to):
            return False
        if offer.cabin.value == "BUSINESS":
            return trip.wants_business and (transatlantic or (international and offer.total_air_minutes > 360))
        return True

    candidates = [offer for offer in offers if permitted(offer)]
    if trip.date_mode.value == "FLEXIBLE":
        ahead = [o for o in candidates if (day(o.segments[0].depart) - day(trip.booking_date)).days >= 7]
        candidates = ahead or candidates
    if not candidates:
        return "NO_COMPLIANT_FLIGHT", set(), 0
    cabin = "BUSINESS" if any(o.cabin.value == "BUSINESS" for o in candidates) else "ECONOMY"
    same = [o for o in candidates if o.cabin.value == cabin]
    floor = min(o.fare_cents for o in same)

    def pays(offer) -> int:
        if not trip.wants_checked_bag:
            return 0
        return sum(fee - 3000 for fee in (s.bag_fee_cents for s in offer.segments) if fee > 3000)

    near = [o for o in same if o.fare_cents - floor <= 10000]
    best = min(pays(o) for o in near)
    return "NONE", {o.offer_id for o in near if pays(o) == best}, best
