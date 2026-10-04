# SPDX-License-Identifier: GPL-3.0-or-later
"""UI scenario runner, executed inside a *windowed* Blender started by ``python scripts/dev.py test ui``.

Blender runs with ``--enable-event-simulate`` (real input is ignored; ``Window.event_simulate`` feeds
mouse/keyboard events), ``--factory-startup`` and the isolated test profile. Each ``scenario_*.py``
module defines ``scenario(h)``, a generator that yields delays (seconds) so the event loop can process
the simulated events between steps. Results go to ``$ASC_UI_RESULTS`` (JSON) and the exit code.

Needs a display: local only (not part of the CI).
"""

import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
RESULTS = os.environ.get("ASC_UI_RESULTS", str(HERE / "results.json"))
SHOTS = Path(os.environ.get("ASC_UI_SHOTS", str(HERE / "shots")))
FILTER = os.environ.get("ASC_UI_FILTER", "")

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "blender"))


class Helper:
    """Small API for scenarios: window/area lookup, event simulation, checks, screenshots."""

    def __init__(self, name):
        self.name = name
        self.checks = []

    # -- context ------------------------------------------------------------------------------
    @property
    def window(self):
        return bpy.context.window_manager.windows[0]

    def view3d(self):
        best = None
        for area in self.window.screen.areas:
            if area.type == 'VIEW_3D' and (best is None or area.width * area.height > best.width * best.height):
                best = area
        region = next(r for r in best.regions if r.type == 'WINDOW')
        return best, region, best.spaces.active.region_3d

    def override(self, **extra):
        area, region, _rv3d = self.view3d()
        kw = dict(window=self.window, screen=self.window.screen, area=area, region=region)
        kw.update(extra)
        return bpy.context.temp_override(**kw)

    def addon(self, sub=""):
        name = os.environ.get("ASC_ADDON_MODULE", "bl_ext.user_default.animation_sculptor")
        return importlib.import_module(name + ("." + sub if sub else ""))

    # -- events -------------------------------------------------------------------------------
    def to_window(self, region_co):
        _area, region, _rv3d = self.view3d()
        return int(round(region.x + region_co[0])), int(round(region.y + region_co[1]))

    def event(self, type, value='NOTHING', co=None, **mods):
        x, y = co if co is not None else (0, 0)
        self.window.event_simulate(type, value, x=x, y=y, **mods)

    def move(self, co, **mods):
        self.event('MOUSEMOVE', 'NOTHING', co, **mods)

    # -- results ------------------------------------------------------------------------------
    def check(self, label, ok, detail=""):
        self.checks.append({"label": label, "ok": bool(ok), "detail": str(detail)})
        print(f"[ui] {'PASS' if ok else 'FAIL'} {self.name}: {label} {detail}")

    def screenshot(self, label):
        SHOTS.mkdir(parents=True, exist_ok=True)
        area, _region, _rv3d = self.view3d()
        path = SHOTS / f"{self.name}-{label}.png"
        with self.override():
            bpy.ops.screen.screenshot_area(filepath=str(path))
        return path


def _load_scenarios():
    out = []
    for path in sorted(HERE.glob("scenario_*.py")):
        if FILTER and FILTER not in path.stem:
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        out.append((path.stem, module.scenario))
    return out


_queue = []
_results = []
_current = {"gen": None, "helper": None}


def _finish():
    total = [c for r in _results for c in r["checks"]]
    failed = [c for c in total if not c["ok"]]
    Path(RESULTS).write_text(json.dumps({"scenarios": _results}, indent=2), encoding="utf-8")
    print(f"[ui] {len(total) - len(failed)} passed, {len(failed)} failed -> {RESULTS}")
    sys.stdout.flush()
    os._exit(1 if failed or not total else 0)


def _tick():
    try:
        if _current["gen"] is None:
            if not _queue:
                _finish()
                return None
            name, scenario = _queue.pop(0)
            helper = Helper(name)
            _current["helper"] = helper
            _current["gen"] = scenario(helper)
            _results.append({"name": name, "checks": helper.checks})
        try:
            delay = next(_current["gen"])
        except StopIteration:
            _current["gen"] = None
            delay = 0.2
        return float(delay if delay is not None else 0.1)
    except Exception:
        traceback.print_exc()
        helper = _current["helper"]
        if helper is not None:
            helper.check("scenario raised", False, traceback.format_exc(limit=3))
        _current["gen"] = None
        return 0.2


def main():
    bpy.context.preferences.view.show_splash = False
    # Rigify rigs carry rig_ui.py; without auto-exec Blender shows a blocking popup on load
    bpy.context.preferences.filepaths.use_scripts_auto_execute = True
    _queue.extend(_load_scenarios())
    bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)


main()
