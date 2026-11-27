"""Tests of the geometry helpers behind stagekit.physical, on tiny scenes made of boxes (no cast pack, no clip needed).

    blender -b --factory-startup --python tools/tests/physical/test_physical.py

Covers: penetration depth of a box in a box (and a hand-sized graze that is a grip), a body point against a closed door leaf and an open one,
rain streaks under a canopy and in the open, and the merge of per-frame flags into one item. Exits non-zero when any check fails.
"""
from __future__ import annotations

import math
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.dont_write_bytecode = True

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

from stagekit import physical  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(name)


def box(name: str, size, loc, offset=(0.0, 0.0, 0.0)):
    """A closed box mesh object of size (x, y, z) metres centred at loc (offset moves the mesh inside the object: a hinge at one end)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = (v.co.x * size[0] + offset[0], v.co.y * size[1] + offset[1], v.co.z * size[2] + offset[2])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    return ob


def depsgraph():
    bpy.context.view_layer.update()
    return bpy.context.evaluated_depsgraph_get()


def test_penetration():
    print("penetration depth")
    big = box("big", (1, 1, 1), (0, 0, 0))
    small = box("small", (0.5, 0.5, 0.5), (0.65, 0, 0))             # reaches 10 cm into the big box
    far = box("far", (0.5, 0.5, 0.5), (3.0, 0, 0))
    graze = box("graze", (0.5, 0.5, 0.5), (0.735, 0, 0))            # 1.5 cm into the big box: a grip's worth of contact
    dg = depsgraph()
    e = {o.name: physical.build_eval_mesh(o, dg) for o in (big, small, far, graze)}
    r = physical.penetration_depth_cm(e["small"], e["big"])
    check("box 10 cm into a box measures about 10 cm", r is not None and abs(r["depth_cm"] - 10.0) < 0.6, str(r))
    r2 = physical.penetration_depth_cm(e["big"], e["small"])
    check("depth is the same whichever mesh is first", r2 is not None and abs(r2["depth_cm"] - 10.0) < 0.6, str(r2))
    check("boxes apart do not overlap", physical.penetration_depth_cm(e["far"], e["big"]) is None)
    r3 = physical.penetration_depth_cm(e["graze"], e["big"])
    check("a 1.5 cm graze is measured without hands", r3 is not None and 1.0 < r3["depth_cm"] < 2.0, str(r3))
    hands = [(Vector((0.5, 0.0, 0.0)), 0.4)]                         # a hand big enough to cover the whole edge of the small box
    check("a graze under 2.5 cm inside a hand's reach is a grip, not a fault", physical.penetration_depth_cm(e["graze"], e["big"], hands=hands) is None)
    r4 = physical.penetration_depth_cm(e["small"], e["big"], hands=hands)
    check("10 cm inside a hand's reach is still a fault", r4 is not None and r4["depth_cm"] > 5.0, str(r4))


def test_leaf():
    print("passage through a leaf")
    leaf = box("test.leaf", (1.0, 0.04, 2.1), (0, 0, 0), offset=(0.5, 0.0, 1.05))      # hinged at its left end, 1 m wide, 4 cm thick
    lo, hi, thin = Vector((0.0, -0.02, 0.0)), Vector((1.0, 0.02, 2.1)), 1
    body = Vector((0.5, 0.0, 1.0))
    depsgraph()
    pen_closed = physical.leaf_penetration([leaf.matrix_world.inverted() @ body], lo, hi, thin)
    check("a body in a closed leaf is inside it", pen_closed > 0.1, f"{pen_closed:.3f} m")
    check("a closed leaf reads 0 degrees", physical.open_degrees(leaf) == 0.0)
    leaf.rotation_euler.z = math.radians(90)
    depsgraph()
    pen_open = physical.leaf_penetration([leaf.matrix_world.inverted() @ body], lo, hi, thin)
    check("the same point is clear once the leaf has swung open", pen_open == 0.0, f"{pen_open:.3f} m")
    check("an open leaf reads its angle", abs(physical.open_degrees(leaf) - 90.0) < 0.1)
    beside = physical.leaf_penetration([leaf.matrix_world.inverted() @ Vector((0.0, 0.5, 1.0))], lo, hi, thin)
    check("a body in the swung leaf's new place is inside it", beside > 0.1, f"{beside:.3f} m")


def test_rain():
    print("rain under cover")
    sc = bpy.context.scene
    box("test_canopy", (2.0, 2.0, 0.1), (0, 0, 3.0))
    box("sofa_slab", (2.0, 2.0, 0.1), (10, 0, 3.0))                  # solid, but not cover
    dg = depsgraph()
    under, open_air, under_sofa = np.array([[0.2, 0.1, 1.0]]), np.array([[5.0, 0.0, 1.0]]), np.array([[10.0, 0.0, 1.0]])
    n, names = physical.rain_cover_hits(sc, dg, under)
    check("a streak under the canopy is covered by it", n == 1 and names.get("test_canopy") == 1, str(dict(names)))
    n, _ = physical.rain_cover_hits(sc, dg, open_air)
    check("a streak in the open is not covered", n == 0)
    n, _ = physical.rain_cover_hits(sc, dg, under_sofa)
    check("something solid that is not cover does not count", n == 0)
    pts = np.vstack([under, open_air, under_sofa])
    kept = physical.streaks_under_boxes(pts, [physical._aabb_of(bpy.data.objects["test_canopy"])])
    check("only streaks below a cover box are tested", len(kept) == 1 and abs(kept[0][0] - 0.2) < 1e-6)


def test_merge():
    print("merging per-frame flags")
    def fl(frame, level, value, actor="a", obj="x", code="interpenetration"):
        return {"code": code, "actor": actor, "object": obj, "frame": frame, "level": level, "value": value, "unit": "cm", "extra": {}}
    flags = [fl(10, "warn", 3.0), fl(12, "block", 6.0), fl(15, "warn", 9.0), fl(20, "block", 7.5), fl(11, "warn", 2.0, obj="y")]
    out = physical.merge_flags(flags)
    check("one item per (code, actor, object)", len(out) == 2, str([(r["object"], r["frames"]) for r in out]))
    r = next(x for x in out if x["object"] == "x")
    check("frame range is first to last flagged frame", r["frames"] == [10, 20], str(r["frames"]))
    check("the worst frame is the largest value at the highest level", r["frame"] == 20 and r["value"] == 7.5 and r["level"] == "block", f"{r['frame']} {r['value']} {r['level']}")
    q = next(x for x in out if x["object"] == "y")
    check("a warning-only fault stays a warning", q["level"] == "warn" and q["frames"] == [11, 11])
    check("blocks sort before warnings", out[0]["level"] == "block")
    check("every item text names the numbers and a way out", all(isinstance(physical._text(x), str) and len(physical._text(x)) > 30 for x in out))
    check("the defaults read when style.json has no physical key", physical.config()["interp"]["block_cm"] == 5.0)


def main() -> int:
    for fn in (test_penetration, test_leaf, test_rain, test_merge):
        try:
            fn()
        except Exception:                                  # noqa: BLE001
            traceback.print_exc()
            FAILS.append(fn.__name__)
    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all physical tests passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    code = main()
    if code:
        sys.exit(code)
