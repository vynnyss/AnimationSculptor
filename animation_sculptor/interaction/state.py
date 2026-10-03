# SPDX-License-Identifier: GPL-3.0-or-later
"""Transient interaction state (derived, never saved: dropped on file load / undo)."""

HOVER = None      # picking.Hit under the mouse, or None
GESTURE = None    # dict describing the running gesture (for the overlay), or None
MESSAGE = ""      # last refusal / info message shown in the header and overlay
STATS = {}        # profiling counters (e.g. last_move_ms)


def reset():
    global HOVER, GESTURE, MESSAGE
    HOVER = None
    GESTURE = None
    MESSAGE = ""
