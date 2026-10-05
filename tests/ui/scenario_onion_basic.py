# SPDX-License-Identifier: GPL-3.0-or-later
"""Expanded onion on the Vale with the simple skeleton (ADR 0014): the head, torso and legs are separate
meshes of one skeleton, and their ghosts must move together (one spacing per character), turned on with
the N-panel toggles. Uses the local asset (``dev.py basic-rig``)."""

import os
import time
from pathlib import Path

import bpy
from mathutils import Vector

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "basic_rig_test.blend"


def _wait(cond, timeout=20.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def scenario(h):
    if not ASSET.exists():
        h.check("basic rig asset present (python scripts/dev.py basic-rig)", True, "skipped")
        return
    bpy.ops.wm.open_mainfile(filepath=str(ASSET), load_ui=False)
    yield 0.5
    provider = h.addon("trails.provider")
    scene = bpy.context.scene
    rig = bpy.data.objects[scene["asc_asset_rig"]]
    for ob in bpy.data.objects:                  # the Vale's knee/shoulder/skirt pieces are hidden in the file
        if ob.type == 'MESH':
            ob.hide_set(False)
    meshes = [ob for ob in bpy.data.objects if ob.type == 'MESH' and ob.visible_get()
              and provider.character_of(ob.name) == rig.name]
    h.check("several visible meshes of one skeleton", len(meshes) >= 2, [m.name for m in meshes])
    bpy.context.view_layer.objects.active = rig
    scene.frame_set(12)
    s = scene.asc_sculpt
    s.show_rig = False
    s.radius_linked = True
    s.radius_past = 6.0
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.body")
    t = scene.asc_trails
    t.path_engine = 'STEP'
    t.onion_include_armature_meshes = True
    area, region, rv3d = h.view3d()
    target = Vector((0.0, 0.0, 1.0))
    eye = Vector((0.0, -9.0, 1.2))                  # front view: screen-right is world +X
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 9.0

    s.onion_show = True                              # the N-panel toggles
    s.onion_spread = True
    h.check("the expanded onion hook is on", provider.onion_spread_enabled())
    yield 0.5
    keys = [(m.name, "") for m in meshes]
    yield from _wait(lambda: all(len(getattr(provider.engine.CACHE.get(k), "onion", {})) >= 6 for k in keys))
    h.check("every mesh of the character has ghosts",
            all(len(getattr(provider.engine.CACHE.get(k), "onion", {})) >= 6 for k in keys),
            {k[0]: len(getattr(provider.engine.CACHE.get(k), "onion", {})) for k in keys})
    with h.override():
        offs = [Vector(provider.ghost_offset(bpy.context, m.name, 8, 12)) for m in meshes]
    h.check("all the meshes shift by the same amount (one spacing per character)",
            max((o - offs[0]).length for o in offs) < 1e-6, [tuple(round(c, 4) for c in o) for o in offs])
    yield 0.5
    h.screenshot("1-expanded")

    s = bpy.context.scene.asc_sculpt
    s.onion_spread = False
    s.onion_show = False
    s.show_rig = True
    h.check("the onion skin is off", not bpy.context.scene.asc_trails.onion_show)
