# SPDX-License-Identifier: GPL-3.0-or-later
"""Rigify adapter (rig generated from the "Human" metarig). Map validated on Blender 5.2.1 against the
public generated rig and the maintainer's character (docs/design/rig-adapter.md)."""

from .adapter import RigAdapter, register_adapter
from .concepts import SIDES

NON_CONTROL_PREFIXES = ("ORG-", "MCH-", "DEF-", "VIS_", "WGT-")
REQUIRED = ("root", "torso")

_CENTER = {"root": "root", "torso": "torso", "hips": "hips", "chest": "chest", "neck": "neck", "head": "head"}
_LIMB = {
    "shoulder": "shoulder", "upper_arm": "upper_arm_fk", "forearm": "forearm_fk", "hand": "hand_fk",
    "hand_ik": "hand_ik", "pole_arm": "upper_arm_ik_target",
    "thigh": "thigh_fk", "shin": "shin_fk", "foot": "foot_fk", "foot_ik": "foot_ik", "pole_leg": "thigh_ik_target",
}
CONCEPT_TO_BONE = dict(_CENTER)
for _concept, _bone in _LIMB.items():
    for _side in SIDES:
        CONCEPT_TO_BONE[f"{_concept}.{_side}"] = f"{_bone}.{_side}"
BONE_TO_CONCEPT = {bone: concept for concept, bone in CONCEPT_TO_BONE.items()}

_CHAINS = {
    "hand": ("upper_arm", "forearm", "hand"),
    "foot": ("thigh", "shin", "foot"),
}
FK_CONCEPTS = ("upper_arm", "forearm", "hand", "thigh", "shin", "foot")
_SWITCH = {"arm": "upper_arm_parent", "leg": "thigh_parent"}   # holds the IK_FK property (0 = IK, 1 = FK)


@register_adapter
class RigifyAdapter(RigAdapter):
    id = "rigify"

    @classmethod
    def detect(cls, arm_ob) -> float:
        if arm_ob is None or arm_ob.type != 'ARMATURE' or "rig_id" not in arm_ob.data:
            return 0.0
        bones = arm_ob.data.bones
        if not all(name in bones for name in REQUIRED):
            return 0.3
        hits = sum(1 for bone in CONCEPT_TO_BONE.values() if bone in bones)
        return 0.5 + 0.5 * hits / len(CONCEPT_TO_BONE)

    def bone_for(self, concept):
        return CONCEPT_TO_BONE.get(concept)

    def concept_for(self, bone_name):
        return BONE_TO_CONCEPT.get(bone_name)

    def chain(self, concept):
        base, _, side = concept.partition(".")
        links = _CHAINS.get(base)
        if not links or side not in SIDES:
            return []
        return [CONCEPT_TO_BONE[f"{link}.{side}"] for link in links]

    def ik_fk_state(self, arm_ob, limb):
        kind, _, side = limb.partition(".")
        bone = _SWITCH.get(kind)
        pb = arm_ob.pose.bones.get(f"{bone}.{side}") if bone else None
        if pb is None or "IK_FK" not in pb:
            return None
        return float(pb["IK_FK"])

    def translation_allowed(self, bone_name):
        # FK chain controls rotate; Rigify leaves location unlocked on the chain roots (upper_arm_fk,
        # thigh_fk) but moving them detaches the limb — not a sculpt target (FK sculpt: Escopo 4)
        concept = self.concept_for(bone_name)
        return concept is None or concept.partition(".")[0] not in FK_CONCEPTS

    def is_control(self, bone_name):
        return not bone_name.startswith(NON_CONTROL_PREFIXES)

    def deform_bones(self, arm_ob):
        return [b.name for b in arm_ob.data.bones if b.name.startswith("DEF-")]
