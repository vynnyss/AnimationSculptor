# SPDX-License-Identifier: GPL-3.0-or-later
"""Sculpt overlay drawn on top of the trails (gpu only; patterns from the vendored LMP ``draw.py``)."""

import math

import blf
import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from ..trails.lmp import compat
from . import picking, state

_handle = None

COLOR_KEY = (1.0, 1.0, 1.0, 1.0)
COLOR_SAMPLED = (0.55, 0.85, 1.0, 1.0)
COLOR_ACTIVE = (1.0, 0.75, 0.2, 1.0)
COLOR_REFUSED = (1.0, 0.25, 0.2, 1.0)
COLOR_PREVIEW = (1.0, 0.85, 0.3, 1.0)
SPEED_SLOW = np.array((0.1, 0.4, 1.0))
SPEED_FAST = np.array((1.0, 0.15, 0.1))


def _ring(cx, cy, radius, segments=24):
    pts = []
    for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        pts.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius))
    return pts


def _draw_polyline(shader, pts, color, width):
    if len(pts) < 2:
        return
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": pts})
    shader.bind()
    shader.uniform_float("color", color)
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    batch.draw(shader)


def _speed_colors(world_pts):
    """Blue (slow) → red (fast) per point, from the distance travelled per frame (like the LMP Speed mode)."""
    p = np.asarray(world_pts, dtype=np.float64)
    if len(p) < 2:
        return np.tile(np.r_[SPEED_SLOW, 1.0], (len(p), 1))
    speed = np.linalg.norm(np.diff(p, axis=0), axis=1)
    speed = np.r_[speed[:1], speed]
    top = float(np.percentile(speed, 95)) if len(speed) > 4 else float(speed.max())
    t = np.clip(speed / (top if top > 1e-9 else 1.0), 0.0, 1.0)[:, None]
    rgb = SPEED_SLOW[None] + (SPEED_FAST - SPEED_SLOW)[None] * t
    return np.c_[rgb, np.ones(len(p))]


def _draw_dots(points_2d, colors, size):
    shader = gpu.shader.from_builtin('POINT_FLAT_COLOR')
    pos = [(x, y, 0.0) for x, y in points_2d]
    batch = batch_for_shader(shader, 'POINTS', {"pos": pos, "color": [tuple(c) for c in colors]})
    gpu.state.point_size_set(size)
    shader.bind()
    batch.draw(shader)


def _draw_label(co, text, px):
    blf.size(0, int(13 * px))
    blf.color(0, 1.0, 1.0, 1.0, 1.0)
    blf.position(0, co[0] + 14 * px, co[1] + 10 * px, 0.0)
    blf.draw(0, text)


def _draw_ring(shader, co, radius, color, width):
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": _ring(co[0], co[1], radius)})
    shader.bind()
    shader.uniform_float("color", color)
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    batch.draw(shader)


def draw_pixel():
    hover, gesture, refusal = state.HOVER, state.GESTURE, state.REFUSAL
    if hover is None and gesture is None and refusal is None:
        return
    context = bpy.context
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return
    px = compat.pixel_size()
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    try:
        if gesture is not None:
            preview = gesture.get("preview")
            if preview:
                world = np.asarray(preview, dtype=np.float64)
                scr = picking.project_points(region, rv3d, world)
                ok = ~np.isnan(scr[:, 0])                                  # drop points behind the view
                pts = [(float(x), float(y)) for x, y in scr[ok]]
                if gesture.get("speed"):
                    _draw_dots(pts, _speed_colors(world)[ok], 6.0 * px)    # spacing: dots coloured by speed
                    shader.bind()
                else:
                    _draw_polyline(shader, pts, COLOR_PREVIEW, 2.5 * px)
            for world, w in gesture.get("falloff") or ():
                if world is None:
                    continue
                fco = picking.world_to_screen(region, rv3d, world)
                if fco is not None:
                    color = (COLOR_ACTIVE[0], COLOR_ACTIVE[1], COLOR_ACTIVE[2], 0.25 + 0.75 * w)
                    _draw_ring(shader, fco, (3.0 + 5.0 * w) * px, color, 2.0 * px)
            co = picking.world_to_screen(region, rv3d, gesture["world"])
            if co is not None:
                color = COLOR_REFUSED if gesture.get("refused") else COLOR_ACTIVE
                _draw_ring(shader, co, 10.0 * px, color, 2.5 * px)
                if gesture.get("label"):
                    _draw_label(co, gesture["label"], px)
        else:
            if refusal is not None:
                co = picking.world_to_screen(region, rv3d, refusal["world"])
                if co is not None:
                    _draw_ring(shader, co, 11.0 * px, COLOR_REFUSED, 3.0 * px)
            if hover is not None:
                co = picking.world_to_screen(region, rv3d, hover.world)
                if co is not None:
                    _draw_ring(shader, co, 9.0 * px, COLOR_KEY if hover.is_key else COLOR_SAMPLED, 2.0 * px)
    except Exception as exc:
        print(f"[Animation Sculptor] overlay error: {exc}")
    finally:
        gpu.state.blend_set('NONE')


def register():
    global _handle
    unregister()
    if bpy.app.background:
        return
    _handle = bpy.types.SpaceView3D.draw_handler_add(draw_pixel, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _handle
    if _handle is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handle, 'WINDOW')
        except Exception:
            pass
        _handle = None
