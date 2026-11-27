"""Headless test of the kit faults the first film exposed.

    blender -b --factory-startup --python tools/tests/kitfix/test_kit_fixes.py [-- feet campath keys actions set bag rain]

feet      review.feet_gap: a floor within 1 cm of the soles, a slab below it, a box held at the chest, a lifted figure
campath   a door leaf that only swings across the camera's path late in the shot does not block the earlier move; one that is there all along does
keys      a blend=0 key and a turn=0 heading hold the old value until one frame before, then step (no drift across a cut)
actions   read and shout leave a hand that holds a prop, or that the shot has posed, alone
set       the lobby's CCTV view sees the doors and the gate; no laptop on an office chair; the rain card leaves the door gap dry
bag       prop_messenger_bag's body is under its origin
rain      the rain material fades near the lens; splash and glass materials build
Exit code 1 when any check fails.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.path.insert(0, str(ROOT / "tools" / "tests" / "camera"))
sys.path.insert(0, str(ROOT / "examples" / "sets"))
sys.dont_write_bytecode = True
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stagekit  # noqa: E402
from stagekit import assets, camera, campath, cast, core, fx, review  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def slab(top, size=6.0, name="floor"):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    o = bpy.context.object
    o.name = name
    o.scale = (size, size, 0.2)
    o.location = (0, 0, top - 0.1)
    return o


def box_obj(name, dims, at):
    o = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(o)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=dims, verts=bm.verts)
    bm.to_mesh(o.data)
    bm.free()
    o.location = at
    return o


def t_feet():
    for label, top in (("floor 2 mm under the soles", -0.002), ("floor 8 mm above the soles", 0.008), ("floor 5 mm under, slab 25 cm further", -0.005)):
        stagekit.begin("t", 2.0, "draft")
        a = cast.actor("x", "ManagerWomanBlazer", at=(0, 0), face="right", view="side")
        slab(top)
        if "slab" in label:
            slab(-0.25, name="deep")
        dg = core.at_frame(1)
        gap, ob, _z = review.feet_gap(a, dg)
        check(f"feet: {label}", gap is not None and abs(gap) < 0.02, f"gap {None if gap is None else round(gap * 1000, 1)} mm")
    stagekit.begin("t", 2.0, "draft")
    a = cast.actor("x", "ManagerWomanBlazer", at=(0, 0), face="right", view="side")
    slab(0.0)
    box = box_obj("carried_box", (0.3, 0.3, 0.3), (0.2, 0.0, 1.1))
    bpy.context.view_layer.update()
    a.hold(box, "R", 0.0, grip=False)                     # held, but NOT linked to the actor's collection
    dg = core.at_frame(1)
    gap, ob, _z = review.feet_gap(a, dg)
    check("feet: a box carried at the chest is not the floor", gap is not None and abs(gap) < 0.02, f"gap {gap}, hit {ob.name if ob else None}")
    a.stage.location.z = 0.15
    dg = core.at_frame(1)
    gap, ob, _z = review.feet_gap(a, dg)
    check("feet: a lifted figure floats", gap is not None and 0.13 < gap < 0.17, f"gap {gap}")
    a.stage.location.z = -0.12
    dg = core.at_frame(1)
    gap, ob, _z = review.feet_gap(a, dg)
    check("feet: a sunk figure is sunk", gap is not None and -0.14 < gap < -0.10, f"gap {gap}")


def t_campath():
    import world
    for late in (True, False):
        shot = stagekit.begin("cp", 4.0, "draft")
        world.build_world(shot)
        leaf = box_obj("leaf", (1.6, 0.1, 2.4), (0, 3.5, 1.2))
        if late:
            leaf.location = (0, 3.5, -60.0)
            leaf.keyframe_insert("location", frame=1)
            leaf.keyframe_insert("location", frame=80)
            leaf.location = (0, 3.5, 1.2)
            leaf.keyframe_insert("location", frame=81)
            for fc in core.fcurves(leaf):
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"
        cam = camera.Camera()
        cam.view("w", 0.0, pos=(0.0, 1.0, 1.5), aim=(0.0, 8.0, 1.5), lens=30, size="manual")
        cam.dolly(0.3, 2.5, 0.5)
        cam.hold(4.0)
        cam.finish()
        rep = campath.analyse(shot)
        codes = {i["code"] for i in rep["issues"] if i["level"] == "block"}
        if late:
            check("campath: a leaf that arrives after the camera has passed does not block", "camera_through_geometry" not in codes, str([i["detail"] for i in rep["issues"] if i["code"] == "camera_through_geometry"][:2]))
        else:
            check("campath: a leaf that stands in the path all along blocks", "camera_through_geometry" in codes, str(sorted(codes)))


def t_keys():
    stagekit.begin("k", 12.0, "draft")
    a = cast.actor("x", "Aj_Female_Adult", at=(0, 0), face="right", view="3q")
    a.arm("R", 40, 20, 1.0, 0.0)
    a.arm("R", 120, 20, 8.0, 0.0)                          # blend 0: a step at 8 s
    fcs = [fc for fc in core.fcurves(a.J["sh.R"]) if fc.data_path == "rotation_quaternion"]
    f_early, f_mid, f_step = a._f(1.5), a._f(6.0), a._f(8.0)
    drift = max(abs(fc.evaluate(f_mid) - fc.evaluate(f_early)) for fc in fcs)
    jump = max(abs(fc.evaluate(f_step) - fc.evaluate(f_step - 2)) for fc in fcs)
    check("keys: a blend=0 key holds the old value until the frame before", drift < 1e-4 and jump > 0.05, f"drift {drift:.5f}, step {jump:.3f}")
    a.heading(0, 1.0, 0.25)
    a.heading(90, 9.0, 0.0)                                # turn=0
    a._finalize()

    def world_z(f):
        dg = core.at_frame(f)
        return a.root.evaluated_get(dg).matrix_world.to_euler().z

    z_early, z_mid, z_end = world_z(a._f(2.5)), world_z(a._f(8.5)), world_z(a._f(9.5))
    check("keys: a turn=0 heading does not drift in from the last key", abs(z_mid - z_early) < 1e-3 and abs(z_end - z_early) > 0.5, f"early {z_early:.3f} mid {z_mid:.3f} end {z_end:.3f}")


def arm_keys(a, side, t0, t1):
    f0, f1 = a._f(t0), a._f(t1)
    n = 0
    for jn in (f"sh.{side}", f"el.{side}", f"wr.{side}"):
        for fc in core.fcurves(a.J[jn]):
            if fc.data_path == "rotation_quaternion":
                n += sum(1 for kp in fc.keyframe_points if f0 <= kp.co.x <= f1)
    return n


def t_actions():
    stagekit.begin("a", 8.0, "draft")
    a = cast.actor("x", "Aj_Female_Adult", at=(0, 0), face="right", view="3q")
    c = box_obj("coffee", (0.08, 0.08, 0.1), (0.3, 0.0, 1.0))
    bpy.context.view_layer.update()
    a.hold(c, "R", 0.0, grip=False)
    paper = box_obj("paper", (0.2, 0.01, 0.28), (0.3, 0.1, 1.0))
    a.do("read", paper, t=1.0, until=3.0)
    rk, lk = arm_keys(a, "R", 1.4, 3.0), arm_keys(a, "L", 1.4, 3.0)
    check("actions: read with the right hand full uses the left", rk == 0 and lk > 0 and "paper" in a._held and a._held["paper"][2] == "L", f"R keys {rk}, L keys {lk}")
    a.arm("L", 100, 10, 4.5, 0.2)                          # the shot points with the left arm
    n_before = arm_keys(a, "L", 4.0, 7.0)
    a.do("shout", t=4.0, until=6.0)
    rk, lk = arm_keys(a, "R", 4.2, 6.2), arm_keys(a, "L", 4.0, 7.0)
    check("actions: shout leaves a full hand and a posed hand alone", rk == 0 and lk == n_before, f"R keys {rk}, L keys {n_before} -> {lk}")
    stagekit.begin("a2", 6.0, "draft")
    b = cast.actor("y", "Aj_Female_Adult", at=(0, 0), face="right", view="3q")
    b.do("shout", t=1.0, until=3.0)
    check("actions: shout with free hands still raises the right hand", arm_keys(b, "R", 1.0, 3.0) > 0)


def raycast_clear(pos, targets):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    sc = bpy.context.scene
    bad = []
    for k, q in targets.items():
        q = Vector(q)
        d = q - pos
        start, dn, dist = pos.copy(), d.normalized(), d.length
        for _ in range(12):
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, start, dn, distance=dist - (start - pos).length - 0.01)
            if not hit:
                break
            if ob.get("sk_atmo") or any(c.name == "FX" for c in ob.users_collection):
                start = loc + dn * 0.01
                continue
            bad.append((k, ob.name))
            break
    return bad


def t_set():
    import set_office
    import set_office_lobby as L
    stagekit.begin("s", 1.0, "draft")
    S = L.build_set("rain_day")
    pos = Vector(S["cctv"][0])
    bad = raycast_clear(pos, {"door_mid": (0, 0.1, 1.2), "door_L": (-0.7, 0.1, 1.2), "door_R": (0.7, 0.1, 1.2), "door_top": (0, 0.1, 2.0), "gate_mid": (0, 3.9, 1.0),
                              "gate_L": (-1.3, 3.9, 1.0), "gate_R": (1.3, 3.9, 1.0)})
    check("set: the lobby's CCTV view sees the doors and the gate", not bad, str(bad))
    cards = [o for o in bpy.data.objects if o.get("sk_atmo") == "rain on glass"]
    inside = [p for o in cards for p in o.data.polygons if -0.95 < (o.matrix_world @ p.center).x < 0.95 and (o.matrix_world @ p.center).z < 2.1]
    check("set: the rain-on-glass card leaves the door opening dry", bool(cards) and not inside, f"{len(inside)} card faces across the doorway")
    stagekit.begin("s2", 1.0, "draft")
    set_office.build_set("office_day")
    seat = [o for o in bpy.data.objects if o.get("sk_on") and "chair" in str(o.get("sk_on"))]
    lap = [o for o in bpy.data.objects if o.parent is None and "laptop" in o.name and o.location.z < 0.6]
    check("set: nothing is left lying on an office chair seat", not seat and not lap, f"{len(seat)} pieces on chairs, {len(lap)} low laptops")


def t_bag():
    stagekit.begin("b", 1.0, "draft")
    r = assets.use("prop_messenger_bag", at=(0, 0, 0))
    bpy.context.view_layer.update()
    best, bv = (9.0, 9.0), -1
    for o in r.children_recursive:
        if o.type == "MESH" and len(o.data.vertices) >= 8:
            pts = [o.matrix_world @ v.co for v in o.data.vertices]
            lo = [min(p[i] for p in pts) for i in range(3)]
            hi = [max(p[i] for p in pts) for i in range(3)]
            vol = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
            if vol > bv:
                best, bv = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2), vol
    check("bag: the body is under the origin", abs(best[0]) < 0.003 and abs(best[1]) < 0.003, f"body centre {best[0]:.4f}, {best[1]:.4f}")


def t_rain():
    stagekit.begin("r", 1.0, "draft")
    r = fx.rain(dict(lo=(-6, -6), hi=(6, 6)), intensity=1.0, near=(0, -3, 6), height=8.0)
    m = r["streaks"].data.materials[0]
    kinds = {n.bl_idname for n in m.node_tree.nodes}
    check("rain: streaks fade near the lens and carry a random brightness", "ShaderNodeCameraData" in kinds and "RND" in r["streaks"].data.uv_layers, "")
    sp = r["splashes"].data.materials[0]
    check("rain: splash material builds", sp is not None and len(sp.node_tree.nodes) > 10, "")
    w = fx.window_rain(dict(centre=(0, 0, 2), normal=(0, -1, 0), w=3.0, h=2.0))
    check("rain: window card builds", len(w.data.polygons) == 1, f"{len(w.data.polygons)} faces")
    w2 = fx.window_rain(dict(centre=(0, 0, 2), normal=(0, -1, 0), w=3.0, h=2.0), holes=[((-0.5, -1, 0), (0.5, 1, 1.5))])
    check("rain: window card with a hole", len(w2.data.polygons) == 3, f"{len(w2.data.polygons)} faces")


ALL = {"feet": t_feet, "campath": t_campath, "keys": t_keys, "actions": t_actions, "set": t_set, "bag": t_bag, "rain": t_rain}
want = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(ALL)
for n in want:
    try:
        ALL[n]()
    except Exception:
        import traceback
        traceback.print_exc()
        check(f"{n} ran", False)
print("KITFIX " + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
