# SPDX-License-Identifier: GPL-3.0-or-later
"""Girar (ADR 0014) on the simple skeleton: the dedicated tool, holding R with another sculpt tool, and R
pressed in the middle of a drag. Uses the local Vale on the simple skeleton (``dev.py basic-rig``)."""

import math
import os
from pathlib import Path

import bpy
from mathutils import Vector

import body_ui

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "basic_rig_test.blend"
BONE = "forearm.R"


def _rot(rig, frame):
    bpy.context.scene.frame_set(frame)
    return tuple(rig.pose.bones[BONE].rotation_quaternion)


def _arc(h, pivot, start, degrees, steps=10):
    """Mouse positions on a circle around ``pivot`` (window px) from ``start``, turning ``degrees``."""
    r = Vector(start) - Vector(pivot)
    a0 = math.atan2(r.y, r.x)
    for i in range(1, steps + 1):
        a = a0 + math.radians(degrees) * i / steps
        yield (round(pivot[0] + r.length * math.cos(a)), round(pivot[1] + r.length * math.sin(a)))


def scenario(h):
    if not ASSET.exists():
        h.check("basic rig asset present (python scripts/dev.py basic-rig)", True, "skipped")
        return
    bpy.ops.wm.open_mainfile(filepath=str(ASSET), load_ui=False)
    yield 0.5
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    scene = bpy.context.scene
    s = scene.asc_sculpt
    rig = bpy.data.objects[scene["asc_asset_rig"]]
    rig_name = rig.name
    s.interaction_mode = 'BODY'
    s.radius_linked = True
    s.radius_past = 4.0
    bpy.context.view_layer.objects.active = rig
    scene.frame_set(12)
    s.show_rig = False
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
        bpy.ops.ed.undo_push(message="scenario setup")     # undo comes back here (frame 12 included)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.2, 1.6))
    eye = Vector((0.4, -5.0, 1.8))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.6
    yield 0.5
    mesh = next(o for o in bpy.data.objects if o.type == 'MESH' and o.visible_get() and o.name == "Vale_body")
    spot = body_ui.visible_vertex(h, picking, mesh.name, BONE, prefer=("",))
    h.check("a visible vertex of the right forearm", spot is not None)
    if spot is None:
        return
    _vi, world, co, _bone = spot
    head = rig.matrix_world @ rig.pose.bones[BONE].head
    pivot = h.to_window(picking.world_to_screen(region, rv3d, head))

    # --- 1) hold R with the Membro tool -------------------------------------------------------------
    before = _rot(rig, 12)
    yield from body_ui.hover(h, co)
    h.check("hover on the forearm", state.HOVER is not None and state.HOVER.bone == BONE,
            state.HOVER and state.HOVER.bone)
    h.event('R', 'PRESS', co)
    yield 0.3
    h.check("holding R arms the turn", state.ROTATE_HELD, state.ROTATE_HELD)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.check("R + drag starts the turn", state.GESTURE is not None and state.GESTURE["kind"] == "ROTATE",
            state.GESTURE and state.GESTURE["kind"])
    last = co
    for p in _arc(h, pivot, co, 40):
        h.move(p)
        last = p
        yield 0.05
    h.screenshot("1-hold-r")
    h.event('LEFTMOUSE', 'RELEASE', last)
    h.event('R', 'RELEASE', last)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    after = _rot(rig, 12)
    h.check("the forearm turned", max(abs(a - b) for a, b in zip(before, after)) > 0.05, (before, after))
    h.check("R released: not armed any more", not state.ROTATE_HELD)
    center = h.to_window((region.width // 2, region.height // 2))
    yield from body_ui.undo(h, center)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z undoes the turn", max(abs(a - b) for a, b in zip(before, _rot(rig, 12))) < 1e-6)

    # --- 2) the Girar tool --------------------------------------------------------------------------
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.rotate")
    yield 0.3
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.check("the Girar tool starts a turn", state.GESTURE is not None and state.GESTURE["kind"] == "ROTATE",
            state.GESTURE and state.GESTURE["kind"])
    for p in _arc(h, pivot, co, -35):
        h.move(p)
        last = p
        yield 0.05
    h.screenshot("2-tool")
    h.event('LEFTMOUSE', 'RELEASE', last)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    h.check("the Girar tool turned the forearm", max(abs(a - b) for a, b in zip(before, _rot(rig, 12))) > 0.05)
    yield from body_ui.undo(h, center)

    # --- 3) R pressed in the middle of a Membro drag --------------------------------------------------
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
    yield 0.3
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.move((co[0] + 15, co[1] + 10))
    yield 0.1
    h.check("a Membro drag runs", state.GESTURE is not None and state.GESTURE["kind"] == "CHAIN",
            state.GESTURE and state.GESTURE["kind"])
    h.event('R', 'PRESS', (co[0] + 15, co[1] + 10))
    yield 0.2
    h.check("R during the drag turns it into a turn", state.GESTURE is not None and state.GESTURE["kind"] == "ROTATE",
            state.GESTURE and state.GESTURE["kind"])
    for p in _arc(h, pivot, (co[0] + 15, co[1] + 10), 30):
        h.move(p)
        last = p
        yield 0.05
    label = state.GESTURE and state.GESTURE.get("label")
    # the grabbed spot is a few px from the elbow: the angle is sensitive to the pivot, so check the sense
    h.check("the turn follows the mouse around the joint (counter-clockwise ⇒ positive)",
            label is not None and label.startswith("+") and abs(float(label[:-1])) >= 5.0, label)
    h.event('LEFTMOUSE', 'RELEASE', last)
    h.event('R', 'RELEASE', last)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    h.check("the turn was written", max(abs(a - b) for a, b in zip(before, _rot(rig, 12))) > 0.05)
    yield from body_ui.undo(h, center)
    s = bpy.context.scene.asc_sculpt
    s.show_rig = True
