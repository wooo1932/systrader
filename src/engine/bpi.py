from __future__ import annotations
from collections import deque


class BpiCalculator:
    def __init__(self, short_window: int = 10, long_window: int = 30):
        self._short_window = short_window
        self._long_window = long_window
        self._short: deque[bool] = deque(maxlen=short_window)
        self._long: deque[bool] = deque(maxlen=long_window)

    def add(self, is_buy: bool) -> None:
        self._short.append(is_buy)
        self._long.append(is_buy)

    @property
    def short(self) -> float:
        if not self._short:
            return 0.5
        return sum(self._short) / len(self._short)

    @property
    def long(self) -> float:
        if not self._long:
            return 0.5
        return sum(self._long) / len(self._long)

    def is_sell_signal(self, threshold: float) -> bool:
        return self.short <= self.long and self.short < threshold

    def reset(self) -> None:
        self._short.clear()
        self._long.clear()
