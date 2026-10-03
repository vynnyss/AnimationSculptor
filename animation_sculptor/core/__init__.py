# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure core of Animation Sculptor (ADR 0008).

Rules: no ``bpy`` and no ``mathutils`` imports anywhere in this package. Data in
and out is plain Python / numpy. Enforced by ``scripts/checks.py``.
"""
