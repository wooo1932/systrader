from __future__ import annotations
from dataclasses import dataclass


@dataclass
class ScreenResult:
    passed: bool
    reason: str = ""


class Screener:
    def __init__(self, max_holdings: int, min_market_cap: int, max_market_cap: int,
                 min_change_pct: float, max_change_pct: float):
        self.max_holdings = max_holdings
        self.min_market_cap = min_market_cap
        self.max_market_cap = max_market_cap
        self.min_change_pct = min_change_pct
        self.max_change_pct = max_change_pct

    def check(self, market_cap: int, change_pct: float, current_price: float,
              upper_limit_price: float, current_holdings: int) -> ScreenResult:
        if current_holdings >= self.max_holdings:
            return ScreenResult(False, "max_holdings")
        if market_cap < self.min_market_cap:
            return ScreenResult(False, "min_market_cap")
        if market_cap > self.max_market_cap:
            return ScreenResult(False, "max_market_cap")
        if change_pct < self.min_change_pct:
            return ScreenResult(False, "min_change_pct")
        if change_pct > self.max_change_pct:
            return ScreenResult(False, "max_change_pct")
        if current_price >= upper_limit_price * 0.98:
            return ScreenResult(False, "near_upper_limit")
        return ScreenResult(True)
