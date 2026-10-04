# SPDX-License-Identifier: GPL-3.0-or-later
"""Retime and spacing on the generated Rigify rig (acceptance criterion 6, invariants 3 and 4)."""

import bpy
import numpy as np
import pytest
from mathutils import Vector

CONTROLS = ("hand_ik.L", "foot_ik.R", "torso")


def _channelbag(rig):
    return rig.animation_data.action.layers[0].strips[0].channelbags[0]


def _key_frames(rig):
    return {(fc.data_path, fc.array_index): [round(k.co[0], 4) for k in fc.keyframe_points]
            for fc in _channelbag(rig).fcurves}


def _heads(rig, frame, subframe=0.0):
    bpy.context.scene.frame_set(int(frame), subframe=subframe)
    return {b: (rig.matrix_world @ rig.pose.bones[b].head).copy() for b in CONTROLS}


def _op(rig, bone, frame, **kw):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame, **kw)


def test_retime_moves_the_whole_pose(public_rig):
    """Criterion 6: the pose of the whole character moves in time, not just the dragged control."""
    pose12 = _heads(public_rig, 12)
    keys = _key_frames(public_rig)
    assert _op(public_rig, "hand_ik.L", 12, mode='RETIME', new_frame=15) == {'FINISHED'}
    pose15 = _heads(public_rig, 15)
    for bone in CONTROLS:
        assert (pose15[bone] - pose12[bone]).length < 1e-5, bone
    after = _key_frames(public_rig)
    assert after.keys() == keys.keys()
    for channel, frames in keys.items():
        assert len(after[channel]) == len(frames)                        # no key created/removed
        assert after[channel] == sorted(after[channel])                  # order kept (invariant 4)
        assert after[channel] == [15.0 if f == 12.0 else f for f in frames]


def test_retime_is_clamped_between_neighbour_poses(public_rig):
    _op(public_rig, "hand_ik.L", 12, mode='RETIME', new_frame=40)
    frames = _key_frames(public_rig)[('pose.bones["hand_ik.L"].location', 0)]
    assert frames == [1.0, 23.0, 24.0]


def test_retime_works_from_an_fk_control(public_rig):
    """Timing is only time: FK controls can retime the pose too."""
    assert _op(public_rig, "upper_arm_fk.R", 12, mode='RETIME', new_frame=10) == {'FINISHED'}
    assert _key_frames(public_rig)[('pose.bones["torso"].location', 0)] == [1.0, 10.0, 24.0]


def test_retime_selected_scope_moves_only_selected(public_rig):
    for pb in public_rig.pose.bones:
        pb.select = pb.name == "hand_ik.L"
    _op(public_rig, "hand_ik.L", 12, mode='RETIME', new_frame=14, scope='SELECTED')
    frames = _key_frames(public_rig)
    assert frames[('pose.bones["hand_ik.L"].location', 0)] == [1.0, 14.0, 24.0]
    assert frames[('pose.bones["torso"].location', 0)] == [1.0, 12.0, 24.0]


@pytest.mark.parametrize("favor,ease", [(0.3, 0.0), (-0.25, 0.1), (0.0, 0.3)])
def test_spacing_keeps_the_world_path(public_rig, favor, ease):
    """Criterion 6 / invariant 3: points redistribute along the same path (sub-frame dense sampling)."""
    dense = [_heads(public_rig, f, sub)["hand_ik.L"] for f in range(12, 24) for sub in np.linspace(0, 1, 40, endpoint=False)]
    poly = np.array([tuple(p) for p in dense])
    before15 = _heads(public_rig, 15)["hand_ik.L"]
    keys = _key_frames(public_rig)
    assert _op(public_rig, "hand_ik.L", 18, mode='SPACING', favor=favor, ease=ease) == {'FINISHED'}
    assert _key_frames(public_rig) == keys
    for f in range(12, 25):
        p = np.array(tuple(_heads(public_rig, f)["hand_ik.L"]))
        seg_a, seg_b = poly[:-1], poly[1:]
        d = seg_b - seg_a
        t = np.clip(np.einsum("ij,ij->i", p - seg_a, d) / np.maximum(np.einsum("ij,ij->i", d, d), 1e-18), 0, 1)
        dist = np.linalg.norm(seg_a + d * t[:, None] - p, axis=1).min()
        assert dist < 2e-4, (f, dist)
    assert (_heads(public_rig, 15)["hand_ik.L"] - before15).length > 1e-3    # timing really changed (off-centre frame)


def test_spacing_refuses_linear_segment(public_rig):
    for fc in _channelbag(public_rig).fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    assert _op(public_rig, "hand_ik.L", 18, mode='SPACING', favor=0.2) == {'CANCELLED'}


def test_fk_trail_follows_the_bone_tail(public_rig, addon):
    """ASC-PATCH P9: FK controls are traced at the TAIL (the hand of an FK arm), translation ones at the HEAD."""
    import importlib

    provider = importlib.import_module(addon.__name__ + ".trails.provider")
    scene = bpy.context.scene
    s = scene.asc_trails
    s.pinned.clear()
    for bone in ("upper_arm_fk.R", "hand_ik.L"):
        item = s.pinned.add()
        item.obj, item.bone = public_rig, bone
    s.target_mode, s.path_engine, s.enabled = 'PINNED', 'STEP', True
    provider.update_now()
    fk = provider.get_trail(public_rig, "upper_arm_fk.R")
    ik = provider.get_trail(public_rig, "hand_ik.L")
    scene.frame_set(12)
    assert (Vector(fk.point_at(12)) - public_rig.matrix_world @ public_rig.pose.bones["upper_arm_fk.R"].tail).length < 1e-5
    assert (Vector(ik.point_at(12)) - public_rig.matrix_world @ public_rig.pose.bones["hand_ik.L"].head).length < 1e-5
