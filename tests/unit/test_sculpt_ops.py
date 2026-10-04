# SPDX-License-Identifier: GPL-3.0-or-later
"""core.sculpt_ops: invariants of docs/design/motion-sculpt-model.md."""

import numpy as np

from animation_sculptor.core import bezier
from animation_sculptor.core.fcurve_model import ChannelModel
from animation_sculptor.core.sculpt_ops import grab_key


def _model():
    co = [(1.0, 0.0), (12.0, 0.4), (24.0, 0.1)]
    hl = [(-3.0, 0.0), (8.0, 0.35), (20.0, 0.12)]
    hr = [(5.0, 0.0), (16.0, 0.45), (28.0, 0.08)]
    return ChannelModel(co, hl, hr, ["FREE"] * 3, ["ALIGNED"] * 3)


def test_zero_delta_is_identity():
    """Invariant 1: grab with zero delta changes nothing."""
    m = _model()
    assert grab_key(m, 1, 0.0).same_as(m)


def test_grab_moves_key_and_handles_rigidly():
    m = _model()
    g = grab_key(m, 1, 0.25)
    assert g.co[1, 1] == m.co[1, 1] + 0.25
    assert g.hl[1, 1] == m.hl[1, 1] + 0.25 and g.hr[1, 1] == m.hr[1, 1] + 0.25
    assert bezier.evaluate(g, [12.0])[0] == np.float32(m.co[1, 1] + 0.25)


def test_grab_keeps_timing_types_and_other_keys():
    m = _model()
    g = grab_key(m, 1, -0.3)
    np.testing.assert_array_equal(g.co[:, 0], m.co[:, 0])
    np.testing.assert_array_equal(g.hl[:, 0], m.hl[:, 0])
    np.testing.assert_array_equal(g.hr[:, 0], m.hr[:, 0])
    for i in (0, 2):
        np.testing.assert_array_equal(g.co[i], m.co[i])
        np.testing.assert_array_equal(g.hl[i], m.hl[i])
        np.testing.assert_array_equal(g.hr[i], m.hr[i])
    assert (g.hl_type, g.hr_type, g.interp) == (m.hl_type, m.hr_type, m.interp)


def test_grab_does_not_mutate_input():
    m = _model()
    before = m.copy()
    grab_key(m, 0, 1.0)
    assert m.same_as(before)
