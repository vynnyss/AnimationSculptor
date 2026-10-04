# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers of the BODY-mode UI scenarios (grab, smooth, tools): scene setup on the local Vale (or the
public rig + the simple skinned body), mesh-point lookup that the viewport can really see, Action dumps."""

import os
import time
from pathlib import Path

import bpy
import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector

import body_mesh
import deform_check

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "attack_test.blend"


def wait(cond, timeout=10.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def active_tool(h):
    with h.override():
        tool = bpy.context.workspace.tools.from_space_view3d_mode('POSE', create=False)
    return tool.idname if tool else None


def dump(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbag(rig.animation_data.action_slot)
    return {(fc.data_path, fc.array_index): [tuple(k.co) + tuple(k.handle_left) + tuple(k.handle_right)
                                             for k in fc.keyframe_points] for fc in cb.fcurves}


def curve_values(rig, bone, frames):
    """{frame: channel values of ``bone`` evaluated on the F-Curves}."""
    cb = rig.animation_data.action.layers[0].strips[0].channelbag(rig.animation_data.action_slot)
    out = {}
    for fc in cb.fcurves:
        if fc.data_path.startswith(f'pose.bones["{bone}"]'):
            for f in frames:
                out.setdefault(f, []).append(fc.evaluate(f))
    return {f: np.asarray(v) for f, v in out.items()}


def open_scene(h, frame_vale, frame_public, mode='BODY', view=None):
    """Open the Vale (or the public rig with a skinned body) and prepare the 3D view. Returns a dict."""
    vale = ASSET.exists()
    path = str(ASSET) if vale else os.environ["ASC_UI_RIG"]
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    scene = bpy.context.scene
    scene.asc_sculpt.interaction_mode = mode
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and "hand_ik.R" in ob.pose.bones
               and not ob.hide_viewport)
    if not vale:
        body_mesh.add_skinned_body(rig)
    mesh = deform_check.deformed_mesh(rig)
    ctx = {"vale": vale, "rig": rig.name, "mesh": mesh.name, "frame": frame_vale if vale else frame_public,
           "fk": "L" if vale else "R", "ik": "R" if vale else "L"}
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = False
    scene.frame_set(ctx["frame"])
    area, region, rv3d = h.view3d()
    target = Vector((0.0, -0.3, 1.2))
    eye = view or Vector((-2.6, -3.2, 1.6))
    rv3d.view_location = target
    rv3d.view_rotation = (target - eye).to_track_quat('-Z', 'Y')
    rv3d.view_distance = 3.2
    return ctx


def visible_vertex(h, picking, mesh_name, prefix, prefer=("", ".001"), margin=40):
    """A vertex of the deformed part (DEF bone names starting with ``prefix``) that the viewport really sees
    (the ray from the eye hits it first, inside the region), closest to the part's centroid.
    Returns (index, world, window_px, bone) or None."""
    mesh = bpy.data.objects[mesh_name]
    _area, region, rv3d = h.view3d()
    names = sorted(vg.name for vg in mesh.vertex_groups if vg.name.startswith(prefix))
    ordered = [prefix + s for s in prefer[::-1] if prefix + s in names] + [n for n in names]
    pts = deform_check.points(mesh)
    eye = rv3d.view_matrix.inverted().translation
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for bone in ordered:
        idx = deform_check.part(mesh, bone)
        if not len(idx):
            continue
        cen = pts[idx].mean(axis=0)
        order = idx[np.argsort(np.linalg.norm(pts[idx] - cen, axis=1))]
        for vi in order[:600]:
            w = Vector(pts[vi])
            px = picking.world_to_screen(region, rv3d, w)
            if px is None or not (margin < px[0] < region.width - margin and margin < px[1] < region.height - margin):
                continue
            # test the real pixel rays (integer window px, the way the mouse arrives) and their 1 px neighbours
            wx, wy = round(px[0]), round(px[1])
            good = True
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                m = Vector((wx + dx, wy + dy))
                o = view3d_utils.region_2d_to_origin_3d(region, rv3d, m)
                d = view3d_utils.region_2d_to_vector_3d(region, rv3d, m)
                ok, loc, _n, _i, ob, _mx = bpy.context.scene.ray_cast(depsgraph, o, d)
                if not (ok and ob.name == mesh_name and (loc - w).length < 0.01):
                    good = False
                    break
            if good:
                return int(vi), Vector(w), h.to_window((wx, wy)), bone
    return None


def vertex_window_px(h, picking, mesh_name, vi, frame=None):
    mesh = bpy.data.objects[mesh_name]
    _area, region, rv3d = h.view3d()
    px = picking.world_to_screen(region, rv3d, Vector(deform_check.points(mesh, frame)[vi]))
    return None if px is None else Vector(h.to_window(px))


def release_mods(h, co, *keys):
    for key in keys:
        h.event(key, 'PRESS', co)
        h.event(key, 'RELEASE', co)


def undo(h, co, redo=False):
    """Ctrl+Z / Ctrl+Shift+Z with explicit modifier release (simulated modifiers stay pressed)."""
    h.event('Z', 'PRESS', co, ctrl=True, shift=redo)
    h.event('Z', 'RELEASE', co, ctrl=True, shift=redo)
    yield 0.5
    release_mods(h, co, 'LEFT_CTRL', *(['LEFT_SHIFT'] if redo else []))
    yield 0.1


def drag(h, start, end, steps=8, dt=0.05, release=True):
    h.event('LEFTMOUSE', 'PRESS', start)
    yield 0.3
    for i in range(1, steps + 1):
        h.move((start[0] + (end[0] - start[0]) * i // steps, start[1] + (end[1] - start[1]) * i // steps))
        yield dt
    if release:
        h.event('LEFTMOUSE', 'RELEASE', end)
        yield 0.5


def hover(h, co, jitter=25):
    """Move the mouse onto ``co`` from a few pixels away (several moves so the gizmo's test_select runs)."""
    for d in (jitter, jitter // 2, 3, 0):
        h.move((co[0] + d, co[1] + d))
        yield 0.15
    yield 0.3
