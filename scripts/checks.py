# SPDX-License-Identifier: GPL-3.0-or-later
"""Static project checks (no Blender needed).

Run via ``python scripts/dev.py validate``; also executed by ``tests/unit`` so CI
fails when a rule is broken. Each check returns a list of human-readable errors.
"""

from __future__ import annotations

import ast
import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "animation_sculptor"

# Modules that only exist inside Blender. ``core`` must not import any of them (ADR 0008).
BLENDER_ONLY_MODULES = {"bpy", "bpy_extras", "bpy_types", "mathutils", "bmesh", "gpu", "gpu_extras", "blf", "bgl", "aud", "idprop"}

# Rig-specific bone naming that must stay inside ``rig/`` (ADR 0002).
BONE_NAME_PATTERNS = [
    re.compile(r"""["']DEF-"""),
    re.compile(r"""["']ORG-"""),
    re.compile(r"""["']MCH-"""),
    re.compile(r"""_(?:fk|ik)\.[LR]\b"""),
]
BONE_NAME_ALLOWED_DIRS = ("rig", os.path.join("trails", "lmp"))

MIN_BLENDER = (5, 2, 0)


def _py_files(base: Path):
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def check_core_has_no_blender_imports() -> list[str]:
    errors = []
    core = PKG / "core"
    for path in _py_files(core):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in BLENDER_ONLY_MODULES:
                    rel = path.relative_to(ROOT).as_posix()
                    errors.append(f"{rel}:{node.lineno}: core must not import '{name}' (ADR 0008)")
    return errors


def check_no_bone_names_outside_rig() -> list[str]:
    errors = []
    for path in _py_files(PKG):
        rel_pkg = path.relative_to(PKG)
        if str(rel_pkg).startswith(BONE_NAME_ALLOWED_DIRS):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for pattern in BONE_NAME_PATTERNS:
                if pattern.search(line):
                    rel = path.relative_to(ROOT).as_posix()
                    errors.append(f"{rel}:{lineno}: rig bone name outside rig/ (ADR 0002): {line.strip()}")
                    break
    return errors


def _parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def check_manifest() -> list[str]:
    path = PKG / "blender_manifest.toml"
    if not path.exists():
        return [f"missing {path.relative_to(ROOT).as_posix()}"]
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    errors = []
    expected = {"schema_version": "1.0.0", "id": "animation_sculptor", "name": "Animation Sculptor", "type": "add-on"}
    for key, value in expected.items():
        if data.get(key) != value:
            errors.append(f"manifest: {key} should be {value!r}, got {data.get(key)!r}")
    try:
        if _parse_version(data.get("blender_version_min", "0")) < MIN_BLENDER:
            errors.append("manifest: blender_version_min must be >= 5.2.0 (ADR 0004)")
    except ValueError:
        errors.append("manifest: blender_version_min is not a version")
    if data.get("license") != ["SPDX:GPL-3.0-or-later"]:
        errors.append("manifest: license must be ['SPDX:GPL-3.0-or-later'] (ADR 0007)")
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(data.get("version", ""))):
        errors.append("manifest: version must be MAJOR.MINOR.PATCH")
    return errors


def _slug(heading: str) -> str:
    heading = re.sub(r"[^\w\- ]", "", heading.strip().lower(), flags=re.UNICODE)
    return heading.replace(" ", "-")


def check_markdown_links() -> list[str]:
    """Relative links and #anchors between Markdown files must resolve."""
    files = [p for p in ROOT.rglob("*.md") if not any(part.startswith(".") for part in p.relative_to(ROOT).parts)]
    headings = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        headings[path.resolve()] = {_slug(h) for h in re.findall(r"^#+\s+(.*)$", text, re.MULTILINE)}
    errors = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, anchor = target.partition("#")
            dest = (path.parent / file_part).resolve() if file_part else path.resolve()
            rel = path.relative_to(ROOT).as_posix()
            if not dest.exists():
                errors.append(f"{rel}: broken link -> {target}")
            elif anchor and dest.suffix == ".md" and anchor not in headings.get(dest, set()):
                errors.append(f"{rel}: missing anchor -> {target}")
    return errors


ALL_CHECKS = (
    check_core_has_no_blender_imports,
    check_no_bone_names_outside_rig,
    check_manifest,
    check_markdown_links,
)


def run_all() -> list[str]:
    errors = []
    for check in ALL_CHECKS:
        errors.extend(check())
    return errors


if __name__ == "__main__":
    problems = run_all()
    for problem in problems:
        print(problem)
    raise SystemExit(1 if problems else 0)
