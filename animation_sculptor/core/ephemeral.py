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
- more bones (or ``solver=DLS``, the ``Corpo`` scope): damped least squares with fixed iterations
  (``core/solve``); with ``WORLD`` the last bone keeps its world orientation and the others carry it.

Pins (``Corpo``): FK limbs hanging from a chain bone whose end must stay put in world (feet). After the
chain moves, each pinned limb is re-solved with the two-bone IK so its end (and, for three bones, the
last bone's world orientation) is where it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import kinematics as kin
from . import solve

WORLD, LOCAL = "WORLD", "LOCAL"
AUTO, DLS = "AUTO", "DLS"
REACH_TOL = 1e-6


@dataclass
class Chain:
    """An FK chain sampled at N frames. Shapes: base (N, 4, 4); links (K, 4, 4) or (N, K, 4, 4);
    lengths (K,); loc/scale (N, K, 3); rot: K arrays, (N, 4) quaternion or (N, 3) Euler per ``modes``;
    lock_rotation (K, 3) bools (quaternion: locks the x/y/z components, like Blender's 3D locks);
    point: the dragged point in the last bone's local space, (3,) or per frame (N, 3); None = its tail
    (0, length, 0). A point grabbed on the body surface is rigid with its bone."""

    base: np.ndarray
    links: np.ndarray
    lengths: np.ndarray
    loc: np.ndarray
    rot: list
    modes: list
    scale: np.ndarray
    lock_rotation: np.ndarray = field(default=None)
    point: np.ndarray = field(default=None)

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

    def local_point(self) -> np.ndarray:
        """(N, 3) dragged point in the last bone's local space."""
        if self.point is None:
            p = np.array([0.0, float(self.lengths[-1]), 0.0])
        else:
            p = np.asarray(self.point, dtype=np.float64)
        return np.broadcast_to(p, (self.frame_count, 3))

    def point_world(self, world) -> np.ndarray:
        """(N, 3) world position of the dragged point for the chain's world matrices (N, K, 4, 4)."""
        last = world[:, -1]
        return np.einsum("nij,nj->ni", last[:, :3, :3], self.local_point()) + last[:, :3, 3]

    def tip(self, rot3=None) -> np.ndarray:
        """World position (N, 3) of the dragged point (the tail of the last bone by default)."""
        return self.point_world(self.world(rot3))


@dataclass
class Pin:
    """An FK limb (2 or 3 bones) hanging from chain bone ``parent`` whose end stays put in world.
    ``rel`` (N, 4, 4): from that chain bone's world matrix to the limb root's parent space;
    ``limb.base`` is ignored (rebuilt from the chain before and after the edit)."""

    parent: int
    rel: np.ndarray
    limb: Chain


@dataclass
class Result:
    rot: list               # K arrays, same layout as Chain.rot
    tip: np.ndarray         # (N, 3) tip after the edit (FK of the new rotations)
    target: np.ndarray      # (N, 3) wanted tip
    reached: np.ndarray     # (N,) bool: |tip − target| < REACH_TOL
    pins: list = field(default_factory=list)    # per Pin: its bones' new rotations (Chain.rot layout)
    pins_reached: np.ndarray = None             # (N,) bool: every pinned end stayed put (False: leg overstretched)


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


def _dls_deltas(heads, tip, target, orientation):
    """Own deltas from the damped least squares; ``WORLD`` keeps the last bone's world orientation."""
    n, k = heads.shape[:2]
    if orientation != WORLD or k < 2:
        deltas, _tip = solve.dls_chain(heads, tip, target)
        return deltas
    d, _tip = solve.dls_chain(heads[:, :k - 1], heads[:, k - 1], target - (tip - heads[:, -1]))
    deltas = np.broadcast_to(np.eye(3), (n, k, 3, 3)).copy()
    deltas[:, :k - 1] = d
    total = np.broadcast_to(np.eye(3), (n, 3, 3)).copy()
    for j in range(k - 1):
        total = total @ d[:, j]
    deltas[:, k - 1] = np.linalg.inv(total)
    return deltas


def _own_deltas(chain, world, target, orientation, bend_axis, solver=AUTO):
    """Own world turn of each bone (N, K, 3, 3) in the old configuration."""
    n, k = chain.frame_count, chain.bone_count
    heads = world[:, :, :3, 3]
    tip = chain.point_world(world)
    eye = np.broadcast_to(np.eye(3), (n, 3, 3))
    deltas = np.broadcast_to(np.eye(3), (n, k, 3, 3)).copy()
    if solver == DLS and k > 1:
        return _dls_deltas(heads, tip, target, orientation)
    if k == 1:
        deltas[:, 0] = kin.aim(heads[:, 0], tip, target)
    elif k in (2, 3):
        if bend_axis is None:
            bend_axis = world[:, 1, :3, 0]           # the middle bone's X axis (elbow/knee hinge)
        if k == 2:
            c, t = tip, target
        else:
            c = heads[:, 2]
            t = target - (tip - heads[:, 2])  # where the hand's head must go (hand keeps its world turn)
        d1, d2, _tip = kin.two_bone_ik(heads[:, 0], heads[:, 1], c, t, bend_axis)
        deltas[:, 0] = d1
        deltas[:, 1] = d2
        if k == 3:
            deltas[:, 2] = np.linalg.inv(d1 @ d2) if orientation == WORLD else eye
    else:
        deltas = _dls_deltas(heads, tip, target, orientation)
    return deltas


def _native(r, old, mode, locks, active):
    """Rotation matrices → the bone's rotation values, continuous with ``old``; weight 0 ⇒ ``old``."""
    if mode == "QUATERNION":
        q = kin.mat3_to_quat(r)
        vals = np.where((np.sum(q * old, axis=1) < 0.0)[:, None], -q, q)   # same hemisphere as before
    else:
        vals = kin.mat3_to_euler(r, mode, compatible=old)
    vals = _apply_locks(vals, old, mode, locks)
    return np.where(active[:, None], vals, old)


def _solve_pin(pin, world_old, world_new, active):
    """Re-solve one pinned limb after the chain moved: same end position (and last-bone world turn)."""
    limb = pin.limb
    k = limb.bone_count
    if k not in (2, 3):
        raise ValueError("pinned limbs have 2 or 3 bones")
    old_limb = replace(limb, base=world_old[:, pin.parent] @ pin.rel)
    new_limb = replace(limb, base=world_new[:, pin.parent] @ pin.rel)
    rot3 = limb.rotation_matrices()
    wo = old_limb.world(rot3)
    wn = new_limb.world(rot3)
    heads_n = wn[:, :, :3, 3]
    if k == 2:
        c, t = kin.tails(wn[:, 1], limb.lengths[1]), kin.tails(wo[:, 1], limb.lengths[1])
    else:
        c, t = heads_n[:, 2], wo[:, 2, :3, 3]
    d1, d2, tip = kin.two_bone_ik(heads_n[:, 0], heads_n[:, 1], c, t, wn[:, 1, :3, 0])
    reached = (np.linalg.norm(tip - t, axis=1) < REACH_TOL) | ~active
    new_rot3 = rot3.copy()
    new_rot3[:, 0] = kin.local_rotation_update(_frames_rot(new_limb, wn, 0), d1, rot3[:, 0])
    new_rot3[:, 1] = kin.local_rotation_update(_frames_rot(new_limb, wn, 1), d2, rot3[:, 1])
    if k == 3:      # the last bone (foot) keeps its old world orientation
        w2 = new_limb.world(new_rot3)
        frame = _frames_rot(new_limb, w2, 2)
        new_rot3[:, 2] = kin.orthonormalize(np.linalg.inv(frame) @ kin.orthonormalize(wo[:, 2, :3, :3]))
    locks = limb.lock_rotation
    return [_native(new_rot3[:, i], np.asarray(limb.rot[i], dtype=np.float64), limb.modes[i],
                    None if locks is None else np.asarray(locks)[i], active) for i in range(k)], reached


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


def sculpt(chain: Chain, weights, delta, orientation=WORLD, bend_axis=None, solver=AUTO, pins=()) -> Result:
    """Run the ephemeral gesture. ``weights`` (N,) in [0, 1]; ``delta`` (3,) world drag; ``solver`` AUTO
    (by chain length) or DLS; ``pins``: FK limbs whose end stays put (``Pin``)."""
    reason = check(chain) or next((check(p.limb) for p in pins if check(p.limb)), "")
    if reason:
        raise ValueError(reason)
    weights = np.asarray(weights, dtype=np.float64)
    delta = np.asarray(delta, dtype=np.float64)
    rot3 = chain.rotation_matrices()
    world = chain.world(rot3)
    tip0 = chain.point_world(world)
    target = tip0 + weights[:, None] * delta[None, :]
    active = weights > 0.0
    deltas = _own_deltas(chain, world, target, orientation, bend_axis, solver)

    new_rot = []
    new_rot3 = rot3.copy()
    for i, (old, mode) in enumerate(zip(chain.rot, chain.modes)):
        old = np.asarray(old, dtype=np.float64)
        frame = _frames_rot(chain, world, i)
        r = kin.local_rotation_update(frame, deltas[:, i], rot3[:, i])
        locks = None if chain.lock_rotation is None else np.asarray(chain.lock_rotation)[i]
        vals = _native(r, old, mode, locks, active)                    # weight 0 ⇒ bit-identical
        new_rot.append(vals)
        new_rot3[:, i] = kin.rotation_to_mat3(vals, mode)
    world_new = chain.world(new_rot3)
    tip = chain.point_world(world_new)
    tip = np.where(active[:, None], tip, tip0)
    reached = np.linalg.norm(tip - target, axis=1) < REACH_TOL
    solved = [_solve_pin(p, world, world_new, active) for p in pins]
    pins_reached = np.ones(len(weights), dtype=bool)
    for _rot, ok in solved:
        pins_reached &= ok
    return Result(rot=new_rot, tip=tip, target=target, reached=reached, pins=[r for r, _ok in solved],
                  pins_reached=pins_reached)
