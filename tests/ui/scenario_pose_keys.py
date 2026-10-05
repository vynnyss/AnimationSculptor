# SPDX-License-Identifier: GPL-3.0-or-later
"""Pose to pose (ADR 0015) on the simple skeleton, from zero: I records the whole pose (no bone selected),
a body drag at a frame without a key makes one pose there (no dense keys), and the neighbouring poses in the
time window follow only by "Influência nas poses"."""

import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

import body_ui

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "basic_rig_test.blend"
BONE = "forearm.R"


def _pose_frames(h, rig):
    return h.addon("interaction.ephemeral_edit").pose_frames(rig)


def _tail(rig, frame):
    bpy.context.scene.frame_set(frame)
    return np.array(rig.matrix_world @ rig.pose.bones[BONE].tail)


def _frame(h, f):
    with h.override():
        bpy.context.scene.frame_set(f)
    return (yield 0.2)


def scenario(h):
    if not ASSET.exists():
        h.check("basic rig asset present (python scripts/dev.py basic-rig)", True, "skipped")
        return
    bpy.ops.wm.open_mainfile(filepath=str(ASSET), load_ui=False)
    yield 0.5
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    scene = bpy.context.scene
    rig = bpy.data.objects[scene["asc_asset_rig"]]
    rig_name = rig.name
    rig.animation_data.action = None                     # start from zero
    s = scene.asc_sculpt
    s.interaction_mode = 'BODY'
    s.key_mode = 'POSE'
    s.pose_influence = 0.25
    s.radius_linked = True
    s.radius_past = 12.0
    s.show_rig = False
    bpy.context.view_layer.objects.active = rig
    for pb in rig.pose.bones:
        pb.select = False
    scene.frame_set(1)
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
        bpy.ops.ed.undo_push(message="scenario setup")
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.2, 1.6))
    eye = Vector((0.4, -5.0, 1.8))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.6
    yield 0.5
    center = h.to_window((region.width // 2, region.height // 2))

    # --- I at 1 and 24: two poses of the whole character, nothing selected -----------------------------
    h.event('I', 'PRESS', center)
    h.event('I', 'RELEASE', center)
    yield 0.3
    scene = bpy.context.scene
    scene.frame_set(24)
    yield 0.2
    h.event('I', 'PRESS', center)
    h.event('I', 'RELEASE', center)
    yield 0.3
    rig = bpy.data.objects[rig_name]
    h.check("I records the whole pose (no bone selected)", _pose_frames(h, rig) == [1, 24], _pose_frames(h, rig))

    # --- a drag at 12 (no key there) makes one pose; 1 and 24 follow only a little -------------------
    before = {f: _tail(rig, f) for f in (1, 24)}
    bpy.context.scene.frame_set(12)
    yield 0.3
    spot = body_ui.visible_vertex(h, picking, "Vale_body", BONE, prefer=("",))
    h.check("a visible vertex of the right forearm", spot is not None)
    if spot is None:
        return
    co = spot[2]
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    h.check("the drag runs", state.GESTURE is not None and state.GESTURE["kind"] == "CHAIN",
            state.GESTURE and state.GESTURE["kind"])
    end = (co[0] + 60, co[1] + 40)
    for i in range(1, 9):
        h.move((co[0] + 60 * i // 8, co[1] + 40 * i // 8))
        yield 0.05
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    h.check("the drag made one pose at 12 (no dense keys)", _pose_frames(h, rig) == [1, 12, 24],
            _pose_frames(h, rig))
    moved = {f: float(np.linalg.norm(_tail(rig, f) - before[f])) for f in (1, 24)}
    h.check("the neighbouring poses follow only a little (influence 25%)",
            all(m < 0.05 for m in moved.values()), moved)
    bpy.context.scene.frame_set(12)
    yield 0.3
    h.screenshot("1-pose-at-12")
    yield from body_ui.undo(h, center)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z removes the pose at 12", _pose_frames(h, rig) == [1, 24], _pose_frames(h, rig))
