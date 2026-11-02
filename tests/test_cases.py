"""The scripted cases under tests/cases/, replayed offline through the real tools and the real verifier:
each gets the verdict it expects, and each keeps to the hosted budget and the prescribed path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from replay import matches, replay

CASES = sorted((Path(__file__).resolve().parent / "cases").glob("*.json"))
MOST_SEARCH_CHARS = 12_000  # one search result must stay small enough for the hosted model's context


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_are_gold_wrong_missing_tampered_and_boundary_cases() -> None:
    kinds = {load(path)["kind"] for path in CASES}
    assert kinds == {"gold", "wrong", "missing", "malformed", "tampered", "boundary"}
    assert sum(load(path)["kind"] == "gold" for path in CASES) >= 10


@pytest.mark.parametrize("path", CASES, ids=[path.stem for path in CASES])
def test_each_case_gets_its_verdict(path: Path) -> None:
    case = load(path)
    problems = matches(replay(case), case["expect"])
    assert not problems, problems


@pytest.mark.parametrize("path", CASES, ids=[path.stem for path in CASES])
def test_each_case_keeps_to_the_hosted_budget(path: Path) -> None:
    case = load(path)
    tools = [step["tool"] for step in case["steps"] if "tool" in step] + ["submit"]
    assert len(tools) <= 5, "the hosted agent has six steps"
    if case["kind"] == "gold":
        path_taken = ["get_trip", "submit"] if case["expect"].get("consultant") else ["get_trip", "search_flights",
                                                                                       "submit"]
        assert tools == path_taken, "the prescribed path"


def test_gold_searches_fit_the_hosted_context(tmp_path: Path) -> None:
    from contract import SearchInput, TripInput
    from plugin import get_trip, search_flights

    longest = 0
    for seed in range(0, 10_000, 3):
        started = get_trip(TripInput(seed), tmp_path)
        trip = started.trip
        found = search_flights(SearchInput(seed, started.run_id, trip.origin.code, trip.destination.code,
                                           trip.date_from, trip.date_to), tmp_path)
        from slimconfig import plain_output

        longest = max(longest, len(json.dumps(plain_output(found))))
    assert longest <= MOST_SEARCH_CHARS, longest
