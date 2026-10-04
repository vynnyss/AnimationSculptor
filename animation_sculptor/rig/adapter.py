# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig Adapter interface and selection (ADR 0002, docs/design/rig-adapter.md).

The core and the interaction speak in concepts and capabilities; an adapter translates them for one
armature. Adapters only answer questions: they never write animation.
"""

from __future__ import annotations

from .concepts import ROTATION, TRANSLATION, ControlInfo


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
