# SPDX-License-Identifier: GPL-3.0-or-later
"""Onion skin through ``trails/provider``: toggle, ghosts on the time ruler window, expanded (spread)
onion hook (LMP patch P11)."""

import importlib

import bpy
import pytest
from mathutils import Matrix, Vector

import public_rig as pr
from body_mesh import BODY_NAME, add_skinned_body


@pytest.fixture
def provider(addon):
    return importlib.import_module(addon.__name__ + ".trails.provider")


@pytest.fixture
def engine(addon):
    return importlib.import_module(addon.__name__ + ".trails.lmp.engine")


@pytest.fixture
def draw(addon):
    return importlib.import_module(addon.__name__ + ".trails.lmp.draw")


@pytest.fixture
def body_rig(public_rig):
    add_skinned_body(public_rig)
    scene = bpy.context.scene
    s = scene.asc_trails
    s.pinned.clear()
    item = s.pinned.add()
    item.obj = public_rig
    item.bone = "hand_ik.L"
    s.target_mode = 'PINNED'
    s.path_engine = 'STEP'
    s.path_range_mode = 'SCENE'
    s.enabled = True
    scene.frame_start, scene.frame_end = 1, 60
    scene.frame_set(30)
    return public_rig


@pytest.fixture(autouse=True)
def _no_spread(provider):
    """The spread hook is module state: always remove it after a test."""
    yield
    provider.set_onion_spread(False)


def _ghost_frames(engine, scene):
    s = scene.asc_trails
    frames = engine.onion_frame_list(None, s, scene, scene.frame_current)     # FRAMES mode: no cache needed
    return sorted(f for f, side, _i, _n in frames if side != 0)


def test_set_onion_toggles_property(provider, body_rig):
    scene = bpy.context.scene
    assert scene.asc_trails.onion_show is False
    provider.set_onion(scene, True)
    assert scene.asc_trails.onion_show is True
    assert tuple(scene.asc_trails.onion_color_before) == pytest.approx(provider.PAST_COLOR)
    assert tuple(scene.asc_trails.onion_color_after) == pytest.approx(provider.FUTURE_COLOR)
    provider.set_onion(scene, False)
    assert scene.asc_trails.onion_show is False


def test_set_onion_keeps_user_colours(provider, body_rig):
    scene = bpy.context.scene
    scene.asc_trails.onion_color_before = (0.1, 0.2, 0.9)
    provider.set_onion(scene, True)
    assert tuple(scene.asc_trails.onion_color_before) == pytest.approx((0.1, 0.2, 0.9))


@pytest.mark.parametrize("past,future", [(0, 0), (5, 0), (0, 7), (4, 6), (12, 12), (20, 15), (30, 3)])
def test_sync_window_ghosts_on_expected_frames(provider, engine, body_rig, past, future):
    scene = bpy.context.scene
    scene.asc_trails.onion_mode = 'KEYFRAMES'          # the sync forces per-frame ghosts
    provider.set_onion(scene, True)
    before, after, step = provider.sync_onion_window(scene, past, future)
    s = scene.asc_trails
    assert (s.onion_before, s.onion_after, s.onion_step) == (before, after, step)
    assert s.onion_mode == 'FRAMES'
    f0 = scene.frame_current
    expected = sorted([f0 - step * i for i in range(1, before + 1)] + [f0 + step * i for i in range(1, after + 1)])
    expected = [f for f in expected if scene.frame_start <= f <= scene.frame_end]     # onion_clamp_range
    assert _ghost_frames(engine, scene) == expected
    assert all(f0 - past <= f <= f0 + future for f in expected)
    assert before <= 12 and after <= 12
    if past == 0:
        assert not any(f < f0 for f in expected)
    if future == 0:
        assert not any(f > f0 for f in expected)
    if (past, future) == (12, 12):
        assert step == 1 and before == after == 12
    if (past, future) == (20, 15):
        assert step == 2 and len(expected) == 10 + 7


def test_sync_window_computes_the_ghost_meshes(provider, engine, body_rig):
    scene = bpy.context.scene
    provider.set_onion(scene, True)
    provider.sync_onion_window(scene, 4, 3)
    provider.update_now()
    cache = engine.CACHE[(BODY_NAME, "")]
    assert set(cache.onion) | set(cache.mats) >= {29, 28, 27, 26, 31, 32, 33}


def _fake_rv3d(rotation):
    class RV:
        view_matrix = Matrix.Rotation(rotation, 4, 'Z').inverted()
    return RV()


def test_spread_offset_function(provider, draw, body_rig):
    scene = bpy.context.scene
    ctx = bpy.context
    rig = body_rig
    provider.sync_onion_window(scene, 6, 6)
    provider.set_onion_spread(True, spacing=0.5)
    assert draw.GHOST_OFFSET is provider.ghost_offset and provider.onion_spread_enabled()
    for rot in (0.0, 0.7, -1.9):
        rv3d = _fake_rv3d(rot)
        right = Vector(rv3d.view_matrix[0][:3])
        assert provider.ghost_offset(ctx, rig.name, 30, 30, rv3d=rv3d) is None
        assert draw.GHOST_OFFSET(ctx, rig.name, 30, 30) is None            # no 3D view in background
        for df in (-6, -2, 1, 3, 6):
            off = Vector(provider.ghost_offset(ctx, rig.name, 30 + df, 30, rv3d=rv3d))
            assert off.dot(right) == pytest.approx(0.5 * df, abs=1e-5)       # proportional, signed
            assert (off - right * off.dot(right)).length < 1e-5              # only along screen-right
    provider.set_onion_spread(False)
    assert draw.GHOST_OFFSET is None and not provider.onion_spread_enabled()


def test_spread_step_scales_offset_per_ghost(provider, body_rig):
    scene = bpy.context.scene
    provider.sync_onion_window(scene, 24, 24)           # step 2
    assert scene.asc_trails.onion_step == 2
    provider.set_onion_spread(True, spacing=1.0)
    rv3d = _fake_rv3d(0.0)
    off = Vector(provider.ghost_offset(bpy.context, body_rig.name, 32, 30, rv3d=rv3d))
    assert off.x == pytest.approx(1.0)                  # one ghost step = one spacing


def test_spread_auto_spacing_from_character_width(provider, body_rig):
    pts = [c.matrix_world @ Vector(v) for c in body_rig.children_recursive if c.type == 'MESH' for v in c.bound_box]
    width = max(max(p.x for p in pts) - min(p.x for p in pts), max(p.y for p in pts) - min(p.y for p in pts))
    provider.set_onion_spread(True)
    assert provider.spread_spacing(body_rig.name) == pytest.approx(width * 1.1, rel=1e-4)
    # deterministic: scrubbing frames does not change it
    bpy.context.scene.frame_set(10)
    assert provider.spread_spacing(body_rig.name) == pytest.approx(width * 1.1, rel=1e-4)


def test_onion_frame_stepping_keeps_the_unkeyed_pose(public_rig, addon):
    """ASC-PATCH P10 (rev. 0.7.0): the onion skin ghosts the *mesh*; stepping frames for it must not throw away
    a pose of its armature that is not keyed yet (Relax, G without I…)."""
    import importlib

    provider = importlib.import_module(addon.__name__ + ".trails.provider")
    rig = public_rig
    scene = bpy.context.scene
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    for pb in rig.pose.bones:
        pb.select = pb.name == "hand_ik.L"
    provider.set_onion(scene, True)
    provider.sync_onion_window(scene, 4, 4)
    pb = rig.pose.bones["hand_ik.L"]
    pb.location = (0.2, -0.1, 0.3)                        # not keyed
    provider.update_now()
    assert tuple(round(v, 6) for v in pb.location) == (0.2, -0.1, 0.3)
