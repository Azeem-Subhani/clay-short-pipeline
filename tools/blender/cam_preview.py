"""Camera preview ("playblast"): every frame of a shot at low resolution, with the view and move burnt in, as an MP4,
plus a top-down diagram of the camera path and the campath measurements.

    blender -b --factory-startup --python tools/blender/cam_preview.py -- --clip output/clips/<slug> --shot sh01
    blender -b --factory-startup --python tools/blender/cam_preview.py -- --script some/shot.py --seconds 8 --out <dir>

Writes, in <clip>/review/<shot>/camera/ (or --out):
    preview.mp4     every frame, 270x480 by default; top line: view id, the moves that are running, frame counter (above the caption band)
    path.png        top-down: the set outline, marks, actors, the camera path coloured by speed (blue slow .. red fast), an arrow per move, view ids
    campath.json    the stagekit.campath report (subjects in frame, hidden faces, geometry, speed, jerk, captions)
The shot script is loaded exactly like run_shot.py does (same time base, words and plan), using its functions.
--engine draft (EEVEE with the project's draft quality, the default) or workbench (flat studio light, no shadows or materials).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
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

import stagekit  # noqa: E402
from stagekit import campath, core, review  # noqa: E402

FONT = next((f for f in ("C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf") if Path(f).exists()), None)


# ----------------------------------------------------------------------------- engine and size
def setup_render(sc, width: int, height: int, engine: str = "draft"):
    """Low-cost preview settings. 'draft' = the project's draft EEVEE quality (soft shadows, light), 'workbench' = flat studio light."""
    if engine == "workbench":
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT"
        sc.display.render_aa = "OFF"
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGB"
    else:
        core.apply_render_settings(sc, "draft")
    sc.render.resolution_x, sc.render.resolution_y = width, height
    sc.render.resolution_percentage = 100
    sc.render.use_stamp = False


# ----------------------------------------------------------------------------- labels
def frame_labels(shot) -> dict[int, str]:
    """frame -> 'view id  move+move' burnt in at the top."""
    cam = shot.camera
    moves = [m for m in cam.moves]
    out = {}
    for f in range(1, shot.frames + 1):
        v = cam.view_at(f)
        active = []
        for m in moves:
            f0, f1 = round(m["t0"] * shot.fps) + 1, round(m["t1"] * shot.fps) + 1
            if f0 <= f <= f1 and m["type"] not in active:
                active.append(m["type"])
        out[f] = f"{v['id'] if v else '-'}  {'+'.join(active) if active else 'hold'}"
    return out


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace("%", "\\%").replace(",", "\\,")


def encode(frames_dir: Path, shot, labels: dict[int, str], out_mp4: Path, step: int = 1, width: int = 270):
    """FFmpeg: PNG sequence -> MP4 with the view/move label and a frame counter burnt in at the top."""
    fs = max(10, round(width * 0.052))
    font = f"fontfile='{FONT.replace(':', chr(92) + ':')}':" if FONT else ""
    rendered = list(range(1, shot.frames + 1, step))
    runs, cur = [], None
    for n, f in enumerate(rendered):
        lab = labels.get(f, "")
        if cur and cur[2] == lab:
            cur[1] = n
        else:
            cur = [n, n, lab]
            runs.append(cur)
    chain = []
    for a, b, lab in runs:
        chain.append(f"drawtext={font}text='{_esc(lab)}':x=6:y=8:fontsize={fs}:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=3:enable='between(n\\,{a}\\,{b})'")
    chain.append(f"drawtext={font}text='%{{eif\\:n*{step}+1\\:d}}/{shot.frames}':x=w-tw-6:y=8:fontsize={fs}:fontcolor=yellow:box=1:boxcolor=black@0.6:boxborderw=3")
    # label and counter both sit at the very top, so the whole lower part stays free for the caption band
    script = frames_dir.parent / "burn.ffscript"
    script.write_text(",".join(chain), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-framerate", str(shot.fps / step), "-start_number", "1", "-i", str(frames_dir / "f_%04d.png"),
           "-/vf", str(script), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-r", str(shot.fps / step), str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode and "-/vf" in r.stderr:                                       # an older FFmpeg
        cmd[cmd.index("-/vf")] = "-filter_script:v"
        r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("ffmpeg failed: " + r.stderr[-600:])
    return out_mp4


# ----------------------------------------------------------------------------- the frames
def render_frames(shot, frames_dir: Path, step: int = 1) -> dict:
    """Render every frame (every `step`th) with Blender's animation renderer. Returns timing."""
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("f_*.png"):
        old.unlink()
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.frame_step = 1, shot.frames, step
    sc.render.filepath = str(frames_dir / "f_")
    t0 = time.perf_counter()
    bpy.ops.render.render(animation=True)
    dt = time.perf_counter() - t0
    sc.frame_step = 1
    n = len(list(frames_dir.glob("f_*.png")))
    return {"frames": n, "seconds": round(dt, 2), "s_per_frame": round(dt / max(1, n), 3)}


# ----------------------------------------------------------------------------- the path diagram
def _hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


class _Canvas:
    def __init__(self, w, h, bg=(0.07, 0.075, 0.09)):
        self.a = np.empty((h, w, 3), dtype=np.float32)
        self.a[:] = bg
        self.w, self.h = w, h

    def dot(self, x, y, r, col):
        x0, x1, y0, y1 = int(max(0, x - r)), int(min(self.w, x + r + 1)), int(max(0, y - r)), int(min(self.h, y + r + 1))
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        m = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
        self.a[y0:y1, x0:x1][m] = col

    def line(self, p, q, col, r=1.0):
        n = int(max(abs(q[0] - p[0]), abs(q[1] - p[1]), 1))
        for i in range(n + 1):
            t = i / n
            self.dot(p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, r, col)

    def tri(self, c, d, size, col):
        d = np.array(d, dtype=float)
        d = d / (np.linalg.norm(d) or 1.0)
        n = np.array([-d[1], d[0]])
        c = np.array(c, dtype=float)
        tip, b1, b2 = c + d * size, c - d * size * 0.6 + n * size * 0.6, c - d * size * 0.6 - n * size * 0.6
        for a, b in ((tip, b1), (b1, b2), (b2, tip)):
            self.line(a, b, col, 1.2)
        self.dot(c[0], c[1], 1.5, col)


def _ramp(t: float):
    t = max(0.0, min(1.0, t))
    stops = [(0.0, (0.2, 0.55, 1.0)), (0.4, (0.2, 0.9, 0.5)), (0.7, (1.0, 0.9, 0.2)), (1.0, (1.0, 0.25, 0.2))]
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            k = (t - a) / (b - a)
            return tuple(ca[i] + (cb[i] - ca[i]) * k for i in range(3))
    return stops[-1][1]


def path_diagram(shot, report: dict, out_png: Path, size: int = 900) -> Path:
    """Top-down diagram of one shot's camera path. Colours: blue = slow .. red = fast (scale in the corner)."""
    cam = shot.camera
    sc = bpy.context.scene
    # camera samples, every frame
    P, A, V = [], [], []
    prev = None
    for f in range(1, shot.frames + 1):
        core.at_frame(f)
        mw = cam.ob.matrix_world
        p = mw.translation.copy()
        P.append(p)
        A.append((mw.to_3x3() @ Vector((0, 0, -1))).normalized())
        V.append(0.0 if prev is None else (p - prev).length * shot.fps)
        prev = p
    cuts = {v["frame"] for v in cam._views if v.get("cut")}
    for f in cuts:
        if 1 < f <= len(V):
            V[f - 1] = 0.0
    core.at_frame(1)
    # the set: hulls of the meshes in the set (the ground and sky-size things are left out)
    shapes, marks, actors = [], [], []
    for ob in bpy.data.objects:
        if ob.hide_render or any(c.name in ("RIG", "FX") for c in ob.users_collection):
            continue
        if ob.type == "MESH":
            pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
            xs, ys = [q.x for q in pts], [q.y for q in pts]
            if max(max(xs) - min(xs), max(ys) - min(ys)) > 30 or max(q.z for q in pts) < 0.02:
                continue
            shapes.append(_hull([(round(q.x, 3), round(q.y, 3)) for q in pts]))
        elif ob.type == "EMPTY" and ob.name.lower().startswith("mark"):
            marks.append((ob.name, ob.matrix_world.translation.copy()))
    for name, a in shot.actors.items():
        actors.append((name, a.stage.matrix_world.translation.copy()))
    xs = [p.x for p in P] + [q[0] for s in shapes for q in s] + [m[1].x for m in marks] + [a[1].x for a in actors]
    ys = [p.y for p in P] + [q[1] for s in shapes for q in s] + [m[1].y for m in marks] + [a[1].y for a in actors]
    pad = 1.0
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    scale = (size - 20) / max(x1 - x0, y1 - y0, 1e-3)
    wpx, hpx = int((x1 - x0) * scale) + 20, int((y1 - y0) * scale) + 20

    def px(x, y):
        return (10 + (x - x0) * scale, hpx - 10 - (y - y0) * scale)

    cv = _Canvas(wpx, hpx)
    for yy in range(math.ceil(y0), math.floor(y1) + 1):            # 1 m grid
        cv.line(px(x0, yy), px(x1, yy), (0.12, 0.125, 0.15), 0.5)
    for xx in range(math.ceil(x0), math.floor(x1) + 1):
        cv.line(px(xx, y0), px(xx, y1), (0.12, 0.125, 0.15), 0.5)
    for poly in shapes:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            cv.line(px(*a), px(*b), (0.45, 0.47, 0.52), 1.0)
    labels = []
    for name, p in marks:
        cx, cy = px(p.x, p.y)
        cv.line((cx - 4, cy), (cx + 4, cy), (0.9, 0.7, 0.3), 1)
        cv.line((cx, cy - 4), (cx, cy + 4), (0.9, 0.7, 0.3), 1)
        labels.append((cx + 6, cy - 4, name, "orange", 0.8))
    for name, p in actors:
        cx, cy = px(p.x, p.y)
        cv.dot(cx, cy, 5, (0.95, 0.95, 0.95))
        labels.append((cx + 7, cy - 5, name, "white", 0.9))
    vs = sorted(v for v in V if v > 1e-6)
    vmax = max(vs[int(0.98 * (len(vs) - 1))] if vs else 1.0, 1.0)         # the scale ignores the odd whip: red = the fast end of this shot
    for i in range(len(P) - 1):                                      # the path, coloured by speed
        if (i + 2) in cuts:
            continue
        col = _ramp(V[i + 1] / vmax)
        cv.line(px(P[i].x, P[i].y), px(P[i + 1].x, P[i + 1].y), col, 2.0)
    for i in range(0, len(P), 6):                                    # where it looks
        a, d = px(P[i].x, P[i].y), A[i]
        b = px(P[i].x + d.x * 0.9, P[i].y + d.y * 0.9)
        cv.line(a, b, (0.3, 0.85, 0.95), 0.6)
    for m in report["moves"]:                                        # an arrow per move
        if m["type"] in ("drift", "rack_focus", "handheld"):
            continue
        fm = min(len(P) - 2, max(0, round(((m["t0"] + m["t1"]) / 2) * shot.fps)))
        d = (P[fm + 1].x - P[fm - 1].x, -(P[fm + 1].y - P[fm - 1].y)) if fm > 0 else (1, 0)
        c = px(P[fm].x, P[fm].y)
        if abs(d[0]) + abs(d[1]) < 1e-6:
            cv.dot(c[0], c[1], 3.5, (1, 1, 1))
        else:
            cv.tri(c, (d[0], d[1]), 7, (1, 1, 1))
        labels.append((c[0] + 8, c[1] + 4, m["type"], "white", 0.7))
    for vi, v in enumerate(cam._views):                              # view ids at their start
        p = P[min(len(P) - 1, v["frame"] - 1)]
        c = px(p.x, p.y)
        cv.dot(c[0], c[1], 4, (1.0, 0.35, 0.8))
        labels.append((c[0] - 4, c[1] - 16 - (vi % 3) * 11, f"{vi + 1}:{v['id']}", "#ff7ad0", 0.95))
    raw = out_png.with_name(out_png.stem + "_raw.png")
    review._save_pixels(cv.a, raw)
    fs = max(11, size // 60)
    chain = [f"drawtext=fontfile='{FONT.replace(':', chr(92) + ':')}':text='{_esc(t)}':x={x:.0f}:y={y:.0f}:fontsize={fs}:fontcolor={c}" for x, y, t, c, _a in labels]
    ff = f"fontfile='{FONT.replace(':', chr(92) + ':')}'"
    chain.append(f"drawtext={ff}:text='{_esc(shot.id)}  camera path, top-down':x=8:y=6:fontsize={fs}:fontcolor=white")
    chain.append(f"drawtext={ff}:text='{_esc(f'speed blue 0 to red {vmax:.1f} m/s   white arrow = move   pink dot = view start   cyan tick = where it looks')}':x=8:y={6 + fs + 4}:fontsize={max(9, fs - 3)}:fontcolor=gray")
    script = out_png.with_suffix(".ffscript")
    script.write_text(",".join(chain), encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-/vf", str(script), "-frames:v", "1", str(out_png)], capture_output=True, text=True)
    if r.returncode:
        print("[cam_preview] diagram labels failed:", r.stderr[-300:])
        raw.replace(out_png)
    else:
        raw.unlink()
    script.unlink()
    return out_png


# ----------------------------------------------------------------------------- one call
def preview(shot, out_dir: Path, width: int = 270, height: int = 480, engine: str = "draft", step: int = 1, video: bool = True) -> dict:
    """Measure the path, draw the diagram, render and encode. Returns what was written and the timing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cam = shot.camera
    cam.finish()
    t = time.perf_counter()
    rep = campath.analyse(shot)
    t_path = time.perf_counter() - t
    campath.write(rep, out_dir / "campath.json")
    t = time.perf_counter()
    path_diagram(shot, rep, out_dir / "path.png")
    t_diag = time.perf_counter() - t
    res = {"campath": str(out_dir / "campath.json"), "path_png": str(out_dir / "path.png"), "blocking": rep["blocking"], "warnings": rep["warnings"],
           "seconds_campath": round(t_path, 2), "seconds_diagram": round(t_diag, 2), "engine": engine, "size": [width, height]}
    if video:
        setup_render(bpy.context.scene, width, height, engine)
        fr = out_dir / "frames"
        tm = render_frames(shot, fr, step)
        t = time.perf_counter()
        encode(fr, shot, frame_labels(shot), out_dir / "preview.mp4", step, width)
        tm["seconds_encode"] = round(time.perf_counter() - t, 2)
        res.update({"mp4": str(out_dir / "preview.mp4"), **tm})
    (out_dir / "preview.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


# ----------------------------------------------------------------------------- loading a shot like run_shot.py
def load_shot(a):
    """Build the shot the way run_shot.py does and return it (shot functions come from run_shot: time base, words, plan)."""
    import run_shot
    if a.script:
        script = Path(a.script).resolve()
        seconds, shot_id, clip = float(a.seconds or 6.0), script.stem, None
    else:
        clip = Path(a.clip).resolve()
        shot_id = a.shot
        script = clip / "blender" / f"{shot_id}.py"
        seconds, _src = run_shot.shot_seconds(clip, shot_id, a.seconds)
    if not script.exists():
        raise SystemExit(f"missing shot script {script}")
    shot = stagekit.begin(shot_id, seconds, "draft")
    if clip:
        shot.clip_dir = clip
        shot.words = run_shot.shot_words(clip, shot_id, seconds)
        shot.plan = run_shot.plan_entry(clip, shot_id)
        whole = run_shot.plan_of(clip)
        shot.world = whole.get("world", {})
        shot.cast_plan = {c["id"]: c for c in whole.get("cast", [])}
    sys.path.insert(0, str(script.parent))
    spec = importlib.util.spec_from_file_location(f"shot_{shot_id}", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "build_shot"):
        raise SystemExit(f"{script.name} must define build_shot(shot)")
    mod.build_shot(shot)
    for _a in list(getattr(shot, "actors", {}).values()):
        if hasattr(_a, "_finalize"):
            _a._finalize()
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, shot.frames
    return shot, (clip / "review" / shot_id / "camera" if clip else None)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="cam_preview")
    ap.add_argument("--clip")
    ap.add_argument("--shot")
    ap.add_argument("--script", help="a stand-alone shot script with build_shot(shot) instead of --clip/--shot")
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--width", type=int, default=270)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--engine", choices=("draft", "workbench"), default="draft")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--no-video", action="store_true", help="only the measurements and the path diagram")
    a = ap.parse_args(argv)
    if not a.script and not (a.clip and a.shot):
        raise SystemExit("give --clip and --shot, or --script")
    try:
        shot, default_out = load_shot(a)
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("[cam_preview] BUILD FAILED")
        sys.exit(3)
    out = Path(a.out).resolve() if a.out else (default_out or Path.cwd() / "camera_preview")
    res = preview(shot, out, a.width, a.height, a.engine, a.step, not a.no_video)
    rep = json.loads((out / "campath.json").read_text(encoding="utf-8"))
    print(campath.summary(rep))
    print(f"[cam_preview] {json.dumps(res)}")
    if "s_per_frame" in res:
        print(f"[cam_preview] {res['frames']} frames at {a.width}x{a.height} ({a.engine}): {res['s_per_frame']} s/frame, {res['seconds']} s in total")
    sys.exit(0 if rep["blocking"] == 0 else 4)


if __name__ == "__main__":
    main()
