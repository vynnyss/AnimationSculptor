# SPDX-License-Identifier: GPL-3.0-or-later
"""Smooth tool (docs/design/sculpt-ux.md "Smooth"): holding the button over a part and moving back and forth
applies passes of temporal smoothing inside the ruler's window; nothing outside changes; one undo step;
a click without moving writes nothing."""

import bpy
import numpy as np

import body_ui
import deform_check


def _world_path(rig_name, bone, frames):
    scene = bpy.context.scene
    out = []
    for f in frames:
        scene.frame_set(f)
        rig = bpy.data.objects[rig_name]
        out.append(np.array(rig.matrix_world @ rig.pose.bones[bone].head))
    return np.asarray(out)


def _roughness(path):
    return float(np.linalg.norm(np.diff(path, n=2, axis=0), axis=1).sum())


def scenario(h):
    ctx = body_ui.open_scene(h, 18, 12)
    yield 0.5
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    rig_name, mesh_name, f0 = ctx["rig"], ctx["mesh"], ctx["frame"]
    ik = ctx["ik"]
    bone = f"hand_ik.{ik}"
    scene = bpy.context.scene
    s = scene.asc_sculpt
    s.radius_linked = False
    s.radius_past, s.radius_future = 6.0, 6.0
    s.interaction_mode = 'BODY'
    s.show_rig = False
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.smooth")
    yield 0.6
    h.check("tool is Smooth", body_ui.active_tool(h) == "animation_sculptor.smooth", body_ui.active_tool(h))
    scene.frame_set(f0)
    all_frames = list(range(1, 41)) if ctx["vale"] else list(range(1, 25))
    inside = list(range(f0 - 6, f0 + 7))
    rig = bpy.data.objects[rig_name]
    dump0 = body_ui.dump(rig)
    values0 = body_ui.curve_values(rig, bone, all_frames)
    path0 = _world_path(rig_name, bone, inside)
    scene.frame_set(f0)

    found = body_ui.visible_vertex(h, picking, mesh_name, f"DEF-hand.{ik}", prefer=("",))
    if found is None:
        found = body_ui.visible_vertex(h, picking, mesh_name, f"DEF-forearm.{ik}")
    h.check("found a visible vertex on the IK hand mesh", found is not None)
    if found is None:
        return
    vi, world, co, deform_bone = found
    yield from body_ui.hover(h, co)
    hit = state.HOVER
    h.check("HOVER is the IK hand (body)", hit is not None and hit.on_body and hit.bone == bone,
            hit and (hit.on_body, hit.deform, hit.bone, hit.kind))
    h.screenshot("1-hover-hand")

    # --- a click without moving writes nothing ------------------------------------------------------------------
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.event('LEFTMOUSE', 'RELEASE', co)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    h.check("a click without moving writes nothing", body_ui.dump(rig) == dump0)
    h.check("no gesture left running after the click", state.GESTURE is None)

    # --- the stroke: ~120 px back and forth ---------------------------------------------------------------------
    scene = bpy.context.scene
    scene.frame_set(f0)
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    g = state.GESTURE
    h.check("the press starts a Smooth gesture", g is not None and g["kind"] == "SMOOTH", g and g["kind"])
    labels = []
    xs = [30, 60, 30, 0]       # 4 moves of 30 px = 120 px of back-and-forth travel (~15 passes at 8 px each)
    for x in xs:
        h.move((co[0] + x, co[1]))
        yield 0.08
        if state.GESTURE is not None:
            labels.append(state.GESTURE.get("label", ""))
    h.screenshot("2-smoothing")
    h.event('LEFTMOUSE', 'RELEASE', (co[0], co[1]))
    yield 0.6
    passes = max((int(l.split("×")[1]) for l in labels if "×" in l), default=0)
    h.check("passes > 0 happened", passes > 0, f"max passes {passes}")
    rig = bpy.data.objects[rig_name]
    values1 = body_ui.curve_values(rig, bone, all_frames)
    changed_in = max(float(np.abs(values1[f] - values0[f]).max()) for f in inside)
    outside = [f for f in all_frames if f < f0 - 7 or f > f0 + 7]
    changed_out = max(float(np.abs(values1[f] - values0[f]).max()) for f in outside)
    h.check("keys of the hand control changed inside the window", changed_in > 1e-6, f"{changed_in:.2e}")
    h.check("nothing changed outside the window", changed_out < 1e-6, f"{changed_out:.2e}")
    path1 = _world_path(rig_name, bone, inside)
    r0, r1 = _roughness(path0), _roughness(path1)
    h.check("the hand's world path roughness decreased or stayed equal", r1 <= r0 + 1e-9, f"{r0:.5f} -> {r1:.5f}")
    bpy.context.scene.frame_set(f0)
    h.screenshot("3-after-smooth")
    yield from body_ui.undo(h, co)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z undoes the whole stroke", body_ui.dump(rig) == dump0)
    h.check("no gesture left running", state.GESTURE is None)
