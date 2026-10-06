# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (compat.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""
Version compatibility helpers.

The add-on targets Blender 5.1 / 5.2 but keeps working on 4.2+ where the
underlying APIs exist.  Everything that changed between 4.2 and 5.x
(slotted Actions, bone selection, modal-operator introspection ...) is
wrapped here so the rest of the code can stay version agnostic.
"""

import bpy

VERSION = bpy.app.version
IS_5X = VERSION >= (5, 0, 0)
HAS_SLOTTED_ACTIONS = VERSION >= (4, 4, 0)

# Operators that we never want to interfere with while they are running
# (a depsgraph frame step in the middle of a transform would fight with the
# modal operator over the object's location).
_BLOCKING_MODAL_PREFIXES = ("TRANSFORM_OT_", "ANIM_OT_", "GRAPH_OT_", "ACTION_OT_", "SCREEN_OT_animation")


# ---------------------------------------------------------------------------
# Animation data access
# ---------------------------------------------------------------------------

def get_fcurves(adt):
    """Return a list of F-Curves for the Action assigned to *adt*.

    Handles both the legacy single-action API (``Action.fcurves``, removed in
    Blender 5.0) and the slotted-action API introduced in 4.4
    (``layers -> strips -> channelbag(slot) -> fcurves``).
    """
    if adt is None:
        return []
    act = adt.action
    if act is None:
        return []

    slot = getattr(adt, "action_slot", None)
    if slot is not None:
        # Preferred helper (4.4+).
        try:
            from bpy_extras import anim_utils
            cb = anim_utils.action_get_channelbag_for_slot(act, slot)
            if cb is not None:
                return list(cb.fcurves)
            return []
        except Exception:
            pass
        # Manual walk of the layered action.
        try:
            for layer in act.layers:
                for strip in layer.strips:
                    if getattr(strip, "type", 'KEYFRAME') != 'KEYFRAME':
                        continue
                    cb = strip.channelbag(slot)
                    if cb is not None:
                        return list(cb.fcurves)
        except Exception:
            pass

    # Legacy API (< 5.0).
    fcurves = getattr(act, "fcurves", None)
    if fcurves is not None:
        try:
            return list(fcurves)
        except Exception:
            return []
    return []


def get_drivers(adt):
    if adt is None:
        return []
    try:
        return list(adt.drivers)
    except Exception:
        return []


def has_nla_strips(adt):
    if adt is None:
        return False
    try:
        if not adt.use_nla:
            return False
        for track in adt.nla_tracks:
            if track.mute:
                continue
            if len(track.strips):
                return True
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# Bones
# ---------------------------------------------------------------------------

def pose_bone_selected(pbone):
    """Bone selection moved from ``Bone.select`` to ``PoseBone.select`` in 5.0."""
    sel = getattr(pbone, "select", None)
    if sel is None:
        try:
            sel = pbone.bone.select
        except Exception:
            sel = False
    return bool(sel)


def set_pose_bone_selected(pbone, value):
    """ASC-PATCH P13: write the selection (``PoseBone.select`` in 5.x, ``Bone.select`` before)."""
    if hasattr(pbone, "select"):
        pbone.select = bool(value)
    else:
        pbone.bone.select = bool(value)


def pose_bone_hidden(pbone):
    try:
        if pbone.bone.hide:
            return True
    except Exception:
        pass
    return bool(getattr(pbone, "hide", False))


def active_pose_bone_name(arm_ob):
    try:
        ab = arm_ob.data.bones.active
        if ab is not None:
            return ab.name
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Window / modal operators
# ---------------------------------------------------------------------------

def main_window():
    """Return a usable window (timers do not always have one in their context)."""
    try:
        win = bpy.context.window
        if win is not None:
            return win
    except Exception:
        pass
    try:
        wins = bpy.context.window_manager.windows
        if len(wins):
            return wins[0]
    except Exception:
        pass
    return None


def blocking_modal_running():
    """True while a transform-like modal operator is running in any window.

    Uses ``Window.modal_operators`` (available in 4.2+).  When the attribute
    does not exist we cannot know, so we report False and rely on the
    debounce delay instead.
    """
    try:
        wm = bpy.context.window_manager
        for win in wm.windows:
            ops = getattr(win, "modal_operators", None)
            if ops is None:
                return False
            for op in ops:
                idname = getattr(op, "bl_idname", "")
                if idname.startswith(_BLOCKING_MODAL_PREFIXES):
                    return True
    except Exception:
        return False
    return False


def is_playing():
    try:
        wm = bpy.context.window_manager
        for win in wm.windows:
            scr = win.screen
            if scr is not None and scr.is_animation_playing:
                return True
    except Exception:
        return False
    return False


def tag_redraw_all():
    try:
        wm = bpy.context.window_manager
        for win in wm.windows:
            for area in win.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:
        pass


def ui_scale():
    try:
        s = bpy.context.preferences.system.ui_scale
        if s and s > 0.1:
            return s
    except Exception:
        pass
    return 1.0


def pixel_size():
    try:
        p = bpy.context.preferences.system.pixel_size
        if p and p > 0.1:
            return p
    except Exception:
        pass
    return 1.0


def id_key(idblock):
    """Hashable identity for an ID data-block: (id_type, name)."""
    try:
        return (idblock.id_type, idblock.name)
    except Exception:
        return (type(idblock).__name__, getattr(idblock, "name", ""))
