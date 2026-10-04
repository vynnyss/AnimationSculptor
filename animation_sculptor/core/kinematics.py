# SPDX-License-Identifier: GPL-3.0-or-later
"""Rigid-chain kinematics for the ephemeral rig (pure numpy — ADR 0008, ADR 0011).

Conventions follow Blender: quaternions are (w, x, y, z); a bone's local transform ("basis") is
T(location) · R(rotation) · S(scale); a bone points along its local +Y, tail = head + (0, length, 0).
Euler orders name the axes in application order: 'XYZ' means R = Rz · Ry · Rx.

Chain model (docs/design/ephemeral-rig.md): bones root → tip, with

    world[0] = base(f) · basis[0](f)
    world[i] = world[i-1] · link[i](f) · basis[i](f)        (i ≥ 1)

``base(f)`` is the world matrix of the root's parent space (from frame stepping in ``anim/spaces``),
``link[i]`` the rigid transform from bone i-1 to bone i's parent space (``inv(rest[i-1]) · rest[i]`` for a
plain child; measured per frame when there is a helper bone in between, e.g. Rigify's ``MCH-hand_fk``).
Nothing here knows bone names or Blender types. Every function is deterministic (fixed operation order).
"""

from __future__ import annotations

import numpy as np

EULER_ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
_AXIS = {"X": 0, "Y": 1, "Z": 2}
EPS = 1e-12
GIMBAL_EPS = 1e-12    # float64 (Blender uses 16·FLT_EPSILON for its float matrices)


# --------------------------------------------------------------------------------------------- vectors
def normalize(v, axis=-1):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v, axis=axis, keepdims=True)
    return np.where(n > EPS, v / np.where(n > EPS, n, 1.0), 0.0)


def any_perpendicular(v):
    """A unit vector perpendicular to each (…, 3) ``v`` (deterministic choice)."""
    v = np.asarray(v, dtype=np.float64)
    ref = np.where((np.abs(v[..., 0]) < 0.9)[..., None], np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]))
    return normalize(np.cross(v, ref))


# ------------------------------------------------------------------------------------------ quaternions
def quat_normalize(q):
    return normalize(q)


def quat_mul(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack((aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw), axis=-1)


def quat_conj(q):
    q = np.asarray(q, dtype=np.float64)
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def quat_from_axis_angle(axis, angle):
    axis = normalize(axis)
    half = 0.5 * np.asarray(angle, dtype=np.float64)
    return np.concatenate((np.cos(half)[..., None], axis * np.sin(half)[..., None]), axis=-1)


def quat_to_mat3(q):
    q = quat_normalize(q)
    w, x, y, z = np.moveaxis(q, -1, 0)
    m = np.empty(q.shape[:-1] + (3, 3))
    m[..., 0, 0] = 1 - 2 * (y * y + z * z)
    m[..., 0, 1] = 2 * (x * y - w * z)
    m[..., 0, 2] = 2 * (x * z + w * y)
    m[..., 1, 0] = 2 * (x * y + w * z)
    m[..., 1, 1] = 1 - 2 * (x * x + z * z)
    m[..., 1, 2] = 2 * (y * z - w * x)
    m[..., 2, 0] = 2 * (x * z - w * y)
    m[..., 2, 1] = 2 * (y * z + w * x)
    m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def mat3_to_quat(m):
    """Rotation matrix (…, 3, 3) → unit quaternion with w ≥ 0 (Shepperd's method, vectorised)."""
    m = np.asarray(m, dtype=np.float64)
    shape = m.shape[:-2]
    a = m.reshape(-1, 3, 3)
    m00, m11, m22 = a[:, 0, 0], a[:, 1, 1], a[:, 2, 2]
    tr = m00 + m11 + m22
    with np.errstate(invalid="ignore", divide="ignore"):
        s0 = 2.0 * np.sqrt(np.maximum(tr + 1.0, 0.0))
        s1 = 2.0 * np.sqrt(np.maximum(1.0 + m00 - m11 - m22, 0.0))
        s2 = 2.0 * np.sqrt(np.maximum(1.0 + m11 - m00 - m22, 0.0))
        s3 = 2.0 * np.sqrt(np.maximum(1.0 + m22 - m00 - m11, 0.0))
        q0 = np.stack((0.25 * s0, (a[:, 2, 1] - a[:, 1, 2]) / s0, (a[:, 0, 2] - a[:, 2, 0]) / s0,
                       (a[:, 1, 0] - a[:, 0, 1]) / s0), axis=-1)
        q1 = np.stack(((a[:, 2, 1] - a[:, 1, 2]) / s1, 0.25 * s1, (a[:, 0, 1] + a[:, 1, 0]) / s1,
                       (a[:, 0, 2] + a[:, 2, 0]) / s1), axis=-1)
        q2 = np.stack(((a[:, 0, 2] - a[:, 2, 0]) / s2, (a[:, 0, 1] + a[:, 1, 0]) / s2, 0.25 * s2,
                       (a[:, 1, 2] + a[:, 2, 1]) / s2), axis=-1)
        q3 = np.stack(((a[:, 1, 0] - a[:, 0, 1]) / s3, (a[:, 0, 2] + a[:, 2, 0]) / s3,
                       (a[:, 1, 2] + a[:, 2, 1]) / s3, 0.25 * s3), axis=-1)
    use0 = tr > 0.0
    use1 = ~use0 & (m00 > m11) & (m00 > m22)
    use2 = ~use0 & ~use1 & (m11 > m22)
    q = np.where(use0[:, None], q0, np.where(use1[:, None], q1, np.where(use2[:, None], q2, q3)))
    q = quat_normalize(q)
    q = np.where((q[:, 0] < 0.0)[:, None], -q, q)
    return q.reshape(shape + (4,))


def quat_continuity(q, previous=None):
    """Flip quaternions along axis 0 so consecutive ones share a hemisphere (q·q_prev ≥ 0).

    ``previous`` (4,) is the quaternion before the first one (e.g. the key left of the window)."""
    q = np.array(q, dtype=np.float64)
    prev = None if previous is None else np.asarray(previous, dtype=np.float64)
    for i in range(len(q)):
        if prev is not None and float(np.dot(q[i], prev)) < 0.0:
            q[i] = -q[i]
        prev = q[i]
    return q


def rotation_between(a, b):
    """Minimal rotation matrix taking direction ``a`` to direction ``b`` (…, 3) — Blender's
    ``rotation_difference`` of the two directions. Opposite vectors rotate 180° about a perpendicular."""
    a = normalize(a)
    b = normalize(b)
    axis = np.cross(a, b)
    s = np.linalg.norm(axis, axis=-1)
    c = np.clip(np.sum(a * b, axis=-1), -1.0, 1.0)
    angle = np.arctan2(s, c)
    fallback = any_perpendicular(a)
    axis = np.where((s > 1e-9)[..., None], axis / np.where(s > 1e-9, s, 1.0)[..., None], fallback)
    return axis_angle_to_mat3(axis, angle)


def axis_angle_to_mat3(axis, angle):
    return quat_to_mat3(quat_from_axis_angle(axis, angle))


# ------------------------------------------------------------------------------------------------ euler
def _check_order(order):
    if order not in EULER_ORDERS:
        raise ValueError(f"unknown euler order {order!r}")


def _axis_mat(axis, angle):
    c, s = np.cos(angle), np.sin(angle)
    m = np.zeros(np.shape(angle) + (3, 3))
    i = _AXIS[axis]
    j, k = (i + 1) % 3, (i + 2) % 3
    m[..., i, i] = 1.0
    m[..., j, j] = c
    m[..., k, k] = c
    m[..., k, j] = s
    m[..., j, k] = -s
    return m


def euler_to_mat3(e, order="XYZ"):
    """Euler angles (…, 3) stored as (x, y, z) → rotation matrix; the first axis of ``order`` applies first."""
    _check_order(order)
    e = np.asarray(e, dtype=np.float64)
    m = None
    for axis in order:
        r = _axis_mat(axis, e[..., _AXIS[axis]])
        m = r if m is None else r @ m
    return m


def _mat3_to_euler_pair(m, order):
    """The two Euler solutions (…, 3) of a rotation matrix for ``order`` (R = R_k(c) · R_j(b) · R_i(a)).

    Even orders (XYZ, YZX, ZXY): R[k,i] = −sin b, R[k,j] = cos b sin a, R[j,i] = cos b sin c; odd orders
    flip the signs of those three terms (parity p = ±1). Near gimbal lock (cos b ≈ 0) c = 0."""
    i, j, k = (_AXIS[ax] for ax in order)
    p = 1.0 if (j - i) % 3 == 1 else -1.0
    m = np.asarray(m, dtype=np.float64)
    cy = np.hypot(m[..., i, i], m[..., j, i])
    big = cy > GIMBAL_EPS
    sb = -p * m[..., k, i]
    e1 = np.empty(m.shape[:-2] + (3,))
    e2 = np.empty_like(e1)
    e1[..., i] = np.where(big, np.arctan2(p * m[..., k, j], m[..., k, k]), np.arctan2(-p * m[..., j, k], m[..., j, j]))
    e1[..., j] = np.arctan2(sb, cy)
    e1[..., k] = np.where(big, np.arctan2(p * m[..., j, i], m[..., i, i]), 0.0)
    e2[..., i] = np.where(big, np.arctan2(-p * m[..., k, j], -m[..., k, k]), e1[..., i])
    e2[..., j] = np.where(big, np.arctan2(sb, -cy), e1[..., j])
    e2[..., k] = np.where(big, np.arctan2(-p * m[..., j, i], -m[..., i, i]), 0.0)
    return e1, e2


def _wrap_to(e, ref):
    """Shift each angle by multiples of 2π to lie within π of ``ref``."""
    return e - 2.0 * np.pi * np.round((e - ref) / (2.0 * np.pi))


def mat3_to_euler(m, order="XYZ", compatible=None):
    """Rotation matrix → Euler (x, y, z). With ``compatible`` (…, 3), pick the solution (and 2π shifts)
    closest to it, like Blender's ``Matrix.to_euler(order, compatible)``; otherwise the first solution."""
    _check_order(order)
    e1, e2 = _mat3_to_euler_pair(m, order)
    if compatible is None:
        return e1
    ref = np.asarray(compatible, dtype=np.float64)
    e1 = _wrap_to(e1, ref)
    e2 = _wrap_to(e2, ref)
    d1 = np.sum(np.abs(e1 - ref), axis=-1)
    d2 = np.sum(np.abs(e2 - ref), axis=-1)
    return np.where((d2 < d1)[..., None], e2, e1)


def euler_continuity(m, order, previous):
    """Rotation matrices (N, 3, 3) → Euler (N, 3), each compatible with the one before (``previous`` first)."""
    out = np.empty((len(m), 3))
    prev = np.asarray(previous, dtype=np.float64)
    for i in range(len(m)):
        out[i] = mat3_to_euler(m[i], order, prev)
        prev = out[i]
    return out


# ---------------------------------------------------------------------------------------------- basis
def rotation_to_mat3(rot, mode):
    """Rotation values (quaternion (…, 4) or Euler (…, 3)) for a Blender rotation mode → (…, 3, 3)."""
    if mode == "QUATERNION":
        return quat_to_mat3(rot)
    if mode in EULER_ORDERS:
        return euler_to_mat3(rot, mode)
    raise ValueError(f"unsupported rotation mode {mode!r}")


def basis_matrices(loc, rot3, scale):
    """T · R · S as (…, 4, 4) from location (…, 3), rotation matrices (…, 3, 3) and scale (…, 3)."""
    loc = np.asarray(loc, dtype=np.float64)
    m = np.zeros(loc.shape[:-1] + (4, 4))
    m[..., :3, :3] = np.asarray(rot3, dtype=np.float64) * np.asarray(scale, dtype=np.float64)[..., None, :]
    m[..., :3, 3] = loc
    m[..., 3, 3] = 1.0
    return m


def forward(base, links, basis):
    """World matrices (N, K, 4, 4) of a chain.

    base (N, 4, 4); links (K, 4, 4) or (N, K, 4, 4) — ``links[:, 0]`` is ignored (the root hangs from
    ``base``); basis (N, K, 4, 4)."""
    base = np.asarray(base, dtype=np.float64)
    basis = np.asarray(basis, dtype=np.float64)
    links = np.asarray(links, dtype=np.float64)
    n, k = basis.shape[:2]
    if links.ndim == 3:
        links = np.broadcast_to(links, (n,) + links.shape)
    world = np.empty((n, k, 4, 4))
    world[:, 0] = base @ basis[:, 0]
    for i in range(1, k):
        world[:, i] = world[:, i - 1] @ links[:, i] @ basis[:, i]
    return world


def tails(world, lengths):
    """Tail positions (N, K, 3): head + world Y axis × length (bone scale included, as in Blender)."""
    lengths = np.asarray(lengths, dtype=np.float64)
    return world[..., :3, 3] + world[..., :3, 1] * lengths[..., None]


def local_rotation_update(frame_rot, delta_world, rot3_local):
    """New local rotation matrices when a bone's world orientation is turned by ``delta_world``.

    ``frame_rot`` (…, 3, 3) is the rotation of the bone's *parent space* (world · link, before the
    bone's own basis) **before** any change of its ancestors; ``delta_world`` is the bone's own turn
    expressed in that old configuration (ancestor turns excluded). Result: ``F⁻¹ · Δ · F · R`` —
    exact when ``F`` is a rotation or a similarity, re-orthonormalised otherwise."""
    f = np.asarray(frame_rot, dtype=np.float64)
    f_inv = np.linalg.inv(f)
    r = f_inv @ np.asarray(delta_world, dtype=np.float64) @ f @ np.asarray(rot3_local, dtype=np.float64)
    return orthonormalize(r)


def orthonormalize(m):
    """Nearest rotation (polar decomposition via SVD), keeping det = +1."""
    u, _s, vt = np.linalg.svd(np.asarray(m, dtype=np.float64))
    r = u @ vt
    det = np.linalg.det(r)
    fix = np.ones(r.shape[:-2] + (3,))
    fix[..., 2] = np.sign(np.where(det == 0.0, 1.0, det))
    return (u * fix[..., None, :]) @ vt


def unit_rotation(m):
    """Rotation part of (…, 3, 3) linear maps with scale (columns normalised, then orthonormalised)."""
    return orthonormalize(m)


# ------------------------------------------------------------------------------------------------- IK
def two_bone_ik(a, b, c, target, bend_axis=None):
    """Analytic two-bone IK in world space, vectorised over (N, 3).

    a = root head, b = middle joint, c = tip (end of the second bone), ``target`` = wanted tip.
    The bend happens in the current plane of (a, b, c) — the existing pose is the pole, the limb never
    flips; ``bend_axis`` (N, 3) is the fallback normal when the limb is straight. Out of reach ⇒ the
    limb stretches to its limit towards the target (no scaling); too close ⇒ folds to |l1 − l2|.

    Returns (Δ1, Δ2): world rotations (N, 3, 3) — Δ1 turns the first bone about ``a``; Δ2 turns the
    second bone about ``b`` in the old configuration — and the new tip positions (N, 3).
    New positions: b' = a + Δ1 (b − a), c' = b' + Δ1 Δ2 (c − b).
    """
    a, b, c, t = (np.asarray(v, dtype=np.float64) for v in (a, b, c, target))
    u1, u2 = b - a, c - b
    l1 = np.linalg.norm(u1, axis=-1)
    l2 = np.linalg.norm(u2, axis=-1)
    n = np.cross(u1, u2)
    nlen = np.linalg.norm(n, axis=-1)
    if bend_axis is None:
        fallback = any_perpendicular(u1)
    else:
        fallback = normalize(np.asarray(bend_axis, dtype=np.float64) - normalize(u1) * np.sum(
            np.asarray(bend_axis, dtype=np.float64) * normalize(u1), axis=-1, keepdims=True))
        fallback = np.where((np.linalg.norm(fallback, axis=-1) > EPS)[..., None], fallback, any_perpendicular(u1))
    n = np.where((nlen > 1e-9 * np.maximum(l1 * l2, EPS))[..., None], n / np.maximum(nlen, EPS)[..., None], fallback)

    # 1) bend: interior angle at b so that |c' − a| = d
    d = np.linalg.norm(t - a, axis=-1)
    d = np.clip(d, np.abs(l1 - l2), l1 + l2)
    cos_b = np.clip((l1 * l1 + l2 * l2 - d * d) / np.maximum(2.0 * l1 * l2, EPS), -1.0, 1.0)
    interior_new = np.arccos(cos_b)
    cos_old = np.clip(np.sum(-u1 * u2, axis=-1) / np.maximum(l1 * l2, EPS), -1.0, 1.0)
    interior_old = np.arccos(cos_old)
    # turning u2 about n by +θ decreases the interior angle by θ (n = u1 × u2 orientation)
    d2 = axis_angle_to_mat3(n, interior_old - interior_new)
    c_bent = b + np.einsum("nij,nj->ni", d2, u2)

    # 2) swing: minimal rotation about a taking (c_bent − a) to (t − a)
    to_t = t - a
    reach = c_bent - a
    d1 = rotation_between(reach, np.where((np.linalg.norm(to_t, axis=-1) > EPS)[..., None], to_t, reach))
    tip = a + np.einsum("nij,nj->ni", d1, reach)
    return d1, d2, tip


def aim(head, tail, target):
    """Minimal world rotation (N, 3, 3) about ``head`` pointing the bone (head → tail) at ``target``."""
    head, tail, target = (np.asarray(v, dtype=np.float64) for v in (head, tail, target))
    to_t = target - head
    cur = tail - head
    ok = (np.linalg.norm(to_t, axis=-1) > EPS)[..., None]
    return rotation_between(cur, np.where(ok, to_t, cur))
