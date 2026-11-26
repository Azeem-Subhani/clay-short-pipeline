"""test_aj_actor.py - the Aj actor's contract, measured: control joints and real bones stay together, load and finish times.

    blender -b --factory-startup --python tools/chars_aj/test_aj_actor.py -- [--bodies Male_Teen,Female_Kid] [--frames 200] [--out <dir>]

Per body: a bare Aj actor in a 10 s shot; every control joint gets a random turn on every frame (arms by quaternion,
the rest by euler, within generous human ranges), the figure is moved and tipped about the stage, the collars are
worked out (_finalize), and then on every frame the largest distance between a control pivot and the head of the
bone it drives is measured (binding error, mm; the contract is < 0.5 mm) and the largest angle between a bone's
world turn and its target's (degrees). A second pass adds the actor API's squash (non-uniform scale) to see what it
costs. Also timed: loading one actor, and _finalize on a 10 s shot.
Writes <out>/binding.json.
"""
import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Euler, Quaternion, Vector

PIPE = Path(__file__).resolve().parents[2]
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
sys.path.insert(0, str(PIPE / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import aj_rig, cast  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--bodies", default="Male_Teen,Female_Kid,Male_Senior,Female_Adult")
ap.add_argument("--frames", type=int, default=200)
ap.add_argument("--out", default=str(PIPE / "output" / "_staging" / "aj_actor"))
a = ap.parse_args(argv)
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
RANGES = {"spine": 25, "spine1": 25, "torso": 25, "neck": 35, "head": 40, "hips": 20}
LEGS = {"hip": 70, "kn": 70, "an": 30, "toe": 20}


def rq(rnd, deg):
    ax = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))).normalized()
    return Quaternion(ax, math.radians(rnd.uniform(0, deg)))


def one(body, squash):
    t0 = time.time()
    shot = stagekit.begin("ajbind", 10.0, "draft")
    act = cast.actor("x", body, at=(0, 0), face="right", view="3q")
    t_load = time.time() - t0
    rnd = random.Random(7)
    N = a.frames
    for f in range(1, N + 1):
        for jn, ob in act.J.items():
            if jn in ("root", "skirt", "cape"):
                continue
            if jn.startswith(("sh.", "el.", "wr.", "cl.")):
                if jn.startswith("cl."):
                    continue                                   # the collar is derived from the arm
                ob.rotation_quaternion = rq(rnd, 150 if jn.startswith("sh.") else 120)
                ob.keyframe_insert("rotation_quaternion", frame=f)
            else:
                base = jn.split(".")[0]
                r = RANGES.get(base, LEGS.get(base, 20))
                ob.rotation_euler = Euler([math.radians(rnd.uniform(-r, r)) for _ in range(3)])
                ob.keyframe_insert("rotation_euler", frame=f)
        act.J["hips"].location = act._hips_rest + Vector([rnd.uniform(-0.05, 0.05) for _ in range(3)])
        act.J["hips"].keyframe_insert("location", frame=f)
        act.stage.location = (rnd.uniform(-2, 2), rnd.uniform(-2, 2), rnd.uniform(0, 0.5))
        act.stage.keyframe_insert("location", frame=f)
        act.tilt.rotation_euler = (math.radians(rnd.uniform(-20, 20)), math.radians(rnd.uniform(-20, 20)), math.radians(rnd.uniform(-180, 180)))
        act.tilt.keyframe_insert("rotation_euler", frame=f)
        if squash:                                             # what a 3.5% non-uniform squash of the whole figure costs
            k = rnd.uniform(-1, 1) * 0.14 * 0.25
            act.tilt.scale = (1 + 0.6 * k, 1 + 0.6 * k, 1 - k)
            act.tilt.keyframe_insert("scale", frame=f)
        act.ctrl["breath"] = rnd.uniform(0, 1)
        act.ctrl.keyframe_insert('["breath"]', frame=f)
    t1 = time.time()
    act._finalize()
    t_fin = time.time() - t1
    worst, worst_f, rot = 0.0, 0, 0.0
    for f in range(1, N + 1):
        e = aj_rig.binding_error(act, f)
        if e > worst:
            worst, worst_f = e, f
        rot = max(rot, aj_rig.rotation_error(act))
    return {"load_s": round(t_load, 2), "finalize_s_10s_shot": round(t_fin, 2), "frames": N, "max_binding_mm": round(worst, 4),
            "worst_frame": worst_f, "max_rotation_deg": round(rot, 4), "pass": worst < 0.5}


res = {}
for b in [x for x in a.bodies.split(",") if x]:
    for sq in (False, True):
        r = one("Aj_" + b if not b.startswith("Aj_") else b, sq)
        res[f"{b}{' +squash' if sq else ''}"] = r
        print("BIND", b, "squash" if sq else "plain", r, flush=True)
(out / "binding.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print("BIND_DONE")
