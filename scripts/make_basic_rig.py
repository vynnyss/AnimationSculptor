# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig a plain character mesh with a simple deform skeleton (no control rig) for Animation Sculptor.

Run by ``python scripts/dev.py basic-rig`` (or directly):

    blender --background <mesh.blend> --factory-startup --python scripts/make_basic_rig.py -- \\
        --output <rigged.blend> [--test-output tests/assets/local/basic_rig_test.blend]

The source file is only read: results are written with ``save_as_mainfile(copy=True)`` to other paths.
The skeleton is Mixamo-like — the deform bones *are* the controls (ADR 0014): ``root`` (translation only),
``hips`` (translation + rotation), every other bone rotation only (location locked), quaternions. The joints
are literal positions measured on ``Vale_new_Basic_mesh.blend`` (A-pose, ~2.7 m, facing −Y, centred on
x ≈ 0.06; left side mirrored) and snapped to the centre of the mesh's cross-section around them. Meshes are
bound with automatic weights. ``--test-output`` also gets a small deterministic Action for the tests.
"""

from __future__ import annotations

import argparse
import sys

SCRIPT_VERSION = 1
RIG_NAME = "Vale_rig"
ACTION_NAME = "asc_test_basic"
MIRROR_X = 0.12          # left side x = MIRROR_X − right side x (symmetry plane x = 0.06)

# bone -> (head, tail) for the centre and the RIGHT side (".R"); the left side is mirrored.
CENTER = {
    "root": ((0.06, -0.12, 0.0), (0.06, 0.18, 0.0)),
    "hips": ((0.06, -0.14, 1.40), (0.06, -0.14, 1.55)),
    "spine": ((0.06, -0.14, 1.55), (0.06, -0.15, 1.72)),
    "spine.001": ((0.06, -0.15, 1.72), (0.06, -0.16, 1.90)),
    "chest": ((0.06, -0.16, 1.90), (0.06, -0.14, 2.10)),
    "neck": ((0.06, -0.14, 2.10), (0.06, -0.14, 2.27)),
    "head": ((0.06, -0.14, 2.27), (0.06, -0.14, 2.62)),
}
RIGHT = {
    "shoulder": ((0.00, -0.13, 2.08), (-0.148, -0.115, 2.077)),
    "upper_arm": ((-0.148, -0.115, 2.077), (-0.351, -0.046, 1.747)),
    "forearm": ((-0.351, -0.046, 1.747), (-0.49, -0.11, 1.41)),
    "hand": ((-0.49, -0.11, 1.41), (-0.54, -0.135, 1.30)),
    "thigh": ((-0.044, -0.14, 1.44), (-0.182, -0.127, 0.888)),
    "shin": ((-0.182, -0.127, 0.888), (-0.344, -0.04, 0.265)),
    "foot": ((-0.344, -0.04, 0.265), (-0.41, -0.24, 0.06)),
    "toe": ((-0.41, -0.24, 0.06), (-0.47, -0.35, 0.03)),
}
# fingers (right hand): knuckle → middle → last joint → tip, measured on close-ups of the hand
FINGERS = {
    "thumb": ((-0.495, -0.16, 1.37), (-0.49, -0.19, 1.32), (-0.488, -0.205, 1.285), (-0.487, -0.21, 1.25)),
    "index": ((-0.545, -0.175, 1.30), (-0.538, -0.181, 1.255), (-0.532, -0.187, 1.222), (-0.525, -0.192, 1.19)),
    "middle": ((-0.545, -0.143, 1.30), (-0.538, -0.150, 1.255), (-0.532, -0.155, 1.222), (-0.525, -0.160, 1.183)),
    "ring": ((-0.545, -0.110, 1.30), (-0.538, -0.117, 1.255), (-0.532, -0.123, 1.222), (-0.525, -0.130, 1.188)),
    "pinky": ((-0.545, -0.080, 1.30), (-0.538, -0.086, 1.258), (-0.532, -0.092, 1.226), (-0.525, -0.098, 1.198)),
}
PARENT = {
    "root": None, "hips": "root", "spine": "hips", "spine.001": "spine", "chest": "spine.001",
    "neck": "chest", "head": "neck",
    "shoulder": "chest", "upper_arm": "shoulder", "forearm": "upper_arm", "hand": "forearm",
    "thigh": "hips", "shin": "thigh", "foot": "shin", "toe": "foot",
}
CONNECTED = {"spine", "spine.001", "chest", "neck", "head", "forearm", "hand", "shin", "foot", "toe"}
# joints re-centred on the mesh cross-section (bone, end): limbs and the neck
SNAP = [("upper_arm", 0), ("upper_arm", 1), ("forearm", 1), ("thigh", 0), ("thigh", 1), ("shin", 1),
        ("neck", 0), ("neck", 1)]
SNAP_SLAB = 0.03          # half thickness of the cross-section slab (m)
SNAP_RADIUS = 0.13        # vertices farther than this from the joint are ignored (m)

# deterministic test animation (quaternions w, x, y, z) for --test-output: frame -> bone -> rotation
TEST_KEYS = {
    1: {},
    12: {"upper_arm.R": (0.9239, 0.3827, 0.0, 0.0), "forearm.R": (0.9659, 0.2588, 0.0, 0.0),
         "spine.001": (0.9848, 0.0, 0.0, 0.1736), "head": (0.9848, 0.0, 0.1736, 0.0),
         "thigh.L": (0.9659, 0.2588, 0.0, 0.0), "index.01.R": (0.9239, 0.3827, 0.0, 0.0)},
    24: {"upper_arm.R": (0.9659, -0.2588, 0.0, 0.0), "forearm.R": (0.9239, 0.3827, 0.0, 0.0),
         "spine.001": (0.9848, 0.0, 0.0, -0.1736), "head": (0.9848, 0.0, -0.1736, 0.0),
         "thigh.L": (1.0, 0.0, 0.0, 0.0), "index.01.R": (1.0, 0.0, 0.0, 0.0)},
}
TEST_HIPS = {1: (0.0, 0.0, 0.0), 12: (0.0, -0.08, -0.05), 24: (0.0, 0.0, 0.0)}
FRAME_START, FRAME_END = 1, 24


def mirror(p):
    return (MIRROR_X - p[0], p[1], p[2])


def bone_table():
    """name -> (head, tail, parent, connected) for the whole skeleton (pure; testable without Blender)."""
    out = {}
    for name, (h, t) in CENTER.items():
        out[name] = (h, t, PARENT[name], name in CONNECTED)
    for side in ("R", "L"):
        conv = (lambda p: p) if side == "R" else mirror
        for base, (h, t) in RIGHT.items():
            parent = PARENT[base]
            parent = parent if parent in CENTER else f"{parent}.{side}"
            out[f"{base}.{side}"] = (conv(h), conv(t), parent, base in CONNECTED)
        for finger, pts in FINGERS.items():
            for i in range(3):
                parent = f"hand.{side}" if i == 0 else f"{finger}.0{i}.{side}"
                out[f"{finger}.0{i + 1}.{side}"] = (conv(pts[i]), conv(pts[i + 1]), parent, i > 0)
    return out


def snap_joints(table, vertices):
    """Re-centre the SNAP joints on the cross-section of the mesh (vertices: (V, 3) numpy, world)."""
    import numpy as np

    joints = {}
    for base, end in SNAP:
        for side in (("",) if base in CENTER else (".R", ".L")):
            name = base + side
            head, tail, _p, _c = table[name]
            p = np.asarray(head if end == 0 else tail, dtype=np.float64)
            d = np.asarray(tail, dtype=np.float64) - np.asarray(head, dtype=np.float64)
            d /= np.linalg.norm(d)
            rel = vertices - p
            along = rel @ d
            perp = rel - np.outer(along, d)
            mask = (np.abs(along) < SNAP_SLAB) & (np.linalg.norm(perp, axis=1) < SNAP_RADIUS)
            if mask.sum() >= 6:
                joints[(name, end)] = tuple(p + perp[mask].mean(axis=0))
    # apply: a joint is shared by a bone's tail and its connected children's heads
    new = dict(table)
    for (name, end), q in joints.items():
        h, t, parent, connected = new[name]
        new[name] = (q, t, parent, connected) if end == 0 else (h, q, parent, connected)
        if end == 1:
            for child, (ch, ct, cp, cc) in list(new.items()):
                if cp == name and cc:
                    new[child] = (q, ct, cp, cc)
        elif connected and parent is not None:
            ph, pt, pp, pc = new[parent]
            new[parent] = (ph, q, pp, pc)
    return new


def _weight_orphans(ob, rig):
    """Vertices the heat weighting left without weights (small islands) go fully to the nearest deform
    bone segment (deterministic). Returns how many vertices were fixed."""
    import numpy as np

    deform = [b for b in rig.data.bones if b.use_deform]
    mw = rig.matrix_world
    seg = [(np.array(mw @ b.head_local), np.array(mw @ b.tail_local), b.name) for b in deform]
    obw = np.array(ob.matrix_world)
    fixed = 0
    for v in ob.data.vertices:
        if any(g.weight > 0.0 for g in v.groups):
            continue
        p = obw[:3, :3] @ np.array(v.co) + obw[:3, 3]
        best, best_d = None, None
        for a, b, name in seg:
            ab = b - a
            t = float(np.clip(np.dot(p - a, ab) / max(float(np.dot(ab, ab)), 1e-12), 0.0, 1.0))
            d = float(np.linalg.norm(a + t * ab - p))
            if best_d is None or d < best_d:
                best, best_d = name, d
        vg = ob.vertex_groups.get(best) or ob.vertex_groups.new(name=best)
        vg.add([v.index], 1.0, 'REPLACE')
        fixed += 1
    return fixed


def create_rig(scene, table, name=RIG_NAME):
    """Armature object from a bone table: deform bones = controls, quaternions; ``root`` translation only,
    ``hips`` translation + rotation, every other bone rotation only (ADR 0014)."""
    import bpy

    arm = bpy.data.armatures.new(name)
    rig = bpy.data.objects.new(name, arm)
    scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    for ob in scene.objects:
        ob.select_set(False)
    rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones
    for bone_name, (h, t, _p, _c) in table.items():
        b = eb.new(bone_name)
        b.head, b.tail = h, t
    for bone_name, (_h, _t, parent, connected) in table.items():
        if parent:
            eb[bone_name].parent = eb[parent]
            eb[bone_name].use_connect = connected
    for b in eb:
        b.use_deform = b.name != "root"
    bpy.ops.armature.select_all(action='SELECT')
    bpy.ops.armature.calculate_roll(type='GLOBAL_NEG_Y')
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        if pb.name == "root":
            pb.lock_rotation = (True, True, True)
            pb.lock_rotation_w = True
        elif pb.name != "hips":
            pb.lock_location = (True, True, True)
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.display_type = 'OCTAHEDRAL'
    rig.show_in_front = True
    return rig


def add_test_action(rig, scene):
    """The small deterministic Action of the test asset (TEST_KEYS rotations, TEST_HIPS location)."""
    import bpy
    from bpy_extras import anim_utils

    action = bpy.data.actions.new(ACTION_NAME)
    slot = action.slots.new(id_type='OBJECT', name=rig.name)
    adt = rig.animation_data_create()
    adt.action, adt.action_slot = action, slot
    cb = anim_utils.action_ensure_channelbag_for_slot(action, slot)
    animated = sorted({b for keys in TEST_KEYS.values() for b in keys})
    for bone in animated:
        for i in range(4):
            fc = cb.fcurves.ensure(f'pose.bones["{bone}"].rotation_quaternion', index=i, group_name=bone)
            for frame, keys in TEST_KEYS.items():
                fc.keyframe_points.insert(frame, keys.get(bone, (1.0, 0.0, 0.0, 0.0))[i], options={'FAST'})
            fc.update()
    for i in range(3):
        fc = cb.fcurves.ensure('pose.bones["hips"].location', index=i, group_name="hips")
        for frame, loc in TEST_HIPS.items():
            fc.keyframe_points.insert(frame, loc[i], options={'FAST'})
        fc.update()
    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.frame_set(FRAME_START)
    scene["asc_asset_rig"] = rig.name
    return action


def build(output, test_output=None):
    import bpy
    import numpy as np

    scene = bpy.context.scene
    meshes = [ob for ob in scene.objects if ob.type == 'MESH']
    body = max(meshes, key=lambda ob: len(ob.data.vertices))
    co = np.empty(len(body.data.vertices) * 3)
    body.data.vertices.foreach_get("co", co)
    mw = np.array(body.matrix_world)
    verts = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    table = snap_joints(bone_table(), verts)
    rig = create_rig(scene, table)

    # bind every mesh with automatic weights (visibility kept as in the source)
    hidden = {ob.name: ob.hide_get() for ob in meshes}
    for ob in meshes:
        ob.hide_set(False)
        ob.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    report = {}
    for ob in meshes:
        ob.select_set(False)
        ob.hide_set(hidden[ob.name])
        report[ob.name] = (_weight_orphans(ob, rig), len(ob.data.vertices))
    scene["asc_basic_rig_version"] = SCRIPT_VERSION
    scene["asc_basic_rig"] = rig.name
    bpy.ops.wm.save_as_mainfile(filepath=output, copy=True)
    print(f"[basic-rig] wrote {output} ({len(table)} bones) weights: {report}")

    if test_output:
        add_test_action(rig, scene)
        bpy.ops.wm.save_as_mainfile(filepath=test_output, copy=True)
        print(f"[basic-rig] wrote {test_output} (action {ACTION_NAME!r})")


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--test-output", default=None)
    args = parser.parse_args(argv)
    build(args.output, args.test_output)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
