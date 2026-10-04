# SPDX-License-Identifier: GPL-3.0-or-later
"""core.timing_ops: pose keys, retime and spacing (motion-sculpt-model.md, operations 3–4, invariants 3–4)."""

import numpy as np
import pytest

from animation_sculptor.core import bezier, timing_ops as T
from animation_sculptor.core.fcurve_model import ChannelModel

FRAMES = [1.0, 10.0, 20.0, 30.0]


def _chan(values, frames=FRAMES, dys=None, types="AUTO_CLAMPED", interp="BEZIER"):
    """Channel with 1/3-duration handles; ``dys`` are per-key handle slopes (value units per frame)."""
    n = len(frames)
    dys = dys if dys is not None else [0.1 * (i + 1) for i in range(n)]
    co, hl, hr = [], [], []
    for i, (f, v) in enumerate(zip(frames, values)):
        dl = (f - frames[i - 1]) / 3 if i > 0 else (frames[1] - f) / 3
        dr = (frames[i + 1] - f) / 3 if i < n - 1 else (f - frames[i - 1]) / 3
        co.append((f, v))
        hl.append((f - dl, v - dys[i] * dl))
        hr.append((f + dr, v + dys[i] * dr))
    return ChannelModel(co, hl, hr, [types] * n, [types] * n, [interp] * n)


def _xyz(**kw):
    return [_chan([0.0, 1.0, 3.0, 2.0], dys=[0.0, 0.2, 0.1, -0.3], **kw),
            _chan([0.0, 2.0, -1.0, 0.5], dys=[0.1, -0.2, 0.4, 0.0], **kw),
            _chan([1.0, 0.0, 0.7, 1.5], dys=[0.0, 0.3, -0.1, 0.2], **kw)]


def test_pose_keys_union_sorted_and_merged():
    a = _chan([0, 1, 2], frames=[1.0, 5.0, 9.0])
    b = _chan([0, 1], frames=[5.0 + 5e-4, 7.0])
    c = _chan([0, 1], frames=[1.0, 3.0])
    keys = T.pose_keys([a, b, c])
    np.testing.assert_allclose(keys, [1.0, 3.0, 5.0, 7.0, 9.0], atol=1e-3)
    assert len(T.pose_keys([a, b])) == 4
    assert (np.diff(keys) > 0).all()


def test_pose_keys_empty():
    assert T.pose_keys([]).size == 0
    empty = ChannelModel(np.empty((0, 2)), np.empty((0, 2)), np.empty((0, 2)))
    assert T.pose_keys([empty]).size == 0


def test_retime_limits_neighbours_and_open_ends():
    m = _xyz()
    assert T.retime_limits(m, 10.0) == (1.0, 20.0)
    assert T.retime_limits(m, 20.0) == (10.0, 30.0)
    assert T.retime_limits(m, 1.0) == (-np.inf, 10.0)
    assert T.retime_limits(m, 30.0) == (20.0, np.inf)


def test_retime_moves_key_and_handles_in_every_channel():
    m = _xyz()
    out, applied = T.retime(m, 10.0, 12.5)
    assert applied == 12.5
    for a, b in zip(m, out):
        np.testing.assert_array_equal(b.co[1] - a.co[1], [2.5, 0.0])
        np.testing.assert_array_equal(b.hl[1] - a.hl[1], [2.5, 0.0])
        np.testing.assert_array_equal(b.hr[1] - a.hr[1], [2.5, 0.0])
        for k in (0, 2, 3):
            np.testing.assert_array_equal(b.co[k], a.co[k])
            np.testing.assert_array_equal(b.hl[k], a.hl[k])
            np.testing.assert_array_equal(b.hr[k], a.hr[k])
        assert b.hl_type == a.hl_type and b.interp == a.interp
    assert m[0].co[1, 0] == 10.0                      # inputs untouched


def test_retime_channel_without_key_is_unchanged_and_no_key_created():
    full = _chan([0.0, 1.0, 3.0, 2.0])
    partial = _chan([0.0, 5.0], frames=[1.0, 20.0])   # no key at 10
    out, _ = T.retime([full, partial], 10.0, 14.0)
    assert out[1].same_as(partial)
    assert [o.key_count for o in out] == [4, 2]
    np.testing.assert_array_equal(out[0].co[:, 1], full.co[:, 1])


def test_retime_preserves_key_order_and_values():
    m = _xyz()
    for target in (-50.0, 2.0, 15.0, 19.5, 80.0):
        out, applied = T.retime(m, 10.0, target)
        for a, b in zip(m, out):
            assert (np.diff(b.frames) > 0).all()
            np.testing.assert_array_equal(b.values, a.values)
            np.testing.assert_array_equal(b.hl[:, 1], a.hl[:, 1])
            np.testing.assert_array_equal(b.hr[:, 1], a.hr[:, 1])


def test_retime_clamps_to_min_gap_from_neighbours():
    m = _xyz()
    assert T.retime(m, 10.0, 100.0)[1] == 19.0
    assert T.retime(m, 10.0, -100.0)[1] == 2.0
    assert T.retime(m, 10.0, 19.5, min_gap=2.0)[1] == 18.0
    assert T.retime(m, 1.0, -100.0)[1] == -100.0      # open end: free
    assert T.retime(m, 30.0, 500.0)[1] == 500.0


def test_retime_returns_applied_frame_and_zero_delta_is_identity():
    m = _xyz()
    out, applied = T.retime(m, 10.0, 10.0)
    assert applied == 10.0
    assert all(a.same_as(b) for a, b in zip(m, out))
    out, applied = T.retime(m, 10.0, 25.0)
    assert applied == 19.0 and out[0].co[1, 0] == 19.0


def test_retime_too_narrow_gap_does_not_move():
    close = _chan([0.0, 1.0, 2.0], frames=[1.0, 2.0, 3.0])
    out, applied = T.retime([close], 2.0, 2.4)
    assert applied == 2.0 and out[0].same_as(close)


def test_retime_keeps_the_moved_value():
    m = _xyz()
    out, applied = T.retime(m, 10.0, 13.0)
    for a, b in zip(m, out):
        assert bezier.evaluate(b, [applied])[0] == pytest.approx(bezier.evaluate(a, [10.0])[0], abs=1e-6)


def test_lambdas_and_clamp():
    m = _chan([0.0, 1.0, 3.0, 2.0])
    lo, li = T.segment_lambdas(m, 1)
    assert lo == pytest.approx(1 / 3) and li == pytest.approx(1 / 3)
    assert T.clamp_lambdas(0.0, -1.0) == (T.MIN_LAMBDA, T.MIN_LAMBDA)
    assert T.clamp_lambdas(0.3, 0.4) == (0.3, 0.4)
    lo, li = T.clamp_lambdas(0.9, 0.9)
    assert lo + li == pytest.approx(T.MAX_LAMBDA_SUM) and lo == pytest.approx(li)
    lo, li = T.clamp_lambdas(2.0, 0.5)               # proportional scaling
    assert lo + li == pytest.approx(T.MAX_LAMBDA_SUM) and lo / li == pytest.approx(4.0)


def _polyline(models, frames):
    return np.stack([bezier.evaluate(m, frames) for m in models], axis=1)


def _dist_to_polyline(points, poly):
    a, b = poly[:-1], poly[1:]
    ab = b - a
    denom = np.maximum((ab * ab).sum(1), 1e-30)
    best = np.full(len(points), np.inf)
    for i, p in enumerate(points):
        t = np.clip(((p - a) * ab).sum(1) / denom, 0.0, 1.0)
        best[i] = np.linalg.norm(a + t[:, None] * ab - p, axis=1).min()
    return best


def test_spacing_preserve_path_changes_only_inner_handle_x():
    m = _chan([0.0, 1.0, 3.0, 2.0], dys=[0.0, 0.2, 0.1, -0.3])
    out, reason = T.set_spacing(m, 10.0, 20.0, 0.1, 0.6)
    assert reason == ""
    np.testing.assert_array_equal(out.co, m.co)
    np.testing.assert_array_equal(out.hl[:, 1], m.hl[:, 1])
    np.testing.assert_array_equal(out.hr[:, 1], m.hr[:, 1])
    assert out.hr[1, 0] == pytest.approx(10.0 + 0.1 * 10.0)
    assert out.hl[2, 0] == pytest.approx(20.0 - 0.6 * 10.0)
    for k, side in [(0, "hl"), (0, "hr"), (1, "hl"), (2, "hr"), (3, "hl"), (3, "hr")]:
        np.testing.assert_array_equal(getattr(out, side)[k], getattr(m, side)[k])
    assert out.hl_type[1] == out.hr_type[1] == out.hl_type[2] == out.hr_type[2] == "FREE"
    assert out.hl_type[0] == out.hr_type[0] == out.hl_type[3] == out.hr_type[3] == "AUTO_CLAMPED"


def test_spacing_preserve_path_keeps_3d_path_and_changes_timing():
    models = _xyz()
    out = [T.set_spacing(m, 10.0, 20.0, 0.1, 0.6)[0] for m in models]
    before = _polyline(models, np.linspace(10.0, 20.0, 2000))
    after = _polyline(out, np.linspace(10.0, 20.0, 50))
    assert _dist_to_polyline(after, before).max() < 1e-4
    moved = np.linalg.norm(_polyline(out, [13.0]) - _polyline(models, [13.0]))
    assert moved > 1e-3


def test_spacing_preserve_smoothness_aligns_handles_and_keeps_segment_path():
    models = _xyz()
    out = [T.set_spacing(m, 10.0, 20.0, 0.15, 0.5, T.PRESERVE_SMOOTHNESS)[0] for m in models]
    for a, b in zip(models, out):
        for k in (1, 2):
            assert b.hl_type[k] == b.hr_type[k] == "ALIGNED"
            (kx, ky), (lx, ly), (rx, ry) = b.co[k], b.hl[k], b.hr[k]
            assert (ry - ky) * (kx - lx) == pytest.approx((ky - ly) * (rx - kx), abs=1e-9)
        for k, side in ((0, "hl"), (0, "hr"), (3, "hl"), (3, "hr")):
            np.testing.assert_array_equal(getattr(b, side)[k], getattr(a, side)[k])
        np.testing.assert_array_equal(b.hl[1, 0], a.hl[1, 0])      # x of the other handles stays
        np.testing.assert_array_equal(b.hr[2, 0], a.hr[2, 0])
    before = _polyline(models, np.linspace(10.0, 20.0, 2000))
    after = _polyline(out, np.linspace(10.0, 20.0, 50))
    assert _dist_to_polyline(after, before).max() < 1e-4


def test_spacing_refuses_missing_keys_non_adjacent_and_non_bezier():
    m = _chan([0.0, 1.0, 3.0, 2.0])
    for k0, k1 in ((10.0, 25.0), (5.0, 20.0), (1.0, 20.0), (20.0, 10.0)):
        out, reason = T.set_spacing(m, k0, k1, 0.3, 0.3)
        assert reason and out is m
    out, reason = T.set_spacing(_chan([0.0, 1.0, 3.0, 2.0], interp="LINEAR"), 10.0, 20.0, 0.3, 0.3)
    assert reason == "segmento LINEAR"
    out, reason = T.set_spacing(_chan([0.0, 1.0, 3.0, 2.0], interp="CONSTANT"), 10.0, 20.0, 0.3, 0.3)
    assert reason == "segmento CONSTANT"


def test_spacing_from_gesture_direction_and_clamp():
    lo, li = T.spacing_from_gesture(1 / 3, 1 / 3, 0.1, 0.0)
    assert lo > 1 / 3 and li < 1 / 3
    lo, li = T.spacing_from_gesture(1 / 3, 1 / 3, 0.0, 0.1)
    assert lo > 1 / 3 and li > 1 / 3
    for favor, ease in ((5.0, 0.0), (-5.0, 0.0), (0.0, 5.0), (0.0, -5.0), (3.0, -3.0)):
        lo, li = T.spacing_from_gesture(0.3, 0.3, favor, ease)
        assert lo >= T.MIN_LAMBDA - 1e-12 and li >= T.MIN_LAMBDA - 1e-12 and lo + li <= T.MAX_LAMBDA_SUM + 1e-12
    for favor, ease in ((0.1, 0.0), (-0.1, 0.0), (0.0, -0.5), (0.0, 0.3)):   # moderate: floor holds
        lo, li = T.spacing_from_gesture(0.3, 0.3, favor, ease)
        assert lo >= T.MIN_LAMBDA and li >= T.MIN_LAMBDA and lo + li <= T.MAX_LAMBDA_SUM + 1e-12


def test_retime_frames_from_screen_projection():
    assert T.retime_frames_from_screen((30, 40), (1, 0), 10.0) == pytest.approx(3.0)
    assert T.retime_frames_from_screen((30, 40), (3, 4), 10.0) == pytest.approx(5.0)
    assert T.retime_frames_from_screen((30, 40), (-3, -4), 10.0) == pytest.approx(-5.0)
    assert T.retime_frames_from_screen((30, 0), (0, 1), 10.0) == pytest.approx(0.0)


@pytest.mark.parametrize("direction,ppf", [((0.0, 0.0), 10.0), ((1e-9, 0.0), 10.0), ((1.0, 0.0), 0.5)])
def test_retime_frames_from_screen_fallback(direction, ppf):
    assert T.retime_frames_from_screen((40, 99), direction, ppf) == pytest.approx(2.0)
