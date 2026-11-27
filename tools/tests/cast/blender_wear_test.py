"""Inside-Blender test: a rigid add-on with a per-body file (glasses on the Head, a wrist watch on the forearm) must end up in the same
place on the figure whether it comes from the character's own `addons` list (worn while the rig is still at the origin) or from
actor.wear() after the actor has been placed and scaled (a plan's costume.wear, or a shot's own call).

    blender -b --factory-startup --python tools/tests/cast/blender_wear_test.py -- [--body Male_Adult] [--at 3.0,2.0]

Everything is measured in the figure's own native frame (the pack's metres, rig at rest): world points are taken back with
T = rig.matrix_world @ arm0^-1. For the glasses: the middle of the front rim (the bridge) against the nose-bridge landmark: the front-most point
of the body's own surface on the centre line, 7 cm under the 'brow' landmark of library/characters/aj/bodies/<body>.json. For the watch: its centre against the
forearm bone's tail (the wrist). Prints the numbers and a JSON line; exits 1 when the shot-time path is more than 2 cm from the
list path.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

PIPE = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
sys.path.insert(0, str(PIPE / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import aj_wardrobe as W, cast, cast_aj  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--body", default="Male_Adult")
ap.add_argument("--outfit", default="shirt_trousers")
ap.add_argument("--at", default="3.0,2.0")
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
at = tuple(float(v) for v in a.at.split(","))

W.fit_ok = lambda f, rigid=False: bool(f) and f.get("status") == "pass"     # the outfit's review verdict is not under test
ent0 = cast_aj.entry(a.body)
BASE = dict(ent0, name="T", outfit=a.outfit, addons=[], bare=False, era=["modern"], height_m=None)
WITH = dict(BASE, addons=[{"item": "glasses"}, {"item": "wrist_watch"}])
cast_aj.entry = lambda b: dict(WITH) if b == "TL" else dict(BASE) if b == "TW" else ent0

shot = stagekit.begin("weartest", 1.0, "draft")
listed = cast.actor("l", "TL", at=at)                                       # add-ons from the character's own list
worn = cast.actor("w", "TW", at=(at[0] + 2.0, at[1]), view="front")          # add-ons put on after placing and scaling
worn.wear("glasses")
worn.wear("wrist_watch")
for x in shot.actors.values():
    x._finalize()
bpy.context.scene.frame_set(1)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()


def native(actor, p):
    T = actor.rig.matrix_world @ actor._wd["arm0"].inverted()
    return T.inverted() @ p


def verts_world(ob):
    me = ob.evaluated_get(dg).to_mesh()
    pts = [ob.matrix_world @ v.co for v in me.vertices]
    ob.evaluated_get(dg).to_mesh_clear()
    return pts


def addon_obj(actor, item):
    return next(o for o in actor._wd["addons"][item]["objs"] if o.type == "MESH")


def bridge(actor):
    """Middle of the front rim in the native frame: the vertices in the front 6 mm of the glasses, near the centre line."""
    pts = [native(actor, p) for p in verts_world(addon_obj(actor, "glasses"))]
    ymin = min(p.y for p in pts)
    front = [p for p in pts if p.y < ymin + 0.006]
    cx = (min(p.x for p in front) + max(p.x for p in front)) / 2
    mid = [p for p in front if abs(p.x - cx) < 0.012] or front
    return sum(mid, Vector()) / len(mid)


def watch(actor):
    pts = [native(actor, p) for p in verts_world(addon_obj(actor, "wrist_watch"))]
    return sum(pts, Vector()) / len(pts)


def wrist(actor):
    b = actor.rig.pose.bones["mixamorig:LeftForeArm"]
    return native(actor, actor.rig.matrix_world @ b.tail)


def nose_bridge(actor, z):
    """The nose-bridge landmark: the front-most point of the body's own surface on the centre line at height z (native frame)."""
    me = actor.mesh.evaluated_get(dg)
    m = me.to_mesh()
    pts = [native(actor, actor.mesh.matrix_world @ v.co) for v in m.vertices]
    me.to_mesh_clear()
    line = [p for p in pts if abs(p.x) < 0.006 and abs(p.z - z) < 0.006]
    return min(line, key=lambda p: p.y)


EYE_Z = W.measured_marks(a.body)["brow"]["at"][2] - 0.07               # the nose bridge sits about 7 cm under the brow landmark
out = {"body": a.body, "placed_at": at}
for tag, act in (("list", listed), ("wear", worn)):
    g, w = bridge(act), watch(act)
    n = nose_bridge(act, EYE_Z)
    out[tag] = {"glasses_bridge_to_nose_bridge_m": round((g - n).length, 4), "glasses_bridge_native": [round(v, 4) for v in g],
                "nose_bridge_native": [round(v, 4) for v in n], "watch_to_wrist_m": round((w - wrist(act)).length, 4)}
d_g = (bridge(listed) - bridge(worn)).length
d_w = (watch(listed) - watch(worn)).length
out["wear_vs_list_m"] = {"glasses": round(d_g, 4), "watch": round(d_w, 4)}
print("WEARTEST " + json.dumps(out), flush=True)
ok = d_g < 0.02 and d_w < 0.02
print("PASS" if ok else "FAIL", "wear() after placing matches the character's own list:", out["wear_vs_list_m"])
sys.exit(0 if ok else 1)
