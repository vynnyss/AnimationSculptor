# SPDX-License-Identifier: GPL-3.0-or-later
"""Public test rig, generated at test time (no binary in the repository, works on CI).

Rigify "Human" metarig → ``pose.rigify_generate`` in the current (background) Blender, plus a small
literal animation on translation controls. Distinct from the user's character asset
(``tests/assets/local/attack_test.blend``), which never leaves the user's machine.
"""

import addon_utils
import bpy
from bpy_extras import anim_utils

RIG_NAME = "rig"
ACTION_NAME = "asc_public_test"
FRAME_START, FRAME_END = 1, 24
KEY_FRAMES = (1, 12, 24)

# bone -> channel -> {frame: values}; translation controls the sculpt tool targets first
KEYS = {
    "hand_ik.L": {
        "location": {1: (0.0, 0.0, 0.0), 12: (0.15, -0.35, 0.40), 24: (-0.05, -0.10, 0.10)},
        "rotation_quaternion": {1: (1.0, 0.0, 0.0, 0.0), 12: (0.9239, 0.3827, 0.0, 0.0), 24: (1.0, 0.0, 0.0, 0.0)},
    },
    "foot_ik.R": {
        "location": {1: (0.0, 0.0, 0.0), 12: (0.0, -0.25, 0.12), 24: (0.0, -0.30, 0.0)},
    },
    "torso": {
        "location": {1: (0.0, 0.0, 0.0), 12: (0.0, -0.10, -0.08), 24: (0.0, -0.15, 0.0)},
    },
    "upper_arm_fk.R": {
        "rotation_quaternion": {1: (1.0, 0.0, 0.0, 0.0), 12: (0.9659, 0.0, 0.0, 0.2588), 24: (1.0, 0.0, 0.0, 0.0)},
    },
}


def generate(path: str) -> None:
    """Generate the rig in a separate background Blender (clean factory state for Rigify)."""
    import subprocess

    cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python", __file__, "--", path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"public rig generation failed:\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}")


def build(path: str) -> None:
    """Generate the rig into the current (fresh, factory) file and save it to ``path``."""
    addon_utils.enable("rigify", default_set=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    bpy.ops.object.armature_human_metarig_add()
    metarig = bpy.context.active_object
    bpy.ops.pose.rigify_generate()
    rig = bpy.data.objects[RIG_NAME]
    bpy.data.objects.remove(metarig)

    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.frame_set(FRAME_START)

    action = bpy.data.actions.new(ACTION_NAME)
    slot = action.slots.new(id_type='OBJECT', name=rig.name)
    adt = rig.animation_data_create()
    adt.action = action
    adt.action_slot = slot
    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
    for bone, channels in KEYS.items():
        pb = rig.pose.bones[bone]
        for channel, frames in channels.items():
            size = len(next(iter(frames.values())))
            for index in range(size):
                fc = channelbag.fcurves.ensure(pb.path_from_id(channel), index=index, group_name=bone)
                for frame, values in frames.items():
                    fc.keyframe_points.insert(frame, values[index], options={'FAST'})
                fc.update()

    for ob in bpy.data.objects:
        if ob is not rig:
            ob.hide_viewport = ob.hide_render = True
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    scene["asc_public_rig"] = rig.name
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)


if __name__ == "__main__":
    import sys

    build(sys.argv[sys.argv.index("--") + 1])
