# SPDX-License-Identifier: GPL-3.0-or-later
"""Unkeyed pose edits survive the trails (maintainer report on PR #11): after Breakdowner/Push/Relax or a
plain G, the pose must stay until the user keys it — trail recomputation must never re-apply the Action."""

import os
import time
from pathlib import Path

import bpy
from mathutils import Vector

ASSET = Path(os.environ.get("ASC_REPO_ROOT", ".")) / "tests" / "assets" / "local" / "attack_test.blend"


def _wait(cond, timeout=8.0, step=0.1):
    t_end = time.time() + timeout
    while not cond() and time.time() < t_end:
        yield step


def scenario(h):
    if ASSET.exists():
        path, bones, frame = str(ASSET), ("hand_ik.R", "torso"), 13
    else:
        path, bones, frame = os.environ["ASC_UI_RIG"], ("hand_ik.L", "torso"), 6
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    yield 0.5
    provider = h.addon("trails.provider")
    engine = h.addon("trails.lmp.engine")
    tool_id = h.addon("interaction.sculpt_tool").TOOL_ID
    scene = bpy.context.scene
    rig = next(ob for ob in bpy.data.objects if ob.type == 'ARMATURE' and bones[0] in ob.pose.bones and not ob.hide_viewport)
    bpy.context.view_layer.objects.active = rig
    with h.override():
        bpy.ops.object.mode_set(mode='POSE')
        bpy.ops.wm.tool_set_by_id(name=tool_id)
    for pb in rig.pose.bones:
        pb.select = pb.name in bones
    rig.data.bones.active = rig.data.bones[bones[0]]
    scene.frame_set(frame)
    yield 0.5
    ready = lambda: all((t := provider.get_trail(rig, b)) is not None and t.complete for b in bones)  # noqa: E731
    yield from _wait(ready)

    def pose():
        return [tuple(rig.pose.bones[b].location) for b in bones]

    # Relax (a native pose-slide operator), confirmed without keying
    animated = pose()
    with h.override():
        result = bpy.ops.pose.relax('EXEC_DEFAULT', factor=1.0)
    edited = pose()
    h.check("Relax changed the pose", 'FINISHED' in result and edited != animated, (result, animated, edited))
    yield 1.5                                     # let the trail engine react (debounce + recompute)
    yield from _wait(lambda: engine.STATE.job is None and engine.STATE.timer_fn is None, timeout=5.0)
    h.check("unkeyed Relax pose survives the trail update", pose() == edited, (pose(), edited, engine.STATE.last_engine_info))

    # a plain unkeyed move, then a forced Refresh
    rig.pose.bones[bones[0]].location.x += 0.1
    moved = pose()
    yield 1.0
    with h.override():
        bpy.ops.asc_trails.refresh()
    yield 0.5
    h.check("unkeyed move survives Refresh", pose() == moved, (pose(), moved, engine.STATE.last_engine_info))

    # keying then keeps it as animation
    with h.override():
        bpy.ops.anim.keyframe_insert_by_name(type="LocRotScale")
    yield 1.0
    scene.frame_set(frame + 1)
    scene.frame_set(frame)
    h.check("after I the pose is the animation", all((Vector(a) - Vector(b)).length < 1e-5 for a, b in zip(pose(), moved)))
