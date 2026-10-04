# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig Adapter interface and selection (ADR 0002, docs/design/rig-adapter.md).

The core and the interaction speak in concepts and capabilities; an adapter translates them for one
armature. Adapters only answer questions: they never write animation.
"""

from __future__ import annotations

from .concepts import ROTATION, TRANSLATION, ControlInfo

TIP, LIMB, BODY = "TIP", "LIMB", "BODY"   # ephemeral gesture scopes (design: Ponta / Membro / Corpo)
LIMB_BONES = 3
BODY_BONES = 8
CHAIN, IK = "CHAIN", "IK"     # how a grabbed body part is sculpted: ephemeral rig / grab-arc of an IK control


class RigAdapter:
    id = "base"

    def __init__(self, arm_ob):
        self.arm_name = arm_ob.name

    @classmethod
    def detect(cls, arm_ob) -> float:
        """Confidence 0..1 that this adapter understands ``arm_ob``."""
        return 0.0

    # -- vocabulary ---------------------------------------------------------------------------
    def bone_for(self, concept: str) -> str | None:
        return None

    def concept_for(self, bone_name: str) -> str | None:
        return None

    def chain(self, concept: str) -> list:
        return []

    def ik_fk_state(self, arm_ob, limb: str) -> float | None:
        """0 = IK, 1 = FK; None when the rig has no switch for ``limb`` ('arm.L', 'leg.R')."""
        return None

    # -- classification -----------------------------------------------------------------------
    def is_control(self, bone_name: str) -> bool:
        return True

    def translation_allowed(self, bone_name: str) -> bool:
        """Adapters veto translation for controls that are rotation-only by design (FK chains)."""
        return True

    def deform_bones(self, arm_ob) -> list:
        return [b.name for b in arm_ob.data.bones if b.use_deform]

    def classify(self, arm_ob, bone_name: str) -> ControlInfo | None:
        pb = arm_ob.pose.bones.get(bone_name)
        if pb is None or not self.is_control(bone_name):
            return None
        bone = getattr(pb, "bone", None)
        if bone is not None and getattr(bone, "use_connect", False):
            free = (False, False, False)     # Blender ignores location of connected bones
        else:
            free = tuple(not locked for locked in pb.lock_location)
        if not self.translation_allowed(bone_name):
            free = (False, False, False)
        caps = set()
        if any(free):
            caps.add(TRANSLATION)
        rot_locked = pb.lock_rotation_w and all(pb.lock_rotation) if pb.rotation_mode in ('QUATERNION', 'AXIS_ANGLE') \
            else all(pb.lock_rotation)
        if not rot_locked:
            caps.add(ROTATION)
        return ControlInfo(name=bone_name, concept=self.concept_for(bone_name), capabilities=frozenset(caps),
                           free_axes=free, reference="HEAD" if TRANSLATION in caps else "TAIL")

    # -- ephemeral rig (ADR 0011) ---------------------------------------------------------------
    def ephemeral_chain(self, arm_ob, bone_name: str, scope: str = LIMB):
        """Bones (root → dragged bone) the ephemeral gesture may turn, and a refusal reason ('' when fine).

        ``TIP``: the bone alone (it turns to point at the target). ``LIMB``: up to three bones ending at the
        dragged one, walking up the hierarchy while each parent rotates, is a control and has this single
        child (a branch — a spine with arms — ends the limb). No names: works on any skeleton."""
        info = self.classify(arm_ob, bone_name)
        if info is None:
            return [], "não é um controle do rig (MCH/ORG/DEF)"
        if not info.rotates:
            return [], "controle travado (sem rotação livre)"
        chain = [bone_name]
        if scope in (LIMB, BODY):
            # LIMB stops at a branch (a spine with arms); BODY crosses branches up to the top of the skeleton
            limit = LIMB_BONES if scope == LIMB else BODY_BONES
            parent = arm_ob.pose.bones[bone_name].parent
            while parent is not None and len(chain) < limit:
                pinfo = self.classify(arm_ob, parent.name)
                if pinfo is None or not pinfo.rotates or (scope == LIMB and len(parent.children) != 1):
                    break
                chain.insert(0, parent.name)
                parent = parent.parent
        return chain, ""

    def body_override(self, arm_ob, bone_name: str) -> bool:
        """In the ``Corpo`` scope, dragging this control's tail turns the body even if it translates."""
        info = self.classify(arm_ob, bone_name)
        return info is not None and info.rotates

    def control_for_deform(self, arm_ob, deform_bone: str):
        """(control, kind, reason) for a body part grabbed on the mesh (ADR 0013): the control that moves
        that part. Generic skeletons (Mixamo) are animated on the deform bones themselves: the bone, CHAIN."""
        info = self.classify(arm_ob, deform_bone)
        if info is None or not info.rotates:
            return None, None, f"{deform_bone}: parte sem controle (bone travado ou não é controle)"
        return deform_bone, CHAIN, ""

    def ephemeral_aim(self, arm_ob, bone_name: str, scope: str):
        """Bones aimed after the chain moved (decision 10), root first, ending at the dragged one; [] = none."""
        return []

    def ephemeral_pins(self, arm_ob, chain):
        """(chain bone, limb bones) whose end stays put while the ``Corpo`` chain turns: the single-child
        limbs (2–3 bones) hanging from the chain's root that are not on the chain (legs under the hips)."""
        if not chain:
            return [], ""
        root = arm_ob.pose.bones[chain[0]]
        pins = []
        for child in root.children:
            if child.name in chain:
                continue
            limb = [child.name]
            bone = child
            while len(bone.children) == 1 and len(limb) < LIMB_BONES:
                bone = bone.children[0]
                limb.append(bone.name)
            infos = [self.classify(arm_ob, name) for name in limb]
            if len(limb) >= 2 and all(i is not None and i.rotates for i in infos):
                pins.append((chain[0], limb))
        return pins, ""

    def controls(self, arm_ob) -> list:
        out = []
        for pb in arm_ob.pose.bones:
            info = self.classify(arm_ob, pb.name)
            if info is not None and info.capabilities:
                out.append(info)
        return out


_ADAPTERS = []
_CACHE = {}     # (armature name, data name, rig_id) -> adapter


def register_adapter(cls):
    if cls not in _ADAPTERS:
        _ADAPTERS.append(cls)
    return cls


def get_adapter(arm_ob) -> RigAdapter:
    """Best adapter for the armature (cached; ``clear_cache`` on file load / rig change)."""
    key = (arm_ob.name, arm_ob.data.name, str(arm_ob.data.get("rig_id", "")))
    adapter = _CACHE.get(key)
    if adapter is None:
        best = max(_ADAPTERS, key=lambda cls: cls.detect(arm_ob))
        adapter = best(arm_ob)
        _CACHE[key] = adapter
    return adapter


def clear_cache():
    _CACHE.clear()
