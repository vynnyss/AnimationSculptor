# SPDX-License-Identifier: GPL-3.0-or-later
"""Transient interaction state (derived, never saved: dropped on file load / undo)."""

HOVER = None      # picking.Hit under the mouse, or None
GESTURE = None    # dict describing the running gesture (for the overlay), or None
MESSAGE = ""      # last refusal / info message shown in the header and overlay
STATS = {}        # profiling counters (e.g. last_move_ms)
REFUSAL = None    # {"world", "frame", "bone", "reason"} of the last refused point (drawn in red)
RULER_HOVER = None  # 'PAST' / 'FUTURE' end handle of the time ruler under the mouse, or None
RULER_DRAG = None   # end handle being dragged by asc.time_window, or None
LAST_TOOL = None    # last Animation Sculptor tool used (Shift+Alt+K)
RULER_SPAN = 0      # frozen half span (frames) of the ruler while a handle is dragged; 0 = automatic


def reset():
    global HOVER, GESTURE, MESSAGE, REFUSAL, RULER_HOVER, RULER_DRAG, RULER_SPAN
    HOVER = None
    RULER_HOVER = None
    RULER_DRAG = None
    RULER_SPAN = 0
    GESTURE = None
    MESSAGE = ""
    REFUSAL = None
