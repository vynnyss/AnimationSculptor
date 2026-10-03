# SPDX-License-Identifier: GPL-3.0-or-later
"""Viewport interaction: tool, gizmo hover/picking, gesture operator, overlay (ADR 0010)."""

from . import gizmo, overlay, sculpt_tool

_modules = (gizmo, sculpt_tool, overlay)  # the tool references the gizmo group: register it first


def register():
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        try:
            m.unregister()
        except Exception as exc:
            print(f"[Animation Sculptor] unregister error in {m.__name__}: {exc}")
