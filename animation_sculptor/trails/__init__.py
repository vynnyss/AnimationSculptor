# SPDX-License-Identifier: GPL-3.0-or-later
"""Motion trails: vendored Live Motion Path engine (``lmp``) behind ``provider``."""

from . import lmp


def register():
    lmp.register()
    from . import provider

    provider.use_adapter_bone_points(True)
    provider.use_body_targets(True)


def unregister():
    from . import provider

    provider.use_adapter_bone_points(False)
    provider.use_body_targets(False)
    lmp.unregister()
