# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from animation_sculptor.core import onion


@pytest.mark.parametrize("past,future,expected", [
    (0, 0, (0, 0, 1)),
    (5, 0, (5, 0, 1)),
    (0, 7, (0, 7, 1)),
    (12, 12, (12, 12, 1)),
    (13, 4, (6, 2, 2)),
    (20, 15, (10, 7, 2)),
    (100, 30, (12, 3, 8)),
    (13, 12, (6, 6, 2)),
    (0.4, 3.0, (0, 3, 1)),
])
def test_window(past, future, expected):
    assert onion.window(past, future) == expected


@pytest.mark.parametrize("past,future,cap", [(30, 60, 12), (7, 99, 5), (1, 1, 1), (250, 3, 12)])
def test_window_never_exceeds_cap_nor_window(past, future, cap):
    before, after, step = onion.window(past, future, cap)
    assert before <= cap and after <= cap
    assert before * step <= past and after * step <= future
    if step > 1:   # smallest step that fits: one less would exceed the cap
        assert max(int(past), int(future)) // (step - 1) > cap


def test_spread_offset_is_proportional_and_signed():
    assert onion.spread_offset(10, 10, 1, 2.0) == 0.0
    assert onion.spread_offset(8, 10, 1, 2.0) == -4.0
    assert onion.spread_offset(13, 10, 1, 2.0) == 6.0
    assert onion.spread_offset(14, 10, 2, 2.0) == 4.0
