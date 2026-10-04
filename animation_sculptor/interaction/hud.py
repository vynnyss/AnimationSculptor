# SPDX-License-Identifier: GPL-3.0-or-later
"""Time ruler drawn at the bottom of the viewport (design/ephemeral-rig.md, "Régua de tempo no viewport").

Centred on the current frame f₀, it shows the gesture window ``[f₀ − r_past, f₀ + r_future]`` with
the falloff as alpha (past red, future green), the key frames of the active control and two end
handles that the ``asc.time_window`` modal drags. No state of its own: the radii live in
``Scene.asc_sculpt``, the geometry in ``core/ruler``, hover/drag in ``interaction/state``.
"""

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..anim import action_io
from ..core import falloff, ruler
from ..trails import provider
from ..trails.lmp import compat
from ..ui import props
from . import state

COLOR_BG = (0.0, 0.0, 0.0, 0.45)
COLOR_TICK = (1.0, 1.0, 1.0, 0.35)
COLOR_TICK_MAJOR = (1.0, 1.0, 1.0, 0.7)
KEY_PAST = (1.0, 0.45, 0.4)
KEY_FUTURE = (0.45, 1.0, 0.5)
WINDOW_ALPHA = (0.12, 0.7)     # alpha of the window at weight 0 / 1
SAMPLES_PER_SIDE = 48


def visible(context) -> bool:
    """The ruler shows with the tool active on an armature in Pose Mode (and the setting on)."""
    from .gizmo import _tool_active

    s = props.get(context)
    ob = context.active_object
    return (s is not None and s.show_time_ruler and ob is not None and ob.type == 'ARMATURE'
            and ob.mode == 'POSE' and _tool_active(context))


def radii(context):
    s = props.get(context)
    return (s.radius_past, s.radius_future) if s is not None else (0.0, 0.0)


def current_layout(context, region=None):
    region = region or context.region
    if region is None:
        return None
    rp, rf = radii(context)
    px = compat.pixel_size()
    half_span = state.RULER_SPAN or ruler.half_span_for_width(rp, rf, ruler.ruler_width(region.width, px), px)
    return ruler.layout(region.width, region.height, px, context.scene.frame_current, half_span)


def hit(context, mouse):
    """PAST / FUTURE when ``mouse`` (region px) is on an end handle of a visible ruler, else None."""
    if not visible(context):
        return None
    lay = current_layout(context)
    if lay is None:
        return None
    rp, rf = radii(context)
    return ruler.hit_handle(lay, mouse, rp, rf)


def _rects(shader, rects, color):
    if not rects:
        return
    verts, idx = [], []
    for x0, y0, x1, y1 in rects:
        n = len(verts)
        verts += [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        idx += [(n, n + 1, n + 2), (n, n + 2, n + 3)]
    batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=idx)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _window(lay, rp, rf, shape):
    """Gradient quads of the window: alpha = weight, red before f₀ and green after."""
    verts, cols, idx = [], [], []
    y0, y1 = lay.y, lay.y + lay.height
    for side, radius, rgb in ((-1.0, rp, provider.PAST_COLOR), (1.0, rf, provider.FUTURE_COLOR)):
        if radius <= 0.0:
            continue
        offsets = [side * radius * i / SAMPLES_PER_SIDE for i in range(SAMPLES_PER_SIDE + 1)]
        weights = falloff.weight_signed(offsets, rp, rf, shape)
        prev = None
        for o, w in zip(offsets, weights):
            x = min(max(lay.x_of(lay.f0 + o), lay.left), lay.right)
            a = WINDOW_ALPHA[0] + (WINDOW_ALPHA[1] - WINDOW_ALPHA[0]) * float(w)
            n = len(verts)
            verts += [(x, y0), (x, y1)]
            cols += [(*rgb, a), (*rgb, a)]
            if prev is not None:
                idx += [(prev, prev + 1, n + 1), (prev, n + 1, n)]
            prev = n
    if not idx:
        return
    shader = gpu.shader.from_builtin('SMOOTH_COLOR')
    batch = batch_for_shader(shader, 'TRIS', {"pos": verts, "color": cols}, indices=idx)
    shader.bind()
    batch.draw(shader)


def _text(x, y, text, color, size_px, center=True):
    blf.size(0, size_px)
    blf.color(0, *color)
    w, _h = blf.dimensions(0, text)
    blf.position(0, x - (w / 2.0 if center else 0.0), y, 0.0)
    blf.draw(0, text)


def _key_frames(context):
    """Key frames (ints) of the control being sculpted, else under hover, else the active pose bone.

    Read from the Action (not the trail, which may be off): union of the bone's F-Curve key frames.
    """
    ob = context.active_object
    if ob is None or ob.pose is None:
        return ()
    name = state.GESTURE.get("bone") if state.GESTURE else None
    if name is None and state.HOVER is not None and state.HOVER.obj_name == ob.name:
        name = state.HOVER.bone
    pb = ob.pose.bones.get(name) if name is not None else context.active_pose_bone
    if pb is None:
        return ()
    frames = set()
    for fc in action_io.bone_fcurves(ob, pb):
        for kp in fc.keyframe_points:
            frames.add(int(round(kp.co.x)))
    return sorted(frames)


def draw(context):
    """Draw the ruler (POST_PIXEL; called by overlay.draw_pixel)."""
    if not visible(context):
        return
    lay = current_layout(context)
    if lay is None:
        return
    s = props.get(context)
    rp, rf = s.radius_past, s.radius_future
    px = lay.px
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    y0, y1 = lay.y, lay.y + lay.height
    _rects(shader, [(lay.left - 6 * px, y0 - 28 * px, lay.right + 6 * px, y1 + 18 * px)], COLOR_BG)
    _window(lay, rp, rf, s.falloff)

    ticks = lay.ticks()
    _rects(shader, [(lay.x_of(f) - 0.5 * px, y0, lay.x_of(f) + 0.5 * px, y0 + 4 * px)
                    for f, major in ticks if not major], COLOR_TICK)
    _rects(shader, [(lay.x_of(f) - 0.5 * px, y0, lay.x_of(f) + 0.5 * px, y0 + 8 * px)
                    for f, major in ticks if major], COLOR_TICK_MAJOR)
    for f, major in ticks:
        if major and abs(f - lay.f0) * lay.ppf > 18 * px:
            _text(lay.x_of(f), y1 + 4 * px, str(f), (1.0, 1.0, 1.0, 0.6), int(10 * px))

    # Key track: thin line under the strip with a dot per key of the relevant control.
    ty0, ty1 = y0 - ruler.TRACK_BOTTOM_PX * px, y0 - ruler.TRACK_TOP_PX * px
    ty = (ty0 + ty1) / 2.0
    _rects(shader, [(lay.left, ty - 0.5 * px, lay.right, ty + 0.5 * px)], COLOR_TICK)
    marks = ruler.key_marks(_key_frames(context), lay.f0, lay.f0 - lay.half_span, lay.f0 + lay.half_span)
    d = 2.5 * px
    for kind, rgb in ((ruler.PAST, KEY_PAST), (ruler.FUTURE, KEY_FUTURE), ("CURRENT", (1.0, 1.0, 1.0))):
        _rects(shader, [(lay.x_of(f) - d, ty - d, lay.x_of(f) + d, ty + d) for f, k in marks if k == kind],
               (*rgb, 1.0))

    cx = lay.x_of(lay.f0)
    _rects(shader, [(cx - 1.0 * px, y0 - 3 * px, cx + 1.0 * px, y1 + 3 * px)], (*provider.CURRENT_COLOR, 1.0))
    _text(cx, y1 + 4 * px, str(int(lay.f0)), (1.0, 1.0, 1.0, 1.0), int(11 * px))

    tri_shader = shader
    for side, radius, rgb in ((ruler.PAST, rp, provider.PAST_COLOR), (ruler.FUTURE, rf, provider.FUTURE_COLOR)):
        x = ruler.handle_x(lay, side, rp, rf)
        active = side in (state.RULER_HOVER, state.RULER_DRAG)
        half = (1.8 if active else 1.0) * px
        col = (*rgb, 1.0) if active else (*rgb, 0.85)
        _rects(shader, [(x - half, y0 - 3 * px, x + half, y1 + 3 * px)], col)
        tri = ruler.triangle(lay, side, x)
        if active:                                   # bigger triangle: grow around its vertical edge
            w = (tri[1][0] - x) * 0.3
            tri = [(tri[0][0], tri[0][1] + 1.5 * px), (tri[1][0] + w, tri[1][1] - 2 * px),
                   (tri[2][0], tri[2][1] - 2 * px)]
        batch = batch_for_shader(tri_shader, 'TRIS', {"pos": tri})
        tri_shader.bind()
        tri_shader.uniform_float("color", (min(rgb[0] + 0.25, 1.0), min(rgb[1] + 0.25, 1.0),
                                           min(rgb[2] + 0.25, 1.0), 1.0) if active else col)
        batch.draw(tri_shader)
        if radius > 0 or active:
            text = f"{radius:g}"
            blf.size(0, int(10 * px))
            w, _h = blf.dimensions(0, text)
            lx = x + ((-(ruler.TRI_WIDTH_PX + 4) * px - w) if side == ruler.PAST else (ruler.TRI_WIDTH_PX + 4) * px)
            _text(lx, y0 - 23 * px, text, (*rgb, 1.0), int(10 * px), center=False)
