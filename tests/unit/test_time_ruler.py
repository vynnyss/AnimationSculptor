# SPDX-License-Identifier: GPL-3.0-or-later
"""core.falloff.weight_signed (asymmetric falloff) and core.ruler (time-ruler geometry)."""

import numpy as np
import pytest

from animation_sculptor.core import falloff, ruler
from animation_sculptor.core.falloff import weight, weight_signed
from animation_sculptor.core.ruler import FUTURE, PAST

SHAPES = falloff.SHAPES


# ---------------------------------------------------------------- weight_signed

@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("rp,rf", [(3, 10), (10, 3), (5, 5), (0, 4), (4, 0), (0, 0)])
def test_signed_is_one_at_centre(shape, rp, rf):
    assert float(weight_signed(0.0, rp, rf, shape)) == 1.0


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("o", [0.5, 1.0, 2.5, 3.0, 7.0, 9.9, 12.0])
def test_signed_matches_plain_weight_per_side(shape, o):
    rp, rf = 4.0, 10.0
    assert float(weight_signed(-o, rp, rf, shape)) == float(weight(o, rp, shape))
    assert float(weight_signed(o, rp, rf, shape)) == float(weight(o, rf, shape))


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("rp,rf", [(3.0, 10.0), (10.0, 3.0), (6.0, 6.0)])
def test_signed_zero_at_and_beyond_each_radius(shape, rp, rf):
    for extra in (0.0, 0.5, 5.0, 100.0):
        assert float(weight_signed(-(rp + extra), rp, rf, shape)) == 0.0
        assert float(weight_signed(rf + extra, rp, rf, shape)) == 0.0


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_asymmetry(shape):
    assert float(weight_signed(-5, 3, 10, shape)) == 0.0
    assert float(weight_signed(5, 3, 10, shape)) > 0.0
    assert float(weight_signed(5, 10, 3, shape)) == 0.0
    assert float(weight_signed(-5, 10, 3, shape)) > 0.0


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_zero_radius_past_keeps_only_centre_on_that_side(shape):
    offs = np.array([-8.0, -3.0, -0.5, 0.0, 0.5, 3.0, 7.0])
    w = weight_signed(offs, 0.0, 6.0, shape)
    assert np.all(w[offs < 0] == 0.0)
    assert w[offs == 0.0][0] == 1.0
    assert np.array_equal(w[offs > 0], weight(offs[offs > 0], 6.0, shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_zero_radius_future_keeps_only_centre_on_that_side(shape):
    offs = np.array([-8.0, -3.0, -0.5, 0.0, 0.5, 3.0, 7.0])
    w = weight_signed(offs, 6.0, 0.0, shape)
    assert np.all(w[offs > 0] == 0.0)
    assert w[offs == 0.0][0] == 1.0
    assert np.array_equal(w[offs < 0], weight(-offs[offs < 0], 6.0, shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_both_radii_zero_is_only_centre(shape):
    offs = np.array([-2.0, -0.1, 0.0, 0.1, 2.0])
    assert np.array_equal(weight_signed(offs, 0.0, 0.0, shape), [0, 0, 1, 0, 0])


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("r", [1.0, 4.0, 12.5])
def test_signed_equal_radii_is_symmetric(shape, r):
    o = np.linspace(0.0, r * 1.5, 40)
    assert np.array_equal(weight_signed(-o, r, r, shape), weight_signed(o, r, r, shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_scalar_and_array(shape):
    offs = np.array([-6.0, -2.0, 0.0, 3.0, 9.0])
    arr = weight_signed(offs, 4.0, 8.0, shape)
    assert arr.shape == offs.shape
    for o, a in zip(offs, arr):
        assert float(weight_signed(float(o), 4.0, 8.0, shape)) == float(a)
    assert np.all((arr >= 0.0) & (arr <= 1.0))


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_monotonic_non_increasing_per_side(shape):
    mag = np.linspace(0.0, 15.0, 301)
    past = weight_signed(-mag, 5.0, 11.0, shape)
    future = weight_signed(mag, 5.0, 11.0, shape)
    assert np.all(np.diff(past) <= 1e-12)
    assert np.all(np.diff(future) <= 1e-12)


@pytest.mark.parametrize("shape", SHAPES)
def test_signed_is_deterministic(shape):
    offs = np.linspace(-20.0, 20.0, 161)
    a = weight_signed(offs, 7.0, 13.0, shape)
    b = weight_signed(offs, 7.0, 13.0, shape)
    assert np.array_equal(a, b)


# ---------------------------------------------------------------- ruler: half_span / tick_step

@pytest.mark.parametrize("rp,rf", [(0, 0), (3, 4), (16, 0), (0, 16), (17, 3), (40, 40), (100, 7), (500, 500), (123.4, 5)])
def test_half_span_properties(rp, rf):
    h = ruler.half_span_for(rp, rf)
    assert h >= ruler.MIN_HALF_SPAN
    assert h % 5 == 0
    assert h >= 1.25 * max(rp, rf)


def test_half_span_minimum_and_growth():
    assert ruler.half_span_for(0, 0) == ruler.MIN_HALF_SPAN
    assert ruler.half_span_for(100, 0) == 125
    assert ruler.half_span_for(-5, -5) == ruler.MIN_HALF_SPAN


@pytest.mark.parametrize("ppf", [0.05, 0.3, 1.0, 2.0, 5.5, 12.0, 40.0, 100.0])
@pytest.mark.parametrize("min_px", [6.0, 12.0, 40.0, 80.0])
def test_tick_step_is_smallest_nice_step(ppf, min_px):
    step = ruler.tick_step(ppf, min_px)
    assert step in ruler.NICE_STEPS
    if step * ppf >= min_px:
        smaller = [s for s in ruler.NICE_STEPS if s < step]
        assert all(s * ppf < min_px for s in smaller)


def test_tick_step_returns_last_when_nothing_fits():
    assert ruler.tick_step(0.001, 1000.0) == ruler.NICE_STEPS[-1]


def test_tick_step_exact_boundary_and_first():
    assert ruler.tick_step(10.0, 10.0) == 1
    assert ruler.tick_step(10.0, 10.5) == 2
    assert ruler.tick_step(100.0, 1.0) == 1


# ---------------------------------------------------------------- ruler: layout

def _lay(w=1200.0, h=800.0, px=1.0, f0=100.0, half=40):
    lay = ruler.layout(w, h, px, f0, half)
    assert lay is not None
    return lay


@pytest.mark.parametrize("w,h,px", [
    (100, 800, 1.0), (1200, 100, 1.0), (199, 800, 1.0), (300, 200, 2.0), (50, 50, 1.0),
])
def test_layout_none_for_tiny_regions(w, h, px):
    assert ruler.layout(w, h, px, 1.0, 20) is None


def test_layout_none_for_non_positive_half_span():
    assert ruler.layout(1200, 800, 1.0, 1.0, 0) is None


@pytest.mark.parametrize("w,px", [(1200.0, 1.0), (400.0, 1.0), (2000.0, 2.0), (700.0, 1.5)])
def test_layout_geometry(w, px):
    lay = _lay(w=w, h=900.0, px=px, f0=37.0, half=25)
    assert lay.cx == w / 2.0
    assert lay.width <= ruler.MAX_WIDTH_PX * px + 1e-9
    assert lay.width >= 120.0 * px
    assert lay.cx - lay.left == pytest.approx(lay.right - lay.cx)
    assert lay.right - lay.left == pytest.approx(lay.width)
    assert lay.y == ruler.BOTTOM_PX * px
    assert lay.height == ruler.HEIGHT_PX * px
    assert lay.ppf == pytest.approx(lay.width / 50.0)


def test_layout_width_capped():
    lay = _lay(w=5000.0)
    assert lay.width == ruler.MAX_WIDTH_PX == 1400.0


def test_layout_width_fills_region_minus_margins():
    lay = _lay(w=1000.0, px=1.0)
    assert lay.width == 1000.0 - 2 * ruler.SIDE_MARGIN_PX
    lay = _lay(w=2000.0, px=2.0)
    assert lay.width == 2000.0 - 2 * ruler.SIDE_MARGIN_PX * 2.0
    assert _lay(w=5000.0, px=2.0).width == 2800.0


@pytest.mark.parametrize("frame", [-50.0, 0.0, 60.0, 100.0, 123.456, 500.0])
def test_x_of_frame_of_inverse(frame):
    lay = _lay()
    assert lay.frame_of(lay.x_of(frame)) == pytest.approx(frame)
    assert lay.x_of(lay.frame_of(321.0)) == pytest.approx(321.0)


def test_x_of_f0_is_centre_and_edges_are_half_span():
    lay = _lay(f0=77.0, half=30)
    assert lay.x_of(77.0) == lay.cx
    assert lay.x_of(77.0 - 30) == pytest.approx(lay.left)
    assert lay.x_of(77.0 + 30) == pytest.approx(lay.right)


@pytest.mark.parametrize("half", [20, 35, 125, 600])
@pytest.mark.parametrize("f0", [1.0, 100.0, 250.5])
@pytest.mark.parametrize("px", [1.0, 2.0])
def test_ticks_inside_range_and_labels_on_major(half, f0, px):
    lay = _lay(w=2400.0, px=px, f0=f0, half=half)
    ticks = lay.ticks()
    assert ticks
    major = ruler.tick_step(lay.ppf, 40.0 * px)
    minor = ruler.tick_step(lay.ppf, 6.0 * px)
    for f, labelled in ticks:
        assert isinstance(f, int)
        assert f0 - half <= f <= f0 + half
        assert f % minor == 0
        assert labelled == (f % major == 0)
        if labelled:
            assert f % major == 0
    frames = [f for f, _ in ticks]
    assert frames == sorted(set(frames))


# ---------------------------------------------------------------- ruler: handles

def test_handle_x_positions_and_clamp():
    lay = _lay(f0=100.0, half=40)
    assert handle_x_ok(lay, PAST, 10, 20) == pytest.approx(lay.x_of(90.0))
    assert handle_x_ok(lay, FUTURE, 10, 20) == pytest.approx(lay.x_of(120.0))
    assert handle_x_ok(lay, PAST, 0, 0) == lay.cx
    assert handle_x_ok(lay, FUTURE, 0, 0) == lay.cx


def handle_x_ok(lay, side, rp, rf):
    return ruler.handle_x(lay, side, rp, rf)


@pytest.mark.parametrize("huge", [41, 100, 500, 1e6])
def test_handle_x_clamped_to_ruler(huge):
    lay = _lay(f0=100.0, half=40)
    assert ruler.handle_x(lay, PAST, huge, 0) == pytest.approx(lay.left)
    assert ruler.handle_x(lay, FUTURE, 0, huge) == pytest.approx(lay.right)
    for rp, rf in [(huge, huge), (0, huge), (huge, 0)]:
        for side in (PAST, FUTURE):
            x = ruler.handle_x(lay, side, rp, rf)
            assert lay.left <= x <= lay.right


@pytest.mark.parametrize("px", [1.0, 2.0])
def test_hit_handle_near_each_handle(px):
    lay = _lay(w=2000.0, h=900.0, px=px)
    rp, rf = 10, 25
    xp = ruler.handle_x(lay, PAST, rp, rf)
    xf = ruler.handle_x(lay, FUTURE, rp, rf)
    ymid = lay.y + lay.height / 2
    tol = ruler.HANDLE_TOL_PX * px
    assert ruler.hit_handle(lay, (xp, ymid), rp, rf) == PAST
    assert ruler.hit_handle(lay, (xf, ymid), rp, rf) == FUTURE
    assert ruler.hit_handle(lay, (xp + tol * 0.9, ymid), rp, rf) == PAST
    assert ruler.hit_handle(lay, (xf - tol * 0.9, ymid), rp, rf) == FUTURE


@pytest.mark.parametrize("px", [1.0, 2.0])
def test_hit_handle_none_when_far(px):
    lay = _lay(w=2000.0, h=900.0, px=px)
    rp, rf = 10, 25
    xp = ruler.handle_x(lay, PAST, rp, rf)
    xf = ruler.handle_x(lay, FUTURE, rp, rf)
    ymid = lay.y + lay.height / 2
    tol = ruler.HANDLE_TOL_PX * px
    mid = (xp + xf) / 2.0
    assert ruler.hit_handle(lay, (mid, ymid), rp, rf) is None
    assert ruler.hit_handle(lay, (xp - tol * 1.5, ymid), rp, rf) is None
    assert ruler.hit_handle(lay, (xf + tol * 1.5, ymid), rp, rf) is None
    # vertical: outside strip +- tolerance
    below = lay.y - (ruler.TRI_BOTTOM_PX + 6.0) * px
    assert ruler.hit_handle(lay, (xp, below), rp, rf) is None
    assert ruler.hit_handle(lay, (xf, lay.y + lay.height + tol * 1.5), rp, rf) is None
    # vertical: inside tolerance band still hits
    assert ruler.hit_handle(lay, (xp, lay.y - tol * 0.9), rp, rf) == PAST
    assert ruler.hit_handle(lay, (xf, lay.y + lay.height + tol * 0.9), rp, rf) == FUTURE


def test_hit_handle_tolerance_scales_with_px():
    # A 12 px horizontal offset misses at px=1 (tol 8) but hits at px=2 (tol 16).
    for px, expected in ((1.0, None), (2.0, PAST)):
        lay = _lay(w=2000.0, h=900.0, px=px)
        xp = ruler.handle_x(lay, PAST, 10, 25)
        ymid = lay.y + lay.height / 2
        assert ruler.hit_handle(lay, (xp - 12.0, ymid), 10, 25) == expected


def test_hit_handle_coincident_split_by_mouse_side():
    lay = _lay()
    ymid = lay.y + lay.height / 2
    assert ruler.hit_handle(lay, (lay.cx - 3.0, ymid), 0, 0) == PAST
    assert ruler.hit_handle(lay, (lay.cx + 3.0, ymid), 0, 0) == FUTURE
    assert ruler.hit_handle(lay, (lay.cx - ruler.HANDLE_TOL_PX * 2, ymid), 0, 0) is None
    assert ruler.hit_handle(lay, (lay.cx + ruler.HANDLE_TOL_PX * 2, ymid), 0, 0) is None


def test_hit_handle_closest_wins_when_overlapping():
    lay = _lay()
    ymid = lay.y + lay.height / 2
    # radii 1 and 1 -> handles ~ppf px either side of centre, within tolerance of each other
    xp = ruler.handle_x(lay, PAST, 1, 1)
    xf = ruler.handle_x(lay, FUTURE, 1, 1)
    assert ruler.hit_handle(lay, (xp - 0.1, ymid), 1, 1) == PAST
    assert ruler.hit_handle(lay, (xf + 0.1, ymid), 1, 1) == FUTURE


# ---------------------------------------------------------------- ruler: radius_from_x

@pytest.mark.parametrize("side", [PAST, FUTURE])
@pytest.mark.parametrize("snap", [True, False])
def test_radius_never_negative(side, snap):
    lay = _lay()
    wrong_side = lay.right + 500 if side == PAST else lay.left - 500
    assert ruler.radius_from_x(lay, side, wrong_side, snap) == 0.0
    assert ruler.radius_from_x(lay, side, lay.cx, snap) == 0.0


@pytest.mark.parametrize("side", [PAST, FUTURE])
def test_radius_max_500(side):
    lay = _lay()
    far = -1e7 if side == PAST else 1e7
    assert ruler.radius_from_x(lay, side, far) == 500.0
    assert ruler.radius_from_x(lay, side, far, snap=False) == 500.0


@pytest.mark.parametrize("side", [PAST, FUTURE])
def test_radius_snap_and_exact(side):
    lay = _lay(f0=100.0, half=40)
    sign = -1.0 if side == PAST else 1.0
    x = lay.cx + sign * 7.4 * lay.ppf
    assert ruler.radius_from_x(lay, side, x) == 7.0
    assert ruler.radius_from_x(lay, side, x, snap=False) == pytest.approx(7.4)
    x = lay.cx + sign * 7.6 * lay.ppf
    assert ruler.radius_from_x(lay, side, x) == 8.0


def test_radius_direction_of_growth():
    lay = _lay()
    xs = [lay.cx + d for d in (-100.0, -50.0, 0.0, 50.0, 100.0)]
    past = [ruler.radius_from_x(lay, PAST, x, snap=False) for x in xs]
    future = [ruler.radius_from_x(lay, FUTURE, x, snap=False) for x in xs]
    assert past == sorted(past, reverse=True) and past[0] > past[-1]
    assert future == sorted(future) and future[-1] > future[0]


@pytest.mark.parametrize("side", [PAST, FUTURE])
@pytest.mark.parametrize("radius", [0, 1, 5, 13, 24, 40])
@pytest.mark.parametrize("px", [1.0, 2.0])
def test_radius_round_trip_inside_ruler(side, radius, px):
    lay = _lay(w=2400.0, px=px, f0=57.0, half=40)
    rp, rf = (radius, 0) if side == PAST else (0, radius)
    x = ruler.handle_x(lay, side, rp, rf)
    assert ruler.radius_from_x(lay, side, x) == radius
    assert ruler.radius_from_x(lay, side, x, snap=False) == pytest.approx(radius)


# ---------------------------------------------------------------- ruler v2: triangles, key marks

@pytest.mark.parametrize("px", [1.0, 2.0])
def test_triangle_geometry(px):
    lay = _lay(w=2000.0, px=px)
    x = lay.cx + 50.0
    for side, sign in ((PAST, -1.0), (FUTURE, 1.0)):
        apex, outer, inner = ruler.triangle(lay, side, x)
        assert apex[0] == inner[0] == x
        assert apex[1] > inner[1] == outer[1]
        assert apex[1] < lay.y                       # entirely below the strip
        assert (outer[0] - x) * sign == pytest.approx(ruler.TRI_WIDTH_PX * px)


@pytest.mark.parametrize("px", [1.0, 2.0])
def test_hit_handle_covers_triangle(px):
    lay = _lay(w=2000.0, px=px)
    rp, rf = 10, 25
    for side, sign in ((PAST, -1.0), (FUTURE, 1.0)):
        x = ruler.handle_x(lay, side, rp, rf)
        _a, outer, inner = ruler.triangle(lay, side, x)
        # the outer base corner and the base centre are on the handle
        assert ruler.hit_handle(lay, (outer[0], outer[1] + 0.5 * px), rp, rf) == side
        assert ruler.hit_handle(lay, ((outer[0] + inner[0]) / 2, inner[1] + 0.5 * px), rp, rf) == side
        # the same x inside the strip (no triangle there) is beyond the bar tolerance
        far = x + sign * (ruler.HANDLE_TOL_PX + ruler.TRI_WIDTH_PX) * px
        assert ruler.hit_handle(lay, (far, lay.y + lay.height / 2), rp, rf) is None


def test_hit_handle_triangles_of_coincident_handles_split():
    lay = _lay()
    y = lay.y - ruler.TRI_BOTTOM_PX * 0.8
    assert ruler.hit_handle(lay, (lay.cx - 4.0, y), 0, 0) == PAST
    assert ruler.hit_handle(lay, (lay.cx + 4.0, y), 0, 0) == FUTURE


def test_key_marks_classify_dedupe_and_clip():
    marks = ruler.key_marks([10, 10.2, 5, 20, 100, 14, -50], 10.0, 0.0, 30.0)
    assert marks == [(5, PAST), (10, "CURRENT"), (14, FUTURE), (20, FUTURE)]
    assert ruler.key_marks([], 1.0, 0.0, 10.0) == []


def test_wide_ruler_shows_more_frames():
    from animation_sculptor.core import ruler as r
    w = r.ruler_width(2000.0, 1.0)
    hs = r.half_span_for_width(0.0, 0.0, w, 1.0)
    assert hs % 5 == 0 and hs >= r.MIN_HALF_SPAN
    assert w / (2.0 * hs) <= r.TARGET_PX_PER_FRAME + 1e-9
    assert r.half_span_for_width(200.0, 0.0, w, 1.0) >= r.half_span_for(200.0, 0.0)
