# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport interaction: tool, gizmo hover/picking, gesture operator, overlay (ADR 0010)."""

import bpy
from bpy.app.handlers import persistent

from .. import rig
from . import body_pick, gizmo, overlay, sculpt_tool, state

_modules = (gizmo, sculpt_tool, overlay)  # the tool references the gizmo group: register it first


@persistent
def _load_post(*_args):
    """Derived state never survives a file change (adapters are re-detected, hover/gesture dropped)."""
    rig.clear_cache()
    body_pick.clear_cache()
    state.reset()


def register():
    for m in _modules:
        m.register()
    if _load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_post)


def unregister():
    while _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    for m in reversed(_modules):
        try:
            m.unregister()
        except Exception as exc:
            print(f"[Animation Sculptor] unregister error in {m.__name__}: {exc}")
