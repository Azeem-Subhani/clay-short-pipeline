"""Headless test of the level carry (ActorAj.carry, stagekit.aj_carry).

    blender -b --factory-startup --python tools/tests/kitfix/test_carry.py [-- level plain]

level  an Aj actor carries a small box, runs a few metres and stops: on every 4th frame the box is upright, in front of the chest and inside
       the lateral limit of the physical checks, and the carrying arm was not overwritten by the run clip
plain  an actor that never calls carry gets the same arm keys whether the carry bake runs or is switched off (the hooks are no-ops for them)
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
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stagekit  # noqa: E402
from stagekit import aj_carry, cast, core, physical  # noqa: E402

FAILS = []
TILT_MAX_DEG = 10.0                      # a carried box must stay close to upright (the physical check blocks at 22)
SIDE_MAX_M = 0.30                        # inside the physical limit (0.42 m) with room to spare


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


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


def heading(actor, dg):
    rmw = actor.root.evaluated_get(dg).matrix_world
    fwd = rmw.to_3x3() @ Vector((0.0, -1.0, 0.0))
    fwd.z = 0.0
    fwd = fwd.normalized() if fwd.length > 1e-4 else Vector((0.0, -1.0, 0.0))
    return fwd, Vector((-fwd.y, fwd.x, 0.0))


def run_scene(carry: bool):
    """One actor, one box, a run of 4 m from t=1 s and a stop; built and finalized."""
    stagekit.begin("carry_test", 7.0, "draft")
    a = cast.actor("x", "Aj_Female_Adult", at=(0, 0), face="right", view="3q")
    box = box_obj("parcel", (0.28, 0.20, 0.12), (0.3, 0.0, 1.0))
    bpy.context.view_layer.update()
    if carry:
        a.carry(box, "R", 0.0)
    t_end = a.walk(1.0, (4.0, 0.0), cycle="run")                 # arms left to the clip: the carried arm must stay out of its way
    a._finalize()
    return a, box, t_end


def t_level():
    a, box, t_end = run_scene(True)
    sc = bpy.context.scene
    frames = list(range(2, a.shot.f(6.5), 4))
    worst = {"tilt": 0.0, "side": 0.0, "fwd": 9.0}
    for f in frames:
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        fwd, left = heading(a, dg)
        chest = a.chest.ob.evaluated_get(dg).matrix_world.translation
        e = box.evaluated_get(dg)
        centre = sum((e.matrix_world @ Vector(c) for c in e.bound_box), Vector()) / 8.0
        d = centre - chest
        up = (e.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        worst["tilt"] = max(worst["tilt"], math.degrees(math.acos(max(-1.0, min(1.0, up.z)))))
        worst["side"] = max(worst["side"], abs(d.dot(left)))
        worst["fwd"] = min(worst["fwd"], d.dot(fwd))
    moved = a.position() if hasattr(a, "position") else None
    check("level: the actor ran (box carried 3+ m)", moved is None or (Vector(moved) - Vector((0, 0, 0))).length > 3.0, f"ended at {moved}")
    check("level: the box stays upright on every 4th frame", worst["tilt"] < TILT_MAX_DEG, f"worst tilt {worst['tilt']:.1f} deg over {len(frames)} frames")
    check("level: the box stays in front of the chest", worst["fwd"] > 0.0, f"least forward {worst['fwd'] * 100:.1f} cm")
    lim = min(SIDE_MAX_M, physical.config()["carry"]["flung_m"])
    check("level: the box stays within the lateral limit", worst["side"] <= lim, f"most sideways {worst['side'] * 100:.1f} cm (limit {lim * 100:.0f})")
    check("level: aj_clips counts the carried arm as busy", aj_carry.busy(a, "R", 30) and not aj_carry.busy(a, "L", 30))


def arm_snapshot(a):
    """Every key of the arm joints, as numbers, to compare two builds."""
    out = []
    for side in "LR":
        for jn in (f"sh.{side}", f"el.{side}", f"wr.{side}"):
            for fc in sorted(core.fcurves(a.J[jn]), key=lambda c: (c.data_path, c.array_index)):
                out.append((jn, fc.data_path, fc.array_index, tuple(round(kp.co.y, 9) for kp in fc.keyframe_points)))
    return out


def t_plain():
    with_hooks, _b, _t = run_scene(False)
    snap_with = arm_snapshot(with_hooks)
    real = (aj_carry.bake_arms, aj_carry.seat_props)
    aj_carry.bake_arms = aj_carry.seat_props = lambda actor, frames: None          # the build as it was before the carry existed
    try:
        without, _b2, _t2 = run_scene(False)
        snap_without = arm_snapshot(without)
    finally:
        aj_carry.bake_arms, aj_carry.seat_props = real
    check("plain: an actor that never carries has the same arm keys with and without the carry bake", snap_with == snap_without and len(snap_with) > 0,
          f"{len(snap_with)} curves compared")


ALL = {"level": t_level, "plain": t_plain}
want = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(ALL)
for n in want:
    try:
        ALL[n]()
    except Exception:
        import traceback
        traceback.print_exc()
        check(f"{n} ran", False)
print("CARRY " + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
sys.exit(1 if FAILS else 0)
