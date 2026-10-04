# SPDX-License-Identifier: GPL-3.0-or-later
"""A simple skinned "body" for tests that need a mesh deformed by the rig (mesh picking, onion skin).

One closed tube per deform bone (8 sides), each vertex weighted 1.0 to its bone's vertex group, joined in
one mesh with an Armature modifier. Deterministic, no automatic weights, a few hundred vertices. Not a
real character: it only gives every deform bone a surface to hit.
"""

import math

import bpy
from mathutils import Vector

SIDES = 8
BODY_NAME = "asc_test_body"


def _frame(axis):
    axis = axis.normalized()
    ref = Vector((1.0, 0.0, 0.0)) if abs(axis.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    u = axis.cross(ref).normalized()
    return u, axis.cross(u).normalized()


def add_skinned_body(rig, bones=None, radius_factor=0.22, min_radius=0.015):
    """Add (or replace) the test body for ``rig``. ``bones``: deform bone names (default: all deform bones)."""
    old = bpy.data.objects.get(BODY_NAME)
    if old is not None:
        bpy.data.objects.remove(old)
    names = [b.name for b in rig.data.bones if b.use_deform] if bones is None else list(bones)
    verts, faces, groups = [], [], []
    for name in names:
        bone = rig.data.bones[name]
        head, tail = bone.head_local, bone.tail_local
        axis = tail - head
        if axis.length < 1e-6:
            continue
        r = max(min_radius, radius_factor * axis.length)
        u, v = _frame(axis)
        base = len(verts)
        for end in (head, tail):
            for i in range(SIDES):
                a = 2.0 * math.pi * i / SIDES
                verts.append(tuple(end + (u * math.cos(a) + v * math.sin(a)) * r))
        for i in range(SIDES):
            j = (i + 1) % SIDES
            faces.append((base + i, base + j, base + SIDES + j, base + SIDES + i))
        faces.append(tuple(base + i for i in reversed(range(SIDES))))          # head cap
        faces.append(tuple(base + SIDES + i for i in range(SIDES)))           # tail cap
        groups.append((name, range(base, base + 2 * SIDES)))
    mesh = bpy.data.meshes.new(BODY_NAME)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(BODY_NAME, mesh)
    for collection in rig.users_collection:
        collection.objects.link(ob)
    ob.matrix_world = rig.matrix_world
    ob.parent = rig
    ob.matrix_parent_inverse = rig.matrix_world.inverted()
    for name, indices in groups:
        vg = ob.vertex_groups.new(name=name)
        vg.add(list(indices), 1.0, 'REPLACE')
    mod = ob.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    return ob
