from src.engine.bpi import BpiCalculator


def test_empty_bpi():
    bpi = BpiCalculator(short_window=3, long_window=5)
    assert bpi.short == 0.5
    assert bpi.long == 0.5


def test_all_buy_ticks():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    assert bpi.short == 1.0
    assert bpi.long == 1.0


def test_all_sell_ticks():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=False)
    assert bpi.short == 0.0
    assert bpi.long == 0.0


def test_mixed_ticks():
    bpi = BpiCalculator(short_window=4, long_window=4)
    bpi.add(is_buy=True)
    bpi.add(is_buy=False)
    bpi.add(is_buy=True)
    bpi.add(is_buy=False)
    assert bpi.short == 0.5
    assert bpi.long == 0.5


def test_window_sliding():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    bpi.add(is_buy=False)
    bpi.add(is_buy=False)
    assert abs(bpi.short - 1 / 3) < 0.01
    assert abs(bpi.long - 3 / 5) < 0.01


def test_reset():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    bpi.reset()
    assert bpi.short == 0.5
    assert bpi.long == 0.5


def test_sell_signal():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    bpi.add(is_buy=False)
    bpi.add(is_buy=False)
    bpi.add(is_buy=False)
    assert bpi.is_sell_signal(threshold=0.4)


def test_no_sell_signal_when_short_above_long():
    bpi = BpiCalculator(short_window=3, long_window=5)
    for _ in range(5):
        bpi.add(is_buy=True)
    assert not bpi.is_sell_signal(threshold=0.4)
