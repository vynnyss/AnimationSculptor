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


# ------------------------------------------------------------------------------- Corpo: DLS + pins
def _leg(seed=11):
    """A 3-bone FK leg (thigh, shin, foot) pointing down, sampled over N frames."""
    rng = np.random.default_rng(seed)
    links = np.broadcast_to(np.eye(4), (3, 4, 4)).copy()
    lengths = np.array([0.45, 0.42, 0.12])
    links[1, 1, 3], links[2, 1, 3] = lengths[0], lengths[1]
    rot = []
    for i in range(3):
        ang = np.array([np.pi if i == 0 else 0.3 if i == 1 else -0.4, 0.0, 0.0])
        ang = ang + np.linspace(0, 1, N)[:, None] * rng.normal(size=3) * 0.2
        rot.append(kin.mat3_to_quat(kin.euler_to_mat3(ang, "XYZ")))
    base = np.broadcast_to(np.eye(4), (N, 4, 4))
    return ephemeral.Chain(base, links, lengths, np.zeros((N, 3, 3)), rot, ["QUATERNION"] * 3, np.ones((N, 3, 3)))


def _pin(side):
    rel = np.broadcast_to(np.eye(4), (N, 4, 4)).copy()
    rel[:, 0, 3] = 0.1 * side          # hip joint beside the chain root's head
    return ephemeral.Pin(parent=0, rel=rel, limb=_leg(11 if side > 0 else 12))


def _feet(chain, rot, pins, pin_rot=None):
    out = []
    world = ephemeral.Chain(chain.base, chain.links, chain.lengths, chain.loc, rot, chain.modes, chain.scale).world()
    for k, pin in enumerate(pins):
        limb = pin.limb if pin_rot is None else ephemeral.Chain(pin.limb.base, pin.limb.links, pin.limb.lengths,
                                                                pin.limb.loc, pin_rot[k], pin.limb.modes, pin.limb.scale)
        w = ephemeral.Chain(world[:, 0] @ pin.rel, limb.links, limb.lengths, limb.loc, limb.rot, limb.modes,
                            limb.scale).world()
        out.append(w[:, 2])
    return out


def test_dls_world_keeps_the_last_bone_world_turn_and_reaches():
    chain = _chain(5)
    res = ephemeral.sculpt(chain, _weights(), DELTA, orientation=ephemeral.WORLD, solver=ephemeral.DLS)
    assert np.abs(res.tip - res.target).max() < 1e-6
    after = ephemeral.Chain(chain.base, chain.links, chain.lengths, chain.loc, res.rot, chain.modes,
                            chain.scale).world()[:, -1, :3, :3]
    assert np.abs(after - chain.world()[:, -1, :3, :3]).max() < 1e-9


def test_pinned_feet_stay_put_while_the_body_leans():
    chain = _chain(3, modes=["QUATERNION"] * 3)
    pins = [_pin(+1), _pin(-1)]
    before = _feet(chain, chain.rot, pins)
    res = ephemeral.sculpt(chain, _weights(), np.array([0.0, 0.08, -0.05]), solver=ephemeral.DLS, pins=pins)
    assert np.abs(res.tip - res.target).max() < 1e-6
    after = _feet(chain, res.rot, pins, res.pins)
    moved = _feet(chain, res.rot, pins)                       # feet if the legs were not re-solved
    for b, a, m in zip(before, after, moved):
        assert np.abs(a[:, :3, 3] - b[:, :3, 3]).max() < 1e-9          # foot head pinned
        assert np.abs(a[:, :3, :3] - b[:, :3, :3]).max() < 1e-9        # foot keeps its world turn
        assert np.abs(m[:, :3, 3] - b[:, :3, 3]).max() > 1e-3          # (the body really moved them)


def test_pins_are_bit_identical_on_zero_weight_frames():
    chain = _chain(3, modes=["QUATERNION"] * 3)
    pins = [_pin(+1)]
    w = _weights()
    res = ephemeral.sculpt(chain, w, DELTA, solver=ephemeral.DLS, pins=pins)
    out = w == 0.0
    for new, old in zip(res.pins[0], pins[0].limb.rot):
        assert np.array_equal(new[out], np.asarray(old)[out])


def test_overstretched_pin_is_reported():
    chain = _chain(3, modes=["QUATERNION"] * 3)
    pin = _pin(+1)
    ok = ephemeral.sculpt(chain, _weights(), DELTA, solver=ephemeral.DLS, pins=[pin])
    assert ok.pins_reached.all()
    pin.rel[:, 0, 3] = 1.2                # hip joint far from the chain root: turning the root drags it away
    far = ephemeral.sculpt(chain, _weights(), np.array([0.8, 0.0, 0.0]), solver=ephemeral.DLS, pins=[pin])
    assert not far.pins_reached[F0] and far.pins_reached[_weights() == 0.0].all()
