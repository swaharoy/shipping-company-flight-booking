"""The shipping-company-flight-booking verdict: named checks, in order, on the answer key, the run the
submission names, its search receipts, and the booking against rules R1-R8.

Every search receipt is checked against the simulated world rebuilt here (verifier/world.py, the tools' own
file), so any offer the agent saw, on any day it searched, is known exactly.

The first five checks are integrity gates; the rest are the policy. The verdict is valid, scoring 1, only
when every check holds; any failure, gate or policy, scores 0: a booking follows the policy or it does not. A check
that depends on a failed one is "not checked". Expected values come from the verifier's own copy of the
rules applied to the pinned trip and offers; the answer key's own booking is checked to agree with them.
"""

from contract import Cabin, DateMode, Operator, Refusal

from .checks import check, result, run_files
from .rules import (
    BAG_CAP_CENTS,
    BUSINESS_AIR_MINUTES,
    FARE_MARGIN_CENTS,
    advance_ok,
    business_allowed,
    cabin_allowed,
    departure_date,
    in_window,
    is_international,
    is_transatlantic,
    offers_digest,
    out_of_pocket,
    request_plain,
    solve,
)
from .solve import answer_key_problem
from .world import offers_between

TEXT = {
    "answer-key": "The answer key pinned this request's trip, booked today, its offers, and a booking that follows the rules",
    "this-run": "The submission names a run get_trip began for this request on the same booking date, after the answer key",
    "searched": "The agent searched for flights in this run",
    "receipts-match": "Every search in this run returned exactly the route's offers for its query",
    "offer-seen": "The booked offer was among this run's search results, on the trip's route",
    "refusal": "R1/R8: book unless the traveller is a consultant or no offer is allowed, with the right reason",
    "commercial": "R3: a commercial airline, never a charter",
    "dates": "R4: departs in the trip's window, at least 7 days ahead when a flexible window allows it",
    "cabin": "R5: never first; business only when wanted and eligible, and then whenever offered",
    "fare": "R6: the fare is at most $100 above the lowest allowed fare in the booked cabin",
    "bag": "R7: with a checked bag wanted, the lowest traveller out-of-pocket among fares within $100",
    "out-of-pocket": "R7: traveller_out_of_pocket_cents is exact",
}
GATES = ("answer-key", "this-run", "searched", "receipts-match", "offer-seen")
POLICY = ("refusal", "commercial", "dates", "cabin", "fare", "bag", "out-of-pocket")


def money(cents):
    return f"${cents // 100}.{cents % 100:02d}"


class Verdict:
    def __init__(self):
        self.entries = {}
        self.blocked_by = None

    def add(self, check_id, ok, expected="", actual="", message=""):
        if self.blocked_by is not None:
            self.entries[check_id] = check(
                check_id, TEXT[check_id], None, message=f"not checked: {self.blocked_by} failed"
            )
            return
        self.entries[check_id] = check(check_id, TEXT[check_id], ok, expected, actual, message)
        if not ok:
            self.blocked_by = check_id

    def finish(self):
        entries = [self.entries[check_id] for check_id in GATES + POLICY]
        failed = [entry for entry in entries if entry["ok"] is False]
        if not failed:
            return result(True, "valid: the booking follows every rule", score=1.0, checks=entries)
        first = failed[0]
        return result(False, f"{first['id']}: {first['message']}", score=0.0, checks=entries)


def verify_task(arguments, output, reference, workspace):
    verdict = Verdict()
    # Gate 1: the answer key.
    problem = "no answer key was pinned" if reference is None else answer_key_problem(arguments, reference)
    route = f"{arguments.origin.value}-{arguments.destination.value} {arguments.date_from} to {arguments.date_to}"
    verdict.add("answer-key", problem is None, f"the key of {route}", "none" if reference is None else
                f"booked {reference.trip.booking_date}", problem or "the answer key is this request's and follows the rules")
    if problem is not None:
        for check_id in GATES[1:] + POLICY:
            verdict.add(check_id, None)
        return verdict.finish()
    trip, offers = reference.trip, reference.offers
    answer = solve(trip, offers)

    # Gate 2: this run.
    started, searches = run_files(workspace, output.run_id)
    if not isinstance(started, dict) or started.get("request") != request_plain(arguments):
        verdict.add("this-run", False, "a run of this request", output.run_id,
                    f"the workspace holds no run {output.run_id!r} begun by get_trip for this request")
    elif started.get("booking_date") != trip.booking_date:
        verdict.add("this-run", False, f"booked {trip.booking_date}", str(started.get("booking_date")),
                    f"run {output.run_id} was booked on another day than the answer key")
    elif not isinstance(started.get("started_at"), str) or started["started_at"] < reference.pinned_at:
        verdict.add("this-run", False, f"begun after {reference.pinned_at}", str(started.get("started_at")),
                    f"run {output.run_id} began before this task's answer key: it is an earlier run")
    else:
        verdict.add("this-run", True, actual=output.run_id, message=f"run {output.run_id} began at {started['started_at']}")

    # Gate 3: searched (a consultant may be refused without searching).
    needs_search = not (output.booked is False and output.refusal is Refusal.CONSULTANT)
    if needs_search and not searches:
        verdict.add("searched", False, "at least one search_flights call", "none",
                    "the agent booked or refused without calling search_flights in this run")
    else:
        verdict.add("searched", True, actual=f"{len(searches)} searches", message="searched" if searches else
                    "a consultant refusal needs no search")

    # Gate 4: every search receipt matches the simulated world's offers for its query.
    seen = {}
    mismatch = None
    for number, receipt in enumerate(searches, start=1):
        if not isinstance(receipt, dict):
            mismatch = f"search {number}'s receipt is unreadable"
            break
        try:
            expected = offers_between(receipt["origin"], receipt["destination"], receipt["date_from"],
                                      receipt["date_to"])
        except (KeyError, TypeError, ValueError):
            mismatch = f"search {number}'s receipt is malformed"
            break
        if receipt.get("offer_ids") != [o.offer_id for o in expected] or receipt.get("digest") != offers_digest(expected):
            mismatch = f"search {number} returned offers other than the route's offers for its query"
            break
        seen.update({o.offer_id: o for o in expected})
    verdict.add("receipts-match", mismatch is None, "receipts equal to the route's offers", mismatch or "equal",
                mismatch or f"{len(searches)} search receipts match the simulated offers")

    # Gate 5: the booked offer was seen, on the trip's route.
    route = f"{trip.origin.code}-{trip.destination.code}"
    if output.booked and output.offer_id not in seen:
        verdict.add("offer-seen", False, "an offer id from this run's search results", output.offer_id,
                    f"offer {output.offer_id!r} was not among this run's search results")
    elif output.booked:
        flown = seen[output.offer_id]
        flies = f"{flown.segments[0].origin}-{flown.segments[-1].destination}"
        verdict.add("offer-seen", flies == route, f"an offer on {route}", f"{output.offer_id} on {flies}",
                    f"offer {output.offer_id} was in the search results" if flies == route else
                    f"offer {output.offer_id} flies {flies}, not the trip's route {route}")
    else:
        verdict.add("offer-seen", True, message="nothing booked")

    # Policy: booking or refusal.
    want = answer.refusal
    shape_problem = None
    if output.booked and output.refusal is not Refusal.NONE:
        shape_problem = f"booked is true but refusal is {output.refusal.value}: a booking has refusal NONE"
    elif not output.booked and output.refusal is Refusal.NONE:
        shape_problem = "nothing is booked but refusal is NONE: give the reason"
    elif not output.booked and (output.offer_id or output.traveller_out_of_pocket_cents):
        shape_problem = "nothing is booked: offer_id must be empty and traveller_out_of_pocket_cents 0"
    got = "booked" if output.booked else f"not booked ({output.refusal.value})"
    expected = "booked" if want is Refusal.NONE else f"not booked ({want.value})"
    if shape_problem:
        verdict.add("refusal", False, expected, got, shape_problem)
    elif got != expected:
        verdict.add("refusal", False, expected, got, refusal_reason(trip, want))
    else:
        verdict.add("refusal", True, expected, got, refusal_reason(trip, want))
    if not output.booked or verdict.blocked_by is not None:
        message = "nothing is booked" if verdict.blocked_by is None else None
        for check_id in POLICY[1:]:
            if message:
                verdict.add(check_id, True, message=f"not applicable: {message}")
            else:
                verdict.add(check_id, None)
        return verdict.finish()

    offer = seen[output.offer_id]
    oid = offer.offer_id
    # R3
    verdict.add("commercial", offer.operator is Operator.COMMERCIAL, "COMMERCIAL", offer.operator.value,
                f"offer {oid} is flown by {offer.carrier}, a {offer.operator.value.lower()} operator")
    # R4
    day = departure_date(offer)
    pool = [o for o in offers if o.operator is Operator.COMMERCIAL and cabin_allowed(trip, o) and in_window(trip, o)]
    later_possible = trip.date_mode is DateMode.FLEXIBLE and any(advance_ok(trip, o) for o in pool)
    window = trip.date_from if trip.date_mode is DateMode.FIXED else f"{trip.date_from} to {trip.date_to}"
    if not in_window(trip, offer):
        verdict.add("dates", False, window, day, f"offer {oid} departs {day}, outside the trip's dates {window}")
    elif later_possible and not advance_ok(trip, offer):
        verdict.add("dates", False, f"on or after booking {trip.booking_date} + 7 days", day,
                    f"offer {oid} departs {day}, under 7 days after booking on {trip.booking_date}, though "
                    "an allowed flight in the window departs 7 or more days ahead")
    else:
        verdict.add("dates", True, window, day, f"offer {oid} departs {day}")
    # R5
    if offer.cabin is Cabin.FIRST:
        verdict.add("cabin", False, answer.cabin.value, "FIRST", f"offer {oid} is first class, which is never booked")
    elif not cabin_allowed(trip, offer):
        verdict.add("cabin", False, answer.cabin.value, offer.cabin.value, business_reason(trip, offer))
    elif offer.cabin is not answer.cabin:
        verdict.add("cabin", False, answer.cabin.value, offer.cabin.value,
                    "business is wanted and allowed and an allowed business offer exists, so book business")
    else:
        verdict.add("cabin", True, answer.cabin.value, offer.cabin.value, f"{offer.cabin.value} is the cabin to book")
    # R6
    limit = answer.lowest_fare_cents + FARE_MARGIN_CENTS
    verdict.add("fare", offer.fare_cents <= limit, f"at most {money(limit)}", money(offer.fare_cents),
                f"offer {oid} costs {money(offer.fare_cents)}; the lowest allowed {answer.cabin.value} fare is "
                f"{money(answer.lowest_fare_cents)}, so the limit is {money(limit)}")
    # R7 choice
    paid = out_of_pocket(trip, offer)
    if trip.wants_checked_bag:
        verdict.add("bag", paid == answer.out_of_pocket_cents, money(answer.out_of_pocket_cents), money(paid),
                    f"offer {oid} leaves the traveller {money(paid)} for the bag (fees above {money(BAG_CAP_CENTS)} "
                    f"a segment); the least among fares within $100 is {money(answer.out_of_pocket_cents)}")
    else:
        verdict.add("bag", True, message="not applicable: no checked bag is wanted")
    # R7 amount
    stated = output.traveller_out_of_pocket_cents
    verdict.add("out-of-pocket", stated == paid, paid, stated,
                f"offer {oid}'s out-of-pocket is {money(paid)}; the submission says {money(stated) if stated >= 0 else stated}")
    return verdict.finish()


def refusal_reason(trip, want):
    if want is Refusal.CONSULTANT:
        return "the traveller is a consultant: their travel is not billed to the company, so never book it"
    if want is Refusal.NO_COMPLIANT_FLIGHT:
        return "no commercial flight in the trip's dates has an allowed cabin"
    return f"the traveller ({trip.traveller_type.value}) has at least one allowed flight: book it"


def business_reason(trip, offer):
    if not trip.wants_business:
        return f"offer {offer.offer_id} is business but the traveller did not ask for business"
    if not is_international(trip):
        return f"offer {offer.offer_id} is business on a domestic trip: domestic is always coach"
    if not is_transatlantic(trip):
        return (f"offer {offer.offer_id} is business on an international trip with {offer.total_air_minutes} min "
                f"in the air: business needs more than {BUSINESS_AIR_MINUTES} min, or a transatlantic trip")
    return f"offer {offer.offer_id} is business but not allowed" if not business_allowed(trip, offer) else ""
