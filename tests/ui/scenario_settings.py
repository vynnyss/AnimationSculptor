# SPDX-License-Identifier: GPL-3.0-or-later
"""Keymap and scene settings: Shift+Alt+K activates the tool; the scene radius drives the soft grab."""

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


def _active_tool(h):
    area, _region, _rv3d = h.view3d()
    with h.override():
        tool = bpy.context.workspace.tools.from_space_view3d_mode('POSE', create=False)
    return tool.idname if tool else None


def scenario(h):
    if ASSET.exists():
        path, bone, key_frame = str(ASSET), "hand_ik.R", 18
    else:
        path, bone, key_frame = os.environ["ASC_UI_RIG"], "hand_ik.L", 12
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    yield 0.5
    provider = h.addon("trails.provider")
    picking = h.addon("interaction.picking")
    state = h.addon("interaction.state")
    tool_id = h.addon("interaction.sculpt_tool").TOOL_ID
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bone in ob.pose.bones and not ob.hide_viewport)
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name="builtin.select_box")
    for pb in rig.pose.bones:
        pb.select = pb.name == bone
    rig.data.bones.active = rig.data.bones[bone]
    scene.frame_set(1)
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.3, 1.2))
    eye = Vector((-2.6, -3.2, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2
    yield 0.3
    h.check("another tool is active first", _active_tool(h) != tool_id, _active_tool(h))

    center = h.to_window((region.width // 2, region.height // 2))
    h.move(center)
    yield 0.2
    h.event('K', 'PRESS', center, shift=True, alt=True)
    h.event('K', 'RELEASE', center, shift=True, alt=True)
    yield 0.5
    h.check("Shift+Alt+K activates the Animation Sculptor tool", _active_tool(h) == tool_id, _active_tool(h))

    # the scene's soft radius is used by the next grab without touching the wheel
    scene.asc_sculpt.soft_radius = 8.0
    yield from _wait(lambda: (t := provider.get_trail(rig, bone)) is not None and t.complete)
    trail = provider.get_trail(rig, bone)
    co = h.to_window(picking.world_to_screen(region, rv3d, Vector(trail.point_at(key_frame))))
    h.move((co[0] + 25, co[1] + 25))
    yield 0.2
    h.move(co)
    yield 0.3
    h.event('LEFTMOUSE', 'PRESS', co)
    yield 0.3
    h.move((co[0] + 30, co[1] - 20))
    yield 0.3
    falloff = state.GESTURE and state.GESTURE.get("falloff")
    h.check("scene radius drives the soft grab", bool(falloff), falloff and len(falloff))
    h.event('WHEELUPMOUSE', 'PRESS', (co[0] + 30, co[1] - 20))
    yield 0.2
    h.event('ESC', 'PRESS', (co[0] + 30, co[1] - 20))
    h.event('ESC', 'RELEASE', (co[0] + 30, co[1] - 20))
    h.event('LEFTMOUSE', 'RELEASE', (co[0] + 30, co[1] - 20))
    yield 0.3
    h.check("the wheel stores the radius in the scene", scene.asc_sculpt.soft_radius == 9.0, scene.asc_sculpt.soft_radius)

