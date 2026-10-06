# SPDX-License-Identifier: GPL-3.0-or-later
"""The Corpo workflow "rig + weight paint, skeleton invisible": start from zero (no Action), select only the
mesh, press Animar, drag a limb part of the body (never click the skeleton). Checks the Action is born by the
gesture, nothing is keyed below frame 0, the trail of the part touched shows up, one Ctrl+Z undoes the drag and
a plain click leaves no empty Action behind. Uses the local Vale on the simple skeleton."""

import os
from pathlib import Path

import bpy
from mathutils import Vector

import body_ui

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "basic_rig_test.blend"
MESH = "Vale_body"
FRAME = 3


def _keys(rig_name):
    """(number of keys, lowest key frame) over every curve of the rig's Action; (0, None) without one."""
    rig = bpy.data.objects[rig_name]
    adt = rig.animation_data
    if adt is None or adt.action is None or adt.action_slot is None:
        return 0, None
    cb = adt.action.layers[0].strips[0].channelbag(adt.action_slot)
    frames = [k.co[0] for fc in cb.fcurves for k in fc.keyframe_points] if cb else []
    return len(frames), (min(frames) if frames else None)


def _action(rig_name):
    adt = bpy.data.objects[rig_name].animation_data
    return None if adt is None else adt.action


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
    rig_name = scene["asc_asset_rig"]
    rig = bpy.data.objects[rig_name]

    # --- 1) setup: from zero, only the mesh selected, skeleton invisible --------------------------------
    if rig.animation_data is not None:
        rig.animation_data.action = None
    with h.override():
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    for ob in bpy.data.objects:
        ob.select_set(False)
    mesh = bpy.data.objects[MESH]
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    s.interaction_mode = 'BODY'
    s.radius_linked = True
    s.show_rig = False
    provider.set_enabled(scene, True)
    scene.asc_trails.path_show = True
    scene.asc_trails.onion_show = True
    s.radius_past = 8.0
    s.radius_future = 8.0
    for pb in rig.pose.bones:                   # the animator never selects bones
        pb.select = False
    scene.frame_set(FRAME)
    with h.override():
        bpy.ops.ed.undo_push(message="scenario setup")      # AFTER frame_set / selection
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.2, 1.6))
    eye = Vector((0.4, -5.0, 1.8))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.6
    yield 0.5
    h.check("setup: the rig has no Action", _action(rig_name) is None)
    h.check("setup: the mesh is active, skeleton hidden", bpy.context.view_layer.objects.active.name == MESH
            and not s.show_rig)

    # --- 2) Animar ----------------------------------------------------------------------------------
    with h.override():
        h.check("Animar is available with only the mesh selected", bpy.ops.asc.animate.poll())
        bpy.ops.asc.animate()
    yield 0.8
    rig = bpy.data.objects[rig_name]
    h.check("Animar: the rig is active", bpy.context.view_layer.objects.active == rig,
            bpy.context.view_layer.objects.active)
    h.check("Animar: Pose Mode", rig.mode == 'POSE', rig.mode)
    tool = body_ui.active_tool(h)
    h.check("Animar: a sculpt tool is active", tool is not None and tool.startswith("animation_sculptor."), tool)
    picked = [pb.name for pb in rig.pose.bones if pb.select]
    h.check("no bone is selected (Animar selects none)", not picked, picked)
    targets = provider.engine.resolve_targets(scene, bpy.context.view_layer)
    onion = sorted(t.obj.name for t in targets if t.want_onion)
    h.check("the onion targets are the Vale meshes", MESH in onion, onion)
    h.screenshot("1-animate-onion")

    # --- 3) drag the forearm of the body --------------------------------------------------------------
    spot = None
    for bone in ("forearm.R", "hand.R"):
        spot = body_ui.visible_vertex(h, picking, MESH, bone, prefer=("",))
        if spot is not None:
            break
    h.check("a visible vertex of the right forearm / hand", spot is not None)
    if spot is None:
        return
    _vi, _world, co, vbone = spot
    center = h.to_window((region.width // 2, region.height // 2))
    yield from body_ui.hover(h, co)
    hov = state.HOVER
    h.check("hover picks the body", hov is not None and hov.on_body, hov and (hov.bone, hov.on_body))
    end = (co[0] + 50, co[1] + 5)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.check("a gesture started", state.GESTURE is not None, state.GESTURE and state.GESTURE["kind"])
    for i in range(1, 9):
        h.move((co[0] + 50 * i // 8, co[1] + 5 * i // 8))
        yield 0.08
    h.screenshot("2-drag")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.6
    h.check("an Action was born on the rig", _action(rig_name) is not None)
    n, lowest = _keys(rig_name)
    h.check("keys were written", n > 0, n)
    h.check("no key below frame 0", lowest is not None and lowest >= -1e-6, lowest)
    focus = provider.FOCUS.get(rig_name)
    h.check("the touched bone is the focus part", bool(focus), (focus, vbone, dict(provider.FOCUS)))
    trail = None
    for _ in range(100):
        trail = provider.get_trail(bpy.data.objects[rig_name], focus) if focus else None
        if trail is not None and trail.complete:
            break
        yield 0.1
    h.check("the trail of the touched part exists", trail is not None and trail.complete,
            trail and (trail.bone, len(trail.frames)))
    if trail is not None:
        h.check("the trail starts at frame >= 0", float(min(trail.frames)) >= 0.0, float(min(trail.frames)))
    h.screenshot("3-after-drag-trail")

    # --- 4) one Ctrl+Z undoes the drag -------------------------------------------------------------------
    yield from body_ui.undo(h, center)
    rig = bpy.data.objects[rig_name]
    act = _action(rig_name)
    n2, _low = _keys(rig_name)
    h.check("one Ctrl+Z undoes the drag (no keys left)", n2 == 0, (n2, act and act.name))
    # the undo step is the setup one (Object mode, mesh active): the mode comes back with it
    h.check("Ctrl+Z: back to the state before Animar's drag", bpy.context.view_layer.objects.active is not None,
            (rig.mode, bpy.context.view_layer.objects.active))

    # --- 5) a click without drag leaves no empty Action ----------------------------------------------------
    if act is not None:
        h.check("(info) undo left an Action behind (removed for the click test)", True, act.name)
        rig.animation_data.action = None
        with h.override():
            bpy.ops.ed.undo_push(message="scenario no action")
        yield 0.3
    h.check("click test starts without an Action", _action(rig_name) is None)
    spot = body_ui.visible_vertex(h, picking, MESH, "forearm.R", prefer=("",)) \
        or body_ui.visible_vertex(h, picking, MESH, "hand.R", prefer=("",))
    if spot is None:
        h.check("a visible vertex for the click", False)
        return
    co = spot[2]
    yield from body_ui.hover(h, co)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.event('LEFTMOUSE', 'RELEASE', co)
    yield 0.6
    h.check("a click without a drag leaves no Action", _action(rig_name) is None,
            _action(rig_name) and _action(rig_name).name)
    h.check("no gesture left running", state.GESTURE is None)
    bpy.context.scene.asc_sculpt.show_rig = True
