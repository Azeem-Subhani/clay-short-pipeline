"""run_actions.py - run action_test3d.py over many characters in parallel and collect the results. Stdlib only.

    py -3 run_actions.py <out dir> [--set core|all] [--names A,B] [--workers 5] [--render walk,pick_up] [--view 3q --face right]
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(__file__).resolve().parents[1]
PIPE = (W / "clay-short-pipeline") if (W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[2]
import os
import shutil
BL = os.environ.get("BLENDER") or shutil.which("blender") or r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
a = sys.argv[1:]
def opt(name, default):
    if name in a:
        i = a.index(name)
        v = a[i + 1]
        del a[i:i + 2]
        return v
    return default
SET, NAMES, WORKERS, RENDER = opt("--set", "core"), opt("--names", ""), int(opt("--workers", "5")), opt("--render", "")
VIEW, FACE = opt("--view", "3q"), opt("--face", "right")
out = Path(a[0]).resolve()
out.mkdir(parents=True, exist_ok=True)
sheets = json.loads((PIPE / "config" / "cast3d.json").read_text(encoding="utf-8"))["characters"]
names = [n for n in NAMES.split(",") if n] or list(sheets)


def run(n):
    cmd = [BL, "-b", "--factory-startup", "--python", str(Path(__file__).with_name("action_test3d.py")), "--", "--char", n, "--out", str(out), "--set", SET,
           "--view", VIEW, "--face", FACE, "--pipeline", str(PIPE)]
    if RENDER:
        cmd += ["--render", RENDER]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    f = out / f"{n}.json"
    if not f.exists():
        return n, None, (r.stdout + r.stderr)[-800:]
    return n, json.loads(f.read_text(encoding="utf-8"))["results"], ""


tot = ok = 0
bad = []
with ThreadPoolExecutor(WORKERS) as ex:
    for n, res, err in ex.map(run, names):
        if res is None:
            bad.append((n, "NO RESULT", err))
            print(n, "NO RESULT", err[-300:], flush=True)
            continue
        tot += len(res)
        ok += sum(1 for r in res.values() if r["pass"])
        for ac, r in res.items():
            if not r["pass"]:
                bad.append((n, ac, "; ".join(r["fails"])))
        print(f"{n}: {sum(1 for r in res.values() if r['pass'])}/{len(res)}", flush=True)
(out / "summary.json").write_text(json.dumps({"set": SET, "view": VIEW, "face": FACE, "characters": len(names), "combinations": tot, "pass": ok,
                                              "failures": [{"char": c, "action": x, "why": w} for c, x, w in bad]}, indent=1), encoding="utf-8")
print(f"TOTAL {ok}/{tot} pass over {len(names)} characters; {len(bad)} failures")
for c, x, w in bad[:60]:
    print("  FAIL", c, x, w[:160])
