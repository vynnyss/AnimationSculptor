# SPDX-License-Identifier: GPL-3.0-or-later
"""Damped least squares with a fixed number of iterations (pure numpy — ADR 0008, ADR 0011).

Used by the ephemeral rig for chains longer than two bones (spine, neck, ``Corpo``). Same input ⇒ same
output: fixed iteration count, fixed damping, fixed order of operations, no randomness. Pins (fixed
world points per frame) come in phase 4 of docs/design/ephemeral-rig.md.

Each joint has 3 rotational degrees of freedom about world axes; the Jacobian column of joint j and
axis e is ``e × (tip − p_j)``. ``Δθ = Jᵀ (J Jᵀ + λ² I)⁻¹ (target − tip)`` per iteration, applied from the
root to the tip. The error is clamped to ``MAX_STEP`` × chain length per iteration so far (unreachable)
targets do not make it overshoot.
"""

from __future__ import annotations

import numpy as np

from . import kinematics

ITERATIONS = 16
DAMPING = 0.05          # λ, relative to the chain length
MAX_STEP = 0.25         # largest tip correction per iteration, relative to the chain length


def dls_chain(joints, tip, target, iterations=ITERATIONS, damping=DAMPING, stiffness=None):
    """Turn a chain of joints so ``tip`` reaches ``target`` (vectorised over N frames).

    joints (N, K, 3): head of each bone, root first; tip (N, 3): the dragged point (rigid with the
    last bone); target (N, 3); stiffness (K,): ≥ 1 resists turning (1 = free).

    Returns (deltas, tip_new): ``deltas`` (N, K, 3, 3) are the bones' *own* world turns in the old
    configuration (bone j's new world orientation = deltas[0] · … · deltas[j] · old), ready for
    ``kinematics.local_rotation_update``.
    """
    p = np.array(joints, dtype=np.float64)
    tip = np.array(tip, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    n, k = p.shape[:2]
    length = np.linalg.norm(np.diff(np.concatenate((p, tip[:, None]), axis=1), axis=1), axis=-1).sum(axis=1)
    lam2 = (damping * np.maximum(length, 1e-9)) ** 2
    scale = np.ones(k) if stiffness is None else 1.0 / np.asarray(stiffness, dtype=np.float64)
    total = np.broadcast_to(np.eye(3), (n, k, 3, 3)).copy()     # G_j: world turn applied to bone j
    axes = np.eye(3)
    for _ in range(iterations):
        err = target - tip
        norm = np.linalg.norm(err, axis=-1, keepdims=True)
        limit = MAX_STEP * length[:, None]
        err = np.where(norm > limit, err * (limit / np.maximum(norm, 1e-300)), err)   # far targets: no overshoot
        r = tip[:, None, :] - p                                  # (N, K, 3)
        jac = np.cross(axes[None, None, :, :], r[:, :, None, :])  # (N, K, 3 axes, 3) column per (joint, axis)
        jac = (jac * scale[None, :, None, None]).reshape(n, 3 * k, 3).transpose(0, 2, 1)   # (N, 3, 3K)
        jjt = jac @ jac.transpose(0, 2, 1) + lam2[:, None, None] * np.eye(3)
        y = np.linalg.solve(jjt, err[..., None])[..., 0]
        dtheta = (jac.transpose(0, 2, 1) @ y[..., None])[..., 0].reshape(n, k, 3) * scale[None, :, None]
        for j in range(k):
            angle = np.linalg.norm(dtheta[:, j], axis=-1)
            rot = kinematics.axis_angle_to_mat3(np.where((angle > 1e-15)[:, None], dtheta[:, j],
                                                         np.array([1.0, 0.0, 0.0])), angle)
            pivot = p[:, j].copy()
            p[:, j:] = pivot[:, None] + np.einsum("nij,nkj->nki", rot, p[:, j:] - pivot[:, None])
            tip = pivot + np.einsum("nij,nj->ni", rot, tip - pivot)
            total[:, j:] = rot[:, None] @ total[:, j:]
    deltas = np.empty_like(total)
    deltas[:, 0] = total[:, 0]
    for j in range(1, k):
        deltas[:, j] = np.linalg.inv(total[:, j - 1]) @ total[:, j]
    return deltas, tip
