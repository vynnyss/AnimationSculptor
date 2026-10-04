# SPDX-License-Identifier: GPL-3.0-or-later
"""Sculpt overlay drawn on top of the trails (gpu only; patterns from the vendored LMP ``draw.py``)."""

import math

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


def _draw_ring(shader, co, radius, color, width):
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": _ring(co[0], co[1], radius)})
    shader.bind()
    shader.uniform_float("color", color)
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
    batch.draw(shader)


def draw_pixel():
    hover, gesture = state.HOVER, state.GESTURE
    if hover is None and gesture is None:
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
                scr = picking.project_points(region, rv3d, np.asarray(preview, dtype=np.float64))
                pts = [(float(x), float(y)) for x, y in scr if x == x]  # drop points behind the view
                _draw_polyline(shader, pts, COLOR_PREVIEW, 2.5 * px)
            co = picking.world_to_screen(region, rv3d, gesture["world"])
            if co is not None:
                color = COLOR_REFUSED if gesture.get("refused") else COLOR_ACTIVE
                _draw_ring(shader, co, 10.0 * px, color, 2.5 * px)
        elif hover is not None:
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
