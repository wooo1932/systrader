_TICK_TABLE = [
    (2_000, 1),
    (5_000, 5),
    (10_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
]
_DEFAULT_TICK = 1_000


def get_tick_unit(price: int | float) -> int:
    for threshold, unit in _TICK_TABLE:
        if price < threshold:
            return unit
    return _DEFAULT_TICK


def round_to_tick(price: int | float, direction: str = "up") -> int:
    unit = get_tick_unit(price)
    if direction == "up":
        return int(((price + unit - 1) // unit) * unit)
    else:
        return int((price // unit) * unit)
