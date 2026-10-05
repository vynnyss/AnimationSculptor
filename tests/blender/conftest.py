# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
from pathlib import Path

import bpy
import pytest

ADDON_MODULE = os.environ.get("ASC_ADDON_MODULE", "bl_ext.user_default.animation_sculptor")
REPO_ROOT = Path(os.environ.get("ASC_REPO_ROOT", Path(__file__).resolve().parents[2]))
ATTACK_ASSET = Path(os.environ.get("ASC_TEST_ASSET", REPO_ROOT / "tests" / "assets" / "local" / "attack_test.blend"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_rig as public_rig_module  # noqa: E402


@pytest.fixture
def addon_module():
    return ADDON_MODULE


@pytest.fixture
def addon():
    """The installed add-on package (``bl_ext.user_default.animation_sculptor``)."""
    import importlib

    return importlib.import_module(ADDON_MODULE)


@pytest.fixture(scope="session")
def public_rig_path(tmp_path_factory):
    """Rigify rig generated once per session (see ``public_rig.py``); runs on CI."""
    path = tmp_path_factory.mktemp("assets") / "rigify_public.blend"
    public_rig_module.generate(str(path))
    return path


@pytest.fixture
def public_rig(public_rig_path):
    """Fresh copy of the public rig scene; returns the rig object."""
    bpy.ops.wm.open_mainfile(filepath=str(public_rig_path), load_ui=False)
    return bpy.data.objects[public_rig_module.RIG_NAME]


@pytest.fixture
def attack_rig():
    """The user's local attack asset (skips when not generated: ``python scripts/dev.py assets``)."""
    if not ATTACK_ASSET.exists():
        pytest.skip(f"{ATTACK_ASSET.name} not generated (python scripts/dev.py assets)")
    bpy.ops.wm.open_mainfile(filepath=str(ATTACK_ASSET), load_ui=False)
    scene = bpy.context.scene
    return bpy.data.objects[scene["asc_asset_rig"]]


@pytest.fixture
def simple_rig():
    """The simple skeleton of ADR 0014 (same bones as scripts/make_basic_rig.py, unsnapped) on a skinned test
    body, with the small test Action — CI-friendly stand-in for the local Vale (``basic_rig``)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import make_basic_rig
    import body_mesh

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    rig = make_basic_rig.create_rig(scene, make_basic_rig.bone_table())
    body_mesh.add_skinned_body(rig)
    make_basic_rig.add_test_action(rig, scene)
    bpy.context.view_layer.objects.active = rig
    return rig


BASIC_ASSET = Path(os.environ.get("ASC_BASIC_ASSET", REPO_ROOT / "tests" / "assets" / "local" / "basic_rig_test.blend"))


@pytest.fixture
def basic_rig():
    """The maintainer's Vale on the simple skeleton (local: ``python scripts/dev.py basic-rig``)."""
    if not BASIC_ASSET.exists():
        pytest.skip(f"{BASIC_ASSET.name} not generated (python scripts/dev.py basic-rig)")
    bpy.ops.wm.open_mainfile(filepath=str(BASIC_ASSET), load_ui=False)
    return bpy.data.objects[bpy.context.scene["asc_asset_rig"]]
