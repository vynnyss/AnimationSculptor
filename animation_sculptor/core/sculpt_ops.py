# SPDX-License-Identifier: GPL-3.0-or-later
"""Spatial sculpt operations on channel models (pure numpy — ADR 0008).

Math: docs/design/motion-sculpt-model.md ("Operações da Iteração 1").
"""

from __future__ import annotations

from .fcurve_model import ChannelModel


def grab_key(model: ChannelModel, index: int, delta: float) -> ChannelModel:
    """Rigid grab of one key: the key and both of its handles move by ``delta`` in value.

    Handle types and every frame (x) are preserved; other keys are untouched. delta = 0 is identity.
    """
    out = model.copy()
    out.co[index, 1] += delta
    out.hl[index, 1] += delta
    out.hr[index, 1] += delta
    return out


AUTO_TYPES = ("AUTO", "AUTO_CLAMPED", "ALIGNED")


def _align_opposite(out: ChannelModel, key: int, edited: str) -> None:
    """Rotate the opposite handle of ``key`` to be collinear with the edited one, keeping its frame (x):
    tangent continuity at the key without touching any timing (invariant 2)."""
    kx, ky = out.co[key]
    h_edit = out.hr[key] if edited == "R" else out.hl[key]
    h_opp = out.hl[key] if edited == "R" else out.hr[key]
    dx = h_edit[0] - kx
    if abs(dx) < 1e-12:
        return
    slope = (h_edit[1] - ky) / dx
    h_opp[1] = ky + slope * (h_opp[0] - kx)


def _set_types(out: ChannelModel, key: int, edited: str, break_tangent: bool) -> bool:
    """Handle types after editing one side. Returns True when the opposite side must be aligned."""
    edited_type = out.hr_type[key] if edited == "R" else out.hl_type[key]
    if break_tangent or edited_type in ("FREE", "VECTOR"):
        out.hl_type[key] = out.hr_type[key] = "FREE"   # both FREE: Blender must not re-align either side
        return False
    out.hl_type[key] = out.hr_type[key] = "ALIGNED"
    return True


def arc_drag(model: ChannelModel, frame: float, delta: float, break_tangent: bool = False):
    """Move the value at an in-between ``frame`` by ``delta`` editing only the two inner handle values
    of its segment (minimum-norm solution, exact). Keys and every x stay put.

    Returns (new_model, reason): reason is '' on success, else why the channel cannot be edited (the
    model is then returned unchanged).
    """
    from . import bezier   # local: bezier imports fcurve_model only

    k = model.segment_of(frame)
    if k is None:
        return model, "fora do intervalo de keys"
    if model.key_index(frame, eps=bezier.EXACT_KEY_THRESHOLD) is not None:
        return model, "é um key point (use grab)"
    ipo = model.interp[k]
    if ipo != "BEZIER":
        return model, f"segmento {ipo}"
    if delta == 0.0:
        return model.copy(), ""
    t, found = bezier.segment_t(model, k, [frame])
    if not found[0]:
        return model, "segmento sem solução em t"
    _v2, _v3, fac1, fac2 = bezier.correct_bezpart(model.co[k], model.hr[k], model.hl[k + 1], model.co[k + 1])
    b = bezier.bernstein(float(t[0]))
    a1 = float(b[1]) * float(fac1)        # ∂value/∂(right handle y of key k)
    a2 = float(b[2]) * float(fac2)        # ∂value/∂(left handle y of key k+1)
    denom = a1 * a1 + a2 * a2
    if denom < 1e-12:
        return model, "ponto colado no key"
    out = model.copy()
    out.hr[k, 1] += delta * a1 / denom
    out.hl[k + 1, 1] += delta * a2 / denom
    if _set_types(out, k, "R", break_tangent):
        _align_opposite(out, k, "R")
    if _set_types(out, k + 1, "L", break_tangent):
        _align_opposite(out, k + 1, "L")
    return out, ""
