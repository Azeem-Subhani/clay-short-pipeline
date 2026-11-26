"""Clip-backed actions on one Aj body, measured and shown as 6-frame strips (side and 3/4).

blender -b --factory-startup --python tools/chars_aj/test_clips_actions.py -- <Body> <out dir> [case ...]

Cases: walk run sneak sit kneel lie fall slip jump salute carry point (default: all). Per case it prints one JSON line:
  slide_cm   worst drift of a foot point while it is within 1.2 cm of the floor (the point is the ball or the ankle,
             whichever is lower; a new contact or a heel lift restarts it)
  sink_cm    lowest foot point below its standing height (negative = into the floor) on frames the figure is upright
  pop_deg    the largest one-frame change of any joint, against the median one-frame change (entry/exit pops)
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
    out = Path(a[1]) if len(a) > 1 else ROOT / "output" / "_staging" / "aj_clips"
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
    sink = 0.0
    prevJ = None
    steps = []
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
            if low < 0.012:
                if s not in plant or plant[s][0] != kd:
                    plant[s] = (kd, pt.copy())
                else:
                    dd = (pt.xy - plant[s][1].xy).length
                    if os.environ.get("ALLSLIDE") and dd > 0.03:
                        print("SLIDE", f, s, kd, round(dd * 100, 1), "low", round(low * 100, 2))
                    slide = max(slide, dd)
            else:
                plant.pop(s, None)
        J = {jn: a.J[jn].matrix_world.to_quaternion() for jn in a.J}
        if prevJ is not None:
            steps.append(max(min(d, 360.0 - d) for d in (math.degrees(J[j].rotation_difference(prevJ[j]).angle) for j in J)))
        prevJ = J
        if f % 6 == 0:
            be = max(be, aj_rig.binding_error(a, f))
        if "seated_t" in ex and f == shot.f(ex["seated_t"]):
            hz = (arm.matrix_world @ arm.pose.bones["mixamorig:Hips"].head).z
            seat_err = (hz - (ex["seat_top"] + aj_clips.SEAT_UNDER * aj_clips.body(a).leg * a.scale)) * 100
    med = statistics.median(steps) if steps else 0.0
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
