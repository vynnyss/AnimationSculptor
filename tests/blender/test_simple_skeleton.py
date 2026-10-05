# SPDX-License-Identifier: GPL-3.0-or-later
"""The simple skeleton (ADR 0014): built by scripts/make_basic_rig.py, adapted by the generic adapter."""

import importlib

import bpy
import numpy as np
import pytest


def test_simple_rig_shape_and_locks(simple_rig, addon):
    rig = simple_rig
    bones = rig.data.bones
    assert len(bones) == 53
    assert bones["root"].parent is None and not bones["root"].use_deform
    for name in ("thumb", "index", "middle", "ring", "pinky"):
        for side in ("L", "R"):
            assert f"{name}.03.{side}" in bones
    adapter = importlib.import_module(addon.__name__ + ".rig").get_adapter(rig)
    assert adapter.id == "generic"
    info = {b.name: adapter.classify(rig, b.name) for b in bones}
    assert info["hips"].translates and info["hips"].rotates
    assert info["root"].translates and not info["root"].rotates
    assert all(not i.translates and i.rotates for n, i in info.items() if n not in ("root", "hips"))


def test_simple_rig_chains(simple_rig, addon):
    rig = simple_rig
    adapter = importlib.import_module(addon.__name__ + ".rig").get_adapter(rig)
    assert adapter.ephemeral_chain(rig, "hand.L", "LIMB")[0] == ["upper_arm.L", "forearm.L", "hand.L"]
    assert adapter.ephemeral_chain(rig, "index.03.R", "LIMB")[0] == ["index.01.R", "index.02.R", "index.03.R"]
    assert adapter.ephemeral_chain(rig, "foot.R", "LIMB")[0] == ["thigh.R", "shin.R", "foot.R"]
    body, _ = adapter.ephemeral_chain(rig, "head", "BODY")
    assert body == ["hips", "spine", "spine.001", "chest", "neck", "head"]
    pins, _ = adapter.ephemeral_pins(rig, body)
    assert sorted(limb[0] for _b, limb in pins) == ["thigh.L", "thigh.R"]
