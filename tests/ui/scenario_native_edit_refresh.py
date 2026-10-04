# SPDX-License-Identifier: GPL-3.0-or-later
"""Trails follow native edits (acceptance criterion 3): G to move a control, I to key it — the trail
must update without pressing Refresh (maintainer report, 2026-10-03)."""

import os
import time
from pathlib import Path

import bpy
from mathutils import Vector

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "attack_test.blend"


def _wait(cond, timeout=8.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def scenario(h):
    if ASSET.exists():
        path, bone, frame = str(ASSET), "hand_ik.R", 12
    else:
        path, bone, frame = os.environ["ASC_UI_RIG"], "hand_ik.L", 7
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    bpy.context.scene.asc_sculpt.interaction_mode = 'TRAIL'     # trail gestures (ADR 0013: Corpo is the default)
    yield 0.5
    provider = h.addon("trails.provider")
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bone in ob.pose.bones and not ob.hide_viewport)
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
    rig.data.bones.active = rig.data.bones[bone]
    scene.frame_set(frame)
    scene.asc_trails.enabled = True
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.3, 1.2))
    eye = Vector((-2.6, -3.2, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete)
    h.check("trail ready", provider.get_trail(rig, bone) is not None)

    center = h.to_window((region.width // 2, region.height // 2))

    def trail_matches():
        t = provider.get_trail(rig, bone)
        head = rig.matrix_world @ rig.pose.bones[bone].head
        return t is not None and t.point_at(frame) is not None and (Vector(t.point_at(frame)) - head).length < 1e-4

    for step in range(2):   # twice: the first edit after a recompute must not be swallowed either
        h.move(center)
        yield 0.2
        h.event('G', 'PRESS', center)
        h.event('G', 'RELEASE', center)
        yield 0.3
        h.move((center[0] + 60, center[1] + 30))
        yield 0.3
        h.event('LEFTMOUSE', 'PRESS', (center[0] + 60, center[1] + 30))
        h.event('LEFTMOUSE', 'RELEASE', (center[0] + 60, center[1] + 30))
        yield 0.5
        h.event('I', 'PRESS', (center[0] + 60, center[1] + 30))
        h.event('I', 'RELEASE', (center[0] + 60, center[1] + 30))
        yield from _wait(trail_matches)
        t = provider.get_trail(rig, bone)
        head = rig.matrix_world @ rig.pose.bones[bone].head
        err = None if t is None or t.point_at(frame) is None else (Vector(t.point_at(frame)) - head).length
        h.check(f"edit {step + 1}: G + I updates the trail without Refresh", trail_matches(), err)
    h.screenshot("after-g-i")
