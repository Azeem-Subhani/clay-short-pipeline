"""Render single final-quality stills of one shot of a clip to a scratch folder, without touching the clip's render folder.

    blender -b --factory-startup --python tools/tests/kitfix/render_film_still.py -- --clip output/clips/<slug> --shot sh02 --frames 30,180,230 --out <dir> --tag after
Writes <out>/<shot>_<frame:04d>_<tag>.png.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.dont_write_bytecode = True
import bpy  # noqa: E402

import run_shot  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--clip", required=True)
ap.add_argument("--shot", required=True)
ap.add_argument("--frames", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--tag", default="after")
ap.add_argument("--quality", default="final")
a = ap.parse_args(argv)

shot = run_shot.build_shot_scene(Path(a.clip), a.shot, a.quality)
sc = bpy.context.scene
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
for f in (int(x) for x in a.frames.split(",")):
    sc.frame_set(f)
    sc.render.filepath = str(out / f"{a.shot}_{f:04d}_{a.tag}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath, flush=True)
