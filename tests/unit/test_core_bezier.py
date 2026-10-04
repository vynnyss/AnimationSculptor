# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for core.bezier (Blender F-Curve evaluation port; pure numpy, no Blender)."""

import numpy as np

from animation_sculptor.core import bezier
from animation_sculptor.core.fcurve_model import ChannelModel


def two_keys(y0=0.0, y1=5.0, h1=(3.0, 1.0), h2=(7.0, 4.0), interp="BEZIER", extrapolation="CONSTANT"):
    co = np.array([[0.0, y0], [10.0, y1]])
    hl = np.array([[-3.0, y0], list(h2)])
    hr = np.array([list(h1), [13.0, y1]])
    m = ChannelModel(co, hl, hr, interp=[interp, interp], extrapolation=extrapolation)
    m.hl_type = ["FREE"] * 2
    m.hr_type = ["FREE"] * 2
    return m


def empty():
    return ChannelModel(np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2)))


def cubic_x(t, q):
    mt = 1.0 - t
    return mt ** 3 * q[0] + 3 * mt * mt * t * q[1] + 3 * mt * t * t * q[2] + t ** 3 * q[3]


def test_evaluate_at_key_frames_returns_key_values():
    m = two_keys()
    np.testing.assert_array_equal(bezier.evaluate(m, [0.0, 10.0]), [0.0, 5.0])
    co = np.array([[0, 0], [4, 3], [10, -2.0]])
    m3 = ChannelModel(co, co - [1, 0], co + [1, 0])
    assert bezier.evaluate(m3, [4.0])[0] == 3.0
    assert bezier.evaluate(m3, [4.00005])[0] == 3.0
    assert bezier.evaluate(m3, [3.99995])[0] == 3.0
    assert abs(bezier.evaluate(m3, [4.01])[0] - 3.0) > 1e-4


def test_constant_interpolation_holds_left_value():
    m = two_keys(interp="CONSTANT")
    np.testing.assert_array_equal(bezier.evaluate(m, [0.5, 5.0, 9.9]), [0.0, 0.0, 0.0])
    assert bezier.evaluate(m, [10.0])[0] == 5.0


def test_linear_interpolation_matches_formula():
    m = two_keys(y0=1.0, y1=5.0, interp="LINEAR")
    f = np.array([0.5, 2.5, 7.0, 9.25])
    np.testing.assert_allclose(bezier.evaluate(m, f), 1.0 + 4.0 * f / 10.0, atol=1e-6)


def test_constant_extrapolation():
    m = two_keys(y0=1.0, y1=5.0)
    np.testing.assert_array_equal(bezier.evaluate(m, [-5.0, -0.1, 10.1, 50.0]), [1.0, 1.0, 5.0, 5.0])


def test_linear_extrapolation_linear_end_key_uses_neighbor_slope():
    m = two_keys(y0=1.0, y1=5.0, interp="LINEAR", extrapolation="LINEAR")
    np.testing.assert_allclose(bezier.evaluate(m, [-5.0, 15.0]), [-1.0, 7.0], atol=1e-6)


def test_linear_extrapolation_bezier_end_key_uses_handle_slope():
    m = two_keys(y0=1.0, y1=5.0, extrapolation="LINEAR")
    m.hl[0] = [-2.0, 1.0 - 4.0]     # slope (y - hy) / (x - hx) = 2 at the first key
    m.hr[1] = [12.0, 5.0 + 6.0]     # slope 3 at the last key
    np.testing.assert_allclose(bezier.evaluate(m, [-3.0, 14.0]), [1.0 - 6.0, 5.0 + 12.0], atol=1e-5)


def test_single_key_is_constant():
    m = ChannelModel(np.array([[3.0, 2.5]]), np.array([[2.0, 2.5]]), np.array([[4.0, 2.5]]),
                     extrapolation="LINEAR")
    np.testing.assert_array_equal(bezier.evaluate(m, [-10.0, 3.0, 99.0]), [2.5, 2.5, 2.5])


def test_empty_model_returns_zeros():
    out = bezier.evaluate(empty(), [0.0, 1.0, 2.0])
    assert out.shape == (3,)
    np.testing.assert_array_equal(out, 0.0)


def test_correct_bezpart_no_change_within_segment():
    v1, v2, v3, v4 = [0.0, 0.0], [3.0, 1.0], [7.0, 4.0], [10.0, 5.0]
    v2c, v3c, f1, f2 = bezier.correct_bezpart(v1, v2, v3, v4)
    np.testing.assert_array_equal(v2c, v2)
    np.testing.assert_array_equal(v3c, v3)
    assert f1 == 1.0 and f2 == 1.0


def test_correct_bezpart_scales_each_handle_independently():
    v1, v2, v3, v4 = [0.0, 0.0], [15.0, 3.0], [7.0, 4.0], [10.0, 5.0]
    v2c, v3c, f1, f2 = bezier.correct_bezpart(v1, v2, v3, v4)
    np.testing.assert_allclose(f1, 10.0 / 15.0, rtol=1e-6)
    np.testing.assert_allclose(v2c, [10.0, 2.0], atol=1e-5)
    np.testing.assert_array_equal(v3c, v3)      # untouched
    assert f2 == 1.0
    # now the right key's handle reaches back past the left key
    v2c, v3c, f1, f2 = bezier.correct_bezpart([0.0, 0.0], [3.0, 1.0], [-10.0, 0.0], [10.0, 5.0])
    np.testing.assert_array_equal(v2c, [3.0, 1.0])
    assert f1 == 1.0
    np.testing.assert_allclose(f2, 0.5, rtol=1e-6)
    np.testing.assert_allclose(v3c, [0.0, 2.5], atol=1e-5)


def test_findzero_monotone_x():
    q = (0.0, 3.0, 7.0, 10.0)
    frames = np.linspace(0.1, 9.9, 50)
    t, found = bezier.findzero(frames, *q)
    assert found.all()
    assert (t >= 0.0).all() and (t <= 1.0).all()
    np.testing.assert_allclose(cubic_x(t.astype(np.float64), q), frames, atol=1e-4)
    assert (np.diff(t) > 0).all()


def test_solve_cubic_known_roots():
    # (t - 0.25)(t^2 + 1) = t^3 - 0.25 t^2 + t - 0.25
    t, found = bezier.solve_cubic(-0.25, 1.0, -0.25, 1.0)
    assert found.all()
    np.testing.assert_allclose(t, 0.25, atol=1e-6)
    # linear fallback
    t, found = bezier.solve_cubic(-1.0, 4.0, 0.0, 0.0)
    assert found.all()
    np.testing.assert_allclose(t, 0.25, atol=1e-6)
    # no root in [0, 1]
    _t, found = bezier.solve_cubic(5.0, 1.0, 0.0, 0.0)
    assert not found.any()


def test_bernstein_partition_of_unity_and_shape():
    t = np.random.default_rng(0).uniform(0.0, 1.0, 37)
    b = bezier.bernstein(t)
    assert b.shape == (4, 37)
    np.testing.assert_allclose(b.sum(axis=0), 1.0, atol=1e-12)
    assert (b >= 0).all()
    np.testing.assert_allclose(bezier.bernstein([0.0, 1.0]), [[1, 0], [0, 0], [0, 0], [0, 1]], atol=1e-15)


def test_segment_value_is_bernstein_combination():
    m = two_keys(y0=1.0, y1=5.0, h1=(3.0, 2.0), h2=(7.0, 6.5))
    frames = np.linspace(0.3, 9.7, 40)
    t, found = bezier.segment_t(m, 0, frames)
    assert found.all()
    expected = np.array([1.0, 2.0, 6.5, 5.0]) @ bezier.bernstein(t)
    np.testing.assert_allclose(bezier.evaluate(m, frames), expected, atol=1e-5)


def test_value_is_linear_in_handle_y():
    frames = np.linspace(0.3, 9.7, 40)
    base = two_keys(y0=1.0, y1=5.0, h1=(3.0, 2.0), h2=(7.0, 6.0))
    t, _ = bezier.segment_t(base, 0, frames)
    b = bezier.bernstein(t)
    v0 = bezier.evaluate(base, frames)

    def shifted(d1, d2):
        m = base.copy()
        m.hr[0, 1] += d1
        m.hl[1, 1] += d2
        return bezier.evaluate(m, frames)

    for d in (0.5, 1.0):
        np.testing.assert_allclose(shifted(d, 0.0) - v0, d * b[1], atol=1e-4)
        np.testing.assert_allclose(shifted(0.0, d) - v0, d * b[2], atol=1e-4)
    np.testing.assert_allclose(shifted(2.0, 0.0) - v0, 2.0 * (shifted(1.0, 0.0) - v0), atol=1e-4)
    # t does not depend on the handle y values
    t2, _ = bezier.segment_t(base, 0, frames)
    np.testing.assert_array_equal(t, t2)


def test_flat_segment_shortcut():
    m = two_keys(y0=2.0, y1=2.0, h1=(3.0, 2.0), h2=(7.0, 2.0))
    np.testing.assert_array_equal(bezier.evaluate(m, [1.0, 5.0, 9.0]), [2.0, 2.0, 2.0])


def test_evaluate_is_deterministic():
    rng = np.random.default_rng(0)
    m = two_keys(h1=(2.0, 3.0), h2=(8.0, -1.0))
    frames = rng.uniform(-2.0, 12.0, 200)
    a = bezier.evaluate(m, frames)
    b = bezier.evaluate(m, frames)
    np.testing.assert_array_equal(a, b)
    assert a.dtype == np.float64
