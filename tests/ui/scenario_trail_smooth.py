# SPDX-License-Identifier: GPL-3.0-or-later
"""Smooth da trail (docs/design/sculpt-ux.md): rubbing the Smooth brush on a body part smooths that part's
trail, and the trail being smoothed is drawn live during the stroke. Vale on the simple skeleton."""

import os
from pathlib import Path

import bpy
import numpy as np
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
    s = scene.asc_sculpt
    rig = bpy.data.objects[scene["asc_asset_rig"]]
    rig_name = rig.name
    s.interaction_mode = 'BODY'
    s.radius_linked = True
    s.radius_past = 8.0
    s.smooth_mode = 'TRAIL'
    s.show_rig = False
    s.show_trails = True
    bpy.context.view_layer.objects.active = rig
    scene.frame_set(12)
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.smooth")
        bpy.ops.ed.undo_push(message="scenario setup")
    provider.focus_part(rig, BONE)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.2, 1.4))
    eye = Vector((0.4, -5.0, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.6
    yield 1.0
    for _ in range(40):                                      # the focused part's trail is computed
        if provider.get_trail(rig, BONE) is not None:
            break
        yield 0.1
    h.check("the trail of the part is shown", provider.get_trail(rig, BONE) is not None)
    dump0 = body_ui.dump(rig)
    trail0 = provider.get_trail(rig, BONE)
    spot = body_ui.visible_vertex(h, picking, "Vale_body", BONE, prefer=("",))
    h.check("a visible vertex of the forearm", spot is not None)
    if spot is None:
        return
    co = spot[2]
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    g = state.GESTURE
    h.check("the press starts a Smooth gesture", g is not None and g["kind"] == "SMOOTH", g and g["kind"])
    previews = []
    for i in range(1, 41):
        x = 30 * (1 if (i // 4) % 2 == 0 else -1)
        h.move((co[0] + x, co[1] + (i % 4) * 3))
        yield 0.04
        g = state.GESTURE
        if g is not None and g.get("preview"):
            previews.append(np.asarray(g["preview"], dtype=np.float64))
    h.screenshot("1-live-trail")
    h.check("the trail being smoothed is drawn during the stroke", len(previews) > 3, len(previews))
    h.check("the live trail is the whole trail (the smoothed window spliced in)",
            len(previews) > 0 and trail0 is not None and len(previews[-1]) == len(trail0.points),
            len(previews) and len(previews[-1]))
    h.check("the live trail changes as the stroke goes on",
            len(previews) > 3 and np.abs(previews[-1] - previews[0]).max() > 1e-4,
            len(previews) and float(np.abs(previews[-1] - previews[0]).max()))
    last = (co[0], co[1])
    h.event('LEFTMOUSE', 'RELEASE', last)
    yield 0.5
    rig = bpy.data.objects[rig_name]
    h.check("the stroke wrote keys", body_ui.dump(rig) != dump0)
    trail = provider.get_trail(rig, BONE)
    if previews and trail is not None:
        frames = [int(f) for f in trail.frames]
        live = previews[-1]
        if len(live) == len(frames):                         # whole trail (cached one with the window spliced)
            err = float(np.abs(np.asarray(trail.points) - live).max())
        else:                                                # only the window (frames f0 − r − 1 … f0 + r + 1)
            lo = 12 - int(s.radius_past) - 1
            idx = [frames.index(f) for f in range(lo, lo + len(live)) if f in frames]
            err = float(np.abs(np.asarray(trail.points)[idx] - live[[f - lo for f in range(lo, lo + len(live)) if f in frames]]).max())
        h.check("the trail after release is the one drawn live", err < 5e-3, f"{err:.4f} m")
    h.screenshot("2-after")
    center = h.to_window((region.width // 2, region.height // 2))
    yield from body_ui.undo(h, center)
    rig = bpy.data.objects[rig_name]
    h.check("one Ctrl+Z undoes the stroke", body_ui.dump(rig) == dump0)
    bpy.context.scene.asc_sculpt.show_rig = True
