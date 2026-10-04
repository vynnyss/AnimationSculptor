# SPDX-License-Identifier: GPL-3.0-or-later
"""Fallback adapter: any armature. Every pose bone is a control; capabilities come from its locks."""

from .adapter import RigAdapter, register_adapter


@register_adapter
class GenericAdapter(RigAdapter):
    id = "generic"

    @classmethod
    def detect(cls, arm_ob) -> float:
        return 0.1 if arm_ob is not None and arm_ob.type == 'ARMATURE' else 0.0
