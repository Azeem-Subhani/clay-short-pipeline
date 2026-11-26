"""Headless test of the camera move library.

    blender -b --factory-startup --python tools/tests/camera/test_moves.py -- [--only dolly,orbit] [--no-video] [--engine draft|workbench] [--list]

For every move and framing helper it builds the small test set (world.py), runs the move, measures the camera path with
stagekit.campath, renders a 5-frame strip (start, 25%, 50%, 75%, end of the move) to output/_staging/camera/<name>.png and writes
report.json with the measured speeds. It then builds a 12 s sequence that chains establish -> crane down -> push-in -> whip ->
over-the-shoulder -> orbit -> through the doorway -> track with the walker -> rack focus -> hold with drift, and renders it as
output/_staging/camera/sequence/preview.mp4 with the path diagram. Last come deliberately bad moves, which campath must block.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402

import cam_preview  # noqa: E402
import stagekit  # noqa: E402
import world  # noqa: E402
from stagekit import camera, campath, core, review  # noqa: E402

OUT = ROOT / "output" / "_staging" / "camera"
W_PX, H_PX = 270, 480


def new_shot(name: str, seconds: float, engine: str):
    shot = stagekit.begin(name, seconds, "draft")
    cam_preview.setup_render(bpy.context.scene, W_PX, H_PX, engine)
    wd = world.build_world(shot)
    return shot, wd


# ----------------------------------------------------------------------------- the cases: each returns the (t0, t1) window to show
def a_view(cam, wd, **kw):
    cam.view("a", 0.0, on=[wd["A"]], size="medium", side=kw.get("side", 10))


def c_dolly(cam, shot, wd):
    a_view(cam, wd)
    cam.dolly(0.5, 2.5, 0.2)
    return 0.5, 2.5, 3.0


def c_push(cam, shot, wd):
    a_view(cam, wd)
    cam.push(0.5, 2.5, 0.2)
    return 0.5, 2.5, 3.0


def c_truck(cam, shot, wd):
    a_view(cam, wd)
    cam.truck(0.5, 2.5, right=0.6)
    return 0.5, 2.5, 3.0


def c_pan(cam, shot, wd):
    cam.view("w", 0.0, pos=(0, -7, 1.6), aim=(-2.5, 4, 1.4), lens=30, size="wide")
    cam.pan(0.5, 2.5, 28)
    return 0.5, 2.5, 3.0


def c_tilt(cam, shot, wd):
    cam.view("t", 0.0, pos=(-1.2, -1.5, 1.2), aim=(-1.2, 2.0, 0.3), lens=34, size="manual")
    cam.tilt(0.5, 2.5, 38)
    return 0.5, 2.5, 3.0


def c_orbit(cam, shot, wd):
    cam.view("b", 0.0, on=[wd["B"]], size="medium", side=0)
    cam.orbit(0.5, 3.5, wd["B"].stage, deg=30)
    return 0.5, 3.5, 4.0


def c_orbit_rise(cam, shot, wd):
    cam.view("b", 0.0, on=[wd["B"]], size="medium", side=0)
    cam.orbit(0.5, 3.5, wd["B"].stage, deg=-40, rise=1.0, to_distance=4.5)
    return 0.5, 3.5, 4.0


def c_crane(cam, shot, wd):
    cam.view("c", 0.0, pos=(0, -10, 8.0), aim=(0, 3, 1.0), lens=26, size="wide")
    cam.crane(0.5, 3.0, rise=-6.2)
    return 0.5, 3.0, 3.5


def c_crane_tilt(cam, shot, wd):
    cam.view("c", 0.0, pos=(0, -6, 1.6), aim=(0, 2.5, 1.4), lens=28, size="wide")
    cam.crane(0.5, 3.0, rise=4.5, back=2.0, tilt_to=-35)
    return 0.5, 3.0, 3.5


def c_follow(cam, shot, wd):
    wd["W"].walk(0.0, 3.5, (3.5, 0.4))
    cam.view("w", 0.0, on=[wd["W"]], size="full", side=-20)
    cam.follow(wd["W"], 0.0, 3.0, smooth=0.15, lead=0.2)
    return 0.0, 3.0, 3.5


def c_track_with(cam, shot, wd):
    wd["W"].walk(0.0, 4.0, (4.0, 0.4))
    cam.view("w", 0.0, pos=(-4.0, -2.2, 1.5), aim=(-3.5, 0.4, 1.3), lens=36, size="manual")
    cam.track_with(wd["W"], 0.4, 3.0, side="right", distance=2.8)
    return 0.4, 3.6, 4.0


def c_whip(cam, shot, wd):
    cam.view("a", 0.0, on=[wd["A"]], size="medium", side=10)
    cam.whip(1.0, cam.frame(wd["B"], "medium", side=-10), dur=0.35, vid="b")
    return 1.0, 1.35, 2.3


def c_through(cam, shot, wd):
    cam.view("door", 0.0, pos=(0, 0.4, 1.5), aim=(0, 5, 1.4), lens=32, size="manual")
    cam.through(0.6, 2.8, wd["door"], cam.frame(wd["beyond"], "full", side=0, high=8), axis=(0, 1, 0), vid="beyond")
    return 0.6, 2.8, 3.6


def c_rack_focus(cam, shot, wd):
    cam.view("ab", 0.0, framing=cam.two_shot(wd["A"], wd["B"], size="medium"))
    cam.dolly(0.0, 2.2, 0.05)                                    # a rack focus is nearly always laid over a slow push
    cam.rack_focus(0.5, 1.5, wd["B"].head, fstop=1.6)
    return 0.5, 1.5, 2.2


def c_dolly_zoom(cam, shot, wd):
    a_view(cam, wd)
    cam.dolly_zoom(0.5, 2.5, 0.3)
    return 0.5, 2.5, 3.0


def c_handheld(cam, shot, wd):
    a_view(cam, wd)
    cam.handheld(0.3, 2.7, amount=0.03)
    return 0.3, 2.7, 3.0


def c_reveal(cam, shot, wd):
    end = cam.frame(wd["A"], "medium", side=15)
    fwd = (end[1] - end[0]).normalized()
    r = fwd.cross(Vector((0, 0, 1))).normalized()
    p = end[0] + Vector((fwd.x, fwd.y, 0)).normalized() * 1.0 + r * 0.9
    ob = wd["pillar"]
    ob.location = (p.x, p.y, 0.0)
    cam.reveal(0.0, 2.0, ob, end, vid="rev")
    return 0.0, 2.0, 2.4


def c_drift(cam, shot, wd):
    cam.view("a", 0.0, on=[wd["A"]], size="medium", side=10)
    cam.view("b", 2.0, on=[wd["B"]], size="medium", side=-10, still=True)
    cam.view("w", 4.0, pos=(0, -9, 2.2), aim=(0, 3, 1.0), lens=28, size="wide")
    return 0.0, 6.0, 6.0


def c_blend(cam, shot, wd):
    a_view(cam, wd)
    cam.dolly(0.3, 1.3, 0.2, ease="linear")
    cam.truck(1.3, 2.5, right=0.5, ease="linear", blend=0.35)
    return 0.3, 2.5, 3.0


def c_ots(cam, shot, wd):
    cam.line(wd["A"], wd["B"])
    cam.view("ots", 0.0, framing=cam.ots(wd["A"], wd["B"]))
    return 0.0, 2.5, 2.5


def c_reverse(cam, shot, wd):
    cam.view("ots_ab", 0.0, framing=cam.ots(wd["A"], wd["B"]))
    cam.view("ots_ba", 1.5, framing=cam.reverse("ots_ab"))
    return 0.0, 3.0, 3.0


def c_two_shot(cam, shot, wd):
    cam.view("two", 0.0, framing=cam.two_shot(wd["A"], wd["B"], size="medium"))
    return 0.0, 2.5, 2.5


def c_low_hero(cam, shot, wd):
    cam.view("hero", 0.0, framing=cam.low_hero(wd["A"]))
    return 0.0, 2.5, 2.5


def c_top_down(cam, shot, wd):
    cam.view("map", 0.0, framing=cam.top_down([wd["A"], wd["B"], wd["W"]], height=None))
    return 0.0, 2.5, 2.5


def c_establish(cam, shot, wd):
    cam.view("est", 0.0, framing=cam.establish(wd["marks"]))
    return 0.0, 2.5, 2.5


def c_insert(cam, shot, wd):
    cam.view("ins", 0.0, framing=cam.insert(wd["beyond"]))
    return 0.0, 2.5, 2.5


def c_profile(cam, shot, wd):
    cam.view("prof", 0.0, framing=cam.profile(wd["A"], size="medium"))
    return 0.0, 2.5, 2.5


def c_line(cam, shot, wd):
    """The line of action holds: a helper asked for the far side lands on the near side; cross_line=True crosses."""
    cam.line(wd["A"], wd["B"])
    f1 = cam.two_shot(wd["A"], wd["B"], size="medium")
    f2 = cam.two_shot(wd["A"], wd["B"], size="medium", side="far")                 # asks for the other side: mirrored back
    f3 = cam.two_shot(wd["A"], wd["B"], size="medium", side="far", cross_line=True)
    s1, s2, s3 = (cam._side_of(f[0]) for f in (f1, f2, f3))
    shot.notes.append(f"line sides: default {s1}, far {s2}, far+cross_line {s3}")
    assert s1 == s2 and s3 != s1, (s1, s2, s3)
    cam.view("v1", 0.0, framing=f1)
    cam.view("v2", 1.5, framing=f2)
    cam.view("v3", 3.0, framing=f3)
    return 0.0, 4.5, 4.5


CASES = {
    "dolly": c_dolly, "push": c_push, "truck": c_truck, "pan": c_pan, "tilt": c_tilt, "orbit": c_orbit, "orbit_rise": c_orbit_rise, "crane": c_crane,
    "crane_tilt_to": c_crane_tilt, "follow": c_follow, "track_with": c_track_with, "whip": c_whip, "through": c_through, "rack_focus": c_rack_focus,
    "dolly_zoom": c_dolly_zoom, "handheld": c_handheld, "reveal": c_reveal, "drift": c_drift, "blend": c_blend, "ots": c_ots, "reverse": c_reverse,
    "two_shot": c_two_shot, "low_hero": c_low_hero, "top_down": c_top_down, "establish": c_establish, "insert": c_insert, "profile": c_profile,
    "line_of_action": c_line,
}


# ----------------------------------------------------------------------------- the deliberately bad moves
def b_wall(cam, shot, wd):
    cam.view("w", 0.0, pos=(2.4, 2.5, 1.5), aim=(2.4, 5.5, 1.5), lens=30, size="manual")
    cam.dolly(0.5, 2.5, 1.5)                                     # pushed straight through the wall at y=5
    return "camera_through_geometry"


def b_out_of_frame(cam, shot, wd):
    wd["W"].walk(0.5, 3.0, (9.0, 0.4))
    cam.view("w", 0.0, on=[wd["W"]], size="medium")              # a static frame on a man who then walks out of it
    cam.hold(3.0)
    return "subject_out_of_frame"


def b_jump(cam, shot, wd):
    cam.view("a", 0.0, on=[wd["A"]], size="medium")
    cam.move(1.0, 2.0, pos=(0, -80.0, 1.6), aim=wd["A"].head.point(), lens=38)        # 80 m in one second
    return "speed_over_limit"


def b_hidden(cam, shot, wd):
    ob = wd["pillar"]
    ob.location = (-2.6, -0.6, 0.0)                              # a pillar between the lens and her face
    cam.view("a", 0.0, on=[wd["A"]], size="medium", side=0)
    cam.hold(2.5)
    return "face_hidden"


def b_floor(cam, shot, wd):
    cam.view("a", 0.0, on=[wd["A"]], size="medium")
    cam.crane(0.5, 2.0, rise=-2.5)                               # the boom goes below the ground
    return "camera_under_floor"


BAD = {"bad_through_wall": (b_wall, 3.0), "bad_out_of_frame": (b_out_of_frame, 3.5), "bad_80ms_jump": (b_jump, 3.0), "bad_face_hidden": (b_hidden, 3.0), "bad_under_floor": (b_floor, 3.0)}


# ----------------------------------------------------------------------------- strips
def render_still(path: Path, frame: int):
    sc = bpy.context.scene
    sc.frame_set(frame)
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def strip(shot, name: str, t0: float, t1: float, out: Path):
    frames = [shot.f(t0 + (t1 - t0) * k / 4) for k in range(5)]
    tiles = []
    tmp = OUT / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames):
        p = tmp / f"{name}_{i}.png"
        render_still(p, f)
        tiles.append(review._load_pixels(p))
        p.unlink()
    h, w, _ = tiles[0].shape
    sheet = np.full((h, 5 * w + 4 * 4, 3), 0.02, dtype=np.float32)
    for i, a in enumerate(tiles):
        sheet[:, i * (w + 4):i * (w + 4) + w] = a
    review._save_pixels(sheet, out)
    return frames


def peaks(rep, types=None):
    ms = [m for m in rep["moves"] if (types is None or m["type"] in types)]
    return ms


def run_case(name: str, fn, seconds: float, engine: str, strips: bool = True) -> dict:
    shot, wd = new_shot(name, seconds, engine)
    cam = camera.Camera()
    t0, t1, _ = fn(cam, shot, wd)
    cam.finish()
    rep = campath.analyse(shot)
    res = {"case": name, "window": [t0, t1], "blocking": rep["blocking"], "warnings": rep["warnings"], "static_share": rep["static_share"],
           "moves": [{k: m[k] for k in ("type", "t0", "t1", "peak_speed_m_s", "peak_ang_speed_deg_s", "peak_accel_m_s2", "pass", "issues")} for m in rep["moves"]],
           "issues": [f"[{i['level']}] {i['code']} {i['view']}@{i['frame']}: {i['detail']}" for i in rep["issues"]]}
    if strips:
        OUT.mkdir(parents=True, exist_ok=True)
        res["strip_frames"] = strip(shot, name, t0, t1, OUT / f"{name}.png")
    return res


def run_bad(name: str, fn, seconds: float, engine: str) -> dict:
    shot, wd = new_shot(name, seconds, engine)
    cam = camera.Camera()
    expect = fn(cam, shot, wd)
    cam.finish()
    rep = campath.analyse(shot)
    blocks = [i for i in rep["issues"] if i["level"] == "block"]
    return {"case": name, "expected": expect, "caught": any(i["code"] == expect for i in blocks), "blocking_codes": sorted({i["code"] for i in blocks}),
            "first": [f"{i['code']}@{i['frame']}: {i['detail']}" for i in blocks[:3]]}


# ----------------------------------------------------------------------------- the 12 s sequence
def sequence(engine: str, video: bool) -> dict:
    shot, wd = new_shot("sequence", 12.0, engine)
    A, B, W = wd["A"], wd["B"], wd["W"]
    W.stage.location = (-3.2, 10.0, 0.0)
    W.stage.rotation_euler.z = math.radians(90)
    W.walk(6.5, 11.5, (3.4, 10.0))
    cam = camera.Camera()
    cam.line(A, B)
    cam.view("establish", 0.0, framing=cam.establish({"A": A, "B": B, "door": wd["door"], "L": (-5, 0, 0), "R": (5, 0, 0)}, high=34), still=True)
    cam.crane(0.6, 2.0, rise=-4.5)                                                  # boom down into the yard
    cam.view("a_medium", 2.1, on=[A], size="medium", side=12, why="her face")
    cam.dolly(2.1, 3.1, 0.2)                                                        # push in on her
    cam.whip(3.1, cam.frame(B, "medium", side=-12), dur=0.35, vid="b_medium", why="his answer")
    cam.view("ots_a_b", 4.2, framing=cam.ots(A, B), why="her point of view of him")            # held 1.4 s: it drifts
    cam.view("orbit_b", 5.6, on=[B], size="medium", side=-5)
    cam.orbit(5.6, 6.6, B.stage, deg=20)
    cam.through(6.6, 9.1, wd["door"], {"on": W, "size": "medium", "side": -10, "high": 4}, axis=(0, 1, 0), vid="walker", why="out through the door to the man beyond")
    cam.track_with(W, 9.1, 10.2, side="right", distance=2.3)
    cam.rack_focus(9.6, 10.3, wd["beyond"], fstop=2.0)
    cam.view("end_two", 10.4, framing=cam.two_shot(A, B, size="medium"), why="a held two-shot that drifts")
    cam.finish()
    out = OUT / "sequence"
    res = cam_preview.preview(shot, out, W_PX, H_PX, engine, 1, video)
    rep = json.loads((out / "campath.json").read_text(encoding="utf-8"))
    res["views"] = [(v["id"], v["t0"], v["t1"], v["moves"]) for v in rep["views"]]
    res["moves"] = [(m["type"], m["t0"], m["t1"], m["peak_speed_m_s"], m["peak_ang_speed_deg_s"], m["pass"]) for m in rep["moves"]]
    res["issues"] = [f"[{i['level']}] {i['code']} {i['view']}@{i['frame']}: {i['detail']}" for i in rep["issues"]]
    return res


# ----------------------------------------------------------------------------- backwards compatibility with the old API
def old_api(engine: str) -> dict:
    """The old calls give the same cut frames and framings as the old code: checked against the numbers the old code produced by hand."""
    shot, wd = new_shot("oldapi", 6.0, engine)
    A, B = wd["A"], wd["B"]
    cam = camera.Camera()
    cam.view("v1", 0.0, on=[A], size="medium", side=12, high=2, place=0.4)
    cam.push(0.0, 1.5, 0.07)
    cam.view("v2", 1.5, pos=(0.9, -1.5, 2.15), aim=(-0.85, 5.6, 0.95), lens=35, size="full")
    cam.push(2.0, 3.0, 0.08)
    cam.view("v3", 3.0, on=[B], size="close", travel=0.35)
    cam.move(3.5, 4.4, on=[B], size="medium", fill=0.5, side=10, high=-5)
    cam.shake(4.6, 0.04)
    cam.hold(5.0)
    cam.view("v4", 5.0, pos=(0, -9, 2.2), aim=(0, 3, 1.0), lens=28, size="wide", drift=False)
    cam.hold(6.0)
    views = cam.views
    cuts = [(v["id"], v["frame"], v["cut"]) for v in views]
    sc = bpy.context.scene
    fr = {}
    for f in (1, 12, 36, 37, 72, 73, 100, 120, 121):
        core.at_frame(f)
        fr[f] = {"pos": [round(c, 3) for c in cam.ob.matrix_world.translation], "lens": round(cam.data.lens, 2), "view": (cam.view_at(f) or {}).get("id")}
    px = {}
    for f, who in ((1, A), (37, "pos"), (73, B)):
        core.at_frame(f)
        p = who.head.point() if hasattr(who, "head") else Vector((0, 2, 1))
        px[f] = [round(v, 3) for v in cam.project(p, f)]
    # the pose at the first frame of every view must be exactly the requested framing
    first = {v["id"]: [round(c, 3) for c in cam._samples[v["frame"]].pos] for v in views}
    return {"cuts": cuts, "frames": fr, "projection": px, "first_pose_per_view": first, "keys": len(cam.keys), "moves": [(m["type"], m["t0"], m["t1"]) for m in cam.moves],
            "has_attrs": [hasattr(cam, a) for a in ("view", "move", "push", "hold", "follow", "shake", "project", "view_at", "views", "keys")]}


def chain_continuity(engine: str) -> dict:
    """Two chained moves: with blend there is no velocity jump at the join; without it there is a stop."""
    out = {}
    for label, blend in (("blend_0", 0.0), ("blend_0.35", 0.35)):
        shot, wd = new_shot(label, 3.0, engine)
        cam = camera.Camera()
        a_view(cam, wd)
        cam.dolly(0.3, 1.3, 0.2, ease="linear")
        cam.truck(1.3, 2.5, right=0.5, ease="linear", blend=blend)
        cam.finish()
        pts = []
        for f in range(1, shot.frames + 1):
            core.at_frame(f)
            pts.append(cam.ob.matrix_world.translation.copy())
        v = [(pts[i + 1] - pts[i]) * shot.fps for i in range(len(pts) - 1)]
        dv = [(v[i + 1] - v[i]).length * shot.fps for i in range(len(v) - 1)]
        j = shot.f(1.3)
        out[label] = {"max_speed": round(max(x.length for x in v), 3), "velocity_at_join": [round(c, 3) for c in v[j - 1]],
                      "max_accel_within_0.5s_of_join_m_s2": round(max(dv[j - 12:j + 8]), 2)}
    return out


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--no-strips", action="store_true")
    ap.add_argument("--engine", default="draft")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--skip-bad", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        print(", ".join([*CASES, *BAD, "sequence", "old_api", "chain"]))
        return
    only = set(a.only.split(",")) if a.only else None
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"cases": [], "bad": []}
    t_all = time.perf_counter()
    for name, fn in CASES.items():
        if only and name not in only:
            continue
        t = time.perf_counter()
        try:
            r = run_case(name, fn, 4.6 if name == "line_of_action" else 3.0 if name not in ("drift", "crane", "orbit", "track_with", "crane_tilt_to", "through", "follow") else 6.0 if name == "drift" else 4.0, a.engine, not a.no_strips)
        except Exception:
            traceback.print_exc()
            r = {"case": name, "error": traceback.format_exc()[-400:]}
        r["seconds"] = round(time.perf_counter() - t, 1)
        report["cases"].append(r)
        for line in r.get("issues", []):
            print("      ", line)
        print(f"[test] {name}: " + ("ERROR" if "error" in r else f"blocking={r['blocking']} warn={r['warnings']} " + "; ".join(f"{m['type']} v={m['peak_speed_m_s']} w={m['peak_ang_speed_deg_s']} {'ok' if m['pass'] else 'BLOCK'}" for m in r["moves"] if m["type"] != "drift")) + f"  ({r['seconds']}s)", flush=True)
    if not a.skip_bad and (not only or only & set(BAD)):
        for name, (fn, secs) in BAD.items():
            if only and name not in only:
                continue
            r = run_bad(name, fn, secs, a.engine)
            report["bad"].append(r)
            print(f"[test] {name}: expected {r['expected']} -> {'CAUGHT' if r['caught'] else 'MISSED'}  blocking={r['blocking_codes']}", flush=True)
    if not only or "old_api" in only:
        report["old_api"] = old_api(a.engine)
        print("[test] old_api:", json.dumps(report["old_api"]), flush=True)
    if not only or "chain" in only:
        report["chain"] = chain_continuity(a.engine)
        print("[test] chain:", json.dumps(report["chain"]), flush=True)
    if not only or "sequence" in only:
        report["sequence"] = sequence(a.engine, not a.no_video)
        s = report["sequence"]
        print("[test] sequence:", json.dumps({k: s[k] for k in s if k not in ("moves", "views", "issues")}), flush=True)
        for m in s["moves"]:
            print("   move", m)
        for i in s["issues"]:
            print("   ", i)
    report["seconds"] = round(time.perf_counter() - t_all, 1)
    (OUT / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(f"[test] done in {report['seconds']} s -> {OUT / 'report.json'}")


if __name__ == "__main__":
    main()
