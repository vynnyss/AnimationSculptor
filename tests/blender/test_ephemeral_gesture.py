# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 3 of the ephemeral rig (docs/design/ephemeral-rig.md): the gesture on rotation-only controls,
through ``asc.sculpt_gesture`` (Rigify FK arm of the generated rig and a plain armature with the generic
adapter): the tail lands under the drag, only the window changes, refusals, cancel is bit-exact."""

import importlib

import bpy
import numpy as np
import pytest
from mathutils import Vector

ARM = ("upper_arm_fk.R", "forearm_fk.R", "hand_fk.R")


def _tail(rig, bone, frame):
    bpy.context.scene.frame_set(frame)
    return np.array(rig.matrix_world @ rig.pose.bones[bone].tail)


def _tails(rig, bone, frames):
    return {f: _tail(rig, bone, f) for f in frames}


def _dump(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    return {(fc.data_path, fc.array_index): [(tuple(k.co), tuple(k.handle_left), tuple(k.handle_right),
                                              k.handle_left_type, k.handle_right_type, k.interpolation)
                                             for k in fc.keyframe_points] for fc in cb.fcurves}


def _fk(rig, on=True):
    rig.pose.bones["upper_arm_parent.R"]["IK_FK"] = 1.0 if on else 0.0
    rig.pose.bones["forearm_fk.R"].rotation_quaternion = (0.95, 0.31, 0.0, 0.0)   # bent elbow
    rig.keyframe_insert('pose.bones["forearm_fk.R"].rotation_quaternion', frame=1)
    rig.update_tag()


def _gesture(rig, bone, frame, delta, **kw):
    bpy.context.scene.asc_sculpt.key_mode = 'DENSE'      # these check the dense keys (ADR 0011)
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame,
                                      delta=delta, **kw)


@pytest.mark.parametrize("past,future", [(6, 6), (3, 9), (0, 10)])
def test_fk_arm_tail_follows_the_drag_inside_the_window_only(public_rig, past, future):
    rig = public_rig
    _fk(rig)
    frames = list(range(1, 25))
    before = _tails(rig, "hand_fk.R", frames)
    delta = Vector((0.04, -0.05, 0.06))
    assert _gesture(rig, "hand_fk.R", 12, delta, mode='AUTO', radius_past=past, radius_future=future) == {'FINISHED'}
    after = _tails(rig, "hand_fk.R", frames)
    assert np.linalg.norm(after[12] - before[12] - np.array(delta)) < 1e-3           # under the cursor (< 1 mm)
    for f in frames:
        if not (12 - past <= f <= 12 + future):
            assert np.linalg.norm(after[f] - before[f]) < 1e-5, f                       # nothing outside the window


def test_dense_keys_only_in_the_window_and_the_poses_around_it_stay(public_rig):
    rig = public_rig
    _fk(rig)
    dump = _dump(rig)
    _gesture(rig, "hand_fk.R", 12, (0.03, 0.0, 0.05), radius_past=4, radius_future=4)
    path = 'pose.bones["hand_fk.R"].rotation_quaternion'
    after = _dump(rig)
    frames = sorted({round(k[0][0]) for k in after[(path, 0)]})
    assert frames == list(range(7, 18))                     # window 8..16 + one frame of weight 0 each side
    up = 'pose.bones["upper_arm_fk.R"].rotation_quaternion'
    for axis in range(4):
        keys = after[(up, axis)]
        assert keys[0][0] == dump[(up, axis)][0][0] and keys[-1][0] == dump[(up, axis)][-1][0]   # keys 1 and 24
    untouched = {k: v for k, v in dump.items() if not any(b in k[0] for b in ARM)}
    assert all(after[k] == v for k, v in untouched.items())


def test_limb_in_ik_is_refused(public_rig):
    rig = public_rig
    _fk(rig, on=False)
    dump = _dump(rig)
    assert _gesture(rig, "hand_fk.R", 12, (0.05, 0, 0)) == {'CANCELLED'}
    assert _dump(rig) == dump


def test_axis_angle_is_refused(public_rig):
    rig = public_rig
    _fk(rig)
    rig.pose.bones["forearm_fk.R"].rotation_mode = 'AXIS_ANGLE'
    assert _gesture(rig, "hand_fk.R", 12, (0.05, 0, 0)) == {'CANCELLED'}


def test_tip_scope_turns_only_the_dragged_bone(public_rig):
    rig = public_rig
    _fk(rig)
    dump = _dump(rig)
    assert _gesture(rig, "forearm_fk.R", 12, (0.0, -0.06, 0.04), chain_scope='TIP', radius_past=5,
                    radius_future=5) == {'FINISHED'}
    after = _dump(rig)
    up = 'pose.bones["upper_arm_fk.R"].rotation_quaternion'
    assert all(after[(up, a)] == dump[(up, a)] for a in range(4))


def test_chain_edit_restore_is_bit_exact(public_rig, addon):
    """Esc/RMB path: ChainEdit.restore() puts every curve back bit for bit (created curves removed)."""
    ephemeral_edit = importlib.import_module(addon.__name__ + ".interaction.ephemeral_edit")
    rig = public_rig
    _fk(rig)
    dump = _dump(rig)
    edit = ephemeral_edit.ChainEdit(rig, list(ARM), 12, 5, 7)
    edit.apply((0.05, -0.02, 0.03))
    assert _dump(rig) != dump
    edit.set_radii(2, 3)
    edit.apply((0.01, 0.0, 0.02))
    edit.restore()
    assert _dump(rig) == dump


def test_adapter_chains(public_rig):
    from importlib import import_module

    rig = public_rig
    _fk(rig)
    adapter = import_module(__import__("conftest").ADDON_MODULE + ".rig").get_adapter(rig)
    assert adapter.ephemeral_chain(rig, "hand_fk.R", "LIMB") == (list(ARM), "")
    assert adapter.ephemeral_chain(rig, "forearm_fk.R", "LIMB") == (list(ARM[:2]), "")
    assert adapter.ephemeral_chain(rig, "hand_fk.R", "TIP") == (["hand_fk.R"], "")
    bones, reason = adapter.ephemeral_chain(rig, "hand_fk.L", "LIMB")      # left arm still in IK
    assert bones == [] and "IK" in reason


def _plain_armature():
    """Armature without Rigify: root → (spine, a → b → c) with c's chain keyed at 1 and 20."""
    bpy.ops.wm.read_homefile(use_empty=True)
    arm = bpy.data.armatures.new("plain")
    ob = bpy.data.objects.new("plain", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones
    root = eb.new("root"); root.head, root.tail = (0, 0, 0), (0, 0, 0.5)
    spine = eb.new("spine"); spine.head, spine.tail = (0, 0, 0.5), (0, 0, 1.0); spine.parent = root
    a = eb.new("a"); a.head, a.tail = (0, 0, 0.5), (0.4, 0, 0.6); a.parent = root
    b = eb.new("b"); b.head, b.tail = (0.4, 0, 0.6), (0.75, 0, 0.45); b.parent = a; b.use_connect = True
    c = eb.new("c"); c.head, c.tail = (0.75, 0, 0.45), (0.85, 0, 0.4); c.parent = b; c.use_connect = True
    bpy.ops.object.mode_set(mode='POSE')
    action = bpy.data.actions.new("plain_action")
    slot = action.slots.new(id_type='OBJECT', name=ob.name)
    adt = ob.animation_data_create()
    adt.action, adt.action_slot = action, slot
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 20
    for frame, angle in ((1, 0.0), (20, 0.6)):
        scene.frame_set(frame)
        for name in ("a", "b"):
            pb = ob.pose.bones[name]
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (0.0, angle, 0.0)
            ob.keyframe_insert(f'pose.bones["{name}"].rotation_euler', frame=frame)
    return ob


def test_generic_adapter_skeleton_without_control_rig(addon):
    ob = _plain_armature()
    adapter = importlib.import_module(addon.__name__ + ".rig").get_adapter(ob)
    assert adapter.id == "generic"
    assert adapter.ephemeral_chain(ob, "c", "LIMB") == (["a", "b", "c"], "")   # root branches: the limb stops
    before = _tails(ob, "c", range(1, 21))
    delta = Vector((0.0, 0.05, 0.08))
    assert _gesture(ob, "c", 10, delta, radius_past=4, radius_future=4) == {'FINISHED'}
    after = _tails(ob, "c", range(1, 21))
    assert np.linalg.norm(after[10] - before[10] - np.array(delta)) < 1e-3
    for f in range(1, 21):
        if not 6 <= f <= 14:
            assert np.linalg.norm(after[f] - before[f]) < 1e-5, f


def test_fk_arm_skin_follows_the_drag_inside_the_window_only(public_rig):
    """The FK arm turns: the tail ring of the hand skin moves by the drag (the ring centroid is the bone
    tail; measured ~0, tolerance 1 mm like the rig test), the upper arm skin moved too, and the skin outside the window is unchanged."""
    import deform_check as dc

    rig = public_rig
    _fk(rig)
    mesh = dc.deformed_mesh(rig)
    hand = dc.part(mesh, "DEF-hand.R")
    _head_ring, tail_ring = dc.tube_ends(hand)
    upper = dc.part(mesh, "DEF-upper_arm.R")
    frames = list(range(1, 25))
    before = dc.frames_snapshot(mesh, frames)
    delta = Vector((0.04, -0.05, 0.06))
    assert _gesture(rig, "hand_fk.R", 12, delta, mode='AUTO', radius_past=4, radius_future=4) == {'FINISHED'}
    after = dc.frames_snapshot(mesh, frames)
    moved = dc.centroid_shift(before[12], after[12], tail_ring)
    print(f"hand tail ring err {np.linalg.norm(moved - np.array(delta)) * 1000:.2f} mm")
    assert abs(moved - np.array(delta)).max() < 1e-3
    assert np.linalg.norm(dc.centroid_shift(before[12], after[12], upper)) > 1e-3        # the limb turned
    outside = [f for f in frames if not 8 <= f <= 16]
    assert dc.max_change(before, after, outside) < 1e-5
