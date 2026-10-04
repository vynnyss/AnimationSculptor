# SPDX-License-Identifier: GPL-3.0-or-later
"""anim.spaces: P(f) prefetch over frames and detection of constant spaces."""

import importlib
import time

import bpy
import numpy as np
import pytest
from mathutils import Matrix


@pytest.fixture
def spaces(addon):
    return importlib.import_module(addon.__name__ + ".anim.spaces")


def _heads(rig, bone, frames):
    scene = bpy.context.scene
    out = []
    for f in frames:
        scene.frame_set(f)
        pb = rig.pose.bones[bone]
        out.append((tuple(rig.matrix_world @ pb.head), tuple(pb.location)))
    return out


@pytest.mark.parametrize("bone", ["hand_ik.L", "foot_ik.R", "torso"])
def test_prefetch_maps_location_to_head_on_every_frame(public_rig, spaces, bone):
    scene = bpy.context.scene
    scene.frame_set(5)
    frames = list(range(1, 25))
    mats, constant = spaces.prefetch(public_rig, public_rig.pose.bones[bone], frames, scene)
    assert mats.shape == (24, 4, 4)
    assert scene.frame_current == 5       # the scene returns to its frame
    for m, (head, loc) in zip(mats, _heads(public_rig, bone, frames)):
        assert (Matrix(m.tolist()) @ __import__("mathutils").Vector(loc) - __import__("mathutils").Vector(head)).length < 1e-5


def test_ik_control_space_is_not_constant_when_torso_moves(public_rig, spaces):
    # hand_ik.L follows the root/torso through its MCH parent (Armature constraint): never constant
    assert not spaces.is_space_constant(public_rig, public_rig.pose.bones["hand_ik.L"])


def test_constant_space_detected_and_shortcut(public_rig, spaces):
    pb = public_rig.pose.bones["root"]          # parentless, armature object not animated
    assert spaces.is_space_constant(public_rig, pb)
    scene = bpy.context.scene
    mats, constant = spaces.prefetch(public_rig, pb, [1, 12, 24], scene)
    assert constant and np.allclose(mats[0], mats[2])


def test_object_animation_breaks_constancy(public_rig, spaces):
    public_rig.keyframe_insert("location", frame=1)
    assert not spaces.is_space_constant(public_rig, public_rig.pose.bones["root"])


def test_prefetch_cost_on_character(attack_rig, spaces, record_property):
    """Profiling (non-blocking): P(f) per frame on the maintainer's Rigify character."""
    scene = bpy.context.scene
    frames = list(range(scene.frame_start, scene.frame_end + 1))
    t0 = time.perf_counter()
    spaces.prefetch(attack_rig, attack_rig.pose.bones["hand_ik.R"], frames, scene)
    per_frame = (time.perf_counter() - t0) * 1000.0 / len(frames)
    record_property("p_f_ms_per_frame", per_frame)
    print(f"\n[profile] P(f) prefetch hand_ik.R: {per_frame:.2f} ms/frame over {len(frames)} frames")
    assert per_frame < 50.0
