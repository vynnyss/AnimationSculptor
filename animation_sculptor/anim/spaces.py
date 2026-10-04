# SPDX-License-Identifier: GPL-3.0-or-later
"""Base space of a pose bone's ``location`` channels.

``P`` is the affine map from the bone's ``location`` values to the world position of its head at the
current (evaluated) frame: ``head_world = P @ location``, with the bone's rotation/scale held fixed.

``M_arm · M_pose · M_basis⁻¹`` (Motiontrail3D) is only right when ``Bone.use_local_location`` is on;
Rigify IK controls (``hand_ik``, ``foot_ik``…) have it off, so ``location`` acts along the parent's
axes, not the bone's. Instead we ask Blender itself: ``Object.convert_space(LOCAL → POSE)`` applies the
real inheritance rules (local location, inherit rotation/scale, parent pose), and since the head is
affine in ``location`` four conversions give the exact map.
"""

from mathutils import Matrix, Vector


def location_space(ob, pb) -> Matrix:
    """4×4 world matrix ``P`` with ``head_world = P @ location`` at the current frame."""
    basis = pb.matrix_basis
    rot_scale = basis.to_3x3().to_4x4()

    def head_pose(loc):
        local = Matrix.Translation(loc) @ rot_scale
        return ob.convert_space(pose_bone=pb, matrix=local, from_space='LOCAL', to_space='POSE').translation

    origin = head_pose(Vector((0.0, 0.0, 0.0)))
    p = Matrix.Identity(4)
    for axis in range(3):
        e = Vector((0.0, 0.0, 0.0))
        e[axis] = 1.0
        col = head_pose(e) - origin
        for row in range(3):
            p[row][axis] = col[row]
    p.translation = origin
    return ob.matrix_world @ p


def _animated_bones(ob):
    """Names of pose bones with F-Curves or drivers on the object (any channel)."""
    names = set()
    adt = ob.animation_data
    if adt is None:
        return names
    sources = list(adt.drivers)
    if adt.action is not None and adt.action_slot is not None:
        from bpy_extras import anim_utils

        cb = anim_utils.action_get_channelbag_for_slot(adt.action, adt.action_slot)
        if cb is not None:
            sources += list(cb.fcurves)
    for fc in sources:
        path = fc.data_path
        if path.startswith('pose.bones["'):
            names.add(path[len('pose.bones["'):].split('"]', 1)[0])
    return names


def is_space_constant(ob, pb) -> bool:
    """True when the base space of ``location`` cannot change over time: no ancestor of the bone is
    animated or constrained, no driver/animation moves the armature object or its parents, and the
    bone has no constraints of its own. Conservative: False whenever unsure."""
    animated = _animated_bones(ob)   # F-Curves and drivers, by the pose bone they write to
    if pb.constraints:
        return False
    parent = pb.parent
    while parent is not None:
        if parent.name in animated or len(parent.constraints):
            return False
        parent = parent.parent
    if ob.constraints or _object_level_animation(ob):
        return False
    o = ob.parent
    while o is not None:
        adt = o.animation_data
        if o.constraints or (adt is not None and (adt.action is not None or len(adt.drivers))):
            return False
        o = o.parent
    return True


def _object_level_animation(ob) -> bool:
    adt = ob.animation_data
    if adt is None:
        return False
    if any(not d.data_path.startswith("pose.") for d in adt.drivers):
        return True
    if adt.action is None or adt.action_slot is None:
        return False
    from bpy_extras import anim_utils

    cb = anim_utils.action_get_channelbag_for_slot(adt.action, adt.action_slot)
    return cb is not None and any(not fc.data_path.startswith("pose.") for fc in cb.fcurves)


def prefetch(ob, pb, frames, scene):
    """``P(f)`` for each frame as a (N, 4, 4) numpy array. Frame stepping (Rigify is evaluated by the
    depsgraph), skipped when the space is constant. The scene returns to its current frame.
    Returns (matrices, constant)."""
    import numpy as np

    frames = [int(f) for f in frames]
    if not frames:
        return np.empty((0, 4, 4)), True
    if is_space_constant(ob, pb):
        p = np.array(location_space(ob, pb), dtype=np.float64)
        return np.repeat(p[None], len(frames), axis=0), True
    current, sub = scene.frame_current, scene.frame_subframe
    mats = np.empty((len(frames), 4, 4))
    with preserve_pose(ob):
        try:
            for i, f in enumerate(frames):
                scene.frame_set(f)
                mats[i] = np.array(location_space(ob, pb), dtype=np.float64)
        finally:
            scene.frame_set(current, subframe=sub)
    return mats, False


_POSE_CHANNELS = ("location", "rotation_quaternion", "rotation_euler", "rotation_axis_angle", "scale")


class preserve_pose:
    """Context manager: frame stepping re-applies the Action and would discard pose edits that are not
    keyed yet; the current pose of ``ob`` is put back on exit."""

    def __init__(self, ob):
        self.ob = ob

    def __enter__(self):
        self.saved = [(pb.name, [tuple(getattr(pb, c)) for c in _POSE_CHANNELS]) for pb in self.ob.pose.bones]
        return self

    def __exit__(self, *exc):
        bones = self.ob.pose.bones
        for name, values in self.saved:
            pb = bones.get(name)
            if pb is None:
                continue
            for channel, value in zip(_POSE_CHANNELS, values):
                if tuple(getattr(pb, channel)) != value:
                    setattr(pb, channel, value)
        return False
