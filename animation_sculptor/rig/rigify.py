# SPDX-License-Identifier: GPL-3.0-or-later
"""Rigify adapter (rig generated from the "Human" metarig). Map validated on Blender 5.2.1 against the
public generated rig and the maintainer's character (docs/design/rig-adapter.md)."""

from .adapter import BODY, CHAIN, IK, LIMB, RigAdapter, register_adapter
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
# Corpo (ADR 0011, phase 4): torso turns the whole upper body; neck/head hang from the spine through
# Follow constraints (not rigid — the gesture's rigidity check refuses them, see docs)
_BODY = ("torso", "chest", "neck", "head")
_BODY_OVERRIDE = ("hips", "chest", "neck", "head")

# deform bone (without "DEF-" and a trailing ".00N" segment) -> what moves it, for grabbing the body (ADR 0013)
_SPINE = {"spine": "hips", "spine.001": "hips", "spine.002": "chest", "spine.003": "chest",
          "spine.004": "neck", "spine.005": "neck", "spine.006": "head"}
_LIMB_PARTS = {"upper_arm": "arm", "forearm": "arm", "hand": "arm", "thigh": "leg", "shin": "leg", "foot": "leg",
               "toe": "leg"}
# limb in IK: the IK control that moves the part (upper arm / thigh: the pole, i.e. where the elbow/knee points)
_IK_CONTROL = {"upper_arm": "upper_arm_ik_target", "forearm": "hand_ik", "hand": "hand_ik",
               "thigh": "thigh_ik_target", "shin": "foot_ik", "foot": "foot_ik", "toe": "toe_ik"}
_TO_CENTER = {"pelvis": "hips", "breast": "chest"}
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

    def ephemeral_chain(self, arm_ob, bone_name, scope=LIMB):
        """FK limbs come from the concept map (``hand_fk`` hangs from a helper, not from ``forearm_fk``, so
        the hierarchy walk of the base class would stop there); a limb in IK mode is refused."""
        concept = self.concept_for(bone_name)
        base, _, side = (concept or "").partition(".")
        if scope == BODY and base in _BODY_OVERRIDE:
            info = self.classify(arm_ob, bone_name)
            if info is None or not info.rotates:
                return [], "controle travado (sem rotação livre)"
            if base == "hips":
                return [CONCEPT_TO_BONE["torso"], bone_name], ""
            if base in ("neck", "head"):     # not rigid under the chest (Neck/Head Follow): lean, then aim
                return [CONCEPT_TO_BONE["torso"], CONCEPT_TO_BONE["chest"]], ""
            return [CONCEPT_TO_BONE[c] for c in _BODY[:_BODY.index(base) + 1]], ""
        if scope == BODY:
            scope = LIMB          # limbs: the body scope turns the limb
        if base not in FK_CONCEPTS:
            return super().ephemeral_chain(arm_ob, bone_name, "TIP")
        info = self.classify(arm_ob, bone_name)
        if info is None or not info.rotates:
            return [], "controle travado (sem rotação livre)"
        limb = "arm" if base in ("upper_arm", "forearm", "hand") else "leg"
        state = self.ik_fk_state(arm_ob, f"{limb}.{side}")
        if state is not None and state < 0.5:
            ik = "a mão IK" if limb == "arm" else "o pé IK"
            return [], f"membro em IK: arraste {ik} ou mude o membro para FK (IK_FK = 1)"
        if scope != LIMB:
            return [bone_name], ""
        links = _CHAINS["hand" if limb == "arm" else "foot"]
        upto = links[:links.index(base) + 1]
        return [CONCEPT_TO_BONE[f"{link}.{side}"] for link in upto], ""

    def body_override(self, arm_ob, bone_name):
        base = (self.concept_for(bone_name) or "").partition(".")[0]
        return base in _BODY_OVERRIDE and super().body_override(arm_ob, bone_name)

    def control_for_deform(self, arm_ob, deform_bone):
        """DEF-forearm.L.001 → forearm_fk.L (arm in FK, ephemeral rig) or hand_ik.L (arm in IK, grab/arc);
        DEF-spine.00N → hips/chest/neck/head; face and other parts → the control of the same name when it
        exists, else the head."""
        if not deform_bone.startswith(("DEF-", "ORG-")):      # ORG-: props parented to ORG bones (hand…)
            return super().control_for_deform(arm_ob, deform_bone)
        name = deform_bone[len("DEF-"):]
        bones = arm_ob.pose.bones
        base, _, rest = name.partition(".")
        side = rest.split(".")[0] if rest else ""
        if base in _LIMB_PARTS and side in ("L", "R"):
            state = self.ik_fk_state(arm_ob, f"{_LIMB_PARTS[base]}.{side}")
            if state is not None and state < 0.5:
                control = f"{_IK_CONTROL[base]}.{side}"
                kind = CHAIN if base == "toe" else IK
                if base in ("upper_arm", "thigh") and not self._pole_on(arm_ob, _LIMB_PARTS[base], side):
                    # without the pole the *_ik_target bone does nothing: move the hand/foot instead
                    control = f"{'hand_ik' if base == 'upper_arm' else 'foot_ik'}.{side}"
            else:
                control, kind = f"{base}_fk.{side}", CHAIN
            if control in bones:
                return control, kind, ""
        center = _SPINE.get(name) or _TO_CENTER.get(base)
        if center is None and base == "palm":
            center = f"palm.{name.rsplit('.', 1)[-1]}"          # DEF-palm.01.L -> palm.L
        candidates = [center] if center else []
        candidates += [name, name.rsplit(".", 1)[0] if name.count(".") > 1 else name, "head"]
        for control in candidates:
            if control and control in bones and self.is_control(control):
                return control, CHAIN, ""
        return super().control_for_deform(arm_ob, deform_bone)

    def _pole_on(self, arm_ob, limb, side):
        pb = arm_ob.pose.bones.get(f"{_SWITCH[limb]}.{side}")
        return bool(pb is not None and pb.get("pole_vector", False))

    def ephemeral_aim(self, arm_ob, bone_name, scope):
        """Corpo on the neck/head (decision 10): lean torso + chest first, then aim neck (and head)."""
        base = (self.concept_for(bone_name) or "").partition(".")[0]
        if scope != BODY or base not in ("neck", "head"):
            return []
        neck = CONCEPT_TO_BONE["neck"]
        return [neck] if base == "neck" else [neck, bone_name]

    def ephemeral_pins(self, arm_ob, chain):
        """Legs in FK keep their feet when the body turns (pinned to the chain root); legs in IK are
        pinned by the rig itself (``foot_ik`` hangs from the root)."""
        if not chain or self.concept_for(chain[0]) != "torso":
            return [], ""
        pins = []
        for side in ("L", "R"):
            state = self.ik_fk_state(arm_ob, f"leg.{side}")
            if state is not None and state >= 0.5:
                pins.append((chain[0], [CONCEPT_TO_BONE[f"{c}.{side}"] for c in _CHAINS["foot"]]))
        return pins, ""

    def translation_allowed(self, bone_name):
        # FK chain controls rotate; Rigify leaves location unlocked on the chain roots (upper_arm_fk,
        # thigh_fk) but moving them detaches the limb — not a sculpt target (FK sculpt: Escopo 4)
        concept = self.concept_for(bone_name)
        return concept is None or concept.partition(".")[0] not in FK_CONCEPTS

    def is_control(self, bone_name):
        return not bone_name.startswith(NON_CONTROL_PREFIXES)

    def deform_bones(self, arm_ob):
        return [b.name for b in arm_ob.data.bones if b.name.startswith("DEF-")]
