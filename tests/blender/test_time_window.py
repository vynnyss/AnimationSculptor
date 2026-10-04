# SPDX-License-Identifier: GPL-3.0-or-later
"""Time UI (design/ephemeral-rig.md, phase 1): asymmetric soft grab, the time window settings and the
``asc.time_window`` operator, the past/future palette."""

import importlib

import bpy
import pytest
from mathutils import Vector


def _head(rig, bone, frame):
    bpy.context.scene.frame_set(frame)
    return (rig.matrix_world @ rig.pose.bones[bone].head).copy()


def _gesture(rig, bone, frame, delta, **kw):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame, delta=delta, **kw)


@pytest.mark.parametrize("past,future", [(15.0, 0.0), (0.0, 15.0), (15.0, 6.0), (20.0, 15.0)])
def test_asymmetric_soft_grab_moves_each_side_by_its_radius(public_rig, addon, past, future):
    """Keys before the grabbed frame follow with the past radius, keys after with the future radius."""
    falloff = importlib.import_module(addon.__name__ + ".core.falloff")
    delta = Vector((0.0, -0.1, 0.1))
    before = {f: _head(public_rig, "hand_ik.L", f) for f in (1, 12, 24)}
    assert _gesture(public_rig, "hand_ik.L", 12, delta, mode='GRAB', radius_past=past,
                    radius_future=future) == {'FINISHED'}
    assert (_head(public_rig, "hand_ik.L", 12) - before[12] - delta).length < 1e-4
    for f in (1, 24):
        w = float(falloff.weight_signed([f - 12], past, future, "SMOOTH")[0])
        assert (_head(public_rig, "hand_ik.L", f) - before[f] - delta * w).length < 1e-4, (f, w)


def test_one_sided_window_leaves_the_other_side_untouched(public_rig):
    after = _head(public_rig, "hand_ik.L", 24)
    _gesture(public_rig, "hand_ik.L", 12, (0.1, 0.1, 0.1), mode='GRAB', radius_past=30.0, radius_future=0.0)
    assert (_head(public_rig, "hand_ik.L", 24) - after).length < 1e-6


def test_symmetric_radius_prop_still_works(public_rig):
    """``radius`` alone (both sides) behaves as before 0.4.0."""
    a = _head(public_rig, "hand_ik.L", 24)
    _gesture(public_rig, "hand_ik.L", 12, (0.0, 0.0, 0.1), mode='GRAB', radius=15.0)
    assert (_head(public_rig, "hand_ik.L", 24) - a).length > 1e-4


def test_linked_radii_follow_each_other(public_rig):
    s = bpy.context.scene.asc_sculpt
    s.radius_linked = True
    s.radius_past = 7.0
    assert s.radius_future == 7.0
    s.radius_future = 4.0
    assert s.radius_past == 4.0
    s.radius_linked = False
    s.radius_past = 9.0
    assert (s.radius_past, s.radius_future) == (9.0, 4.0)
    s.radius_linked = True             # linking copies the past radius to the future
    assert (s.radius_past, s.radius_future) == (9.0, 9.0)


@pytest.mark.parametrize("linked,side,shift,expected", [
    (False, 'PAST', False, (8.0, 2.0)),
    (False, 'FUTURE', False, (3.0, 8.0)),
    (False, 'FUTURE', True, (8.0, 8.0)),
    (True, 'PAST', False, (8.0, 8.0)),
])
def test_time_window_operator(public_rig, linked, side, shift, expected):
    s = bpy.context.scene.asc_sculpt
    s.radius_linked = False
    s.radius_past, s.radius_future = 3.0, 2.0
    s.radius_linked = linked
    if linked:
        s.radius_past, s.radius_future = 3.0, 3.0
    assert bpy.ops.asc.time_window('EXEC_DEFAULT', side=side, shift=shift, radius=8.0) == {'FINISHED'}
    assert (s.radius_past, s.radius_future) == expected
    assert s.radius_linked == linked


def test_palette_sets_past_red_future_green(public_rig, addon):
    provider = importlib.import_module(addon.__name__ + ".trails.provider")
    scene = bpy.context.scene
    trails = scene.asc_trails
    trails.path_color_past = (0.0, 0.0, 1.0)
    assert bpy.ops.asc.apply_palette() == {'FINISHED'}
    assert tuple(trails.path_color_past) == pytest.approx(provider.PAST_COLOR)
    assert tuple(trails.path_color_future) == pytest.approx(provider.FUTURE_COLOR)
    assert tuple(trails.onion_color_before) == pytest.approx(provider.PAST_COLOR)
    assert tuple(trails.onion_color_after) == pytest.approx(provider.FUTURE_COLOR)
    assert trails.path_color_past[0] > trails.path_color_past[1]          # red
    assert trails.path_color_future[1] > trails.path_color_future[0]      # green
    assert scene.asc_sculpt.palette_applied


def test_tool_has_settings_bar(addon):
    tool = importlib.import_module(addon.__name__ + ".interaction.sculpt_tool").ASC_WT_sculpt
    assert callable(getattr(tool, "draw_settings", None))
