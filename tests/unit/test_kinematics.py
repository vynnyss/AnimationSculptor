# SPDX-License-Identifier: GPL-3.0-or-later
"""core.kinematics and core.solve: quaternions, Euler, chain FK, two-bone IK, aim, damped least squares."""

import numpy as np
import pytest

from animation_sculptor.core import kinematics as kin
from animation_sculptor.core import solve

ORDERS = kin.EULER_ORDERS


def _rand_quats(rng, n):
    return kin.quat_normalize(rng.normal(size=(n, 4)))


def _rand_rot(rng, n):
    return kin.quat_to_mat3(_rand_quats(rng, n))


def _is_rotation(m, tol=1e-9):
    m = np.asarray(m)
    eye = np.broadcast_to(np.eye(3), m.shape)
    return (np.allclose(m @ np.swapaxes(m, -1, -2), eye, atol=tol)
            and np.allclose(np.linalg.det(m), 1.0, atol=tol))


def _rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


_AX = {"X": _rx, "Y": _ry, "Z": _rz}


def _translate(v):
    m = np.eye(4)
    m[:3, 3] = v
    return m


def _mat4(r3, t=(0, 0, 0)):
    m = np.eye(4)
    m[:3, :3] = r3
    m[:3, 3] = t
    return m


# ------------------------------------------------------------------------------------------- quaternions
def test_quat_mat_round_trip_random():
    rng = np.random.default_rng(1)
    q = _rand_quats(rng, 500)
    q = np.where((q[:, 0] < 0)[:, None], -q, q)
    m = kin.quat_to_mat3(q)
    assert _is_rotation(m, 1e-12)
    back = kin.mat3_to_quat(m)
    assert np.allclose(back, q, atol=1e-12)
    assert np.allclose(kin.quat_to_mat3(back), m, atol=1e-12)


def test_quat_mul_matches_matrix_product():
    rng = np.random.default_rng(2)
    a, b = _rand_quats(rng, 200), _rand_quats(rng, 200)
    ab = kin.quat_mul(a, b)
    assert np.allclose(kin.quat_to_mat3(ab), kin.quat_to_mat3(a) @ kin.quat_to_mat3(b), atol=1e-12)
    assert np.allclose(kin.quat_mul(a, kin.quat_conj(a)), [1, 0, 0, 0], atol=1e-12)


def test_mat3_to_quat_w_nonnegative_random():
    rng = np.random.default_rng(3)
    q = kin.mat3_to_quat(_rand_rot(rng, 1000))
    assert np.all(q[:, 0] >= 0.0)
    assert np.allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-12)


@pytest.mark.parametrize("axis", [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, -2, 3), (-1, -1, -1)])
@pytest.mark.parametrize("delta", [0.0, 1e-7, -1e-7])
def test_mat3_to_quat_handles_half_turns(axis, delta):
    m = kin.axis_angle_to_mat3(np.array(axis, float), np.pi + delta)
    q = kin.mat3_to_quat(m)
    assert np.all(np.isfinite(q))
    assert q[0] >= 0.0
    assert np.linalg.norm(q) == pytest.approx(1.0, abs=1e-12)
    assert np.allclose(kin.quat_to_mat3(q), m, atol=1e-7)


def test_quat_continuity_removes_sign_flips():
    rng = np.random.default_rng(4)
    angles = np.linspace(0.0, 5.0, 60)
    q = kin.quat_from_axis_angle(np.tile([0.3, 0.5, 0.8], (60, 1)), angles)
    flips = rng.random(60) < 0.5
    noisy = np.where(flips[:, None], -q, q)
    out = kin.quat_continuity(noisy)
    assert np.all(np.sum(out[1:] * out[:-1], axis=1) >= 0.0)
    assert np.allclose(np.abs(np.sum(out * q, axis=1)), 1.0, atol=1e-12)
    out2 = kin.quat_continuity(-q[:3], previous=q[0])
    assert np.dot(out2[0], q[0]) >= 0.0


# ------------------------------------------------------------------------------------------------ euler
@pytest.mark.parametrize("order", ORDERS)
def test_euler_to_mat3_matches_axis_products(order):
    rng = np.random.default_rng(5)
    e = rng.uniform(-np.pi, np.pi, size=(20, 3))
    m = kin.euler_to_mat3(e, order)
    for k in range(len(e)):
        ref = np.eye(3)
        for ax in order:                      # first axis applies first: R = R_c . R_b . R_a
            ref = _AX[ax](e[k, "XYZ".index(ax)]) @ ref
        assert np.allclose(m[k], ref, atol=1e-12)
    assert np.allclose(kin.euler_to_mat3(e[0], "XYZ"), _rz(e[0, 2]) @ _ry(e[0, 1]) @ _rx(e[0, 0]), atol=1e-12)


def test_euler_rejects_unknown_order():
    with pytest.raises(ValueError):
        kin.euler_to_mat3(np.zeros(3), "XXY")
    with pytest.raises(ValueError):
        kin.mat3_to_euler(np.eye(3), "ABC")


@pytest.mark.parametrize("order", ORDERS)
def test_mat3_to_euler_round_trip(order):
    rng = np.random.default_rng(6)
    e = rng.uniform(-np.pi, np.pi, size=(200, 3))
    mid = "XYZ".index(order[1])
    e[:, mid] = rng.uniform(-1.5, 1.5, size=200)       # middle angle away from gimbal lock
    m = kin.euler_to_mat3(e, order)
    assert np.allclose(kin.euler_to_mat3(kin.mat3_to_euler(m, order), order), m, atol=1e-10)
    comp = kin.mat3_to_euler(m, order, compatible=e)
    assert np.allclose(kin.euler_to_mat3(comp, order), m, atol=1e-10)
    assert np.all(np.abs(comp - e) <= np.pi + 1e-9)


@pytest.mark.parametrize("order", ORDERS)
@pytest.mark.parametrize("sign", [1.0, -1.0])
@pytest.mark.parametrize("off", [0.0, 1e-9, 1e-6, 1e-4])
def test_mat3_to_euler_near_gimbal_lock(order, sign, off):
    rng = np.random.default_rng(7)
    mid = "XYZ".index(order[1])
    e = rng.uniform(-np.pi, np.pi, size=(10, 3))
    e[:, mid] = sign * (np.pi / 2 - off)
    m = kin.euler_to_mat3(e, order)
    out = kin.mat3_to_euler(m, order)
    assert np.all(np.isfinite(out))
    assert np.allclose(kin.euler_to_mat3(out, order), m, atol=1e-6)
    comp = kin.mat3_to_euler(m, order, compatible=e)
    assert np.allclose(kin.euler_to_mat3(comp, order), m, atol=1e-6)


@pytest.mark.parametrize("order", ORDERS)
def test_compatible_picks_solution_within_pi_of_reference(order):
    base = np.array([0.4, -0.3, 0.7])
    m = kin.euler_to_mat3(base, order)
    for shift in (2 * np.pi, -2 * np.pi, 4 * np.pi):
        ref = base + shift
        out = kin.mat3_to_euler(m, order, compatible=ref)
        assert np.all(np.abs(out - ref) <= np.pi + 1e-12)
        assert np.allclose(out, ref, atol=1e-9)
        assert np.allclose(kin.euler_to_mat3(out, order), m, atol=1e-12)
    alt = kin.mat3_to_euler(m, order, compatible=np.array([np.pi, np.pi, np.pi]) + base)
    assert np.allclose(kin.euler_to_mat3(alt, order), m, atol=1e-12)


@pytest.mark.parametrize("order", ["XYZ", "ZYX", "YXZ"])
def test_euler_continuity_crossing_pi_has_no_jumps(order):
    t = np.linspace(0.0, 1.0, 80)
    e = np.stack((2.5 + 1.5 * t, 0.3 * np.sin(3 * t), -2.0 - 2.0 * t), axis=1)    # crosses +pi and -pi
    m = kin.euler_to_mat3(e, order)
    out = kin.euler_continuity(m, order, e[0] - 0.01)
    assert np.allclose(kin.euler_to_mat3(out, order), m, atol=1e-10)
    assert np.all(np.abs(np.diff(out, axis=0)) < np.pi)
    plain = np.stack([kin.mat3_to_euler(x, order) for x in m])


# ---------------------------------------------------------------------------------------- rotation_between
def test_rotation_between_maps_a_to_b():
    rng = np.random.default_rng(8)
    a, b = rng.normal(size=(100, 3)), rng.normal(size=(100, 3))
    r = kin.rotation_between(a, b)
    assert _is_rotation(r)
    assert np.allclose(np.einsum("nij,nj->ni", r, kin.normalize(a)), kin.normalize(b), atol=1e-12)


def test_rotation_between_parallel_and_antiparallel():
    v = np.array([[0.0, 1.0, 0.0], [1.0, 2.0, 3.0], [-3.0, 0.2, 0.0], [1.0, 0.0, 0.0]])
    same = kin.rotation_between(v, 2.5 * v)
    assert np.allclose(same, np.eye(3), atol=1e-12)
    anti = kin.rotation_between(v, -v)
    assert _is_rotation(anti)
    assert np.allclose(np.einsum("nij,nj->ni", anti, kin.normalize(v)), -kin.normalize(v), atol=1e-12)
    ang = np.arccos(np.clip((np.trace(anti, axis1=1, axis2=2) - 1) / 2, -1, 1))
    assert np.allclose(ang, np.pi, atol=1e-7)
    assert _is_rotation(kin.rotation_between(v, -v + 1e-12))


# --------------------------------------------------------------------------------------------- forward
def test_forward_identity_equals_base():
    rng = np.random.default_rng(9)
    n, k = 5, 4
    base = np.stack([_mat4(_rand_rot(rng, 1)[0], rng.normal(size=3)) for _ in range(n)])
    out = kin.forward(base, np.broadcast_to(np.eye(4), (k, 4, 4)), np.broadcast_to(np.eye(4), (n, k, 4, 4)))
    for i in range(k):
        assert np.allclose(out[:, i], base, atol=1e-14)


def test_forward_hand_computed_three_bones():
    base = _translate((1.0, 0.0, 0.0))[None]
    links = np.stack([np.eye(4), _translate((0, 2, 0)), _translate((0, 1, 0))])
    basis = np.stack([_mat4(_rz(np.pi / 2)), np.eye(4), _mat4(_rx(np.pi / 2))])[None]
    w = kin.forward(base, links, basis)
    assert w.shape == (1, 3, 4, 4)
    assert np.allclose(w[0, 0, :3, 3], (1, 0, 0), atol=1e-12)
    assert np.allclose(w[0, 1, :3, 3], (-1, 0, 0), atol=1e-12)
    assert np.allclose(w[0, 2, :3, 3], (-2, 0, 0), atol=1e-12)
    assert np.allclose(w[0, 2, :3, :3], _rz(np.pi / 2) @ _rx(np.pi / 2), atol=1e-12)
    assert np.allclose(w[0, 2, :3, 1], (0, 0, 1), atol=1e-12)
    per_frame = np.broadcast_to(links, (1, 3, 4, 4)).copy()
    per_frame[:, 0] = _translate((9, 9, 9))                     # links[:, 0] is ignored
    assert np.allclose(kin.forward(base, per_frame, basis), w, atol=1e-14)


def test_tails_head_plus_y_times_length():
    rng = np.random.default_rng(10)
    world = np.stack([_mat4(_rand_rot(rng, 1)[0], rng.normal(size=3)) for _ in range(6)]).reshape(2, 3, 4, 4)
    lengths = np.array([0.5, 1.5, 2.0])
    t = kin.tails(world, lengths)
    for i in range(2):
        for j in range(3):
            assert np.allclose(t[i, j], world[i, j, :3, 3] + world[i, j, :3, :3] @ [0, lengths[j], 0], atol=1e-14)


# ------------------------------------------------------------------------------------ local_rotation_update
@pytest.mark.parametrize("uniform_scale", [1.0, 0.37, 2.5])
def test_local_rotation_update_turns_world_orientation_exactly(uniform_scale):
    rng = np.random.default_rng(11)
    n = 50
    frame_rot = _rand_rot(rng, n)
    f = uniform_scale * frame_rot
    rl = _rand_rot(rng, n)
    delta = _rand_rot(rng, n)
    r_new = kin.local_rotation_update(f, delta, rl)
    assert _is_rotation(r_new, 1e-12)
    assert np.allclose(f @ r_new, delta @ f @ rl, atol=1e-12)
    assert np.allclose(frame_rot @ r_new, delta @ frame_rot @ rl, atol=1e-12)


def test_local_rotation_update_identity_delta_keeps_rotation():
    rng = np.random.default_rng(12)
    f, rl = _rand_rot(rng, 10), _rand_rot(rng, 10)
    out = kin.local_rotation_update(f, np.broadcast_to(np.eye(3), (10, 3, 3)), rl)
    assert np.allclose(out, rl, atol=1e-12)


def test_local_rotation_update_through_forward():
    """Apply the update and re-run forward: the bone's world orientation is turned by exactly delta."""
    rng = np.random.default_rng(22)
    n = 20
    base = np.stack([_mat4(_rand_rot(rng, 1)[0] * 1.7, rng.normal(size=3)) for _ in range(n)])
    rl = _rand_rot(rng, n)
    link = _translate((0, 1, 0))
    basis0 = np.stack([_mat4(_rand_rot(rng, 1)[0]) for _ in range(n)])
    basis1 = np.stack([_mat4(r) for r in rl])
    links = np.stack([np.eye(4), link])
    world = kin.forward(base, links, np.stack([basis0, basis1], axis=1))
    frame = (world[:, 0] @ link)[:, :3, :3]
    delta = _rand_rot(rng, n)
    r_new = kin.local_rotation_update(frame, delta, rl)
    world2 = kin.forward(base, links, np.stack([basis0, np.stack([_mat4(r) for r in r_new])], axis=1))
    assert np.allclose(world2[:, 1, :3, :3], delta @ world[:, 1, :3, :3], atol=1e-12)


def test_orthonormalize_returns_nearest_rotation():
    rng = np.random.default_rng(13)
    r = _rand_rot(rng, 20)
    out = kin.orthonormalize(r + 1e-6 * rng.normal(size=r.shape))
    assert _is_rotation(out, 1e-12)
    assert np.allclose(out, r, atol=1e-5)
    assert np.allclose(kin.orthonormalize(3.0 * r), r, atol=1e-12)
    reflected = r @ np.diag([1.0, 1.0, -1.0])
    assert np.allclose(np.linalg.det(kin.orthonormalize(reflected)), 1.0)


# ------------------------------------------------------------------------------------------------- IK
def _ik_case(rng, n, mode="reach"):
    """Random bent limbs and targets. mode: reach | far | near."""
    a = rng.normal(size=(n, 3))
    b = a + rng.normal(size=(n, 3))
    u1 = b - a
    u2 = rng.normal(size=(n, 3))
    u2 -= u1 * (np.sum(u2 * u1, axis=1) / np.sum(u1 * u1, axis=1))[:, None] * 0.3
    c = b + u2
    l1 = np.linalg.norm(b - a, axis=1)
    l2 = np.linalg.norm(c - b, axis=1)
    dirs = kin.normalize(rng.normal(size=(n, 3)))
    if mode == "reach":
        d = np.abs(l1 - l2) + (l1 + l2 - np.abs(l1 - l2)) * rng.uniform(0.05, 0.95, size=n)
    elif mode == "far":
        d = (l1 + l2) * rng.uniform(1.1, 3.0, size=n)
    else:
        d = np.abs(l1 - l2) * rng.uniform(0.0, 0.8, size=n)
    return a, b, c, a + dirs * d[:, None], l1, l2


def test_two_bone_ik_reaches_target_and_preserves_lengths():
    rng = np.random.default_rng(14)
    a, b, c, t, l1, l2 = _ik_case(rng, 300)
    d1, d2, tip = kin.two_bone_ik(a, b, c, t)
    assert np.allclose(tip, t, atol=1e-9)
    assert _is_rotation(d1) and _is_rotation(d2)
    b_new = a + np.einsum("nij,nj->ni", d1, b - a)
    c_new = b_new + np.einsum("nij,nj->ni", d1 @ d2, c - b)
    assert np.allclose(c_new, tip, atol=1e-9)
    assert np.allclose(np.linalg.norm(b_new - a, axis=1), l1, atol=1e-9)
    assert np.allclose(np.linalg.norm(c_new - b_new, axis=1), l2, atol=1e-9)


def test_two_bone_ik_out_of_reach_stretches_towards_target():
    rng = np.random.default_rng(15)
    a, b, c, t, l1, l2 = _ik_case(rng, 200, "far")
    _d1, _d2, tip = kin.two_bone_ik(a, b, c, t)
    assert np.allclose(np.linalg.norm(tip - a, axis=1), l1 + l2, atol=1e-9)
    assert np.allclose(kin.normalize(tip - a), kin.normalize(t - a), atol=1e-9)


def test_two_bone_ik_too_close_folds_to_length_difference():
    rng = np.random.default_rng(16)
    a, b, c, t, l1, l2 = _ik_case(rng, 200, "near")
    _d1, _d2, tip = kin.two_bone_ik(a, b, c, t)
    assert np.all(np.isfinite(tip))
    assert np.allclose(np.linalg.norm(tip - a, axis=1), np.abs(l1 - l2), atol=1e-9)


def test_two_bone_ik_preserves_bend_plane():
    rng = np.random.default_rng(17)
    a, b, c, t, _l1, _l2 = _ik_case(rng, 200)
    d1, _d2, tip = kin.two_bone_ik(a, b, c, t)
    n_old = np.cross(b - a, c - b)
    b_new = a + np.einsum("nij,nj->ni", d1, b - a)
    n_new = np.cross(b_new - a, tip - b_new)
    expected = np.einsum("nij,nj->ni", d1, n_old)
    assert np.allclose(kin.normalize(n_new), kin.normalize(expected), atol=1e-7)


def test_two_bone_ik_straight_limb_uses_bend_axis():
    rng = np.random.default_rng(18)
    n = 50
    a = rng.normal(size=(n, 3))
    dirs = kin.normalize(rng.normal(size=(n, 3)))
    b = a + dirs * 1.0
    c = b + dirs * 0.8                                  # exactly straight
    t = a + kin.normalize(rng.normal(size=(n, 3))) * rng.uniform(0.4, 1.7, size=(n, 1))
    for axis in (None, rng.normal(size=(n, 3)), np.tile([0.0, 0.0, 1.0], (n, 1))):
        d1, d2, tip = kin.two_bone_ik(a, b, c, t, axis)
        assert np.all(np.isfinite(tip)) and np.all(np.isfinite(d1)) and np.all(np.isfinite(d2))
        assert np.allclose(tip, t, atol=1e-9)
    # the second bone folds about the bend axis projected off the limb direction
    axis = np.tile([0.0, 0.0, 1.0], (n, 1))
    _d1, d2, _tip = kin.two_bone_ik(a, b, c, t, axis)
    hinge = kin.normalize(axis - dirs * np.sum(axis * dirs, axis=1, keepdims=True))
    d2_axis = np.stack([d2[:, 2, 1] - d2[:, 1, 2], d2[:, 0, 2] - d2[:, 2, 0], d2[:, 1, 0] - d2[:, 0, 1]], axis=1)
    sel = (np.linalg.norm(np.cross(dirs, axis), axis=1) > 1e-3) & (np.linalg.norm(d2_axis, axis=1) > 1e-6)
    assert sel.sum() > 10
    assert np.allclose(np.abs(np.sum(kin.normalize(d2_axis[sel]) * hinge[sel], axis=1)), 1.0, atol=1e-7)


def test_two_bone_ik_deterministic():
    rng = np.random.default_rng(19)
    a, b, c, t, *_ = _ik_case(rng, 100)
    ax = np.tile([1.0, 0, 0], (100, 1))
    r1 = kin.two_bone_ik(a, b, c, t, ax)
    r2 = kin.two_bone_ik(a, b, c, t, ax)
    for x, y in zip(r1, r2):
        assert np.array_equal(x, y)


def test_two_bone_ik_target_equal_to_current_tip_is_identity():
    rng = np.random.default_rng(20)
    a, b, c, _t, *_ = _ik_case(rng, 50)
    d1, d2, tip = kin.two_bone_ik(a, b, c, c)
    assert np.allclose(tip, c, atol=1e-9)
    assert np.allclose(d1, np.eye(3), atol=1e-6) and np.allclose(d2, np.eye(3), atol=1e-6)


# ------------------------------------------------------------------------------------------------- aim
def test_aim_points_bone_at_target():
    rng = np.random.default_rng(21)
    head = rng.normal(size=(100, 3))
    tail = head + rng.normal(size=(100, 3))
    target = rng.normal(size=(100, 3)) * 3.0
    r = kin.aim(head, tail, target)
    assert _is_rotation(r)
    new_dir = np.einsum("nij,nj->ni", r, tail - head)
    assert np.allclose(kin.normalize(new_dir), kin.normalize(target - head), atol=1e-12)
    assert np.allclose(np.linalg.norm(new_dir, axis=1), np.linalg.norm(tail - head, axis=1), atol=1e-12)


def test_aim_target_at_head_is_identity():
    head = np.array([[1.0, 2.0, 3.0]])
    r = kin.aim(head, head + [0, 1, 0], head)
    assert np.allclose(r, np.eye(3), atol=1e-12)


# ------------------------------------------------------------------------------------------------ solve
def _dls_case(rng, k, bend=0.6):
    lengths = rng.uniform(0.6, 1.4, size=k)
    pts = [np.zeros(3)]
    r = np.eye(3)
    for ln in lengths:
        r = r @ kin.euler_to_mat3(rng.uniform(-bend, bend, size=3), "XYZ")
        pts.append(pts[-1] + r @ np.array([0.0, ln, 0.0]))
    pts = np.array(pts)
    return pts[:-1], pts[-1]


@pytest.mark.parametrize("k", [4, 5, 6])
def test_dls_chain_reaches_reachable_target(k):
    rng = np.random.default_rng(30 + k)
    n = 6
    cases = [_dls_case(rng, k) for _ in range(n)]
    joints = np.stack([c[0] for c in cases])
    tip = np.stack([c[1] for c in cases])
    target = tip + 0.25 * kin.normalize(rng.normal(size=(n, 3)))      # a drag, well inside the reach
    deltas, tip_new = solve.dls_chain(joints, tip, target)
    assert np.allclose(tip_new, target, atol=1e-6)
    assert _is_rotation(deltas, 1e-9)
    for i in range(n):                    # rebuilding the tip from the own deltas gives tip_new
        g = np.eye(3)
        p = joints[i, 0].copy()
        for j in range(k):
            g = g @ deltas[i, j]
            nxt = joints[i, j + 1] if j + 1 < k else tip[i]
            p = p + g @ (nxt - joints[i, j])
        assert np.allclose(p, tip_new[i], atol=1e-9)


def test_dls_chain_deterministic():
    rng = np.random.default_rng(40)
    cases = [_dls_case(rng, 5) for _ in range(4)]
    joints = np.stack([c[0] for c in cases])
    tip = np.stack([c[1] for c in cases])
    target = tip + 0.3 * kin.normalize(rng.normal(size=(4, 3)))
    r1 = solve.dls_chain(joints, tip, target)
    r2 = solve.dls_chain(joints, tip, target)
    assert np.array_equal(r1[0], r2[0]) and np.array_equal(r1[1], r2[1])


def test_dls_chain_unreachable_target_is_finite_and_improves():
    rng = np.random.default_rng(41)
    cases = [_dls_case(rng, 5) for _ in range(4)]
    joints = np.stack([c[0] for c in cases])
    tip = np.stack([c[1] for c in cases])
    target = joints[:, 0] + 100.0 * kin.normalize(rng.normal(size=(4, 3)))
    deltas, tip_new = solve.dls_chain(joints, tip, target)
    assert np.all(np.isfinite(deltas)) and np.all(np.isfinite(tip_new))
    assert np.all(np.linalg.norm(tip_new - target, axis=1) < np.linalg.norm(tip - target, axis=1))
    assert _is_rotation(deltas, 1e-9)


def test_dls_chain_target_at_tip_is_noop():
    rng = np.random.default_rng(42)
    joints, tip = _dls_case(rng, 4)
    deltas, tip_new = solve.dls_chain(joints[None], tip[None], tip[None])
    assert np.allclose(tip_new, tip, atol=1e-12)
    assert np.allclose(deltas, np.eye(3), atol=1e-9)
