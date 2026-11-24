"""Outline consistency test: is the ink one weight, complete and smooth in posed frames, at every scale and distance?

    blender -b --factory-startup --python ink_test.py -- --char Soldier --out <abs dir> [--pack <blend>] [--poses a,b,c]
        [--scales 0.6,1.0,1.5] [--px 900]

For each pose x view x actor scale it renders an INK PASS: every fill white, every outline black, face features hidden,
on a green backdrop, with an orthographic camera (so pixels convert exactly to millimetres). From the pixels:
  width_mm      median stroke width (the smaller of the horizontal and vertical run through each ink pixel)
  thick_ratio   95th percentile / median: heavy spots, doubled lines and blobs push it up (a clean drawing is about 1.4: diagonals)
  coverage      share of the figure's silhouette edge that carries ink: missing outline pushes it down
  spikes        ink pixels further outside the filled silhouette than a line can reach: serrations and spikes
Writes <out>/<char>/ink.json, the pass images, and prints a PASS / FAIL line per character.
Limits (calibrated on characters that are clean by eye; two legs side by side or fingers legitimately read as wider ink):
width within 15 % of the rest pose at every pose and scale; thick_ratio <= 2.4; coverage >= 0.97; spikes <= 3 % of ink.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np

_W = Path(__file__).resolve().parents[2]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[3]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--pack", default=None)
ap.add_argument("--pipeline", default=str(_PIPE))
ap.add_argument("--poses", default="rest,proud,gasp,point,carry,think,hands_up,sit,cross_arms,cower,wave,pull")
ap.add_argument("--scales", default="0.6,1.0,1.5")
ap.add_argument("--px", type=int, default=1600)
a = ap.parse_args(argv)
if a.pack:
    os.environ["CAST_PACK"] = a.pack
os.environ["SHORTS_PROJECT"] = a.pipeline
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import cast  # noqa: E402

poses = a.poses.split(",")
scales = [float(x) for x in a.scales.split(",")]
VIEWS = ["front", "3q", "side"]
shot = stagekit.begin("inktest", len(poses) * len(VIEWS) * 0.5 + 1, "draft")
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = a.px
sc.render.resolution_percentage = 100
sc.eevee.taa_render_samples = 1                      # hard pixel edges: run lengths are exact
sc.render.filter_size = 0.01
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 1.0, 0.0, 1)
sc.world = w
cd = bpy.data.cameras.new("cam")
cd.type = "ORTHO"
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
cam.rotation_euler = (math.pi / 2, 0, 0)
sc.camera = cam
out = Path(a.out).resolve() / a.char
out.mkdir(parents=True, exist_ok=True)
res = {"char": a.char, "rows": []}


def measure(path, zoom):
    img = bpy.data.images.load(str(path))
    n = a.px
    px = np.array(img.pixels[:], dtype=np.float32).reshape(n, n, 4)[:, :, :3]
    bpy.data.images.remove(img)
    green = (px[:, :, 1] > 0.6) & (px[:, :, 0] < 0.4) & (px[:, :, 2] < 0.4)
    ink = (px.max(axis=2) < 0.25)
    fig = ~green
    fill = fig & ~ink
    if ink.sum() < 50:
        return None

    def runs(mask):                                   # length of the run of True through each pixel, along axis 1
        out_ = np.zeros(mask.shape, dtype=np.int32)
        for r in range(mask.shape[0]):
            row = mask[r]
            if not row.any():
                continue
            d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
            s_, e_ = np.where(d == 1)[0], np.where(d == -1)[0]
            for x0, x1 in zip(s_, e_):
                out_[r, x0:x1] = x1 - x0
        return out_

    wpx = np.minimum(runs(ink), runs(ink.T).T)[ink]
    mm = zoom / n * 1000.0
    lo_, hi_ = np.percentile(wpx, 15), np.percentile(wpx, 65)
    core_ = wpx[(wpx >= lo_) & (wpx <= hi_)]
    med = float(core_.mean()) if core_.size else float(np.median(wpx))        # sub-pixel estimate of the plain stroke width
    p95 = float(np.percentile(wpx, 95))
    # silhouette edge: figure pixels with a background neighbour; covered if ink within 1 px
    pad = np.pad(fig, 1)
    edge = fig & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])
    inkp = np.pad(ink, 1)
    near = inkp[1:-1, 1:-1] | inkp[:-2, 1:-1] | inkp[2:, 1:-1] | inkp[1:-1, :-2] | inkp[1:-1, 2:]
    cov = float((edge & near).sum() / max(1, edge.sum()))
    # spikes: ink further from any fill than a whole line width (grow the fill by med px, see what ink is left outside)
    grown = fill.copy()
    for _ in range(int(math.ceil(med * 1.25)) + 1):
        g = np.pad(grown, 1)
        grown = g[1:-1, 1:-1] | g[:-2, 1:-1] | g[2:, 1:-1] | g[1:-1, :-2] | g[1:-1, 2:]
    spikes = float((ink & ~grown).sum() / max(1, ink.sum()))
    return {"width_mm": round(med * mm, 2), "p95_mm": round(p95 * mm, 2), "thick_ratio": round(p95 / max(med, 1e-6), 2), "coverage": round(cov, 4),
            "spikes": round(spikes, 5), "ink_px": int(ink.sum())}


white = None
for scale in scales:
    for o in list(bpy.data.objects):
        if o.name.startswith("x") and o is not cam:
            pass
    act = cast.actor(f"x{int(scale * 100)}", a.char, at=(0, 0), face="right", view="3q", scale=scale)
    cast.look("#FFFFFF", lit=0.0)
    H = act.height
    zoom = H * 1.45
    for m in bpy.data.materials:                      # ink pass: outlines black, every fill white
        if not m.get("sk_look"):
            continue
        m.node_tree.nodes["base"].outputs[0].default_value = (0, 0, 0, 1) if m["sk_look"] == 2 else (1, 1, 1, 1)
    hidden = 0
    for o in act.parts:                               # shapes drawn IN the ink colour are not lines: hide them
        mats = [m.name for m in o.data.materials if m]
        if any(n.endswith(".outline") for n in mats):
            o.hide_render = True
            o["sk_off"] = True
            hidden += 1
    t = 0.0
    jobs = []
    for p in poses:
        for v in VIEWS:
            act.view(v, t)
            act.pose("rest", t, 0.0)
            act.lean(0, t, 0.0)
            act.tilt_head(0, t, 0.0)
            act.legs(0, 0, t, 0.0)
            act.pose(p, t, 0.0)
            jobs.append((shot.f(t) + 2, p, v))
            t += 0.5
    cd.ortho_scale = zoom
    cam.location = (0, -10, H * 0.5)
    for fr, p, v in jobs:
        sc.frame_set(fr)
        path = out / f"ink_{int(scale * 100):03d}__{p}__{v}.png"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        mres = measure(path, zoom)
        if mres:
            res["rows"].append({"scale": scale, "pose": p, "view": v, **mres})
    for o in list(act.coll.all_objects):               # clear this actor before the next scale
        bpy.data.objects.remove(o, do_unlink=True)
    for o in (act.stage, act.tilt):
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)

rows = res["rows"]
ref = [r["width_mm"] for r in rows if r["pose"] == "rest" and abs(r["scale"] - 1.0) < 1e-6]
base = sum(ref) / max(1, len(ref)) if ref else (sum(r["width_mm"] for r in rows) / max(1, len(rows)))
fails = []
for r in rows:
    tag = f"{r['pose']}/{r['view']}@{r['scale']}"
    px_w = r["width_mm"] / (base if base else 1)
    if abs(px_w - 1.0) > 0.15 and r["ink_px"] > 400:
        fails.append(f"{tag}: line {r['width_mm']} mm vs {base:.2f} mm at rest")
    if r["thick_ratio"] > 2.4 and abs(r["scale"] - 1.0) < 1e-6:      # judged at natural size: a figure shrunk to 0.6 keeps the same
                                                                     # line in millimetres, so its small details legitimately close up
        fails.append(f"{tag}: heavy spots (p95 / median = {r['thick_ratio']})")
    if r["coverage"] < 0.97:
        fails.append(f"{tag}: {100 - r['coverage'] * 100:.1f} % of the silhouette has no ink")
    if r["spikes"] > 0.03:
        fails.append(f"{tag}: spikes ({r['spikes'] * 100:.2f} % of the ink lies off the shapes)")
res.update(base_width_mm=round(base, 2), fails=fails, n=len(rows), passed=not fails,
           width_range_mm=[min(r["width_mm"] for r in rows), max(r["width_mm"] for r in rows)] if rows else None,
           worst_thick_ratio=max((r["thick_ratio"] for r in rows), default=None), min_coverage=min((r["coverage"] for r in rows), default=None))
(out / "ink.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(("INK PASS " if not fails else "INK FAIL ") + a.char, f"{len(rows)} frames, line {base:.2f} mm, range {res['width_range_mm']}, "
      f"worst thick ratio {res['worst_thick_ratio']}, min coverage {res['min_coverage']}", "" if not fails else "| " + "; ".join(fails[:6]))
