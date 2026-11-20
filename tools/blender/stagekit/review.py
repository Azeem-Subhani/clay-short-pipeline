"""stagekit.review - review stills, a contact sheet with the Shorts safe area drawn on, and measured checks.

Scripts measure what can be measured (framing, focus, occlusion, exposure); eyes judge the rest from the stills.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

from . import camera as camera_mod
from . import core


def moment_frames(shot) -> list[tuple[str, int]]:
    """first frame, every marked moment, last frame - in time order, without duplicates."""
    items = [("start", 1)] + [(n, shot.f(t)) for n, t in sorted(shot.moments.items(), key=lambda kv: kv[1])] + [("end", shot.frames)]
    seen, out = set(), []
    for n, f in items:
        if f not in seen:
            seen.add(f)
            out.append((n, f))
    return out


def _load_pixels(path: Path):
    img = bpy.data.images.load(str(path), check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[..., :3]          # row 0 = bottom


def _save_pixels(arr, path: Path):
    h, w, _ = arr.shape
    img = bpy.data.images.new("sheet", w, h, alpha=False)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = arr
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    sc = bpy.context.scene
    vt, look = sc.view_settings.view_transform, sc.view_settings.look
    img.save()
    bpy.data.images.remove(img)
    sc.view_settings.view_transform, sc.view_settings.look = vt, look


def _luma(rgb):
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def _owner_objects(subject):
    if hasattr(subject, "actor"):
        a = subject.actor
        return set(o.name for o in a.meshes) | {o.name for o in a.rig.children_recursive}
    if hasattr(subject, "matrix_world"):
        return {subject.name} | {c.name for c in subject.children_recursive}
    return set()


def checks_at(shot, name: str, frame: int, still: Path | None = None) -> dict:
    """Measured facts about one frame: where each registered subject sits, whether it is sharp, hidden, well exposed."""
    sc = bpy.context.scene
    sc.frame_set(frame)
    bpy.context.view_layer.update()
    cam = getattr(shot, "camera", None)
    sa = core.STYLE["safe_area"]
    ex = core.STYLE["exposure"]
    out = {"moment": name, "frame": frame, "t": round((frame - 1) / shot.fps, 2), "subjects": {}, "issues": []}
    if cam is None:
        out["issues"].append("no camera: create camera.Camera(...) in build()")
        return out
    cd = cam.ob.data
    cam_pos = cam.ob.matrix_world.translation
    focus_d = (cam.focus.matrix_world.translation - cam_pos).length
    out["lens_mm"] = round(cd.lens, 1)
    out["fstop"] = round(cd.dof.aperture_fstop, 2) if cd.dof.use_dof else None
    out["focus_m"] = round(focus_d, 2)
    rgb = _load_pixels(still) if still and Path(still).exists() else None
    dg = bpy.context.evaluated_depsgraph_get()
    any_sharp = False
    for sname, subj in shot.subjects.items():
        only = shot.subject_moments.get(sname)
        if only and name not in only:
            continue
        p = core.point_of(subj)
        x, y, z = cam.project(p)
        info = {"x": round(x, 3), "y": round(y, 3), "distance_m": round(z, 2)}
        in_frame = 0 <= x <= 1 and 0 <= y <= 1 and z > 0
        info["in_frame"] = in_frame
        if in_frame:
            info["in_safe_area"] = sa["left"] <= x <= 1 - sa["right"] and sa["bottom"] <= y <= 1 - sa["top"]
            if cd.dof.use_dof and z > 0.05:
                f = cd.lens
                blur = abs(f * f * (z - focus_d) * 1000.0 / (cd.dof.aperture_fstop * camera_mod.SENSOR_MM * z * 1000.0 * max(focus_d * 1000.0 - f, 1.0)))
                info["blur"] = round(blur, 4)
                info["sharp"] = blur <= camera_mod.SHARP_COC * 2.2
            else:
                info["blur"], info["sharp"] = 0.0, True
            any_sharp = any_sharp or info["sharp"]
            d = Vector(p) - cam_pos
            if hasattr(subj, "point") or hasattr(subj, "matrix_world"):     # a bare point may sit inside its own object
                hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, cam_pos, d.normalized(), distance=max(0.0, d.length - 0.12))
                if hit and ob is not None and ob.name not in _owner_objects(subj):
                    info["occluded_by"] = ob.name
            if rgb is not None:
                h, w, _ = rgb.shape
                r = max(4, int(0.035 * h))
                cx, cy = int(x * w), int(y * h)
                patch = rgb[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
                if patch.size:
                    lum = _luma(patch)
                    info["luma"] = round(float(lum.mean()), 3)
                    info["contrast"] = round(float(lum.std()), 3)
        out["subjects"][sname] = info
    vis = {k: v for k, v in out["subjects"].items() if v.get("in_frame")}
    if shot.subjects and not vis:
        out["issues"].append("no registered subject is in frame")
    for k, v in vis.items():
        if v.get("occluded_by"):
            out["issues"].append(f"{k} is hidden behind {v['occluded_by']}")
        if v.get("in_safe_area") is False:
            out["issues"].append(f"{k} sits under the Shorts UI (x={v['x']}, y={v['y']}): keep key content inside the safe area")
        if "luma" in v and not v.get("occluded_by"):
            if v["luma"] < ex["subject_luma"][0]:
                out["issues"].append(f"{k} is too dark to read (luma {v['luma']}): add rim/fill or turn it toward the key - unless it is a deliberate silhouette")
            if v["luma"] > ex["subject_luma"][1]:
                out["issues"].append(f"{k} is burning out (luma {v['luma']}): weaker or larger light")
    if vis and cd.dof.use_dof and not any(v.get("sharp") for v in vis.values()):
        out["issues"].append("nothing registered is in focus: set cam focus on the subject (cam.at(focus=...), cam.rack, cam.follow)")
    if rgb is not None:
        lum = _luma(rgb)
        out["frame_luma"] = round(float(lum.mean()), 3)
        out["clipped"] = round(float((lum > 0.985).mean()), 4)
        out["crushed"] = round(float((lum < 0.012).mean()), 4)
        if out["clipped"] > ex["max_clipped_fraction"]:
            out["issues"].append(f"{out['clipped'] * 100:.1f}% of the frame is burnt white: a light is too strong or too close")
        if out["crushed"] > ex["max_crushed_fraction"]:
            out["issues"].append(f"{out['crushed'] * 100:.0f}% of the frame is pure black: darkness should be deep colour, not underexposure (raise ambient/fill)")
        top = lum[int(lum.shape[0] * 0.80):]
        if float((top < 0.012).mean()) > 0.85:
            out["issues"].append("the top of the 9:16 frame is empty black: raise the walls, add a ceiling or sky backdrop, or tilt/raise the camera")
        if not (ex["frame_mean_luma"][0] <= out["frame_luma"] <= ex["frame_mean_luma"][1]):
            out["issues"].append(f"frame brightness {out['frame_luma']} is outside {ex['frame_mean_luma']}")
    return out


def render_still(path: Path, frame: int):
    sc = bpy.context.scene
    sc.frame_set(frame)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def contact_sheet(paths: list[Path], out: Path, max_height: int = 720):
    """Stills side by side, each with the safe area outlined (content outside the box is covered by the Shorts UI)."""
    sa = core.STYLE["safe_area"]
    tiles = []
    for p in paths:
        a = _load_pixels(p)
        h, w, _ = a.shape
        step = max(1, int(math.ceil(h / max_height)))
        a = a[::step, ::step].copy()
        h, w, _ = a.shape
        x0, x1 = int(sa["left"] * w), int((1 - sa["right"]) * w) - 1
        y0, y1 = int(sa["bottom"] * h), int((1 - sa["top"]) * h) - 1
        col = np.array([1.0, 0.85, 0.2], dtype=np.float32)
        for t in range(2):
            a[y0 + t, x0:x1] = col
            a[y1 - t, x0:x1] = col
            a[y0:y1, x0 + t] = col
            a[y0:y1, x1 - t] = col
        tiles.append(a)
        tiles.append(np.full((h, 6, 3), 0.02, dtype=np.float32))
    sheet = np.concatenate(tiles[:-1], axis=1)
    _save_pixels(sheet, out)
    return out


def stills(shot, out_dir: Path, sheet: bool = True) -> dict:
    """Render the review frames of the current shot and write checks.json + sheet.png next to them."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in [*out_dir.glob("*.png"), out_dir / "checks.json"]:      # never leave a stale sheet or report next to new stills
        if old.exists():
            old.unlink()
    report = {"shot": shot.id, "seconds": shot.seconds, "frames": shot.frames, "quality": shot.quality, "notes": shot.notes,
              "camera_keys": getattr(getattr(shot, "camera", None), "keys", []), "light_rig": bpy.context.scene.get("light_rig"),
              "moments": []}
    paths = []
    for i, (name, frame) in enumerate(moment_frames(shot)):
        p = out_dir / f"{i:02d}_{name}_f{frame:04d}.png"
        render_still(p, frame)
        paths.append(p)
        report["moments"].append(checks_at(shot, name, frame, p) | {"still": p.name})
    report["issues"] = sorted({f"[{m['moment']}] {i}" for m in report["moments"] for i in m["issues"]})
    if sheet and paths:
        contact_sheet(paths, out_dir / "sheet.png")
        report["sheet"] = "sheet.png"
    (out_dir / "checks.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
