#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
"""Development entry point for Animation Sculptor.

Commands:
  link / unlink        install the working tree into your Blender 5.2 as an extension (junction/symlink)
  test unit            pytest in tests/unit with this Python (no Blender)
  test blender [args]  pytest inside Blender --background, isolated user profile
  test all             unit + blender
  test ui [filter]     windowed Blender driven by simulated events (tests/ui; needs a display, local only)
  build                build the extension zip into dist/
  validate             static checks (+ `blender --command extension validate` when Blender is available)
  fetch-blender        (CI, Linux) download the latest Blender 5.2.x into .blender/ and print its path
  assets [--preview]   generate tests/assets/local/attack_test.blend from your Rigify character
  basic-rig            rig a plain mesh with the simple skeleton (copy next to it + tests/assets/local/basic_rig_test.blend)
                       (optionally render the key poses to tests/assets/local/preview/)

Blender is located from (in order): $BLENDER_EXE, scripts/.dev.toml (`blender = '...'`),
the default Windows install path, `blender` on PATH.

The test character (never committed: the repository is public) is located from $ASC_TEST_CHARACTER,
then scripts/.dev.toml (`character = '...'`). Tests that need generated assets skip when they are missing.

Structure adapted from j10er/BlenderAddonTemplate (GPL-3.0): see docs/reference/open-source-provenance.md.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT / "animation_sculptor"
ADDON_ID = "animation_sculptor"
EXT_REPO = "user_default"
ADDON_MODULE = f"bl_ext.{EXT_REPO}.{ADDON_ID}"
BLENDER_SERIES = "5.2"
TEST_PROFILE = ROOT / ".blender_test_profile"
PYDEPS = TEST_PROFILE / "pydeps"
DIST = ROOT / "dist"
LOCAL_ASSETS = ROOT / "tests" / "assets" / "local"
ATTACK_ASSET = LOCAL_ASSETS / "attack_test.blend"
BASIC_ASSET = LOCAL_ASSETS / "basic_rig_test.blend"     # simple skeleton (ADR 0014), from make_basic_rig.py
IS_WINDOWS = os.name == "nt"


def log(msg: str) -> None:
    print(f"[dev] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Blender discovery
# ---------------------------------------------------------------------------

def _config() -> dict:
    path = ROOT / "scripts" / ".dev.toml"
    if path.exists():
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return {}


def find_blender(required: bool = True) -> str | None:
    candidates = [os.environ.get("BLENDER_EXE"), _config().get("blender")]
    if IS_WINDOWS:
        candidates.append(rf"C:\Program Files\Blender Foundation\Blender {BLENDER_SERIES}\blender.exe")
    candidates.append(shutil.which("blender"))
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    if required:
        sys.exit(
            "[dev] Blender 5.2 not found. Set BLENDER_EXE or create scripts/.dev.toml with:\n"
            "      blender = 'C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe'"
        )
    return None


def find_character() -> str | None:
    for candidate in (os.environ.get("ASC_TEST_CHARACTER"), _config().get("character")):
        if candidate and Path(candidate).exists():
            return str(Path(candidate).resolve())
    return None


def blender_eval(blender: str, expr: str, env: dict | None = None) -> str:
    """Evaluate a Python expression in background Blender and return str(result)."""
    code = f"import sys; sys.stdout.write('\\nASC::' + str({expr}) + '\\n'); sys.stdout.flush()"
    proc = subprocess.run(
        [blender, "--background", "--factory-startup", "--python-expr", code],
        capture_output=True, text=True, env=env,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("ASC::"):
            return line[5:]
    sys.exit(f"[dev] Blender evaluation failed ({expr}).\n{proc.stdout}\n{proc.stderr}")


def check_blender_version(blender: str, env: dict | None = None) -> None:
    version = blender_eval(blender, "'.'.join(map(str, __import__('bpy').app.version))", env)
    major_minor = ".".join(version.split(".")[:2])
    if major_minor != BLENDER_SERIES:
        sys.exit(f"[dev] Blender {version} found at {blender}; Animation Sculptor targets {BLENDER_SERIES}.")
    log(f"Blender {version}: {blender}")


# ---------------------------------------------------------------------------
# Links (junction on Windows, symlink elsewhere)
# ---------------------------------------------------------------------------

def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    if hasattr(os.path, "isjunction") and os.path.isjunction(path):
        return True
    if IS_WINDOWS and path.exists():
        attrs = getattr(os.lstat(path), "st_file_attributes", 0)
        return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    return False


def remove_link(path: Path) -> bool:
    if not (path.exists() or path.is_symlink()):
        return False
    if not _is_link(path):
        sys.exit(f"[dev] {path} exists and is not a link; refusing to touch it. Remove it manually.")
    if IS_WINDOWS and path.is_dir():
        os.rmdir(path)  # removes the junction only, never the target
    else:
        path.unlink()
    return True


def make_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    remove_link(link)
    if IS_WINDOWS:
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


def extensions_dir(blender: str, env: dict | None = None) -> Path:
    expr = f"__import__('bpy').utils.user_resource('EXTENSIONS', path='{EXT_REPO}', create=True)"
    return Path(blender_eval(blender, expr, env))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_link(_args) -> None:
    blender = find_blender()
    check_blender_version(blender)
    link = extensions_dir(blender) / ADDON_ID
    make_link(link, PKG_DIR)
    log(f"linked {link} -> {PKG_DIR}")
    log("Restart Blender, then enable 'Animation Sculptor' in Edit > Preferences > Add-ons.")
    log("After code changes: F3 > 'Reload Scripts'.")


def cmd_unlink(_args) -> None:
    blender = find_blender()
    link = extensions_dir(blender) / ADDON_ID
    log(f"removed {link}" if remove_link(link) else f"nothing linked at {link}")


def _run(cmd: list[str], env: dict | None = None) -> int:
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, env=env).returncode


def test_unit(extra: list[str]) -> int:
    return _run([sys.executable, "-m", "pytest", str(ROOT / "tests" / "unit"), *extra])


def _ensure_pydeps() -> None:
    marker = PYDEPS / "pytest"
    if marker.exists():
        return
    log(f"installing pytest for Blender into {PYDEPS} (pure Python, one time)")
    PYDEPS.mkdir(parents=True, exist_ok=True)
    code = _run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(PYDEPS), "pytest"])
    if code != 0:
        sys.exit("[dev] could not install pytest into the test profile")


def test_blender(extra: list[str]) -> int:
    blender = find_blender()
    env = dict(os.environ)
    env["BLENDER_USER_RESOURCES"] = str(TEST_PROFILE)
    env["ASC_PYDEPS"] = str(PYDEPS)
    env["ASC_ADDON_MODULE"] = ADDON_MODULE
    env["ASC_REPO_ROOT"] = str(ROOT)
    env["ASC_TEST_ASSET"] = str(ATTACK_ASSET)
    character = find_character()
    if character:
        env["ASC_TEST_CHARACTER"] = character
    TEST_PROFILE.mkdir(exist_ok=True)
    check_blender_version(blender, env)
    _ensure_pydeps()
    link = extensions_dir(blender, env) / ADDON_ID
    make_link(link, PKG_DIR)
    log(f"test profile: {TEST_PROFILE}  (extension linked at {link})")
    return _run([
        blender, "--background", "--factory-startup", "--python-exit-code", "1",
        "--python", str(ROOT / "tests" / "blender" / "run.py"), "--", *extra,
    ], env=env)


UI_DIR = TEST_PROFILE / "ui"


def test_ui(extra: list[str]) -> int:
    """Run tests/ui scenarios in a windowed Blender with --enable-event-simulate."""
    blender = find_blender()
    env = dict(os.environ)
    env["BLENDER_USER_RESOURCES"] = str(TEST_PROFILE)
    env["ASC_ADDON_MODULE"] = ADDON_MODULE
    env["ASC_REPO_ROOT"] = str(ROOT)
    TEST_PROFILE.mkdir(exist_ok=True)
    check_blender_version(blender, env)
    link = extensions_dir(blender, env) / ADDON_ID
    make_link(link, PKG_DIR)
    UI_DIR.mkdir(parents=True, exist_ok=True)
    rig = UI_DIR / "rigify_public.blend"
    code = _run([blender, "--background", "--factory-startup", "--python-exit-code", "1",
                 "--python", str(ROOT / "tests" / "blender" / "public_rig.py"), "--", str(rig)], env=env)
    if code != 0:
        return code
    env["ASC_UI_RIG"] = str(rig)
    env["ASC_UI_RESULTS"] = str(UI_DIR / "results.json")
    env["ASC_UI_SHOTS"] = str(UI_DIR / "shots")
    env["ASC_UI_FILTER"] = extra[0] if extra else ""
    log(f"UI scenarios: screenshots in {UI_DIR / 'shots'}")
    return _run([blender, "--factory-startup", "--enable-event-simulate", "--addons", ADDON_MODULE,
                 "--python", str(ROOT / "tests" / "ui" / "run_ui.py")], env=env)


def cmd_test(args) -> None:
    extra = args.pytest_args
    if args.suite == "unit":
        code = test_unit(extra)
    elif args.suite == "blender":
        code = test_blender(extra)
    elif args.suite == "ui":
        code = test_ui(extra)
    else:
        code = test_unit([])
        if code == 0:
            code = test_blender([])
    sys.exit(code)


def cmd_build(_args) -> None:
    blender = find_blender()
    check_blender_version(blender)
    DIST.mkdir(exist_ok=True)
    code = _run([blender, "--command", "extension", "build", "--source-dir", str(PKG_DIR), "--output-dir", str(DIST)])
    sys.exit(code)


def cmd_validate(_args) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import checks

    problems = checks.run_all()
    for problem in problems:
        print(problem)
    log(f"static checks: {len(problems)} problem(s)")
    code = 1 if problems else 0
    blender = find_blender(required=False)
    if blender:
        code |= _run([blender, "--command", "extension", "validate", str(PKG_DIR)])
    else:
        log("Blender not found: skipped `extension validate`")
    sys.exit(code)


def cmd_assets(args) -> None:
    blender = find_blender()
    check_blender_version(blender)
    character = find_character()
    if not character:
        sys.exit(
            "[dev] test character not found. Set ASC_TEST_CHARACTER or add to scripts/.dev.toml:\n"
            "      character = 'D:\\path\\to\\character.blend'"
        )
    if Path(character).resolve() == ATTACK_ASSET.resolve():
        sys.exit("[dev] the character and the generated asset must be different files")
    cmd = [
        blender, "--background", character, "--factory-startup", "--python-exit-code", "1",
        "--python", str(ROOT / "scripts" / "make_test_assets.py"), "--", "--output", str(ATTACK_ASSET),
    ]
    if args.preview:
        cmd += ["--preview", str(LOCAL_ASSETS / "preview")]
    sys.exit(_run(cmd))


def find_basic_character() -> str | None:
    for candidate in (os.environ.get("ASC_BASIC_CHARACTER"), _config().get("basic_character")):
        if candidate and Path(candidate).exists():
            return str(Path(candidate).resolve())
    return None


def cmd_basic_rig(args) -> None:
    """Rig the plain mesh with the simple skeleton: a rigged copy next to it (never the source itself) and
    the test asset tests/assets/local/basic_rig_test.blend (with a small Action)."""
    blender = find_blender()
    check_blender_version(blender)
    source = args.source or find_basic_character()
    if not source:
        sys.exit("[dev] plain mesh not found. Pass --source or add to scripts/.dev.toml:\n"
                 "      basic_character = 'D:\\path\\to\\mesh.blend'")
    src = Path(source).resolve()
    output = Path(args.output).resolve() if args.output else src.with_name(
        src.stem.replace("_mesh", "") + "_rigged.blend")
    if output == src or BASIC_ASSET.resolve() == src:
        sys.exit("[dev] the source and the generated files must be different files")
    LOCAL_ASSETS.mkdir(parents=True, exist_ok=True)
    sys.exit(_run([blender, "--background", str(src), "--factory-startup", "--python-exit-code", "1",
                   "--python", str(ROOT / "scripts" / "make_basic_rig.py"), "--",
                   "--output", str(output), "--test-output", str(BASIC_ASSET)]))


def cmd_fetch_blender(_args) -> None:
    if IS_WINDOWS:
        sys.exit("[dev] fetch-blender is for Linux CI")
    base = f"https://download.blender.org/release/Blender{BLENDER_SERIES}/"
    headers = {"User-Agent": "Mozilla/5.0 (animation-sculptor CI)"}
    listing = urllib.request.urlopen(urllib.request.Request(base, headers=headers), timeout=60).read().decode()
    patches = sorted({int(m) for m in re.findall(rf"blender-{re.escape(BLENDER_SERIES)}\.(\d+)-linux-x64\.tar\.xz", listing)})
    if not patches:
        sys.exit(f"[dev] no Linux build found at {base}")
    name = f"blender-{BLENDER_SERIES}.{patches[-1]}-linux-x64"
    dest = ROOT / ".blender"
    exe = dest / name / "blender"
    if not exe.exists():
        dest.mkdir(exist_ok=True)
        archive = dest / f"{name}.tar.xz"
        log(f"downloading {base}{name}.tar.xz")
        with urllib.request.urlopen(urllib.request.Request(base + archive.name, headers=headers), timeout=600) as resp, open(archive, "wb") as out:
            shutil.copyfileobj(resp, out)
        with tarfile.open(archive) as tar:
            tar.extractall(dest, filter="data")
        archive.unlink()
    if not exe.exists():
        sys.exit(f"[dev] download finished but {exe} is missing")
    print(exe)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("link").set_defaults(func=cmd_link)
    sub.add_parser("unlink").set_defaults(func=cmd_unlink)
    p_test = sub.add_parser("test")
    p_test.add_argument("suite", choices=["unit", "blender", "ui", "all"])
    p_test.add_argument("pytest_args", nargs=argparse.REMAINDER, help="extra pytest arguments")
    p_test.set_defaults(func=cmd_test)
    sub.add_parser("build").set_defaults(func=cmd_build)
    sub.add_parser("validate").set_defaults(func=cmd_validate)
    sub.add_parser("fetch-blender").set_defaults(func=cmd_fetch_blender)
    p_basic = sub.add_parser("basic-rig")
    p_basic.add_argument("--source", default=None, help="plain mesh .blend (default: basic_character)")
    p_basic.add_argument("--output", default=None, help="rigged copy (default: <source>_rigged.blend)")
    p_basic.set_defaults(func=cmd_basic_rig)
    p_assets = sub.add_parser("assets")
    p_assets.add_argument("--preview", action="store_true", help="also render the key poses to PNG")
    p_assets.set_defaults(func=cmd_assets)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
