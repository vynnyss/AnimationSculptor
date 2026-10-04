# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings, preferences, and acceptance criterion 8: save → reopen keeps the Action exactly and adds
nothing to the file besides the scene settings."""

import bpy
import pytest


def _dump(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    return {(fc.data_path, fc.array_index): [(tuple(k.co), tuple(k.handle_left), tuple(k.handle_right),
                                              k.handle_left_type, k.handle_right_type, k.interpolation)
                                             for k in fc.keyframe_points] for fc in cb.fcurves}


def _id_props(id_block):
    return set(id_block.keys())


def test_scene_settings_registered_with_defaults(public_rig):
    s = bpy.context.scene.asc_sculpt
    assert (s.radius_past, s.radius_future, s.radius_linked, s.show_time_ruler, s.falloff, s.timing_scope,
            s.spacing_policy, s.hide_on_playback) == \
        (0.0, 0.0, True, True, 'SMOOTH', 'CHARACTER', 'PRESERVE_PATH', True)


def test_preferences_registered(addon_module):
    prefs = bpy.context.preferences.addons[addon_module].preferences
    assert prefs.hit_radius_px == 12 and prefs.precision == pytest.approx(0.1)


def test_panels_registered():
    for name in ("ASC_PT_main", "ASC_PT_tool", "ASC_PT_breakdown", "ASC_PT_stats", "ASC_TR_PT_main"):
        assert hasattr(bpy.types, name), name
    assert bpy.types.ASC_PT_tool.bl_parent_id == "ASC_PT_main"


def test_save_reload_keeps_everything(public_rig, tmp_path):
    """Criterion 8: edit with every gesture kind, save, reopen: identical Action, settings kept, no extra data."""
    scene = bpy.context.scene
    objects_before = sorted(o.name for o in bpy.data.objects)
    actions_before = sorted(a.name for a in bpy.data.actions)
    props_before = {"scene": _id_props(scene), "rig": _id_props(public_rig), "data": _id_props(public_rig.data)}
    rig_name = public_rig.name
    op = bpy.ops.asc.sculpt_gesture
    assert op('EXEC_DEFAULT', obj_name=rig_name, bone="hand_ik.L", frame=12, delta=(0.1, 0, 0.05)) == {'FINISHED'}
    assert op('EXEC_DEFAULT', obj_name=rig_name, bone="hand_ik.L", frame=6, delta=(0, 0.05, 0.05), mode='ARC') == {'FINISHED'}
    assert op('EXEC_DEFAULT', obj_name=rig_name, bone="hand_ik.L", frame=12, mode='RETIME', new_frame=14) == {'FINISHED'}
    assert op('EXEC_DEFAULT', obj_name=rig_name, bone="hand_ik.L", frame=18, mode='SPACING', favor=0.2) == {'FINISHED'}
    scene.asc_sculpt.radius_linked = False
    scene.asc_sculpt.radius_past = 6.0
    scene.asc_sculpt.radius_future = 2.0
    scene.asc_sculpt.spacing_policy = 'PRESERVE_SMOOTHNESS'
    scene.asc_trails.enabled = True
    dump = _dump(bpy.data.objects[rig_name])
    path = str(tmp_path / "saved.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    rig = bpy.data.objects[rig_name]
    scene = bpy.context.scene
    assert _dump(rig) == dump
    s = scene.asc_sculpt
    assert (s.radius_past, s.radius_future, s.radius_linked) == (6.0, 2.0, False)
    assert s.spacing_policy == 'PRESERVE_SMOOTHNESS'
    assert scene.asc_trails.enabled
    assert sorted(o.name for o in bpy.data.objects) == objects_before
    assert sorted(a.name for a in bpy.data.actions) == actions_before
    assert {"scene": _id_props(scene), "rig": _id_props(rig), "data": _id_props(rig.data)} == props_before
    # the motion-path settings of the rig are untouched by the trail engine (ASC-PATCH P4)
    assert rig.pose.animation_visualization.motion_path.type in {'CURRENT_FRAME', 'RANGE'}


def test_file_opens_without_the_extension(public_rig, tmp_path, addon_module):
    """Uninstalling the add-on loses nothing: the animation is a plain Action."""
    import addon_utils

    rig_name = public_rig.name
    bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig_name, bone="hand_ik.L", frame=12, delta=(0.1, 0, 0))
    dump = _dump(public_rig)
    path = str(tmp_path / "plain.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    addon_utils.disable(addon_module, default_set=True)
    try:
        bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
        assert _dump(bpy.data.objects[rig_name]) == dump
        assert not hasattr(bpy.types.Scene, "asc_sculpt")
    finally:
        addon_utils.enable(addon_module, default_set=True, handle_error=lambda exc: (_ for _ in ()).throw(exc))


def test_file_from_0_3_0_opens_with_both_radii_equal(public_rig, tmp_path):
    """0.3.0 saved one symmetric ``soft_radius``: on load it becomes the past and the future radius."""
    s = bpy.context.scene.asc_sculpt
    s.radius_past = s.radius_future = 0.0
    s.soft_radius = 5.0
    s.settings_version = 0              # what a 0.3.0 file holds (the property did not exist)
    path = str(tmp_path / "v030.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False)
    s = bpy.context.scene.asc_sculpt
    assert (s.radius_past, s.radius_future, s.radius_linked, s.settings_version) == (5.0, 5.0, True, 1)
    s.radius_linked = False
    s.radius_past = 3.0                 # migrated once: reopening keeps the user's radii
    path2 = str(tmp_path / "v040.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path2)
    bpy.ops.wm.open_mainfile(filepath=path2, load_ui=False)
    s = bpy.context.scene.asc_sculpt
    assert (s.radius_past, s.radius_future) == (3.0, 5.0)
