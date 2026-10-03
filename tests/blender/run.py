# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point executed *inside* Blender by ``scripts/dev.py test blender``.

Blender is started with --background --factory-startup and an isolated
BLENDER_USER_RESOURCES profile where the working tree is linked as the
``user_default`` extension. This script enables the add-on, then runs pytest.
"""

import os
import sys

pydeps = os.environ.get("ASC_PYDEPS")
if pydeps:
    sys.path.insert(0, pydeps)

repo_root = os.environ.get("ASC_REPO_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
module = os.environ.get("ASC_ADDON_MODULE", "bl_ext.user_default.animation_sculptor")

import addon_utils  # noqa: E402
import pytest  # noqa: E402


def _raise(exc):
    raise exc


addon_utils.enable(module, default_set=True, handle_error=_raise)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
code = pytest.main([
    os.path.join(repo_root, "tests", "blender"),
    "-p", "no:cacheprovider",
    "--rootdir", repo_root,
    *argv,
])
sys.exit(int(code))
