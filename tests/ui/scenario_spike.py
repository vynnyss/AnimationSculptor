# SPDX-License-Identifier: GPL-3.0-or-later
"""Interaction spike (ADR 0010): tool + gizmo hover + modal drag + one undo step per gesture + Esc."""

import os
import time

import bpy
from mathutils import Vector

import public_rig as pr

BONE = "hand_ik.L"
KEY_FRAME = 12


def _location_keys(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    path = rig.pose.bones[BONE].path_from_id("location")
    out = []
    for i in range(3):
        fc = cb.fcurves.find(path, index=i)
        out.append([(tuple(k.co), tuple(k.handle_left), tuple(k.handle_right)) for k in fc.keyframe_points])
    return out


def _wait(cond, timeout=10.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def scenario(h):
    bpy.ops.wm.open_mainfile(filepath=os.environ["ASC_UI_RIG"], load_ui=False)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    tool_id = h.addon("interaction.sculpt_tool").TOOL_ID

    scene = bpy.context.scene
    rig = bpy.data.objects[pr.RIG_NAME]
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == BONE
    rig.data.bones.active = rig.data.bones[BONE]
    scene.frame_set(1)

    area, region, rv3d = h.view3d()
    space = area.spaces.active
    space.overlay.show_bones = True
    rv3d.view_perspective = 'PERSP'
    target = Vector((0.6, -0.3, 1.5))
    eye = Vector((0.6, -4.0, 1.6))   # front view (character faces -Y)
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 2.2

    with h.override():
        bpy.ops.wm.tool_set_by_id(name=tool_id)
    yield 0.5
    yield from _wait(lambda: (t := provider.get_trail(rig, BONE)) is not None and t.complete)
    trail = provider.get_trail(rig, BONE)
    h.check("tool enables the trail of the selected control", trail is not None and trail.complete,
            trail and trail.engine)
    if trail is None:
        return
    h.check("native solver used in the UI", trail.engine == 'NATIVE', trail.engine)

    key_world = Vector(trail.point_at(KEY_FRAME))
    key_px = picking.world_to_screen(region, rv3d, key_world)
    win_co = h.to_window(key_px)

    # --- hover ------------------------------------------------------------------------------------
    h.move((win_co[0] + 40, win_co[1] + 40))
    yield 0.2
    h.move(win_co)
    yield 0.3
    hover = state.HOVER
    h.check("hover picks the key point", hover is not None and hover.frame == KEY_FRAME and hover.is_key,
            hover and (hover.bone, hover.frame, hover.is_key))
    h.screenshot("1-hover")

    # --- grab gesture -------------------------------------------------------------------------------
    keys_before = _location_keys(rig)
    target_px = (win_co[0] + 90, win_co[1] + 50)
    h.event('LEFTMOUSE', 'PRESS', win_co)
    yield 0.3
    h.check("press starts the modal gesture", state.GESTURE is not None)
    steps = 6
    for i in range(1, steps + 1):
        h.move((win_co[0] + 90 * i // steps, win_co[1] + 50 * i // steps))
        yield 0.1
    h.check("trail engine suspended during the drag", provider.is_suspended())
    h.screenshot("2-drag")
    move_ms = state.STATS.get("last_move_ms")
    h.event('LEFTMOUSE', 'RELEASE', target_px)
    yield 0.5
    h.check("release ends the gesture", state.GESTURE is None and not provider.is_suspended())
    scene.frame_set(KEY_FRAME)
    head = rig.matrix_world @ rig.pose.bones[BONE].head
    head_px = picking.world_to_screen(region, rv3d, head)
    err_px = (Vector(h.to_window(head_px)) - Vector(target_px)).length
    h.check("control follows the mouse (key point under the cursor)", err_px < 2.0, f"{err_px:.2f} px")
    h.check(f"mouse-move cost recorded: {move_ms:.2f} ms" if move_ms else "mouse-move cost recorded", move_ms is not None)
    keys_after = _location_keys(rig)
    h.check("grab changed the key values", keys_after != keys_before)
    h.check("no keys added, timing intact",
            [[k[0][0] for k in ch] for ch in keys_after] == [[k[0][0] for k in ch] for ch in keys_before])
    yield from _wait(lambda: (t := provider.get_trail(rig, BONE)) is not None and t.complete)
    new_trail = provider.get_trail(rig, BONE)
    h.check("trail recomputed after release matches the rig",
            new_trail is not None and (Vector(new_trail.point_at(KEY_FRAME)) - head).length < 1e-4)
    h.screenshot("3-after")

    # --- one undo step per gesture -------------------------------------------------------------
    h.event('Z', 'PRESS', target_px, ctrl=True)
    h.event('Z', 'RELEASE', target_px, ctrl=True)
    yield 0.8
    rig = bpy.data.objects[pr.RIG_NAME]
    h.check("one Ctrl+Z restores the keys exactly", _location_keys(rig) == keys_before)
    h.event('Z', 'PRESS', target_px, ctrl=True, shift=True)
    h.event('Z', 'RELEASE', target_px, ctrl=True, shift=True)
    yield 0.8
    rig = bpy.data.objects[pr.RIG_NAME]
    h.check("redo re-applies the gesture", _location_keys(rig) == keys_after)

    # --- Esc cancels bit for bit -----------------------------------------------------------------
    scene = bpy.context.scene  # undo replaced the data-blocks
    yield from _wait(lambda: (t := provider.get_trail(rig, BONE)) is not None and t.complete)
    scene.frame_set(1)
    trail = provider.get_trail(rig, BONE)
    win_co = h.to_window(picking.world_to_screen(region, rv3d, Vector(trail.point_at(KEY_FRAME))))
    h.move((win_co[0] + 30, win_co[1]))
    yield 0.2
    h.move(win_co)
    yield 0.3
    keys_before = _location_keys(rig)
    h.event('LEFTMOUSE', 'PRESS', win_co)
    yield 0.3
    h.move((win_co[0] - 60, win_co[1] + 30))
    yield 0.2
    h.check("drag before Esc changed the keys", _location_keys(rig) != keys_before)
    h.event('ESC', 'PRESS', (win_co[0] - 60, win_co[1] + 30))
    yield 0.3
    h.event('ESC', 'RELEASE', (win_co[0] - 60, win_co[1] + 30))
    h.event('LEFTMOUSE', 'RELEASE', (win_co[0] - 60, win_co[1] + 30))
    yield 0.3
    h.check("Esc restores the F-Curves bit for bit", _location_keys(rig) == keys_before)
    h.check("Esc leaves no gesture running", state.GESTURE is None and not provider.is_suspended())

    # --- Ctrl+LMB is the time gesture (not implemented in the spike: refused, nothing changes) ----
    h.move(win_co)
    yield 0.3
    state.MESSAGE = ""
    h.event('LEFTMOUSE', 'PRESS', win_co, ctrl=True)
    yield 0.2
    h.event('LEFTMOUSE', 'RELEASE', win_co, ctrl=True)
    yield 0.3
    h.check("Ctrl+LMB does not grab", _location_keys(rig) == keys_before and state.GESTURE is None)
    h.check("Ctrl+LMB on a trail point reaches the gesture operator (time gesture)", "tempo" in state.MESSAGE,
            repr(state.MESSAGE))
