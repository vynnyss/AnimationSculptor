# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig adapters with fake armatures (no Blender): detection, mapping, classification."""

from types import SimpleNamespace

import pytest

from animation_sculptor import rig
from animation_sculptor.rig import rigify


class _Data(dict):
    """Armature data: ID properties via mapping, bones via attribute."""

    def __init__(self, props, bone_names, deform=()):
        super().__init__(props)
        self.name = "Armature"
        self.bones = _Bones({n: SimpleNamespace(name=n, use_deform=n in deform) for n in bone_names})


class _Bones(dict):
    """Like bpy_prop_collection: iteration yields items, ``in`` and ``get`` work by name."""

    def __iter__(self):
        return iter(self.values())


def _pose_bone(name, lock_loc=(False, False, False), lock_rot=(False, False, False), mode='QUATERNION', props=None):
    pb = SimpleNamespace(name=name, lock_location=lock_loc, lock_rotation=lock_rot, lock_rotation_w=False,
                         rotation_mode=mode)
    pb._props = props or {}
    return pb


class _PB(SimpleNamespace):
    def __contains__(self, key):
        return key in self._props

    def __getitem__(self, key):
        return self._props[key]


def _armature(bone_specs, props=None, deform=()):
    bones = _Bones()
    for spec in bone_specs:
        pb = _PB(**vars(_pose_bone(**spec)))
        bones[pb.name] = pb
    data = _Data(props or {}, list(bones.keys()), deform)
    return SimpleNamespace(name="rig", type='ARMATURE', data=data, pose=SimpleNamespace(bones=bones))


def _rigify_rig():
    specs = [{"name": b} for b in rigify.CONCEPT_TO_BONE.values()]
    specs = [s for s in specs if not s["name"].startswith(("hand_fk", "foot_fk"))]
    specs += [{"name": "hand_fk.L", "lock_loc": (True, True, True)}, {"name": "hand_fk.R", "lock_loc": (True, True, True)},
              {"name": "foot_fk.L", "lock_loc": (True, True, True)}, {"name": "foot_fk.R", "lock_loc": (True, True, True)},
              {"name": "MCH-hand_ik.parent.L"}, {"name": "ORG-hand.L"}, {"name": "DEF-hand.L"},
              {"name": "upper_arm_parent.L", "props": {"IK_FK": 1.0}},
              {"name": "thigh_parent.L", "props": {"IK_FK": 0.0}}]
    return _armature(specs, props={"rig_id": "abc123"}, deform=("DEF-hand.L",))


def setup_function():
    rig.clear_cache()


def test_rigify_detected_over_generic():
    arm = _rigify_rig()
    assert rig.get_adapter(arm).id == "rigify"
    assert rigify.RigifyAdapter.detect(arm) > 0.9


def test_generic_for_plain_armature():
    arm = _armature([{"name": "Bone"}, {"name": "Bone.001"}])
    adapter = rig.get_adapter(arm)
    assert adapter.id == "generic"
    assert [c.name for c in adapter.controls(arm)] == ["Bone", "Bone.001"]


def test_rigify_without_required_bones_has_low_confidence():
    arm = _armature([{"name": "hand_ik.L"}], props={"rig_id": "x"})
    assert rigify.RigifyAdapter.detect(arm) < 0.5


def test_concept_mapping_round_trip():
    adapter = rigify.RigifyAdapter(_rigify_rig())
    for concept in rig.concepts.CONCEPTS:
        bone = adapter.bone_for(concept)
        assert bone is not None, concept
        assert adapter.concept_for(bone) == concept
    assert adapter.bone_for("pole_arm.L") == "upper_arm_ik_target.L"
    assert adapter.bone_for("hand.R") == "hand_fk.R"


def test_non_controls_are_never_edited():
    arm = _rigify_rig()
    adapter = rig.get_adapter(arm)
    for name in ("MCH-hand_ik.parent.L", "ORG-hand.L", "DEF-hand.L"):
        assert not adapter.is_control(name)
        assert adapter.classify(arm, name) is None
    assert all(not c.name.startswith(("MCH-", "ORG-", "DEF-")) for c in adapter.controls(arm))


def test_capabilities_from_locks():
    arm = _rigify_rig()
    adapter = rig.get_adapter(arm)
    assert adapter.classify(arm, "hand_ik.L").translates
    fk = adapter.classify(arm, "hand_fk.L")
    assert not fk.translates and fk.rotates and fk.reference == "TAIL"
    assert adapter.classify(arm, "hand_ik.L").reference == "HEAD"


def test_ik_fk_state_and_chain():
    arm = _rigify_rig()
    adapter = rig.get_adapter(arm)
    assert adapter.ik_fk_state(arm, "arm.L") == pytest.approx(1.0)
    assert adapter.ik_fk_state(arm, "leg.L") == pytest.approx(0.0)
    assert adapter.ik_fk_state(arm, "arm.R") is None
    assert adapter.chain("hand.L") == ["upper_arm_fk.L", "forearm_fk.L", "hand_fk.L"]
    assert adapter.chain("root") == []


def test_deform_bones():
    arm = _rigify_rig()
    assert rig.get_adapter(arm).deform_bones(arm) == ["DEF-hand.L"]


def test_adapter_cached_per_armature():
    arm = _rigify_rig()
    assert rig.get_adapter(arm) is rig.get_adapter(arm)


def test_rigify_fk_chain_is_rotation_only_even_with_free_location():
    """Rigify leaves location unlocked on upper_arm_fk/thigh_fk; they are still rotation controls."""
    arm = _rigify_rig()
    info = rig.get_adapter(arm).classify(arm, "upper_arm_fk.L")
    assert info.rotates and not info.translates and info.free_axes == (False, False, False)


def test_connected_bone_never_translates():
    arm = _armature([{"name": "a"}, {"name": "b"}])
    arm.pose.bones["b"].bone = SimpleNamespace(use_connect=True)
    adapter = rig.get_adapter(arm)
    assert not adapter.classify(arm, "b").translates
    assert adapter.classify(arm, "a").translates
