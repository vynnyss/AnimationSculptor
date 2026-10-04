# SPDX-License-Identifier: GPL-3.0-or-later
"""After releasing a grab the trail must refresh by itself (no frame change, no Refresh button).

Regression for the maintainer's report on PR #5. Uses the local attack asset when present (the
real Rigify character), else the public rig.
"""

import os
import time
from pathlib import Path

import bpy
from mathutils import Vector

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "attack_test.blend"


def _wait(cond, timeout=10.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def scenario(h):
    if ASSET.exists():
        path, bone, key_frame = str(ASSET), "hand_ik.R", 18
    else:
        path, bone, key_frame = os.environ["ASC_UI_RIG"], "hand_ik.L", 12
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    bpy.context.scene.asc_sculpt.interaction_mode = 'TRAIL'     # trail gestures (ADR 0013: Corpo is the default)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    tool_id = h.addon("interaction.sculpt_tool").TOOL_ID

    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bone in ob.pose.bones and not ob.hide_viewport)
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
    rig.data.bones.active = rig.data.bones[bone]
    scene.frame_set(1)

    area, region, rv3d = h.view3d()
    rv3d.view_perspective = 'PERSP'
    target = Vector((0.0, -0.3, 1.2))
    eye = Vector((-2.6, -3.2, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2

    with h.override():
        bpy.ops.wm.tool_set_by_id(name=tool_id)
    yield 0.5
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete)
    trail = provider.get_trail(rig, bone)
    h.check("trail ready", trail is not None and trail.complete)
    if trail is None:
        return
    old_point = Vector(trail.point_at(key_frame))
    win_co = h.to_window(picking.world_to_screen(region, rv3d, old_point))
    h.move((win_co[0] + 30, win_co[1] + 30))
    yield 0.2
    h.move(win_co)
    yield 0.3
    h.check("hover on the key", state.HOVER is not None and state.HOVER.frame == key_frame,
            state.HOVER and (state.HOVER.bone, state.HOVER.frame))
    h.event('LEFTMOUSE', 'PRESS', win_co)
    yield 0.3
    end = (win_co[0] + 70, win_co[1] - 40)
    for i in range(1, 6):
        h.move((win_co[0] + 70 * i // 5, win_co[1] - 40 * i // 5))
        yield 0.1
    preview = state.GESTURE and state.GESTURE.get("preview")
    h.check("live trail preview during the drag", preview is not None and len(preview) > 1)
    h.screenshot("1-drag")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.3
    # no frame change, no Refresh: the engine must recompute on its own
    head = rig.matrix_world @ rig.pose.bones[bone].head
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete
                     and (Vector(t.point_at(key_frame)) - head).length < 1e-4, timeout=8.0)
    trail = provider.get_trail(rig, bone)
    ok = trail is not None and (Vector(trail.point_at(key_frame)) - head).length < 1e-4
    h.check("trail refreshed by itself after release", ok,
            None if trail is None else f"{(Vector(trail.point_at(key_frame)) - head).length:.5f} m")
    h.check("current frame is the key frame", scene.frame_current == key_frame, scene.frame_current)
    stats = {k: round(v, 2) for k, v in state.STATS.items()}
    h.check(f"timings recorded {stats}", "prefetch_ms" in stats and "refresh_ms" in stats)
    h.screenshot("2-released")
