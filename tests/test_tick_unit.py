from src.engine.tick_unit import get_tick_unit, round_to_tick


def test_tick_unit_below_2000():
    assert get_tick_unit(1500) == 1
    assert get_tick_unit(1) == 1
    assert get_tick_unit(1999) == 1


def test_tick_unit_2000_to_5000():
    assert get_tick_unit(2000) == 5
    assert get_tick_unit(4999) == 5


def test_tick_unit_5000_to_10000():
    assert get_tick_unit(5000) == 10
    assert get_tick_unit(9999) == 10


def test_tick_unit_10000_to_50000():
    assert get_tick_unit(10000) == 50
    assert get_tick_unit(49999) == 50


def test_tick_unit_50000_to_200000():
    assert get_tick_unit(50000) == 100
    assert get_tick_unit(199999) == 100


def test_tick_unit_200000_to_500000():
    assert get_tick_unit(200000) == 500
    assert get_tick_unit(499999) == 500


def test_tick_unit_above_500000():
    assert get_tick_unit(500000) == 1000
    assert get_tick_unit(1000000) == 1000


def test_round_to_tick_up():
    assert round_to_tick(10030, direction="up") == 10050
    assert round_to_tick(10050, direction="up") == 10050


def test_round_to_tick_down():
    assert round_to_tick(10030, direction="down") == 10000
    assert round_to_tick(10050, direction="down") == 10050
