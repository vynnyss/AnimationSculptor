# SPDX-License-Identifier: GPL-3.0-or-later
"""Grabbing the body on a real character: the grabbed skin spot (a wrist vertex blending forearm and hand)
follows ``its own path + w(f)·Δ`` on every frame of the window, not only at the grabbed frame (review
finding of the UX reform). A spot right at a joint can be unreachable (it moves on a sphere around the
shoulder): then the correction must never make it worse. Local asset only (the Vale's skin)."""

import importlib
import sys
from pathlib import Path

import bpy
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deform_check  # noqa: E402

F0, RP, RF = 16, 5, 5
CHAIN = ["upper_arm_fk.L", "forearm_fk.L"]


def _blended_vertex(mesh, first, second):
    """A vertex weighted to both deform groups (≥ 0.15 each), and a face using it."""
    groups = {vg.name: vg.index for vg in mesh.vertex_groups}
    a, b = groups.get(first), groups.get(second)
    if a is None or b is None:
        return None, None
    for v in mesh.data.vertices:
        w = {g.group: g.weight for g in v.groups}
        if w.get(a, 0.0) >= 0.15 and w.get(b, 0.0) >= 0.15:
            for poly in mesh.data.polygons:
                if v.index in poly.vertices:
                    return v.index, tuple(poly.vertices)
    return None, None


def test_grabbed_skin_follows_its_path_on_every_frame(attack_rig, addon):
    rig = attack_rig
    ee = importlib.import_module(addon.__name__ + ".interaction.ephemeral_edit")
    falloff = importlib.import_module(addon.__name__ + ".core.falloff")
    mesh = deform_check.deformed_mesh(rig)
    vertex, face = _blended_vertex(mesh, "DEF-forearm.L.001", "DEF-hand.L")      # wrist skin
    if vertex is None:
        pytest.skip("no blended wrist vertex on this character")
    frames = list(range(F0 - RP, F0 + RF + 1))
    before = {f: deform_check.points(mesh, f)[vertex] for f in range(F0 - RP - 3, F0 + RF + 4)}
    bpy.context.scene.frame_set(F0)
    delta = np.array([0.0, -0.04, 0.05])
    edit = ee.ChainEdit(rig, CHAIN, F0, RP, RF, point_world=before[F0], point_bone="forearm_fk.L",
                        point_deform="DEF-forearm.L", point_skin=(mesh.name, face))
    assert edit.editable, edit.reason
    edit.apply(delta)
    edit.finish()
    weights = falloff.weight_signed(np.asarray(frames, dtype=np.float64) - F0, RP, RF, "SMOOTH")
    for f, w in zip(frames, weights):
        moved = deform_check.points(mesh, f)[vertex] - before[f]
        assert np.linalg.norm(moved - w * delta) < 3e-3, (f, w, moved)
    for f in list(range(F0 - RP - 3, F0 - RP - 1)) + list(range(F0 + RF + 2, F0 + RF + 4)):
        assert np.linalg.norm(deform_check.points(mesh, f)[vertex] - before[f]) < 1e-5, f


def test_unreachable_spot_at_the_elbow_never_gets_worse(attack_rig, addon):
    rig = attack_rig
    ee = importlib.import_module(addon.__name__ + ".interaction.ephemeral_edit")
    mesh = deform_check.deformed_mesh(rig)
    vertex, face = _blended_vertex(mesh, "DEF-upper_arm.L.001", "DEF-forearm.L")
    if vertex is None:
        pytest.skip("no blended elbow vertex on this character")
    frames = list(range(F0 - RP, F0 + RF + 1))
    before = {f: deform_check.points(mesh, f)[vertex] for f in frames}
    bpy.context.scene.frame_set(F0)
    delta = np.array([0.0, -0.04, 0.05])
    edit = ee.ChainEdit(rig, CHAIN, F0, RP, RF, point_world=before[F0], point_bone="forearm_fk.L",
                        point_deform="DEF-forearm.L", point_skin=(mesh.name, face))
    edit.apply(delta)
    w = edit.weights[1:-1]
    first = [np.linalg.norm(deform_check.points(mesh, f)[vertex] - before[f] - wi * delta) for f, wi in zip(frames, w)]
    edit.finish()
    final = [np.linalg.norm(deform_check.points(mesh, f)[vertex] - before[f] - wi * delta) for f, wi in zip(frames, w)]
    assert all(b <= a + 1e-4 for a, b in zip(first, final)), (first, final)
