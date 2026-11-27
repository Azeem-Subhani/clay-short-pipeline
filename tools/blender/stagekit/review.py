"""stagekit.review - look at a shot before it is rendered: stills from every view, and measured facts about each.

For every camera view the shot defines, two stills are rendered (early and late in the view), plus one at each
shot.moment(). Each still is stamped with its view, time and the words being spoken, and drawn with the Shorts safe area
(yellow) and the caption band (blue). checks.json records what was measured: who is in frame and how large, whether a face
is hidden behind the set, sits under the captions or the Shorts UI, whether feet are on the ground, whether the camera
is inside something, exposure. The numbers find mistakes; the pictures decide whether the shot is good.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from . import core


def review_frames(shot, only=None) -> list[tuple[str, int, str]]:
    """(label, frame, view id) for every still worth looking at."""
    cam = getattr(shot, "camera", None)
    out = []
    views = list(getattr(cam, "views", [])) if cam else []
    for i, v in enumerate(views):
        if only and v["id"] not in only:
            continue
        f0 = v["frame"]
        f1 = (views[i + 1]["frame"] - 1) if i + 1 < len(views) else shot.frames
        n = f1 - f0 + 1
        if n < 20:
            picks = [("", f0 + n // 2)]
        else:
            picks = [("a", f0 + max(2, int(n * 0.22))), ("b", f0 + int(n * 0.86))]
        for tag, f in picks:
            out.append((f"{v['id']}{'.' + tag if tag else ''}", max(1, min(shot.frames, f)), v["id"]))
    for name, t in shot.moments.items():
        f = shot.f(t)
        v = cam.view_at(f) if cam else None
        if only and (not v or v["id"] not in only):
            continue
        out.append((name, f, v["id"] if v else ""))
    if not out:
        out = [("first", 1, ""), ("last", shot.frames, "")]
    seen, uniq = set(), []
    for lab, f, vid in sorted(out, key=lambda x: x[1]):
        if f not in seen:
            seen.add(f)
            uniq.append((lab, f, vid))
    return uniq


def _load_pixels(path: Path):
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1, :, :3].copy()


def _save_pixels(arr, path: Path):
    h, w, _ = arr.shape
    img = bpy.data.images.new("sheet", w, h, alpha=False)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[:, :, :3] = arr[::-1]
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def _luma(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _own(actor) -> set:
    return {o.name for o in actor.coll.all_objects}


FEET_TOLERANCE = 0.06            # m: a figure this far above or into the surface under its soles is blocked (a shoe's own sole, about 2.6 mm, is contact)


def _is_cast_or_fx(ob) -> bool:
    return any(c.name == "FX" or c.name.startswith("CAST") for c in ob.users_collection)


def own_and_held(actor) -> set:
    """Names of everything that is the actor: its own collection, every prop it holds (and their parts), and anything parented to or
    constrained to those (a worn add-on, a bag on a strap), so the ground check never mistakes a carried box for the floor."""
    own = set(_own(actor))
    roots = []
    for pname in list(getattr(actor, "_held", {})):
        ob = bpy.data.objects.get(pname)
        if ob is not None:
            roots.append(ob)
    for ob in roots:
        own.add(ob.name)
        own.update(c.name for c in ob.children_recursive)
    # anything riding on the actor by a constraint (a prop attached by hand) or a parent chain that reaches the actor
    for ob in bpy.data.objects:
        if ob.name in own:
            continue
        cur, hops = ob.parent, 0
        while cur is not None and hops < 12:
            if cur.name in own:
                own.add(ob.name)
                break
            cur, hops = cur.parent, hops + 1
        else:
            for c in ob.constraints:
                tgt = getattr(c, "target", None)
                if tgt is not None and tgt.name in own:
                    own.add(ob.name)
                    break
    return own


def lowest_sole(actor, dg, own=None):
    """(z, (x, y)) of the lowest point of the actor's own visible meshes (the soles, shoe thickness included), at the current frame."""
    own = own if own is not None else own_and_held(actor)
    best = None
    held = set(getattr(actor, "_held", {}))
    for ob in actor.coll.all_objects:
        if ob.type != "MESH" or ob.hide_render or ob.name in held:
            continue
        ev = ob.evaluated_get(dg)
        mw = ev.matrix_world
        zmin = min((mw @ Vector(c)).z for c in ev.bound_box)
        if best is not None and zmin > best[0] + 0.3:
            continue
        try:
            me = ev.to_mesh()
        except RuntimeError:
            continue
        n = len(me.vertices)
        if n:
            co = np.empty(n * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            m = np.array(mw, dtype=np.float32)
            w = co @ m[:3, :3].T + m[:3, 3]
            i = int(np.argmin(w[:, 2]))
            if best is None or float(w[i, 2]) < best[0]:
                best = (float(w[i, 2]), (float(w[i, 0]), float(w[i, 1])))
        ev.to_mesh_clear()
    return best


def feet_gap(actor, dg):
    """(gap, object, floor_z): how far the lowest sole point is above (+) or below (-) the first surface under it that is not the actor, or
    anything the actor holds or wears, measured straight down from 35 cm above the soles and stepping through the actor's own parts. The
    floor is sampled under the lowest point and under the stage origin (the higher wins, so a heel over a step edge is not 'floating').
    (None, None, None) when there is no surface under the actor or no mesh to measure."""
    sc = bpy.context.scene
    own = own_and_held(actor)
    low = lowest_sole(actor, dg, own)
    if low is None:
        return None, None, None
    z0, xy0 = low
    base = actor.stage.evaluated_get(dg).matrix_world.translation
    found = None
    for x, y in (xy0, (base.x, base.y)):
        origin = Vector((x, y, z0 + 0.35))
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, origin, Vector((0, 0, -1)), distance=8.0)
        tries = 0
        while hit and ob is not None and (ob.name in own or _is_cast_or_fx(ob)) and tries < 150:
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, loc - Vector((0, 0, 0.0003)), Vector((0, 0, -1)), distance=8.0)
            tries += 1
        if hit and ob is not None and (found is None or loc.z > found[0]):
            found = (loc.z, ob)
    if found is None:
        return None, None, None
    return z0 - found[0], found[1], found[0]


def caption_band() -> tuple[float, float]:
    """(top, bottom) of the caption line as fractions from the TOP of the frame."""
    c = core.STYLE["captions"]
    half = c["font_size_px"] * 0.75 / core.STYLE["video"]["height"]
    return c["center_y_fraction"] - half, c["center_y_fraction"] + half


def checks_at(shot, label: str, frame: int, view_id: str, still: Path | None = None) -> dict:
    sc = bpy.context.scene
    dg = core.at_frame(frame)
    cam = getattr(shot, "camera", None)
    sa = core.STYLE["safe_area"]
    ex = core.STYLE["exposure"]
    t = (frame - 1) / shot.fps
    out = {"still": label, "view": view_id, "frame": frame, "t": round(t, 2), "words": shot.said(t - 0.4, t + 0.6), "subjects": {}, "issues": [], "items": []}

    def add(level: str, code: str, text: str):
        """One finding: the plain text stays in out['issues'] (older readers), level and code go in out['items']."""
        out["issues"].append(text)
        out["items"].append({"level": level, "code": code, "text": text})

    if cam is None:
        add("block", "no_camera", "no camera: create camera.Camera() and at least one cam.view(...)")
        return out
    cam_pos = cam.ob.matrix_world.translation.copy()
    fwd = cam.ob.matrix_world.to_3x3() @ Vector((0, 0, -1))
    out["lens_mm"] = round(cam.data.lens, 1)
    out["camera_tilt_deg"] = round(math.degrees(math.asin(max(-1, min(1, -fwd.z)))), 1)
    cap_top, cap_bot = caption_band()
    v = cam.view_at(frame) or {}
    wide = v.get("size") == "wide"
    visible = 0
    for name, subj in shot.subjects.items():
        only = shot.subject_moments.get(name)
        if only and label not in only and view_id not in only:
            continue
        actor = shot.actors.get(name)
        p = core.point_of(subj)
        x, y, z = cam.project(p)
        info = {"x": round(x, 3), "y_from_top": round(1 - y, 3), "distance_m": round(z, 2)}
        info["in_frame"] = bool(-0.02 <= x <= 1.02 and -0.02 <= y <= 1.02 and z > 0)
        if info["in_frame"]:
            visible += 1
            info["in_safe_area"] = bool(sa["left"] <= x <= 1 - sa["right"] and sa["bottom"] <= y <= 1 - sa["top"])
            if actor is not None:
                r = actor.head_r * actor.scale
                yt = cam.project(p + Vector((0, 0, r)))[1]
                yb = cam.project(p - Vector((0, 0, r)))[1]
                info["head_height"] = round(abs(yt - yb), 3)
                top_f, bot_f = 1 - max(yt, yb), 1 - min(yt, yb)
                overlap = max(0.0, min(bot_f, cap_bot) - max(top_f, cap_top)) / max(bot_f - top_f, 1e-6)
                info["under_captions"] = round(overlap, 2)
                if overlap > 0.25:
                    add("warn", "face_under_captions", f"{name}: the caption line covers {int(overlap * 100)}% of the face. Raise the subject in frame (place=0.36) or reframe.")
                if not wide and info["head_height"] < 0.035:
                    add("warn", "face_too_small", f"{name}: the face is only {info['head_height'] * 100:.1f}% of the frame height in a '{v.get('size', '?')}' view: too small to read on a phone. Go closer, or mark the view wide if the place is the subject.")
            d = p - cam_pos
            skip = _own(actor) if actor is not None else ({subj.name} | {c.name for c in subj.children_recursive} if hasattr(subj, "children_recursive") else set())
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, cam_pos, d.normalized(), distance=max(0.0, d.length - 0.1))
            tries = 0
            while hit and ob is not None and (ob.name in skip or ob.users_collection and ob.users_collection[0].name in ("FX", "CAST") or ob.name.startswith("CAST_")) and tries < 6:
                start = loc + d.normalized() * 0.02
                rest = (p - start).length - 0.1
                if rest <= 0:
                    hit = False
                    break
                hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, start, d.normalized(), distance=rest)
                tries += 1
            if hit and ob is not None and ob.name not in skip and not any(c.name.startswith("CAST") for c in ob.users_collection):
                info["hidden_behind"] = ob.name
                add("block", "subject_hidden", f"{name} is hidden behind {ob.name}")
            if info.get("in_safe_area") is False and not info.get("hidden_behind"):
                add("warn", "outside_safe_area", f"{name} sits under the Shorts UI (x={info['x']}, {info['y_from_top']} from the top): keep faces and key props inside the yellow box")
        out["subjects"][name] = info
    if shot.subjects and not visible:
        add("block", "nothing_in_frame", "nothing the plan cares about is in frame in this still")
    # feet on the ground
    for name, actor in shot.actors.items():
        if any(a <= t <= b for (n, a, b) in shot.airborne if n == name) or getattr(actor, "floating", False):
            continue
        base = actor.stage.evaluated_get(dg).matrix_world.translation.copy()
        x, y, z = cam.project(base)
        if not (0 <= x <= 1 and 0 <= y <= 1 and z > 0):
            continue
        gap, ob, floor_z = feet_gap(actor, dg)
        if gap is not None and abs(gap) > FEET_TOLERANCE:
            add("block", "actor_floating" if gap > 0 else "actor_sunk", f"{name} {'floats' if gap > 0 else 'is sunk'} {abs(gap):.2f} m {'above' if gap > 0 else 'into'} {ob.name}: stand them on it (z={floor_z:.2f}), or mark the moment with actor.move(..., arc=) / actor.floating = True")
    # the camera itself
    hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, cam_pos, fwd, distance=0.35)
    if hit and ob is not None:
        add("block", "camera_inside_geometry", f"the camera is inside or pressed against {ob.name}: move it back")
    below, *_ = sc.ray_cast(dg, cam_pos, Vector((0, 0, -1)), distance=30.0)
    if not below:                                             # a camera down in a drained pond or a pit still has a floor under it
        add("block", "camera_under_floor", "the camera is under the ground: nothing is below it")
    cast_in_frame = any(n in shot.actors and i.get("in_frame") for n, i in out["subjects"].items())
    if abs(out["camera_tilt_deg"]) > 60 and cast_in_frame:               # the cast is solid 3D: a steep angle is allowed, a near-vertical one is worth a look
        add("warn", "steep_angle", f"the camera looks {'up' if out['camera_tilt_deg'] < 0 else 'down'} {abs(out['camera_tilt_deg']):.0f} degrees with characters in frame: "
                                   "past 60 degrees heads foreshorten and faces are hard to read. Fine for a top-down map or a deliberate low hero shot.")
    if still and Path(still).exists():
        rgb = _load_pixels(still)
        lum = _luma(rgb)
        out["frame_luma"] = round(float(lum.mean()), 3)
        out["clipped"] = round(float((lum > 0.985).mean()), 4)
        out["crushed"] = round(float((lum < 0.012).mean()), 4)
        if out["clipped"] > ex["max_clipped_fraction"]:
            add("block" if out["clipped"] >= 0.5 else "warn", "blown_out", f"{out['clipped'] * 100:.1f}% of the frame is burnt white: a light or the sky is too strong")
        if out["crushed"] > ex["max_crushed_fraction"]:
            add("block" if out["crushed"] >= 0.85 else "warn", "mostly_black", f"{out['crushed'] * 100:.0f}% of the frame is pure black: darkness should be deep colour (raise ambient)")
        if not (ex["frame_mean_luma"][0] <= out["frame_luma"] <= ex["frame_mean_luma"][1]):
            add("block" if (out["frame_luma"] < 0.02 or out["frame_luma"] > 0.95) else "warn", "brightness", f"frame brightness {out['frame_luma']} is outside {ex['frame_mean_luma']}")
        band = rgb[int(cap_top * rgb.shape[0]):int(cap_bot * rgb.shape[0]), int(0.14 * rgb.shape[1]):int(0.86 * rgb.shape[1])]
        if band.size:
            bl = _luma(band)
            out["caption_band_luma"] = round(float(bl.mean()), 3)
            out["caption_band_busy"] = round(float(bl.std()), 3)
    return out


def render_still(path: Path, frame: int, note: str = ""):
    sc = bpy.context.scene
    sc.frame_set(frame)
    r = sc.render
    r.use_stamp = bool(note)
    if note:
        r.use_stamp_note = True
        r.stamp_note_text = note
        for k in ("use_stamp_date", "use_stamp_time", "use_stamp_render_time", "use_stamp_frame", "use_stamp_scene", "use_stamp_camera", "use_stamp_filename",
                  "use_stamp_lens", "use_stamp_marker", "use_stamp_memory", "use_stamp_hostname", "use_stamp_frame_range", "use_stamp_sequencer_strip"):
            if hasattr(r, k):
                setattr(r, k, False)
        r.stamp_font_size = max(9, int(r.resolution_y * r.resolution_percentage / 100 * 0.022))
        r.stamp_background = (0, 0, 0, 0.75)
        r.stamp_foreground = (1, 1, 1, 1)
        r.use_stamp_labels = False
    r.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    r.use_stamp = False


def contact_sheet(paths: list[Path], out: Path, cols: int = 6, max_height: int = 640, marks: bool = True):
    """Stills in time order, left to right and top to bottom. Yellow box = Shorts safe area. Blue lines = caption band
    (marks=False leaves the pictures clean, for the dense sheets that are read for contact and clipping)."""
    sa = core.STYLE["safe_area"]
    cap_top, cap_bot = caption_band()
    tiles = []
    for p in paths:
        a = _load_pixels(p)
        h, w, _ = a.shape
        step = max(1, int(math.ceil(h / max_height)))
        a = a[::step, ::step].copy()
        h, w, _ = a.shape
        x0, x1 = int(sa["left"] * w), int((1 - sa["right"]) * w) - 1
        y0, y1 = int(sa["top"] * h), int((1 - sa["bottom"]) * h) - 1
        yel = np.array([1.0, 0.85, 0.2], dtype=np.float32)
        blu = np.array([0.3, 0.75, 1.0], dtype=np.float32)
        if marks:
            a[y0, x0:x1] = yel
            a[y1, x0:x1] = yel
            a[y0:y1, x0] = yel
            a[y0:y1, x1] = yel
            for yy in (int(cap_top * h), int(cap_bot * h)):
                a[min(h - 1, yy), int(0.14 * w):int(0.86 * w):2] = blu
        tiles.append(a)
    h, w, _ = tiles[0].shape
    cols = min(cols, len(tiles))
    rows = -(-len(tiles) // cols)
    sheet = np.full((rows * (h + 6), cols * (w + 6), 3), 0.03, dtype=np.float32)
    for i, a in enumerate(tiles):
        r, c = divmod(i, cols)
        hh, ww, _ = a.shape
        sheet[r * (h + 6):r * (h + 6) + min(h, hh), c * (w + 6):c * (w + 6) + min(w, ww)] = a[:h, :w]
    _save_pixels(sheet, out)
    return out


DENSE_STEP = 12                                                # frames between dense review frames: two a second at 24 fps
DENSE_PER_SHEET = 6                                            # 3 x 2: each frame stays large enough to see a hand on a handle
DENSE_PERCENT = 50                                             # dense frames are rendered at least this large (540x960), whatever the stills quality: in the
                                                               # study a reviewer found 62% of the faults at this size against 48% at 270x480, most of the gain
                                                               # in glasses, lanyards and collars


def dense_sheets(shot, out_dir: Path, only=None, step: int = DENSE_STEP) -> dict:
    """The whole shot, two frames a second, on clean sheets of six (review/<shot>/dense/dense_NN.png): what the reviewer reads for
    contact, clipping, facing and continuity between the few posed stills. A blind test on the first film (docs/PIPELINE_FAULT_STUDY.md)
    found a reviewer catches about half of all such faults, and most of the severe ones, from sheets like these. With only= (a few
    views redone) the frames of the other views are kept and every sheet is tiled again."""
    cam = getattr(shot, "camera", None)
    dd = out_dir / "dense"
    dd.mkdir(parents=True, exist_ok=True)
    frames = sorted({*range(1, shot.frames + 1, max(1, step)), shot.frames})
    for old in dd.glob("f*.png"):
        f = int(old.stem[1:])
        v = cam.view_at(f) if cam else None
        if f not in frames or not only or (v and v["id"] in only):
            old.unlink()
    for old in dd.glob("dense_*.png"):
        old.unlink()
    r = bpy.context.scene.render
    was = r.resolution_percentage
    r.resolution_percentage = max(was, DENSE_PERCENT)
    try:
        for f in frames:
            p = dd / f"f{f:04d}.png"
            if p.exists():
                continue
            v = cam.view_at(f) if cam else None
            t = (f - 1) / shot.fps                                # the narrator's words at this frame go in the stamp: what is shown is
            render_still(p, f, f"{shot.id} {v['id'] if v else ''}  f{f}/{shot.frames}  {t:.1f}s  \"{shot.said(t - 0.3, t + 0.3)}\"")   # read against what is said
    finally:
        r.resolution_percentage = was
    paths = sorted(dd.glob("f*.png"))
    sheets = []
    for i in range(0, len(paths), DENSE_PER_SHEET):
        out = dd / f"dense_{i // DENSE_PER_SHEET + 1:02d}.png"
        contact_sheet(paths[i:i + DENSE_PER_SHEET], out, cols=3, max_height=10 ** 6, marks=False)
        sheets.append(f"dense/{out.name}")
    return {"step": step, "frames": [int(p.stem[1:]) for p in paths], "sheets": sheets}


FONT = next((f for f in ("C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf") if Path(f).exists()), None)
LONG_VIEW_S = 2.5                                              # a view held longer than this gets a motion strip even without a move of its own


def _ff_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace("%", "\\%").replace(",", "\\,")


def _burn_labels(src: Path, labels: list[tuple[int, int, str, int]]) -> bool:
    """Draw (x, y, text, size) labels on a PNG with FFmpeg. Returns False (picture left as it is) when FFmpeg or a font is missing."""
    ff = shutil.which("ffmpeg")
    if not ff or not FONT:
        return False
    font = FONT.replace(":", "\\:")
    chain = ",".join(f"drawtext=fontfile='{font}':text='{_ff_text(t)}':x={x}:y={y}:fontsize={fs}:fontcolor=white" for x, y, t, fs in labels)
    script = src.with_suffix(".ffscript")
    script.write_text(chain, encoding="utf-8")
    tmp = src.with_name(src.stem + "_lab.png")
    ok = False
    for flag in ("-/vf", "-filter_script:v"):                 # the first spelling is FFmpeg 7+; the second is older
        r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), flag, str(script), "-frames:v", "1", str(tmp)], capture_output=True, text=True)
        if r.returncode == 0 and tmp.exists():
            ok = True
            break
    script.unlink(missing_ok=True)
    if ok:
        tmp.replace(src)
    else:
        tmp.unlink(missing_ok=True)
    return ok


def motion_targets(shot, only=None) -> list[dict]:
    """What needs a motion strip: every move the camera was given (the automatic drift is left out: it is the hold below) and every
    view held longer than LONG_VIEW_S that no move of its own already covers for most of its length."""
    cam = getattr(shot, "camera", None)
    if cam is None:
        return []
    views = list(cam.views)
    span = {}
    for i, v in enumerate(views):
        span[v["id"]] = (v["frame"], (views[i + 1]["frame"] - 1) if i + 1 < len(views) else shot.frames)
    out, covered, names = [], {}, {}

    def name_for(base: str) -> str:
        names[base] = names.get(base, 0) + 1
        return base if names[base] == 1 else f"{base}_{names[base]}"

    for m in cam.moves:
        if m.get("auto") or m["type"] == "drift":
            continue
        vid = m.get("view") or ""
        if only and vid not in only:
            continue
        f0, f1 = max(1, shot.f(m["t0"])), min(shot.frames, shot.f(m["t1"]))
        if f1 <= f0:
            f1 = min(shot.frames, f0 + 1)
        out.append({"view": vid, "move": m["type"], "f0": f0, "f1": f1, "name": name_for(f"{vid}_{m['type']}")})
        covered[vid] = covered.get(vid, 0) + (f1 - f0 + 1)
    for vid, (a, b) in span.items():
        if only and vid not in only:
            continue
        n = b - a + 1
        if n / shot.fps > LONG_VIEW_S and covered.get(vid, 0) < 0.8 * n:
            drift = next((m for m in cam.moves if m.get("view") == vid and m["type"] == "drift"), None)
            kind = "drift" if drift else "hold"
            out.append({"view": vid, "move": kind, "f0": a, "f1": b, "name": name_for(f"{vid}_{kind}")})
    return sorted(out, key=lambda t: (t["f0"], t["name"]))


def motion_strips(shot, out_dir: Path, still_files: dict[int, Path], only=None, max_height: int = 640) -> list[dict]:
    """A 5-frame strip (start, 25%, 50%, 75%, end) for each target of motion_targets(), written to <out_dir>/motion/<view>_<move>.png and
    labelled with view id, move type and frame numbers. Frames that a review still already shows are reused; frames shared between strips
    are rendered once. Tiles are cut down to at most max_height pixels tall, like the contact sheet."""
    targets = motion_targets(shot, only)
    if not targets:
        return []
    mdir = out_dir / "motion"
    tmp = mdir / "_frames"
    mdir.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    pix: dict[int, np.ndarray] = {}

    def tile(frame: int):
        if frame not in pix:
            src = still_files.get(frame)
            if src is None or not Path(src).exists():
                src = tmp / f"{frame:04d}.png"
                if not src.exists():
                    render_still(src, frame)
            a = _load_pixels(Path(src))
            step = max(1, int(math.ceil(a.shape[0] / max_height)))
            pix[frame] = a[::step, ::step].copy()
        return pix[frame]

    out = []
    for t in targets:
        f0, f1 = t["f0"], t["f1"]
        frames = [int(round(f0 + (f1 - f0) * k / 4)) for k in range(5)]
        tiles = [tile(f) for f in frames]
        h, w, _ = tiles[0].shape
        gap, fs = 4, max(12, w // 20)
        hdr = 2 * fs + 14
        sheet = np.full((hdr + h, 5 * w + 4 * gap, 3), 0.02, dtype=np.float32)
        for i, a in enumerate(tiles):
            sheet[hdr:hdr + min(h, a.shape[0]), i * (w + gap):i * (w + gap) + min(w, a.shape[1])] = a[:h, :w]
        path = mdir / f"{t['name']}.png"
        _save_pixels(sheet, path)
        labels = [(6, 4, f"{t['view']}  {t['move']}  frames {f0}-{f1}  ({(f0 - 1) / shot.fps:.2f}-{f1 / shot.fps:.2f} s)", fs)]
        for i, (f, pct) in enumerate(zip(frames, (0, 25, 50, 75, 100))):
            labels.append((i * (w + gap) + 6, fs + 9, f"f{f} {pct}pct", fs))
        labelled = _burn_labels(path, labels)
        out.append({"file": f"motion/{path.name}", "view": t["view"], "move": t["move"], "frames": frames, "t0": round((f0 - 1) / shot.fps, 3),
                    "t1": round(f1 / shot.fps, 3), "labelled": labelled})
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def _level_items(m: dict) -> list[dict]:
    """The findings of one still, with levels. A checks.json from before levels existed has strings only: those count as warnings."""
    its = m.get("items")
    if its is None:
        its = [{"level": "warn", "code": "measured", "text": t} for t in m.get("issues", [])]
    return [{**it, "source": "still", "view": m.get("view"), "frame": m.get("frame"), "still": m.get("still")} for it in its]


def _merge_items(items: list[dict]) -> list[dict]:
    """The same finding in two stills of one view is one finding: keep the first, list the stills."""
    seen: dict[tuple, dict] = {}
    for it in items:
        key = (it["source"], it.get("view"), it["code"], it["text"] if it["source"] != "campath" else it.get("frame"))
        if key in seen:
            if it.get("still") and it["still"] not in seen[key].setdefault("stills", []):
                seen[key]["stills"].append(it["still"])
            continue
        it = dict(it)
        if it["source"] == "still":
            it["stills"] = [it.pop("still")] if it.get("still") else []
        seen[key] = it
    return list(seen.values())


def stills(shot, out_dir: Path, sheet: bool = True, only=None, strips: bool = True) -> dict:
    """Render the review frames of the current shot and write checks.json + sheet.png next to them, the camera path measurements
    (campath.json) and the motion strips (motion/*.png).

    checks.json: "issues" (plain text lines, as before), "items" (the same findings with level block|warn, code, source still|view|world|campath,
    view, frame, text), "blocking" and "warnings" (counts of items), "campath" (the whole-shot camera report summary and its issues), "motion"
    (the strips). A blocking item must be fixed before the shot is rendered."""
    from . import campath, physical
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = []                                                  # stills of other views from an earlier run (only= renders a few views)
    kept_motion = []
    if not only:
        for old in [*out_dir.glob("*.png"), out_dir / "checks.json"]:
            if old.exists():
                old.unlink()
        shutil.rmtree(out_dir / "motion", ignore_errors=True)
    elif (out_dir / "checks.json").exists():
        try:
            old_report = json.loads((out_dir / "checks.json").read_text(encoding="utf-8"))
            for m in old_report.get("stills", []):
                if m.get("view") in only or not (out_dir / m.get("file", "?")).exists():
                    if (out_dir / m.get("file", "?")).exists():
                        (out_dir / m["file"]).unlink()         # this view is being redone
                else:
                    kept.append(m)
            for m in old_report.get("motion", []):
                if m.get("view") in only:
                    (out_dir / m["file"]).unlink(missing_ok=True)
                elif (out_dir / m["file"]).exists():
                    kept_motion.append(m)
        except (ValueError, OSError, KeyError):
            kept, kept_motion = [], []
    cam = getattr(shot, "camera", None)
    sc = bpy.context.scene
    report = {"shot": shot.id, "seconds": shot.seconds, "frames": shot.frames, "quality": shot.quality, "notes": shot.notes,
              "views": getattr(cam, "views", []), "light_rig": sc.get("light_rig"), "cast_look": sc.get("cast_look"),
              "surfaces": json.loads(sc.get("surfaces_used") or "{}"), "stills": []}
    cp = campath.analyse(shot)                                  # the whole camera path, every second frame (the stills below only see a few frames)
    campath.write(cp, out_dir / "campath.json")
    ph = physical.sweep(shot)                                   # contact, passage, grip, carry and reach measured over the whole shot, whatever views are redone
    (out_dir / "physical.json").write_text(json.dumps(ph, indent=1), encoding="utf-8")
    paths = []
    still_files: dict[int, Path] = {}
    for i, (label, frame, vid) in enumerate(review_frames(shot, only)):
        p = out_dir / f"{frame:04d}_{label.replace('/', '_')}.png"
        t = (frame - 1) / shot.fps
        render_still(p, frame, f"{shot.id} {label}  {t:.1f}s  \"{shot.said(t - 0.35, t + 0.5)}\"")
        paths.append(p)
        still_files[frame] = p
        report["stills"].append(checks_at(shot, label, frame, vid, p) | {"file": p.name, "view": vid})
    report["stills"] = sorted(kept + report["stills"], key=lambda m: m.get("file", ""))
    issues = sorted({f"[{m['still']}] {i}" for m in report["stills"] for i in m["issues"]})
    items = [it for m in report["stills"] for it in _level_items(m)]
    for n in shot.notes:
        if n.startswith("WORLD:"):
            issues.append(n)
            items.append({"level": "warn", "code": "world", "source": "world", "view": None, "frame": None, "text": n})
    # the cut list itself
    views = report["views"]
    for i, v in enumerate(views):
        f1 = (views[i + 1]["frame"] - 1) if i + 1 < len(views) else shot.frames
        v["seconds"] = round((f1 - v["frame"] + 1) / shot.fps, 2)
        v["words"] = shot.said((v["frame"] - 1) / shot.fps, f1 / shot.fps)
        lim = core.STYLE["views"]
        if v["seconds"] < lim["min_seconds"] and v["size"] != "insert":
            text = f"this view lasts {v['seconds']}s: under {lim['min_seconds']}s nothing but an insert can be read. Merge it with its neighbour."
            issues.append(f"[{v['id']}] {text}")
            items.append({"level": "warn", "code": "view_too_short", "source": "view", "view": v["id"], "frame": v["frame"], "text": text})
        if v["seconds"] > lim["max_seconds_without_change"]:
            text = f"this view runs {v['seconds']}s. If nothing new happens in it (an action, a reaction, a camera travel), the viewer is waiting: add a beat or a closer view."
            issues.append(f"[{v['id']}] {text}")
            items.append({"level": "warn", "code": "view_too_long", "source": "view", "view": v["id"], "frame": v["frame"], "text": text})
    if not views:
        issues.append("the shot has no camera views")
        items.append({"level": "block", "code": "no_views", "source": "view", "view": None, "frame": None, "text": "the shot has no camera views"})
    # the camera path
    for i in cp.get("issues", []):
        issues.append(f"[camera {i['view']}@{i['frame']}] {i['code']}: {i['detail']}")
        items.append({"level": i["level"], "code": i["code"], "source": "campath", "view": i["view"], "frame": i["frame"], "text": i["detail"]})
    for it in ph["items"]:                                       # the physical checks (stagekit.physical): what the scene does, not what a frame looks like
        issues.append(f"[physical {it['code']}] {it['text']}")
        items.append(it)
    report["physical"] = {"file": "physical.json", "blocking": ph["blocking"], "warnings": ph["warnings"], "seconds": ph["seconds"], "frames_checked": ph["frames_checked"],
                          "holds": ph["holds"], "interactions": ph["interactions"]}
    sa = getattr(shot, "set_audit", None)                        # set by run_shot: the plan/set agreement and stagekit.audit of the set (source "set")
    if sa:
        for it in sa["items"]:
            issues.append(f"[set {it['code']}] {it['text']}")
            items.append(it)
        report["set_audit"] = {"inventory": sa.get("inventory"), "blocking": sum(1 for it in sa["items"] if it["level"] == "block"),
                               "warnings": sum(1 for it in sa["items"] if it["level"] == "warn")}
    items = _merge_items(items)
    report["issues"] = issues
    report["items"] = items
    report["blocking"] = sum(1 for i in items if i["level"] == "block")
    report["warnings"] = sum(1 for i in items if i["level"] == "warn")
    report["campath"] = {"file": "campath.json", "blocking": cp.get("blocking", 0), "warnings": cp.get("warnings", 0), "static_share": cp.get("static_share"),
                         "moves": [{k: m.get(k) for k in ("type", "view", "t0", "t1", "peak_speed_m_s", "peak_ang_speed_deg_s", "pass", "issues")} for m in cp.get("moves", [])],
                         "issues": cp.get("issues", [])}
    if strips and cam is not None:
        report["motion"] = sorted(kept_motion + motion_strips(shot, out_dir, still_files, only), key=lambda m: (m["t0"], m["file"]))
    else:
        report["motion"] = kept_motion
    if sheet and paths:
        contact_sheet(sorted(out_dir.glob("[0-9][0-9][0-9][0-9]_*.png")), out_dir / "sheet.png")
        report["sheet"] = "sheet.png"
    if strips and cam is not None:
        report["dense"] = dense_sheets(shot, out_dir, only)
    (out_dir / "checks.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
