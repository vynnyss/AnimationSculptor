# Third-party notices

Animation Sculptor is licensed under GPL-3.0-or-later.

## Live Motion Path & Onion Skin

- Authors: Experience Elysian (copyright "2026 Experience Elysian")
- License: GPL-3.0-or-later
- Source: https://github.com/daim1993/blender-live-motion-path
- Vendored from commit `0e173fd`
- Location in this extension: `animation_sculptor/trails/lmp/`
  (`engine.py`, `draw.py`, `compat.py`, `handlers.py`, `props.py`, `ops.py`, `ui.py`, `__init__.py`)

This code is **modified** for Animation Sculptor (namespace rename, suspend/resume hooks,
restoration of motion-path settings, UI integration). Original file headers are preserved and
each change is marked `# ASC-PATCH Pn` in the source. The list of changes is in
`docs/reference/open-source-provenance.md` in the project repository.

## Blender (algorithms ported)

- Authors: Blender Foundation and Blender authors
- License: GPL-2.0-or-later
- Source: https://projects.blender.org/blender/blender (`source/blender/blenkernel/intern/fcurve.cc`, Blender 5.2)
- Location in this extension: `animation_sculptor/core/bezier.py`

The F-Curve evaluation algorithms (keyframe search, extrapolation, handle correction, Bezier
root finding) are ported to numpy so the result matches `FCurve.evaluate` bit for bit.
`animation_sculptor/anim/action_io.py` also adapts the channelbag access of the Live Motion
Path code listed above.

When more code is vendored or ported, list it here (project, authors, license, link) and in
`docs/reference/open-source-provenance.md`.
