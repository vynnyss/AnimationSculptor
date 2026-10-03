# SPDX-License-Identifier: GPL-3.0-or-later
"""Project-level unit tests: run with plain Python, no Blender."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import checks  # noqa: E402


def test_core_imports_without_blender():
    assert "bpy" not in sys.modules
    core = importlib.import_module("animation_sculptor.core")
    assert core.__name__ == "animation_sculptor.core"
    assert "bpy" not in sys.modules, "importing the package/core must not import bpy (ADR 0008)"


def test_package_exposes_register_unregister():
    pkg = importlib.import_module("animation_sculptor")
    assert callable(pkg.register)
    assert callable(pkg.unregister)


def test_core_has_no_blender_imports():
    assert checks.check_core_has_no_blender_imports() == []


def test_no_bone_names_outside_rig():
    assert checks.check_no_bone_names_outside_rig() == []


def test_manifest():
    assert checks.check_manifest() == []


def test_markdown_links():
    assert checks.check_markdown_links() == []


def test_core_import_rule_detects_violation(tmp_path, monkeypatch):
    """The checker itself must catch a forbidden import."""
    pkg = tmp_path / "animation_sculptor" / "core"
    pkg.mkdir(parents=True)
    (pkg / "bad.py").write_text("import mathutils\nfrom bpy import types\n", encoding="utf-8")
    monkeypatch.setattr(checks, "ROOT", tmp_path)
    monkeypatch.setattr(checks, "PKG", tmp_path / "animation_sculptor")
    errors = checks.check_core_has_no_blender_imports()
    assert len(errors) == 2


def test_bone_rule_detects_violation(tmp_path, monkeypatch):
    pkg = tmp_path / "animation_sculptor"
    (pkg / "interaction").mkdir(parents=True)
    (pkg / "rig").mkdir()
    (pkg / "interaction" / "tool.py").write_text('BONE = "hand_ik.L"\n', encoding="utf-8")
    (pkg / "rig" / "rigify.py").write_text('BONE = "hand_ik.L"\n', encoding="utf-8")
    monkeypatch.setattr(checks, "ROOT", tmp_path)
    monkeypatch.setattr(checks, "PKG", pkg)
    errors = checks.check_no_bone_names_outside_rig()
    assert len(errors) == 1 and "interaction" in errors[0]
