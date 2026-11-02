import itertools

import pytest

from plugin import receipts


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch):
    """A clock that ticks one second per reading, so receipts' times are known and increasing."""
    ticks = itertools.count()

    def now() -> str:
        second = next(ticks)
        return f"2026-11-02 00:{second // 60:02d}:{second % 60:02d}.000000"

    monkeypatch.setattr(receipts, "CLOCK", now)
    return now
