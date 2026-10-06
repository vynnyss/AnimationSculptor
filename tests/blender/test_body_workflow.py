# SPDX-License-Identifier: GPL-3.0-or-later
"""Corpo-mode workflow after the maintainer's walk cycle (0.9.0): elbows never flip between frames,
Smooth works on the whole limb, a character without animation can be sculpted from zero, gestures never
write keys before frame 0, and the onion/trail targets do not depend on selecting the skeleton."""

import importlib
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import body_mesh  # noqa: E402

ARM_R = ["upper_arm.R", "forearm.R", "hand.R"]
WALK = [(1, (0, -0.3, 0)), (7, (0, 0.3, 0.1)), (13, (0, -0.3, 0)), (19, (0, 0.3, 0.1)), (25, (0, -0.3, 0)),
        (13, (0.1, 0.2, -0.2)), (7, (0, 0, 0.3))]


def _mod(addon, name):
    return importlib.import_module(f"{addon.__name__}.{name}")


def _elbow_jumps(rig, frames):
    pts = []
    for f in frames:
        bpy.context.scene.frame_set(f)
        pts.append(np.array(rig.matrix_world @ rig.pose.bones["forearm.R"].head))
    return np.linalg.norm(np.diff(np.array(pts), axis=0), axis=1)


def _drag(addon, rig, frame, delta, radius=12):
    ee = _mod(addon, "interaction.ephemeral_edit")
    bpy.context.scene.frame_set(frame)
    tip = np.array(rig.matrix_world @ rig.pose.bones["hand.R"].tail)
    edit = ee.ChainEdit(rig, ARM_R, frame, radius, radius, point_world=tuple(tip), point_bone="hand.R")
    assert edit.editable, edit.reason
    edit.apply(np.array(delta, dtype=float))
    edit.finish()
    return edit


def _keys(rig, prefix):
    cb = _mod_action_io().channelbag(rig)
    return [k.co.x for fc in cb.fcurves if fc.data_path.startswith(prefix) for k in fc.keyframe_points]


def _mod_action_io():
    name = next(m for m in sys.modules if m.endswith("animation_sculptor.anim.action_io"))
    return sys.modules[name]


def test_walk_drags_never_flip_the_elbow(simple_rig, addon):
    """The maintainer's walk cycle: several Membro drags on the hand with a wide window. The two-bone IK
    took the elbow's side from each frame's plane, which is noise for a nearly straight arm: the elbow
    jumped 0.5–0.7 m between frames. Now it bends to the rest pose's side (hinge = forearm X axis)."""
    rig = simple_rig
    frames = list(range(-12, 40))
    start = _elbow_jumps(rig, frames).max()
    for frame, delta in WALK:
        _drag(addon, rig, frame, delta)
        assert _elbow_jumps(rig, frames).max() < max(0.2, 3.0 * start)


def test_rest_bend_sign_reads_the_natural_side(simple_rig, addon):
    ee = _mod(addon, "interaction.ephemeral_edit")
    assert ee.rest_bend_sign(simple_rig, ["hand.R"]) == 1.0           # one bone: no middle joint
    assert ee.rest_bend_sign(simple_rig, ARM_R) in (1.0, -1.0)


def test_sculpt_from_zero_makes_the_action(simple_rig, addon):
    action_io = _mod(addon, "anim.action_io")
    rig = simple_rig
    rig.animation_data.action = None
    assert action_io.refusal(rig, rig.pose.bones["hand.R"], "rotation_quaternion")
    name = action_io.ensure_action(rig)
    assert name and rig.animation_data.action.name == name and rig.animation_data.action_slot is not None
    assert action_io.ensure_action(rig) == ""                          # already there: nothing new
    _drag(addon, rig, 12, (0.0, -0.2, 0.1), radius=4)
    assert len(action_io.channelbag(rig).fcurves) > 0
    action_io.drop_if_empty(rig, name)                                 # written: kept
    assert bpy.data.actions.get(name) is not None


def test_an_unused_new_action_is_dropped(simple_rig, addon):
    action_io = _mod(addon, "anim.action_io")
    rig = simple_rig
    rig.animation_data.action = None
    name = action_io.ensure_action(rig)
    action_io.drop_if_empty(rig, name)
    assert bpy.data.actions.get(name) is None and rig.animation_data.action is None


def test_gestures_never_key_before_frame_0(simple_rig, addon):
    rig = simple_rig
    scene = bpy.context.scene
    assert scene.asc_sculpt.clip_negative                              # on by default
    _drag(addon, rig, 2, (0.0, -0.2, 0.1), radius=10)
    assert min(_keys(rig, 'pose.bones["upper_arm.R"]')) >= 0.0
    scene.asc_sculpt.clip_negative = False
    _drag(addon, rig, 2, (0.0, 0.2, 0.0), radius=10)
    assert min(_keys(rig, 'pose.bones["upper_arm.R"]')) < 0.0


def test_smooth_on_the_limb_calms_a_jittery_elbow(simple_rig, addon):
    """Smooth used to touch only the bone under the cursor; the elbow's path depends on the upper arm."""
    smooth_edit = _mod(addon, "interaction.smooth_edit")
    adapter = _mod(addon, "rig").get_adapter(simple_rig)
    rig = simple_rig
    rng = np.random.default_rng(7)
    for frame in range(2, 24, 2):                                      # a jittery arm, like the walk cycle
        _drag(addon, rig, frame, tuple(rng.normal(scale=0.15, size=3)), radius=0)
    frames = list(range(4, 21))
    noisy = _elbow_jumps(rig, frames)
    bones, why = adapter.ephemeral_chain(rig, "forearm.R", "LIMB")
    assert not why and "upper_arm.R" in bones
    edit = smooth_edit.SmoothEdit(rig, bones, 12, 10, 10, strength=0.5, sigma=1.5)
    assert edit.editable
    edit.apply_passes(30)
    calm = _elbow_jumps(rig, frames)
    assert np.std(np.diff(calm)) < 0.5 * np.std(np.diff(noisy))


def test_body_mode_targets_ignore_the_selection(simple_rig, addon):
    provider = _mod(addon, "trails.provider")
    engine = provider.engine
    rig = simple_rig
    scene = bpy.context.scene
    body = body_mesh.add_skinned_body(rig) if bpy.data.objects.get(body_mesh.BODY_NAME) is None else \
        bpy.data.objects[body_mesh.BODY_NAME]
    vl = bpy.context.view_layer
    s = scene.asc_trails
    s.onion_show = True
    s.path_show = True
    for ob in vl.objects:
        ob.select_set(False)
    vl.objects.active = body                                           # the mesh, not the skeleton
    scene.asc_sculpt.interaction_mode = 'BODY'
    keys = {(t.obj_name, t.bone or "", t.want_path, t.want_onion) for t in engine.resolve_targets(scene, vl)}
    assert (body.name, "", False, True) in keys                        # onion without touching the skeleton
    provider.focus_part(rig, "forearm.R")
    keys = {(t.obj_name, t.bone or "", t.want_path) for t in engine.resolve_targets(scene, vl)}
    assert (rig.name, "forearm.R", True) in keys                       # the part touched shows its trail
    sig = engine.selection_signature(scene, vl)
    provider.focus_part(rig, "hand.R")
    assert engine.selection_signature(scene, vl) != sig                # a new part re-targets
    scene.asc_sculpt.interaction_mode = 'TRAIL'                        # Trail: the part picked + selected bones
    rig.pose.bones["thigh.L"].select = True
    bpy.context.view_layer.objects.active = rig
    if rig.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')
    keys = {(t.obj_name, t.bone or "") for t in engine.resolve_targets(scene, vl)}
    assert {(rig.name, "hand.R"), (rig.name, "thigh.L")} <= keys
    scene.asc_sculpt.trail_all = True                                  # Todas: every part
    keys = {t.bone for t in engine.resolve_targets(scene, vl) if t.bone}
    assert {"hips", "head", "foot.R", "index.02.L"} <= keys
    scene.asc_sculpt.trail_all = False
    s.target_mode = 'PINNED'
    assert provider._body_targets(scene, vl) is None                   # pinned: the user's explicit choice
    s.target_mode = 'SELECTED'
    provider.FOCUS.clear()


def test_animate_enters_pose_mode_from_the_mesh(simple_rig, addon):
    rig = simple_rig
    body = bpy.data.objects.get(body_mesh.BODY_NAME) or body_mesh.add_skinned_body(rig)
    vl = bpy.context.view_layer
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for ob in vl.objects:
        ob.select_set(False)
    body.select_set(True)
    vl.objects.active = body
    rig.hide_set(True)                                                 # the skeleton hidden after skinning
    sculpt_tool = _mod(addon, "interaction.sculpt_tool")
    assert sculpt_tool.ASC_OT_animate.character(bpy.context) == rig
    win = bpy.context.window_manager.windows[0] if bpy.context.window_manager.windows else None
    area = next((a for a in win.screen.areas if a.type == 'VIEW_3D'), None) if win else None
    if area is None:                                                   # background: no 3D view to run in
        return
    with bpy.context.temp_override(window=win, area=area):
        assert bpy.ops.asc.animate() == {'FINISHED'}
    assert vl.objects.active == rig and rig.mode == 'POSE' and rig.visible_get()


def _tail_path(rig, bone, frames):
    out = []
    for f in frames:
        bpy.context.scene.frame_set(f)
        out.append(np.array(rig.matrix_world @ rig.pose.bones[bone].tail))
    return np.array(out)


def test_trail_smooth_smooths_the_path_itself(simple_rig, addon):
    """Smooth "Trail": the hand's world path is Gaussian-smoothed and the arm solved to follow it."""
    ee = _mod(addon, "interaction.ephemeral_edit")
    rig = simple_rig
    rng = np.random.default_rng(11)
    for frame in range(2, 24, 2):                                      # a jittery hand path
        _drag(addon, rig, frame, tuple(rng.normal(scale=0.12, size=3)), radius=0)
    frames = list(range(0, 27))
    before = _tail_path(rig, "hand.R", frames)
    bpy.context.scene.frame_set(12)
    point = rig.matrix_world @ rig.pose.bones["hand.R"].tail
    edit = ee.TrailSmoothEdit(rig, ARM_R, 12, 8, 8, point_world=tuple(point), point_bone="hand.R")
    assert edit.editable, edit.reason
    edit.apply_passes(20)
    after = _tail_path(rig, "hand.R", frames)
    inside = [i for i, f in enumerate(frames) if 6 <= f <= 18]
    rough = lambda p: float(np.linalg.norm(np.diff(p[inside], n=2, axis=0), axis=1).mean())   # noqa: E731
    assert rough(after) < 0.5 * rough(before)
    outside = [i for i, f in enumerate(frames) if f < 3 or f > 21]   # beyond the window: untouched
    assert np.abs(after[outside] - before[outside]).max() < 1e-5
    # the hand lands on the smoothed path (the IK reaches it)
    j = list(edit.frames).index(12)
    assert np.linalg.norm(after[frames.index(12)] - edit._path[j]) < 1e-3
    edit.apply_passes(0)                                               # back to the original, bit for bit
    assert np.abs(_tail_path(rig, "hand.R", frames) - before).max() < 1e-6


def _pose_drag(addon, rig, frame, delta, radius=12, influence=0.25):
    ee = _mod(addon, "interaction.ephemeral_edit")
    bpy.context.scene.frame_set(frame)
    tip = np.array(rig.matrix_world @ rig.pose.bones["hand.R"].tail)
    edit = ee.ChainEdit(rig, ARM_R, frame, radius, radius, point_world=tuple(tip), point_bone="hand.R",
                        key_mode=ee.POSE, pose_influence=influence)
    assert edit.editable, edit.reason
    edit.apply(np.array(delta, dtype=float))
    edit.finish()
    return edit


def _key_frames(rig, bone):
    cb = _mod_action_io().channelbag(rig)
    return sorted({round(k.co.x) for fc in cb.fcurves if fc.data_path.startswith(f'pose.bones["{bone}"]')
                   for k in fc.keyframe_points})


def test_pose_to_pose_keys_only_the_posed_frame_and_the_poses(simple_rig, addon):
    """ADR 0015: a drag at a frame without a key inserts one there; the neighbouring poses move by
    falloff × influence; no dense keys."""
    rig = simple_rig
    poses = _mod(addon, "interaction.ephemeral_edit").pose_frames(rig)
    assert poses == [1, 12, 24]                                        # the test Action's poses
    _pose_drag(addon, rig, 6, (0.0, -0.15, 0.1))
    for bone in ARM_R:
        assert _key_frames(rig, bone) == [1, 6, 12, 24], bone          # one new key, at 6 only
    bpy.context.scene.frame_set(6)
    tip = np.array(rig.matrix_world @ rig.pose.bones["hand.R"].tail)
    assert tip is not None


def test_pose_influence_zero_locks_the_other_poses(simple_rig, addon):
    rig = simple_rig
    frames = [1, 12, 24]
    before = _tail_path(rig, "hand.R", frames)
    _pose_drag(addon, rig, 6, (0.0, -0.15, 0.1), influence=0.0)
    assert np.abs(_tail_path(rig, "hand.R", frames) - before).max() < 1e-5
    _pose_drag(addon, rig, 8, (0.0, 0.1, 0.0), influence=0.5)
    moved = np.linalg.norm(_tail_path(rig, "hand.R", frames) - before, axis=1)
    assert moved[1] > 1e-4                                             # pose 12 (in the window) follows a bit


def test_pose_drag_reaches_the_target_at_the_posed_frame(simple_rig, addon):
    rig = simple_rig
    bpy.context.scene.frame_set(12)
    tip0 = np.array(rig.matrix_world @ rig.pose.bones["hand.R"].tail)
    delta = np.array((0.0, -0.12, 0.08))
    _pose_drag(addon, rig, 12, delta)
    bpy.context.scene.frame_set(12)
    tip = np.array(rig.matrix_world @ rig.pose.bones["hand.R"].tail)
    assert np.linalg.norm(tip - (tip0 + delta)) < 1e-3


def test_key_pose_keys_the_whole_character(simple_rig, addon):
    rig = simple_rig
    rig.animation_data.action = None
    scene = bpy.context.scene
    scene.frame_set(7)
    bpy.context.view_layer.objects.active = rig
    for pb in rig.pose.bones:
        pb.select = False                                              # nothing selected: still the whole pose
    assert bpy.ops.asc.key_pose() == {'FINISHED'}
    keyed = {fc.data_path.split('"')[1] for fc in _mod_action_io().channelbag(rig).fcurves}
    assert {"hips", "spine", "head", "hand.R", "thigh.L", "index.02.R"} <= keyed
    assert _mod(addon, "interaction.ephemeral_edit").pose_frames(rig) == [7]
