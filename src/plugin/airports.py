"""The committed airport snapshot (OurAirports, public domain) and flight times derived from distance."""

import json
import math
from functools import cache
from pathlib import Path

from contract import Airport

DATA = Path(__file__).resolve().parent / "data" / "airports.json"
EARTH_RADIUS_KM = 6371.0
CRUISE_KMH = 870  # average block speed used to turn distance into minutes in the air
TAXI_MINUTES = 20


@cache
def snapshot() -> dict:
    """{code: record} from data/airports.json."""
    document = json.loads(DATA.read_text(encoding="utf-8"))
    return {record["code"]: record for record in document["airports"]}


def codes() -> list[str]:
    return list(snapshot())


def airport(code: str) -> Airport:
    record = snapshot().get(code)
    if record is None:
        raise ValueError(f"unknown airport {code!r}")
    return Airport(
        code=record["code"],
        name=record["name"],
        city=record["city"],
        country=record["country"],
        continent=record["continent"],
    )


@cache
def distance_km(origin: str, destination: str) -> float:
    """Great-circle distance between two airports."""
    a, b = snapshot()[origin], snapshot()[destination]
    lat1, lon1, lat2, lon2 = (math.radians(value) for value in (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


@cache
def air_minutes(origin: str, destination: str) -> int:
    """Minutes in the air for a nonstop flight: distance at cruise speed, plus taxi time."""
    return TAXI_MINUTES + round(distance_km(origin, destination) * 60 / CRUISE_KMH)
