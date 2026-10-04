# SPDX-License-Identifier: GPL-3.0-or-later
"""The ephemeral-rig gesture as a pure function (ADR 0011, docs/design/ephemeral-rig.md).

Input: one FK chain (root → tip) sampled at every integer frame of the time window, the falloff
weight of each frame and the world drag Δ. Output: new local rotations of every bone at every frame,
so the tip (tail of the last bone) follows ``tip(f) + w(f)·Δ``; frames with weight 0 come back
bit-identical. No rig is created anywhere: the "rig" is this math, and it is gone after the call.

Solve per chain length (deterministic, docs "Solve"):
- 1 bone (``Ponta``): minimal rotation pointing the bone at the target.
- 2 bones: analytic two-bone IK; the tip is the tail of the second bone.
- 3 bones (``Membro``: upper, lower, hand): two-bone IK on the first two so the hand's head goes where
  the hand must be; orientation ``WORLD`` keeps the hand's world orientation (the tail lands exactly),
  ``LOCAL`` keeps its local rotation (the hand turns with the forearm).
- more bones: damped least squares with fixed iterations (``core/solve``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import kinematics as kin
from . import solve

WORLD, LOCAL = "WORLD", "LOCAL"
REACH_TOL = 1e-6


@dataclass
class Chain:
    """An FK chain sampled at N frames. Shapes: base (N, 4, 4); links (K, 4, 4) or (N, K, 4, 4);
    lengths (K,); loc/scale (N, K, 3); rot: K arrays, (N, 4) quaternion or (N, 3) Euler per ``modes``;
    lock_rotation (K, 3) bools (quaternion: locks the x/y/z components, like Blender's 3D locks)."""

    base: np.ndarray
    links: np.ndarray
    lengths: np.ndarray
    loc: np.ndarray
    rot: list
    modes: list
    scale: np.ndarray
    lock_rotation: np.ndarray = field(default=None)

    @property
    def bone_count(self) -> int:
        return len(self.modes)

    @property
    def frame_count(self) -> int:
        return len(self.base)

    def rotation_matrices(self) -> np.ndarray:
        return np.stack([kin.rotation_to_mat3(r, m) for r, m in zip(self.rot, self.modes)], axis=1)

    def world(self, rot3=None) -> np.ndarray:
        rot3 = self.rotation_matrices() if rot3 is None else rot3
        return kin.forward(self.base, self.links, kin.basis_matrices(self.loc, rot3, self.scale))

    def tip(self, rot3=None) -> np.ndarray:
        """World position (N, 3) of the dragged point: the tail of the last bone."""
        world = self.world(rot3)
        return kin.tails(world[:, -1], self.lengths[-1])


@dataclass
class Result:
    rot: list               # K arrays, same layout as Chain.rot
    tip: np.ndarray         # (N, 3) tip after the edit (FK of the new rotations)
    target: np.ndarray      # (N, 3) wanted tip
    reached: np.ndarray     # (N,) bool: |tip − target| < REACH_TOL


def check(chain: Chain) -> str:
    """Refusal reason for a chain the solve cannot handle ('' when fine)."""
    for mode in chain.modes:
        if mode == "AXIS_ANGLE":
            return "rotação AXIS_ANGLE não suportada (use quaternion ou Euler)"
        if mode != "QUATERNION" and mode not in kin.EULER_ORDERS:
            return f"modo de rotação {mode} não suportado"
    if chain.bone_count < 1:
        return "cadeia vazia"
    return ""


def _frames_rot(chain, world, i):
    """Rotation of bone i's parent space (before its basis), old configuration (N, 3, 3)."""
    links = np.asarray(chain.links, dtype=np.float64)
    if i == 0:
        frame = chain.base
    elif links.ndim == 3:
        frame = world[:, i - 1] @ links[i]
    else:
        frame = world[:, i - 1] @ links[:, i]
    return frame[:, :3, :3]


def _own_deltas(chain, world, target, orientation, bend_axis):
    """Own world turn of each bone (N, K, 3, 3) in the old configuration."""
    n, k = chain.frame_count, chain.bone_count
    heads = world[:, :, :3, 3]
    tails = kin.tails(world, chain.lengths)
    eye = np.broadcast_to(np.eye(3), (n, 3, 3))
    deltas = np.broadcast_to(np.eye(3), (n, k, 3, 3)).copy()
    if k == 1:
        deltas[:, 0] = kin.aim(heads[:, 0], tails[:, 0], target)
    elif k in (2, 3):
        if bend_axis is None:
            bend_axis = world[:, 1, :3, 0]           # the middle bone's X axis (elbow/knee hinge)
        if k == 2:
            c, t = tails[:, 1], target
        else:
            c = heads[:, 2]
            t = target - (tails[:, 2] - heads[:, 2])  # where the hand's head must go (hand keeps its world turn)
        d1, d2, _tip = kin.two_bone_ik(heads[:, 0], heads[:, 1], c, t, bend_axis)
        deltas[:, 0] = d1
        deltas[:, 1] = d2
        if k == 3:
            deltas[:, 2] = np.linalg.inv(d1 @ d2) if orientation == WORLD else eye
    else:
        deltas, _tip = solve.dls_chain(heads, tails[:, -1], target)
    return deltas


def _apply_locks(new, old, mode, locks):
    if locks is None or not np.any(locks):
        return new
    out = new.copy()
    if mode == "QUATERNION":
        locked = [1 + a for a in range(3) if locks[a]]
        free = [1 + a for a in range(3) if not locks[a]]
        out[:, locked] = old[:, locked]          # exact: the locked components never change
        s_locked = np.sum(out[:, locked] ** 2, axis=1)
        s_free = np.sum(out[:, free] ** 2, axis=1)
        over = s_locked + s_free > 1.0
        fac = np.sqrt(np.clip(1.0 - s_locked, 0.0, None) / np.maximum(s_free, 1e-300))
        out[:, free] = np.where(over[:, None], out[:, free] * fac[:, None], out[:, free])
        rest = np.clip(1.0 - np.sum(out[:, 1:] ** 2, axis=1), 0.0, None)
        out[:, 0] = np.sign(np.where(new[:, 0] == 0.0, 1.0, new[:, 0])) * np.sqrt(rest)
        return out
    for a in range(3):
        if locks[a]:
            out[:, a] = old[:, a]
    return out


def sculpt(chain: Chain, weights, delta, orientation=WORLD, bend_axis=None) -> Result:
    """Run the ephemeral gesture. ``weights`` (N,) in [0, 1]; ``delta`` (3,) world drag."""
    reason = check(chain)
    if reason:
        raise ValueError(reason)
    weights = np.asarray(weights, dtype=np.float64)
    delta = np.asarray(delta, dtype=np.float64)
    rot3 = chain.rotation_matrices()
    world = chain.world(rot3)
    tip0 = kin.tails(world[:, -1], chain.lengths[-1])
    target = tip0 + weights[:, None] * delta[None, :]
    active = weights > 0.0
    deltas = _own_deltas(chain, world, target, orientation, bend_axis)

    new_rot = []
    new_rot3 = rot3.copy()
    for i, (old, mode) in enumerate(zip(chain.rot, chain.modes)):
        old = np.asarray(old, dtype=np.float64)
        frame = _frames_rot(chain, world, i)
        r = kin.local_rotation_update(frame, deltas[:, i], rot3[:, i])
        if mode == "QUATERNION":
            q = kin.mat3_to_quat(r)
            q = np.where((np.sum(q * old, axis=1) < 0.0)[:, None], -q, q)   # same hemisphere as before
            vals = q
        else:
            vals = kin.mat3_to_euler(r, mode, compatible=old)
        locks = None if chain.lock_rotation is None else np.asarray(chain.lock_rotation)[i]
        vals = _apply_locks(vals, old, mode, locks)
        vals = np.where(active[:, None], vals, old)                    # weight 0 ⇒ bit-identical
        new_rot.append(vals)
        new_rot3[:, i] = kin.rotation_to_mat3(vals, mode)
    tip = kin.tails(chain.world(new_rot3)[:, -1], chain.lengths[-1])
    tip = np.where(active[:, None], tip, tip0)
    reached = np.linalg.norm(tip - target, axis=1) < REACH_TOL
    return Result(rot=new_rot, tip=tip, target=target, reached=reached)
