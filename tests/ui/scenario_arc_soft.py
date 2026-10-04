# SPDX-License-Identifier: GPL-3.0-or-later
"""Arc drag of an in-between, soft grab with the mouse wheel and a visible refusal (FK control)."""

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


def _keys(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    return {(fc.data_path, fc.array_index): [k.co[0] for k in fc.keyframe_points] for fc in cb.fcurves}


def scenario(h):
    if ASSET.exists():
        path, bone, fk_bone, key_frame, mid_frame = str(ASSET), "hand_ik.R", "upper_arm_fk.L", 18, 13
    else:
        path, bone, fk_bone, key_frame, mid_frame = os.environ["ASC_UI_RIG"], "hand_ik.L", "upper_arm_fk.R", 12, 6
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
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
        pb.select = pb.name in (bone, fk_bone)
    rig.data.bones.active = rig.data.bones[bone]
    scene.frame_set(1)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.3, 1.2))
    eye = Vector((-2.6, -3.2, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2
    with h.override():
        bpy.ops.wm.tool_set_by_id(name=tool_id)
    yield 0.5
    ready = lambda b: (t := provider.get_trail(rig, b)) is not None and t.complete  # noqa: E731
    yield from _wait(lambda: ready(bone) and ready(fk_bone))

    def win(world):
        return h.to_window(picking.world_to_screen(region, rv3d, Vector(world)))

    def hover(co):
        h.move((co[0] + 25, co[1] + 25))
        yield 0.2
        h.move(co)
        yield 0.3

    # --- arc drag of an in-between ---------------------------------------------------------------
    trail = provider.get_trail(rig, bone)
    co = win(trail.point_at(mid_frame))
    yield from hover(co)
    h.check("hover picks the in-between", state.HOVER is not None and not state.HOVER.is_key
            and state.HOVER.frame == mid_frame, state.HOVER and (state.HOVER.frame, state.HOVER.is_key))
    keys = _keys(rig)
    end = (co[0] + 50, co[1] + 40)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.check("arc gesture started", state.GESTURE is not None and state.GESTURE["kind"] == "ARC")
    for i in range(1, 6):
        h.move((co[0] + 50 * i // 5, co[1] + 40 * i // 5))
        yield 0.1
    h.screenshot("1-arc-drag")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.5
    scene_frame = scene.frame_current
    head = rig.matrix_world @ rig.pose.bones[bone].head
    err = (Vector(h.to_window(picking.world_to_screen(region, rv3d, head))) - Vector(end)).length
    h.check("in-between ends under the cursor", scene_frame == mid_frame and err < 2.0, f"{err:.2f} px")
    h.check("arc drag adds no keys and keeps timing", _keys(rig) == keys)

    # --- soft grab: wheel grows the radius ---------------------------------------------------------
    yield from _wait(lambda: ready(bone))
    trail = provider.get_trail(rig, bone)
    neighbors = [f for f in trail.keyframes if f != key_frame]
    before = {f: Vector(trail.point_at(f)) for f in neighbors}
    co = win(trail.point_at(key_frame))
    yield from hover(co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    for _ in range(8):
        h.event('WHEELUPMOUSE', 'PRESS', co)
        yield 0.05
    h.move((co[0] + 40, co[1] - 30))
    yield 0.3
    weights = state.GESTURE and state.GESTURE.get("falloff")
    h.check("wheel sets the soft radius (falloff points drawn)", bool(weights), weights and len(weights))
    h.screenshot("2-soft-grab")
    h.event('LEFTMOUSE', 'RELEASE', (co[0] + 40, co[1] - 30))
    yield 0.5
    yield from _wait(lambda: ready(bone))
    trail = provider.get_trail(rig, bone)
    moved = [f for f in neighbors if (Vector(trail.point_at(f)) - before[f]).length > 1e-4]
    h.check("neighbour keys followed", len(moved) > 0, moved)
    bpy.context.scene.asc_sculpt.radius_past = bpy.context.scene.asc_sculpt.radius_future = 0.0

    # --- refusal is visible (only the FK control selected, so its trail is the only one) ---------------
    rig.pose.bones[bone].select = False
    rig.data.bones.active = rig.data.bones[fk_bone]
    yield 0.5
    yield from _wait(lambda: ready(fk_bone) and provider.get_trail(rig, bone) is None or ready(fk_bone))
    fk_trail = provider.get_trail(rig, fk_bone)
    def inside(f):
        p2 = picking.world_to_screen(region, rv3d, Vector(fk_trail.point_at(f)))
        return p2 is not None and 20 < p2.x < region.width - 20 and 20 < p2.y < region.height - 20

    fk_key = next((f for f in fk_trail.keyframes if fk_trail.point_at(f) is not None and inside(f)), None)
    h.check("an FK key point is visible", fk_key is not None)
    if fk_key is None:
        return
    co = win(fk_trail.point_at(fk_key))
    yield from hover(co)
    h.check("hover on the FK trail key", state.HOVER is not None and state.HOVER.bone == fk_bone,
            state.HOVER and (state.HOVER.bone, state.HOVER.frame, state.HOVER.is_key, round(state.HOVER.distance, 1)))
    keys = _keys(rig)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    h.event('LEFTMOUSE', 'RELEASE', co)
    yield 0.3
    refusal = state.REFUSAL
    h.check("FK key refused with a reason", refusal is not None and "rotação" in refusal["reason"],
            refusal and refusal["reason"])
    h.check("refusal changes nothing", _keys(rig) == keys)
    h.screenshot("3-refusal")
