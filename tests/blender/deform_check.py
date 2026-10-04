# SPDX-License-Identifier: GPL-3.0-or-later
"""Check the deformation of the character's mesh, not only the rig (maintainer's request, 2026-10-04).

``deformed_mesh(rig)`` finds the visible mesh deformed by the rig (the Vale's body in the local asset, the
simple skinned body of ``body_mesh`` in the public rig); ``points(mesh, frame)`` evaluates its world vertex
positions at a frame; ``part(mesh, bone)`` are the vertices dominated by a deform bone. A gesture is then
checked on the skin: the grabbed part moved by the drag, the rest of the window followed, nothing outside it
changed.
"""

import bpy
import numpy as np


def deformed_mesh(rig):
    """The largest visible mesh with an Armature modifier on ``rig`` (None when there is none)."""
    meshes = [ob for ob in bpy.data.objects if ob.type == 'MESH' and ob.visible_get()
              and any(m.type == 'ARMATURE' and m.object is rig for m in ob.modifiers)]
    return max(meshes, key=lambda ob: len(ob.data.vertices)) if meshes else None


def points(mesh, frame=None):
    """(V, 3) evaluated world vertex positions at ``frame`` (the current frame when None)."""
    scene = bpy.context.scene
    if frame is not None and scene.frame_current != frame:
        scene.frame_set(frame)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(depsgraph)
    data = ev.to_mesh()
    try:
        co = np.empty(len(data.vertices) * 3, dtype=np.float64)
        data.vertices.foreach_get("co", co)
        mw = np.array(ev.matrix_world, dtype=np.float64)
        co = co.reshape(-1, 3)
        return co @ mw[:3, :3].T + mw[:3, 3]
    finally:
        ev.to_mesh_clear()


def part(mesh, bone, min_weight=0.5):
    """Indices of the vertices whose weight for ``bone``'s vertex group is ≥ ``min_weight`` and largest."""
    vg = mesh.vertex_groups.get(bone)
    if vg is None:
        return np.empty(0, dtype=np.int64)
    out = []
    for v in mesh.data.vertices:
        best = max(v.groups, key=lambda g: g.weight, default=None)
        if best is not None and best.group == vg.index and best.weight >= min_weight:
            out.append(v.index)
    return np.asarray(out, dtype=np.int64)


def frames_snapshot(mesh, frames):
    """{frame: (V, 3)} evaluated positions."""
    return {f: points(mesh, f) for f in frames}


def max_change(before, after, frames, idx=None):
    """Largest vertex displacement over ``frames`` (optionally restricted to vertex indices ``idx``)."""
    worst = 0.0
    for f in frames:
        a, b = before[f], after[f]
        if idx is not None:
            a, b = a[idx], b[idx]
        if len(a):
            worst = max(worst, float(np.linalg.norm(b - a, axis=1).max()))
    return worst
