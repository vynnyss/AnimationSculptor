# SPDX-License-Identifier: GPL-3.0-or-later
"""Toolbar tools and modes (docs/design/sculpt-ux.md): Shift+Alt+K re-activates the last Animation Sculptor
tool; the TRAIL mode turns the trails on; the Corpo tool grabs the chest mesh and leans the torso, feet stay."""

import bpy
from mathutils import Vector

import body_ui

CORPO = "animation_sculptor.body"


def _feet(rig):
    return {side: (rig.matrix_world @ rig.pose.bones[f"foot_ik.{side}"].head).copy() for side in ("L", "R")}


def _shift_alt_k(h, co):
    h.event('K', 'PRESS', co, shift=True, alt=True)
    h.event('K', 'RELEASE', co, shift=True, alt=True)


def scenario(h):
    ctx = body_ui.open_scene(h, 16, 12)
    yield 0.5
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    provider = h.addon("trails.provider")
    state.LAST_TOOL = None        # fresh session: earlier scenarios may have used another tool
    rig_name, mesh_name, f0 = ctx["rig"], ctx["mesh"], ctx["frame"]
    scene = bpy.context.scene
    s = scene.asc_sculpt
    s.radius_linked = False
    s.radius_past, s.radius_future = 4.0, 4.0
    s.show_rig = False
    area, region, rv3d = h.view3d()
    center = h.to_window((region.width // 2, region.height // 2))
    h.move(center)
    yield 0.2

    # --- Shift+Alt+K: literal case, tool activated through tool_set_by_id only ------------------------------
    with h.override():
        bpy.ops.wm.tool_set_by_id(name=CORPO)
    yield 0.3
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    yield 0.3
    h.check("a non-Animation-Sculptor tool is active", body_ui.active_tool(h) == "builtin.select_box",
            body_ui.active_tool(h))
    _shift_alt_k(h, center)
    yield 0.5
    h.check("Shift+Alt+K after tool_set_by_id(Corpo) activates Corpo (last used tool)",
            body_ui.active_tool(h) == CORPO, f"active={body_ui.active_tool(h)} LAST_TOOL={state.LAST_TOOL}")

    # --- mode TRAIL turns the trails on ------------------------------------------------------------------------
    scene = bpy.context.scene
    provider.set_enabled(scene, False)
    s = scene.asc_sculpt
    s.interaction_mode = 'BODY'
    yield 0.2
    h.check("trails are off in BODY mode (precondition)", not provider.is_enabled(scene))
    s.interaction_mode = 'TRAIL'
    yield 0.3
    h.check("switching interaction_mode to TRAIL turns the trails on", provider.is_enabled(bpy.context.scene))
    bpy.context.scene.asc_sculpt.interaction_mode = 'BODY'
    yield 0.3
    h.check("back to BODY mode", bpy.context.scene.asc_sculpt.interaction_mode == 'BODY')

    # --- Corpo tool: drag the chest mesh ------------------------------------------------------------------------
    with h.override():
        bpy.ops.wm.tool_set_by_id(name=CORPO)
    yield 0.6
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    scene.frame_set(f0)
    dump0 = body_ui.dump(rig)
    feet0 = _feet(rig)
    chest0 = (rig.matrix_world @ rig.pose.bones["chest"].tail).copy()
    found = body_ui.visible_vertex(h, picking, mesh_name, "DEF-spine", prefer=(".002", ".003"))
    h.check("found a visible vertex on the chest mesh", found is not None, found and found[3])
    if found is None:
        return
    vi, world, co, deform_bone = found
    yield from body_ui.hover(h, co)
    hit = state.HOVER
    h.check("HOVER is a body hit on the chest (CHAIN, control chest)",
            hit is not None and hit.on_body and hit.bone == "chest" and hit.kind == "CHAIN",
            hit and (hit.on_body, hit.deform, hit.bone, hit.kind, hit.mesh))
    h.screenshot("1-hover-chest")
    end = (co[0] + 45, co[1] - 5)
    yield from body_ui.drag(h, co, end, release=False)
    g = state.GESTURE
    h.check("the drag starts the Corpo chain gesture", g is not None and g["kind"] == "CHAIN", g and g["kind"])
    h.screenshot("2-leaning")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.6
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    scene.frame_set(f0)
    chest1 = (rig.matrix_world @ rig.pose.bones["chest"].tail).copy()
    h.check("the chest moved (torso leans)", (chest1 - chest0).length > 0.02, f"{(chest1 - chest0).length:.3f} m")
    moved = max((_feet(rig)[side] - feet0[side]).length for side in ("L", "R"))
    h.check("the IK feet stay put", moved < 1e-5, f"{moved:.2e} m")
    px = body_ui.vertex_window_px(h, picking, mesh_name, vi, f0)
    err = (px - Vector(end)).length if px is not None else 1e9
    h.check("the grabbed chest vertex ends near the cursor", err < 10.0, f"{err:.2f} px")
    h.screenshot("3-after-lean")
    yield from body_ui.undo(h, end)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z restores the Action", body_ui.dump(rig) == dump0)
    h.check("the gesture set LAST_TOOL to Corpo", state.LAST_TOOL == CORPO, state.LAST_TOOL)

    # --- Shift+Alt+K again, now after a real gesture ------------------------------------------------------------
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    yield 0.3
    center = h.to_window((region.width // 2, region.height // 2))
    h.move(center)
    yield 0.2
    _shift_alt_k(h, center)
    yield 0.5
    h.check("Shift+Alt+K after a Corpo gesture activates Corpo", body_ui.active_tool(h) == CORPO, body_ui.active_tool(h))
