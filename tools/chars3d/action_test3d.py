"""action_test3d.py - perform named actions on ONE 3D character in a plain test scene and measure every frame.

    blender -b --factory-startup --python action_test3d.py -- --char Queen --out <abs dir> [--actions a,b,c | --set core|all]
            [--view 3q] [--face right] [--render a,b] [--px 300] [--pipeline <root>] [--other AdultMan]

For each action: the figure, and whatever the action needs (a prop on a block, a target post, a destination, a second
character), exactly as the 2D tests set them up. Measured on every frame:
  held_gap    how far a held prop is from the palm that holds it (metres)             -> hands keep hold of props
  foot_slide  how far a foot that is on the ground moved since the last frame          -> no skating
  sunk        how far the lowest foot is below the ground                              -> nothing sinks through the floor
  reach_min   the closest the acting palm came to a thing the action must touch        -> hands land on things
Writes <out>/<char>.json. --render also writes frames (every 2nd) to <out>/<char>/<action>/NNNN.png.
"""
import argparse
import json
import math
import os
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Vector

_W = Path(__file__).resolve().parents[1]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[2]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--actions", default="")
ap.add_argument("--set", default="core")
ap.add_argument("--view", default="3q")
ap.add_argument("--face", default="right")
ap.add_argument("--render", default="")
ap.add_argument("--px", type=int, default=300)
ap.add_argument("--pipeline", default=str(_PIPE))
ap.add_argument("--other", default="AdultMan")
a = ap.parse_args(argv)
os.environ["SHORTS_PROJECT"] = a.pipeline
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import actions, cast, core  # noqa: E402

CORE = ["walk", "run", "point", "pick_up", "hold_up", "hand_over", "gasp", "talk", "sit_down", "wave", "laugh", "crouch"]
TOUCH = {"pick_up": 0.07, "press": 0.07, "knock": 0.09, "turn_key": 0.08, "push": 0.10, "pull": 0.10, "lift": 0.09, "receive": 0.09, "open_door": 0.10}
names = [n for n in a.actions.split(",") if n] or (CORE if a.set == "core" else list(actions.ACTIONS))
render = set(n for n in a.render.split(",") if n)
out = Path(a.out).resolve()
out.mkdir(parents=True, exist_ok=True)
LEN = 9.0
F = 1 if a.face == "right" else -1


def flat(name, col):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = 0.8
    return m


def box(name, size, at, col):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + size[2] / 2))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    ob.data.materials.append(flat("m_" + name, col))
    return ob


def one(action):
    spec = actions.ACTIONS[action]
    needs = spec["needs"]
    shot = stagekit.begin("actiontest", LEN, "draft")
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = a.px, int(a.px * 4 / 3)
    sc.render.resolution_percentage = 100
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.84, 0.78, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    sc.world = w
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(-30))
    sc.collection.objects.link(sun)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    bpy.context.active_object.data.materials.append(flat("ground", (0.70, 0.66, 0.58)))
    moving = spec["group"] == "moving" and "to" in needs or action in ("chase", "haul", "roll", "crawl")
    x0 = -0.9 * F if moving else (-0.35 * F if needs else 0.0)
    cd = bpy.data.cameras.new("cam")
    cd.lens = 50
    cam = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (0.0, -4.2, 0.95)
    cam.rotation_euler = (math.radians(88), 0, 0)
    act = cast.actor("x", a.char, at=(x0, 0), face=a.face, view=a.view)
    H = act.height
    cam.location = (0.0, -(4.4 if moving or "other" in needs else 3.5) * max(0.75, H / 1.7), H * 0.56)
    kw, target = {}, None
    if action == "slip_banana":
        target = box("peel", (0.16, 0.10, 0.02), (x0 + 0.55 * F, -0.02, 0.0), (0.95, 0.82, 0.2))
    elif "prop" in needs or action in ("hold_up", "show", "use_tool", "pour", "drink", "eat", "read", "write", "phone", "stash", "take_out"):
        if action in ("pick_up", "lift", "receive", "haul"):
            hgt = 0.0 if action == "haul" else 0.34 * H
            if hgt:
                box("stand", (0.3, 0.3, hgt), (x0 + 0.52 * F, 0.0, 0), (0.55, 0.5, 0.45))
            target = box("prop", (0.11, 0.11, 0.11), (x0 + 0.52 * F, -0.02, hgt), (0.92, 0.72, 0.2))
        else:
            target = box("prop", (0.05, 0.05, 1.0) if action == "use_tool" else (0.1, 0.1, 0.12), (x0 + 0.3 * F, 0.0, 0.45 * H), (0.92, 0.72, 0.2))
            if action == "take_out":
                core.show(target, 0.0, False)
        shot.props["prop"] = target
    if action == "juggle":
        kw["props"] = []
        for i, col in enumerate(((0.9, 0.3, 0.25), (0.25, 0.55, 0.9), (0.95, 0.8, 0.2))):
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.045 * max(0.6, H / 1.7), location=(x0, -0.1, 0.5 + 0.1 * i), segments=16, ring_count=8)
            b_ = bpy.context.active_object
            b_.data.materials.append(flat(f"m_ball{i}", col))
            kw["props"].append(b_)
    if "target" in needs:
        far_ = action in ("point", "aim", "watch", "inspect")
        arm = act.arm_length()
        shz = act.shoulder_height()
        target = box("post", (0.08, 0.08, 0.08), (x0 + (0.62 if far_ else 0.62 * arm) * F, -0.16 if not far_ else 0.0, 0.52 * H if far_ else shz - 0.3 * arm),
                     (0.8, 0.25, 0.2))
    if "other" in needs or action in ("hand_over", "whisper"):
        other = cast.actor("y", a.other, at=(x0 + 0.95 * F, 0), face="left" if F > 0 else "right", view=a.view)
        if "other" in needs:
            target = other
        else:
            kw["to" if action == "hand_over" else "target"] = other
            if action == "whisper":
                target = other
                kw.pop("target", None)
    if "to" in needs and action != "hand_over":
        if action == "climb":
            kw["to"] = (x0, 0.0, 0.8)
        elif action == "put_down":
            box("stand", (0.3, 0.3, 0.34 * H), (x0 + 0.52 * F, 0.0, 0), (0.55, 0.5, 0.45))
            kw["to"] = (x0 + 0.52 * F, -0.02, 0.34 * H + 0.06)
        else:
            kw["to"] = (x0 + (0.9 if action in ("sneak", "tiptoe", "crawl", "haul") else 1.8) * F, 0.0, 0.0)
    T0 = 0.35
    if action in ("put_down", "throw", "drop", "hand_over"):
        act.hold(target, "R", 0.05)
        act.arm("R", 52, 66, 0.1, 0.0)
    if action == "stand_up":
        act.pose("sit", 0.05, 0.0)
    if action in ("get_up", "wake_up"):
        act.do("lie_down", t=0.0, speed=4.0)
        T0 = 0.6
    args = [target] if target is not None else []
    t_end = act.do(action, *args, t=T0, **kw)
    t_end = min(LEN - 0.2, max(t_end, T0 + 0.3) + 0.35)
    act.idle(0.0, t_end)
    for a_ in shot.actors.values():
        a_._finalize()
    f_end = shot.f(t_end)
    sc.frame_end = f_end
    res = {"frames": f_end, "held_gap": 0.0, "foot_slide": 0.0, "sunk": 0.0, "reach_min": None}
    prev = None
    prev_yaw = None
    lying = action in ("lie_down", "sleep", "fall", "slip", "slip_banana", "crawl", "roll", "get_up", "wake_up", "swim", "kneel", "plead", "hang", "climb")
    tgt_ob = target if (target is not None and hasattr(target, "matrix_world")) else None
    for f in range(1, f_end + 1):
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        for pname, h in act._held.items():
            pr = bpy.data.objects.get(pname)
            if pr is None or h[0][0].influence < 0.999:
                continue
            gap = (pr.evaluated_get(dg).matrix_world.translation - h[1].evaluated_get(dg).matrix_world.translation).length
            res["held_gap"] = max(res["held_gap"], gap)
        feet = {s: act.J[f"an.{s}"].evaluated_get(dg).matrix_world.translation.copy() for s in "LR"}
        if not lying:
            rest = act.b["ankle_z"] * act.scale
            low = min(v.z for v in feet.values())
            res["sunk"] = max(res["sunk"], rest - low - 0.0)
            yaw = act.root.evaluated_get(dg).matrix_world.to_euler().z
            turning = prev_yaw is not None and abs(math.atan2(math.sin(yaw - prev_yaw), math.cos(yaw - prev_yaw))) > 0.012
            prev_yaw = yaw
            if prev is not None and not turning:               # a figure turning on the spot re-plants its feet: not a slide
                for s in "LR":
                    if feet[s].z < rest + 0.012 and prev[s].z < rest + 0.012:
                        res["foot_slide"] = max(res["foot_slide"], (Vector((feet[s].x, feet[s].y)) - Vector((prev[s].x, prev[s].y))).length)
        prev = feet
        if action in TOUCH and tgt_ob is not None:
            d = min((act.palm[s].evaluated_get(dg).matrix_world.translation - tgt_ob.evaluated_get(dg).matrix_world.translation).length for s in "LR")
            res["reach_min"] = d if res["reach_min"] is None else min(res["reach_min"], d)
        if action in render and f % 2 == 1:
            fd = out / a.char / action
            fd.mkdir(parents=True, exist_ok=True)
            sc.render.filepath = str(fd / f"{(f + 1) // 2:04d}.png")
            bpy.ops.render.render(write_still=True)
    fails = []
    if res["held_gap"] > 0.03:
        fails.append(f"a held prop is {res['held_gap'] * 100:.1f} cm from the palm")
    walking = action in ("walk", "run", "sneak", "tiptoe", "pace", "chase", "step_forward", "carry")
    if res["foot_slide"] > (0.035 if walking else 0.06):
        fails.append(f"a foot on the ground moves {res['foot_slide'] * 100:.1f} cm in one frame")
    if res["sunk"] > 0.04:
        fails.append(f"a foot is {res['sunk'] * 100:.1f} cm below the ground")
    if action in TOUCH and res["reach_min"] is not None and res["reach_min"] > TOUCH[action] + 0.06:
        fails.append(f"the palm never comes closer than {res['reach_min'] * 100:.1f} cm to the thing")
    res = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}
    res["fails"] = fails
    res["pass"] = not fails
    return res


results = {}
for n in names:
    try:
        results[n] = one(n)
    except Exception as ex:
        tb = traceback.format_exc().strip().splitlines()
        results[n] = {"pass": False, "fails": [f"error: {type(ex).__name__}: {ex}"], "trace": tb[-6:]}
    print("ACTION", a.char, n, "PASS" if results[n]["pass"] else "FAIL " + "; ".join(results[n]["fails"]), flush=True)
(out / f"{a.char}.json").write_text(json.dumps({"char": a.char, "view": a.view, "face": a.face, "results": results}, indent=1), encoding="utf-8")
ok = sum(1 for r in results.values() if r["pass"])
print(f"ACTIONS_DONE {a.char}: {ok}/{len(results)} pass")
