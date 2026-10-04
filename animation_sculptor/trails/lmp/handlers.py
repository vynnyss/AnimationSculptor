# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (handlers.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""Application handlers that keep the overlay live."""

import bpy
from bpy.app.handlers import persistent

from . import engine


@persistent
def _depsgraph_update_post(scene, depsgraph):
    try:
        engine.depsgraph_changed(scene, depsgraph)
    except Exception as e:
        print("[Live Motion Onion] depsgraph handler error: %s" % e)


@persistent
def _frame_change_post(scene, depsgraph=None):
    try:
        engine.frame_changed(scene)
    except Exception as e:
        print("[Live Motion Onion] frame handler error: %s" % e)


@persistent
def _playback_pre(scene, depsgraph=None):
    engine.playback_started(scene)


@persistent
def _playback_post(scene, depsgraph=None):
    engine.playback_stopped(scene)


@persistent
def _load_post(*args):
    engine.clear_all()
    engine.STATE.reset()
    engine.schedule(delay=0.2)


@persistent
def _undo_post(scene, depsgraph=None):
    engine.clear_all()
    engine.schedule(delay=0.0)


_pairs = (
    ("depsgraph_update_post", _depsgraph_update_post),
    ("frame_change_post", _frame_change_post),
    ("animation_playback_pre", _playback_pre),
    ("animation_playback_post", _playback_post),
    ("load_post", _load_post),
    ("undo_post", _undo_post),
    ("redo_post", _undo_post),
)


def register():
    for name, fn in _pairs:
        lst = getattr(bpy.app.handlers, name, None)
        if lst is None:
            continue
        if fn not in lst:
            lst.append(fn)


def unregister():
    for name, fn in _pairs:
        lst = getattr(bpy.app.handlers, name, None)
        if lst is None:
            continue
        while fn in lst:
            lst.remove(fn)
    try:
        engine._cancel_timer()
    except Exception:
        pass
