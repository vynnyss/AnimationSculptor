# SPDX-License-Identifier: GPL-3.0-or-later
"""anim.action_io (Slotted Actions, foreach I/O) and anim.snapshot."""

import importlib

import pytest


@pytest.fixture
def aio(addon):
    return importlib.import_module(addon.__name__ + ".anim.action_io")


@pytest.fixture
def snapshot_mod(addon):
    return importlib.import_module(addon.__name__ + ".anim.snapshot")


def _dump(fc):
    return [(tuple(k.co), tuple(k.handle_left), tuple(k.handle_right), k.handle_left_type,
             k.handle_right_type, k.interpolation) for k in fc.keyframe_points]


def test_channelbag_and_bone_fcurves(public_rig, aio):
    cb = aio.channelbag(public_rig)
    assert cb is not None and len(cb.fcurves) > 0
    pb = public_rig.pose.bones["hand_ik.L"]
    paths = {(fc.data_path, fc.array_index) for fc in aio.bone_fcurves(public_rig, pb)}
    assert (pb.path_from_id("location"), 0) in paths
    assert all(p.startswith(pb.path_from_id()) for p, _ in paths)


def test_round_trip_is_lossless(public_rig, aio):
    for fc in aio.channelbag(public_rig).fcurves:
        before = _dump(fc)
        aio.write_channel(fc, aio.read_channel(fc), update=False)
        assert _dump(fc) == before, fc.data_path
        aio.write_channel(fc, aio.read_channel(fc), update=True)
        assert _dump(fc) == before, fc.data_path    # auto handles were already consistent


def test_write_changes_key_count(public_rig, aio):
    fc = aio.channelbag(public_rig).fcurves[0]
    model = aio.read_channel(fc)
    shorter = model.copy()
    shorter.co, shorter.hl, shorter.hr = model.co[:2].copy(), model.hl[:2].copy(), model.hr[:2].copy()
    shorter.hl_type, shorter.hr_type, shorter.interp = model.hl_type[:2], model.hr_type[:2], model.interp[:2]
    aio.write_channel(fc, shorter)
    assert len(fc.keyframe_points) == 2
    aio.write_channel(fc, model, update=False)
    assert len(fc.keyframe_points) == model.key_count
    assert aio.read_channel(fc).same_as(model)


def test_aligned_handles_written_collinear_survive_update(public_rig, aio):
    """Investigation item: fcurve.update() keeps ALIGNED handles we wrote collinear."""
    fc = aio.channelbag(public_rig).fcurves.find(public_rig.pose.bones["hand_ik.L"].path_from_id("location"), index=2)
    model = aio.read_channel(fc)
    k = 1
    x, y = model.co[k]
    model.hl_type[k] = model.hr_type[k] = "ALIGNED"
    model.hl[k] = (x - 3.0, y - 0.2)
    model.hr[k] = (x + 1.5, y + 0.1)        # same direction, different length
    aio.write_channel(fc, model, update=True)
    kp = fc.keyframe_points[k]
    assert tuple(kp.handle_left) == pytest.approx((x - 3.0, y - 0.2), abs=1e-5)
    assert tuple(kp.handle_right) == pytest.approx((x + 1.5, y + 0.1), abs=1e-5)


def test_ensure_channel_and_key(public_rig, aio):
    pb = public_rig.pose.bones["hand_ik.L"]
    cb = aio.channelbag(public_rig)
    cb.fcurves.remove(cb.fcurves.find(pb.path_from_id("location"), index=1))
    fc, created = aio.ensure_channel(public_rig, pb, "location", 1)
    assert created and fc.group is not None and fc.group.name == pb.name
    idx, inserted = aio.ensure_key(fc, 5, 0.25)
    assert inserted and fc.keyframe_points[idx].co[1] == pytest.approx(0.25)
    fc2, created2 = aio.ensure_channel(public_rig, pb, "location", 1)
    assert fc2 == fc and not created2
    idx2, inserted2 = aio.ensure_key(fc, 5, 9.0)
    assert idx2 == idx and not inserted2


def test_snapshot_restores_bit_for_bit(public_rig, aio, snapshot_mod):
    pb = public_rig.pose.bones["hand_ik.L"]
    cb = aio.channelbag(public_rig)
    path = pb.path_from_id("location")
    cb.fcurves.remove(cb.fcurves.find(path, index=1))
    before = {(fc.data_path, fc.array_index): _dump(fc) for fc in cb.fcurves}
    snap = snapshot_mod.Snapshot(public_rig)
    for i in range(3):
        snap.capture(path, i)
    fc0 = cb.fcurves.find(path, index=0)
    aio.ensure_key(fc0, 5, 0.0)                        # inserted key
    fc0.keyframe_points[0].co[1] += 1.0                # edited key
    aio.ensure_channel(public_rig, pb, "location", 1)  # created curve
    snap.restore()
    after = {(fc.data_path, fc.array_index): _dump(fc) for fc in cb.fcurves}
    assert after == before


def test_refusals(public_rig, aio):
    pb = public_rig.pose.bones["hand_ik.L"]
    assert aio.refusal(public_rig, pb) == ""
    fc = aio.channelbag(public_rig).fcurves.find(pb.path_from_id("location"), index=0)
    mod = fc.modifiers.new("NOISE")
    assert "modificador" in aio.refusal(public_rig, pb)
    fc.modifiers.remove(mod)
    public_rig.animation_data.action_influence = 0.5
    assert aio.refusal(public_rig, pb)
