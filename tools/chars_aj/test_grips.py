"""Grips on real props (library/assets) and the hand/prop poses of the carrying actions, measured and shown close up.

blender -b --factory-startup --python tools/chars_aj/test_grips.py -- <Body> <out dir> props [prop_id ...]
blender -b --factory-startup --python tools/chars_aj/test_grips.py -- <Body> <out dir> poses [action ...]

props: per library prop the actor picks it up (a.do("pick_up")) and the script measures
  pen_mm        grips.check penetration of the hand skin into the prop's real mesh once the hand has settled (limit 1.5)
  touching      fingers touching it
  jump_mm       distance the prop moves between the last frame before the hold and the first frame of the hold (limit 5)
  settle_mm     how far it moves in the hand (against the Hand bone) in the 12 frames after the hold: the settling into the grip
  grip          the grip type used (power / pen / pinch / palm / palm2) and the report's reason when none fits
and writes <out>/<Body>_<prop>_a.png and _b.png (two close-up angles on the hand and the prop).

poses: per action (pick_up, put_down, carry, hand_over, drink, eat, read, phone, show) the actor performs it with a small
  prop and the script reports, at the end of the action, where the prop and the palm are against the head:
  gap_mm   how far the prop's nearest vertex is from the head sphere (negative = inside the head)
  chin_dz  prop top above the chin (m; positive = the prop reaches above the chin)
  chest_dz prop centre above the chest point (m)
"""
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("SHORTS_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
import bpy                                              # noqa: E402
import numpy as np                                      # noqa: E402
from mathutils import Vector                            # noqa: E402

import stagekit                                         # noqa: E402
from stagekit import aj_hands, assets, cast, core       # noqa: E402
from ajkit import grips                                 # noqa: E402

DEFAULT_PROPS = ["prop_sweep_brush", "prop_walking_cane", "prop_knight_sword", "prop_smith_hammer", "prop_door_key", "prop_fortune_card",
                 "prop_innkeeper_tankard", "prop_librarian_book", "prop_football", "prop_school_bag", "prop_butler_tray",
                 "prop_laundry_basket_modern"]
ACTIONS = ["pick_up", "put_down", "carry", "hand_over", "drink", "eat", "read", "phone", "show"]


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return a[0], Path(a[1]).resolve(), a[2], a[3:]


def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    shot = stagekit.begin("t_grip", 8.0, "draft")
    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -6.0, 1.0)
    cam.rotation_euler = (math.radians(88), 0.0, 0.0)
    return shot, sc, cam


def lighting(sc):
    sc.world = bpy.data.worlds.new("W")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.5, 0.5, 0.55, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (0.9, 0, -0.5)
    sc.collection.objects.link(sun)
    bpy.ops.mesh.primitive_plane_add(size=40)


def prop_points(prop):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in [prop, *prop.children_recursive]:
        if o.type != "MESH":
            continue
        e = o.evaluated_get(dg)
        m = e.to_mesh()
        co = np.empty(len(m.vertices) * 3)
        m.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(e.matrix_world)
        pts.append(co @ mw[:3, :3].T + mw[:3, 3])
        e.to_mesh_clear()
    return np.concatenate(pts) if pts else np.zeros((1, 3))


def hold_frame(a, prop):
    cons = a._held[prop.name][0]
    f = None
    for fc in core.fcurves(prop):
        if fc.data_path.endswith(".influence"):
            for kp in fc.keyframe_points:
                if kp.co.y > 0.5:
                    f = int(round(kp.co.x)) if f is None else min(f, int(round(kp.co.x)))
    return f


def close_up(sc, cam, a, prop, side, path, azim):
    """Two angles on the hand holding the prop: azim 0 = from the front-left, 1 = from the side."""
    f = sc.frame_current
    palm = a.palm[side].matrix_world.translation
    pts = prop_points(prop)
    ctr = (palm + Vector(pts.mean(0))) / 2
    span = max(0.35, float(np.ptp(pts, axis=0).max()) * 0.9)
    d = span * 2.4
    ang = math.radians(-35 if azim == 0 else 90)
    cam.location = ctr + Vector((math.sin(ang) * d, -math.cos(ang) * d, 0.15 * d))
    cam.data.lens = 50
    cam.data.clip_start = 0.02
    dirv = ctr - cam.location
    cam.rotation_euler = dirv.to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 480, 480, 100
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def run_props(body, out, names):
    out.mkdir(parents=True, exist_ok=True)
    for pid in names or DEFAULT_PROPS:
        shot, sc, cam = scene()
        rec = {"body": body, "prop": pid}
        try:
            a = cast.actor("x", body, at=(0.0, 0), face="right", view="side")
            prop = assets.use(pid, name="P", at=(0.0, 0.0, 0.0))
            bpy.context.view_layer.update()
            # the prop stands in front of the figure at hand height (a rod upright, a flat thing flat)
            pts = prop_points(prop)
            lo, hi = pts.min(0), pts.max(0)
            p0 = a.position()
            target = Vector((p0.x + 0.38 * a.scale, p0.y - 0.05, a.hips_height() if hasattr(a, "hips_height") else 0.95 * a.scale))
            prop.location = target - Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)) + Vector((0, 0, 0))
            bpy.context.view_layer.update()
            t_end = a.do("pick_up", prop, t=0.3)
            a.idle(0, shot.seconds)
            a._finalize()
            f0 = hold_frame(a, prop)
            sc.frame_set(f0 - 1)
            before = prop.matrix_world.translation.copy()
            sc.frame_set(f0)
            at0 = prop.matrix_world.translation.copy()
            hb = lambda: a.rig.matrix_world @ a.rig.pose.bones["mixamorig:RightHand"].matrix         # noqa: E731
            def inhand():
                m = hb()
                return m.to_3x3().normalized().transposed() @ (prop.matrix_world.translation - m.translation)
            rel0 = inhand()
            sc.frame_set(f0 + 12)
            settled = inhand()
            rep = grips.check(prop, "Right", arm=a.rig, body=a.mesh, touch_mm=1.5, max_pen_mm=1.5)
            rec.update(pen_mm=rep["penetration_mm"], touching=rep["touching"], ok=rep["ok"],
                       jump_mm=round((at0 - before).length * 1000, 2), settle_mm=round((settled - rel0).length * 1000, 2),
                       hold_frame=f0, grip=getattr(a, "_last_grip", None),
                       notes=[n for n in shot.notes if n.startswith(a.id)][:3])
            lighting(sc)
            sc.frame_set(f0 + 12)
            close_up(sc, cam, a, prop, "R", out / f"{body}_{pid}_a.png", 0)
            close_up(sc, cam, a, prop, "R", out / f"{body}_{pid}_b.png", 1)
        except Exception as e:
            import traceback
            traceback.print_exc()
            rec["error"] = f"{type(e).__name__}: {e}"
        print("GRIP " + json.dumps(rec, default=str))


def run_poses(body, out, names):
    import bmesh
    out.mkdir(parents=True, exist_ok=True)
    for name in names or ACTIONS:
        shot, sc, cam = scene()
        rec = {"body": body, "action": name}
        try:
            a = cast.actor("x", body, at=(0.0, 0), face="right", view="side")
            b = cast.actor("y", body, at=(1.1, 0), face="left", view="side") if name == "hand_over" else None
            cup = bpy.data.objects.new("cup", bpy.data.meshes.new("cup"))
            sc.collection.objects.link(cup)
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.04, radius2=0.045, depth=0.1)
            bm.to_mesh(cup.data)
            bm.free()
            p0 = a.position()
            cup.location = (p0.x + 0.3 * a.scale, p0.y - 0.05, 0.9 * a.scale)
            bpy.context.view_layer.update()
            t = 0.3
            if name == "pick_up":
                t_end = a.do("pick_up", cup, t=t)
            elif name == "put_down":
                a.do("pick_up", cup, t=t)
                t_end = a.do("put_down", cup, t=2.0, to=(p0.x + 0.4 * a.scale, p0.y - 0.05, 0.9 * a.scale))
            elif name == "carry":
                t_end = a.do("carry", cup, t=t)
            elif name == "hand_over":
                a.do("pick_up", cup, t=t)
                t_end = a.do("hand_over", cup, t=2.0, to=b)
            elif name == "drink":
                a.do("pick_up", cup, t=t)
                t_end = a.do("drink", cup, t=2.0)
            elif name == "eat":
                a.do("pick_up", cup, t=t)
                t_end = a.do("eat", cup, t=2.0)
            elif name == "read":
                a.do("pick_up", cup, t=t)
                t_end = a.do("read", cup, t=2.0, until=3.6)
            elif name == "phone":
                a.do("pick_up", cup, t=t)
                t_end = a.do("phone", cup, t=2.0, until=3.6, screen=True)
            elif name == "show":
                a.do("pick_up", cup, t=t)
                t_end = a.do("show", cup, t=2.0)
            else:
                raise SystemExit(f"unknown action {name}")
            for x in (a, b):
                if x is not None:
                    x.idle(0, shot.seconds)
                    x._finalize()
            sc.frame_set(min(shot.frames, shot.f(t_end)))
            hc = a.head.point()
            hr = a.head_r * a.scale
            pts = prop_points(cup)
            d = np.linalg.norm(pts - np.array(hc), axis=1).min()
            top = float(pts[:, 2].max())
            chin = hc.z - hr * 1.0
            chest = a.chest.point().z
            rec.update(gap_mm=round((d - hr) * 1000), chin_dz=round(top - chin, 3), chest_dz=round(float(pts[:, 2].mean()) - chest, 3),
                       head_r_mm=round(hr * 1000))
            lighting(sc)
            for i, (x, y) in enumerate(((0.0, -2.6), (2.4, -1.4))):
                p = a.stage.matrix_world.translation
                cam.location = (p.x + x + 0.3, p.y + y, 1.2 * a.scale)
                dd = Vector((p.x + 0.3, p.y, 1.1 * a.scale)) - cam.location
                cam.rotation_euler = dd.to_track_quat("-Z", "Y").to_euler()
                sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 480, 480, 100
                sc.render.filepath = str(out / f"{body}_pose_{name}_{'ab'[i]}.png")
                bpy.ops.render.render(write_still=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            rec["error"] = f"{type(e).__name__}: {e}"
        print("POSE " + json.dumps(rec))


def main():
    body, out, mode, rest = args()
    {"props": run_props, "poses": run_poses}[mode](body, out, rest)


main()
