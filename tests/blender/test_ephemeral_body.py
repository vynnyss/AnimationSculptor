# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 4 of the ephemeral rig (docs/design/ephemeral-rig.md): the ``Corpo`` scope (spine solved by damped
least squares, legs pinned) on a Mixamo-like skeleton (generic adapter) and on the generated Rigify rig,
and the rigidity check that refuses chains whose links are driven by constraints (Rigify's neck/head)."""

import bpy
import numpy as np
import pytest
from mathutils import Vector


def _tail(ob, bone, frame):
    bpy.context.scene.frame_set(frame)
    return np.array(ob.matrix_world @ ob.pose.bones[bone].tail)


def _tails(ob, bone, frames):
    return {f: _tail(ob, bone, f) for f in frames}


def _gesture(ob, bone, frame, delta, **kw):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=ob.name, bone=bone, frame=frame, delta=delta,
                                      mode='CHAIN', chain_scope='BODY', **kw)


def _skeleton():
    """Mixamo-like: Hips → Spine → Spine1 → Neck → Head, Spine1 → arms, Hips → legs (3 bones each)."""
    bpy.ops.wm.read_homefile(use_empty=True)
    arm = bpy.data.armatures.new("mixamo_like")
    ob = bpy.data.objects.new("mixamo_like", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones

    def bone(name, head, tail, parent=None, connect=False):
        b = eb.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = eb[parent]
            b.use_connect = connect
        return b

    bone("Hips", (0, 0, 1.0), (0, 0, 1.1))
    bone("Spine", (0, 0, 1.1), (0, 0, 1.3), "Hips", True)
    bone("Spine1", (0, 0, 1.3), (0, 0, 1.5), "Spine", True)
    bone("Neck", (0, 0, 1.5), (0, 0, 1.6), "Spine1", True)
    bone("Head", (0, 0, 1.6), (0, -0.02, 1.8), "Neck", True)
    bone("LeftArm", (0.15, 0, 1.45), (0.45, 0, 1.45), "Spine1")
    for side, x in (("Left", 0.1), ("Right", -0.1)):
        bone(f"{side}UpLeg", (x, 0, 1.0), (x, -0.12, 0.57), "Hips")                 # bent knee: the leg has slack
        bone(f"{side}Leg", (x, -0.12, 0.57), (x, 0, 0.1), f"{side}UpLeg", True)
        bone(f"{side}Foot", (x, 0, 0.1), (x, -0.12, 0.02), f"{side}Leg", True)
    bpy.ops.object.mode_set(mode='POSE')
    action = bpy.data.actions.new("mixamo_like_action")
    slot = action.slots.new(id_type='OBJECT', name=ob.name)
    adt = ob.animation_data_create()
    adt.action, adt.action_slot = action, slot
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, 30
    for frame, angle in ((1, 0.0), (30, 0.3)):
        for name in ("Hips", "Spine", "Spine1", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"):
            pb = ob.pose.bones[name]
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (angle * (0.5 if "Leg" in name else 1.0), 0.0, 0.1 * angle)
            ob.keyframe_insert(f'pose.bones["{name}"].rotation_euler', frame=frame)
    return ob


def test_generic_body_chain_and_pins(addon):
    import importlib

    ob = _skeleton()
    adapter = importlib.import_module(addon.__name__ + ".rig").get_adapter(ob)
    chain, reason = adapter.ephemeral_chain(ob, "Head", "BODY")
    assert reason == "" and chain == ["Hips", "Spine", "Spine1", "Neck", "Head"]
    pins, _ = adapter.ephemeral_pins(ob, chain)
    assert sorted(limb[0] for _b, limb in pins) == ["LeftUpLeg", "RightUpLeg"]
    assert all(len(limb) == 3 for _b, limb in pins)


def test_body_lean_keeps_the_feet_planted():
    ob = _skeleton()
    frames = range(1, 31)
    head = _tails(ob, "Head", frames)
    feet = {s: _tails(ob, f"{s}Foot", frames) for s in ("Left", "Right")}
    delta = Vector((0.0, -0.12, -0.10))       # within reach of the spine (a straight spine cannot stretch)
    assert _gesture(ob, "Head", 15, delta, radius_past=6, radius_future=6) == {'FINISHED'}
    head_after = _tails(ob, "Head", frames)
    assert np.linalg.norm(head_after[15] - head[15] - np.array(delta)) < 1e-3          # head under the drag
    for s in ("Left", "Right"):
        after = _tails(ob, f"{s}Foot", frames)
        assert max(np.linalg.norm(after[f] - feet[s][f]) for f in frames) < 1e-4, s   # feet pinned
    for f in frames:
        if not 9 <= f <= 21:
            assert np.linalg.norm(head_after[f] - head[f]) < 1e-5, f                   # nothing outside


def _fk_legs(rig, on=True):
    for side in ("L", "R"):
        rig.pose.bones[f"thigh_parent.{side}"]["IK_FK"] = 1.0 if on else 0.0
    rig.update_tag()


def test_rigify_chest_leans_the_torso_with_fk_feet_pinned(public_rig):
    rig = public_rig
    _fk_legs(rig, True)
    frames = range(1, 25)
    feet = {s: _tails(rig, f"foot_fk.{s}", frames) for s in ("L", "R")}
    chest = _tails(rig, "chest", frames)
    delta = Vector((0.0, -0.08, -0.03))
    assert _gesture(rig, "chest", 12, delta, radius_past=5, radius_future=5) == {'FINISHED'}
    chest_after = _tails(rig, "chest", frames)
    assert np.linalg.norm(chest_after[12] - chest[12] - np.array(delta)) < 1e-3
    for s in ("L", "R"):
        after = _tails(rig, f"foot_fk.{s}", frames)
        assert max(np.linalg.norm(after[f] - feet[s][f]) for f in frames) < 1e-4, s


def test_rigify_hips_with_ik_legs_is_fine(public_rig):
    rig = public_rig
    _fk_legs(rig, False)
    feet = _tails(rig, "foot_ik.L", range(1, 25))
    assert _gesture(rig, "hips", 12, (0.0, 0.05, 0.0), radius_past=4, radius_future=4) == {'FINISHED'}
    after = _tails(rig, "foot_ik.L", range(1, 25))
    assert max(np.linalg.norm(after[f] - feet[f]) for f in range(1, 25)) < 1e-5         # the rig pins IK feet


@pytest.mark.parametrize("bone", ["head", "neck"])
def test_rigify_neck_head_lean_then_aim(public_rig, bone):
    """Decision 10: Corpo on the neck/head leans torso + chest, then aims the bone at the target."""
    rig = public_rig
    _fk_legs(rig, False)
    before = _tails(rig, bone, range(1, 25))
    delta = np.array([0.0, -0.06, -0.03])
    assert _gesture(rig, bone, 12, Vector(delta), radius_past=4, radius_future=4) == {'FINISHED'}
    after = _tails(rig, bone, range(1, 25))
    err = np.linalg.norm(after[12] - before[12] - delta)
    print(f"{bone} two-stage error at f0: {err * 1000:.2f} mm")
    assert err < 2e-3
    for f in range(1, 25):
        if not 8 <= f <= 16:
            assert np.linalg.norm(after[f] - before[f]) < 1e-5, f


@pytest.mark.parametrize("bone,legs_fk", [("hips", True)])
def test_rigify_non_rigid_chains_are_refused(public_rig, bone, legs_fk):
    rig = public_rig
    _fk_legs(rig, legs_fk)
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    before = len(cb.fcurves)
    assert _gesture(rig, bone, 12, (0.0, 0.05, 0.0), radius_past=4, radius_future=4) == {'CANCELLED'}
    assert len(cb.fcurves) == before
