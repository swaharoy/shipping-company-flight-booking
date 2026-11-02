"""A seeded pseudo-random stream built on SHA-256, so a seed gives the same numbers on every machine and
Python version (unlike `random`, whose algorithms may change)."""

import hashlib


class Rng:
    def __init__(self, seed: int, label: str = "trip") -> None:
        self.prefix = f"shipping-company-flight-booking:{label}:{seed}:"
        self.count = 0

    def bits(self) -> int:
        """The next 64 random bits."""
        digest = hashlib.sha256(f"{self.prefix}{self.count}".encode()).digest()
        self.count += 1
        return int.from_bytes(digest[:8], "big")

    def randint(self, low: int, high: int) -> int:
        """An integer from low to high, both included."""
        if high < low:
            raise ValueError(f"empty range {low}..{high}")
        return low + self.bits() % (high - low + 1)

    def choice(self, items):
        if not items:
            raise ValueError("choice from an empty sequence")
        return items[self.randint(0, len(items) - 1)]

    def chance(self, percent: int) -> bool:
        """True with the given probability in percent."""
        return self.randint(1, 100) <= percent

    def shuffled(self, items) -> list:
        items = list(items)
        for index in range(len(items) - 1, 0, -1):
            other = self.randint(0, index)
            items[index], items[other] = items[other], items[index]
        return items
