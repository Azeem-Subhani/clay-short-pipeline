"""Try every dressing theme: build it in a plain shell, audit it, render the wide and the plan, and print one line each.

    py -3 tools/tests/sets/run_themes.py [--out <dir>] [theme ...]

Needs Blender (tools/common.py finds it). The audit may block: these are probes of the recipes, not finished sets; what
matters is that every recipe builds and what its wide view measures. Writes <out>/<theme>/{wide,plan,audit.json}.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from common import blender_cmd  # noqa: E402

ALL = ["great_hall", "castle_kitchen", "tavern", "peasant_cottage", "office_private", "home_living_room", "home_kitchen", "shop_interior",
       "market_street", "village_square", "army_camp", "battlefield", "city_street"]


def main():
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else ROOT / "output" / "set_probes"
    if "--out" in args:
        i = args.index("--out")
        args = args[:i] + args[i + 2:]
    themes = args or ALL
    bl = blender_cmd()
    rows = []
    for t in themes:
        d = out / t
        d.mkdir(parents=True, exist_ok=True)
        (d / "audit.json").unlink(missing_ok=True)                      # a failed build must not read as the last good one
        env = dict(os.environ, SK_THEME=t)
        cmd = [*bl, str(ROOT / "tools/blender/set_preview.py"), "--", "--set", str(HERE / "set_theme_probe.py"),
               "--out", str(d), "--views", "wide,plan"]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        a = d / "audit.json"
        if not a.exists():
            rows.append((t, "BUILD FAILED", r.stdout[-600:] + r.stderr[-600:]))
            continue
        j = json.loads(a.read_text(encoding="utf-8"))
        inv = j["inventory"]
        blocks = [i["code"] for i in j["issues"] if i["level"] == "block"]
        rows.append((t, f"types {inv['prop_types']:2d}  objects {inv['objects_visible']:3d}  layers {sum(1 for v in inv['layers'].values() if v)}/4  practicals {inv['practicals_visible']:2d}  details {inv['details']:2d}  tris {inv['triangles']:6d}  blocks: {', '.join(sorted(set(blocks))) or 'none'}", ""))
    for t, line, extra in rows:
        print(f"{t:18s} {line}")
        if extra:
            print(extra)


main()
