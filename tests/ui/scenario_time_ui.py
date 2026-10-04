# SPDX-License-Identifier: GPL-3.0-or-later
"""Time UI (design/ephemeral-rig.md, phase 1): the time ruler's end handles set the past/future radius
(one undo step, Esc cancels), the asymmetric soft grab moves only the keys inside the window, the
trails get the past red / future green palette when the tool turns them on."""

import os
import time
from pathlib import Path

import bpy
from mathutils import Vector

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "attack_test.blend"


def _wait(cond, timeout=10.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def _key_values(rig, bone):
    """{frame: (x, y, z)} of the location keys of ``bone``."""
    action = rig.animation_data.action
    cb = action.layers[0].strips[0].channelbag(rig.animation_data.action_slot)
    path = rig.pose.bones[bone].path_from_id("location")
    out = {}
    for i in range(3):
        fc = cb.fcurves.find(path, index=i)
        if fc is None:
            continue
        for kp in fc.keyframe_points:
            out.setdefault(int(round(kp.co[0])), [0.0, 0.0, 0.0])[i] = kp.co[1]
    return {f: tuple(v) for f, v in out.items()}


def scenario(h):
    if ASSET.exists():
        path, bone, key_frame = str(ASSET), "hand_ik.R", 18
    else:
        path, bone, key_frame = os.environ["ASC_UI_RIG"], "hand_ik.L", 12
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    bpy.context.scene.asc_sculpt.interaction_mode = 'TRAIL'     # trail gestures (ADR 0013: Corpo is the default)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    hud = h.addon("interaction.hud")
    ruler = h.addon("core.ruler")
    scene = bpy.context.scene
    s = scene.asc_sculpt     # re-fetched after every undo/redo: undo invalidates Python references to ID data
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bone in ob.pose.bones and not ob.hide_viewport)
    rig_name = rig.name
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
    rig.data.bones.active = rig.data.bones[bone]
    scene.frame_set(key_frame)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.3, 1.2))
    eye = Vector((-2.6, -3.2, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2
    s.radius_linked = False
    s.radius_past = s.radius_future = 0.0
    with h.override():
        bpy.ops.wm.tool_set_by_id(name="animation_sculptor.sculpt")
        # settings written from Python have no undo step: push one so Ctrl+Z comes back to this state, not to
        # the values saved in the file
        bpy.ops.ed.undo_push(message="scenario setup")
    yield 0.5
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete)

    trails = scene.asc_trails
    past, future = tuple(trails.path_color_past), tuple(trails.path_color_future)
    h.check("the tool applies the palette: past red, future green",
            past[0] > past[1] and future[1] > future[0] and s.palette_applied, (past, future))

    with h.override():
        lay = hud.current_layout(bpy.context, region)
    h.check("the time ruler has a layout in the viewport", lay is not None)
    h.screenshot("1-ruler")

    def handle(side):
        x = ruler.handle_x(lay, side, s.radius_past, s.radius_future)
        return h.to_window((x + (-2 if side == ruler.PAST else 2), lay.y + lay.height / 2))

    # --- drag the future handle 10 frames to the right ---------------------------------------------
    co = handle(ruler.FUTURE)
    h.move((co[0], co[1] + 60))
    yield 0.2
    h.move(co)
    yield 0.3
    h.check("hovering the right end of the ruler picks the future handle", state.RULER_HOVER == 'FUTURE',
            state.RULER_HOVER)
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    h.check("press starts the ruler drag", state.RULER_DRAG == 'FUTURE', state.RULER_DRAG)
    end = (int(round(co[0] - 2 + 10 * lay.ppf)), co[1])
    for i in range(1, 6):
        h.move((co[0] + (end[0] - co[0]) * i // 5, co[1]))
        yield 0.05
    h.screenshot("2-dragging-future")
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.3
    h.check("dragging the future end sets only the future radius", (s.radius_past, s.radius_future) == (0.0, 10.0),
            (s.radius_past, s.radius_future))
    h.check("the drag ended", state.RULER_DRAG is None and state.RULER_SPAN == 0)

    center = h.to_window((region.width // 2, region.height // 2))
    h.move(center)
    yield 0.2
    h.event('Z', 'PRESS', center, ctrl=True)
    h.event('Z', 'RELEASE', center, ctrl=True)
    yield 0.4
    s = bpy.context.scene.asc_sculpt
    h.check("one Ctrl+Z undoes the ruler drag", s.radius_future == 0.0, s.radius_future)
    h.event('Z', 'PRESS', center, ctrl=True, shift=True)
    h.event('Z', 'RELEASE', center, ctrl=True, shift=True)
    yield 0.4
    s = bpy.context.scene.asc_sculpt
    h.check("Ctrl+Shift+Z redoes it", s.radius_future == 10.0, s.radius_future)
    # simulated modifier state outlives the Z event: release Shift/Ctrl explicitly (Shift = both sides)
    for key in ('LEFT_SHIFT', 'LEFT_CTRL'):
        h.event(key, 'PRESS', center)
        h.event(key, 'RELEASE', center)
    yield 0.2

    # --- past handle 3 frames to the left ---------------------------------------------------------
    with h.override():
        lay = hud.current_layout(bpy.context, region)
    co = handle(ruler.PAST)
    h.move((co[0], co[1] + 60))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    end = (int(round(co[0] + 2 - 3 * lay.ppf)), co[1])
    h.move(end)
    yield 0.2
    h.event('LEFTMOUSE', 'RELEASE', end)
    yield 0.3
    h.check("dragging the past end sets only the past radius", (s.radius_past, s.radius_future) == (3.0, 10.0),
            (s.radius_past, s.radius_future))

    # --- Esc cancels a ruler drag -------------------------------------------------------------------
    co = handle(ruler.FUTURE)
    h.move((co[0], co[1] + 60))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.2
    h.move((co[0] + int(5 * lay.ppf), co[1]))
    yield 0.2
    h.event('ESC', 'PRESS', (co[0] + int(5 * lay.ppf), co[1]))
    h.event('ESC', 'RELEASE', (co[0] + int(5 * lay.ppf), co[1]))
    h.event('LEFTMOUSE', 'RELEASE', (co[0] + int(5 * lay.ppf), co[1]))
    yield 0.3
    h.check("Esc restores the radii", (s.radius_past, s.radius_future) == (3.0, 10.0),
            (s.radius_past, s.radius_future))

    # --- asymmetric soft grab: past 3, future 10 ---------------------------------------------------
    rig = bpy.data.objects[rig_name]
    before = _key_values(rig, bone)
    neighbours = sorted(f for f in before if f != key_frame)
    inside = [f for f in neighbours if -3 < f - key_frame < 10]
    outside = [f for f in neighbours if f not in inside]
    trail = provider.get_trail(rig, bone)
    co = h.to_window(picking.world_to_screen(region, rv3d, Vector(trail.point_at(key_frame))))
    h.move((co[0] + 25, co[1] + 25))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    ms = []
    for i in range(1, 6):
        h.move((co[0] + 8 * i, co[1] - 6 * i))
        yield 0.05
        ms.append(state.STATS.get("last_move_ms", 0.0))
    h.screenshot("3-asymmetric-grab")
    h.event('LEFTMOUSE', 'RELEASE', (co[0] + 40, co[1] - 30))
    yield 0.5
    after = _key_values(rig, bone)
    moved = [f for f in neighbours if max(abs(a - b) for a, b in zip(after[f], before[f])) > 1e-6]
    # (the public rig fallback has no neighbour key inside this window: nothing to move is also right)
    h.check("the asymmetric soft grab moves the keys inside the window", set(inside) <= set(moved),
            f"inside {inside} moved {moved}")
    h.check("keys outside the window stay", not (set(outside) & set(moved)), f"outside {outside} moved {moved}")
    h.check("mouse move under 16 ms", max(ms) < 16.0, f"{max(ms):.2f} ms")
    h.event('Z', 'PRESS', center, ctrl=True)
    h.event('Z', 'RELEASE', center, ctrl=True)
    yield 0.4
