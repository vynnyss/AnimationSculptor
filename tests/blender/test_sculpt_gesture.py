# SPDX-License-Identifier: GPL-3.0-or-later
"""Gesture operator, parametric form (``execute``): same edit as a mouse drag, testable in background."""

import importlib

import bpy
import pytest
from mathutils import Vector


def _head(rig, bone, frame):
    bpy.context.scene.frame_set(frame)
    return (rig.matrix_world @ rig.pose.bones[bone].head).copy()


def _channelbag(rig):
    return rig.animation_data.action.layers[0].strips[0].channelbags[0]


def _keys(rig):
    return {(fc.data_path, fc.array_index): [tuple(kp.co) for kp in fc.keyframe_points] for fc in _channelbag(rig).fcurves}


def _grab(rig, bone, frame, delta):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame, delta=delta)


def test_registered():
    assert hasattr(bpy.ops.asc, "sculpt_gesture")
    assert "ASC_GGT_trails" in {c.bl_idname for c in bpy.types.GizmoGroup.__subclasses__()}
    assert "ASC_GT_trail_points" in {c.bl_idname for c in bpy.types.Gizmo.__subclasses__()}


@pytest.mark.parametrize("bone,frame", [("hand_ik.L", 12), ("foot_ik.R", 24), ("torso", 12)])
def test_grab_moves_control_by_world_delta(public_rig, bone, frame):
    """Acceptance criterion 4: the control lands where the drag says (error < 1 mm)."""
    delta = Vector((0.12, -0.05, 0.08))
    before = _head(public_rig, bone, frame)
    keys_before = _keys(public_rig)
    assert _grab(public_rig, bone, frame, delta) == {'FINISHED'}
    after = _head(public_rig, bone, frame)
    assert (after - before - delta).length < 1e-4
    keys_after = _keys(public_rig)
    assert keys_after.keys() == keys_before.keys()
    for channel, keys in keys_before.items():
        assert [k[0] for k in keys_after[channel]] == [k[0] for k in keys]  # no new keys, timing intact


def test_grab_only_touches_the_key_at_the_frame(public_rig):
    other = _head(public_rig, "hand_ik.L", 24)
    _grab(public_rig, "hand_ik.L", 12, (0.1, 0.1, 0.1))
    assert (_head(public_rig, "hand_ik.L", 24) - other).length < 1e-6


def test_zero_delta_is_identity(public_rig):
    """Invariant 1: grab with zero delta changes nothing."""
    keys = _keys(public_rig)
    _grab(public_rig, "hand_ik.L", 12, (0.0, 0.0, 0.0))
    assert _keys(public_rig) == keys


def test_locked_axis_stays(public_rig):
    pb = public_rig.pose.bones["hand_ik.L"]
    pb.lock_location[2] = True
    fc_z = _channelbag(public_rig).fcurves.find(pb.path_from_id("location"), index=2)
    local_z = fc_z.evaluate(12)
    _grab(public_rig, "hand_ik.L", 12, (0.05, 0.05, 0.2))
    assert fc_z.evaluate(12) == pytest.approx(local_z)


def test_refuses_driver(public_rig):
    public_rig.pose.bones["hand_ik.L"].driver_add("location", 0)
    keys = _keys(public_rig)
    assert _grab(public_rig, "hand_ik.L", 12, (0.1, 0, 0)) == {'CANCELLED'}
    assert _keys(public_rig) == keys


def test_refuses_active_nla(public_rig):
    adt = public_rig.animation_data
    track = adt.nla_tracks.new()
    track.strips.new("strip", 1, adt.action)
    assert _grab(public_rig, "hand_ik.L", 12, (0.1, 0, 0)) == {'CANCELLED'}


def test_grab_mode_refuses_frame_without_key(public_rig):
    assert bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=public_rig.name, bone="hand_ik.L", frame=6,
                                      delta=(0.1, 0, 0), mode='GRAB') == {'CANCELLED'}


def test_trails_resumed_after_gesture(public_rig, addon):
    provider = importlib.import_module(addon.__name__ + ".trails.provider")
    _grab(public_rig, "hand_ik.L", 12, (0.1, 0, 0))
    assert not provider.is_suspended()


@pytest.mark.parametrize("bone", ["hand_ik.L", "foot_ik.R", "torso", "upper_arm_fk.R"])
@pytest.mark.parametrize("frame", [1, 7, 12])
def test_location_space_maps_location_to_head(public_rig, addon, bone, frame):
    """anim.spaces.location_space: head_world = P @ location, including Rigify IK controls
    (use_local_location off), where M_arm @ M_pose @ inverse(M_basis) is wrong."""
    spaces = importlib.import_module(addon.__name__ + ".anim.spaces")
    bpy.context.scene.frame_set(frame)
    pb = public_rig.pose.bones[bone]
    p = spaces.location_space(public_rig, pb)
    head = public_rig.matrix_world @ pb.head
    assert (p @ pb.location - head).length < 1e-5


def _drop_location_key(rig, bone, frame, axis):
    fc = _channelbag(rig).fcurves.find(rig.pose.bones[bone].path_from_id("location"), index=axis)
    kp = next(k for k in fc.keyframe_points if abs(k.co[0] - frame) < 1e-3)
    fc.keyframe_points.remove(kp)
    fc.update()
    return fc


def test_grab_inserts_missing_location_key(public_rig):
    """Edits are always stored as keyframes: an axis without a key at the key point gets one."""
    fc = _drop_location_key(public_rig, "hand_ik.L", 12, 0)
    assert all(abs(k.co[0] - 12) > 1e-3 for k in fc.keyframe_points)
    before = _head(public_rig, "hand_ik.L", 12)
    delta = Vector((0.1, 0.0, 0.05))
    assert _grab(public_rig, "hand_ik.L", 12, delta) == {'FINISHED'}
    assert any(abs(k.co[0] - 12) < 1e-3 for k in fc.keyframe_points)
    assert (_head(public_rig, "hand_ik.L", 12) - before - delta).length < 1e-4


def test_grab_creates_missing_location_fcurve(public_rig):
    cb = _channelbag(public_rig)
    pb = public_rig.pose.bones["hand_ik.L"]
    cb.fcurves.remove(cb.fcurves.find(pb.path_from_id("location"), index=1))
    before = _head(public_rig, "hand_ik.L", 12)
    delta = Vector((0.0, -0.1, 0.0))
    assert _grab(public_rig, "hand_ik.L", 12, delta) == {'FINISHED'}
    fc = cb.fcurves.find(pb.path_from_id("location"), index=1)
    assert fc is not None and [k.co[0] for k in fc.keyframe_points] == [12.0]
    assert (_head(public_rig, "hand_ik.L", 12) - before - delta).length < 1e-4


def test_cancel_removes_inserted_keys_bit_for_bit(public_rig, addon):
    """Invariant 5 with auto-keying: snapshot -> insert + edit -> restore == original."""
    sculpt_tool = importlib.import_module(addon.__name__ + ".interaction.sculpt_tool")
    _drop_location_key(public_rig, "hand_ik.L", 12, 2)
    cb = _channelbag(public_rig)
    pb = public_rig.pose.bones["hand_ik.L"]
    cb.fcurves.remove(cb.fcurves.find(pb.path_from_id("location"), index=1))
    keys = _keys(public_rig)
    bpy.context.scene.frame_set(12)
    edit = sculpt_tool._GrabEdit(public_rig, pb, 12)
    edit.apply((0.2, -0.1, 0.3))
    assert _keys(public_rig) != keys
    edit.restore()
    assert _keys(public_rig) == keys


def test_preview_matches_evaluated_rig(public_rig, addon):
    """Invariant 6: the live trail preview equals the rig evaluated after the edit."""
    sculpt_tool = importlib.import_module(addon.__name__ + ".interaction.sculpt_tool")
    pb = public_rig.pose.bones["hand_ik.L"]
    edit = sculpt_tool._GrabEdit(public_rig, pb, 12)
    frames = list(range(1, 25))
    edit.prefetch(frames)
    edit.apply((0.15, -0.05, 0.1))
    preview = edit.preview()
    for f, p in zip(frames, preview):
        assert (Vector(p) - _head(public_rig, "hand_ik.L", f)).length < 1e-4, f


def test_grab_moves_the_hand_skin_by_the_drag(public_rig):
    """The skin follows the rig: the hand is rigid under an IK control, so every vertex of its part moves
    by the drag (measured 5e-6 m; tolerance 1e-4, the grab criterion); the neighbouring key poses stay put on the skin."""
    import deform_check as dc

    mesh = dc.deformed_mesh(public_rig)
    idx = dc.part(mesh, "DEF-hand.L")
    assert len(idx) > 0
    frames = list(range(1, 25))
    before = dc.frames_snapshot(mesh, frames)
    delta = Vector((0.12, -0.05, 0.08))
    assert _grab(public_rig, "hand_ik.L", 12, delta) == {'FINISHED'}
    after = dc.frames_snapshot(mesh, frames)
    shift = after[12][idx] - before[12][idx]
    print(f"hand skin: mean err {abs(shift.mean(axis=0) - delta).max():.2e}, max err {abs(shift - delta).max():.2e}")
    assert abs(shift.mean(axis=0) - delta).max() < 1e-4
    assert abs(shift - delta).max() < 1e-4                                       # rigid: every vertex
    assert dc.max_change(before, after, [1, 24]) < 1e-5                          # neighbouring key poses
    rest = [i for i in range(len(before[12])) if i not in set(idx.tolist())]
    assert dc.max_change(before, after, [12], rest) > 1e-3                       # the arm followed too


def test_soft_grab_skin_only_changes_inside_the_window(public_rig):
    import deform_check as dc

    mesh = dc.deformed_mesh(public_rig)
    before = dc.frames_snapshot(mesh, [1, 12, 24])
    assert bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=public_rig.name, bone="hand_ik.L", frame=12,
                                      delta=(0.0, -0.1, 0.1), radius_past=0.0, radius_future=6.0) == {'FINISHED'}
    after = dc.frames_snapshot(mesh, [1, 12, 24])
    assert dc.max_change(before, after, [1]) < 1e-5                              # past radius 0
    assert dc.max_change(before, after, [24]) < 1e-5                             # key 24 is 12 frames away (> 6)
    assert dc.max_change(before, after, [12]) > 1e-2
