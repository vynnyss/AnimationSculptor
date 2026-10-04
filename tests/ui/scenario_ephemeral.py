# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral rig, phase 3 (docs/design/ephemeral-rig.md): dragging the trail of an FK hand turns the arm.
The hand tail ends under the cursor, keys are written at every frame of the window only, one Ctrl+Z undoes
the gesture, Esc restores the curves bit for bit, the wheel changes the window during the drag."""

import os
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "attack_test.blend"


def _wait(cond, timeout=10.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def _dump(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbag(rig.animation_data.action_slot)
    return {(fc.data_path, fc.array_index): [tuple(k.co) + tuple(k.handle_left) + tuple(k.handle_right)
                                             for k in fc.keyframe_points] for fc in cb.fcurves}


def _key_frames(rig, bone):
    path = f'pose.bones["{bone}"].rotation_quaternion'
    cb = rig.animation_data.action.layers[0].strips[0].channelbag(rig.animation_data.action_slot)
    fc = cb.fcurves.find(path, index=0)
    return sorted(int(round(k.co[0])) for k in fc.keyframe_points) if fc else []


def scenario(h):
    if ASSET.exists():
        path, side, f0 = str(ASSET), "L", 16
    else:
        path, side, f0 = os.environ["ASC_UI_RIG"], "R", 12
    bone = f"hand_fk.{side}"
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    bpy.context.scene.asc_sculpt.interaction_mode = 'TRAIL'     # trail gestures (ADR 0013: Corpo is the default)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bone in ob.pose.bones and not ob.hide_viewport)
    rig_name = rig.name
    if not ASSET.exists():
        rig.pose.bones[f"upper_arm_parent.{side}"]["IK_FK"] = 1.0
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
    rig.data.bones.active = rig.data.bones[bone]
    scene.frame_set(f0)
    s = scene.asc_sculpt
    s.radius_linked = False
    s.radius_past, s.radius_future = 4.0, 6.0
    s.ephemeral_scope, s.tip_orientation = 'LIMB', 'WORLD'
    area, region, rv3d = h.view3d()
    target = Vector((0.2, -0.2, 1.3))
    eye = Vector((-2.4, -3.0, 1.7))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.0
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
    yield 0.5
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete)
    trail = provider.get_trail(rig, bone)
    h.check("the FK hand has a trail", trail is not None and trail.point_at(f0) is not None)
    if trail is None or trail.point_at(f0) is None:
        return

    keys_before = _key_frames(rig, bone)
    dump = _dump(rig)
    co = h.to_window(picking.world_to_screen(region, rv3d, Vector(trail.point_at(f0))))
    end = (co[0] + 45, co[1] + 35)

    # --- Esc first: bit-exact restore --------------------------------------------------------------
    h.move((co[0] + 25, co[1] + 25))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.check("press starts the chain gesture", state.GESTURE is not None and state.GESTURE["kind"] == "CHAIN",
            state.GESTURE and state.GESTURE["kind"])
    h.move(end)
    yield 0.3
    h.event('ESC', 'PRESS', end)
    h.event('ESC', 'RELEASE', end)
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.4
    rig = bpy.data.objects[rig_name]
    h.check("Esc restores the curves bit for bit", _dump(rig) == dump)

    # --- the real drag -----------------------------------------------------------------------------
    h.move((co[0] + 25, co[1] + 25))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    ms = []
    for i in range(1, 6):
        h.move((co[0] + (end[0] - co[0]) * i // 5, co[1] + (end[1] - co[1]) * i // 5))
        yield 0.05
        ms.append(state.STATS.get("last_move_ms", 0.0))
    h.screenshot("1-chain-drag")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    scene.frame_set(f0)
    tail = rig.matrix_world @ rig.pose.bones[bone].tail
    px = picking.world_to_screen(region, rv3d, tail)
    err = (Vector(h.to_window(px)) - Vector(end)).length if px is not None else 1e9
    h.check("the hand tail ends under the cursor", err < 1.5, f"{err:.2f} px")
    keys_after = _key_frames(rig, bone)
    # dense from the key before the window to the key after it (design: borders extended to the neighbours)
    lo = max((k for k in keys_before if k < f0 - 4 - 1), default=f0 - 5)
    hi = min((k for k in keys_before if k > f0 + 6 + 1), default=f0 + 7)
    new = sorted(set(keys_after) - set(keys_before))
    h.check("one key per frame between the neighbour keys of the window, nothing else",
            set(keys_after) == set(keys_before) - set(range(lo + 1, hi)) | set(range(lo, hi + 1)),
            f"{lo}..{hi}, new {new}")
    h.check("mouse move under 16 ms", max(ms) < 16.0, f"{max(ms):.2f} ms (prefetch {state.STATS.get('prefetch_ms', 0):.0f} ms)")
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete)
    h.screenshot("2-after-release")

    center = h.to_window((region.width // 2, region.height // 2))
    h.move(center)
    yield 0.2
    h.event('Z', 'PRESS', center, ctrl=True)
    h.event('Z', 'RELEASE', center, ctrl=True)
    yield 0.5
    for key in ('LEFT_CTRL',):
        h.event(key, 'PRESS', center)
        h.event(key, 'RELEASE', center)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z undoes the whole gesture", _dump(rig) == dump)
