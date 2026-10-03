# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate the local attack regression asset from the user's Rigify character.

Normally launched by ``python scripts/dev.py assets``, which runs, inside Blender 5.2:

    blender --background <character.blend> --factory-startup --python scripts/make_test_assets.py -- \
        --output tests/assets/local/attack_test.blend [--preview <dir>]

The character file is only read: the result is written with ``save_as_mainfile(copy=True)``
to a different path. The copy gets:

- every object except the Rigify control rig hidden in viewport and render (meshes, sword,
  helper armatures), so motion trails are easy to see;
- a new Slotted Action ``asc_test_attack`` assigned to the rig (slot ``OB<rig name>``), keyed with
  the literal key poses below (Bézier, auto-clamped handles). The character's previous actions are
  kept untouched (fake user) and fingerprinted;
- timeline markers for the key poses and scene custom properties ``asc_asset_version`` & co.

Key poses were authored as world-space intents (hand/feet positions, blade direction, torso
yaw/pitch, head looking at the target) on ``Vale_Rig_Animations.blend`` and converted once to the
local channel values below. Everything is literal: no randomness, no solving at generation time.
The right arm is IK (sword hand); the left arm is switched to FK (``IK_FK = 1``) so FK controls are
exercised too.

Also importable from tests (``import make_test_assets``) for the constants and ``action_fingerprint``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ACTION_NAME = "asc_test_attack"
SCRIPT_VERSION = 1
FRAME_START, FRAME_END = 1, 40

# frame -> phase name (also written as timeline markers)
KEY_POSES = {
    1: "idle",
    10: "anticipation",
    16: "attack",
    18: "impact",
    26: "follow_through",
    40: "recovery",
}

# IK/FK switches keyed once at the first frame (Rigify convention: 0 = IK, 1 = FK).
IK_FK = {
    "upper_arm_parent.R": 0.0,
    "upper_arm_parent.L": 1.0,
    "thigh_parent.R": 0.0,
    "thigh_parent.L": 0.0,
}

# Local pose-bone channel values per key frame (Rigify control rig, Blender 5.2.1).
# Quaternions are already sign-continuous between consecutive keys (shortest path).
POSES = {
    1: {
        "root": {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0)},
        "torso": {"location": (0.0, 0.0589, 0.0378), "rotation_quaternion": (0.934, 0.0, 0.0, -0.3572)},
        "chest": {"rotation_quaternion": (0.9884, 0.0033, 0.0201, -0.1504)},
        "head": {"rotation_quaternion": (0.9294, 0.0789, 0.3592, -0.0305)},
        "hand_ik.R": {"location": (0.1018, 0.3469, 0.0585), "rotation_quaternion": (0.9281, -0.2554, 0.2708, 0.0059)},
        "upper_arm_ik_target.R": {"location": (-0.2826, -0.1958, -0.1128)},
        "foot_ik.L": {"location": (-0.1827, -0.13, 0.0588), "rotation_quaternion": (0.9235, 0.2809, 0.004, -0.2612)},
        "foot_ik.R": {"location": (0.2701, 0.2115, -0.0038), "rotation_quaternion": (0.9448, 0.0, 0.0, -0.3278)},
        "thigh_ik_target.L": {"location": (0.1016, 0.1557, -0.0587)},
        "thigh_ik_target.R": {"location": (0.0323, 0.0577, -0.0541)},
        "upper_arm_fk.L": {"rotation_quaternion": (0.9767, -0.1841, 0.1014, -0.0436)},
        "forearm_fk.L": {"rotation_quaternion": (0.9424, 0.3345, 0.0, 0.0)},
        "hand_fk.L": {"rotation_quaternion": (0.9618, 0.0012, -0.2583, 0.0912)},
    },
    10: {
        "root": {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0)},
        "torso": {"location": (0.0166, 0.1146, -0.0199), "rotation_quaternion": (0.8564, -0.0374, 0.0225, -0.5145)},
        "chest": {"rotation_quaternion": (0.9905, -0.0432, 0.0057, -0.1304)},
        "head": {"rotation_quaternion": (0.8558, 0.0996, 0.5075, -0.0145)},
        "hand_ik.R": {"location": (0.1577, 0.2993, 0.7785), "rotation_quaternion": (-0.0454, -0.1826, 0.9816, 0.0313)},
        "upper_arm_ik_target.R": {"location": (-0.2492, -1.3096, 0.1733)},
        "foot_ik.L": {"location": (-0.1801, -0.1672, 0.1044), "rotation_quaternion": (0.9235, 0.2809, 0.004, -0.2612)},
        "foot_ik.R": {"location": (0.2701, 0.2115, -0.0038), "rotation_quaternion": (0.9448, 0.0, 0.0, -0.3278)},
        "thigh_ik_target.L": {"location": (0.4455, 0.4047, -0.0531)},
        "thigh_ik_target.R": {"location": (0.4245, 0.0063, -0.0866)},
        "upper_arm_fk.L": {"rotation_quaternion": (0.9402, -0.0493, -0.1675, 0.2925)},
        "forearm_fk.L": {"rotation_quaternion": (0.9676, 0.2523, 0.0, 0.0)},
        "hand_fk.L": {"rotation_quaternion": (0.8847, -0.2631, -0.3196, -0.2143)},
    },
    16: {
        "root": {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0)},
        "torso": {"location": (-0.0034, -0.0754, -0.0599), "rotation_quaternion": (0.9636, 0.0674, -0.0181, -0.2582)},
        "chest": {"rotation_quaternion": (0.9981, 0.0436, 0.0019, 0.0436)},
        "head": {"rotation_quaternion": (0.9618, 0.0018, 0.2711, -0.0386)},
        "hand_ik.R": {"location": (0.2377, -0.2107, 0.6185), "rotation_quaternion": (0.2395, -0.1184, 0.4709, -0.8408)},
        "upper_arm_ik_target.R": {"location": (-0.4846, -0.4864, 0.02)},
        "foot_ik.L": {"location": (-0.1601, -0.4672, 0.0014), "rotation_quaternion": (0.9914, 0.0, 0.0, -0.1305)},
        "foot_ik.R": {"location": (0.2701, 0.2115, -0.0038), "rotation_quaternion": (0.9448, 0.0, 0.0, -0.3278)},
        "thigh_ik_target.L": {"location": (0.2443, 0.0057, 0.1117)},
        "thigh_ik_target.R": {"location": (-0.2222, 0.2131, 0.1527)},
        "upper_arm_fk.L": {"rotation_quaternion": (0.921, -0.2715, 0.2668, 0.0833)},
        "forearm_fk.L": {"rotation_quaternion": (0.9042, 0.4271, 0.0, 0.0)},
        "hand_fk.L": {"rotation_quaternion": (0.9626, 0.175, -0.2059, -0.0172)},
    },
    18: {
        "root": {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0)},
        "torso": {"location": (-0.0034, -0.1854, -0.1199), "rotation_quaternion": (0.9839, 0.1558, -0.0136, -0.0861)},
        "chest": {"rotation_quaternion": (0.986, 0.1036, 0.0136, 0.1298)},
        "head": {"rotation_quaternion": (0.9904, -0.099, 0.0945, -0.0206)},
        "hand_ik.R": {"location": (0.3677, -0.5607, 0.0985), "rotation_quaternion": (0.1631, 0.1799, -0.3518, -0.904)},
        "upper_arm_ik_target.R": {"location": (-0.264, -0.2252, -0.3792)},
        "foot_ik.L": {"location": (-0.1601, -0.4672, 0.0014), "rotation_quaternion": (0.9914, 0.0, 0.0, -0.1305)},
        "foot_ik.R": {"location": (0.2701, 0.2115, -0.0038), "rotation_quaternion": (0.9448, 0.0, 0.0, -0.3278)},
        "thigh_ik_target.L": {"location": (-0.1323, -0.0912, 0.3671)},
        "thigh_ik_target.R": {"location": (-0.4642, 0.5264, 0.2451)},
        "upper_arm_fk.L": {"rotation_quaternion": (0.8755, -0.0289, 0.48, 0.0477)},
        "forearm_fk.L": {"rotation_quaternion": (0.985, -0.1723, 0.0, 0.0)},
        "hand_fk.L": {"rotation_quaternion": (0.7341, 0.674, -0.082, 0.0083)},
    },
    26: {
        "root": {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0)},
        "torso": {"location": (0.0166, -0.2254, -0.1399), "rotation_quaternion": (0.9779, 0.1901, 0.0166, 0.0856)},
        "chest": {"rotation_quaternion": (0.9793, 0.0953, 0.0609, 0.168)},
        "head": {"rotation_quaternion": (0.984, -0.1399, -0.1074, 0.0266)},
        "hand_ik.R": {"location": (0.5377, -0.3807, -0.1615), "rotation_quaternion": (0.5428, 0.4414, -0.4804, -0.5289)},
        "upper_arm_ik_target.R": {"location": (-0.016, -0.2674, -0.506)},
        "foot_ik.L": {"location": (-0.1601, -0.4672, 0.0014), "rotation_quaternion": (0.9914, 0.0, 0.0, -0.1305)},
        "foot_ik.R": {"location": (0.2701, 0.2115, -0.0038), "rotation_quaternion": (0.9448, 0.0, 0.0, -0.3278)},
        "thigh_ik_target.L": {"location": (-0.5062, -0.0947, 0.4641)},
        "thigh_ik_target.R": {"location": (-0.5645, 0.8439, 0.1677)},
        "upper_arm_fk.L": {"rotation_quaternion": (0.7999, 0.0448, 0.5743, 0.1685)},
        "forearm_fk.L": {"rotation_quaternion": (0.985, -0.1723, 0.0, 0.0)},
        "hand_fk.L": {"rotation_quaternion": (0.7371, 0.6728, -0.0452, 0.0451)},
    },
    40: {
        "root": {"location": (0.0, 0.0, 0.0), "rotation_quaternion": (1.0, 0.0, 0.0, 0.0)},
        "torso": {"location": (-0.0034, -0.1254, -0.0199), "rotation_quaternion": (0.9449, 0.033, -0.0114, -0.3254)},
        "chest": {"rotation_quaternion": (0.9987, 0.0262, -0.0011, -0.0436)},
        "head": {"rotation_quaternion": (0.9403, 0.0427, 0.3354, -0.0388)},
        "hand_ik.R": {"location": (0.1018, 0.2469, 0.0585), "rotation_quaternion": (0.9281, -0.2554, 0.2708, 0.0059)},
        "upper_arm_ik_target.R": {"location": (-0.2151, 0.0165, -0.1055)},
        "foot_ik.L": {"location": (-0.1601, -0.4672, 0.0014), "rotation_quaternion": (0.9914, 0.0, 0.0, -0.1305)},
        "foot_ik.R": {"location": (0.2701, 0.2115, -0.0038), "rotation_quaternion": (0.9448, 0.0, 0.0, -0.3278)},
        "thigh_ik_target.L": {"location": (0.3349, 0.1742, -0.0057)},
        "thigh_ik_target.R": {"location": (-0.1423, 0.1994, 0.0598)},
        "upper_arm_fk.L": {"rotation_quaternion": (0.9681, -0.1672, 0.1684, -0.0801)},
        "forearm_fk.L": {"rotation_quaternion": (0.9487, 0.3163, 0.0, 0.0)},
        "hand_fk.L": {"rotation_quaternion": (0.9792, 0.0743, -0.1779, 0.0624)},
    },
}

KEYED_BONES = tuple(POSES[1])

# Preview cameras: (name, location, look-at). The character faces -Y; the sword is on its -X side.
PREVIEW_CAMERAS = (
    ("side", (-5.2, -0.4, 1.3), (0.0, -0.25, 1.15)),
    ("front3q", (2.6, -4.8, 1.6), (0.0, -0.2, 1.15)),
)


def action_fingerprint(action) -> str:
    """Stable hash of every F-Curve key of an action (all slots/layers/strips), rounded to 1e-5."""
    rows = []
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                for fcurve in channelbag.fcurves:
                    keys = [
                        (round(k.co[0], 5), round(k.co[1], 5),
                         round(k.handle_left[0], 5), round(k.handle_left[1], 5),
                         round(k.handle_right[0], 5), round(k.handle_right[1], 5),
                         k.interpolation)
                        for k in fcurve.keyframe_points
                    ]
                    rows.append((channelbag.slot.identifier, fcurve.data_path, fcurve.array_index, keys))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def find_rigify_rig(objects):
    rigs = [ob for ob in objects if ob.type == "ARMATURE" and "rig_id" in ob.data]
    if len(rigs) != 1:
        raise RuntimeError(f"expected exactly one Rigify rig (armature data with 'rig_id'), found {[r.name for r in rigs]}")
    return rigs[0]


def _reset_pose(rig) -> None:
    for pb in rig.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def build(output: str) -> None:
    import bpy
    from bpy_extras import anim_utils

    if bpy.app.version[:2] != (5, 2):
        raise RuntimeError(f"Blender 5.2 required, running {bpy.app.version_string}")
    source = bpy.data.filepath
    if not source:
        raise RuntimeError("open the character .blend first (blender --background <file> --python ...)")
    if os.path.normcase(os.path.abspath(output)) == os.path.normcase(os.path.abspath(source)):
        raise RuntimeError("refusing to overwrite the character file")

    scene = bpy.context.scene
    rig = find_rigify_rig(bpy.data.objects)
    missing = [n for n in (*KEYED_BONES, *IK_FK) if n not in rig.pose.bones]
    if missing:
        raise RuntimeError(f"rig {rig.name!r} lacks controls {missing}")

    # Keep (and fingerprint) every pre-existing action; none of them is modified.
    fingerprints = {}
    for action in bpy.data.actions:
        fingerprints[action.name] = action_fingerprint(action)
        action.use_fake_user = True
    previous = rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else ""

    # Fresh action + slot for the rig.
    adt = rig.animation_data or rig.animation_data_create()
    adt.action = None
    _reset_pose(rig)
    action = bpy.data.actions.new(ACTION_NAME)
    slot = action.slots.new(id_type="OBJECT", name=rig.name)
    adt.action = action
    adt.action_slot = slot
    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)

    for bone in KEYED_BONES:
        for channel in POSES[1][bone]:
            data_path = f'pose.bones["{bone}"].{channel}'
            for index in range(len(POSES[1][bone][channel])):
                fcurve = channelbag.fcurves.new(data_path, index=index, group_name=bone)
                points = fcurve.keyframe_points
                points.add(len(POSES))
                for point, frame in zip(points, sorted(POSES)):
                    point.co = (frame, POSES[frame][bone][channel][index])
                    point.interpolation = "BEZIER"
                    point.handle_left_type = point.handle_right_type = "AUTO_CLAMPED"
                fcurve.update()
    for bone, value in IK_FK.items():
        rig.pose.bones[bone]["IK_FK"] = value
        fcurve = channelbag.fcurves.new(f'pose.bones["{bone}"]["IK_FK"]', index=0, group_name=bone)
        fcurve.keyframe_points.add(1)
        fcurve.keyframe_points[0].co = (FRAME_START, value)
        fcurve.keyframe_points[0].interpolation = "CONSTANT"
        fcurve.update()

    # Only the control rig stays visible.
    for ob in bpy.data.objects:
        if ob is not rig:
            ob.hide_viewport = True
            ob.hide_render = True

    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.timeline_markers.clear()
    for frame, name in KEY_POSES.items():
        scene.timeline_markers.new(name, frame=frame)
    scene.frame_set(FRAME_START)

    scene["asc_asset_version"] = bpy.app.version_string
    scene["asc_asset_script_version"] = SCRIPT_VERSION
    scene["asc_asset_source"] = os.path.basename(source)
    scene["asc_asset_rig"] = rig.name
    scene["asc_asset_previous_action"] = previous
    scene["asc_source_action_fingerprints"] = json.dumps(fingerprints, sort_keys=True)

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output, copy=True, check_existing=False, compress=True)
    print(f"[assets] wrote {output} (action {ACTION_NAME!r}, rig {rig.name!r}, source {os.path.basename(source)!r})")


def render_preview(out_dir: str) -> None:
    """Render each key pose with the meshes visible (in memory only; nothing is saved)."""
    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    for ob in bpy.data.objects:
        if ob.type in {"MESH", "ARMATURE"} and not ob.name.startswith("WGT-") and ob.users_collection:
            if all(not c.hide_render for c in ob.users_collection):
                ob.hide_viewport = ob.hide_render = False
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x, scene.render.resolution_y = 520, 620
    scene.render.image_settings.file_format = "PNG"
    ground = bpy.data.objects.new("asc_preview_ground", bpy.data.meshes.new("asc_preview_ground"))
    ground.data.from_pydata([(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)], [], [(0, 1, 2, 3)])
    scene.collection.objects.link(ground)
    cameras = []
    for name, location, target in PREVIEW_CAMERAS:
        cam = bpy.data.objects.new(f"asc_preview_{name}", bpy.data.cameras.new(name))
        cam.data.lens = 35
        cam.location = location
        cam.rotation_euler = (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(cam)
        cameras.append((name, cam))
    os.makedirs(out_dir, exist_ok=True)
    for frame, phase in KEY_POSES.items():
        scene.frame_set(frame)
        for name, cam in cameras:
            scene.camera = cam
            scene.render.filepath = os.path.join(out_dir, f"f{frame:03d}_{phase}_{name}.png")
            bpy.ops.render.render(write_still=True)
    print(f"[assets] previews in {out_dir}")


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="make_test_assets.py")
    parser.add_argument("--output", required=True)
    parser.add_argument("--preview", help="directory for PNG renders of the key poses (optional)")
    args = parser.parse_args(argv)
    build(args.output)
    if args.preview:
        render_preview(args.preview)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
