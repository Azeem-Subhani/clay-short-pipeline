"""One action, one character, one view and facing, in a plain test scene (NOT a pipeline set or clip).

    blender -b --factory-startup --python action_test.py -- --char Soldier --action pick_up --view 3q --face right
        --pack <library.blend> --out <abs dir> [--px 360] [--other AdultMan] [--no-render] [--strip-step 2] [--scale 1.0]

Builds: a neutral backdrop, a ground plane, a Shorts-shaped perspective camera, the character, and whatever the action
needs (a small prop on a block, a target post, a destination, a second character). Performs the action through
actor.do(...), measures every frame (written to <out>/<char>/<action>__<view>_<face>.json) and renders all frames
(<...>/frames/NNNN.png). work/tools/action_media.py turns the frames into the strip PNG and the MP4.

Measured per frame, for stagekit's own bones (so it is the pose the renderer gets):
  joint_gap      largest distance between a limb part's joint and the part below it (metres)       -> arms / legs joined
  held_gap       distance on screen between a held prop and the palm (metres at the figure)        -> hands grip props
  foot_slide     how far a planted foot moved along the ground since the last frame (metres)       -> no foot sliding
  hand_side      +1 if the acting hand is on the target's side of the body, -1 if not               -> no reversed arms
  elbow_flex     elbow angle signed so that + is the way an elbow folds in that view               -> no arm bent backward
  lifted / over_head   whether the hand parts are drawn in front of the head when the palm is over it -> depth order
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector

_W = Path(__file__).resolve().parents[2]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[3]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True)
ap.add_argument("--action", required=True)
ap.add_argument("--view", default="3q")
ap.add_argument("--face", default="right")
ap.add_argument("--out", required=True)
ap.add_argument("--pack", default=None)
ap.add_argument("--pipeline", default=str(_PIPE))
ap.add_argument("--px", type=int, default=360)
ap.add_argument("--other", default="AdultMan")
ap.add_argument("--chars-dir", default=None, help="folder of per-character .blend files: each character is loaded from its own small file")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--scale", type=float, default=1.0)
ap.add_argument("--samples", type=int, default=8)
ap.add_argument("--speed", type=float, default=1.0)
ap.add_argument("--frame-step", type=int, default=1, help="render every Nth frame (measurements always cover every frame)")
a = ap.parse_args(argv)
if a.pack:
    os.environ["CAST_PACK"] = a.pack
os.environ["SHORTS_PROJECT"] = a.pipeline
os.environ.setdefault("CAST_CULL_VIEWS", "1")      # render only the drawing that shows (3x faster test frames)
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import actions, cast, core  # noqa: E402

spec = actions.ACTIONS[a.action]
needs = spec["needs"]
LEN = 9.0
shot = stagekit.begin("actiontest", LEN, "draft")
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y = a.px, int(a.px * 4 / 3)
sc.render.resolution_percentage = 100
sc.eevee.taa_render_samples = a.samples
for nm, val in (("use_raytracing", False), ("use_fast_gi", False), ("use_shadows", False)):
    try:
        setattr(sc.eevee, nm, val)
    except Exception:
        pass
w = bpy.data.worlds.new("W")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.84, 0.78, 1)
sc.world = w
sc.view_settings.view_transform = "Standard"


def flat(name, col):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes.clear()
    e = m.node_tree.nodes.new("ShaderNodeEmission")
    e.inputs[0].default_value = (*col, 1)
    o = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    m.node_tree.links.new(e.outputs[0], o.inputs[0])
    return m


def box(name, size, at, col):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + size[2] / 2))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    ob.data.materials.append(flat("m_" + name, col))
    return ob


bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
bpy.context.active_object.data.materials.append(flat("ground", (0.70, 0.66, 0.58)))
F = 1 if a.face == "right" else -1
moving = spec["group"] == "moving" and "to" in needs or a.action in ("chase", "haul", "roll", "crawl")
x0 = -0.9 * F if moving else (-0.35 * F if needs else 0.0)
def use_pack(name):
    """point the cast at the small per-character file when there is one (much faster than the whole library)"""
    if a.chars_dir and (Path(a.chars_dir) / f"{name}.blend").exists():
        os.environ["CAST_PACK"] = str(Path(a.chars_dir) / f"{name}.blend")


use_pack(a.char)
act = cast.actor("x", a.char, at=(x0, 0), face=a.face, view=a.view, scale=a.scale)
cd = bpy.data.cameras.new("cam")
cd.lens = 50
cam = bpy.data.objects.new("cam", cd)
sc.collection.objects.link(cam)
H = act.height
cam.location = (0.0, -(4.4 if moving or "other" in needs else 3.5) * max(0.75, H / 1.7), H * 0.56)
cam.rotation_euler = (math.radians(88), 0, 0)
sc.camera = cam
act._billboard(cam)
cast.look("#FFFFFF", lit=0.0)

kw = {}
target = None
reach_z = 0.0
if a.action == "slip_banana":
    pass
elif "prop" in needs or a.action in ("hold_up", "show", "use_tool", "pour", "drink", "eat", "read", "write", "phone", "stash", "take_out"):
    stand = None
    if a.action in ("pick_up", "lift", "receive", "haul"):
        low = a.action in ("haul",)
        hgt = 0.0 if low else 0.34 * H
        if hgt:
            stand = box("stand", (0.3, 0.3, hgt), (x0 + 0.52 * F * a.scale, 0.0, 0), (0.55, 0.5, 0.45))
        target = box("prop", (0.11, 0.11, 0.11), (x0 + 0.52 * F * a.scale, -0.02, hgt), (0.92, 0.72, 0.2))
    else:
        long_ = a.action == "use_tool"
        target = box("prop", (0.05, 0.05, 1.0) if long_ else (0.1, 0.1, 0.12), (x0 + 0.3 * F, 0.0, 0.9 * H * 0.5), (0.92, 0.72, 0.2))
        if a.action == "take_out":
            core.show(target, 0.0, False)
    shot.props["prop"] = target
if a.action == "juggle":                                 # three small balls
    kw["props"] = []
    for i, col in enumerate(((0.9, 0.3, 0.25), (0.25, 0.55, 0.9), (0.95, 0.8, 0.2))):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.045 * max(0.6, H / 1.7), location=(x0, -0.1, 0.5 + 0.1 * i), segments=16, ring_count=8)
        b_ = bpy.context.active_object
        b_.name = f"ball{i}"
        b_.data.materials.append(flat(f"m_ball{i}", col))
        kw["props"].append(b_)
if a.action == "slip_banana":                            # a flat yellow peel one step ahead
    target = box("peel", (0.16, 0.10, 0.02), (x0 + 0.55 * F * a.scale, -0.02, 0.0), (0.95, 0.82, 0.2))
if "target" in needs:
    far_ = a.action in ("point", "aim", "watch", "inspect")          # things looked or pointed at are out of reach; things touched are not
    _c = act._calib[act._view_key()]
    _arm = (_c["arm_upper.R"][3] + _c["arm_lower.R"][3]) * a.scale
    _shz = float(act.rigs[act._view_key()].data.bones["arm_upper.R"].head_local.z) * a.scale
    # a touched thing stands within reach of the ACTING shoulder: on a body whose shoulder sits back from its centre line
    # (the ghost in 3/4) the same distance from the centre would be out of reach of a straight arm
    _shx = float(act.rigs[act._view_key()].data.bones["arm_upper.R"].head_local.x) * act._mirror() * a.scale * F
    _near = 0.72 * _arm + min(0.0, _shx)
    target = box("post", (0.08, 0.08, 0.08), (x0 + (0.62 if far_ else _near) * F, 0.0, 0.52 * H if far_ else _shz - 0.3 * _arm), (0.8, 0.25, 0.2))
if "other" in needs or a.action in ("hand_over", "whisper"):
    use_pack(a.other)
    other = cast.actor("y", a.other, at=(x0 + 0.95 * F, 0), face="left" if F > 0 else "right", view=a.view)
    other._billboard(cam)
    if "other" in needs:
        target = other
    else:
        kw["to" if a.action == "hand_over" else "target"] = other
        if a.action == "whisper":
            target = other
            kw.pop("target", None)
if "to" in needs and a.action != "hand_over":
    if a.action == "climb":
        kw["to"] = (x0, 0.0, 0.8)
    elif a.action == "put_down":
        box("stand", (0.3, 0.3, 0.34 * H), (x0 + 0.52 * F * a.scale, 0.0, 0), (0.55, 0.5, 0.45))
        kw["to"] = (x0 + 0.52 * F * a.scale, -0.02, 0.34 * H + 0.06)
    else:
        kw["to"] = (x0 + (0.9 if a.action in ("sneak", "tiptoe", "crawl", "haul") else 1.8) * F, 0.0, 0.0)
T0 = 0.35
if a.action in ("put_down", "throw", "drop", "hand_over"):
    act.hold(target, "R", 0.05)
    act.arm("R", 52, 66, 0.1, 0.0)
if a.action in ("stand_up",):
    act.pose("sit", 0.05, 0.0)
if a.action in ("get_up", "wake_up"):
    act.do("lie_down", t=0.0, speed=4.0)
    T0 = 0.6
args = [target] if target is not None else []
t_end = act.do(a.action, *args, t=T0, speed=a.speed, **kw)
t_end = min(LEN - 0.2, max(t_end, T0 + 0.3) + 0.35)
act.idle(0.0, t_end)
f_end = shot.f(t_end)
sc.frame_end = f_end

if a.no_render:                # measuring needs bones and transforms only: skip building the ink geometry on every frame
    for o_ in bpy.data.objects:
        md_ = o_.modifiers.get("Outline") if o_.type == "MESH" else None
        if md_ is not None:
            md_.show_viewport = False

# ----------------------------------------------------------------------------- measurements
view_key = act._view_key()
side = "R"
out = Path(a.out).resolve() / a.char
out.mkdir(parents=True, exist_ok=True)
tag = f"{a.action}__{a.view}_{a.face}"
rows = []
prev_feet = None
ground = None


def world(rig_e, v):
    return rig_e.matrix_world @ v


def on_screen(p, q):
    """distance between two world points as the camera sees them, in metres at the depth of q (the figure)"""
    cmat = cam.matrix_world.inverted()
    a2, b2 = cmat @ p, cmat @ q
    a2 = Vector((a2.x / -a2.z, a2.y / -a2.z)) * -b2.z
    return (Vector((b2.x, b2.y)) - a2).length


cam_right = cam.matrix_world.to_3x3() @ Vector((1, 0, 0))
for f in range(1, f_end + 1):
    dg = core.at_frame(f)
    vk = {0: "Front", 1: "ThreeQuarter", 2: "Side"}[int(act.root.evaluated_get(dg)["view"])]
    rig = act.rigs[vk].evaluated_get(dg)
    pb = rig.pose.bones
    row = {"f": f, "view": vk}
    # joints: a lower part must start exactly where its upper part ends
    gap = 0.0
    par = 0.0
    for up_, lo_ in (("arm_upper", "arm_lower"), ("arm_lower", "hand"), ("leg_upper", "leg_lower"), ("leg_lower", "foot")):
        for s_ in "LR":
            gap = max(gap, (world(rig, pb[f"{up_}.{s_}"].tail) - world(rig, pb[f"{lo_}.{s_}"].head)).length)
    for o in act.parts:
        if o["cl_view"] != vk or "_Lower." not in o["cl_part"]:
            continue
        upn = o["cl_part"].replace("_Lower.", ".")
        uo = next((q for q in act.parts if q["cl_view"] == vk and q["cl_part"] == upn), None)
        if uo is not None:
            inv = rig.matrix_world.inverted()
            pa, pc = inv @ o.evaluated_get(dg).matrix_world.translation, inv @ uo.evaluated_get(dg).matrix_world.translation
            gap = max(gap, math.hypot(pa.x - pc.x, pa.z - pc.z))      # in the figure's own plane: layers differ in depth by design
            par = max(par, on_screen(o.evaluated_get(dg).matrix_world.translation, uo.evaluated_get(dg).matrix_world.translation))
    row["joint_gap"] = round(max(0.0, gap), 5)
    row["parallax"] = round(par, 4)             # how far the camera's perspective shifts a lifted forearm against its upper arm
    # elbow: + = folds the way an elbow does in this drawing
    tw = act._toward(vk)
    for s_ in "LR":
        u = pb[f"arm_upper.{s_}"]
        l_ = pb[f"arm_lower.{s_}"]
        du, dl = (u.tail - u.head), (l_.tail - l_.head)
        au, al = math.atan2(du.x, -du.z), math.atan2(dl.x, -dl.z)
        fl = math.degrees((al - au + math.pi) % math.tau - math.pi)
        row[f"elbow_{s_}"] = round(fl * (tw if vk != "Front" else 1.0), 1)
    # held props: on screen the prop must sit in the palm
    hg = 0.0
    for pname, h_ in act._held.items():
        s_ = h_[2]
        pr = bpy.data.objects.get(pname)
        if pr is None or not any(c.influence > 0.5 for c in pr.evaluated_get(dg).constraints if c.name.startswith("hold_")):
            continue
        pw = pr.evaluated_get(dg).matrix_world.translation
        bone = pb[f"palm.{s_}"] if f"palm.{s_}" in pb else pb[f"hand.{s_}"]
        hw = world(rig, bone.head)
        off = act._held[pname][3]["offset"] if len(act._held[pname]) > 3 else (0, 0, 0)
        hg = max(hg, max(0.0, on_screen(pw, hw) - math.hypot(off[0], off[2])))        # the offset the shot asked for is not a gap
    row["held_gap"] = round(hg, 4)
    # planted feet
    feet = {s_: world(rig, pb[f"foot.{s_}"].tail) for s_ in "LR"}
    if ground is None:
        ground = min(v.z for v in feet.values())
    slide = 0.0
    mir = act.root.evaluated_get(dg).scale.x > 0
    if prev_feet is not None and not act.floating and vk == prev_view and mir == prev_mir:      # a turn flips the drawing: not a slide
        for s_ in "LR":
            if feet[s_].z < ground + 0.012 and prev_feet[s_].z < ground + 0.012:
                d = feet[s_] - prev_feet[s_]
                slide = max(slide, abs(d.dot(cam_right)))
    row["foot_slide"] = round(slide, 4)
    row["feet"] = {s_: [round(feet[s_].dot(cam_right), 3), round(feet[s_].z - ground, 3)] for s_ in "LR"}
    row["mirror"] = mir
    row["root_x"] = round(act.stage.evaluated_get(dg).matrix_world.translation.dot(cam_right), 3)
    prev_feet, prev_view, prev_mir = feet, vk, mir
    # depth: palm over the head -> the hand must be in front of the head
    hc = world(rig, pb["head_c"].head) if "head_c" in pb else None
    if hc is not None:
        for s_ in "LR":
            pc = world(rig, pb[f"palm.{s_}"].head)
            over = (pc - hc).length < act.head_r * act.scale
            hand = next((q for q in act.parts if q["cl_view"] == vk and q["cl_part"] == f"Hand.{s_}"), None)
            if hand is not None and over:
                row[f"over_head_{s_}"] = 1
                row[f"lifted_{s_}"] = int(hand.evaluated_get(dg).delta_location.y < -0.05)
    # the acting hand and the target
    if target is not None and hasattr(target, "matrix_world") and "target" in needs + ("prop",) * int("prop" in needs):
        tp = target.evaluated_get(dg).matrix_world.translation
        sh = world(rig, pb[f"arm_upper.{side}"].head)
        hd = world(rig, pb[f"palm.{side}"].head) if f"palm.{side}" in pb else world(rig, pb[f"hand.{side}"].head)
        dt, dh = (tp - sh).dot(cam_right), (hd - sh).dot(cam_right)
        row["hand_side"] = 1 if (abs(dt) < 0.05 or dt * dh >= 0) else -1
        row["hand_target"] = round(on_screen(tp, hd), 4)
    rows.append(row)

lead_f = shot.f(T0 + spec["lead"] / a.speed)
meta = {"char": a.char, "action": a.action, "view": a.view, "face": a.face, "frames": f_end, "fps": shot.fps, "t0": T0, "t_end": round(t_end, 3),
        "hit_frame": lead_f, "needs": list(needs), "group": spec["group"], "floating": bool(act.floating), "notes": shot.notes,
        "body": act.body, "rows": rows}
(out / f"{tag}.json").write_text(json.dumps(meta), encoding="utf-8")
print("ACTION_MEASURED", a.char, tag, f_end, "frames")

if not a.no_render:
    fd = out / "frames" / tag
    fd.mkdir(parents=True, exist_ok=True)
    for k, f in enumerate(range(1, f_end + 1, max(1, a.frame_step))):
        sc.frame_set(f)
        sc.render.filepath = str(fd / f"{k + 1:04d}.png")
        bpy.ops.render.render(write_still=True)
    print("ACTION_RENDERED", a.char, tag, f_end)
