# SPDX-License-Identifier: GPL-3.0-or-later
"""core.dense: dense keys in the time window with the borders preserved (docs/design/ephemeral-rig.md,
"Keys densas: regra de escrita")."""

import numpy as np
import pytest

from animation_sculptor.core import bezier, dense
from animation_sculptor.core.fcurve_model import ChannelModel

KEYS = [(1.0, 0.0), (10.0, 0.6), (16.0, 1.0), (18.0, 0.9), (26.0, 0.2), (40.0, 0.5)]
ALL = np.arange(-5, 51, dtype=np.float64)


def _model(types="AUTO_CLAMPED", interp="BEZIER", border_types=None):
    co = np.array(KEYS)
    x, y = co[:, 0], co[:, 1]
    slope = np.gradient(y, x)
    hl = np.stack((x - 2.0, y - 2.0 * slope), axis=1)
    hr = np.stack((x + 2.0, y + 2.0 * slope), axis=1)
    hl_t, hr_t = [types] * len(x), [types] * len(x)
    if border_types:
        for i, t in border_types.items():
            hl_t[i] = hr_t[i] = t
    return ChannelModel(co, hl, hr, hl_t, hr_t, [interp] * len(x))


def _window_values(model, a, b, bump=0.3):
    f = np.arange(a, b + 1, dtype=np.float64)
    return bezier.evaluate(model, f) + bump * np.sin(f)


@pytest.mark.parametrize("variant", [
    dict(), dict(types="ALIGNED"), dict(border_types={1: "FREE", 4: "FREE"}),
    dict(border_types={1: "VECTOR", 4: "VECTOR"}), dict(interp="LINEAR"),
])
@pytest.mark.parametrize("a,b", [(14, 22), (11, 17), (16, 18), (2, 39)])
def test_outside_the_window_nothing_changes(variant, a, b):
    m = _model(**variant)
    out = dense.write_dense(m, a, _window_values(m, a, b))
    outside = (ALL < a) | (ALL > b)
    assert np.abs(bezier.evaluate(out, ALL)[outside] - bezier.evaluate(m, ALL)[outside]).max() < 1e-6


@pytest.mark.parametrize("a,b", [(14, 22), (11, 17), (2, 39)])
def test_inside_the_window_integer_frames_take_the_values(a, b):
    m = _model()
    vals = _window_values(m, a, b)
    out = dense.write_dense(m, a, vals)
    assert np.abs(bezier.evaluate(out, np.arange(a, b + 1, dtype=np.float64)) - vals).max() < 1e-6


def test_keys_outside_the_borders_are_bit_identical_and_one_key_per_frame_between():
    m = _model()
    out = dense.write_dense(m, 14, _window_values(m, 14, 22))
    f_start, f_end, k_left, k_right = dense.window_span(m, 14, 22)
    assert (f_start, f_end, k_left, k_right) == (11, 25, 1, 4)
    assert np.array_equal(out.frames, np.r_[1.0, 10.0, np.arange(11, 26), 26.0, 40.0])
    for src, dst in ((0, 0), (5, len(out.frames) - 1)):
        assert np.array_equal(out.co[dst], m.co[src])
        assert np.array_equal(out.hl[dst], m.hl[src]) and np.array_equal(out.hr[dst], m.hr[src])
        assert (out.hl_type[dst], out.hr_type[dst], out.interp[dst]) == (m.hl_type[src], m.hr_type[src], m.interp[src])


@pytest.mark.parametrize("types", ["AUTO", "AUTO_CLAMPED", "ALIGNED"])
def test_auto_borders_are_frozen_aligned_and_collinear(types):
    m = _model(types=types)
    out = dense.write_dense(m, 14, _window_values(m, 14, 22))
    left, right = 1, len(out.frames) - 2
    for j, outer, inner in ((left, out.hl, out.hr), (right, out.hr, out.hl)):
        assert out.hl_type[j] == out.hr_type[j] == "ALIGNED"
        key = out.co[j]
        assert np.array_equal(key, m.co[1] if j == left else m.co[4])
        u, v = key - outer[j], inner[j] - key
        assert abs(u[0] * v[1] - u[1] * v[0]) < 1e-12           # collinear
        assert u[0] * v[0] > 0.0                                # on opposite sides of the key
    assert np.array_equal(out.hl[left], m.hl[1]) and np.array_equal(out.hr[right], m.hr[4])


@pytest.mark.parametrize("a,b", [(14, 22), (-3, 5), (35, 45), (-10, 60), (10, 16)])
def test_writing_the_current_values_changes_nothing(a, b):
    m = _model()
    cur = bezier.evaluate(m, np.arange(a, b + 1, dtype=np.float64))
    out = dense.write_dense(m, a, cur)
    assert np.abs(bezier.evaluate(out, ALL) - bezier.evaluate(m, ALL)).max() < 1e-6


def test_window_before_first_key_and_after_last_key():
    m = _model()
    out = dense.write_dense(m, -3, _window_values(m, -3, 4))
    assert out.frames[0] == -3.0 and dense.window_span(m, -3, 4)[2] is None
    out = dense.write_dense(m, 36, _window_values(m, 36, 45))
    assert out.frames[-1] == 45.0 and dense.window_span(m, 36, 45)[3] is None


def test_empty_model_gets_the_window_keys():
    empty = ChannelModel(np.empty((0, 2)), np.empty((0, 2)), np.empty((0, 2)))
    out = dense.write_dense(empty, 5, [1.0, 2.0, 3.0], default=0.0)
    assert np.array_equal(out.frames, [5.0, 6.0, 7.0])
    assert np.array_equal(out.values, [1.0, 2.0, 3.0])
    assert out.hl_type == ["AUTO_CLAMPED"] * 3 and out.interp == ["BEZIER"] * 3


def test_deterministic():
    m = _model()
    a = dense.write_dense(m, 14, _window_values(m, 14, 22))
    b = dense.write_dense(m, 14, _window_values(m, 14, 22))
    assert a.same_as(b)
