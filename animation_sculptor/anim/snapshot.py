# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapshot/restore of F-Curves for cancelling a gesture (Esc/RMB). Undo stays with Blender.

Restore is bit for bit (invariant 5): values are written verbatim, F-Curves created during the
gesture are removed, keys inserted during the gesture disappear.
"""

from . import action_io


class Snapshot:
    def __init__(self, ob):
        self.ob = ob
        self._channels = {}       # (data_path, index) -> ChannelModel, or None when the curve did not exist

    def capture(self, data_path, index):
        key = (data_path, index)
        if key in self._channels:
            return
        cb = action_io.channelbag(self.ob)
        fc = cb.fcurves.find(data_path, index=index) if cb is not None else None
        self._channels[key] = None if fc is None else action_io.read_channel(fc)

    def capture_fcurve(self, fc):
        self.capture(fc.data_path, fc.array_index)

    def restore(self):
        cb = action_io.channelbag(self.ob)
        if cb is None:
            return
        for (path, index), model in self._channels.items():
            fc = cb.fcurves.find(path, index=index)
            if model is None:
                if fc is not None:
                    cb.fcurves.remove(fc)
            elif fc is not None:
                action_io.write_channel(fc, model, update=False)
        action_io.tag(self.ob)
