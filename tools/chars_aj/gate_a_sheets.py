"""gate_a_sheets - the Gate A pictures: who is in this film, dressed, and is it right?

    blender -b --factory-startup --python tools/chars_aj/gate_a_sheets.py -- --clip <abs clip dir> [--px 300] [--no-qa]
    blender -b --factory-startup --python tools/chars_aj/gate_a_sheets.py -- --char <Name> [--px 300]          -> library/characters/aj/previews/<Name>.png
    blender -b --factory-startup --python tools/chars_aj/gate_a_sheets.py -- --lineup [--chars A,B,...]          -> library/characters/aj/previews/_lineup.png

For every character the plan casts (shotplan.json > cast, each with its per-clip costume), one sheet <clip>/review/cast/<id>.png:
    row 1  full body: front, three-quarter, side, back
    row 2  the face close up: neutral, happy, surprised, angry, sad
    row 3  one action pose holding a prop (a mug), and a height line-up beside a 2.0 m door outline and the other cast of the clip
plus <clip>/review/cast/lineup.png (the whole cast together, in costume) and <id>.qa.json (tools/chars_aj/qa.py, run in
this process; a character's blocking findings are stamped in red on its sheet). A character with blocking findings must not be
reported as ready: the last stdout line is {"previews": [...], "blocking": {"<id>": n}}.
Light: the look the film will have. The house rig (lights.rig, interior_day: its sky and soft back light, no sun) and, for every
picture, viewlight.stand_in: the warm key, cool fill, low front fill and camera white balance the per-view step gives a person seen
from that camera, so skin and costume colours are judged as they will look on screen. --no-stand-in: the old rig with its sun and no
white balance. A neutral studio floor and a round backdrop (its grey is set to the white balance's light colour, so it stays grey);
EEVEE at the draft settings. Labels are real text burnt in (character id, base, body, outfit, add-ons, hair, face).
--out <dir> (with --char or --lineup) writes the sheet there instead of library/characters/aj/previews (and the QA report there too).
"""
import argparse
import json
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stagekit  # noqa: E402
from stagekit import aj_wardrobe, cast, lights  # noqa: E402

DOOR_H, DOOR_W = 2.0, 0.9
EXPRS = ["neutral", "happy", "surprised", "angry", "sad"]
VIEWS = [("front", 0.0), ("three-quarter", 38.0), ("side", 90.0), ("back", 180.0)]
BG = (0.20, 0.21, 0.23)


# ----------------------------------------------------------------------------------------------- the studio
def _flat(name, col, rough=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    return m


MOOD = "interior_day"        # the studio's mood: the approved room's colour split (warm key, cooler fill, white balance 4900 K)
STAND_IN = True              # light each picture with viewlight.stand_in (the film's key, fills and white balance); --no-stand-in: the old rig


def studio(shot, w, h):
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    # With the stand-in the per-view key replaces the sun (as in the film, where a room has no sun on the faces); the sky world
    # and the soft back light stay.
    lights.rig(MOOD, sun_from=35.0, strength=0.0 if STAND_IN else 1.0, ambient=lights.mood_look(MOOD)["world"] if STAND_IN else None)
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    bpy.context.active_object.data.materials.append(_flat("floor", (0.36, 0.36, 0.38)))
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=30.0, depth=14.0, end_fill_type="NOTHING", location=(0, 0, 7.0))
    tube = bpy.context.active_object
    tube.data.materials.append(_backdrop(lights.mood_look(MOOD)["wb"] if STAND_IN else None))
    tube.visible_shadow = False
    return shot


def light_for(cam, head):
    """The film's light on the character for this camera: the stand-in key, fills and white balance for a head at `head`."""
    if STAND_IN:
        from stagekit import viewlight
        bpy.context.view_layer.update()
        r = viewlight.stand_in(cam, Vector(head), mood=MOOD, name="gate_a")
        print(f"[gate_a] stand-in key {r['key_power'] or 0:.0f} W at {r['key_distance'] or 0:.1f} m, {r['angle_off_lens'] or 0:.0f} deg off the lens"
              + (f"; {'; '.join(r['compromises'])}" if r["compromises"] else ""), flush=True)


def _backdrop(wb=None):
    """A uniform neutral grey that does not change with the camera's side (emission, so the light rig does not tint it). Under a white
    balance of `wb` K its colour is that light's colour, so it still renders neutral grey."""
    m = bpy.data.materials.new("backdrop")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    k = lights.kelvin_rgb(wb) if wb else (1.0, 1.0, 1.0)
    e.inputs["Color"].default_value = (0.30 * k[0], 0.31 * k[1], 0.33 * k[2], 1)
    e.inputs["Strength"].default_value = 1.0
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def camera(at, aim, ortho):
    cd = bpy.data.cameras.new("cam")
    cd.type = "ORTHO"
    cd.ortho_scale = ortho
    cam = bpy.data.objects.new("cam", cd)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    cam.location = Vector(at)
    cam.rotation_euler = (Vector(aim) - Vector(at)).to_track_quat("-Z", "Y").to_euler()
    return cam


def render_to(path, frame=1, w=None, h=None):
    sc = bpy.context.scene
    if w:
        sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.frame_set(frame)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return load_px(path)


def load_px(path):
    im = bpy.data.images.load(str(path))
    a = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
    bpy.data.images.remove(im)
    return a[::-1].copy()                # top row first


# ----------------------------------------------------------------------------------------------- labels (real text)
def text_layer(w, h, items, tmp):
    """RGBA image (top row first) with burnt-in text. items: (text, x, y, size_px, (r, g, b)) with y the top of the line."""
    sc = bpy.data.scenes.new("labels")
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.color_mode = "RGBA"
    sc.display.shading.light = "FLAT"
    sc.display.shading.color_type = "OBJECT"
    sc.view_settings.view_transform = "Standard"
    cd = bpy.data.cameras.new("lc")
    cd.type = "ORTHO"
    cd.ortho_scale = max(w, h)
    cam = bpy.data.objects.new("lc", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = (w / 2, -h / 2, 50)
    made = []
    for text, x, y, size, col in items:
        c = bpy.data.curves.new("t", "FONT")
        c.body = text
        c.size = size * 0.82
        c.align_x, c.align_y = "LEFT", "TOP"
        ob = bpy.data.objects.new("t", c)
        ob.location = (x, -y, 0)
        ob.color = (*col, 1.0)
        sc.collection.objects.link(ob)
        made.append((ob, c))
    sc.render.filepath = str(tmp)
    bpy.ops.render.render(write_still=True, scene=sc.name)
    img = load_px(tmp)
    for ob, c in made:
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(c)
    bpy.data.scenes.remove(sc)
    bpy.data.cameras.remove(cd)
    return img


def blit(canvas, tile, x, y):
    h, w = tile.shape[:2]
    canvas[y:y + h, x:x + w, :3] = tile[..., :3]


def overlay(canvas, layer):
    a = layer[..., 3:4]
    canvas[..., :3] = canvas[..., :3] * (1 - a) + layer[..., :3] * a


# ----------------------------------------------------------------------------------------------- one character
def make_actor(entry, at=(0, 0), face="right"):
    return cast.actor(entry["id"], entry["base"], at=at, face=face, view="front", scale=float(entry.get("scale", 1.0)), costume=entry.get("costume"))


def body_words(a):
    d = aj_wardrobe.describe(a)
    return d


def mug(act):
    """A plain mug in the right hand."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.045, depth=0.10, location=(0, 0, 0))
    ob = bpy.context.active_object
    ob.name = f"{act.id}.mug"
    ob.data.materials.append(_flat("mug", (0.85, 0.30, 0.18), 0.4))
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def sheet_for(entry, others, qa_items, out_png, px, tmpdir):
    """Everything for one character: returns the number of blocking findings."""
    t0 = time.time()
    cid = entry["id"]
    W1, H1 = px, int(px * 2.0)
    FW = int(4 * W1 / 5)
    LW = 3 * W1 + 2 * 8
    shot = stagekit.begin("gate_a", 1.0, "draft")
    studio(shot, W1, H1)
    act = make_actor(entry)
    H = act.height
    act.idle(0.0, 1.0)
    fps = shot.fps
    for i, e in enumerate(EXPRS):                      # the five faces on frames 1..5, neutral again for the pose
        act.expr(e, i / fps, 0.0)
    act.expr("neutral", 5 / fps, 0.0)
    prop = mug(act)                                    # the pose: a mug offered in the right hand, frame 7
    act.pose("offer", 6 / fps, 0.0)
    bpy.context.scene.frame_set(shot.f(6 / fps))
    bpy.context.view_layer.update()
    prop.location = act.palm["R"].matrix_world.translation + Vector((0.0, 0.0, 0.0))
    act.hold(prop, "R", 6 / fps)
    # the height line-up stands far to the side: a twin of the subject first, then the rest of the cast, beside a 2.0 m door
    gx = 8.0
    twin = dict(entry, id=cid + "_h")
    line = [(twin, make_actor(twin, at=(gx + DOOR_W + 0.6, 0.0)))]
    for k, o in enumerate(others):
        line.append((o, make_actor(o, at=(gx + DOOR_W + 0.6 + 0.95 * (k + 1), 0.0))))
    for _e, x in line:
        x.idle(0.0, 1.0)
    bar = _flat("door", (0.95, 0.78, 0.2), 0.6)
    for dx, dz, sx, sz in ((0, DOOR_H / 2, 0.05, DOOR_H), (DOOR_W, DOOR_H / 2, 0.05, DOOR_H), (DOOR_W / 2, DOOR_H, DOOR_W + 0.05, 0.05)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(gx + dx, 0.3, dz))
        c = bpy.context.active_object
        c.scale = (sx, 0.05, sz)
        c.data.materials.append(bar)
    door_objs = [o for o in bpy.data.objects if o.data is not None and o.type == "MESH" and o.data.materials and o.data.materials[0] is bar]
    for x in [act] + [x for _e, x in line]:
        x._finalize()
    bpy.context.view_layer.update()

    def show(subject, mug_on, lineup_on):
        act.coll.hide_render = not subject
        prop.hide_render = not mug_on
        for _e, x in line:
            x.coll.hide_render = not lineup_on
        for d in door_objs:
            d.hide_render = not lineup_on
    tiles = {}
    show(True, False, False)
    R = 12.0
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    head = act.head.point().copy()
    for name, deg in VIEWS:                            # row 1: the camera goes round the figure
        rad = math.radians(deg)
        cam = camera((math.sin(rad) * R, -math.cos(rad) * R, H * 0.5), (0, 0, H * 0.5), H * 1.18)
        light_for(cam, head)
        tiles[name] = render_to(tmpdir / f"_{cid}_{name}.png", 1, W1, H1)
    hz = act.head.point().z                            # row 2: the face
    cam = camera((0.0, -R, hz + 0.03 * H), (0.0, 0.0, hz + 0.03 * H), 0.46 * max(1.0, H / 1.6))
    light_for(cam, head)
    tiles_f = [render_to(tmpdir / f"_{cid}_f{i}.png", shot.f(i / fps), FW, FW) for i in range(len(EXPRS))]
    show(True, True, False)                                                        # row 3: the pose
    bpy.context.scene.frame_set(shot.f(6 / fps) + 3)
    px_ = act.palm["R"].matrix_world.translation
    cam = camera((7.0, -R * 0.6, H * 0.5), (px_.x * 0.5, 0.0, H * 0.5), H * 1.4)
    light_for(cam, act.head.point().copy())
    pose_tile = render_to(tmpdir / f"_{cid}_pose.png", shot.f(6 / fps) + 3, W1, H1)
    show(False, False, True)
    ortho_h = 2.4                                      # row 3: the line-up, 2.4 m of height in a LW x H1 picture
    xs = gx + (DOOR_W + 0.6 + 0.95 * len(line)) / 2.0
    cam = camera((xs, -R, ortho_h / 2 - 0.1), (xs, 0.0, ortho_h / 2 - 0.1), ortho_h * LW / H1)
    light_for(cam, line[0][1].head.point().copy())     # keyed on the subject's twin; the rest of the line-up stands in the same light
    lineup = render_to(tmpdir / f"_{cid}_line.png", 1, LW, H1)
    # ---- compose
    gap = 8
    head_h = 150
    cap = 24
    sheet_w = 4 * W1 + 3 * gap
    sheet_h = head_h + H1 + cap + FW + cap + H1 + cap
    canvas = np.ones((sheet_h, sheet_w, 4), dtype=np.float32)
    canvas[..., :3] = 0.09
    y = head_h
    for i, (name, _d) in enumerate(VIEWS):
        blit(canvas, tiles[name], i * (W1 + gap), y)
    y += H1 + cap
    for i, t in enumerate(tiles_f):
        blit(canvas, t, int(i * (sheet_w - FW) / 4), y)
    y += FW + cap
    blit(canvas, pose_tile, 0, y)
    blit(canvas, lineup, W1 + gap, y)
    d = body_words(act)
    ent = aj_wardrobe  # noqa: F841
    items = [(f"{cid}", 14, 8, 30, (1, 1, 1)),
             (f"base {entry['base']}   body {d.get('body', entry.get('body', '?'))}   face {d.get('face')}   height {H:.2f} m", 14, 48, 17, (0.85, 0.85, 0.9)),
             (f"outfit {d['outfit']}   add-ons {', '.join(d['addons']) or 'none'}   skin {d.get('skin') or 'default'}", 14, 72, 17, (0.85, 0.85, 0.9)),
             (f"hair {d['hair'] or 'none'}   facial hair {d['facial_hair'] or 'none'}", 14, 96, 17, (0.85, 0.85, 0.9)),
             (f"palette {json.dumps(d.get('palette', {}))}", 14, 120, 17, (0.85, 0.85, 0.9))]
    for i, (name, _d) in enumerate(VIEWS):
        items.append((name, i * (W1 + gap) + 8, head_h + 4, 16, (1, 1, 1)))
    y2 = head_h + H1 + cap
    for i, e in enumerate(EXPRS):
        items.append((e, int(i * (sheet_w - FW) / 4) + 8, y2 + 4, 16, (1, 1, 1)))
    y3 = y2 + FW + cap
    items.append(("holding a mug", 8, y3 + 4, 16, (1, 1, 1)))
    others_txt = ", ".join(o["id"] for o in others) or "(alone in this film)"
    items.append((f"height line-up: door 2.0 m, then {cid}, {others_txt}", W1 + gap + 8, y3 + 4, 16, (1, 1, 1)))
    blocking = [i for i in qa_items if i["level"] == "block"]
    warn = [i for i in qa_items if i["level"] == "warn"]
    yy = 8
    xr = sheet_w - 640
    if blocking:
        items.append((f"NOT READY: {len(blocking)} blocking finding(s)", xr, yy, 20, (1.0, 0.25, 0.2)))
        yy += 26
        for i in blocking[:3]:
            items.append(((i["code"] + ": " + i["detail"])[:90], xr, yy, 14, (1.0, 0.35, 0.3)))
            yy += 20
    else:
        items.append(("QA: no blocking findings", xr, yy, 18, (0.5, 0.9, 0.5)))
        yy += 24
    for i in warn[:3 if blocking else 4]:
        items.append(((i["code"] + ": " + i["detail"])[:96], xr, yy, 13, (0.95, 0.8, 0.4)))
        yy += 19
    layer = text_layer(sheet_w, sheet_h, items, tmpdir / "_labels.png")
    overlay(canvas, layer)
    save_png(canvas, out_png)
    print(f"GATE_A sheet {cid}: {time.time() - t0:.1f} s, {len(blocking)} blocking, {len(warn)} warning(s) -> {out_png}", flush=True)
    return len(blocking)


def save_png(canvas, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = canvas.shape[:2]
    im = bpy.data.images.new("out", w, h, alpha=False)
    out = canvas[::-1].copy()
    out[..., 3] = 1.0
    im.pixels.foreach_set(out.ravel())
    im.filepath_raw = str(path)
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


# ----------------------------------------------------------------------------------------------- the line-up of the cast
def lineup_sheet(entries, out_png, px, tmpdir, per_row=6, title=""):
    """All characters together, in costume, in rows of `per_row`, each with its id under it."""
    t0 = time.time()
    entries = list(entries)
    nrows = (len(entries) + per_row - 1) // per_row
    pw = int(per_row * px * 0.62)
    ph = int(px * 1.55)
    shot = stagekit.begin("gate_a_line", 1.0, "draft")
    studio(shot, pw, ph)
    acts = []
    for r in range(nrows):                              # every row stands at the same place; only the row being photographed is shown
        for c, e in enumerate(entries[r * per_row:(r + 1) * per_row]):
            a = make_actor(e, at=(c * 1.0, 0.0))
            a.idle(0.0, 1.0)
            acts.append((r, c, e, a))
    for _r, _c, _e, a in acts:
        a._finalize()
    bpy.context.view_layer.update()
    tall = max(a.height for _r, _c, _e, a in acts)
    ort_h = tall * 1.12
    rows_img = []
    for r in range(nrows):
        for r2, _c, _e, a in acts:
            a.coll.hide_render = r2 != r
        n = min(per_row, len(entries) - r * per_row)
        xc = (n - 1) / 2.0
        wmeters = per_row * 1.0
        cam = camera((xc, -14.0, ort_h / 2), (xc, 0.0, ort_h / 2), wmeters)
        cam.data.ortho_scale = wmeters
        mid = min((a for r2, _c, _e, a in acts if r2 == r), key=lambda a: abs(a.head.point().x - xc))
        light_for(cam, mid.head.point().copy())       # keyed on the middle of the row; the others stand in the same light
        rows_img.append(render_to(tmpdir / f"_line{r}.png", 1, pw, ph))
    cap = 54
    W = pw
    Ht = 70 + nrows * (ph + cap)
    canvas = np.ones((Ht, W, 4), dtype=np.float32)
    canvas[..., :3] = 0.09
    items = [(title or "cast", 14, 10, 30, (1, 1, 1))]
    for r in range(nrows):
        y = 70 + r * (ph + cap)
        blit(canvas, rows_img[r], 0, y)
        n = min(per_row, len(entries) - r * per_row)
        for c in range(n):
            e = entries[r * per_row + c]
            x = int((W - per_row * (W / per_row)) / 2 + (c + 0.5 - (n - 1) / 2 + (per_row - 1) / 2) * (W / per_row)) - int(W / per_row / 2) + 6
            items.append((e["id"][:22], x - 4, y + ph + 4, 14, (1, 1, 1)))
            items.append((e["base"][:22] if e["base"] != e["id"] else "", x, y + ph + 24, 12, (0.7, 0.7, 0.75)))
    overlay(canvas, text_layer(W, Ht, items, tmpdir / "_labels.png"))
    save_png(canvas, out_png)
    print(f"GATE_A lineup of {len(entries)}: {time.time() - t0:.1f} s -> {out_png}", flush=True)


# ----------------------------------------------------------------------------------------------- a character that cannot be built
def unavailable_sheet(entry, reason, out_png, tmpdir):
    """A sheet that says why there is no picture: the plan casts someone the project cannot dress yet."""
    stagekit.begin("gate_a_none", 1.0, "draft")
    w, h = 1224, 420
    canvas = np.ones((h, w, 4), dtype=np.float32)
    canvas[..., :3] = (0.22, 0.06, 0.06)
    items = [(entry["id"], 14, 10, 30, (1, 1, 1)), (f"base {entry['base']}", 14, 52, 18, (0.85, 0.85, 0.9)),
             ("NOT READY: this character cannot be built", 14, 100, 24, (1.0, 0.3, 0.25))]
    words_ = reason.split()
    line, y = "", 148
    for wd in words_:
        if len(line) + len(wd) > 110:
            items.append((line, 14, y, 15, (1.0, 0.75, 0.7)))
            line, y = "", y + 22
        line += wd + " "
    items.append((line, 14, y, 15, (1.0, 0.75, 0.7)))
    overlay(canvas, text_layer(w, h, items[:14], tmpdir / "_labels.png"))
    save_png(canvas, out_png)


def castable(entry):
    """None when the character can be built, else the reason (the same rules as the plan check)."""
    sys.path.insert(0, str(PIPE / "tools"))
    import cast_data as cd
    reg = cd.cast()
    name, ch, bare = cd.resolve(reg, entry["base"])
    if ch is None and bare is None:
        return f"'{entry['base']}' is not a registered character or a body id. Run: py -3 tools/clip.py casting <clip> (--apply to register what it can adapt)"
    if ch is not None:
        errs = cd.check_costume(reg, cd.wardrobe(), ch, entry.get("costume"), None, entry["id"], name)
        if errs:
            return "; ".join(errs)
    return None


# ----------------------------------------------------------------------------------------------- QA in this process
def load_qa():
    """tools/chars_aj/qa.py by path (the name `qa` is also tools/qa.py, the film's QA)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("aj_char_qa", str(Path(__file__).resolve().parent / "qa.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run_qa(entry):
    qa = load_qa()
    stagekit.begin("qa", 1.0, "draft")
    act = make_actor(entry)
    r = qa.check_actor(act)
    items = r["items"] + qa.action_items(entry["base"])
    rep = qa.finish(entry["id"], items, r["measured"])
    return rep


# ----------------------------------------------------------------------------------------------- main
def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip")
    ap.add_argument("--char")
    ap.add_argument("--lineup", action="store_true")
    ap.add_argument("--chars", default="")
    ap.add_argument("--px", type=int, default=300)
    ap.add_argument("--no-qa", action="store_true")
    ap.add_argument("--out", default=None, help="with --char / --lineup: write the sheet (and QA) here instead of the library")
    ap.add_argument("--no-stand-in", action="store_true", help="the old studio light: the rig's sun, no stand-in key, no white balance")
    a = ap.parse_args(argv)
    global STAND_IN
    STAND_IN = not a.no_stand_in
    cfg = json.loads((PIPE / "config" / "cast.json").read_text(encoding="utf-8"))
    tmp = PIPE / "output" / "_staging" / "gate_a_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    previews, blocking = [], {}

    def with_qa(entry):
        if a.no_qa:
            return []
        rep = run_qa(entry)
        qd = (Path(out_dir) if a.clip or a.out else PIPE / "library" / "characters" / "aj" / "qa") / f"{entry['id']}.qa.json"
        qd.parent.mkdir(parents=True, exist_ok=True)
        qd.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        blocking[entry["id"]] = rep["blocking"]
        return rep["items"]

    if a.clip:
        clip = Path(a.clip)
        plan = json.loads((clip / "shotplan.json").read_text(encoding="utf-8"))
        cast_list = [dict(c) for c in plan.get("cast", [])]
        out_dir = clip / "review" / "cast"
        out_dir.mkdir(parents=True, exist_ok=True)
        ready = []
        for c in cast_list:
            why = castable(c)
            if why:
                unavailable_sheet(c, why, out_dir / f"{c['id']}.png", tmp)
                blocking[c["id"]] = 1
                print(f"GATE_A {c['id']}: cannot be built: {why}", flush=True)
                previews.append(str(out_dir / f"{c['id']}.png"))
                continue
            ready.append(c)
        for c in ready:
            others = [o for o in ready if o["id"] != c["id"]]
            qa_items = with_qa(c)
            sheet_for(c, others, qa_items, out_dir / f"{c['id']}.png", a.px, tmp)
            previews.append(str(out_dir / f"{c['id']}.png"))
        if ready:
            lineup_sheet(ready, out_dir / "lineup.png", a.px, tmp, title=f"{clip.name}: the cast" + (f" ({len(cast_list) - len(ready)} cannot be built yet)" if len(ready) < len(cast_list) else ""))
            previews.append(str(out_dir / "lineup.png"))
    elif a.char or a.lineup:
        out_dir = Path(a.out).resolve() if a.out else PIPE / "library" / "characters" / "aj" / "previews"
        out_dir.mkdir(parents=True, exist_ok=True)
        names = [n for n in a.chars.split(",") if n] or ([a.char] if a.char else list(cfg["characters"]))
        entries = [{"id": n, "base": n, "costume": None} for n in names]
        if a.lineup:
            lineup_sheet(entries, out_dir / "_lineup.png", a.px, tmp, per_row=6, title=f"the starter cast ({len(entries)})")
            previews.append(str(out_dir / "_lineup.png"))
        else:
            e = entries[0]
            qa_items = with_qa(e)
            sheet_for(e, [], qa_items, out_dir / f"{e['id']}.png", a.px, tmp)
            previews.append(str(out_dir / f"{e['id']}.png"))
    else:
        ap.error("give --clip, --char or --lineup")
    for p in tmp.glob("_*.png"):
        p.unlink()
    print(json.dumps({"previews": previews, "blocking": blocking}))
    if any(blocking.values()):                           # the sheets are made, but the gate must not be marked ready
        print("GATE_A NOT READY: blocking findings for " + ", ".join(k for k, v in blocking.items() if v), flush=True)
        sys.stdout.flush()
        raise SystemExit(7)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
