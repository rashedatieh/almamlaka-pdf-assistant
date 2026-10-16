"""In-app spend guards (PROJECT_PLAN §3.4; ACCEPTANCE Q-01, Q-02).

DAILY_BUDGET_USD caps Claude spend per UTC day, computed from each response's `usage` and app/prices.py.
The check runs before any model call, so an exhausted budget makes no Anthropic call. Cloud Run runs at
most one instance, so an in-memory counter is exact; it resets on redeploy, which the cap tolerates
because the Anthropic workspace spend limit remains the hard stop.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, date, datetime


class BudgetExhausted(Exception):
    """Today's in-app Claude budget is used up (HTTP 429 budget_exhausted)."""


class TurnCapReached(Exception):
    """This conversation reached MAX_TURNS_PER_SESSION."""


class DailyBudget:
    def __init__(self, limit_usd: float, today: Callable[[], date] | None = None) -> None:
        self.limit_usd = limit_usd
        self._today = today or (lambda: datetime.now(UTC).date())
        self._day = self._today()
        self._spent = 0.0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        if self._today() != self._day:
            self._day, self._spent = self._today(), 0.0

    @property
    def spent_today(self) -> float:
        with self._lock:
            self._roll()
            return self._spent

    def check(self) -> None:
        if self.spent_today >= self.limit_usd:
            raise BudgetExhausted(f"daily budget ${self.limit_usd:.2f} reached")

    def record(self, cost_usd: float) -> None:
        with self._lock:
            self._roll()
            self._spent += max(cost_usd, 0.0)
