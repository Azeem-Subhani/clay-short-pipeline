"""Pose x view x facing frames of one character in a plain test scene (not a pipeline set).

    blender -b --factory-startup --python work/tools/bl/pose_sheet.py -- --char Soldier --out <dir> [--poses a,b] [--px 360]
        [--pipeline <pipeline root>] [--pack <.blend>] [--trans a>b,c>d] [--zoom 2.6]

Writes <out>/<char>/<pose>__<view>_<face>.png (static poses, blend=0) or, with --trans, frame strips of the blend
between two poses: <out>/<char>/T_<a>-<b>__<view>_<face>__NN.png. Tile them with work/tools/sheet.py.
"""
import argparse
import os
import sys
from pathlib import Path

import bpy

_W = Path(__file__).resolve().parents[2]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[3]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--poses", default=None)
ap.add_argument("--trans", default=None)
ap.add_argument("--px", type=int, default=360)
ap.add_argument("--zoom", type=float, default=2.4)
ap.add_argument("--pipeline", default=str(_PIPE))
ap.add_argument("--pack", default=None)
ap.add_argument("--views", default="front,3q,side")
ap.add_argument("--faces", default="right,left")
ap.add_argument("--samples", type=int, default=8)
a = ap.parse_args(argv)
if a.pack:
    os.environ["CAST_PACK"] = a.pack
os.environ["SHORTS_PROJECT"] = a.pipeline
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import cast, core  # noqa: E402

views = a.views.split(",")
faces = a.faces.split(",")
poses = a.poses.split(",") if a.poses else list(cast.POSES)
trans = [tuple(x.split(">")) for x in a.trans.split(",")] if a.trans else []
combos = [(v, f) for v in views for f in faces]
STEP = 0.5                                   # seconds per static pose
TLEN = 0.5                                   # seconds per transition (12 frames)
n_static = 0 if trans else len(poses) * len(combos)
seconds = n_static * STEP + len(trans) * len(combos) * (TLEN + 0.5) + 1.0
shot = stagekit.begin("posetest", seconds, "draft")
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = a.px
sc.render.resolution_percentage = 100
sc.eevee.taa_render_samples = a.samples
sc.render.film_transparent = False
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.87, 0.8, 1)
sc.world = w
sc.view_settings.view_transform = "Standard"
cd = bpy.data.cameras.new("cam")
cd.type = "ORTHO"
cd.ortho_scale = a.zoom
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
cam.location = (0, -10, a.zoom * 0.42)
cam.rotation_euler = (1.5707963, 0, 0)
sc.camera = cam
cast.look("#FFFFFF", lit=0.0)
act = cast.actor("x", a.char, at=(0, 0), face="right", view="3q")
out = Path(a.out).resolve() / a.char
out.mkdir(parents=True, exist_ok=True)
jobs = []
t = 0.0
if not trans:
    for p in poses:
        for v, f in combos:
            act.view(v, t)
            act.face(f, t)
            act.pose("rest", t, 0.0)
            act.lean(0, t, 0.0)
            act.tilt_head(0, t, 0.0)
            act.legs(0, 0, t, 0.0)
            for s in "LR":
                act.hand(s, "mitten", t, 0.0)
            act.pose(p, t, 0.0)
            jobs.append((shot.f(t) + 2, out / f"{p}__{v}_{f}.png"))
            t += STEP
else:
    for pa, pb in trans:
        for v, f in combos:
            act.view(v, t)
            act.face(f, t)
            act.pose("rest", t, 0.0)
            act.lean(0, t, 0.0)
            act.tilt_head(0, t, 0.0)
            act.legs(0, 0, t, 0.0)
            act.pose(pa, t, 0.0)
            act.pose(pb, t + 0.25 + TLEN, TLEN)
            f0 = shot.f(t + 0.25)
            for k in range(0, int(TLEN * shot.fps) + 1, 2):
                jobs.append((f0 + k, out / f"T_{pa}-{pb}__{v}_{f}__{k:02d}.png"))
            t += TLEN + 0.5
for fr, path in jobs:
    sc.frame_set(fr)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
print("POSE_SHEET_DONE", len(jobs))
