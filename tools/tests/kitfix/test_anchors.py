"""Headless test of fixture grip points (stagekit.anchors, furnish.anchor, ActorAj.interact) and the walk-through-a-leaf check.

    blender -b --factory-startup --python tools/tests/kitfix/test_anchors.py [-- surface negative positive]

surface    every authored grip point of glass_doors, card_reader_post, badge_reader, badge_gate and lift_doors lies within 1 cm of the real mesh
           and is seen from the side its normal names, at the default size AND at another size (placed and turned in the world)
negative   an actor on the wrong side of a leaf raises; one 2 m away raises; a walk through a closed leaf is recorded in shot.passages and reported by physical.sweep as a
           blocking through_closed_leaf (the walk is still built); the same walk after the leaf swung 85 degrees reports nothing
positive   one interact per fixture type puts the palm within 2 cm of the anchor at the hit frame, with the hand a person would use
Exit code 1 when any check fails.
"""
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.dont_write_bytecode = True
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import stagekit  # noqa: E402
from stagekit import anchors, cast, core, furnish, physical  # noqa: E402

FAILS = []
ACTOR = "OfficeWomanCardigan"


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def world_bvh(root):
    """The fixture's evaluated meshes in world space, as one BVH (the real skin the hand must meet)."""
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    verts, tris = [], []
    for o in [root, *root.children_recursive]:
        if o.type != "MESH" or o.hide_render:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ev.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        me.calc_loop_triangles()
        tris += [tuple(base + i for i in t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, tris)


# a default one and one with other options, placed and turned in the world (the badge reader has no size: it is placed and turned)
FIXTURES = [
    ("glass_doors", furnish.glass_doors, {}, dict(width=1.6, height=2.4)),
    ("card_reader_post", furnish.card_reader_post, {}, dict(height=1.3)),
    ("badge_reader", furnish.badge_reader, {}, {}),
    ("badge_gate", furnish.badge_gate, {}, dict(lanes=2, lane_w=1.1, length=1.5)),
    ("lift_doors", furnish.lift_doors, {}, dict(count=3, height=3.0)),
]


def t_surface():
    stagekit.begin("anchors_surface", 2.0, "draft")
    for n, (name, make, _o, other) in enumerate(FIXTURES):
        for label, opts, at, rz in (("default", {}, (n * 12.0, 0.0, 0.0), 0.0), ("other", other, (n * 12.0, 6.0, 0.0), 35.0)):
            piece = make(at=at, rot_z=rz, name=f"{name}_{label}", **opts)
            names = furnish.anchors_of(piece)
            check(f"surface: {name} ({label}) has grip points", bool(names), ", ".join(names))
            bvh = world_bvh(piece)
            worst, bad = 0.0, []
            for a in names:
                ev = furnish.anchor(piece, a).eval()
                loc, _nrm, _i, dist = bvh.find_nearest(ev.point)
                seen = bvh.ray_cast(ev.point + ev.normal * 0.05, -ev.normal, 0.2)[0] is not None            # seen from the normal's side, nothing in front
                near_cm = dist * 100.0
                worst = max(worst, near_cm)
                if near_cm > 1.0 or not seen:
                    bad.append(f"{a}: {near_cm:.2f} cm, seen={seen}")
            check(f"surface: {name} ({label}) every anchor within 1 cm of its mesh, on its normal's side", not bad,
                  f"{len(names)} anchors, worst {worst:.3f} cm" + (" ; " + "; ".join(bad) if bad else ""))


def actor(cid, at, face="right"):
    a = cast.actor(cid, ACTOR, at=at, face=face)
    a.heading((at[0], at[1] + 1.0), 0.0, turn=0.0)
    return a


def raises(kind, fn):
    try:
        fn()
    except kind as ex:
        return True, str(ex)
    except Exception as ex:                                      # noqa: BLE001
        return False, f"{type(ex).__name__}: {ex}"
    return False, "did not raise"


def t_negative():
    stagekit.begin("anchors_neg1", 4.0, "draft")
    doors = furnish.glass_doors(at=(0, 0, 0))
    a = actor("t1", (0.05, -0.55))
    ok, msg = raises(anchors.InteractionError, lambda: a.interact(furnish.anchor(doors, "handle_R_in"), hit=0.8))
    check("negative: the lobby-side handle from the street side raises, naming the actor, the anchor and the number", ok and "t1" in msg and "handle_R_in" in msg and "wrong side" in msg, msg)

    stagekit.begin("anchors_neg2", 4.0, "draft")
    doors = furnish.glass_doors(at=(0, 0, 0))
    a = actor("t2", (0.05, -2.18))
    ok, msg = raises(anchors.InteractionError, lambda: a.interact(furnish.anchor(doors, "handle_R_out"), hit=0.8, auto_move=False))
    check("negative: a handle 2 m away raises (no auto_move)", ok and "cannot reach" in msg, msg)

    shot = stagekit.begin("anchors_neg3", 6.0, "draft")
    furnish.glass_doors(at=(0, 0, 0))
    a = actor("t3", (0.45, -1.0))
    a.walk(0.2, (0.45, 1.0), speed=2.2)                          # does not raise: the walk is still animated
    a._finalize()
    ps = getattr(shot, "passages", [])
    note = next((n for n in shot.notes if "leaf_R" in n), "")
    check("negative: a walk through a closed leaf is written down (shot.passages and a note naming the leaf, the time and its angle)",
          len(ps) == 1 and "leaf_R" in ps[0]["barrier"] and abs(ps[0]["open_deg"]) < 1.0 and "0.0 degrees" in note and "s:" in note, f"{ps} / {note}")
    items = [i for i in physical.sweep(shot)["items"] if i["code"] == "through_closed_leaf"]
    check("negative: physical.sweep reports it as one blocking through_closed_leaf item", len(items) == 1 and items[0]["level"] == "block" and "leaf_R" in items[0]["object"], str(items))

    shot4 = stagekit.begin("anchors_neg4", 6.0, "draft")
    doors = furnish.glass_doors(at=(0, 0, 0))
    leaf = furnish.part(doors, "leaf_R")
    core.key(leaf, "rotation_euler", 0.0, (0.0, 0.0, 0.0))
    core.move(leaf, 0.0, 0.3, rotation_deg=(0.0, 0.0, -85.0))
    a = actor("t4", (0.45, -1.0))
    try:
        t_arr = a.walk(0.4, (0.45, 1.0), speed=2.2)
        a._finalize()
        items = [i for i in physical.sweep(shot4)["items"] if i["code"] == "through_closed_leaf"]
        check("negative: the same walk after the leaf swung 85 degrees records and reports nothing", not getattr(shot4, "passages", []) and not items, f"arrives {t_arr:.2f}s, {items}")
    except Exception as ex:                                      # noqa: BLE001
        check("negative: the same walk after the leaf swung 85 degrees passes", False, f"{type(ex).__name__}: {ex}")


def measure(a, ref, side, t):
    a._finalize()
    f = a._f(t)
    dg = core.at_frame(f)
    palm = a.palm[side].evaluated_get(dg).matrix_world.translation.copy()
    e = ref.eval(f)
    return (palm - (e.point + e.normal * e.clearance)).length * 100.0         # from where the palm should rest: the surface point plus the clearance


def t_positive():
    cases = [
        ("glass_doors", lambda: furnish.glass_doors(at=(0, 0, 0)), "handle_R_in", None, "hold_door", {"hold": 0.3}),
        ("card_reader_post", lambda: furnish.card_reader_post(at=(0, 0, 0)), "tap", None, "tap", {"hold": 0.2, "withdraw": 0.15}),
        ("badge_reader", lambda: furnish.badge_reader(at=(0, 0, 1.2)), "tap", None, "tap", {"hold": 0.2}),
        ("badge_gate", lambda: furnish.badge_gate(at=(0, 0, 0)), "reader_1", None, "tap", {"hold": 0.2}),
        ("lift_doors", lambda: furnish.lift_doors(at=(0, 0, 0)), "call_0", None, "press", {"hold": 0.18}),
    ]
    for name, make, aname, spot, kind, opts in cases:
        stagekit.begin(f"anchors_pos_{name}", 4.0, "draft")
        piece = make()
        ref = furnish.anchor(piece, aname)
        stand = spot or ref.stand()
        a = actor("p", (stand[0], stand[1]))
        try:
            hit = 1.2
            a.interact(ref, hit=hit, kind=kind, **opts)
            side = ref.eval(1).hand if ref.eval(1).hand in "LR" else "R"
            cm = measure(a, ref, side, hit)
            check(f"positive: {name}.{aname} {kind}: palm within 2 cm of its resting point at the hit frame", cm <= 2.0, f"{cm:.2f} cm")
        except Exception as ex:                                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"positive: {name}.{aname} {kind}", False, f"{type(ex).__name__}: {ex}")


ALL = {"surface": t_surface, "negative": t_negative, "positive": t_positive}
want = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(ALL)
for n in want:
    try:
        ALL[n]()
    except Exception:
        import traceback
        traceback.print_exc()
        check(f"{n} ran", False)
print("ANCHORS " + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
