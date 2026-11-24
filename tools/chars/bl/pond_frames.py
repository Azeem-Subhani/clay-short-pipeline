"""Re-render chosen frames of one pond-clip shot with the pipeline's own shot code and locked settings.

    blender -b --factory-startup --python pond_frames.py -- --clip <clip dir> --shot sh01 --frames 9,41,217 --out <abs dir>
        [--quality final] [--pipeline <root>]

Frame numbers are 1-based inside the shot. Output: <out>/<shot>_<frame:04d>.png. Builds the shot exactly as run_shot.py does.
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

import bpy

_W = Path(__file__).resolve().parents[2]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[3]
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--clip", required=True)
ap.add_argument("--shot", required=True)
ap.add_argument("--frames", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--quality", default="final")
ap.add_argument("--pipeline", default=str(_PIPE))
a = ap.parse_args(argv)
os.environ["SHORTS_PROJECT"] = a.pipeline
for line in (Path(a.pipeline) / ".env").read_text(encoding="utf-8").splitlines() if (Path(a.pipeline) / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import run_shot  # noqa: E402
import stagekit  # noqa: E402

clip = Path(a.clip).resolve()
seconds, _src = run_shot.shot_seconds(clip, a.shot, None)
shot = stagekit.begin(a.shot, seconds, a.quality)
shot.clip_dir = clip
shot.words = run_shot.shot_words(clip, a.shot, seconds)
shot.plan = run_shot.plan_entry(clip, a.shot)
whole = run_shot.plan_of(clip)
shot.world = whole.get("world", {})
shot.cast_plan = {c["id"]: c for c in whole.get("cast", [])}
script = clip / "blender" / f"{a.shot}.py"
sys.path.insert(0, str(script.parent))
spec = importlib.util.spec_from_file_location(f"shot_{a.shot}", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.build_shot(shot)
sc = bpy.context.scene
out = Path(a.out).resolve()
out.mkdir(parents=True, exist_ok=True)
for f in [int(x) for x in a.frames.split(",")]:
    sc.frame_set(f)
    sc.render.filepath = str(out / f"{a.shot}_{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("POND_FRAME", a.shot, f, flush=True)
for n in shot.notes:
    print("[note]", n)
