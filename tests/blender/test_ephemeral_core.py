# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 2 of the ephemeral rig (docs/design/ephemeral-rig.md) against Blender on the generated Rigify rig:
FK in numpy equals the depsgraph, and the pure gesture written as dense keys moves the FK hand's tail
where it says inside the window and nowhere outside it.

The chain is built here from Blender data the way phase 3's ``anim/spaces.prefetch_chain`` will:
``base(f)`` = world matrix of the root's parent space by frame stepping, ``links`` from the rest
matrices (``hand_fk`` hangs from ``MCH-hand_fk``, a rigid helper under ``forearm_fk``)."""

import importlib

import bpy
import numpy as np
import pytest
from mathutils import Matrix, Quaternion

CHAIN = ("upper_arm_fk.R", "forearm_fk.R", "hand_fk.R")
FRAMES = list(range(1, 25))


def _np(m):
    return np.array(m, dtype=np.float64)


def _core(addon, name):
    return importlib.import_module(f"{addon.__name__}.core.{name}")


def _rest_links(rig, bones):
    """links[i] = inv(rest[i-1]) · rest[i] in armature space (links[0] unused)."""
    rest = [_np(rig.data.bones[b].matrix_local) for b in bones]
    links = np.broadcast_to(np.eye(4), (len(bones), 4, 4)).copy()
    for i in range(1, len(bones)):
        links[i] = np.linalg.inv(rest[i - 1]) @ rest[i]
    return links


def _sample(rig, bones, frames, ephemeral):
    """Chain sampled by frame stepping + the depsgraph matrices of each bone and the hand tail."""
    scene = bpy.context.scene
    n, k = len(frames), len(bones)
    base = np.empty((n, 4, 4))
    loc = np.empty((n, k, 3))
    scale = np.empty((n, k, 3))
    rot = [np.empty((n, 4)) for _ in bones]
    world_bl = np.empty((n, k, 4, 4))
    tail = np.empty((n, 3))
    mw = _np(rig.matrix_world)
    for fi, f in enumerate(frames):
        scene.frame_set(f)
        pbs = [rig.pose.bones[b] for b in bones]
        base[fi] = mw @ _np(pbs[0].matrix) @ np.linalg.inv(_np(pbs[0].matrix_basis))
        for i, pb in enumerate(pbs):
            loc[fi, i] = pb.location
            scale[fi, i] = pb.scale
            rot[i][fi] = pb.rotation_quaternion
            world_bl[fi, i] = mw @ _np(pb.matrix)
        tail[fi] = np.array(rig.matrix_world @ pbs[-1].tail)
    lengths = np.array([rig.data.bones[b].length for b in bones])
    chain = ephemeral.Chain(base, _rest_links(rig, bones), lengths, loc, rot, ["QUATERNION"] * k, scale)
    return chain, world_bl, tail


def _pose_forearm_and_hand(rig):
    """Give the (unanimated) forearm and hand a bent, non-trivial pose that frame_set does not reset."""
    rig.pose.bones["forearm_fk.R"].rotation_quaternion = Quaternion((1.0, 0.0, 0.0), 0.9)
    rig.pose.bones["hand_fk.R"].rotation_quaternion = Quaternion((0.3, 0.2, 1.0), 0.5)


def test_numpy_fk_matches_the_depsgraph(public_rig, addon):
    """FK in numpy (rest links, base by frame stepping) = Blender's pose matrices, < 1e-5 m."""
    ephemeral = _core(addon, "ephemeral")
    kin = _core(addon, "kinematics")
    _pose_forearm_and_hand(public_rig)
    chain, world_bl, tail_bl = _sample(public_rig, CHAIN, FRAMES, ephemeral)
    world = chain.world()
    assert np.abs(world[..., :3, 3] - world_bl[..., :3, 3]).max() < 1e-5
    assert np.abs(world[..., :3, :3] - world_bl[..., :3, :3]).max() < 1e-5
    assert np.abs(kin.tails(world[:, -1], chain.lengths[-1]) - tail_bl).max() < 1e-5


@pytest.mark.parametrize("radius_past,radius_future", [(6, 6), (3, 9), (0, 8)])
def test_dense_ephemeral_edit_moves_the_hand_tail_only_inside_the_window(public_rig, addon, radius_past,
                                                                          radius_future):
    ephemeral = _core(addon, "ephemeral")
    falloff = _core(addon, "falloff")
    dense = _core(addon, "dense")
    action_io = importlib.import_module(f"{addon.__name__}.anim.action_io")
    rig = public_rig
    _pose_forearm_and_hand(rig)
    # key the pose so it is part of the Action (otherwise frame_set keeps the live pose everywhere anyway)
    for bone in CHAIN[1:]:
        rig.keyframe_insert(f'pose.bones["{bone}"].rotation_quaternion', frame=1)
    f0 = 12
    frames = list(range(f0 - radius_past, f0 + radius_future + 1))
    chain, _world, tail_before_win = _sample(rig, CHAIN, frames, ephemeral)
    _c, _w, tail_before_all = _sample(rig, CHAIN, FRAMES, ephemeral)
    weights = falloff.weight_signed(np.asarray(frames, dtype=np.float64) - f0, radius_past, radius_future)
    delta = np.array([0.05, -0.04, 0.06])
    result = ephemeral.sculpt(chain, weights, delta)
    assert result.reached.all()

    for i, bone in enumerate(CHAIN):
        pb = rig.pose.bones[bone]
        for axis in range(4):
            fc, _created = action_io.ensure_channel(rig, pb, "rotation_quaternion", axis)
            model = action_io.read_channel(fc)
            out = dense.write_dense(model, frames[0], result.rot[i][:, axis], default=pb.rotation_quaternion[axis])
            action_io.write_channel(fc, out)
    action_io.tag(rig)

    _c, _w, tail_after_all = _sample(rig, CHAIN, FRAMES, ephemeral)
    inside = np.isin(FRAMES, frames)
    target = dict(zip(frames, result.target))
    for fi, f in enumerate(FRAMES):
        if inside[fi]:
            assert np.linalg.norm(tail_after_all[fi] - target[f]) < 1e-4, f      # float32 keys
        else:
            assert np.linalg.norm(tail_after_all[fi] - tail_before_all[fi]) < 1e-5, f
    i0 = frames.index(f0)
    assert np.linalg.norm(tail_after_all[FRAMES.index(f0)] - (tail_before_win[i0] + delta)) < 1e-4
