"""search_flights: the seed's one-way offers on a route, departing on the searched days."""

from pathlib import Path

from contract import SearchInput, SearchOutput
from plugin import generator, receipts
from plugin.rules import SEARCH_MAX_DAYS, day_number, matches_search, offers_digest


def search_flights(value: SearchInput, workspace: Path) -> SearchOutput:
    span = day_number(value.date_to) - day_number(value.date_from)
    if not 0 <= span <= SEARCH_MAX_DAYS:
        raise ValueError(f"date_to must be 0 to {SEARCH_MAX_DAYS} days after date_from")
    # A search outside a booking run (run_id empty) is only shown, never recorded.
    folder = receipts.run_folder(workspace, value.run_id, value.seed) if value.run_id else None
    world = generator.make(value.seed)
    offers = [
        offer
        for offer in world.offers
        if matches_search(offer, value.origin, value.destination, value.date_from, value.date_to)
    ]
    if folder is None:
        return SearchOutput(run_id="", offers=offers)
    receipts.add_search(
        folder,
        {
            "seed": value.seed,
            "origin": value.origin,
            "destination": value.destination,
            "date_from": value.date_from,
            "date_to": value.date_to,
            "offer_ids": [offer.offer_id for offer in offers],
            "digest": offers_digest(offers),
        },
    )
    return SearchOutput(run_id=value.run_id, offers=offers)
