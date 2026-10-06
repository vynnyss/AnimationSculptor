# SPDX-License-Identifier: GPL-3.0-or-later
"""core.pose_keys: pose-to-pose writing (ADR 0015)."""

import numpy as np

from animation_sculptor.core import bezier
from animation_sculptor.core.fcurve_model import ChannelModel
from animation_sculptor.core.pose_keys import write_keys


def _model(frames, values):
    x = np.asarray(frames, dtype=np.float64)
    y = np.asarray(values, dtype=np.float64)
    co = np.stack((x, y), axis=1)
    return ChannelModel(co, co - (1.0, 0.0), co + (1.0, 0.0))


def test_existing_key_moves_rigidly_and_keeps_its_timing():
    m = _model([1, 12, 24], [0.0, 1.0, 0.0])
    m.hl[1] = (10.0, 0.8)
    m.hr[1] = (14.0, 1.2)
    out = write_keys(m, [12], [1.5])
    assert out.key_count == 3
    assert out.co[1].tolist() == [12.0, 1.5]
    assert out.hl[1].tolist() == [10.0, 1.3] and out.hr[1].tolist() == [14.0, 1.7]   # same Δy, same x
    for k in (0, 2):                                                                    # others bit-identical
        assert np.array_equal(out.co[k], m.co[k]) and np.array_equal(out.hl[k], m.hl[k])


def test_missing_key_is_inserted_in_order():
    m = _model([1, 24], [0.0, 0.0])
    out = write_keys(m, [12], [0.7])
    assert out.frames.tolist() == [1.0, 12.0, 24.0]
    assert out.values[1] == 0.7
    assert out.hl_type[1] == out.hr_type[1] == "AUTO_CLAMPED" and out.interp[1] == "BEZIER"
    assert out.hl[1, 0] < 12.0 < out.hr[1, 0]


def test_a_new_channel_is_anchored_at_the_other_poses():
    out = write_keys(_model([], []), [12], [0.5], default=0.1, anchors=[1, 12, 24])
    assert out.frames.tolist() == [1.0, 12.0, 24.0]
    assert out.values.tolist() == [0.1, 0.5, 0.1]                   # the other poses keep the old value
    assert abs(bezier.evaluate(out, np.array([1.0]))[0] - 0.1) < 1e-6      # Blender evaluates in float32


def test_several_frames_and_the_input_is_not_changed():
    m = _model([1, 6, 12], [0.0, 0.2, 0.4])
    before = m.copy()
    out = write_keys(m, [6, 12, 18], [0.3, 0.5, 0.9])
    assert out.frames.tolist() == [1.0, 6.0, 12.0, 18.0]
    assert out.values.tolist() == [0.0, 0.3, 0.5, 0.9]
    assert m.same_as(before)
