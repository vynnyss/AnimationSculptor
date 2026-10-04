# SPDX-License-Identifier: GPL-3.0-or-later
"""UX reform (docs/design/sculpt-ux.md): body picking, deform bone -> control, the body gesture through the
operator (a surface point dragged on the skin), the Smooth brush, the toolbar tools and the mode toggles."""

import importlib

import bpy
import numpy as np
import pytest
from mathutils import Vector

import body_mesh
import deform_check as dc


def _rig_pkg(addon):
    return importlib.import_module(addon.__name__ + ".rig")


def _body_pick(addon):
    mod = importlib.import_module(addon.__name__ + ".interaction.body_pick")
    mod.clear_cache()
    return mod


def _head_tail(rig, bone):
    mw = rig.matrix_world
    pb = rig.pose.bones[bone]
    return np.array(mw @ pb.head), np.array(mw @ pb.tail)


def _gesture(rig, bone, frame, delta, **kw):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame,
                                      delta=delta, **kw)


def _fk_arm(rig, on=True):
    rig.pose.bones["upper_arm_parent.R"]["IK_FK"] = 1.0 if on else 0.0
    rig.pose.bones["forearm_fk.R"].rotation_quaternion = (0.95, 0.31, 0.0, 0.0)   # bent elbow
    rig.keyframe_insert('pose.bones["forearm_fk.R"].rotation_quaternion', frame=1)
    rig.update_tag()


# -- 1. body_pick ----------------------------------------------------------------------------------
def _cast_at_bone(rig, bone):
    """Ray cast from outside toward the middle of ``bone``'s tube; the first direction whose hit lands on
    that tube (hit point at the tube radius from the bone axis) wins. Returns (object, face index, location)."""
    bpy.context.scene.frame_set(1)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    head, tail = _head_tail(rig, bone)
    axis = tail - head
    radius = max(0.015, 0.22 * np.linalg.norm(axis))     # body_mesh defaults
    unit = axis / np.linalg.norm(axis)
    ref = np.array([1.0, 0, 0]) if abs(unit[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(unit, ref)
    u /= np.linalg.norm(u)
    v = np.cross(unit, u)
    mid = (head + tail) / 2.0
    for angle in np.linspace(0, 2 * np.pi, 8, endpoint=False):
        direction = np.cos(angle) * u + np.sin(angle) * v
        origin = mid + direction * 1.5
        ok, location, _n, index, hit, _m = bpy.context.scene.ray_cast(
            depsgraph, Vector(origin), Vector(-direction))
        if not ok or hit is None or hit.name != body_mesh.BODY_NAME:
            continue
        loc = np.array(location)
        along = np.dot(loc - head, unit)
        dist = np.linalg.norm(loc - head - along * unit)
        if 0.0 <= along <= np.linalg.norm(axis) and dist < radius * 1.02:
            return hit, index, location
    raise AssertionError(f"no unobstructed ray toward {bone}")


@pytest.mark.parametrize("bone", ["DEF-forearm.L", "DEF-thigh.L", "DEF-spine.006", "DEF-hand.R", "DEF-spine.003"])
def test_bone_at_returns_the_deform_bone_under_the_ray(public_rig, addon, bone):
    pick = _body_pick(addon)
    hit, index, location = _cast_at_bone(public_rig, bone)
    ob = hit.original
    depsgraph = bpy.context.evaluated_depsgraph_get()
    assert pick.bone_at(ob, ob.evaluated_get(depsgraph), public_rig, index, location) == bone


def test_bone_at_falls_back_to_the_nearest_bone_when_the_topology_changed(public_rig, addon):
    """A face index that does not exist (subdivision-like evaluated topology): the nearest posed bone."""
    pick = _body_pick(addon)
    _hit, _index, location = _cast_at_bone(public_rig, "DEF-forearm.L")
    ob = bpy.data.objects[body_mesh.BODY_NAME]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    assert pick.bone_at(ob, ob.evaluated_get(depsgraph), public_rig, 10 ** 6, location) == "DEF-forearm.L"


def test_bone_held_prop_gives_its_parent_bone(public_rig, addon):
    """A mesh parented to a bone (sword) is grabbed through that bone."""
    pick = _body_pick(addon)
    prop = bpy.data.objects.new("prop", bpy.data.meshes.new("prop"))
    bpy.context.scene.collection.objects.link(prop)
    prop.parent, prop.parent_type, prop.parent_bone = public_rig, 'BONE', "hand_fk.L"
    depsgraph = bpy.context.evaluated_depsgraph_get()
    assert pick.bone_at(prop, prop.evaluated_get(depsgraph), public_rig, 0, (0, 0, 0)) == "hand_fk.L"


def test_region_triangles(public_rig, addon):
    pick = _body_pick(addon)
    ob = bpy.data.objects[body_mesh.BODY_NAME]
    part = set(dc.part(ob, "DEF-forearm.L").tolist())
    tris = pick.region_triangles(ob, public_rig, "DEF-forearm.L")
    assert len(tris) > 0 and tris.shape[1] == 3
    assert set(tris.reshape(-1).tolist()) <= part                         # the region is made of its vertices
    assert len(pick.region_triangles(ob, public_rig, "root")) == 0        # a bone without vertices
    assert len(pick.region_triangles(ob, public_rig, "no-such-bone")) == 0


def test_deformed_meshes(public_rig, addon):
    pick = _body_pick(addon)
    other = bpy.data.objects.new("cube", bpy.data.meshes.new("cube"))
    bpy.context.scene.collection.objects.link(other)
    names = {ob.name for ob in pick.deformed_meshes(bpy.context.scene, public_rig)}
    assert names == {body_mesh.BODY_NAME}
    ob = bpy.data.objects[body_mesh.BODY_NAME]
    ob.modifiers[0].show_viewport = False
    assert pick.deformed_meshes(bpy.context.scene, public_rig) == []


# -- 2. RigAdapter.control_for_deform --------------------------------------------------------------
def test_control_for_deform_rigify(public_rig, addon):
    rig_pkg = _rig_pkg(addon)
    rig = public_rig
    adapter = rig_pkg.get_adapter(rig)
    assert adapter.id == "rigify"
    arm = rig.pose.bones["upper_arm_parent.R"]
    leg = rig.pose.bones["thigh_parent.L"]
    arm["IK_FK"] = 1.0
    assert adapter.control_for_deform(rig, "DEF-forearm.R.001") == ("forearm_fk.R", rig_pkg.CHAIN, "")
    assert adapter.control_for_deform(rig, "DEF-upper_arm.R") == ("upper_arm_fk.R", rig_pkg.CHAIN, "")
    arm["IK_FK"] = 0.0
    assert adapter.control_for_deform(rig, "DEF-forearm.R.001") == ("hand_ik.R", rig_pkg.IK, "")
    leg["IK_FK"] = 0.0
    # pole off (Rigify default): the *_ik_target bone does nothing, the upper arm/thigh move the hand/foot
    assert adapter.control_for_deform(rig, "DEF-upper_arm.L") == ("hand_ik.L", rig_pkg.IK, "")
    assert adapter.control_for_deform(rig, "DEF-thigh.L")[0] == "foot_ik.L"
    rig.pose.bones["upper_arm_parent.L"]["pole_vector"] = True
    rig.pose.bones["thigh_parent.L"]["pole_vector"] = True
    assert adapter.control_for_deform(rig, "DEF-upper_arm.L") == ("upper_arm_ik_target.L", rig_pkg.IK, "")
    assert adapter.control_for_deform(rig, "DEF-thigh.L")[0] == "thigh_ik_target.L"
    assert adapter.control_for_deform(rig, "DEF-thigh.L")[1] == rig_pkg.IK
    leg["IK_FK"] = 1.0
    assert adapter.control_for_deform(rig, "DEF-thigh.L") == ("thigh_fk.L", rig_pkg.CHAIN, "")


@pytest.mark.parametrize("deform,control", [
    ("DEF-spine.006", "head"),
    ("DEF-spine.003", "chest"),
    ("DEF-spine", "hips"),
    ("DEF-pelvis.L", "hips"),
    ("DEF-breast.R", "chest"),
    ("DEF-palm.01.L", "palm.L"),
    ("DEF-f_index.02.L", "f_index.02.L"),
    ("DEF-forehead.L", "head"),
])
def test_control_for_deform_rigify_body_parts(public_rig, addon, deform, control):
    rig_pkg = _rig_pkg(addon)
    assert deform in public_rig.data.bones
    assert rig_pkg.get_adapter(public_rig).control_for_deform(public_rig, deform) == (control, rig_pkg.CHAIN, "")


def test_control_for_deform_generic_is_the_bone_itself(addon):
    from test_ephemeral_gesture import _plain_armature

    rig_pkg = _rig_pkg(addon)
    ob = _plain_armature()
    adapter = rig_pkg.get_adapter(ob)
    assert adapter.id == "generic"
    assert adapter.control_for_deform(ob, "b") == ("b", rig_pkg.CHAIN, "")
    control, kind, reason = adapter.control_for_deform(ob, "nope")
    assert control is None and reason


# -- 3. body gesture on a surface point ------------------------------------------------------------
@pytest.mark.parametrize("vertex_end", [0, 1])
def test_body_gesture_drags_the_surface_point(public_rig, addon, vertex_end):
    """A spot on the forearm skin dragged with the operator (use_point): the nearest vertex of the part ends
    at point + delta (< 2 mm), the rest of the window follows, nothing outside the window changes."""
    rig_pkg = _rig_pkg(addon)
    rig = public_rig
    _fk_arm(rig)
    adapter = rig_pkg.get_adapter(rig)
    control, kind, _reason = adapter.control_for_deform(rig, "DEF-forearm.R.001")
    assert (control, kind) == ("forearm_fk.R", rig_pkg.CHAIN)
    mesh = dc.deformed_mesh(rig)
    part = dc.part(mesh, "DEF-forearm.R.001")
    assert len(part)
    frames = list(range(1, 25))
    before = dc.frames_snapshot(mesh, frames)
    ring = dc.tube_ends(part)[vertex_end]
    point = before[12][ring[2]]
    near = part[np.argmin(np.linalg.norm(before[12][part] - point, axis=1))]
    assert near == ring[2]                                                    # the tracked vertex
    delta = np.array([0.03, -0.04, 0.05])
    assert _gesture(rig, control, 12, Vector(delta), mode='CHAIN', chain_scope='LIMB', use_point=True,
                    point=Vector(point), radius_past=4, radius_future=4) == {'FINISHED'}
    after = dc.frames_snapshot(mesh, frames)
    err = np.linalg.norm(after[12][near] - (point + delta))
    print(f"surface point error: {err * 1000:.3f} mm")
    assert err < 2e-3
    assert dc.max_change(before, after, [f for f in frames if not 8 <= f <= 16]) < 1e-5
    assert dc.max_change(before, after, [11, 12, 13]) > 1e-2                  # the window really moved


# -- 4. Smooth -------------------------------------------------------------------------------------
def _add_noise(rig, bone, frames, amplitude=0.02, seed=1):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    rng = np.random.default_rng(seed)
    path = rig.pose.bones[bone].path_from_id("location")
    for axis in range(3):
        fc = cb.fcurves.find(path, index=axis)
        base = {f: fc.evaluate(f) for f in frames}
        for f in frames:
            fc.keyframe_points.insert(f, base[f] + rng.normal(0.0, amplitude), options={'FAST'})
        fc.update()
    rig.update_tag()


def _channel(rig, bone, frames):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    path = rig.pose.bones[bone].path_from_id("location")
    return np.array([[cb.fcurves.find(path, index=a).evaluate(f) for a in range(3)] for f in frames])


def _roughness(values):
    return float((np.diff(values, 2, axis=0) ** 2).sum())


def _smooth(rig, bone, frame, passes, **kw):
    return bpy.ops.asc.sculpt_gesture('EXEC_DEFAULT', obj_name=rig.name, bone=bone, frame=frame, mode='SMOOTH',
                                      passes=passes, radius_past=6, radius_future=6, **kw)


def test_smooth_reduces_roughness_with_passes(public_rig):
    rig = public_rig
    frames = list(range(1, 25))
    _add_noise(rig, "hand_ik.L", frames)
    original = _channel(rig, "hand_ik.L", frames)
    inside = [f - 1 for f in range(6, 19)]
    rough = [_roughness(original[inside[0]:inside[-1] + 1])]
    for passes in (1, 3, 8):
        # fresh copy of the noisy animation for each N: the operator reads the current curves
        _restore(rig, "hand_ik.L", frames, original)
        assert _smooth(rig, "hand_ik.L", 12, passes) == {'FINISHED'}
        out = _channel(rig, "hand_ik.L", frames)
        rough.append(_roughness(out[inside[0]:inside[-1] + 1]))
        outside = [f - 1 for f in frames if f < 5 or f > 19]
        assert np.abs(out[outside] - original[outside]).max() < 1e-6          # nothing outside the window
    print("roughness by passes (0,1,3,8):", ["%.3e" % r for r in rough])
    assert rough[0] > rough[1] > rough[2] > rough[3]


def _restore(rig, bone, frames, values):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    path = rig.pose.bones[bone].path_from_id("location")
    for axis in range(3):
        fc = cb.fcurves.find(path, index=axis)
        for f, v in zip(frames, values[:, axis]):
            fc.keyframe_points.insert(f, v, options={'FAST'})
        fc.update()
    rig.update_tag()


def test_smooth_zero_passes_changes_nothing(public_rig):
    rig = public_rig
    frames = list(range(1, 25))
    _add_noise(rig, "hand_ik.L", frames)
    before = _channel(rig, "hand_ik.L", frames)
    assert _smooth(rig, "hand_ik.L", 12, 0) == {'FINISHED'}
    assert np.abs(_channel(rig, "hand_ik.L", frames) - before).max() < 1e-6


def test_smooth_refuses_a_bone_without_animation(public_rig):
    rig = public_rig
    assert _smooth(rig, "hand_ik.R", 12, 3) == {'CANCELLED'}


def test_smooth_makes_the_hand_skin_path_smoother(public_rig):
    rig = public_rig
    frames = list(range(1, 25))
    _add_noise(rig, "hand_ik.L", frames)
    mesh = dc.deformed_mesh(rig)
    idx = dc.part(mesh, "DEF-hand.L")

    def path():
        snap = dc.frames_snapshot(mesh, frames)
        return np.array([snap[f][idx].mean(axis=0) for f in frames])

    before = path()
    assert _smooth(rig, "hand_ik.L", 12, 6) == {'FINISHED'}
    after = path()
    window = slice(5, 18)
    print(f"hand skin path roughness: {_roughness(before[window]):.3e} -> {_roughness(after[window]):.3e}")
    assert _roughness(after[window]) < 0.5 * _roughness(before[window])
    assert np.abs(after[[0, 1, 2, 3, 20, 21, 22, 23]] - before[[0, 1, 2, 3, 20, 21, 22, 23]]).max() < 1e-5


# -- 5. tools and modes ----------------------------------------------------------------------------
def test_the_four_tools_exist(addon):
    sculpt_tool = importlib.import_module(addon.__name__ + ".interaction.sculpt_tool")
    labels = {t.bl_idname: t.bl_label for t in sculpt_tool.TOOLS}
    assert labels == {"animation_sculptor.tip": "Ponta", "animation_sculptor.sculpt": "Membro",
                      "animation_sculptor.body": "Corpo", "animation_sculptor.smooth": "Smooth"}
    assert sculpt_tool.TOOL_IDS == tuple(t.bl_idname for t in sculpt_tool.TOOLS)
    assert all(issubclass(t, bpy.types.WorkSpaceTool) for t in sculpt_tool.TOOLS)
    assert hasattr(bpy.ops.asc, "activate_tool")


def test_tools_can_be_activated_in_pose_mode(public_rig, addon):
    """The toolbar tools register in the workspace; activating needs a pose-mode 3D view context, which may
    not exist in background (then only the registration is checked)."""
    sculpt_tool = importlib.import_module(addon.__name__ + ".interaction.sculpt_tool")
    windows = bpy.context.window_manager.windows
    area = next((a for w in windows for a in w.screen.areas if a.type == 'VIEW_3D'), None)
    if area is None:
        pytest.skip("no 3D view in background Blender: tool activation needs a window")
    window = next(w for w in windows if area in list(w.screen.areas))
    region = next(r for r in area.regions if r.type == 'WINDOW')
    bpy.context.view_layer.objects.active = public_rig
    bpy.ops.object.mode_set(mode='POSE')
    for tool_id in sculpt_tool.TOOL_IDS:
        with bpy.context.temp_override(window=window, area=area, region=region):
            assert bpy.ops.wm.tool_set_by_id(name=tool_id) == {'FINISHED'}
            assert sculpt_tool.active_tool_id(bpy.context) == tool_id


def test_trail_mode_turns_the_trails_on(public_rig):
    scene = bpy.context.scene
    assert scene.asc_sculpt.interaction_mode == 'BODY'
    scene.asc_trails.enabled = False
    scene.asc_sculpt.interaction_mode = 'BODY'
    assert not scene.asc_trails.enabled
    scene.asc_sculpt.interaction_mode = 'TRAIL'
    assert scene.asc_trails.enabled


def test_onion_toggles_call_the_provider(public_rig, addon):
    provider = importlib.import_module(addon.__name__ + ".trails.provider")
    scene = bpy.context.scene
    sculpt, trails = scene.asc_sculpt, scene.asc_trails
    assert not trails.onion_show and not provider.onion_spread_enabled()
    sculpt.onion_show = True
    assert trails.onion_show
    sculpt.onion_spread = True
    assert provider.onion_spread_enabled()
    sculpt.onion_spread = False
    assert not provider.onion_spread_enabled()
    sculpt.onion_spread = True
    sculpt.onion_show = False                      # spread follows the onion
    assert not trails.onion_show and not provider.onion_spread_enabled()
