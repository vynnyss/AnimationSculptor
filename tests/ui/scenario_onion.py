# SPDX-License-Identifier: GPL-3.0-or-later
"""Onion skin (design/sculpt-ux.md, "Onion skin"): the ghosts follow the ruler window, and the expanded
onion draws them spread sideways like a film strip (past red on the left, future green on the right)."""

import os
import time

import bpy
from mathutils import Vector

import body_mesh


def _wait(cond, timeout=15.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def scenario(h):
    bpy.ops.wm.open_mainfile(filepath=os.environ["ASC_UI_RIG"], load_ui=False)
    yield 0.5
    provider = h.addon("trails.provider")
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and "hand_ik.L" in ob.pose.bones)
    body = body_mesh.add_skinned_body(rig)
    bpy.context.view_layer.objects.active = rig
    s = scene.asc_trails
    s.pinned.clear()
    item = s.pinned.add()
    item.obj = rig
    item.bone = "hand_ik.L"
    s.target_mode = 'PINNED'
    s.path_engine = 'STEP'
    s.path_range_mode = 'SCENE'
    s.onion_opacity = 0.5
    scene.frame_set(12)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.3, 1.0))
    eye = Vector((0.0, -6.0, 1.2))                  # front view: screen-right is world +X
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 6.0
    provider.set_enabled(scene, True)
    provider.apply_palette(scene)

    provider.set_onion(scene, True)
    before, after, step = provider.sync_onion_window(scene, 8, 8)
    h.check("the onion skin is on", s.onion_show)
    h.check("the window sets the ghost counts", (s.onion_before, s.onion_after, s.onion_step) == (8, 8, 1),
            (s.onion_before, s.onion_after, s.onion_step))
    h.check("the spread hook is off", not provider.onion_spread_enabled())
    yield 0.5
    yield from _wait(lambda: len(provider.engine.CACHE.get((body.name, ""), type("c", (), {"onion": {}})).onion) >= 12)
    h.screenshot("1-onion-in-place")

    provider.set_onion_spread(True)
    h.check("the spread hook is installed", provider.onion_spread_enabled())
    spacing = provider.spread_spacing(rig.name)
    h.check("automatic spacing is positive", spacing > 0.1, spacing)
    with h.override():
        right = Vector(bpy.context.region_data.view_matrix[0][:3])
        past = Vector(provider.ghost_offset(bpy.context, rig.name, 10, 12))
        future = Vector(provider.ghost_offset(bpy.context, rig.name, 15, 12))
    h.check("the current frame never moves", provider.ghost_offset(bpy.context, rig.name, 12, 12) is None)
    h.check("past ghosts shift left, future ghosts right", past.dot(right) < 0 < future.dot(right),
            (past.dot(right), future.dot(right)))
    h.check("the shift is proportional to f - f0",
            abs(future.dot(right) / past.dot(right) + 1.5) < 1e-4, (past.dot(right), future.dot(right)))
    yield 0.5
    h.screenshot("2-onion-expanded")

    provider.set_onion_spread(False)
    h.check("turning the spread off removes the hook", not provider.onion_spread_enabled())
    provider.set_onion(scene, False)
    h.check("the onion skin is off", not s.onion_show)
