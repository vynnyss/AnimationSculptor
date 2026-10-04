# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for ChannelModel (pure numpy, no Blender)."""

import numpy as np
import pytest

from animation_sculptor.core.fcurve_model import ChannelModel


def make(frames=(0.0, 5.0, 10.0), values=(0.0, 2.0, 1.0)):
    co = np.array(list(zip(frames, values)), dtype=np.float64)
    hl = co - np.array([1.0, 0.0])
    hr = co + np.array([1.0, 0.0])
    return ChannelModel(co, hl, hr)


def empty():
    return ChannelModel(np.zeros((0, 2)), np.zeros((0, 2)), np.zeros((0, 2)))


def test_defaults_per_key():
    m = make()
    assert m.key_count == 3
    assert m.hl_type == ["AUTO_CLAMPED"] * 3
    assert m.hr_type == ["AUTO_CLAMPED"] * 3
    assert m.interp == ["BEZIER"] * 3
    assert m.extrapolation == "CONSTANT"
    assert m.data_path == "" and m.index == 0


def test_mismatched_lengths_raise():
    co = np.zeros((3, 2))
    with pytest.raises(ValueError):
        ChannelModel(co, np.zeros((2, 2)), np.zeros((3, 2)))
    with pytest.raises(ValueError):
        ChannelModel(co, co, co, interp=["BEZIER"] * 2)
    with pytest.raises(ValueError):
        ChannelModel(co, co, co, hl_type=["FREE"])


def test_frames_and_values_properties():
    m = make()
    np.testing.assert_array_equal(m.frames, [0.0, 5.0, 10.0])
    np.testing.assert_array_equal(m.values, [0.0, 2.0, 1.0])


def test_copy_is_independent():
    m = make()
    c = m.copy()
    assert c.same_as(m)
    c.co[0, 1] = 9.0
    c.hl[1, 0] = -3.0
    c.hr[2, 1] = 7.0
    c.hl_type[0] = "FREE"
    c.hr_type[0] = "FREE"
    c.interp[0] = "LINEAR"
    assert m.co[0, 1] == 0.0
    assert m.hl[1, 0] == 4.0
    assert m.hr[2, 1] == 1.0
    assert m.hl_type[0] == m.hr_type[0] == "AUTO_CLAMPED"
    assert m.interp[0] == "BEZIER"


def test_same_as_bit_for_bit():
    m = make()
    assert m.same_as(m.copy())
    c = m.copy()
    c.co[1, 1] += 1e-12
    assert not m.same_as(c)
    c = m.copy()
    c.hr_type[2] = "FREE"
    assert not m.same_as(c)
    c = m.copy()
    c.hl_type[0] = "VECTOR"
    assert not m.same_as(c)
    c = m.copy()
    c.interp[1] = "CONSTANT"
    assert not m.same_as(c)
    c = m.copy()
    c.extrapolation = "LINEAR"
    assert not m.same_as(c)


def test_key_index_with_eps():
    m = make()
    assert m.key_index(5.0) == 1
    assert m.key_index(5.0005) == 1
    assert m.key_index(5.01) is None
    assert m.key_index(5.01, eps=0.1) == 1
    assert m.key_index(-3.0) is None


def test_key_index_empty():
    m = empty()
    assert m.key_count == 0
    assert m.key_index(0.0) is None


def test_segment_of():
    m = make()
    assert m.segment_of(2.5) == 0
    assert m.segment_of(7.0) == 1
    assert m.segment_of(5.0) == 1      # on an inner key: the segment that starts there
    assert m.segment_of(0.0) == 0
    assert m.segment_of(10.0) == 1     # last key maps to the last segment
    assert m.segment_of(-0.1) is None
    assert m.segment_of(10.1) is None


def test_segment_of_needs_two_keys():
    one = make(frames=(3.0,), values=(1.0,))
    assert one.segment_of(3.0) is None
    assert empty().segment_of(0.0) is None
