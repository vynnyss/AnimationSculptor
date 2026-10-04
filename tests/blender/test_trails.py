# SPDX-License-Identifier: GPL-3.0-or-later
"""Vendored Live Motion Path engine behind ``trails/provider`` (frame-stepping engine in background)."""

import importlib

import bpy
import numpy as np
import pytest

import public_rig as pr


@pytest.fixture
def provider(addon):
    return importlib.import_module(addon.__name__ + ".trails.provider")


@pytest.fixture
def engine(addon):
    return importlib.import_module(addon.__name__ + ".trails.lmp.engine")


def _pin(scene, rig, bones):
    s = scene.asc_trails
    s.pinned.clear()
    for bone in bones:
        item = s.pinned.add()
        item.obj = rig
        item.bone = bone
    s.target_mode = 'PINNED'
    s.path_engine = 'STEP'          # the native solver needs a window (not available in --background)
    s.path_range_mode = 'SCENE'
    s.enabled = True


def _evaluated_heads(rig, bone, frames):
    scene = bpy.context.scene
    out = []
    for f in frames:
        scene.frame_set(int(f))
        out.append(rig.matrix_world @ rig.pose.bones[bone].head)
    return np.array(out)


def test_namespace_registered():
    assert hasattr(bpy.types.Scene, "asc_trails")
    assert not hasattr(bpy.types.Scene, "motion_onion")  # coexists with the original add-on
    assert hasattr(bpy.ops.asc_trails, "refresh")
    assert bpy.types.ASC_TR_PT_main.bl_parent_id == "ASC_PT_main"
    assert bpy.types.ASC_TR_PT_main.bl_category == "Animation Sculptor"


def test_defaults_onion_off():
    assert bpy.context.scene.asc_trails.onion_show is False


def test_trail_matches_evaluated_rig(public_rig, provider):
    scene = bpy.context.scene
    _pin(scene, public_rig, ["hand_ik.L", "torso"])
    provider.update_now()
    for bone in ("hand_ik.L", "torso"):
        trail = provider.get_trail(public_rig, bone)
        assert trail is not None and trail.complete and trail.engine == 'STEP'
        assert list(trail.frames) == list(range(pr.FRAME_START, pr.FRAME_END + 1))
        assert trail.keyframes == pr.KEY_FRAMES
        expected = _evaluated_heads(public_rig, bone, trail.frames)
        np.testing.assert_allclose(trail.points, expected, atol=1e-5)
    # the hand actually moves along the trail
    hand = provider.get_trail(public_rig, "hand_ik.L")
    assert np.ptp(hand.points, axis=0).max() > 0.1


def test_suspend_keeps_cache_and_resume_invalidates(public_rig, provider, engine):
    scene = bpy.context.scene
    _pin(scene, public_rig, ["hand_ik.L"])
    provider.update_now()
    before = provider.get_trail(public_rig, "hand_ik.L")

    fc = public_rig.animation_data.action.layers[0].strips[0].channelbags[0].fcurves.find(
        'pose.bones["hand_ik.L"].location', index=2)
    key = (public_rig.name, "hand_ik.L")
    with provider.suspended(keys=[key]):
        assert provider.is_suspended()
        for kp in fc.keyframe_points:
            kp.co.y += 0.5
            kp.handle_left.y += 0.5
            kp.handle_right.y += 0.5
        fc.update()
        engine.depsgraph_changed(scene, bpy.context.evaluated_depsgraph_get())
        engine.schedule(delay=0.0)
        assert engine.STATE.timer_fn is None  # nothing scheduled while suspended
        provider.update_now()                 # no-op while suspended
        during = provider.get_trail(public_rig, "hand_ik.L")
        np.testing.assert_array_equal(during.points, before.points)
    assert not provider.is_suspended()
    assert provider.get_trail(public_rig, "hand_ik.L") is None  # invalidated by resume()
    provider.update_now()
    after = provider.get_trail(public_rig, "hand_ik.L")
    np.testing.assert_allclose(after.points, _evaluated_heads(public_rig, "hand_ik.L", after.frames), atol=1e-5)
    assert not np.allclose(after.points, before.points)


def test_suspend_nests(provider):
    provider.suspend()
    provider.suspend()
    provider.resume()
    assert provider.is_suspended()
    provider.resume()
    assert not provider.is_suspended()
    provider.resume()  # extra resume is harmless
    assert not provider.is_suspended()


def test_native_solver_settings_restored(public_rig, engine):
    """ASC-PATCH P4: helpers used around the native solver restore the persistent settings."""
    avs = public_rig.pose.animation_visualization.motion_path
    original = {a: getattr(avs, a) for a in ("type", "range", "frame_start", "frame_end", "bake_location")}
    saved = engine._avs_save(avs)
    avs.type = 'RANGE'
    avs.frame_start, avs.frame_end = 3, 7
    avs.bake_location = 'TAILS' if original["bake_location"] != 'TAILS' else 'HEADS'
    engine._avs_restore(avs, saved)
    assert {a: getattr(avs, a) for a in original} == original


def test_action_update_invalidates_trail(public_rig, provider, engine):
    """ASC-PATCH P7 (maintainer report): keying with I / editing in the Graph Editor only updates the
    Action; the trail must still be recomputed (it kept the old path until Refresh)."""
    from types import SimpleNamespace

    scene = bpy.context.scene
    _pin(scene, public_rig, ["hand_ik.L"])
    provider.update_now()
    assert provider.get_trail(public_rig, "hand_ik.L") is not None
    action = public_rig.animation_data.action
    fake = SimpleNamespace(updates=[SimpleNamespace(id=action, is_updated_transform=False, is_updated_geometry=False)])
    engine.depsgraph_changed(scene, fake)
    assert provider.get_trail(public_rig, "hand_ik.L") is None


def test_native_points_validated_against_live_bone(public_rig, engine):
    """ASC-PATCH P8 (found with a UI scenario): pose.paths_calculate returns silent zeros for bones in a
    hidden collection; such a native path is rejected so the bone falls back to frame stepping. A path
    that differs from an unkeyed live pose is valid (maintainer report on PR #11: comparing with the live
    pose sent the engine to frame stepping, which threw the unkeyed pose away)."""
    scene = bpy.context.scene
    scene.frame_set(5)
    pb = public_rig.pose.bones["hand_ik.L"]
    live = tuple(public_rig.matrix_world @ pb.head)
    assert engine._native_points_valid(public_rig, "hand_ik.L", {5: live}, 5, 'HEAD')
    assert engine._native_points_valid(public_rig, "hand_ik.L", {5: (live[0] + 0.3, live[1], live[2])}, 5, 'HEAD')
    assert not engine._native_points_valid(public_rig, "hand_ik.L", {4: (0.0, 0.0, 0.0), 5: (0.0, 0.0, 0.0)}, 5, 'HEAD')


def test_frame_stepping_keeps_unkeyed_pose(public_rig, provider):
    """ASC-PATCH P10: the STEP engine changes frames (re-applying the Action) but restores the unkeyed pose."""
    scene = bpy.context.scene
    _pin(scene, public_rig, ["hand_ik.L"])          # STEP engine
    scene.frame_set(6)
    pb = public_rig.pose.bones["hand_ik.L"]
    pb.location.x += 0.2
    edited = tuple(pb.location)
    provider.update_now()
    assert provider.get_trail(public_rig, "hand_ik.L") is not None
    assert tuple(pb.location) == edited


def test_trail_on_local_attack_asset(attack_rig, provider):
    """The user's character (local only): trail of the sword hand equals the evaluated rig."""
    scene = bpy.context.scene
    _pin(scene, attack_rig, ["hand_ik.R", "foot_ik.L"])
    provider.update_now()
    for bone in ("hand_ik.R", "foot_ik.L"):
        trail = provider.get_trail(attack_rig, bone)
        assert trail is not None and trail.complete
        assert set(trail.keyframes) >= {1, 10, 16, 18, 26, 40}
        np.testing.assert_allclose(trail.points, _evaluated_heads(attack_rig, bone, trail.frames), atol=1e-4)


def test_own_settings_restore_does_not_invalidate(public_rig, provider, engine):
    """Regression (found via UI screenshot): restoring the motion-path settings after the native solver tags
    the rig for update; that update must not clear the trail just computed (infinite recompute loop)."""
    from types import SimpleNamespace

    scene = bpy.context.scene
    _pin(scene, public_rig, ["hand_ik.L"])
    provider.update_now()
    assert provider.get_trail(public_rig, "hand_ik.L") is not None

    avs = public_rig.pose.animation_visualization.motion_path
    saved = engine._avs_save(avs)
    avs.frame_start = saved["frame_start"] + 5
    engine._avs_restore(avs, saved, public_rig)
    fake = SimpleNamespace(updates=[SimpleNamespace(id=public_rig, is_updated_transform=True, is_updated_geometry=False)])
    engine.depsgraph_changed(scene, fake)
    assert provider.get_trail(public_rig, "hand_ik.L") is not None  # our own update: ignored once
    engine.depsgraph_changed(scene, fake)
    assert provider.get_trail(public_rig, "hand_ik.L") is None      # a real edit still invalidates
