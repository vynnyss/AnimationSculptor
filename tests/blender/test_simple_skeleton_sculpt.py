# SPDX-License-Identifier: GPL-3.0-or-later
"""Sculpting on the simple skeleton (ADR 0014) checked on the deformed MESH, not only on the bones:
Membro (hand drag), Corpo (head drag, thigh pins) and Girar (RotateEdit) on the skinned test body."""

import importlib

import bpy
import numpy as np
import pytest

ARM_R = ("upper_arm.R", "forearm.R", "hand.R")
FINGERS_R = tuple(f"{n}.0{i}.R" for n in ("thumb", "index", "middle", "ring", "pinky") for i in (1, 2, 3))
FRAME = 12
RADIUS = 4
TOL_SPOT = 0.01        # 1 cm: the skin spot lands under the target
TOL_STILL = 1e-5


def _mod(addon, name):
    return importlib.import_module(f"{addon.__name__}.{name}")


def _body(rig):
    return bpy.data.objects["asc_test_body"]


def _groups(body):
    """{vertex group name: [vertex indices]} (the test body weights every vertex 1.0 to one group)."""
    names = {vg.index: vg.name for vg in body.vertex_groups}
    out = {}
    for v in body.data.vertices:
        out.setdefault(names[max(v.groups, key=lambda g: g.weight).group], []).append(v.index)
    return out


def _verts(body, frame):
    """Deformed vertices (V, 3), world, at ``frame`` (depsgraph evaluation)."""
    bpy.context.scene.frame_set(frame)
    ob_eval = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ob_eval.to_mesh()
    try:
        co = np.array([tuple(v.co) for v in mesh.vertices], dtype=np.float64)
    finally:
        ob_eval.to_mesh_clear()
    mw = np.asarray(ob_eval.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3]


def _all(body, frames):
    return {f: _verts(body, f) for f in frames}


def _dump(rig):
    cb = rig.animation_data.action.layers[0].strips[0].channelbags[0]
    return {(fc.data_path, fc.array_index): [(tuple(k.co), tuple(k.handle_left), tuple(k.handle_right),
                                              k.handle_left_type, k.handle_right_type, k.interpolation)
                                             for k in fc.keyframe_points] for fc in cb.fcurves}


def _tail_head(rig, bone, frame):
    bpy.context.scene.frame_set(frame)
    pb = rig.pose.bones[bone]
    mw = rig.matrix_world
    return np.array(mw @ pb.head), np.array(mw @ pb.tail)


def _side_face(body, indices):
    """A quad of the tube side (not a cap) whose vertices all belong to ``indices``."""
    ids = set(indices)
    for p in body.data.polygons:
        if len(p.vertices) == 4 and set(p.vertices) <= ids:
            return tuple(p.vertices)
    raise AssertionError("no side face")


def _face_spot(body, face, frame):
    pts = _verts(body, frame)[list(face)]
    return pts.mean(axis=0)


def _chain_edit(addon, rig, bone, scope, delta, radius=RADIUS):
    ee = _mod(addon, "interaction.ephemeral_edit")
    adapter = _mod(addon, "rig").get_adapter(rig)
    bones, reason = adapter.ephemeral_chain(rig, bone, scope)
    assert not reason, reason
    pins = adapter.ephemeral_pins(rig, bones)[0] if scope == "BODY" else []
    body = _body(rig)
    groups = _groups(body)
    face = _side_face(body, groups[bone])
    spot = _face_spot(body, face, FRAME)
    edit = ee.ChainEdit(rig, bones, FRAME, radius, radius, scope=scope, pins=pins, point_world=tuple(spot),
                        point_bone=bone, point_skin=(body.name, face))
    assert edit.editable, edit.reason
    edit.apply(delta)
    edit.finish()
    return edit, bones, face, spot


def _moved(a, b, idx):
    idx = list(idx)
    return float(np.abs(a[idx] - b[idx]).max()) if idx else 0.0


def _indices(groups, names):
    return [i for n in names for i in groups.get(n, [])]


def test_membro_drag_moves_the_hand_skin_and_nothing_else(simple_rig, addon):
    rig = simple_rig
    body = _body(rig)
    groups = _groups(body)
    frames = list(range(1, 25))
    before = _all(body, frames)
    dump = _dump(rig)
    delta = np.array((0.03, -0.04, 0.05))
    edit, bones, face, spot = _chain_edit(addon, rig, "hand.R", "LIMB", delta)
    assert bones == list(ARM_R)

    after = _all(body, frames)
    # the grabbed skin spot reaches its target (spot + delta) at the grabbed frame
    got = after[FRAME][list(face)].mean(axis=0)
    assert np.linalg.norm(got - (spot + delta)) < TOL_SPOT
    # every other limb, the trunk and the legs stay put at every frame (arm chain + R fingers move)
    moving = set(ARM_R) | set(FINGERS_R)
    others = _indices(groups, [n for n in groups if n not in moving])
    for f in frames:
        assert _moved(after[f], before[f], others) < TOL_STILL, f
    feet = _indices(groups, ("foot.L", "foot.R", "shin.L", "shin.R", "toe.L", "toe.R"))
    assert _moved(after[FRAME], before[FRAME], feet) < TOL_STILL
    assert _moved(after[FRAME], before[FRAME], groups["hand.R"]) > 0.02
    # outside the window nothing changes on the mesh either
    for f in frames:
        if f < FRAME - RADIUS or f > FRAME + RADIUS:
            assert _moved(after[f], before[f], range(len(after[f]))) < TOL_STILL, f

    # Action: keys outside the window (+1 pad) are bit-identical, edits live in the slot's channelbag
    action = rig.animation_data.action
    assert not hasattr(action, "fcurves")
    cb = action.layers[0].strips[0].channelbags[0]
    assert cb.slot_handle == rig.animation_data.action_slot.handle
    new = _dump(rig)
    lo, hi = FRAME - RADIUS - 1, FRAME + RADIUS + 1
    # (dense keys fill the span between the neighbouring keys, so extra keys may appear there, but every
    # original key outside the window survives untouched and the curve outside the window is unchanged)
    for key, keys in dump.items():
        new_cos = {k[0] for k in new[key]}
        for k in keys:
            if k[0][0] < lo or k[0][0] > hi:
                assert k[0] in new_cos, key
    path = 'pose.bones["forearm.R"].rotation_quaternion'
    window = sorted({round(k[0][0]) for k in new[(path, 0)] if lo <= k[0][0] <= hi})
    assert window == list(range(lo, hi + 1))
    # untouched bones' curves are bit-identical
    for key, keys in dump.items():
        if not any(b in key[0] for b in ARM_R):
            assert new[key] == keys, key
    edit.restore()
    assert _dump(rig) == dump


def test_corpo_drag_on_head_keeps_the_feet(simple_rig, addon):
    rig = simple_rig
    body = _body(rig)
    groups = _groups(body)
    frames = list(range(FRAME - RADIUS, FRAME + RADIUS + 1))
    before = _all(body, frames)
    delta = np.array((0.04, -0.05, 0.03))
    edit, bones, face, spot = _chain_edit(addon, rig, "head", "BODY", delta)
    assert bones == ["hips", "spine", "spine.001", "chest", "neck", "head"]
    assert sorted(limb[0] for _j, limb in edit.pins) == ["thigh.L", "thigh.R"]
    after = _all(body, frames)
    got = after[FRAME][list(face)].mean(axis=0)
    assert np.linalg.norm(got - (spot + delta)) < 0.02
    assert _moved(after[FRAME], before[FRAME], groups["head"]) > 0.02
    legs = _indices(groups, ("foot.L", "foot.R", "toe.L", "toe.R"))
    for f in frames:
        assert _moved(after[f], before[f], legs) < 5e-3, f      # pins hold the feet


def _rotate_edit(addon, rig, bone, **kw):
    ee = _mod(addon, "interaction.ephemeral_edit")
    edit = ee.RotateEdit(rig, bone, FRAME, RADIUS, RADIUS, **kw)
    assert edit.editable, edit.reason
    return edit


def _unit(v):
    return v / np.linalg.norm(v)


def _angle(a, b):
    return float(np.arccos(np.clip(np.dot(_unit(a), _unit(b)), -1.0, 1.0)))


def _xaxis(rig, bone):
    bpy.context.scene.frame_set(FRAME)
    return np.array(rig.matrix_world.to_3x3() @ rig.pose.bones[bone].matrix.to_3x3().col[0])


def test_rotate_forearm_about_the_view_axis(simple_rig, addon):
    rig = simple_rig
    body = _body(rig)
    groups = _groups(body)
    h0, t0 = _tail_head(rig, "forearm.R", FRAME)
    d0 = t0 - h0
    axis = _unit(np.cross(d0, (0.3, 0.2, 1.0)))             # a view axis perpendicular to the bone
    before = _all(body, (FRAME, 1))
    edit = _rotate_edit(addon, rig, "forearm.R", view_axis=tuple(axis))
    angle = 0.5
    edit.apply_rotation(angle)
    h1, t1 = _tail_head(rig, "forearm.R", FRAME)
    assert np.linalg.norm(h1 - h0) < 1e-5                    # turns about its head
    assert abs(_angle(d0, t1 - h1) - angle) < 1e-3
    assert np.dot(np.cross(d0, t1 - h1), axis) > 0           # turn direction follows the axis (right hand)
    after = _all(body, (FRAME, 1))
    assert _moved(after[FRAME], before[FRAME], groups["forearm.R"]) > 0.02
    assert _moved(after[FRAME], before[FRAME], groups["hand.R"]) > 0.02
    for name in ("upper_arm.R", "upper_arm.L", "chest", "head", "thigh.R"):
        assert _moved(after[FRAME], before[FRAME], groups[name]) < TOL_STILL, name
    assert _moved(after[1], before[1], range(len(after[1]))) < TOL_STILL      # outside the window


def test_rotate_twist_turns_about_the_bone_axis(simple_rig, addon):
    rig = simple_rig
    body = _body(rig)
    groups = _groups(body)
    h0, t0 = _tail_head(rig, "forearm.R", FRAME)
    x0 = _xaxis(rig, "forearm.R")
    before = _verts(body, FRAME)
    edit = _rotate_edit(addon, rig, "forearm.R")
    angle = 0.6
    edit.apply_rotation(angle, twist=True)
    h1, t1 = _tail_head(rig, "forearm.R", FRAME)
    x1 = _xaxis(rig, "forearm.R")
    assert np.linalg.norm(t1 - t0) < 1e-5 and np.linalg.norm(h1 - h0) < 1e-5   # tail stays put
    assert abs(_angle(x0, x1) - angle) < 1e-3                                  # roll changes by the angle
    after = _verts(body, FRAME)
    assert _moved(after, before, groups["forearm.R"]) > 0.005
    assert _moved(after, before, groups["upper_arm.R"]) < TOL_STILL


def test_rotate_angle_zero_leaves_the_action_bit_identical(simple_rig, addon):
    rig = simple_rig
    dump = _dump(rig)
    edit = _rotate_edit(addon, rig, "forearm.R")
    edit.apply_rotation(0.0)
    edit.apply_rotation(0.0, twist=True)
    assert _dump(rig) == dump


def test_rotate_angle_zero_leaves_the_pose_and_mesh_unchanged(simple_rig, addon):
    rig = simple_rig
    body = _body(rig)
    frames = list(range(1, 25))
    before = _all(body, frames)
    edit = _rotate_edit(addon, rig, "forearm.R")
    edit.apply_rotation(0.0)
    edit.apply_rotation(0.0, twist=True)
    after = _all(body, frames)
    for f in frames:
        assert _moved(after[f], before[f], range(len(after[f]))) < 1e-5, f


@pytest.mark.parametrize("gesture", ["membro", "corpo", "girar", "twist"])
def test_root_never_rotates_and_hips_location_is_untouched(simple_rig, addon, gesture):
    rig = simple_rig
    adapter = _mod(addon, "rig").get_adapter(rig)
    assert tuple(rig.pose.bones["root"].lock_rotation) == (True, True, True)
    assert adapter.classify(rig, "root").rotates is False
    dump = _dump(rig)
    if gesture == "membro":
        _chain_edit(addon, rig, "hand.R", "LIMB", np.array((0.03, -0.04, 0.05)))
    elif gesture == "corpo":
        _chain_edit(addon, rig, "head", "BODY", np.array((0.04, -0.05, 0.03)))
    else:
        edit = _rotate_edit(addon, rig, "forearm.R", view_axis=(0.0, 0.0, 1.0))
        edit.apply_rotation(0.7, twist=gesture == "twist")
    new = _dump(rig)
    assert new != dump
    for key in set(dump) | set(new):
        if '"root"' in key[0] or "location" in key[0]:
            assert new.get(key) == dump.get(key), key       # root and every location curve untouched
    assert not any('"root"' in k[0] for k in new)
    hips_rot_changed = any('"hips"' in k[0] and "rotation" in k[0] and new[k] != dump.get(k) for k in new)
    assert hips_rot_changed == (gesture == "corpo")          # only BODY turns the hips
    for f in (1, FRAME, 24):
        bpy.context.scene.frame_set(f)
        assert tuple(rig.pose.bones["root"].rotation_quaternion) == (1.0, 0.0, 0.0, 0.0)
