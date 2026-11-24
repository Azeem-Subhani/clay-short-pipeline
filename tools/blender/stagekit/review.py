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
    out = {"still": label, "view": view_id, "frame": frame, "t": round(t, 2), "words": shot.said(t - 0.4, t + 0.6), "subjects": {}, "issues": []}
    if cam is None:
        out["issues"].append("no camera: create camera.Camera() and at least one cam.view(...)")
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
                    out["issues"].append(f"{name}: the caption line covers {int(overlap * 100)}% of the face. Raise the subject in frame (place=0.36) or reframe.")
                if not wide and info["head_height"] < 0.035:
                    out["issues"].append(f"{name}: the face is only {info['head_height'] * 100:.1f}% of the frame height in a '{v.get('size', '?')}' view: too small to read on a phone. Go closer, or mark the view wide if the place is the subject.")
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
                out["issues"].append(f"{name} is hidden behind {ob.name}")
            if info.get("in_safe_area") is False and not info.get("hidden_behind"):
                out["issues"].append(f"{name} sits under the Shorts UI (x={info['x']}, {info['y_from_top']} from the top): keep faces and key props inside the yellow box")
        out["subjects"][name] = info
    if shot.subjects and not visible:
        out["issues"].append("nothing the plan cares about is in frame in this still")
    # feet on the ground
    for name, actor in shot.actors.items():
        if any(a <= t <= b for (n, a, b) in shot.airborne if n == name) or getattr(actor, "floating", False):
            continue
        base = actor.stage.evaluated_get(dg).matrix_world.translation.copy()
        x, y, z = cam.project(base)
        if not (0 <= x <= 1 and 0 <= y <= 1 and z > 0):
            continue
        origin = base + Vector((0, 0, 1.2))
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, origin, Vector((0, 0, -1)), distance=6.0)
        skip = _own(actor)
        tries = 0
        while hit and ob is not None and (ob.name in skip or any(c.name in ("FX",) or c.name.startswith("CAST") for c in ob.users_collection)) and tries < 60:
            hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, loc - Vector((0, 0, 0.01)), Vector((0, 0, -1)), distance=6.0)
            tries += 1
        if hit:
            gap = base.z - loc.z
            if abs(gap) > 0.06:
                out["issues"].append(f"{name} {'floats' if gap > 0 else 'is sunk'} {abs(gap):.2f} m {'above' if gap > 0 else 'into'} {ob.name}: stand them on it (z={loc.z:.2f}), or mark the moment with actor.move(..., arc=) / actor.floating = True")
    # the camera itself
    hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, cam_pos, fwd, distance=0.35)
    if hit and ob is not None:
        out["issues"].append(f"the camera is inside or pressed against {ob.name}: move it back")
    below, *_ = sc.ray_cast(dg, cam_pos, Vector((0, 0, -1)), distance=30.0)
    if not below:                                             # a camera down in a drained pond or a pit still has a floor under it
        out["issues"].append("the camera is under the ground: nothing is below it")
    cast_in_frame = any(n in shot.actors and i.get("in_frame") for n, i in out["subjects"].items())
    if abs(out["camera_tilt_deg"]) > 32 and cast_in_frame:
        out["issues"].append(f"the camera looks {'down' if out['camera_tilt_deg'] > 0 else 'up'} {abs(out['camera_tilt_deg']):.0f} degrees with characters in frame: "
                             "flat figures turn to slivers beyond about 30. Keep steep angles for inserts of objects.")
    if still and Path(still).exists():
        rgb = _load_pixels(still)
        lum = _luma(rgb)
        out["frame_luma"] = round(float(lum.mean()), 3)
        out["clipped"] = round(float((lum > 0.985).mean()), 4)
        out["crushed"] = round(float((lum < 0.012).mean()), 4)
        if out["clipped"] > ex["max_clipped_fraction"]:
            out["issues"].append(f"{out['clipped'] * 100:.1f}% of the frame is burnt white: a light or the sky is too strong")
        if out["crushed"] > ex["max_crushed_fraction"]:
            out["issues"].append(f"{out['crushed'] * 100:.0f}% of the frame is pure black: darkness should be deep colour (raise ambient)")
        if not (ex["frame_mean_luma"][0] <= out["frame_luma"] <= ex["frame_mean_luma"][1]):
            out["issues"].append(f"frame brightness {out['frame_luma']} is outside {ex['frame_mean_luma']}")
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


def contact_sheet(paths: list[Path], out: Path, cols: int = 6, max_height: int = 640):
    """Stills in time order, left to right and top to bottom. Yellow box = Shorts safe area. Blue lines = caption band."""
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


def stills(shot, out_dir: Path, sheet: bool = True, only=None) -> dict:
    """Render the review frames of the current shot and write checks.json + sheet.png next to them."""
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = []                                                  # stills of other views from an earlier run (only= renders a few views)
    if not only:
        for old in [*out_dir.glob("*.png"), out_dir / "checks.json"]:
            if old.exists():
                old.unlink()
    elif (out_dir / "checks.json").exists():
        try:
            for m in json.loads((out_dir / "checks.json").read_text(encoding="utf-8")).get("stills", []):
                if m.get("view") in only or not (out_dir / m.get("file", "?")).exists():
                    if (out_dir / m.get("file", "?")).exists():
                        (out_dir / m["file"]).unlink()         # this view is being redone
                else:
                    kept.append(m)
        except (ValueError, OSError):
            kept = []
    cam = getattr(shot, "camera", None)
    sc = bpy.context.scene
    report = {"shot": shot.id, "seconds": shot.seconds, "frames": shot.frames, "quality": shot.quality, "notes": shot.notes,
              "views": getattr(cam, "views", []), "light_rig": sc.get("light_rig"), "cast_look": sc.get("cast_look"),
              "surfaces": json.loads(sc.get("surfaces_used") or "{}"), "stills": []}
    paths = []
    for i, (label, frame, vid) in enumerate(review_frames(shot, only)):
        p = out_dir / f"{frame:04d}_{label.replace('/', '_')}.png"
        t = (frame - 1) / shot.fps
        render_still(p, frame, f"{shot.id} {label}  {t:.1f}s  \"{shot.said(t - 0.35, t + 0.5)}\"")
        paths.append(p)
        report["stills"].append(checks_at(shot, label, frame, vid, p) | {"file": p.name, "view": vid})
    report["stills"] = sorted(kept + report["stills"], key=lambda m: m.get("file", ""))
    issues = sorted({f"[{m['still']}] {i}" for m in report["stills"] for i in m["issues"]})
    issues += [n for n in shot.notes if n.startswith("WORLD:")]
    # the cut list itself
    views = report["views"]
    for i, v in enumerate(views):
        f1 = (views[i + 1]["frame"] - 1) if i + 1 < len(views) else shot.frames
        v["seconds"] = round((f1 - v["frame"] + 1) / shot.fps, 2)
        v["words"] = shot.said((v["frame"] - 1) / shot.fps, f1 / shot.fps)
        lim = core.STYLE["views"]
        if v["seconds"] < lim["min_seconds"] and v["size"] != "insert":
            issues.append(f"[{v['id']}] this view lasts {v['seconds']}s: under {lim['min_seconds']}s nothing but an insert can be read. Merge it with its neighbour.")
        if v["seconds"] > lim["max_seconds_without_change"]:
            issues.append(f"[{v['id']}] this view runs {v['seconds']}s. If nothing new happens in it (an action, a reaction, a camera travel), the viewer is waiting: add a beat or a closer view.")
    if not views:
        issues.append("the shot has no camera views")
    report["issues"] = issues
    if sheet and paths:
        contact_sheet(sorted(out_dir.glob("[0-9][0-9][0-9][0-9]_*.png")), out_dir / "sheet.png")
        report["sheet"] = "sheet.png"
    (out_dir / "checks.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
