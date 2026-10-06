# SPDX-License-Identifier: GPL-3.0-or-later
"""Body and trail tools are separated by the mode (decision of 2026-10-05) on the simple skeleton: in the
Corpo mode the trails are only shown — the body under a trail point is what gets picked; in the Trail mode
the trail point is picked and dragged (one Ctrl+Z restores the Action); back in Corpo the body is picked."""

import os
from pathlib import Path

import bpy
from mathutils import Vector

import body_ui

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "basic_rig_test.blend"
BONE = "hand.R"
FRAME = 12


def _wait_trail(provider, rig_name, bone, timeout=10.0):
    import time
    t_end = time.time() + timeout
    while time.time() < t_end:
        t = provider.get_trail(bpy.data.objects[rig_name], bone)
        if t is not None and t.complete:
            return t
        yield 0.1
    return None


def _values(rig_name):
    """The whole Action (every channel: the hand is moved through its limb's chain) as keys + handles."""
    return body_ui.dump(bpy.data.objects[rig_name])


def _diff(a, b):
    keys = set(a) | set(b)
    return sum(1 for k in keys if a.get(k) != b.get(k))


def _head(rig_name):
    bpy.context.scene.frame_set(FRAME)
    rig = bpy.data.objects[rig_name]
    return tuple(rig.matrix_world @ rig.pose.bones[BONE].head)


def scenario(h):
    if not ASSET.exists():
        h.check("basic rig asset present (python scripts/dev.py basic-rig)", True, "skipped")
        return
    bpy.ops.wm.open_mainfile(filepath=str(ASSET), load_ui=False)
    yield 0.5
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    provider = h.addon("trails.provider")
    scene = bpy.context.scene
    s = scene.asc_sculpt
    rig = bpy.data.objects[scene["asc_asset_rig"]]
    rig_name = rig.name
    s.interaction_mode = 'BODY'
    s.radius_linked = True
    s.radius_past = 0.0
    s.radius_future = 0.0
    s.show_rig = False
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
    for pb in rig.pose.bones:
        pb.select = pb.name == BONE
    rig.data.bones.active = rig.data.bones[BONE]
    provider.set_paths(scene, True)
    scene.frame_set(FRAME)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.2, 1.6))
    eye = Vector((0.4, -5.0, 1.8))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.6
    yield 0.5
    h.check("trails are on", scene.asc_trails.enabled and scene.asc_trails.path_show)
    trail = yield from _wait_trail(provider, rig_name, BONE)
    h.check(f"the {BONE} trail is computed", trail is not None)
    if trail is None:
        h.check("trail targets", False, provider.targets())
        return
    with h.override():
        bpy.ops.ed.undo_push(message="scenario setup")     # AFTER frame_set / selection
    yield 0.3
    h.screenshot("0-setup")
    center = h.to_window((region.width // 2, region.height // 2))

    # --- 1) hover a trail point ----------------------------------------------------------------------
    trail = provider.get_trail(rig, BONE)
    pt = trail.point_at(FRAME)
    px = picking.world_to_screen(region, rv3d, Vector(pt))
    h.check("the trail point is on screen", px is not None and 20 < px.x < region.width - 20
            and 20 < px.y < region.height - 20, px)
    co = h.to_window(px)
    yield from body_ui.hover(h, co)
    hov = state.HOVER
    h.check("Corpo mode: a trail point is never picked (the body or nothing)",
            hov is None or hov.on_body, hov and (hov.bone, hov.frame, hov.on_body, hov.on_bone))
    h.screenshot("1-hover-trail-body-mode")
    bpy.context.scene.asc_sculpt.interaction_mode = 'TRAIL'
    yield 0.3
    trail = yield from _wait_trail(provider, rig_name, BONE)
    yield from body_ui.hover(h, (co[0] + 6, co[1]))
    yield from body_ui.hover(h, co)
    hov = state.HOVER
    h.check("Trail mode: the trail point is picked", hov is not None and not hov.on_body and hov.bone == BONE
            and hov.frame == FRAME, hov and (hov.bone, hov.frame, hov.on_body, hov.on_bone))
    h.screenshot("1b-hover-trail-trail-mode")

    # --- 2) drag it ----------------------------------------------------------------------------------
    vals0, head0 = _values(rig_name), _head(rig_name)
    h.check("the Action has curves", len(vals0) > 0, len(vals0))
    end = (co[0] + 40, co[1])
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.check("a trail gesture started", state.GESTURE is not None, state.GESTURE and state.GESTURE["kind"])
    for i in range(1, 9):
        h.move((co[0] + 40 * i // 8, co[1]))
        yield 0.08
    h.screenshot("2-drag")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.6
    vals1, head1 = _values(rig_name), _head(rig_name)
    dval = _diff(vals0, vals1)
    dpos = (Vector(head1) - Vector(head0)).length
    h.check("the hand moved at that frame (channels changed + position)", dval > 0 and dpos > 1e-3, (dval, dpos))
    yield from body_ui.undo(h, center)
    vals2, head2 = _values(rig_name), _head(rig_name)
    h.check("one Ctrl+Z restores the Action bit-for-bit",
            vals2 == vals0, _diff(vals0, vals2))
    h.check("... and the hand position", tuple(head2) == tuple(head0), (head0, head2))

    # --- 3) back in Corpo: the body is picked ---------------------------------------------------------
    bpy.context.scene.asc_sculpt.interaction_mode = 'BODY'
    yield 0.3
    rig = bpy.data.objects[rig_name]
    mesh = next(o for o in bpy.data.objects if o.type == 'MESH' and o.visible_get() and o.name == "Vale_body")
    trail = provider.get_trail(rig, BONE)
    trail_px = [Vector(h.to_window(p)) for p in
                (picking.world_to_screen(region, rv3d, Vector(q)) for q in trail.points) if p is not None]
    spot = None
    for prefix in ("thigh.L", "forearm.L", "upper_arm.L", "spine", "thigh.R"):
        cand = body_ui.visible_vertex(h, picking, mesh.name, prefix, prefer=("",))
        if cand is not None and min((Vector(cand[2]) - t).length for t in trail_px) > 80:
            spot = cand
            break
    h.check("a body spot far from every trail", spot is not None)
    if spot is None:
        return
    _vi, _w, bco, bbone = spot
    yield from body_ui.hover(h, bco)
    hov = state.HOVER
    h.check("hover picks the body", hov is not None and hov.on_body, hov and (hov.bone, hov.on_body))
    h.screenshot("3-hover-body")
    bpy.context.scene.asc_sculpt.show_rig = True
