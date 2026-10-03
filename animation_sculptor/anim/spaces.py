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
