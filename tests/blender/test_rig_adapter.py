# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig adapters on real armatures: generated Rigify rig (CI), the maintainer's character (local), plain armature."""

import importlib

import bpy
import pytest


@pytest.fixture
def rig_pkg(addon):
    pkg = importlib.import_module(addon.__name__ + ".rig")
    pkg.clear_cache()
    return pkg


def _check_rigify(arm, rig_pkg):
    adapter = rig_pkg.get_adapter(arm)
    assert adapter.id == "rigify"
    concepts = importlib.import_module(rig_pkg.__name__ + ".concepts")
    for concept in concepts.CONCEPTS:
        bone = adapter.bone_for(concept)
        assert bone in arm.pose.bones, (concept, bone)
    controls = {c.name: c for c in adapter.controls(arm)}
    assert all(not name.startswith(("MCH-", "ORG-", "DEF-")) for name in controls)
    for name in ("hand_ik.L", "hand_ik.R", "foot_ik.L", "foot_ik.R", "torso", "root",
                 "upper_arm_ik_target.L", "thigh_ik_target.R"):
        assert controls[name].translates, name
        assert controls[name].reference == "HEAD"
    for name in ("upper_arm_fk.L", "forearm_fk.L", "hand_fk.L", "thigh_fk.R"):
        assert controls[name].rotates and not controls[name].translates, name
        assert controls[name].reference == "TAIL"
    for limb in ("arm.L", "arm.R", "leg.L", "leg.R"):
        state = adapter.ik_fk_state(arm, limb)
        assert state is not None and 0.0 <= state <= 1.0
    deform = adapter.deform_bones(arm)
    assert deform and all(name.startswith("DEF-") for name in deform)
    assert adapter.chain("hand.L") == ["upper_arm_fk.L", "forearm_fk.L", "hand_fk.L"]
    return adapter


def test_rigify_adapter_on_generated_rig(public_rig, rig_pkg):
    _check_rigify(public_rig, rig_pkg)


def test_rigify_adapter_on_character(attack_rig, rig_pkg):
    adapter = _check_rigify(attack_rig, rig_pkg)
    bpy.context.scene.frame_set(1)
    assert adapter.ik_fk_state(attack_rig, "arm.L") == pytest.approx(1.0)   # left arm FK in the asset
    assert adapter.ik_fk_state(attack_rig, "arm.R") == pytest.approx(0.0)


def test_generic_adapter_on_plain_armature(rig_pkg):
    arm_data = bpy.data.armatures.new("asc_plain")
    arm = bpy.data.objects.new("asc_plain", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    for i, name in enumerate(("a", "b")):
        eb = arm_data.edit_bones.new(name)
        eb.head, eb.tail = (0, 0, i), (0, 0, i + 1)
    bpy.ops.object.mode_set(mode='POSE')
    arm.pose.bones["b"].lock_location = (True, True, True)
    try:
        adapter = rig_pkg.get_adapter(arm)
        assert adapter.id == "generic"
        controls = {c.name: c for c in adapter.controls(arm)}
        assert controls["a"].translates and not controls["b"].translates
    finally:
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.data.objects.remove(arm)


def test_gesture_refuses_fk_and_mechanism_bones(public_rig):
    for bone in ("upper_arm_fk.R", "MCH-hand_ik.parent.L"):
        assert bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=public_rig.name, bone=bone, frame=12,
                                          delta=(0.1, 0, 0)) == {'CANCELLED'}
