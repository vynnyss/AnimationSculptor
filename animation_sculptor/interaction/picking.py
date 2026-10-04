# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen-space picking on motion trails.

Screen ⇄ world helpers follow ``screen_to_world`` / ``world_to_screen`` of the Motion Trail add-on
(Bart Crouch, ``animation_motion_trail.py``, GPL-2.0-or-later), rewritten on top of
``bpy_extras.view3d_utils`` for Blender 5.2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from bpy_extras import view3d_utils
from mathutils import Vector

from ..trails import provider

HIT_RADIUS_PX = 12.0


@dataclass(frozen=True)
class Hit:
    obj_name: str
    bone: str
    frame: int
    is_key: bool
    world: tuple          # (x, y, z) of the trail point
    screen: tuple         # (x, y) region coordinates
    distance: float       # pixels from the mouse
    on_bone: bool = False # the bone's tail at the current frame (direct drag), not a trail point
    on_body: bool = False # a spot on the body's mesh (modo Corpo); ``bone`` is the control that moves it
    deform: str = ""      # deform bone under the cursor (on_body)
    kind: str = ""        # rig.CHAIN (ephemeral rig) / rig.IK (grab/arc of an IK control) (on_body)
    mesh: str = ""        # mesh object hit (on_body)
    reason: str = ""      # why the spot cannot be sculpted ('' when it can)


def project_points(region, rv3d, points: np.ndarray) -> np.ndarray:
    """(N, 3) world points → (N, 2) region pixels; NaN for points behind the view."""
    n = len(points)
    if n == 0:
        return np.empty((0, 2))
    persp = np.array(rv3d.perspective_matrix, dtype=np.float64)
    hom = np.c_[points.astype(np.float64), np.ones(n)] @ persp.T
    w = hom[:, 3]
    out = np.full((n, 2), np.nan)
    ok = w > 1e-6
    out[ok, 0] = (region.width / 2.0) * (1.0 + hom[ok, 0] / w[ok])
    out[ok, 1] = (region.height / 2.0) * (1.0 + hom[ok, 1] / w[ok])
    return out


def world_to_screen(region, rv3d, co) -> Vector | None:
    return view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(co))


def screen_to_world(region, rv3d, mouse, depth_co) -> Vector:
    """Point under ``mouse`` on the view-aligned plane through ``depth_co``."""
    return view3d_utils.region_2d_to_location_3d(region, rv3d, Vector(mouse), Vector(depth_co))


def hit_test(region, rv3d, mouse, trail_keys, radius=None) -> Hit | None:
    """Closest trail point to ``mouse`` within ``radius`` px among the given (obj_name, bone) trails.

    Key points win over sampled points at equal distance (+2 px bias), so a key is easy to grab even
    with dense trails.
    """
    if radius is None:
        from ..ui import prefs

        radius = float(prefs.value("hit_radius_px"))
    best = None
    mx, my = mouse
    for obj_name, bone in trail_keys:
        cache_trail = provider.get_trail_by_key((obj_name, bone))
        if cache_trail is None or len(cache_trail.frames) == 0:
            continue
        scr = project_points(region, rv3d, cache_trail.points)
        d = np.hypot(scr[:, 0] - mx, scr[:, 1] - my)
        d = np.where(np.isnan(d), np.inf, d)
        keys = np.isin(cache_trail.frames, np.asarray(cache_trail.keyframes, dtype=np.int64))
        score = d - 2.0 * keys
        i = int(np.argmin(score))
        if d[i] > radius:
            continue
        if best is None or score[i] < best[0]:
            best = (score[i], Hit(
                obj_name=obj_name,
                bone=bone,
                frame=int(cache_trail.frames[i]),
                is_key=bool(keys[i]),
                world=tuple(float(v) for v in cache_trail.points[i]),
                screen=(float(scr[i, 0]), float(scr[i, 1])),
                distance=float(d[i]),
            ))
    return None if best is None else best[1]


def bone_tip_hit(region, rv3d, mouse, ob, bones, frame, radius=None) -> Hit | None:
    """Closest tail (current pose, current frame) of ``bones`` within ``radius`` px: dragging the bone
    itself, without aiming at its trail (ephemeral rig, phase 4)."""
    if radius is None:
        from ..ui import prefs

        radius = float(prefs.value("hit_radius_px"))
    best = None
    mx, my = mouse
    for name in bones:
        pb = ob.pose.bones.get(name)
        if pb is None:
            continue
        world = ob.matrix_world @ pb.tail
        co = world_to_screen(region, rv3d, world)
        if co is None:
            continue
        d = float(((co.x - mx) ** 2 + (co.y - my) ** 2) ** 0.5)
        if d <= radius and (best is None or d < best.distance):
            from ..anim import action_io

            best = Hit(obj_name=ob.name, bone=name, frame=int(frame), is_key=action_io.bone_has_key(ob, pb, frame),
                       world=tuple(world), screen=(co.x, co.y), distance=d, on_bone=True)
    return best
