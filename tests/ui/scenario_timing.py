# SPDX-License-Identifier: GPL-3.0-or-later
"""Ctrl+LMB timing gestures: retime of a pose key and spacing of a segment, with cancel and undo."""

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


def _keys(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    return {(fc.data_path, fc.array_index): [round(k.co[0], 3) for k in fc.keyframe_points] for fc in cb.fcurves}


def scenario(h):  # noqa: C901
    if ASSET.exists():
        path, bone, other, key_frame, mid_frame = str(ASSET), "hand_ik.R", "torso", 16, 13
    else:
        path, bone, other, key_frame, mid_frame = os.environ["ASC_UI_RIG"], "hand_ik.L", "torso", 12, 18
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    tool_id = h.addon("interaction.sculpt_tool").TOOL_ID
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bone in ob.pose.bones and not ob.hide_viewport)
    rig_name = rig.name
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
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
    ready = lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete  # noqa: E731
    yield from _wait(ready)

    def win(frame):
        return h.to_window(picking.world_to_screen(region, rv3d, Vector(provider.get_trail(rig, bone).point_at(frame))))

    def hover(co):
        h.move((co[0] + 25, co[1] + 25))
        yield 0.2
        h.move(co)
        yield 0.3

    # --- retime: Ctrl+drag the key point forward along the trail ---------------------------------
    keys0 = _keys(rig)
    co = win(key_frame)
    toward = Vector(win(key_frame + 1)) - Vector(co)
    toward = toward.normalized() if toward.length > 1e-3 else Vector((1.0, 0.0))
    yield from hover(co)
    h.event('LEFTMOUSE', 'PRESS', co, ctrl=True)
    yield 0.3
    h.check("Ctrl+LMB on a key starts a retime", state.GESTURE is not None and state.GESTURE["kind"] == "RETIME")
    end = co
    for i in range(1, 8):
        end = (int(co[0] + toward.x * 12 * i), int(co[1] + toward.y * 12 * i))
        h.move(end, ctrl=True)
        yield 0.1
    label = state.GESTURE and state.GESTURE.get("label")
    h.screenshot("1-retime")
    h.event('LEFTMOUSE', 'RELEASE', end, ctrl=True)
    yield 0.5
    keys1 = _keys(rig)
    path_hand = f'pose.bones["{bone}"].location'
    path_other = f'pose.bones["{other}"].location'
    new_hand = [f for f in keys1[(path_hand, 0)] if f not in keys0[(path_hand, 0)]]
    h.check("the dragged key moved later in time", len(new_hand) == 1 and new_hand[0] > key_frame, (label, new_hand))
    h.check("the whole pose moved (other control too)",
            new_hand and new_hand[0] in keys1[(path_other, 0)] and key_frame not in keys1[(path_other, 0)])
    h.check("no keys created", all(len(keys1[c]) == len(k) for c, k in keys0.items()))
    h.event('Z', 'PRESS', end, ctrl=True)
    h.event('Z', 'RELEASE', end, ctrl=True)
    yield 0.8
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    h.check("one Ctrl+Z undoes the retime", _keys(rig) == keys0)

    # --- spacing: Ctrl+drag an in-between sideways ---------------------------------------------------
    # (the selection was made from Python without an undo step, so the undo dropped it: select again)
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
    rig.data.bones.active = rig.data.bones[bone]
    yield 0.3
    yield from _wait(ready)
    scene.frame_set(1)
    yield 0.3
    trail = provider.get_trail(rig, bone)
    dense = np.array([trail.point_at(f) for f in trail.frames if trail.point_at(f) is not None], dtype=np.float64)
    co = win(mid_frame)
    yield from hover(co)
    h.event('LEFTMOUSE', 'PRESS', co, ctrl=True)
    yield 0.3
    h.check("Ctrl+LMB on an in-between starts spacing", state.GESTURE is not None and state.GESTURE["kind"] == "SPACING")
    for i in range(1, 8):
        h.move((co[0] + 15 * i, co[1]), ctrl=True)
        yield 0.1
    preview = state.GESTURE and state.GESTURE.get("preview")
    h.check("spacing preview dots coloured by speed", bool(preview) and state.GESTURE.get("speed"))
    h.screenshot("2-spacing")
    h.event('LEFTMOUSE', 'RELEASE', (co[0] + 105, co[1]), ctrl=True)
    yield 0.5
    h.check("spacing adds or moves no key", _keys(rig) == keys0)
    scene.frame_set(mid_frame)
    p = np.array(tuple(rig.matrix_world @ rig.pose.bones[bone].head))
    d = np.linalg.norm(dense - p, axis=1).min()
    moved = np.linalg.norm(np.array(trail.point_at(mid_frame)) - p)
    h.check("the in-between slid along the old path", moved > 1e-3, f"moved {moved:.4f} m, nearest old point {d:.4f} m")
    yield from _wait(ready)
    h.screenshot("3-after-spacing")

    # --- Esc cancels a timing gesture bit for bit ----------------------------------------------------
    keys2 = _keys(rig)
    scene.frame_set(1)
    co = win(key_frame)
    yield from hover(co)
    h.event('LEFTMOUSE', 'PRESS', co, ctrl=True)
    yield 0.3
    h.move((co[0] + 60, co[1] + 20), ctrl=True)
    yield 0.2
    h.event('ESC', 'PRESS', (co[0] + 60, co[1] + 20))
    h.event('ESC', 'RELEASE', (co[0] + 60, co[1] + 20))
    h.event('LEFTMOUSE', 'RELEASE', (co[0] + 60, co[1] + 20))
    yield 0.4
    h.check("Esc restores the timing bit for bit", _keys(rig) == keys2 and state.GESTURE is None)
