# SPDX-License-Identifier: GPL-3.0-or-later
# Vendored from https://github.com/daim1993/blender-live-motion-path@0e173fd (draw.py). Modified for Animation Sculptor:
# see docs/reference/open-source-provenance.md. Original copyright 2026 Experience Elysian.
# ASC-PATCH P1: namespace renamed throughout (Scene.motion_onion -> Scene.asc_trails, LMO_* -> ASC_TR_*,
# motion_onion.* operators -> asc_trails.*) so the original add-on can be installed side by side.
"""GPU drawing of motion paths and onion skins (viewport draw handlers)."""

import math

import bpy
import blf
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from . import compat, engine
from .engine import CACHE, STATE

_handles = []
_shaders = {}
_onion_shader = None
_onion_shader_tried = False

_FONT = 0

# ASC-PATCH P11: optional per-ghost world-space offset hook, installed by trails/provider.py (expanded
# onion skin). Callable (context, obj_name, frame, current_frame) -> (x, y, z) | None. Drawing only.
GHOST_OFFSET = None


# ---------------------------------------------------------------------------
# Shaders
# ---------------------------------------------------------------------------

def _builtin(name):
    sh = _shaders.get(name)
    if sh is None:
        sh = gpu.shader.from_builtin(name)
        _shaders[name] = sh
    return sh


_ONION_VERT = """
void main()
{
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
    vNormal = nor;
}
"""

_ONION_FRAG = """
void main()
{
    vec3 n = normalize(vNormal);
    vec3 viewDir = viewParams.xyz;
    vec3 lightDir = lightParams.xyz;
    float lightStrength = lightParams.w;
    float rimStrength = viewParams.w;
    /* two sided lighting: flip normals that face away from the viewer */
    float facing = dot(n, viewDir);
    if (facing < 0.0) {
        n = -n;
        facing = -facing;
    }
    float diff = max(dot(n, lightDir), 0.0);
    float shade = mix(1.0, 0.3 + 0.7 * diff, lightStrength);
    float rim = pow(1.0 - clamp(facing, 0.0, 1.0), 3.0) * rimStrength;
    vec3 col = color.rgb * shade + rim * (color.rgb * 0.5 + 0.5);
    float a = clamp(color.a + rim * color.a, 0.0, 1.0);
    fragColor = vec4(col, a);
}
"""


def _get_onion_shader():
    """Small lit shader for ghosts (compiled once).  None when unavailable.

    Push constants are packed into 112 bytes (MAT4 + 3 x VEC4) to stay under the
    128 byte minimum guaranteed by Vulkan."""
    global _onion_shader, _onion_shader_tried
    if _onion_shader is not None or _onion_shader_tried:
        return _onion_shader
    _onion_shader_tried = True
    try:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', "ModelViewProjectionMatrix")
        info.push_constant('VEC4', "color")
        info.push_constant('VEC4', "lightParams")   # xyz: light direction, w: strength
        info.push_constant('VEC4', "viewParams")    # xyz: view direction, w: rim strength
        info.vertex_in(0, 'VEC3', "pos")
        info.vertex_in(1, 'VEC3', "nor")
        iface = gpu.types.GPUStageInterfaceInfo("lmo_onion_iface")
        iface.smooth('VEC3', "vNormal")
        info.vertex_out(iface)
        info.fragment_out(0, 'VEC4', "fragColor")
        info.vertex_source(_ONION_VERT)
        info.fragment_source(_ONION_FRAG)
        _onion_shader = gpu.shader.create_from_info(info)
        del iface
        del info
    except Exception as e:
        print("[Live Motion Onion] shaded ghost shader unavailable, using flat shading: %s" % e)
        STATE.shaded_shader_failed = True
        _onion_shader = None
    return _onion_shader


def _uniform(shader, name, value):
    try:
        shader.uniform_float(name, value)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------

def _batch(skin, kind, shader):
    b = skin.batches.get(kind)
    if b is not None:
        return b
    try:
        if kind == 'solid_shaded':
            b = batch_for_shader(shader, 'TRIS', {"pos": skin.pos, "nor": skin.nor}, indices=skin.tris)
        elif kind == 'solid_flat':
            b = batch_for_shader(shader, 'TRIS', {"pos": skin.pos}, indices=skin.tris)
        elif kind == 'wire':
            b = batch_for_shader(shader, 'LINES', {"pos": skin.pos}, indices=skin.edges)
        else:
            return None
    except Exception:
        # numpy buffers rejected for some reason -> fall back to plain sequences
        try:
            if kind == 'solid_shaded':
                b = batch_for_shader(shader, 'TRIS', {"pos": skin.pos.tolist(), "nor": skin.nor.tolist()},
                                     indices=skin.tris.tolist())
            elif kind == 'solid_flat':
                b = batch_for_shader(shader, 'TRIS', {"pos": skin.pos.tolist()}, indices=skin.tris.tolist())
            else:
                b = batch_for_shader(shader, 'LINES', {"pos": skin.pos.tolist()}, indices=skin.edges.tolist())
        except Exception as e:
            print("[Live Motion Onion] could not build ghost batch: %s" % e)
            return None
    skin.batches[kind] = b
    return b


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _restore_state():
    try:
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)
        gpu.state.face_culling_set('NONE')
        gpu.state.line_width_set(1.0)
        gpu.state.point_size_set(1.0)
    except Exception:
        pass


def _lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _ghost_color(s, side, index, count):
    """(r, g, b, a) for a ghost."""
    if count <= 1:
        t = 0.0
    else:
        t = (index - 1) / float(count - 1)
    alpha = s.onion_opacity * (1.0 - s.onion_falloff * t)
    if side == 0:
        alpha = s.onion_opacity
    mode = s.onion_color_mode
    if mode == 'SINGLE':
        col = tuple(s.onion_color)
    elif mode == 'GRADIENT':
        col = _lerp3(tuple(s.onion_color_near), tuple(s.onion_color_far), t)
    else:
        if side < 0:
            col = tuple(s.onion_color_before)
        elif side > 0:
            col = tuple(s.onion_color_after)
        else:
            col = tuple(s.onion_color)
    return (col[0], col[1], col[2], max(0.0, min(1.0, alpha)))


def _view_vectors(rv3d):
    """(view_dir, light_dir) in world space."""
    try:
        vinv = rv3d.view_matrix.inverted()
    except Exception:
        vinv = Matrix.Identity(4)
    view_dir = (vinv.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()   # towards the viewer
    light_dir = (vinv.to_3x3() @ Vector((-0.35, 0.55, 1.0))).normalized()
    return tuple(view_dir), tuple(light_dir)


def _mvp():
    return gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix()


# ---------------------------------------------------------------------------
# Onion skins
# ---------------------------------------------------------------------------

def _draw_onion(context, s, scene, targets, region, rv3d):
    cf = scene.frame_current
    px = compat.pixel_size()
    view_dir, light_dir = _view_vectors(rv3d)
    mvp = _mvp()
    shaded = None
    if s.onion_shading == 'SHADED':
        shaded = _get_onion_shader()
    flat = _builtin('UNIFORM_COLOR')
    polyline = _builtin('POLYLINE_UNIFORM_COLOR')
    draw_solid = s.onion_draw_type in ('SOLID', 'BOTH')
    draw_wire = s.onion_draw_type in ('WIRE', 'BOTH')
    depth_test = 'NONE' if s.onion_xray else 'LESS_EQUAL'
    viewport = (float(region.width), float(region.height))

    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set(depth_test)

    for t in targets:
        if not t.want_onion:
            continue
        cache = CACHE.get(t.key)
        if cache is None:
            continue
        ghosts = engine.onion_frame_list(cache, s, scene, cf)
        # farthest first so near ghosts are drawn on top
        ghosts.sort(key=lambda g: (-abs(g[0] - cf), g[0]))
        for f, side, index, count in ghosts:
            skin = cache.world_skin(f)
            if skin is None or skin.nverts == 0:
                continue
            color = _ghost_color(s, side, index, count)
            if color[3] <= 0.001:
                continue
            # ASC-PATCH P11: shift the ghost on screen (expanded onion); cached data is untouched
            ghost_mvp = mvp
            offset = GHOST_OFFSET(context, cache.obj_name, f, cf) if GHOST_OFFSET is not None else None
            if offset is not None and any(offset):
                shift = Matrix.Translation(offset)
                ghost_mvp = mvp @ shift
                gpu.matrix.push()
                gpu.matrix.multiply_matrix(shift)
            else:
                offset = None
            try:  # ASC-PATCH P11: the matrix stack stays balanced even if drawing a ghost fails
                if draw_solid and len(skin.tris):
                    gpu.state.depth_mask_set(bool(s.onion_depth_write))
                    if s.onion_backface_culling:
                        gpu.state.face_culling_set('FRONT' if skin.flip else 'BACK')
                    else:
                        gpu.state.face_culling_set('NONE')
                    if shaded is not None:
                        batch = _batch(skin, 'solid_shaded', shaded)
                        if batch is not None:
                            shaded.bind()
                            _uniform(shaded, "ModelViewProjectionMatrix", ghost_mvp)  # ASC-PATCH P11
                            _uniform(shaded, "color", color)
                            _uniform(shaded, "lightParams", (light_dir[0], light_dir[1], light_dir[2], s.onion_light_strength))
                            _uniform(shaded, "viewParams", (view_dir[0], view_dir[1], view_dir[2], s.onion_rim))
                            batch.draw(shaded)
                    else:
                        batch = _batch(skin, 'solid_flat', flat)
                        if batch is not None:
                            flat.bind()
                            _uniform(flat, "color", color)
                            batch.draw(flat)
                    gpu.state.face_culling_set('NONE')
                if draw_wire and len(skin.edges):
                    gpu.state.depth_mask_set(False)
                    wcol = (color[0], color[1], color[2], min(1.0, color[3] * s.onion_wire_opacity))
                    batch = _batch(skin, 'wire', polyline)
                    if batch is not None:
                        polyline.bind()
                        _uniform(polyline, "color", wcol)
                        _uniform(polyline, "lineWidth", s.onion_wire_width * px)
                        _uniform(polyline, "viewportSize", viewport)
                        try:
                            polyline.uniform_bool("lineSmooth", [True])
                        except Exception:
                            pass
                        batch.draw(polyline)
            finally:
                if offset is not None:   # ASC-PATCH P11
                    gpu.matrix.pop()
    gpu.state.depth_mask_set(False)
    gpu.state.face_culling_set('NONE')


# ---------------------------------------------------------------------------
# Motion paths
# ---------------------------------------------------------------------------

def _color_signature(s, cf, lo, hi):
    return (s.path_color_mode, tuple(s.path_color), tuple(s.path_color_past), tuple(s.path_color_future),
            tuple(s.path_color_start), tuple(s.path_color_end), tuple(s.path_color_slow),
            tuple(s.path_color_fast), s.path_alpha, s.path_fade, s.path_show_past, s.path_show_future,
            cf, lo, hi)


def _path_colors(frames, pts, cf, s, lo, hi):
    n = len(frames)
    cols = np.empty((n, 4), dtype=np.float32)
    mode = s.path_color_mode
    if mode == 'SINGLE':
        cols[:, :3] = np.array(tuple(s.path_color), dtype=np.float32)
    elif mode == 'GRADIENT':
        span = max(1, hi - lo)
        t = ((frames - lo) / float(span)).clip(0.0, 1.0).astype(np.float32)
        a = np.array(tuple(s.path_color_start), dtype=np.float32)
        b = np.array(tuple(s.path_color_end), dtype=np.float32)
        cols[:, :3] = a[None, :] + (b - a)[None, :] * t[:, None]
    elif mode == 'SPEED':
        if n > 1:
            d = np.linalg.norm(np.diff(pts.astype(np.float64), axis=0), axis=1)
            df = np.diff(frames.astype(np.float64))
            df[df == 0] = 1.0
            speed = d / df
            speed = np.concatenate([speed[:1], speed])
            hi_s = float(np.percentile(speed, 95)) if n > 4 else float(speed.max())
            if hi_s <= 1e-9:
                hi_s = 1.0
            t = (speed / hi_s).clip(0.0, 1.0).astype(np.float32)
        else:
            t = np.zeros(n, dtype=np.float32)
        a = np.array(tuple(s.path_color_slow), dtype=np.float32)
        b = np.array(tuple(s.path_color_fast), dtype=np.float32)
        cols[:, :3] = a[None, :] + (b - a)[None, :] * t[:, None]
    else:  # PAST_FUTURE
        past = np.array(tuple(s.path_color_past), dtype=np.float32)
        fut = np.array(tuple(s.path_color_future), dtype=np.float32)
        before = frames < cf
        cols[:, :3] = np.where(before[:, None], past[None, :], fut[None, :])
    alpha = np.full(n, s.path_alpha, dtype=np.float32)
    if s.path_fade > 0.0:
        half = float(max(1, max(cf - lo, hi - cf)))
        dist = (np.abs(frames - cf) / half).clip(0.0, 1.0).astype(np.float32)
        alpha *= (1.0 - s.path_fade * dist)
    cols[:, 3] = alpha
    return cols


def _draw_paths(context, s, scene, targets, region, rv3d):
    cf = scene.frame_current
    px = compat.pixel_size()
    lo, hi = engine.path_display_range(scene, s)
    line_shader = _builtin('POLYLINE_SMOOTH_COLOR')
    try:
        point_shader = _builtin('POINT_FLAT_COLOR')
    except Exception:
        point_shader = None
    viewport = (float(region.width), float(region.height))

    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE' if s.path_xray else 'LESS_EQUAL')
    gpu.state.depth_mask_set(False)

    for t in targets:
        if not t.want_path:
            continue
        cache = CACHE.get(t.key)
        if cache is None or cache.path_points is None or cache.path_frames is None:
            continue
        frames = cache.path_frames
        pts = cache.path_points
        mask = (frames >= lo) & (frames <= hi)
        if not s.path_show_past:
            mask &= frames >= cf
        if not s.path_show_future:
            mask &= frames <= cf
        idx = np.nonzero(mask)[0]
        if len(idx) == 0:
            continue
        sig = _color_signature(s, cf, lo, hi) + (len(idx), int(idx[0]), int(idx[-1]))
        cc = cache.color_cache
        if cc is None or cc[0] != sig:
            f_sel = frames[idx]
            p_sel = np.ascontiguousarray(pts[idx])
            cols = _path_colors(f_sel, p_sel, cf, s, lo, hi)
            line_batch = None
            point_batch = None
            try:
                if len(p_sel) >= 2:
                    line_batch = batch_for_shader(line_shader, 'LINE_STRIP', {"pos": p_sel, "color": cols})
                if point_shader is not None:
                    point_batch = batch_for_shader(point_shader, 'POINTS', {"pos": p_sel, "color": cols})
            except Exception as e:
                print("[Live Motion Onion] path batch failed: %s" % e)
            cc = (sig, cols, line_batch, point_batch)
            cache.color_cache = cc
        _sig, cols, line_batch, point_batch = cc
        if line_batch is not None:
            line_shader.bind()
            _uniform(line_shader, "lineWidth", s.path_line_width * px)
            _uniform(line_shader, "viewportSize", viewport)
            try:
                line_shader.uniform_bool("lineSmooth", [True])
            except Exception:
                pass
            line_batch.draw(line_shader)
        if s.path_show_points and point_batch is not None:
            point_shader.bind()
            _uniform(point_shader, "size", s.path_point_size * px)
            point_batch.draw(point_shader)


# ---------------------------------------------------------------------------
# 2D overlay: keyframe markers, current frame marker, frame numbers
# ---------------------------------------------------------------------------

def _marker_tris(cx, cy, size, shape, out_verts, out_tris):
    base = len(out_verts)
    r = size * 0.5
    if shape == 'SQUARE':
        out_verts.extend(((cx - r, cy - r, 0.0), (cx + r, cy - r, 0.0), (cx + r, cy + r, 0.0), (cx - r, cy + r, 0.0)))
        out_tris.extend(((base, base + 1, base + 2), (base, base + 2, base + 3)))
    elif shape == 'CIRCLE':
        segs = 16
        out_verts.append((cx, cy, 0.0))
        for i in range(segs):
            a = 2.0 * math.pi * i / segs
            out_verts.append((cx + math.cos(a) * r, cy + math.sin(a) * r, 0.0))
        for i in range(segs):
            out_tris.append((base, base + 1 + i, base + 1 + (i + 1) % segs))
    else:  # DIAMOND
        out_verts.extend(((cx, cy - r, 0.0), (cx + r, cy, 0.0), (cx, cy + r, 0.0), (cx - r, cy, 0.0)))
        out_tris.extend(((base, base + 1, base + 2), (base, base + 2, base + 3)))


def _current_point(t):
    """Live world position of a target (object origin or bone point) at the current frame."""
    ob = bpy.data.objects.get(t.obj_name)
    if ob is None:
        return None
    try:
        if t.bone:
            pb = ob.pose.bones.get(t.bone) if ob.pose is not None else None
            if pb is None:
                return None
            s = bpy.context.scene.asc_trails
            point = engine.bone_point(ob, t.bone, s)  # ASC-PATCH P9
            if point == 'TAIL':
                return ob.matrix_world @ pb.tail
            if point == 'CENTER':
                return ob.matrix_world @ ((pb.head + pb.tail) * 0.5)
            return ob.matrix_world @ pb.head
        return ob.matrix_world.translation.copy()
    except Exception:
        return None


def _draw_markers_2d(context, s, scene, targets, region, rv3d):
    from bpy_extras import view3d_utils

    cf = scene.frame_current
    lo, hi = engine.path_display_range(scene, s)
    px = compat.pixel_size()
    ui = compat.ui_scale()
    shader = _builtin('UNIFORM_COLOR')
    want_keys = s.path_show_keyframes
    want_cur = s.path_show_current
    want_num = s.path_show_numbers

    key_verts, key_tris = [], []
    cur_verts, cur_tris = [], []
    labels = []
    step = max(1, s.path_number_step)

    for t in targets:
        if not t.want_path:
            continue
        cache = CACHE.get(t.key)
        if cache is None:
            continue
        # current frame marker follows the live object / bone position
        if want_cur:
            p = _current_point(t)
            if p is not None:
                co = view3d_utils.location_3d_to_region_2d(region, rv3d, p)
                if co is not None:
                    _marker_tris(co.x, co.y, s.path_current_size * px, 'CIRCLE', cur_verts, cur_tris)
        if cache.path_points is None or cache.path_frames is None:
            continue
        if not (want_keys or want_num):
            continue
        # a target that does not move has all its markers stacked on one point: skip them
        if len(cache.path_points) > 1 and float(np.ptp(cache.path_points, axis=0).max()) < 1e-5:
            continue
        frames = cache.path_frames
        keyset = set(cache.keyframes) if (want_keys or want_num) else set()
        for i in range(len(frames)):
            f = int(frames[i])
            if f < lo or f > hi:
                continue
            if not s.path_show_past and f < cf:
                continue
            if not s.path_show_future and f > cf:
                continue
            is_key = f in keyset
            need_label = want_num and (f % step == 0 or (s.path_numbers_keyframes and is_key))
            if not (is_key and want_keys) and not need_label:
                continue
            p = cache.path_points[i]
            co = view3d_utils.location_3d_to_region_2d(region, rv3d, Vector((float(p[0]), float(p[1]), float(p[2]))))
            if co is None:
                continue
            if is_key and want_keys:
                _marker_tris(co.x, co.y, s.path_keyframe_size * px, s.path_keyframe_shape, key_verts, key_tris)
            if need_label:
                labels.append((co.x, co.y, str(f), is_key))

    gpu.state.blend_set('ALPHA')
    gpu.state.depth_test_set('NONE')
    if key_tris:
        col = tuple(s.path_keyframe_color) + (s.path_alpha,)
        try:
            batch = batch_for_shader(shader, 'TRIS', {"pos": key_verts}, indices=key_tris)
            shader.bind()
            _uniform(shader, "color", col)
            batch.draw(shader)
        except Exception as e:
            print("[Live Motion Onion] marker batch failed: %s" % e)
    if cur_tris:
        col = tuple(s.path_current_color) + (s.path_alpha,)
        try:
            batch = batch_for_shader(shader, 'TRIS', {"pos": cur_verts}, indices=cur_tris)
            shader.bind()
            _uniform(shader, "color", col)
            batch.draw(shader)
        except Exception as e:
            print("[Live Motion Onion] marker batch failed: %s" % e)
    if labels:
        size = max(6, int(round(s.path_number_size * ui)))
        try:
            blf.size(_FONT, size)
        except Exception:
            blf.size(_FONT, size, 72)
        try:
            blf.enable(_FONT, blf.SHADOW)
            blf.shadow(_FONT, 3, 0.0, 0.0, 0.0, 0.8)
            blf.shadow_offset(_FONT, 1, -1)
        except Exception:
            pass
        r, g, b = s.path_number_color
        off = s.path_number_offset * px
        for x, y, text, is_key in labels:
            blf.color(_FONT, r, g, b, s.path_alpha)
            blf.position(_FONT, x + off, y + off, 0.0)
            blf.draw(_FONT, text)
        try:
            blf.disable(_FONT, blf.SHADOW)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _visible(context, s):
    if not s.enabled:
        return False
    if s.respect_overlays:
        try:
            if not context.space_data.overlay.show_overlays:
                return False
        except Exception:
            pass
    return True


def draw_view3d():
    context = bpy.context
    scene = context.scene
    s = getattr(scene, "asc_trails", None)
    if s is None or not _visible(context, s):
        return
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    playing = STATE.playing
    try:
        targets = engine.get_draw_targets(context)
        if not targets:
            return
        if s.onion_show and not (playing and s.hide_onion_on_playback):
            _draw_onion(context, s, scene, targets, region, rv3d)
        if s.path_show and not (playing and s.hide_path_on_playback):
            _draw_paths(context, s, scene, targets, region, rv3d)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        _restore_state()


def draw_pixel():
    context = bpy.context
    scene = context.scene
    s = getattr(scene, "asc_trails", None)
    if s is None or not _visible(context, s):
        return
    if not s.path_show or (STATE.playing and s.hide_path_on_playback):
        return
    if not (s.path_show_keyframes or s.path_show_current or s.path_show_numbers):
        return
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    try:
        targets = STATE.targets
        if targets:
            _draw_markers_2d(context, s, scene, targets, region, rv3d)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        _restore_state()


def register():
    unregister()
    if bpy.app.background:
        return
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_view3d, (), 'WINDOW', 'POST_VIEW'))
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_pixel, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    global _onion_shader, _onion_shader_tried
    for h in _handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
        except Exception:
            pass
    _handles.clear()
    _shaders.clear()
    _onion_shader = None
    _onion_shader_tried = False
    for c in CACHE.values():
        for skin in c.onion.values():
            skin.clear_gpu()
        c.color_cache = None
