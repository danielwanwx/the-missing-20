"""Production and deterministic implementations of the trusted clock port."""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class ManualClock:
    def __init__(self, current: datetime) -> None:
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("manual clock requires a timezone-aware datetime")
        self._current = current

    def now(self) -> datetime:
        return self._current

    def set(self, current: datetime) -> None:
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("manual clock requires a timezone-aware datetime")
        if current < self._current:
            raise ValueError("manual clock cannot move backwards")
        self._current = current
