# SPDX-License-Identifier: GPL-3.0-or-later
"""BODY mode (docs/design/sculpt-ux.md "Agarrar o corpo"): with the rig hidden, hovering the character's mesh
highlights the part and picks its control; dragging sculpts the pose at the current frame. FK forearm -> ephemeral
chain (the grabbed surface point follows the cursor); IK hand -> grab/arc of the IK control. Ctrl+Z / Esc restore."""

import bpy
import numpy as np
from mathutils import Vector

import body_ui
import deform_check


def _hand_head(rig, bone):
    return (rig.matrix_world @ rig.pose.bones[bone].head).copy()


def scenario(h):
    ctx = body_ui.open_scene(h, 16, 12)
    yield 0.5
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    rig_name, mesh_name, f0 = ctx["rig"], ctx["mesh"], ctx["frame"]
    fk, ik = ctx["fk"], ctx["ik"]
    scene = bpy.context.scene
    s = scene.asc_sculpt
    s.radius_linked = False
    s.radius_past, s.radius_future = 4.0, 4.0
    s.interaction_mode = 'BODY'
    s.key_mode = 'DENSE'      # this scenario checks dense keys (ADR 0011)
    s.show_rig = False
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
    yield 0.6
    area, region, rv3d = h.view3d()
    h.check("Ligar Rigify OFF hides the bones in the 3D view", area.spaces.active.overlay.show_bones is False,
            area.spaces.active.overlay.show_bones)
    h.check("tool is Membro", body_ui.active_tool(h) == "animation_sculptor.sculpt", body_ui.active_tool(h))

    rig = bpy.data.objects[rig_name]
    window_frames = list(range(f0 - 8, f0 + 9, 4))
    far = [f for f in (f0 - 12, f0 + 12, 1, 40) if f != f0 and 1 <= f]
    before_action = body_ui.dump(rig)
    mesh = bpy.data.objects[mesh_name]
    pts_before = {f: deform_check.points(mesh, f) for f in far}
    scene.frame_set(f0)

    # --- left (FK) forearm mesh -------------------------------------------------------------------------------
    found = body_ui.visible_vertex(h, picking, mesh_name, f"DEF-forearm.{fk}")
    h.check("found a visible vertex on the forearm mesh", found is not None, found and found[3])
    if found is None:
        return
    vi, world, co, deform_bone = found
    yield from body_ui.hover(h, co)
    hit = state.HOVER
    h.check("HOVER is a body hit on the forearm (CHAIN, forearm_fk)",
            hit is not None and hit.on_body and hit.deform.startswith(f"DEF-forearm.{fk}") and
            hit.bone == f"forearm_fk.{fk}" and hit.kind == "CHAIN",
            hit and (hit.on_body, hit.deform, hit.bone, hit.kind, hit.mesh))
    h.check("the hit mesh is the character's body", hit is not None and hit.mesh == mesh_name, hit and hit.mesh)
    h.screenshot("1-hover-left-forearm")

    end = (co[0] + 40, co[1] - 10)       # 40 px right, a little up
    yield from body_ui.drag(h, co, end, release=False)
    g = state.GESTURE
    h.check("the drag runs an ephemeral chain gesture", g is not None and g["kind"] == "CHAIN", g and g["kind"])
    h.screenshot("2-dragging-forearm")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.6
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    scene.frame_set(f0)
    px = body_ui.vertex_window_px(h, picking, mesh_name, vi, f0)
    err = (px - Vector(end)).length if px is not None else 1e9
    h.check("the grabbed surface vertex ends under the cursor", err < 2.0, f"{err:.2f} px")
    h.screenshot("3-after-drag-forearm")
    after = {f: deform_check.points(bpy.data.objects[mesh_name], f) for f in far}
    moved = deform_check.max_change(pts_before, after, far)
    h.check("the mesh outside the time window is unchanged", moved < 1e-5, f"{moved:.2e} m")
    h.check("the Action changed", body_ui.dump(rig) != before_action)
    yield from body_ui.undo(h, end)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z restores the Action exactly", body_ui.dump(rig) == before_action)
    s = bpy.context.scene.asc_sculpt
    s.radius_linked, s.radius_past, s.radius_future = False, 4.0, 4.0

    # --- Esc during a second drag ------------------------------------------------------------------------------
    scene = bpy.context.scene
    scene.frame_set(f0)
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    for i in range(1, 5):
        h.move((co[0] - 10 * i, co[1] + 8 * i))
        yield 0.05
    h.event('ESC', 'PRESS', (co[0] - 40, co[1] + 32))
    h.event('ESC', 'RELEASE', (co[0] - 40, co[1] + 32))
    yield 0.4
    h.event('LEFTMOUSE', 'RELEASE', (co[0] - 40, co[1] + 32))
    yield 0.4
    rig = bpy.data.objects[rig_name]
    h.check("Esc during a drag restores the Action bit for bit", body_ui.dump(rig) == before_action)
    h.check("no gesture left running", state.GESTURE is None, state.GESTURE and state.GESTURE["kind"])

    # --- right (IK) hand mesh ----------------------------------------------------------------------------------
    for label, frame in (("grab at a key", f0), ("arc at an in-between", 13 if ctx["vale"] else 7)):
        scene = bpy.context.scene
        scene.frame_set(frame)
        found = body_ui.visible_vertex(h, picking, mesh_name, f"DEF-hand.{ik}", prefer=("",))
        if found is None:
            found = body_ui.visible_vertex(h, picking, mesh_name, f"DEF-forearm.{ik}")
        h.check(f"[{label}] found a visible vertex on the IK hand/forearm mesh", found is not None)
        if found is None:
            continue
        vi, world, co, deform_bone = found
        rig = bpy.data.objects[rig_name]
        dump0 = body_ui.dump(rig)
        head0 = _hand_head(rig, f"hand_ik.{ik}")
        _a, region, rv3d = h.view3d()
        scr0 = Vector(picking.world_to_screen(region, rv3d, head0))
        yield from body_ui.hover(h, co)
        hit = state.HOVER
        h.check(f"[{label}] HOVER is the IK control", hit is not None and hit.on_body and hit.kind == "IK" and
                hit.bone == f"hand_ik.{ik}", hit and (hit.on_body, hit.deform, hit.bone, hit.kind, hit.mesh))
        h.screenshot(f"4-hover-ik-hand-f{frame}")
        end = (co[0] + 40, co[1] - 30)
        yield from body_ui.drag(h, co, end)
        h.screenshot(f"5-after-ik-drag-f{frame}")
        rig = bpy.data.objects[rig_name]
        bpy.context.scene.frame_set(frame)
        head1 = _hand_head(rig, f"hand_ik.{ik}")
        h.check(f"[{label}] the IK hand moved", (head1 - head0).length > 0.02, f"{(head1 - head0).length:.3f} m")
        scr1 = Vector(picking.world_to_screen(region, rv3d, head1))
        want = Vector((end[0] - co[0], end[1] - co[1]))      # window and region y both point up
        got = scr1 - scr0
        err = (got - want).length
        # the grab point is on the forearm/hand surface, not on the control: the control follows the drag delta
        h.check(f"[{label}] the IK control follows the cursor delta", err < 12.0,
                f"moved {tuple(round(v, 1) for v in got)} px, drag {tuple(want)} px, off {err:.1f} px")
        yield from body_ui.undo(h, end)
        rig = bpy.data.objects[rig_name]
        h.check(f"[{label}] one Ctrl+Z restores the Action", body_ui.dump(rig) == dump0)
        s = bpy.context.scene.asc_sculpt
        s.radius_linked, s.radius_past, s.radius_future = False, 4.0, 4.0
