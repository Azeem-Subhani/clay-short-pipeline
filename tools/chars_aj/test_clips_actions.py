"""Clip-backed actions on one Aj body, measured and shown as 6-frame strips (side and 3/4).

blender -b --factory-startup --python tools/chars_aj/test_clips_actions.py -- <Body> <out dir> [case ...]

Cases: walk run sneak sit kneel lie fall slip jump salute carry point (default: all). Per case it prints one JSON line:
  slide_cm   worst drift of a foot point that is planted: within 1.2 cm of the floor and moving under 1.5 cm a frame (the
             point is the ball or the ankle, whichever is lower; a new contact or a heel lift restarts it)
  slide_any_cm  the same without the speed condition (a foot swinging past the floor at 1 cm counts too)
  sink_cm    lowest foot point below its standing height (negative = into the floor) on frames the figure is upright
  pop_deg    the largest one-frame change of any joint, against the median one-frame change (entry/exit pops)
  pops       joints whose one-frame change (against their parent) beats their own 5-frame median by more than 12 degrees:
             the count and the worst three as [frame, joint, degrees over the median]
  skin_sink_cm  the lowest vertex of the evaluated body mesh against the floor (negative = into the floor), every 2nd frame
  binding_mm aj_rig.binding_error every 6th frame (the skin following the control rig)
  seat_err_cm for sit with a seat: hip joint height minus (seat top + SEAT_UNDER)
  notes      the shot notes the build wrote (residual problems the code knows about)
and writes <out>/<Body>_<case>_side.png and _3q.png (6 frames side by side)."""
import json
import math
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("SHORTS_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
import bpy                                              # noqa: E402
from mathutils import Vector                            # noqa: E402

import stagekit                                         # noqa: E402
from stagekit import aj_clips, aj_rig, cast             # noqa: E402

ALL = ["walk", "run", "sneak", "sit", "kneel", "lie", "fall", "slip", "jump", "salute", "carry", "point"]


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    body = a[0] if a else "Male_Teen"
    out = Path(a[1]).resolve() if len(a) > 1 else ROOT / "output" / "_staging" / "aj_clips"
    return body, out, a[2:] or ALL


def stage(case, a, shot):
    """Build the case; returns (t_end, frames to show, extra measures)."""
    ex = {}
    if case in ("walk", "run", "sneak"):
        t1 = a.do(case, to=(3.0, 0.0), t=0.3)
        return t1 + 0.4, [0.3, 0.3 + (t1 - 0.3) * 0.25, 0.3 + (t1 - 0.3) * 0.5, 0.3 + (t1 - 0.3) * 0.75, t1 - 0.05, t1 + 0.35], ex
    if case == "sit":
        seat = bpy.data.objects.new("seat", bpy.data.meshes.new("seat"))
        bpy.context.scene.collection.objects.link(seat)
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        bm.to_mesh(seat.data)
        bm.free()
        p = a.position()
        seat.scale = (0.45, 0.45, 0.45)
        back = 0.39 * aj_clips.body(a).k_root * a.scale       # Stand_To_Sit steps back about this far
        seat.location = (p.x - back - 0.05, p.y, 0.225)      # behind the figure (it faces +X); top at 0.45 m
        bpy.context.view_layer.update()
        t1 = a.do("sit_down", t=0.3, on=seat)
        t2 = a.do("sit_idle", t=t1, until=t1 + 1.0)
        t3 = a.do("stand_up", t=t2)
        ex["seat_top"] = 0.45
        ex["seated_t"] = t1 - 0.1
        return t3 + 0.3, [0.3, (0.3 + t1) / 2, t1, t2, (t2 + t3) / 2, t3], ex
    if case == "kneel":
        t1 = a.do("kneel", t=0.3)
        t2 = a.do("stand_up", t=t1 + 0.5)
        return t2 + 0.3, [0.3, (0.3 + t1) / 2, t1, t1 + 0.5, (t1 + t2) / 2, t2], ex
    if case == "lie":
        t1 = a.do("lie_down", t=0.3)
        t2 = a.do("get_up", t=t1 + 0.5)
        return t2 + 0.3, [0.3, (0.3 + t1) / 2, t1, t1 + 0.5, (t1 + t2) / 2, t2], ex
    if case == "idle":
        return 6.0, [0.5, 1.5, 2.5, 3.5, 4.5, 5.5], ex
    if case in ("fall", "slip", "jump", "salute"):
        name = {"fall": "fall", "slip": "slip", "jump": "jump", "salute": "salute"}[case]
        t1 = a.do(name, t=0.3)
        return t1 + 0.4, [0.3 + (t1 - 0.3) * u for u in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)], ex
    if case in ("carry", "point"):
        if case == "carry":
            box = bpy.data.objects.new("box", bpy.data.meshes.new("box"))
            bpy.context.scene.collection.objects.link(box)
            import bmesh
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=0.3)
            bm.to_mesh(box.data)
            bm.free()
            p = a.position()
            box.location = (p.x + 0.3, p.y - 0.05, 0.9)
            try:
                a.do("pick_up", box, t=0.2)
            except Exception as e:                          # the grip path is not this file's to test; say so
                ex["carry_error"] = f"{type(e).__name__}: {e}"
        else:
            try:
                a.do("point", t=0.2, target=(4.0, 0.0, 1.2))
            except Exception as e:
                ex["point_error"] = f"{type(e).__name__}: {e}"
        t1 = a.walk(1.4, (3.0, 0.0), arms=False)
        return t1 + 0.4, [1.4 + (t1 - 1.4) * u for u in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)], ex
    raise SystemExit(f"unknown case {case}")


def measure(a, shot, t_end, ex):
    sc = bpy.context.scene
    fe = min(shot.frames, shot.f(t_end))
    plant = {}
    slide = 0.0
    slide_any = 0.0                                  # the strict reading: every frame within 1.2 cm of the floor, however fast
    plant2, last = {}, {}
    sink = 0.0
    prevJ = None
    steps = []
    jsteps = {}
    skin_low = 9.0
    be = 0.0
    seat_err = None
    for f in range(shot.f(0.3), fe + 1):            # from the action's start (the turn to face the goal comes before)
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        arm = a.rig.evaluated_get(dg)
        upright = getattr(a, "_clip_state", "standing") == "standing"
        for s, side in (("L", "Left"), ("R", "Right")):
            toe = arm.matrix_world @ arm.pose.bones["mixamorig:" + side + "ToeBase"].head
            an = arm.matrix_world @ arm.pose.bones["mixamorig:" + side + "Foot"].head
            lt = toe.z - a.W[f"toe.{s}"].z * a.scale
            la = an.z - a.W[f"an.{s}"].z * a.scale
            kd, pt = ("toe", toe) if lt < la else ("an", an)
            low = min(lt, la)
            sink = min(sink, low)
            if os.environ.get("DUMPFEET") and int(os.environ["DUMPFEET"].split(":")[0]) <= f <= int(os.environ["DUMPFEET"].split(":")[1]):
                print("SLIDE feet", f, s, "an", [round(v, 3) for v in an], "toe", [round(v, 3) for v in toe], "low", round(low * 100, 2))
            if low < 0.012:
                if s in last and last[s][0] == kd and (pt.xy - last[s][1].xy).length < 0.015:      # slow: carrying weight
                    if s not in plant2 or plant2[s][0] != kd:
                        plant2[s] = (kd, last[s][1].copy())
                    slide = max(slide, (pt.xy - plant2[s][1].xy).length)
                else:
                    plant2.pop(s, None)
                last[s] = (kd, pt.copy())
                if s not in plant or plant[s][0] != kd:
                    plant[s] = (kd, pt.copy())
                else:
                    dd = (pt.xy - plant[s][1].xy).length
                    if os.environ.get("ALLSLIDE") and dd > 0.03:
                        print("SLIDE", f, s, kd, round(dd * 100, 1), "low", round(low * 100, 2))
                    slide_any = max(slide_any, dd)
            else:
                plant.pop(s, None)
                plant2.pop(s, None)
                last.pop(s, None)
        W_ = {jn: a.J[jn].matrix_world.to_quaternion() for jn in a.J}
        J = {}
        for jn in aj_rig.JOINTS:
            par = aj_rig.JOINTS[jn][1]
            J[jn] = W_[par].inverted() @ W_[jn]
        if prevJ is not None:
            ds = {j: math.degrees(J[j].rotation_difference(prevJ[j]).angle) for j in J}
            ds = {j: min(d, 360.0 - d) for j, d in ds.items()}
            steps.append(max(ds.values()))
            for j, d in ds.items():
                jsteps.setdefault(j, []).append((f, d))
        prevJ = J
        if f % 2 == 0:
            import numpy as np
            me = a.mesh.evaluated_get(dg)
            m = me.to_mesh()
            co = np.empty(len(m.vertices) * 3)
            m.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            Mw = np.array([list(r) for r in me.matrix_world])
            zz = co @ Mw[2, :3] + Mw[2, 3]
            skin_low = min(skin_low, float(zz.min()))
            if os.environ.get("SINKDBG") and zz.min() < 0.002:
                print("SLIDE sink", f, round(float(zz.min()) * 100, 2), "at", [round(float(v), 3) for v in (co[zz.argmin()])], max(((g.weight, a.mesh.vertex_groups[g.group].name) for g in a.mesh.data.vertices[int(zz.argmin())].groups)))
            me.to_mesh_clear()
        if f % 6 == 0:
            be = max(be, aj_rig.binding_error(a, f))
        if "seated_t" in ex and f == shot.f(ex["seated_t"]):
            hz = (arm.matrix_world @ arm.pose.bones["mixamorig:Hips"].head).z
            seat_err = (hz - (ex["seat_top"] + aj_clips.SEAT_UNDER * aj_clips.body(a).leg * a.scale)) * 100
    med = statistics.median(steps) if steps else 0.0
    pops = []
    for j, lst in jsteps.items():
        for i, (fr_, d) in enumerate(lst):
            loc = statistics.median(x[1] for x in lst[max(0, i - 2):i + 3])
            if d - loc > 12.0:
                pre = getattr(a, "_pre_steps", {}).get((fr_, j))
                pops.append([fr_, j, round(d - loc, 1), None if pre is None else round(pre, 1)])
    pops.sort(key=lambda p: -p[2])
    # a pop is the clip's own motion when the clip turns that joint as fast in that frame; ours when it does not
    ours = [p for p in pops if p[3] is None or (p[2] + statistics.median([x[1] for x in jsteps[p[1]]]) - p[3]) > 12.0]
    return {"pops_n": len(pops), "pops_ours": len(ours), "pops_top": ours[:8], "skin_sink_cm": round((skin_low - 0.0) * 100, 2),
            **_legacy(med, steps, slide, sink, be, seat_err), "slide_any_cm": round(slide_any * 100, 2)}


def _legacy(med, steps, slide, sink, be, seat_err):
    return {"slide_cm": round(slide * 100, 2), "sink_cm": round(sink * 100, 2), "pop_deg": round(max(steps or [0]), 1),
            "median_step_deg": round(med, 2), "binding_mm": round(be, 3),
            "seat_err_cm": None if seat_err is None else round(seat_err, 2)}


def strip(shot, a, times, path, cam_xy, look_z=0.8):
    sc = bpy.context.scene
    cam = sc.camera
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 240, 320, 100
    sc.render.film_transparent = False
    tiles = []
    for i, tt in enumerate(times):
        f = max(1, min(shot.frames, shot.f(tt)))
        sc.frame_set(f)
        p = a.stage.matrix_world.translation
        cam.location = (p.x + cam_xy[0], p.y + cam_xy[1], 1.0)
        d = Vector((p.x, p.y, look_z)) - cam.location
        cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        tp = path.with_name(path.stem + f"_{i}.png")
        sc.render.filepath = str(tp)
        bpy.ops.render.render(write_still=True)
        tiles.append(tp)
    imgs = [bpy.data.images.load(str(t)) for t in tiles]
    w, h = imgs[0].size
    out = bpy.data.images.new(path.stem, w * len(imgs), h)
    px = [0.0] * (w * len(imgs) * h * 4)
    for k, im in enumerate(imgs):
        src = list(im.pixels)
        for y in range(h):
            a0 = (y * w * len(imgs) + k * w) * 4
            px[a0:a0 + w * 4] = src[y * w * 4:(y + 1) * w * 4]
    out.pixels = px
    out.filepath_raw = str(path)
    out.file_format = "PNG"
    out.save()
    for t in tiles:
        t.unlink()


def main():
    body, out, cases = args()
    out.mkdir(parents=True, exist_ok=True)
    for case in cases:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        shot = stagekit.begin(f"t_{case}", 12.0, "draft")
        sc = bpy.context.scene
        cd = bpy.data.cameras.new("cam")
        cam = bpy.data.objects.new("cam", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.location = (0.0, -6.0, 1.0)                       # the scene camera before the actor: "right" is +X
        cam.rotation_euler = (math.radians(88), 0.0, 0.0)
        bpy.context.view_layer.update()
        a = cast.actor("x", body, at=(-1.0, 0), face="right", view="side")
        rec = {"body": body, "case": case}
        try:
            t_end, times, ex = stage(case, a, shot)
            a.idle(0, shot.seconds)
            a._finalize()
            rec.update(measure(a, shot, t_end, ex))
            rec.update({k: v for k, v in ex.items() if k.endswith("error")})
            rec["ground"] = [{k: v for k, v in g.items() if k != "f1"} for g in getattr(a, "_ground_log", [])] if os.environ.get("GROUNDLOG") else None
            if os.environ.get("GROUNDLOG") and getattr(a, "_last_walk", None):
                rec["walk"] = a._last_walk
            rec["notes"] = [n for n in shot.notes if n.startswith(a.id)][:6]
            w = bpy.data.worlds.new("W")
            sc.world = w
            sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
            sun.data.energy = 3
            sun.rotation_euler = (0.9, 0, -0.5)
            sc.collection.objects.link(sun)
            bpy.ops.mesh.primitive_plane_add(size=40)
            strip(shot, a, times, out / f"{body}_{case}_side.png", (0.0, -4.2))
            strip(shot, a, times, out / f"{body}_{case}_3q.png", (2.6, -3.3))
        except aj_clips.MissingClip as e:
            rec["missing"] = e.name
        except Exception as e:
            import traceback
            traceback.print_exc()
            rec["error"] = f"{type(e).__name__}: {e}"
        print("CASE " + json.dumps(rec))


main()
