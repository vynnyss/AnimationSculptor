# SPDX-License-Identifier: GPL-3.0-or-later
"""Grab the body (ADR 0013, docs/design/sculpt-ux.md "Agarrar o corpo"): what is under the mouse.

Raycast on the evaluated scene → mesh deformed by the active armature (Armature modifier) or parented to one
of its bones → the deform bone of that spot (largest summed weight on the hit face; nearest posed bone
segment when the evaluated topology differs from the mesh, e.g. subdivision) → the control the rig adapter
says moves it. Also the triangles of a bone's region, for the blue highlight. Derived data only (caches
are dropped on file load).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector

_REGION_CACHE = {}      # (mesh name, vertex count, bone) -> (T, 3) int32 triangle vertex indices
_DOMINANT_CACHE = {}    # (mesh name, vertex count) -> {vertex: dominant deform group name}


@dataclass(frozen=True)
class BodyHit:
    mesh: str           # object hit
    deform: str         # deform bone under the cursor
    world: tuple        # hit point on the surface (world)
    face: tuple = ()    # vertex indices of the hit face (evaluated mesh = mesh topology), () otherwise


def clear_cache():
    _REGION_CACHE.clear()
    _DOMINANT_CACHE.clear()


def _deformed_by(ob, arm_ob) -> bool:
    if ob.type != 'MESH':
        return False
    if ob.parent is arm_ob and ob.parent_type == 'BONE':
        return True
    return any(m.type == 'ARMATURE' and m.object is arm_ob and m.show_viewport for m in ob.modifiers)


def deformed_meshes(scene, arm_ob):
    return [ob for ob in scene.objects if ob.visible_get() and _deformed_by(ob, arm_ob)]


def _nearest_bone(arm_ob, names, point):
    best, best_d = None, None
    p = np.asarray(point, dtype=np.float64)
    mw = arm_ob.matrix_world
    for name in names:
        pb = arm_ob.pose.bones.get(name)
        if pb is None:
            continue
        a = np.asarray(mw @ pb.head)
        b = np.asarray(mw @ pb.tail)
        ab = b - a
        t = float(np.clip(np.dot(p - a, ab) / max(float(np.dot(ab, ab)), 1e-12), 0.0, 1.0))
        d = float(np.linalg.norm(a + t * ab - p))
        if best_d is None or d < best_d:
            best, best_d = name, d
    return best


def _deform_names(arm_ob):
    return {b.name for b in arm_ob.data.bones if b.use_deform}


def bone_at(ob, ob_eval, arm_ob, face_index, point):
    """Deform bone of the hit spot (see module docstring)."""
    if ob.parent is arm_ob and ob.parent_type == 'BONE' and not any(m.type == 'ARMATURE' for m in ob.modifiers):
        return ob.parent_bone or None              # a prop held by a bone (sword, shield)
    deform = _deform_names(arm_ob)
    mesh, emesh = ob.data, ob_eval.data
    groups = {vg.index: vg.name for vg in ob.vertex_groups if vg.name in deform}
    if len(emesh.vertices) == len(mesh.vertices) and 0 <= face_index < len(emesh.polygons) and groups:
        acc = {}
        for v in emesh.polygons[face_index].vertices:
            for g in mesh.vertices[v].groups:
                name = groups.get(g.group)
                if name is not None:
                    acc[name] = acc.get(name, 0.0) + g.weight
        if acc:
            return max(sorted(acc), key=lambda n: acc[n])     # sorted: deterministic on ties
    candidates = [n for n in groups.values()] or sorted(deform)
    return _nearest_bone(arm_ob, candidates, point)


def pick(context, region, rv3d, mouse, arm_ob) -> BodyHit | None:
    """The body spot under ``mouse`` (region px) for the armature ``arm_ob``, or None."""
    co = Vector(mouse)
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
    depsgraph = context.evaluated_depsgraph_get()
    ok, location, _normal, index, hit_ob, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
    if not ok or hit_ob is None:
        return None
    ob = hit_ob.original if hasattr(hit_ob, "original") else hit_ob
    if not _deformed_by(ob, arm_ob):
        return None
    ob_eval = ob.evaluated_get(depsgraph)
    deform = bone_at(ob, ob_eval, arm_ob, index, location)
    if deform is None:
        return None
    face = ()
    emesh = ob_eval.data
    if len(emesh.vertices) == len(ob.data.vertices) and 0 <= index < len(emesh.polygons):
        face = tuple(emesh.polygons[index].vertices)
    return BodyHit(mesh=ob.name, deform=deform, world=tuple(location), face=face)


def skin_points(mesh_name, indices):
    """World positions (len(indices), 3) of mesh vertices on the evaluated (deformed) mesh, current frame."""
    import bpy

    ob = bpy.data.objects[mesh_name]
    ob_eval = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    verts = ob_eval.data.vertices
    mw = np.asarray(ob_eval.matrix_world, dtype=np.float64)
    co = np.array([tuple(verts[i].co) for i in indices], dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3]


# -- highlight -------------------------------------------------------------------------------------
def _dominant(ob, deform):
    key = (ob.name, len(ob.data.vertices))
    cached = _DOMINANT_CACHE.get(key)
    if cached is not None:
        return cached
    groups = {vg.index: vg.name for vg in ob.vertex_groups if vg.name in deform}
    out = {}
    for v in ob.data.vertices:
        best, best_w = None, 0.0
        for g in v.groups:
            name = groups.get(g.group)
            if name is not None and g.weight > best_w:
                best, best_w = name, g.weight
        if best is not None:
            out[v.index] = best
    _DOMINANT_CACHE[key] = out
    return out


def region_triangles(ob, arm_ob, bone):
    """(T, 3) vertex indices of the triangles whose vertices are mostly dominated by ``bone``."""
    key = (ob.name, len(ob.data.vertices), bone)
    tris = _REGION_CACHE.get(key)
    if tris is not None:
        return tris
    dominant = _dominant(ob, _deform_names(arm_ob))
    mesh = ob.data
    mesh.calc_loop_triangles()
    out = []
    for tri in mesh.loop_triangles:
        vs = tri.vertices
        if sum(1 for v in vs if dominant.get(v) == bone) >= 2:
            out.append(tuple(vs))
    tris = np.asarray(out, dtype=np.int32).reshape(-1, 3)
    _REGION_CACHE[key] = tris
    return tris


def highlight_geometry(context, mesh_name, arm_ob, bone, inflate=0.002):
    """World positions (T*3, 3) of the bone's region on the evaluated mesh (slightly pushed out along the
    normals so it draws over the surface), or None when the evaluated topology differs."""
    import bpy

    ob = bpy.data.objects.get(mesh_name)
    if ob is None or bone is None:
        return None
    if ob.parent is arm_ob and ob.parent_type == 'BONE' and not any(m.type == 'ARMATURE' for m in ob.modifiers):
        return None
    tris = region_triangles(ob, arm_ob, bone)
    if len(tris) == 0:
        return None
    ob_eval = ob.evaluated_get(context.evaluated_depsgraph_get())
    emesh = ob_eval.data
    n = len(emesh.vertices)
    if n != len(ob.data.vertices):
        return None
    co = np.empty(n * 3, dtype=np.float32)
    emesh.vertices.foreach_get("co", co)
    nor = np.empty(n * 3, dtype=np.float32)
    emesh.vertex_normals.foreach_get("vector", nor)
    pts = co.reshape(n, 3) + nor.reshape(n, 3) * inflate
    mw = np.asarray(ob_eval.matrix_world, dtype=np.float32)
    world = pts @ mw[:3, :3].T + mw[:3, 3]
    return world[tris.reshape(-1)]
