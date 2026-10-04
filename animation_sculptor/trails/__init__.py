# SPDX-License-Identifier: GPL-3.0-or-later
"""Motion trails: vendored Live Motion Path engine (``lmp``) behind ``provider``."""

from . import lmp


def register():
    lmp.register()


def unregister():
    lmp.unregister()
