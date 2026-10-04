# SPDX-License-Identifier: GPL-3.0-or-later
"""Ephemeral rig, phase 4 (docs/design/ephemeral-rig.md): a click without a drag writes nothing; in the
Corpo scope the chest is dragged by its tail directly (no trail) and the torso leans, the IK feet stay."""

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


def _dump(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbag(rig.animation_data.action_slot)
    return {(fc.data_path, fc.array_index): [tuple(k.co) + tuple(k.handle_left) + tuple(k.handle_right)
                                             for k in fc.keyframe_points] for fc in cb.fcurves}


def scenario(h):
    if ASSET.exists():
        path, fk_side, f0 = str(ASSET), "L", 16
    else:
        path, fk_side, f0 = os.environ["ASC_UI_RIG"], "R", 12
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    bpy.context.scene.asc_sculpt.interaction_mode = 'TRAIL'     # trail gestures (ADR 0013: Corpo is the default)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and "chest" in ob.pose.bones and not ob.hide_viewport)
    rig_name = rig.name
    if not ASSET.exists():
        rig.pose.bones[f"upper_arm_parent.{fk_side}"]["IK_FK"] = 1.0
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    fk = f"hand_fk.{fk_side}"
    for pb in rig.pose.bones:
        pb.select = pb.name == fk
    rig.data.bones.active = rig.data.bones[fk]
    scene.frame_set(f0)
    s = scene.asc_sculpt
    s.radius_linked = False
    s.radius_past, s.radius_future = 4.0, 4.0
    s.ephemeral_scope = 'LIMB'
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.2, 1.2))
    eye = Vector((-2.6, -3.0, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
    yield 0.5
    yield from _wait(lambda: (t := provider.get_trail(rig, fk)) is not None and t.complete)

    # --- a click without a drag writes nothing ------------------------------------------------------
    dump = _dump(rig)
    trail = provider.get_trail(rig, fk)
    co = h.to_window(picking.world_to_screen(region, rv3d, Vector(trail.point_at(f0))))
    h.move((co[0] + 25, co[1] + 25))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    h.event('LEFTMOUSE', 'RELEASE', co)
    yield 0.4
    rig = bpy.data.objects[rig_name]
    h.check("a click without a drag writes nothing (no dense keys)", _dump(rig) == dump)

    # --- Corpo: drag the chest by its tail ------------------------------------------------------------
    s = bpy.context.scene.asc_sculpt
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.body")       # the Corpo tool sets the scope
    for pb in rig.pose.bones:
        pb.select = pb.name == "chest"
    rig.data.bones.active = rig.data.bones["chest"]
    yield 0.5
    feet = {side: (rig.matrix_world @ rig.pose.bones[f"foot_ik.{side}"].head).copy() for side in ("L", "R")}
    tail = rig.matrix_world @ rig.pose.bones["chest"].tail
    co = h.to_window(picking.world_to_screen(region, rv3d, tail))
    h.move((co[0] + 30, co[1] + 30))
    yield 0.2
    h.move(co)
    yield 0.3
    hover = state.HOVER
    h.check("hover picks the chest's tail (bone drag, no trail)", hover is not None and hover.on_bone and
            hover.bone == "chest", hover and (hover.bone, hover.on_bone))
    end = (co[0] - 30, co[1] - 25)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    g = state.GESTURE
    h.check("the drag starts the Corpo chain", g is not None and g["kind"] == "CHAIN", g and g["kind"])
    for i in range(1, 6):
        h.move((co[0] + (end[0] - co[0]) * i // 5, co[1] + (end[1] - co[1]) * i // 5))
        yield 0.05
    h.screenshot("1-body-lean")
    ms = state.STATS.get("last_move_ms", 0.0)
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    scene.frame_set(f0)
    tail = rig.matrix_world @ rig.pose.bones["chest"].tail
    px = picking.world_to_screen(region, rv3d, tail)
    err = (Vector(h.to_window(px)) - Vector(end)).length if px is not None else 1e9
    h.check("the chest tail ends under the cursor", err < 1.5, f"{err:.2f} px")
    moved = max((rig.matrix_world @ rig.pose.bones[f"foot_ik.{side}"].head - feet[side]).length for side in ("L", "R"))
    h.check("the IK feet stay put", moved < 1e-5, f"{moved:.2e} m")
    h.check("mouse move under 16 ms", ms < 16.0, f"{ms:.2f} ms")
    center = h.to_window((region.width // 2, region.height // 2))
    h.move(center)
    yield 0.2
    h.event('Z', 'PRESS', center, ctrl=True)
    h.event('Z', 'RELEASE', center, ctrl=True)
    yield 0.5
    h.event('LEFT_CTRL', 'PRESS', center)
    h.event('LEFT_CTRL', 'RELEASE', center)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z undoes the lean", _dump(rig) == dump)
