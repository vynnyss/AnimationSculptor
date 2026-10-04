# SPDX-License-Identifier: GPL-3.0-or-later
"""Read/write F-Curves of Slotted Actions (Blender 5.2) and convert them to/from ``core.fcurve_model``.

Channel access follows ``compat.get_fcurves`` of the vendored Live Motion Path (channelbag of the
object's action slot), adapted to 5.2 only and extended with writing. Bulk I/O uses
``keyframe_points.foreach_get/foreach_set``; ``FCurve.update()`` once per channel after a write.
"""

from __future__ import annotations

import numpy as np
from bpy_extras import anim_utils

from ..core.fcurve_model import ChannelModel

KEY_EPSILON = 1e-3


def channelbag(ob, create=False):
    """Channelbag of the object's assigned Action slot (None without Action/slot, unless ``create``)."""
    adt = ob.animation_data
    if adt is None or adt.action is None or adt.action_slot is None:
        return None
    if create:
        return anim_utils.action_ensure_channelbag_for_slot(adt.action, adt.action_slot)
    return anim_utils.action_get_channelbag_for_slot(adt.action, adt.action_slot)


def bone_fcurves(ob, pb) -> list:
    """Every F-Curve that animates the pose bone ``pb``."""
    cb = channelbag(ob)
    if cb is None:
        return []
    prefix = pb.path_from_id()
    return [fc for fc in cb.fcurves if fc.data_path.startswith(prefix + ".") or fc.data_path.startswith(prefix + "[")]


def key_index(fc, frame, eps=KEY_EPSILON):
    for i, kp in enumerate(fc.keyframe_points):
        if abs(kp.co.x - frame) < eps:
            return i
    return None


def bone_has_key(ob, pb, frame) -> bool:
    """True when any F-Curve of the bone has a key at ``frame`` (a key point of its trail)."""
    return any(key_index(fc, frame) is not None for fc in bone_fcurves(ob, pb))


def refusal(ob, pb, channel="location") -> str:
    """Reason why ``channel`` of the bone cannot be sculpted, or '' (ADR 0003: refuse, never work around)."""
    adt = ob.animation_data
    if adt is None or adt.action is None:
        return "sem Action (keye a primeira pose com I)"
    if adt.use_nla and any(len(t.strips) and not t.mute for t in adt.nla_tracks):
        return "NLA ativa"
    if adt.action_influence < 1.0 or adt.action_blend_type != 'REPLACE':
        return "Action com influência/blend"
    path = pb.path_from_id(channel)
    if any(d.data_path == path for d in adt.drivers):
        return "canal com driver"
    cb = channelbag(ob)
    if cb is None:
        return "Action sem canais para este rig"
    for fc in cb.fcurves:
        if fc.data_path == path and any(m.active and not m.mute for m in fc.modifiers):
            return "F-Curve com modificador"
    return ""


def read_channel(fc) -> ChannelModel:
    """F-Curve → ChannelModel (lossless for co, handles, handle types, interpolation, extrapolation)."""
    kps = fc.keyframe_points
    n = len(kps)
    co = np.empty(2 * n, dtype=np.float32)
    hl = np.empty(2 * n, dtype=np.float32)
    hr = np.empty(2 * n, dtype=np.float32)
    if n:
        kps.foreach_get("co", co)
        kps.foreach_get("handle_left", hl)
        kps.foreach_get("handle_right", hr)
    return ChannelModel(
        co.astype(np.float64), hl.astype(np.float64), hr.astype(np.float64),
        [kp.handle_left_type for kp in kps], [kp.handle_right_type for kp in kps],
        [kp.interpolation for kp in kps], fc.extrapolation, fc.data_path, fc.array_index,
    )


def write_channel(fc, model: ChannelModel, update=True) -> None:
    """ChannelModel → F-Curve. ``update=False`` writes the values verbatim (snapshot restore)."""
    kps = fc.keyframe_points
    n = model.key_count
    while len(kps) > n:
        kps.remove(kps[len(kps) - 1], fast=True)
    if len(kps) < n:
        kps.add(n - len(kps))
    for kp, tl, tr, ipo in zip(kps, model.hl_type, model.hr_type, model.interp):
        if kp.interpolation != ipo:
            kp.interpolation = ipo
        if kp.handle_left_type != tl:
            kp.handle_left_type = tl
        if kp.handle_right_type != tr:
            kp.handle_right_type = tr
    if n:
        kps.foreach_set("co", model.co.astype(np.float32).ravel())
        kps.foreach_set("handle_left", model.hl.astype(np.float32).ravel())
        kps.foreach_set("handle_right", model.hr.astype(np.float32).ravel())
    if fc.extrapolation != model.extrapolation:
        fc.extrapolation = model.extrapolation
    if update:
        fc.update()


def ensure_channel(ob, pb, channel, index):
    """F-Curve for ``pose.bones[..].channel[index]``, created in the bone's group when missing.
    Returns (fcurve, created)."""
    cb = channelbag(ob, create=True)
    path = pb.path_from_id(channel)
    fc = cb.fcurves.find(path, index=index)
    if fc is not None:
        return fc, False
    return cb.fcurves.ensure(path, index=index, group_name=pb.name), True


def ensure_key(fc, frame, fallback_value):
    """Index of the key at ``frame``, inserting one with the curve's value there when missing.
    Returns (index, inserted)."""
    idx = key_index(fc, frame)
    if idx is not None:
        return idx, False
    value = fc.evaluate(frame) if len(fc.keyframe_points) else fallback_value
    fc.keyframe_points.insert(frame, value, options={'FAST'})
    fc.update()
    return key_index(fc, frame), True


def tag(ob) -> None:
    """Re-evaluate the object at the current frame after F-Curve writes."""
    adt = ob.animation_data
    if adt is not None and adt.action is not None:
        adt.action.update_tag()
    ob.update_tag(refresh={'OBJECT', 'DATA', 'TIME'})
