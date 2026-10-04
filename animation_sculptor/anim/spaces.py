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

    def __init__(self, ob, skip=()):
        """``skip``: bones whose pose is NOT put back (a gesture that just wrote their curves wants the
        evaluated Action there, not the values from before its own write)."""
        self.ob = ob
        self.skip = set(skip)

    def __enter__(self):
        self.saved = [(pb.name, [tuple(getattr(pb, c)) for c in _POSE_CHANNELS]) for pb in self.ob.pose.bones
                      if pb.name not in self.skip]
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


ROTATION_CHANNEL = {"QUATERNION": "rotation_quaternion", "AXIS_ANGLE": "rotation_axis_angle"}


def rotation_channel(pb):
    """(data path channel, size) of the rotation values a pose bone's mode uses."""
    channel = ROTATION_CHANNEL.get(pb.rotation_mode, "rotation_euler")
    return channel, 3 if channel == "rotation_euler" else 4


def prefetch_chain(ob, bones, frames, scene, extra=()):
    """Everything the ephemeral gesture needs about an FK chain at each frame, by frame stepping
    (ADR 0011, docs/design/ephemeral-rig.md): a dict with

    - ``base`` (N, 4, 4): world matrix of the root's parent space (``world[0] = base · basis[0]``);
    - ``links`` (N, K, 4, 4): rigid transform from bone i−1 to bone i's parent space, measured per frame
      (``inv(pose[i−1]) · pose[i] · inv(basis[i])``) — exact also when a helper bone sits in between
      (Rigify's ``MCH-hand_fk``);
    - ``loc``/``scale`` (N, K, 3), ``rot`` (K arrays (N, 4|3)), ``modes``, ``lengths`` (K,), ``locks`` (K, 3).

    ``extra``: other bones whose world matrices (N, 4, 4) are also sampled (``out["extra"][name]``), e.g.
    the bone a grabbed point belongs to when it is not the chain's last bone.

    The live (unkeyed) pose is kept (``preserve_pose``) and the scene returns to its current frame.
    """
    import numpy as np

    frames = [int(f) for f in frames]
    pbs = [ob.pose.bones[b] for b in bones]
    n, k = len(frames), len(pbs)
    modes = [pb.rotation_mode for pb in pbs]
    channels = [rotation_channel(pb) for pb in pbs]
    out = {
        "base": np.empty((n, 4, 4)), "links": np.broadcast_to(np.eye(4), (n, k, 4, 4)).copy(),
        "loc": np.empty((n, k, 3)), "scale": np.empty((n, k, 3)),
        "rot": [np.empty((n, size)) for _channel, size in channels], "modes": modes,
        "lengths": np.array([pb.bone.length for pb in pbs], dtype=np.float64),
        "locks": np.array([tuple(pb.lock_rotation) for pb in pbs], dtype=bool),
        "extra": {name: np.empty((n, 4, 4)) for name in extra},
    }
    mw = np.array(ob.matrix_world, dtype=np.float64)
    current, sub = scene.frame_current, scene.frame_subframe
    with preserve_pose(ob):
        try:
            for fi, f in enumerate(frames):
                scene.frame_set(f)
                pose = [np.array(pb.matrix, dtype=np.float64) for pb in pbs]
                basis_inv = [np.linalg.inv(np.array(pb.matrix_basis, dtype=np.float64)) for pb in pbs]
                out["base"][fi] = mw @ pose[0] @ basis_inv[0]
                for i, pb in enumerate(pbs):
                    if i:
                        out["links"][fi, i] = np.linalg.inv(pose[i - 1]) @ pose[i] @ basis_inv[i]
                    out["loc"][fi, i] = pb.location
                    out["scale"][fi, i] = pb.scale
                    out["rot"][i][fi] = getattr(pb, channels[i][0])
                for name in extra:
                    out["extra"][name][fi] = mw @ np.array(ob.pose.bones[name].matrix, dtype=np.float64)
        finally:
            scene.frame_set(current, subframe=sub)
    return out


RIGID_TOL = 1e-5
_PROBE_ANGLE = 0.3      # radians: test turn applied to each chain bone in turn


def _links(ob, pairs):
    """{(parent, child): inv(pose[parent]) · pose[child] · inv(basis[child])} at the evaluated frame."""
    import numpy as np

    bones = ob.pose.bones
    out = {}
    for parent, child in pairs:
        pp = np.array(bones[parent].matrix, dtype=np.float64)
        pc = np.array(bones[child].matrix, dtype=np.float64)
        bc = np.array(bones[child].matrix_basis, dtype=np.float64)
        out[(parent, child)] = np.linalg.inv(pp) @ pc @ np.linalg.inv(bc)
    return out


def chain_rigidity(ob, bones, attached=()):
    """'' when every link of the chain is rigid, else the reason (ADR 0011: the ephemeral solve assumes
    rigid links between consecutive chain bones and between a chain bone and a pinned limb root).

    Each chain bone is turned a little in turn (at the current frame, live pose) and every link below it
    is measured again; helpers driven by constraints that blend with other bones (Rigify's spine
    distribution, Neck/Head Follow) change and are reported. ``attached``: (chain bone, limb root) pairs.
    The pose is put back exactly; costs one depsgraph update per chain bone."""
    import numpy as np
    from mathutils import Matrix

    pairs = list(zip(bones[:-1], bones[1:])) + list(attached)
    if not pairs:
        return ""
    view_layer = __import__("bpy").context.view_layer
    view_layer.update()
    rest = _links(ob, pairs)
    reason = ""
    with preserve_pose(ob):
        try:
            for j, name in enumerate(bones):
                below = pairs       # a rigid link depends on no chain bone (constraints may reach across)
                pb = ob.pose.bones[name]
                saved = pb.matrix_basis.copy()
                pb.matrix_basis = saved @ Matrix.Rotation(_PROBE_ANGLE, 4, (0.6, 0.0, 0.8))
                view_layer.update()
                probe = _links(ob, below)
                pb.matrix_basis = saved
                for pair in below:
                    if np.abs(probe[pair] - rest[pair]).max() > RIGID_TOL:
                        reason = (f"cadeia não rígida: {pair[1]} não segue {pair[0]} rigidamente "
                                  "(bone auxiliar com constraint entre eles)")
                        break
                if reason:
                    break
        finally:
            view_layer.update()
    return reason
