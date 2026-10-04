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
