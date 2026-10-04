# SPDX-License-Identifier: GPL-3.0-or-later
"""core.sculpt_ops.arc_drag and core.falloff (motion-sculpt-model.md, operations 1–2 and invariants)."""

import numpy as np
import pytest

from animation_sculptor.core import bezier, falloff
from animation_sculptor.core.fcurve_model import ChannelModel
from animation_sculptor.core.sculpt_ops import arc_drag


def _model(types="AUTO_CLAMPED", interp="BEZIER"):
    co = [(1.0, 0.0), (10.0, 0.6), (16.0, 1.0), (30.0, 0.2)]
    hl = [(-2.0, 0.0), (7.0, 0.45), (14.0, 1.0), (25.0, 0.2)]
    hr = [(4.0, 0.0), (12.0, 0.7), (20.6, 1.0), (35.0, 0.2)]
    return ChannelModel(co, hl, hr, [types] * 4, [types] * 4, [interp] * 4)


@pytest.mark.parametrize("frame", [3.0, 5.5, 12.3, 20.0, 27.9])
@pytest.mark.parametrize("delta", [0.3, -0.25, 1e-3])
def test_arc_drag_moves_the_value_exactly(frame, delta):
    m = _model()
    out, reason = arc_drag(m, frame, delta)
    assert reason == ""
    before = bezier.evaluate(m, [frame])[0]
    after = bezier.evaluate(out, [frame])[0]
    assert after - before == pytest.approx(delta, abs=1e-5)


def test_arc_drag_never_changes_x_or_keys():
    """Invariant 2: no x of keys/handles changes; key values stay."""
    m = _model()
    out, _ = arc_drag(m, 12.3, 0.4)
    np.testing.assert_array_equal(out.co, m.co)
    np.testing.assert_array_equal(out.hl[:, 0], m.hl[:, 0])
    np.testing.assert_array_equal(out.hr[:, 0], m.hr[:, 0])


def test_arc_drag_touches_only_its_segment_handles_and_opposites():
    m = _model()
    out, _ = arc_drag(m, 12.3, 0.4)           # segment 1: keys 1 and 2
    changed = {(i, side) for i in range(4) for side, a, b in (("L", out.hl, m.hl), ("R", out.hr, m.hr))
               if not np.array_equal(a[i], b[i])}
    assert changed <= {(1, "R"), (2, "L"), (1, "L"), (2, "R")}   # inner handles + aligned opposites
    assert {(1, "R"), (2, "L")} <= changed
    assert out.hl_type[1] == out.hr_type[1] == "ALIGNED"


def test_aligned_opposite_is_collinear():
    out, _ = arc_drag(_model(), 12.3, 0.4)
    for k in (1, 2):
        (kx, ky), (lx, ly), (rx, ry) = out.co[k], out.hl[k], out.hr[k]
        assert (ry - ky) * (kx - lx) == pytest.approx((ky - ly) * (rx - kx), abs=1e-9)


def test_break_tangent_leaves_neighbor_segments_identical():
    m = _model()
    out, _ = arc_drag(m, 12.3, 0.4, break_tangent=True)
    assert out.hl_type[1] == out.hr_type[1] == "FREE"
    frames = np.r_[np.linspace(1.0, 9.9, 30), np.linspace(16.1, 30.0, 30)]
    np.testing.assert_array_equal(bezier.evaluate(out, frames), bezier.evaluate(m, frames))


@pytest.mark.parametrize("interp", ["LINEAR", "CONSTANT"])
def test_arc_drag_refuses_non_bezier_segments(interp):
    m = _model(interp=interp)
    out, reason = arc_drag(m, 12.3, 0.4)
    assert reason == f"segmento {interp}" and out is m


def test_arc_drag_refuses_keys_and_outside():
    m = _model()
    assert arc_drag(m, 10.0, 0.1)[1]
    assert arc_drag(m, 40.0, 0.1)[1]
    assert arc_drag(m, 0.0, 0.1)[1]


def test_arc_drag_with_overlapping_handles_is_still_exact():
    m = _model(types="FREE")
    m.hr[1] = (25.0, 1.5)            # reaches past key 2: Blender scales it (correct_bezpart)
    out, reason = arc_drag(m, 12.3, 0.2, break_tangent=True)
    assert reason == ""
    assert bezier.evaluate(out, [12.3])[0] - bezier.evaluate(m, [12.3])[0] == pytest.approx(0.2, abs=1e-5)


def test_arc_drag_zero_delta_is_identity():
    m = _model()
    assert arc_drag(m, 12.3, 0.0)[0].same_as(m)


@pytest.mark.parametrize("shape", falloff.SHAPES)
def test_falloff_shapes(shape):
    d = np.array([0.0, 1.0, 2.5, 5.0, 7.0])
    w = falloff.weight(d, 5.0, shape)
    assert w[0] == 1.0 and w[3] == 0.0 and w[4] == 0.0
    assert ((w >= 0) & (w <= 1)).all()
    assert (np.diff(w) <= 1e-12).all()      # monotone non-increasing


def test_falloff_zero_radius_is_only_the_point():
    np.testing.assert_array_equal(falloff.weight([0.0, 1.0], 0.0), [1.0, 0.0])
