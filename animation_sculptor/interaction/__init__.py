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
    from ..trails import provider

    provider.FOCUS.clear()          # the body part last touched belongs to the old file


@persistent
def _depsgraph_post(*_args):
    body_pick.bump()


def register():
    for m in _modules:
        m.register()
    if _load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_load_post)
    if _depsgraph_post not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_depsgraph_post)


def unregister():
    while _load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_load_post)
    while _depsgraph_post in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_depsgraph_post)
    for m in reversed(_modules):
        try:
            m.unregister()
        except Exception as exc:
            print(f"[Animation Sculptor] unregister error in {m.__name__}: {exc}")
