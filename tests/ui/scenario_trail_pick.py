# SPDX-License-Identifier: GPL-3.0-or-later
"""Trail mode with the skeleton hidden and no bone selected (maintainer's report, 2026-10-05): a click on a
body part only picks the part whose trail is shown (no edit, no undo step); then the trail is dragged."""

import os
from pathlib import Path

import bpy
from mathutils import Vector

import body_ui

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "basic_rig_test.blend"
BONE = "forearm.R"


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
    rig = bpy.data.objects[scene["asc_asset_rig"]]
    rig_name = rig.name
    s = scene.asc_sculpt
    s.interaction_mode = 'TRAIL'
    s.show_rig = False
    s.show_trails = True
    bpy.context.view_layer.objects.active = rig
    for pb in rig.pose.bones:
        pb.select = False
    scene.frame_set(12)
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
    yield 0.8
    h.check("no bone selected: no bone trail to edit", not [k for k in provider.targets() if k[1]],
            provider.targets())
    dump0 = body_ui.dump(rig)

    # --- a click on the forearm picks its trail ------------------------------------------------------
    spot = body_ui.visible_vertex(h, picking, "Vale_body", BONE, prefer=("",))
    h.check("a visible vertex of the forearm", spot is not None)
    if spot is None:
        return
    co = spot[2]
    yield from body_ui.hover(h, co)
    hov = state.HOVER
    h.check("Trail mode: hovering the body shows which part", hov is not None and hov.on_body and hov.bone == BONE,
            hov and (hov.bone, hov.on_body))
    h.event('LEFTMOUSE', 'PRESS', co)
    h.event('LEFTMOUSE', 'RELEASE', co)
    yield 0.3
    trail = None
    for _ in range(40):
        trail = provider.get_trail(bpy.data.objects[rig_name], BONE)
        if trail is not None:
            break
        yield 0.1
    rig = bpy.data.objects[rig_name]
    h.check("the click shows the forearm's trail", trail is not None, provider.targets())
    h.check("the click edits nothing", body_ui.dump(rig) == dump0 and state.GESTURE is None)
    h.screenshot("1-trail-picked")
    if trail is None:
        return

    # --- the trail point is dragged --------------------------------------------------------------------
    px = picking.world_to_screen(region, rv3d, Vector(trail.point_at(12)))
    pco = h.to_window(px)
    yield from body_ui.hover(h, (pco[0] + 5, pco[1]))
    yield from body_ui.hover(h, pco)
    hov = state.HOVER
    h.check("the trail point is picked", hov is not None and not hov.on_body and hov.bone == BONE,
            hov and (hov.bone, hov.on_body))
    h.event('LEFTMOUSE', 'PRESS', pco)
    yield 0.2
    for i in range(1, 9):
        h.move((pco[0] + 5 * i, pco[1] + 3 * i))
        yield 0.05
    h.event('LEFTMOUSE', 'RELEASE', (pco[0] + 40, pco[1] + 24))
    yield 0.5
    rig = bpy.data.objects[rig_name]
    h.check("dragging the trail edited the animation", body_ui.dump(rig) != dump0)
    h.screenshot("2-trail-dragged")
    center = h.to_window((region.width // 2, region.height // 2))
    yield from body_ui.undo(h, center)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z undoes the trail drag", body_ui.dump(rig) == dump0)

    # --- "Todas": every part's trail; a click on a body part goes back to that part's trail ------------
    s = bpy.context.scene.asc_sculpt
    s.trail_all = True
    yield 1.0
    bones = {k[1] for k in provider.targets() if k[1]}
    h.check("Todas: the trails of every part are shown", {"hips", "head", "hand.L", "foot.R", BONE} <= bones,
            len(bones))
    h.screenshot("3-all-trails")
    rig = bpy.data.objects[rig_name]
    trail_px = []
    for key in provider.targets():
        tr = provider.get_trail_by_key(key) if key[1] else None
        if tr is not None:
            trail_px += [Vector(h.to_window(p)) for p in
                         (picking.world_to_screen(region, rv3d, Vector(q)) for q in tr.points) if p is not None]
    spot2 = None
    for part in ("spine.001", "chest", "thigh.L", "thigh.R", "upper_arm.L", "shin.L"):
        cand = body_ui.visible_vertex(h, picking, "Vale_body", part, prefer=("",))
        if cand is not None and (not trail_px or min((Vector(cand[2]) - t).length for t in trail_px) > 20):
            spot2 = cand
            break
    h.check("a body spot away from every trail", spot2 is not None)
    if spot2 is not None:
        bco = spot2[2]
        yield from body_ui.hover(h, (bco[0] + 3, bco[1]))
        yield from body_ui.hover(h, bco)
        hov = state.HOVER
        part = hov.bone if hov is not None and hov.on_body else None
        h.check("hovering the body under all the trails picks the part", part is not None,
                hov and (hov.bone, hov.on_body))
        h.event('LEFTMOUSE', 'PRESS', bco)
        h.event('LEFTMOUSE', 'RELEASE', bco)
        yield 0.5
        s = bpy.context.scene.asc_sculpt
        h.check("a body click leaves the overview for that part's trail",
                not s.trail_all and {k[1] for k in provider.targets() if k[1]} == {part},
                (s.trail_all, part, provider.targets()[:4]))
    bpy.context.scene.asc_sculpt.show_rig = True
