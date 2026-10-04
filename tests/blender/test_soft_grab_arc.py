# SPDX-License-Identifier: GPL-3.0-or-later
"""Soft grab and arc drag on the generated Rigify rig (acceptance criteria 4 and 5, invariants 2 and 6)."""

import importlib

import bpy
import pytest
from mathutils import Vector


def _head(rig, bone, frame):
    bpy.context.scene.frame_set(frame)
    return (rig.matrix_world @ rig.pose.bones[bone].head).copy()


def _channelbag(rig):
    return rig.animation_data.action.layers[0].strips[0].channelbags[0]


def _key_frames(rig):
    return {(fc.data_path, fc.array_index): [k.co[0] for k in fc.keyframe_points] for fc in _channelbag(rig).fcurves}


def _gesture(rig, bone, frame, delta, **kw):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame, delta=delta, **kw)


@pytest.mark.parametrize("bone,frame", [("hand_ik.L", 6), ("hand_ik.L", 18), ("foot_ik.R", 7), ("torso", 16)])
def test_arc_drag_moves_in_between_exactly(public_rig, bone, frame):
    """Criterion 5: the in-between goes where the drag says, without new keys or timing changes."""
    delta = Vector((0.06, -0.04, 0.05))
    before = _head(public_rig, bone, frame)
    keys = _key_frames(public_rig)
    assert _gesture(public_rig, bone, frame, delta, mode='ARC') == {'FINISHED'}
    assert (_head(public_rig, bone, frame) - before - delta).length < 1e-4
    assert _key_frames(public_rig) == keys


def test_arc_drag_keeps_key_poses(public_rig):
    keyed = {f: _head(public_rig, "hand_ik.L", f) for f in (1, 12, 24)}
    _gesture(public_rig, "hand_ik.L", 6, (0.1, 0.0, 0.1), mode='ARC')
    for f, p in keyed.items():
        assert (_head(public_rig, "hand_ik.L", f) - p).length < 1e-5


def test_arc_drag_break_tangent_keeps_other_segment(public_rig):
    other = [_head(public_rig, "hand_ik.L", f) for f in (14, 18, 22)]
    _gesture(public_rig, "hand_ik.L", 6, (0.1, 0.0, 0.1), mode='ARC', break_tangent=True)
    for f, p in zip((14, 18, 22), other):
        assert (_head(public_rig, "hand_ik.L", f) - p).length < 1e-5


def test_arc_drag_refuses_linear_segment(public_rig):
    pb = public_rig.pose.bones["hand_ik.L"]
    for i in range(3):
        fc = _channelbag(public_rig).fcurves.find(pb.path_from_id("location"), index=i)
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    assert _gesture(public_rig, "hand_ik.L", 6, (0.1, 0, 0), mode='ARC') == {'CANCELLED'}


def test_soft_grab_moves_neighbors_by_falloff(public_rig, addon):
    falloff = importlib.import_module(addon.__name__ + ".core.falloff")
    delta = Vector((0.0, -0.1, 0.1))
    before = {f: _head(public_rig, "hand_ik.L", f) for f in (1, 12, 24)}
    assert _gesture(public_rig, "hand_ik.L", 12, delta, mode='GRAB', radius=15.0) == {'FINISHED'}
    assert (_head(public_rig, "hand_ik.L", 12) - before[12] - delta).length < 1e-4
    for f in (1, 24):
        w = float(falloff.weight([f - 12], 15.0, "SMOOTH")[0])
        assert 0.0 < w < 1.0
        assert (_head(public_rig, "hand_ik.L", f) - before[f] - delta * w).length < 1e-4, f


def test_radius_zero_is_plain_grab(public_rig):
    other = _head(public_rig, "hand_ik.L", 24)
    _gesture(public_rig, "hand_ik.L", 12, (0.1, 0.1, 0.1), mode='GRAB', radius=0.0)
    assert (_head(public_rig, "hand_ik.L", 24) - other).length < 1e-6
