# SPDX-License-Identifier: GPL-3.0-or-later
"""core.ephemeral: the ephemeral-rig gesture as a pure function (docs/design/ephemeral-rig.md, phase 2)."""

import numpy as np
import pytest

from animation_sculptor.core import ephemeral, falloff
from animation_sculptor.core import kinematics as kin

N, F0 = 61, 30
LENGTHS = (0.3, 0.26, 0.08, 0.12, 0.1)
MODES = ("QUATERNION", "XYZ", "ZXY", "QUATERNION", "YXZ")
DELTA = np.array([0.05, -0.03, 0.04])


def _chain(k, modes=None, seed=3, locks=None):
    rng = np.random.default_rng(seed)
    modes = list(modes or MODES[:k])
    base = np.broadcast_to(np.eye(4), (N, 4, 4)).copy()
    base[:, :3, 3] = (0.1, -0.2, 1.4)
    base[:, :3, :3] = kin.euler_to_mat3(np.linspace(0, 0.4, N)[:, None] * np.array([0.3, 0.1, -0.2]), "XYZ")
    links = np.broadcast_to(np.eye(4), (k, 4, 4)).copy()
    for i in range(1, k):
        links[i, 1, 3] = LENGTHS[i - 1]
    rot = []
    for m in modes:
        ang = np.linspace(0, 1, N)[:, None] * rng.normal(size=3) * 0.8 + rng.normal(size=3) * 0.4
        r3 = kin.euler_to_mat3(ang, "XYZ")
        rot.append(kin.mat3_to_quat(r3) if m == "QUATERNION" else kin.mat3_to_euler(r3, m))
    return ephemeral.Chain(base, links, np.array(LENGTHS[:k]), np.zeros((N, k, 3)), rot, modes,
                           np.ones((N, k, 3)), locks)


def _weights(past=10, future=20):
    return falloff.weight_signed(np.arange(N) - float(F0), past, future)


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_zero_weight_frames_are_bit_identical(k):
    chain = _chain(k)
    w = _weights()
    res = ephemeral.sculpt(chain, w, DELTA)
    out = w == 0.0
    assert out.any() and (~out).any()
    for new, old in zip(res.rot, chain.rot):
        assert np.array_equal(new[out], old[out])


@pytest.mark.parametrize("k", [2, 3])
def test_two_bone_and_limb_reach_the_target_exactly(k):
    chain = _chain(k)
    res = ephemeral.sculpt(chain, _weights(), DELTA)
    assert np.abs(res.tip - res.target).max() < 1e-9
    assert res.reached.all()
    assert np.abs(res.target[F0] - (chain.tip()[F0] + DELTA)).max() < 1e-12


def test_dls_chain_reaches_the_target():
    res = ephemeral.sculpt(_chain(5), _weights(), DELTA)
    assert np.abs(res.tip - res.target).max() < 1e-6


def test_world_orientation_keeps_the_hand_turned_the_same_in_world():
    chain = _chain(3)
    res = ephemeral.sculpt(chain, _weights(), DELTA, orientation=ephemeral.WORLD)
    before = chain.world()[:, 2, :3, :3]
    after = ephemeral.Chain(chain.base, chain.links, chain.lengths, chain.loc, res.rot, chain.modes,
                            chain.scale).world()[:, 2, :3, :3]
    assert np.abs(after - before).max() < 1e-9


def test_local_orientation_keeps_the_hand_local_rotation():
    chain = _chain(3)
    res = ephemeral.sculpt(chain, _weights(), DELTA, orientation=ephemeral.LOCAL)
    r_old = kin.rotation_to_mat3(chain.rot[2], chain.modes[2])
    r_new = kin.rotation_to_mat3(res.rot[2], chain.modes[2])
    assert np.abs(r_new - r_old).max() < 1e-9


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_zero_delta_is_identity(k):
    chain = _chain(k)
    res = ephemeral.sculpt(chain, _weights(), np.zeros(3))
    for new, old in zip(res.rot, chain.rot):
        assert np.abs(new - old).max() < 1e-9
    assert np.abs(res.tip - chain.tip()).max() < 1e-9


@pytest.mark.parametrize("k", [2, 3, 5])
def test_rotation_outputs_are_continuous(k):
    chain = _chain(k)
    res = ephemeral.sculpt(chain, _weights(), DELTA * 3)
    for new, old, mode in zip(res.rot, chain.rot, chain.modes):
        if mode == "QUATERNION":
            assert np.abs(np.linalg.norm(new, axis=1) - 1.0).max() < 1e-12
            assert (np.sum(new * old, axis=1) >= 0.0).all()             # same hemisphere as the input
            assert (np.sum(new[1:] * new[:-1], axis=1) > 0.0).all()     # no flips frame to frame
        else:
            assert (np.abs(new - old) <= np.pi + 1e-9).all()
            assert (np.abs(np.diff(new, axis=0)) < np.pi).all()


def test_result_tip_is_the_fk_of_the_returned_rotations():
    chain = _chain(3)
    res = ephemeral.sculpt(chain, _weights(), DELTA)
    again = ephemeral.Chain(chain.base, chain.links, chain.lengths, chain.loc, res.rot, chain.modes, chain.scale)
    assert np.abs(again.tip() - res.tip).max() < 1e-12


@pytest.mark.parametrize("k", [1, 3, 5])
def test_deterministic(k):
    a = ephemeral.sculpt(_chain(k), _weights(), DELTA)
    b = ephemeral.sculpt(_chain(k), _weights(), DELTA)
    for x, y in zip(a.rot, b.rot):
        assert np.array_equal(x, y)
    assert np.array_equal(a.tip, b.tip)


def test_axis_angle_is_refused():
    chain = _chain(2, modes=["QUATERNION", "XYZ"])
    chain.modes[1] = "AXIS_ANGLE"
    assert "AXIS_ANGLE" in ephemeral.check(chain)
    with pytest.raises(ValueError):
        ephemeral.sculpt(chain, _weights(), DELTA)


def test_locked_euler_axis_keeps_its_value():
    locks = np.zeros((3, 3), dtype=bool)
    locks[1, 2] = True                          # forearm (XYZ euler): Z locked
    chain = _chain(3, locks=locks)
    res = ephemeral.sculpt(chain, _weights(), DELTA)
    assert np.array_equal(res.rot[1][:, 2], chain.rot[1][:, 2])


def test_locked_quaternion_component_keeps_its_value():
    locks = np.zeros((3, 3), dtype=bool)
    locks[0, 0] = True                          # upper arm quaternion: x component locked
    chain = _chain(3, locks=locks)
    res = ephemeral.sculpt(chain, _weights(), DELTA)
    assert np.array_equal(res.rot[0][:, 1], chain.rot[0][:, 1])
    assert np.abs(np.linalg.norm(res.rot[0], axis=1) - 1.0).max() < 1e-12


def test_aim_points_a_single_bone_at_the_target():
    chain = _chain(1)
    res = ephemeral.sculpt(chain, _weights(), DELTA)
    head = chain.world()[:, 0, :3, 3]
    d_new = kin.normalize(res.tip - head)
    d_want = kin.normalize(res.target - head)
    active = _weights() > 0
    assert np.abs(d_new[active] - d_want[active]).max() < 1e-9


def test_out_of_reach_stretches_without_nan():
    chain = _chain(2)
    res = ephemeral.sculpt(chain, _weights(), np.array([3.0, 0.0, 0.0]))
    assert np.isfinite(res.tip).all()
    head = chain.world()[:, 0, :3, 3]
    assert np.abs(np.linalg.norm(res.tip - head, axis=1)[F0] - (LENGTHS[0] + LENGTHS[1])) < 1e-9
