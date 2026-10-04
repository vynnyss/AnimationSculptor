# SPDX-License-Identifier: GPL-3.0-or-later
"""Rig adapters (ADR 0002). The only package allowed to know bone names."""

from . import generic, rigify  # noqa: F401  (register the adapters)
from .adapter import BODY, LIMB, TIP, clear_cache, get_adapter  # noqa: F401
from .concepts import ROTATION, TRANSLATION, ControlInfo  # noqa: F401
