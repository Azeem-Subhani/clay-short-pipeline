"""Preview and audit one set file, headless: render it from six angles, tile them into a sheet, measure it.

    blender -b --factory-startup --python tools/blender/set_preview.py -- --set <path to set_*.py> --time <mood> --out <dir> [--res 540x960]
            [--quality draft|preview|final] [--views wide,cross_a,cross_b,reverse,low,plan] [--no-render]

The set file follows the usual contract (build_set(time) -> dict, MARK, WIDE, LIGHT; see examples/sets/). Views rendered:
  wide      the set's WIDE camera
  cross_a   the same height and distance, turned 60 degrees one way round the middle of the stage
  cross_b   ... 60 degrees the other way
  reverse   from the opposite side, looking back (walls and ceiling between the camera and the room hidden by arch.cutaway)
  low       a low angle from the first mark, looking across the set
  plan      top-down, every wall and the ceiling hidden, the marks labelled
A set file may declare the angles its film really uses:  PREVIEWS = {"name": (pos, aim, lens), ...}  (pos, aim: (x, y, z) in metres; lens: mm).
They are rendered in addition to the six derived views (a name that is also a derived view, such as "wide", replaces it), tiled into the sheet
before the plan, and audited with the rest (prop types, layers, practicals and the rest are counted over every view). PREVIEWS_ONLY = True drops
the derived views and keeps only the declared ones and the plan. --views can name any of them. (build_set may also return them as "previews".)
A 1.75 m capsule stands on each mark for scale (it is added AFTER the audit and is not part of the set).
Writes <out>/wide.png ... plan.png, sheet.png (3 x 2, order wide, cross_a, cross_b / reverse, low, plan), audit.json and
timing.json. Exit code 1 if the audit has blocking issues, 3 if the set fails to build. The last stdout line is
{"previews": [sheet], "blocking": n, "warnings": n}.

Clip mode (what `clip.py setpreview <clip> [set]` runs):

    blender -b --factory-startup --python tools/blender/set_preview.py -- --clip <abs clip dir> [--set <set id>]

takes every set of the clip's shotplan.json (or the one named), finds blender/set_<id>.py, and for each light mood the plan's shots use
for that set builds the set in its own Blender process, renders the sheet to <clip>/review/sets/<set>_<time>/ and checks the set file
against the plan (every planned mark in MARK, the plan's theme, the moods in LIGHT: see tools/blender/planlink.py). The audit and the
agreement items are merged into each audit.json. Exit code 1 if any set has a blocking issue, 3 if one fails to build; the last stdout
line lists every sheet and the totals.
"""
import argparse
import importlib.util
import json
import math
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import planlink  # noqa: E402
import stagekit  # noqa: E402
from stagekit import arch, audit, core  # noqa: E402

ORDER = ["wide", "cross_a", "cross_b", "reverse", "low", "plan"]


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="set_preview")
    ap.add_argument("--set", default=None, help="a set file (single mode), or with --clip the id of one set of the plan")
    ap.add_argument("--clip", default=None, help="clip mode: an absolute clip directory; every set of its plan (or --set <id>)")
    ap.add_argument("--time", default=None)
    ap.add_argument("--out", default=None, help="single mode: the output directory")
    ap.add_argument("--res", default=None, help="WxH of each still (default: half size of the video, 540x960)")
    ap.add_argument("--quality", default="preview", choices=("draft", "preview", "final"))
    ap.add_argument("--views", default=None)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--samples", type=int, default=None)
    return ap.parse_args(argv)


def load_set(path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def standin(pos, name):
    """A 1.75 m capsule (a person for scale): a cylinder and two spheres, flat grey."""
    mat = bpy.data.materials.get("SK_standin") or bpy.data.materials.new("SK_standin")
    mat.diffuse_color = (0.55, 0.57, 0.62, 1.0)
    from stagekit import mat as sk_mat
    m = sk_mat.solid("#8A8F9A", 0.6, name="SK_standin_mat")
    bm_objs = []
    import bmesh
    bm = bmesh.new()
    r = 0.24
    bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=r, radius2=r, depth=1.75 - 2 * r)
    bmesh.ops.translate(bm, vec=(0, 0, r + (1.75 - 2 * r) / 2), verts=bm.verts)
    top = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
    bmesh.ops.translate(bm, vec=(0, 0, 1.75 - r), verts=top["verts"])
    bot = bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
    bmesh.ops.translate(bm, vec=(0, 0, r), verts=bot["verts"])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    me.materials.append(m)
    core.link(ob, "STANDIN")
    ob.location = (pos[0], pos[1], pos[2] if len(pos) > 2 else 0.0)
    ob["sk_kind"] = "standin"
    return ob


def label(text, pos, size=0.55, color="#FFF35A"):
    from stagekit import mat as sk_mat
    cu = bpy.data.curves.new(f"lab_{text}", "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    cu.materials.append(sk_mat.emit(color, 3.0, "SK_label_emit"))
    ob = bpy.data.objects.new(f"lab_{text}", cu)
    core.link(ob, "STANDIN")
    ob.location = pos
    ob["sk_kind"] = "standin"
    return ob


def mk_camera():
    cd = bpy.data.cameras.new("PREVIEW_CAM")
    cd.sensor_width = 36.0
    cd.clip_start, cd.clip_end = 0.05, 600.0
    cd.dof.use_dof = False
    ob = bpy.data.objects.new("PREVIEW_CAM", cd)
    core.link(ob, "RIG")
    bpy.context.scene.camera = ob
    return ob


def aim(cam, pos, target, lens, ortho=None):
    cam.location = pos
    cam.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO" if ortho else "PERSP"
    if ortho:
        cam.data.ortho_scale = ortho
    else:
        cam.data.lens = lens


def look_down(cam, pos, screen_up, ortho):
    """A top-down orthographic camera whose screen-up direction is the world direction screen_up (a unit vector in XY)."""
    from mathutils import Matrix
    yc = Vector((screen_up[0], screen_up[1], 0.0)).normalized()
    zc = Vector((0.0, 0.0, 1.0))
    xc = yc.cross(zc)
    cam.location = pos
    cam.rotation_euler = Matrix((xc, yc, zc)).transposed().to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho


def exposure(path: Path):
    """(mean luma, fraction clipped to white, fraction crushed to black) of a rendered still, display-referred 0-1."""
    im = bpy.data.images.load(str(path), check_existing=False)
    a = np.array(im.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
    bpy.data.images.remove(im)
    luma = a @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return float(luma.mean()), float((luma > 0.98).mean()), float((luma < 0.04).mean())


def tile(paths, out: Path, cols=3):
    imgs = []
    for p in paths:
        im = bpy.data.images.load(str(p), check_existing=False)
        w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        imgs.append(a)
        bpy.data.images.remove(im)
    h, w = imgs[0].shape[:2]
    rows = math.ceil(len(imgs) / cols)
    sheet = np.ones((rows * h + (rows + 1) * 6, cols * w + (cols + 1) * 6, 4), dtype=np.float32) * 0.08
    sheet[..., 3] = 1.0
    for i, a in enumerate(imgs):
        r, c = divmod(i, cols)
        y = (rows - 1 - r) * (h + 6) + 6                  # image rows are bottom-up
        x = c * (w + 6) + 6
        sheet[y:y + h, x:x + w] = a
    im = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    im.pixels.foreach_set(sheet.ravel())
    im.filepath_raw = str(out)
    im.file_format = "PNG"
    im.save()
    return sheet.shape[1], sheet.shape[0]


def clip_mode(a):
    """Every set of a clip's plan, each light mood in its own Blender process; merge the plan/set agreement into each audit.json."""
    import subprocess
    clip = Path(a.clip).resolve()
    plan = json.loads((clip / "shotplan.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in plan.get("sets", [])]
    if a.set:
        if a.set not in ids:
            print(f"[set_preview] the plan has no set '{a.set}' (it has {', '.join(ids)})")
            sys.exit(2)
        ids = [a.set]
    previews, blocking, warnings, rc = [], 0, 0, 0
    for sid in ids:
        f = planlink.set_file(clip, sid)
        times = planlink.times_of(plan, sid) or [None]
        for t in times:
            out = clip / "review" / "sets" / f"{sid}_{t or 'default'}"
            out.mkdir(parents=True, exist_ok=True)
            for old in (out / "sheet.png", out / "audit.json"):
                old.unlink(missing_ok=True)
            print(f"== set {sid} / {t or 'default light'} -> {out}", flush=True)
            items = planlink.agreement(plan, sid, clip, [t] if t else [])
            audit_doc = None
            if f.exists():
                cmd = [bpy.app.binary_path, "-b", "--factory-startup", "--python-exit-code", "3", "--python", str(Path(__file__).resolve()), "--", "--set", str(f), "--out", str(out),
                       "--quality", a.quality]
                for flag, val in (("--time", t), ("--res", a.res), ("--views", a.views), ("--samples", a.samples)):
                    if val:
                        cmd += [flag, str(val)]
                if a.no_render:
                    cmd.append("--no-render")
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                tail = []
                for line in p.stdout:
                    if line.lstrip().startswith("{") and '"previews"' in line:
                        continue                                   # the child's own summary line: this process prints the one that counts
                    print(line, end="", flush=True)
                    tail.append(line)
                p.wait()
                if p.returncode == 3 or not (out / "audit.json").exists():
                    rc = 3
                    items.append(planlink._item("block", "set_build_failed", f"set '{sid}' ({t or 'default light'}) did not build (Blender exit {p.returncode}): " + " | ".join(x.strip() for x in tail[-4:] if x.strip())[-400:]))
                else:
                    audit_doc = json.loads((out / "audit.json").read_text(encoding="utf-8"))
            doc = audit_doc or {"inventory": None, "issues": [], "ok": False}
            for it in items:
                doc["issues"].append({"level": it["level"], "code": it["code"], "object": f"plan/{sid}", "detail": it["text"]})
                print(f"[{it['level']}] {it['code']}: plan/{sid}: {it['text']}")
            doc["plan_items"] = items
            doc["set"], doc["mood"] = sid, t
            b = sum(1 for i in doc["issues"] if i["level"] == "block")
            w = sum(1 for i in doc["issues"] if i["level"] == "warn")
            doc["ok"], doc["blocking"], doc["warnings"] = b == 0, b, w
            (out / "audit.json").write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
            blocking += b
            warnings += w
            if (out / "sheet.png").exists():
                previews.append(str(out / "sheet.png"))
    print(f"[set_preview] {len(ids)} set(s): {blocking} blocking, {warnings} warning(s), {len(previews)} sheet(s)")
    print(json.dumps({"previews": previews, "blocking": blocking, "warnings": warnings}), flush=True)
    sys.exit(rc or (1 if blocking else 0))


def main():
    a = parse()
    if a.clip:
        clip_mode(a)
    if not a.set or not a.out:
        print("[set_preview] give --set <file> --out <dir>, or --clip <clip dir> [--set <id>]")
        sys.exit(2)
    setp = Path(a.set).resolve()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    timing = {"set": str(setp)}
    shot = stagekit.begin("set_preview", 1.0, a.quality)
    sc = bpy.context.scene
    if a.res:
        w, h = (int(x) for x in a.res.lower().split("x"))
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    else:
        sc.render.resolution_percentage = 50 if a.quality != "final" else 100
    if a.samples:
        sc.eevee.taa_render_samples = a.samples
    mod = load_set(setp)
    mood = a.time or next(iter(getattr(mod, "LIGHT", {"interior_day": 0})))
    t0 = time.perf_counter()
    try:
        S = mod.build_set(mood)
    except Exception:
        traceback.print_exc()
        print("[set_preview] BUILD FAILED")
        sys.exit(3)
    timing["build_s"] = round(time.perf_counter() - t0, 2)
    S = S if isinstance(S, dict) else {}
    room = S.get("room")
    MARK = getattr(mod, "MARK", None) or S.get("mark") or {}
    WIDE = getattr(mod, "WIDE", None) or S.get("wide")
    if WIDE is None:
        print("[set_preview] the set file has no WIDE = (pos, aim, lens)")
        sys.exit(3)
    wpos, waim, wlens = Vector(WIDE[0]), Vector(WIDE[1]), float(WIDE[2])
    centre = Vector(room.at) if room is not None else (sum((Vector((v[0], v[1], 0.0)) for v in MARK.values()), Vector((0, 0, 0))) / max(1, len(MARK)) if MARK else Vector((waim.x, waim.y, 0)))
    centre = Vector((centre.x, centre.y, 0.0))

    def rot(p, deg, k=1.0):
        d = Vector((p.x - centre.x, p.y - centre.y, 0.0)) * k
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return Vector((centre.x + d.x * c - d.y * s, centre.y + d.x * s + d.y * c, p.z))

    def inside(p, pad=0.9):
        return room is None or (room.lo[0] + pad < p.x < room.hi[0] - pad and room.lo[1] + pad < p.y < room.hi[1] - pad)

    def cross(deg):
        """The wide camera turned round the middle of the stage, pulled in until it stands inside the room."""
        k = 1.0
        p = rot(wpos, deg, k)
        while not inside(p) and k > 0.2:
            k *= 0.93
            p = rot(wpos, deg, k)
        return p

    views = {
        "wide": (wpos, waim, wlens),
        "cross_a": (cross(55), Vector((centre.x, centre.y, 1.6)), wlens),
        "cross_b": (cross(-55), Vector((centre.x, centre.y, 1.6)), wlens),
    }
    # reverse: from the far side, a little inside, looking back along the wide's line of sight
    rp = Vector((centre.x + (centre.x - wpos.x) * 0.6, centre.y + (centre.y - wpos.y) * 0.6, wpos.z))
    views["reverse"] = (rp, Vector((2 * centre.x - waim.x, 2 * centre.y - waim.y, waim.z)), wlens)
    if MARK:
        ranked = sorted(MARK.items(), key=lambda kv: (Vector((kv[1][0], kv[1][1], 0)) - Vector((waim.x, waim.y, 0))).length)
        m0 = ranked[len(ranked) // 2][1]
        lp = Vector((m0[0], m0[1], 0.5))
        toward = Vector((waim.x, waim.y, 0)) - Vector((lp.x, lp.y, 0))
        toward = toward.normalized() if toward.length > 1e-3 else Vector((0, 1, 0))
        side = Vector((-toward.y, toward.x, 0.0))
        views["low"] = (lp + side * 0.9 - toward * 0.3, Vector((waim.x, waim.y, 1.9)), 24.0)
    else:
        views["low"] = (Vector((wpos.x, wpos.y, 0.6)), waim, wlens)

    # ---- the angles the set file declares for its film, in addition to (or instead of) the derived ones
    declared = getattr(mod, "PREVIEWS", None) or S.get("previews") or {}
    if declared:
        if getattr(mod, "PREVIEWS_ONLY", False) or S.get("previews_only"):
            views = {}
        for n, (p, q, l) in declared.items():
            views[str(n)] = (Vector(p), Vector(q), float(l))
    order = [n for n in ORDER if n in views and n != "plan"] + [n for n in declared if n in views and n not in ORDER] + ["plan"]

    # ---- the audit comes first: it measures the set, not the preview furniture
    t0 = time.perf_counter()
    cams = [{"name": n, "pos": p, "aim": q, "lens": l} for n, (p, q, l) in views.items() if n != "plan"]
    res = audit.audit(cams, room=room, exterior=(room is None), interior=(room is not None))
    timing["audit_s"] = round(time.perf_counter() - t0, 2)
    (out / "audit.json").write_text(json.dumps({**res, "timing": timing, "views": {k: [list(v[0]), list(v[1]), v[2]] for k, v in views.items()}, "mood": mood,
                                                  "inventory_dress": getattr(room, "inventory", None) if room is not None else S.get("inventory")}, indent=1, default=str), encoding="utf-8")
    inv = res["inventory"]
    print(f"[audit] types {inv['prop_types']}  objects {inv['objects_visible']}  layers {inv['layers']}  practicals {inv['practicals_visible']}/{inv['practicals_total']}  atmosphere {inv['atmosphere']}  details {inv['details']}  tris {inv['triangles']}")
    for i in res["issues"]:
        print(f"[{i['level']}] {i['code']}: {i['object']}: {i['detail']}")
    print(f"[audit] {'OK' if res['ok'] else 'BLOCKED'} in {timing['audit_s']}s ({sum(1 for i in res['issues'] if i['level'] == 'block')} block, {sum(1 for i in res['issues'] if i['level'] == 'warn')} warn)")

    nb = sum(1 for i in res["issues"] if i["level"] == "block")
    nw = sum(1 for i in res["issues"] if i["level"] == "warn")

    def finish(sheet):
        print(json.dumps({"previews": [str(sheet)] if sheet else [], "blocking": nb, "warnings": nw}), flush=True)
        sys.exit(0 if res["ok"] else 1)

    if a.no_render:
        finish(None)

    # ---- scale people and the labels for the plan
    for n, m in MARK.items():
        standin((m[0], m[1], m[2] if len(m) > 2 else 0.0), f"standin_{n}")
    labels = [label(n, (m[0], m[1] + 0.5, (m[2] if len(m) > 2 else 0.0) + 0.05)) for n, m in MARK.items()]
    for lb in labels:
        lb.hide_render = True
    cam = mk_camera()
    only = a.views.split(",") if a.views else order
    rendered = []
    timing["render_s"] = {}

    def snap(name):
        sc.render.filepath = str(out / f"{name}.png")
        t1 = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        timing["render_s"][name] = round(time.perf_counter() - t1, 2)
        rendered.append(out / f"{name}.png")
        lum, clip, crush = exposure(out / f"{name}.png")
        ex = core.STYLE["exposure"]
        flag = ""
        if not (ex["frame_mean_luma"][0] <= lum <= ex["frame_mean_luma"][1]) or clip > ex["max_clipped_fraction"]:
            flag = "  <-- outside style/style.json > exposure"
        timing.setdefault("exposure", {})[name] = {"mean_luma": round(lum, 3), "clipped": round(clip, 3), "crushed": round(crush, 3)}
        print(f"[render] {name}: {timing['render_s'][name]}s  luma {lum:.2f} clipped {clip:.3f} crushed {crush:.2f}{flag}")

    for name in order:
        if name not in only:
            continue
        for lb in labels:
            lb.hide_render = (name != "plan")
        if name == "plan":
            size = (room.size[0], room.size[1]) if room is not None else (60, 40)
            if room is not None:
                arch.cutaway(room, Vector((centre.x, centre.y, room.h + 30.0)), ceiling=True)
            asp = sc.render.resolution_x / sc.render.resolution_y
            ext = max(size[1] * 1.1 + 1.0, (size[0] * 1.1 + 1.0) / asp)        # the whole room, whatever its shape, in the tall frame
            look_down(cam, Vector((centre.x, centre.y, 60.0)), (0.0, 1.0), ext)
        else:
            p, q, l = views[name]
            aim(cam, p, q, l)
            if room is not None:
                arch.cutaway(room, p)
        snap(name)
    if rendered:
        sw, sh = tile(rendered, out / "sheet.png", cols=3)
        print(f"[sheet] {out / 'sheet.png'} ({sw}x{sh}) order: {', '.join(n for n in order if n in only)}")
    timing["triangles"] = inv["triangles"]
    (out / "timing.json").write_text(json.dumps(timing, indent=1), encoding="utf-8")
    finish(out / "sheet.png" if rendered else None)


if __name__ == "__main__":
    main()
