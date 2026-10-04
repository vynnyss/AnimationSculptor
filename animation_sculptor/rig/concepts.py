# SPDX-License-Identifier: GPL-3.0-or-later
"""Anatomical vocabulary used by the rest of the add-on (ADR 0002). No bpy; no rig-specific names."""

from __future__ import annotations

from dataclasses import dataclass, field

SIDES = ("L", "R")
CENTER = ("root", "torso", "hips", "chest", "neck", "head")
LIMB = ("shoulder", "upper_arm", "forearm", "hand", "hand_ik", "pole_arm",
        "thigh", "shin", "foot", "foot_ik", "pole_leg")
CONCEPTS = CENTER + tuple(f"{c}.{s}" for c in LIMB for s in SIDES)

TRANSLATION = "TRANSLATION"
ROTATION = "ROTATION"


@dataclass(frozen=True)
class ControlInfo:
    """What the sculpt tool may do with one pose bone."""

    name: str
    concept: str | None = None
    capabilities: frozenset = field(default_factory=frozenset)   # {TRANSLATION, ROTATION}
    free_axes: tuple = (True, True, True)                         # location axes not locked
    reference: str = "HEAD"                                       # trail point: HEAD (translation) / TAIL (FK)

    @property
    def translates(self) -> bool:
        return TRANSLATION in self.capabilities

    @property
    def rotates(self) -> bool:
        return ROTATION in self.capabilities
