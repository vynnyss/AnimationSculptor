# SPDX-License-Identifier: GPL-3.0-or-later
"""core.bezier.evaluate == FCurve.evaluate (ADR 0008: the pure core must reproduce Blender exactly)."""

import importlib
import random

import bpy
import numpy as np
import pytest
from bpy_extras import anim_utils

HANDLE_TYPES = ("FREE", "ALIGNED", "VECTOR", "AUTO", "AUTO_CLAMPED")


@pytest.fixture
def fcurve():
    ob = bpy.data.objects.new("asc_parity", None)
    bpy.context.scene.collection.objects.link(ob)
    action = bpy.data.actions.new("asc_parity")
    slot = action.slots.new(id_type='OBJECT', name=ob.name)
    adt = ob.animation_data_create()
    adt.action, adt.action_slot = action, slot
    cb = anim_utils.action_ensure_channelbag_for_slot(action, slot)
    fc = cb.fcurves.new("location", index=0)
    yield fc
    bpy.data.objects.remove(ob)
    bpy.data.actions.remove(action)


def _randomize(fc, rng):
    fc.keyframe_points.clear()
    for frame in sorted(rng.sample(range(-5, 60), rng.randint(1, 7))):
        fc.keyframe_points.insert(frame, rng.uniform(-2, 2), options={'FAST'})
    for kp in fc.keyframe_points:
        kp.interpolation = rng.choice(("BEZIER", "BEZIER", "BEZIER", "LINEAR", "CONSTANT"))
        kp.handle_left_type = rng.choice(HANDLE_TYPES)
        kp.handle_right_type = rng.choice(HANDLE_TYPES)
    fc.extrapolation = rng.choice(("CONSTANT", "LINEAR"))
    fc.update()
    for kp in fc.keyframe_points:   # long FREE handles: overlapping/looping segments
        if kp.handle_left_type == "FREE":
            kp.handle_left = (kp.co[0] - rng.uniform(0, 20), kp.co[1] + rng.uniform(-3, 3))
        if kp.handle_right_type == "FREE":
            kp.handle_right = (kp.co[0] + rng.uniform(0, 20), kp.co[1] + rng.uniform(-3, 3))


def test_parity_random_curves(fcurve, addon):
    bezier = importlib.import_module(addon.__name__ + ".core.bezier")
    action_io = importlib.import_module(addon.__name__ + ".anim.action_io")
    rng = random.Random(7)
    times = np.linspace(-10.0, 70.0, 801)
    worst = 0.0
    for _ in range(300):
        _randomize(fcurve, rng)
        ours = bezier.evaluate(action_io.read_channel(fcurve), times)
        theirs = np.array([fcurve.evaluate(t) for t in times])
        worst = max(worst, float(np.abs(ours - theirs).max()))
    assert worst <= 1e-6, worst


def test_parity_on_rig_curves(public_rig, addon):
    bezier = importlib.import_module(addon.__name__ + ".core.bezier")
    action_io = importlib.import_module(addon.__name__ + ".anim.action_io")
    times = np.arange(-2.0, 30.0, 0.25)
    for fc in action_io.channelbag(public_rig).fcurves:
        ours = bezier.evaluate(action_io.read_channel(fc), times)
        theirs = np.array([fc.evaluate(t) for t in times])
        assert np.abs(ours - theirs).max() <= 1e-6, fc.data_path
