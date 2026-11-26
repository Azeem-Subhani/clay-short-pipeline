"""look_aj.py - contact sheets of the Aj actors, to look at with your own eyes.

    blender -b --factory-startup --python tools/chars_aj/look_aj.py -- --sheet cast|expr|faces2|hands|actions
            [--chars TeenBoy,Woman] [--actions walk,wave] [--out <dir>] [--px 360]

  cast     each starter character in four turns: front, three-quarter, side, back       -> cast_<Name>.png, cast_sheet.png
  expr     the expression row on one character (head close-up)                         -> expr_<Name>.png
  faces2   two characters side by side with different faces, both speaking in turn      -> faces2.png
  hands    the six hand shapes close up                                                  -> hands_<Name>.png
  actions  named actions, four frames each (a prop from the library for pick_up and hand_over, a second actor for
           hand_over)                                                                    -> act_<Name>_<action>.png
Plain floor, the house light rig (lights.rig), EEVEE at the draft settings, low resolution.
Default output: output/_staging/aj_actor/.
"""
import argparse
import math
import os
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

PIPE = Path(__file__).resolve().parents[2]
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
sys.path.insert(0, str(PIPE / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import assets, cast, core, lights  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--sheet", required=True)
ap.add_argument("--chars", default="")
ap.add_argument("--actions", default="")
ap.add_argument("--out", default=str(PIPE / "output" / "_staging" / "aj_actor"))
ap.add_argument("--px", type=int, default=360)
a = ap.parse_args(argv)
OUT = Path(a.out)
OUT.mkdir(parents=True, exist_ok=True)
STARTERS = ["Boy", "Girl", "TeenBoy", "TeenGirl", "Man", "Woman", "Grandpa", "Grandma"]


def stage(seconds, w, h):
    shot = stagekit.begin("look_aj", seconds, "draft")
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    lights.rig("day_clear", sun_from=35.0)
    m = bpy.data.materials.new("floor")
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.52, 0.47, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
    bpy.context.active_object.data.materials.append(m)
    return shot


def camera(at, aim, lens=50.0, ortho=None):
    cd = bpy.data.cameras.new("cam")
    cd.lens = lens
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = Vector(at)
    cam.rotation_euler = (Vector(aim) - Vector(at)).to_track_quat("-Z", "Y").to_euler()
    return cam


def render(path, frame=1):
    sc = bpy.context.scene
    sc.frame_set(frame)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return Path(path)


def compose(paths, cols, out, gap=6):
    """Put PNG tiles into one grid image (row by row, the first tile top left)."""
    ims = [bpy.data.images.load(str(p)) for p in paths]
    w, h = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    W, H = cols * w + (cols - 1) * gap, rows * h + (rows - 1) * gap
    canvas = np.ones((H, W, 4), dtype=np.float32)
    canvas[..., :3] = 0.12
    for i, im in enumerate(ims):
        px = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        r, c = divmod(i, cols)
        y0 = H - (r + 1) * h - r * gap
        x0 = c * (w + gap)
        canvas[y0:y0 + px.shape[0], x0:x0 + px.shape[1]] = px
    img = bpy.data.images.new("sheet", W, H, alpha=True)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = str(out)
    img.file_format = "PNG"
    img.save()
    for im in ims:
        bpy.data.images.remove(im)
    bpy.data.images.remove(img)
    return out


def finalize(shot):
    for x in shot.actors.values():
        x._finalize()


# ----------------------------------------------------------------------------------------------- sheets
def sheet_cast(names):
    rows = []
    for n in names:
        t0 = time.time()
        shot = stage(1.0, a.px * 4, int(a.px * 2.0))
        heads = (0.0, 40.0, 90.0, 180.0)
        acts = []
        for i, hd in enumerate(heads):
            x = (i - 1.5) * 0.95
            act = cast.actor(f"c{i}", n, at=(x, 0), face="right", view="front")
            act.heading(hd)
            act.idle(0.0, 1.0)
            acts.append(act)
        H = max(x.height for x in acts)
        camera((0, -12, H * 0.55), (0, 0, H * 0.52), ortho=max(4.1, 2.05 * H))
        finalize(shot)
        p = render(OUT / f"cast_{n}.png", 1)
        rows.append(p)
        print(f"LOOK cast {n} height={acts[0].height:.2f} m  {time.time() - t0:.1f} s -> {p}", flush=True)
    if len(rows) > 1:
        compose(rows, 1, OUT / "cast_sheet.png")


def head_cam(act, dist=1.0, side=0.35):
    hz = act.head.point()
    c = hz + Vector((side, -dist, 0.02))
    return camera(c, hz, lens=60.0)


def sheet_expr(n):
    from stagekit import aj_face
    exprs = list(aj_face.names())
    shot = stage(len(exprs) / 24.0 + 1.0, a.px, a.px)
    act = cast.actor("e", n, at=(0, 0), face="right", view="front")
    act.heading(0.0)
    for i, e in enumerate(exprs):
        act.expr(e, i / 24.0, 0.0)
    finalize(shot)
    head_cam(act, 1.25 * act.scale / 0.9, 0.0)
    tiles = [render(OUT / f"_t_expr_{i:02d}.png", i + 1) for i in range(len(exprs))]
    out = compose(tiles, 5, OUT / f"expr_{n}.png")
    print("LOOK expr", n, "order:", ", ".join(exprs), "->", out, flush=True)


def sheet_faces2(n1, n2):
    shot = stage(4.0, a.px * 2, a.px)
    A = cast.actor("a", n1, at=(-0.45, 0), face="right", view="front")
    B = cast.actor("b", n2, at=(0.45, 0), face="left", view="front")
    A.heading(0.0)
    B.heading(0.0)
    A.expr("happy", 0.0, 0.0)
    B.expr("angry", 0.0, 0.0)
    A.speak(0.5, 1.5)
    B.speak(2.2, 3.2)
    finalize(shot)
    H = max(A.height, B.height)
    camera((0, -3.2, H * 0.86), (0, 0, H * 0.84), lens=50.0)
    # A speaking (B quiet, angry) / B speaking (A quiet, happy)
    tiles = []
    for f in (shot.f(0.62), shot.f(0.9), shot.f(2.32), shot.f(2.6)):
        tiles.append(render(OUT / f"_t_f2_{f:03d}.png", f))
    out = compose(tiles, 2, OUT / "faces2.png")
    print("LOOK faces2", n1, n2, "frames", [shot.f(x) for x in (0.62, 0.9, 2.32, 2.6)], "->", out, flush=True)


def sheet_eyes(n):
    """Facing the camera: eyes to the figure's own right (look_x -1), centre, its own left (+1), then up and down.
    The figure's left is screen right in this view, so +1 must look to screen right."""
    shot = stage(1.0, a.px, a.px)
    act = cast.actor("e", n, at=(0, 0), face="right", view="front")
    act.heading(0.0)
    looks = [(-1, 0), (0, 0), (1, 0), (0, 1), (0, -1)]
    for i, (x, z) in enumerate(looks):
        for k, v in (("look_x", x), ("look_z", z)):
            act.ctrl[k] = float(v)
            act.ctrl.keyframe_insert(f'["{k}"]', frame=i + 1)
    finalize(shot)
    head_cam(act, 1.25 * act.scale / 0.9, 0.0)
    tiles = [render(OUT / f"_t_eye_{i:02d}.png", i + 1) for i in range(len(looks))]
    out = compose(tiles, 5, OUT / f"eyes_{n}.png")
    print("LOOK eyes", n, "order: look_x -1, 0, +1, up, down ->", out, flush=True)


def sheet_hands(n):
    from stagekit import aj_hands
    shapes = list(aj_hands.NAMES)
    shot = stage(len(shapes) / 24.0 + 1.0, a.px, a.px)
    act = cast.actor("h", n, at=(0, 0), face="right", view="front")
    act.heading(0.0)
    act.arm("R", 55, 45, 0.0, 0.0)
    for i, s in enumerate(shapes):
        act.hand("R", s, i / 24.0, 0.0)
    finalize(shot)
    bpy.context.scene.frame_set(1)
    p = act.palm["R"].matrix_world.translation.copy()
    camera(p + Vector((-0.05, -0.55, 0.08)), p, lens=60.0)
    tiles = [render(OUT / f"_t_hand_{i:02d}.png", i + 1) for i in range(len(shapes))]
    out = compose(tiles, 3, OUT / f"hands_{n}.png")
    print("LOOK hands", n, "order:", ", ".join(shapes), "->", out, flush=True)


ACTS = ["walk", "run", "wave", "point", "pick_up", "hand_over", "sit_down", "kneel", "cheer", "shrug", "look_around", "facepalm", "cover_mouth"]


def sheet_actions(n, names):
    from stagekit import actions
    for an in names:
        t_build = time.time()
        shot = stage(6.0, a.px, int(a.px * 16 / 9))
        moving = an in ("walk", "run")
        act = cast.actor("x", n, at=(-1.0 if moving else 0.0, 0), face="right", view="3q")
        H = act.height
        kw, args = {}, []
        if an in ("walk", "run"):
            kw["to"] = (1.2, 0.0)
        if an == "point":
            post = bpy.data.objects.new("target", None)
            bpy.context.scene.collection.objects.link(post)
            post.location = (1.6, -0.3, 0.6 * H)
            args = [post]
        if an in ("pick_up", "hand_over"):
            stand = None
            if an == "pick_up":
                bpy.ops.mesh.primitive_cube_add(size=1, location=(0.45, -0.05, 0.19 * H))
                stand = bpy.context.active_object
                stand.scale = (0.3, 0.3, 0.38 * H)
            prop = assets.use("prop_innkeeper_tankard", "prop", at=(0.45, -0.05, 0.38 * H if stand else 0.0))
            shot.props["prop"] = prop
            args = [prop]
            if an == "hand_over":
                other = cast.actor("y", "Man" if n != "Man" else "Woman", at=(0.85, 0), face="left", view="3q")
                kw["to"] = other
                prop.location = act.palm["R"].matrix_world.translation
                act.hold(prop, "R", 0.05)
                act.arm("R", 52, 66, 0.1, 0.0)
        t_end = act.do(an, *args, t=0.4, **kw)
        t_end = min(5.8, max(t_end, 0.8) + 0.4)
        act.idle(0.0, t_end)
        t_fin = time.time()
        finalize(shot)
        t_fin = time.time() - t_fin
        sc = bpy.context.scene
        sc.frame_end = shot.f(t_end)
        cx = 0.2 if not moving else 0.1
        camera((cx + 0.8, -4.6 * max(0.8, H / 1.62), H * 0.62), (cx, 0, H * 0.45), lens=40.0 if moving or an == "hand_over" else 50.0)
        fr = [max(1, int(round(shot.f(0.4) + k * (shot.f(t_end) - shot.f(0.4)) / 3.0))) for k in range(4)]
        tiles = [render(OUT / f"_t_{an}_{i}.png", f) for i, f in enumerate(fr)]
        out = compose(tiles, 4, OUT / f"act_{n}_{an}.png")
        print(f"LOOK action {n} {an} frames={fr} build+finalize={time.time() - t_build:.1f}s finalize={t_fin:.2f}s notes={shot.notes} -> {out}", flush=True)


chars = [c for c in a.chars.split(",") if c]
if a.sheet == "cast":
    sheet_cast(chars or STARTERS)
elif a.sheet == "expr":
    sheet_expr((chars or ["TeenGirl"])[0])
elif a.sheet == "faces2":
    c = chars or ["TeenBoy", "Woman"]
    sheet_faces2(c[0], c[1])
elif a.sheet == "eyes":
    sheet_eyes((chars or ["Man"])[0])
elif a.sheet == "hands":
    sheet_hands((chars or ["Man"])[0])
elif a.sheet == "actions":
    for c in chars or ["TeenBoy", "Woman"]:
        sheet_actions(c, [x for x in a.actions.split(",") if x] or ACTS)
for p in OUT.glob("_t_*.png"):
    p.unlink()
print("LOOK_DONE")
