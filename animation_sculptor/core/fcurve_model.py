# SPDX-License-Identifier: GPL-3.0-or-later
"""In-memory model of one F-Curve channel (pure numpy, no bpy — ADR 0008).

Round trip with a Blender F-Curve is lossless for what Animation Sculptor edits: key/handle coordinates,
handle types, interpolation per key and the curve's extrapolation. ``anim/action_io`` converts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

HANDLE_TYPES = ("FREE", "ALIGNED", "VECTOR", "AUTO", "AUTO_CLAMPED")
INTERPOLATIONS = ("CONSTANT", "LINEAR", "BEZIER")   # easing presets (SINE, BACK…) are not modelled
EXTRAPOLATIONS = ("CONSTANT", "LINEAR")


@dataclass
class ChannelModel:
    """One F-Curve. Arrays have one row per key, sorted by frame."""

    co: np.ndarray                  # float64 (K, 2): (frame, value)
    hl: np.ndarray                  # float64 (K, 2): left handles
    hr: np.ndarray                  # float64 (K, 2): right handles
    hl_type: list = field(default_factory=list)   # K handle type names
    hr_type: list = field(default_factory=list)
    interp: list = field(default_factory=list)    # K interpolation names (segment k → k+1 uses interp[k])
    extrapolation: str = "CONSTANT"
    data_path: str = ""
    index: int = 0

    def __post_init__(self):
        self.co = np.asarray(self.co, dtype=np.float64).reshape(-1, 2)
        self.hl = np.asarray(self.hl, dtype=np.float64).reshape(-1, 2)
        self.hr = np.asarray(self.hr, dtype=np.float64).reshape(-1, 2)
        k = len(self.co)
        if not self.hl_type:
            self.hl_type = ["AUTO_CLAMPED"] * k
        if not self.hr_type:
            self.hr_type = ["AUTO_CLAMPED"] * k
        if not self.interp:
            self.interp = ["BEZIER"] * k
        if not (len(self.hl) == len(self.hr) == len(self.hl_type) == len(self.hr_type) == len(self.interp) == k):
            raise ValueError("ChannelModel arrays must have one entry per key")

    @property
    def key_count(self) -> int:
        return len(self.co)

    @property
    def frames(self) -> np.ndarray:
        return self.co[:, 0]

    @property
    def values(self) -> np.ndarray:
        return self.co[:, 1]

    def copy(self) -> "ChannelModel":
        return ChannelModel(self.co.copy(), self.hl.copy(), self.hr.copy(), list(self.hl_type),
                            list(self.hr_type), list(self.interp), self.extrapolation, self.data_path, self.index)

    def same_as(self, other: "ChannelModel") -> bool:
        """Bit-for-bit equality (cancel/restore invariant)."""
        return (np.array_equal(self.co, other.co) and np.array_equal(self.hl, other.hl)
                and np.array_equal(self.hr, other.hr) and self.hl_type == other.hl_type
                and self.hr_type == other.hr_type and self.interp == other.interp
                and self.extrapolation == other.extrapolation)

    def key_index(self, frame: float, eps: float = 1e-3) -> int | None:
        """Index of the key at ``frame`` (± eps) or None."""
        if self.key_count == 0:
            return None
        d = np.abs(self.co[:, 0] - frame)
        i = int(np.argmin(d))
        return i if d[i] < eps else None

    def segment_of(self, frame: float) -> int | None:
        """Index k of the segment [key k, key k+1] that contains ``frame`` (None outside the keys)."""
        x = self.co[:, 0]
        if self.key_count < 2 or frame < x[0] or frame > x[-1]:
            return None
        k = int(np.searchsorted(x, frame, side="right") - 1)
        return min(k, self.key_count - 2)
