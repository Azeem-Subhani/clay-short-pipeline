"""stagekit.campath - measure the camera's whole path after a shot is built (pure measurement, nothing is changed).

review.py looks at a few stills. This walks the evaluated camera through the entire shot, every second frame, and reports
per view and per move what could go wrong between the stills:

    rep = campath.analyse(shot)         # {"moves": [...], "views": [...], "issues": [{"level", "code", "view", "frame", "detail"}], ...}
    campath.write(rep, path)            # campath.json
    campath.blocking(rep)               # the issues that must be fixed before the shot is rendered

Checks: declared subjects in frame and inside the safe area; a face (or any subject) hidden by set geometry or another
object (rays from the camera to five points of the head); the camera inside geometry, passing through it between two
samples, under the floor, or nearer than 0.3 m to anything; linear speed, acceleration, angular speed and angular
acceleration against style.json > camera (a whip is exempt for its declared time); jerk spikes (a sudden change of
direction); a face crossing the caption band; the share of the shot in which the camera does not move at all; views that
are too short; a cut that crosses the declared line of action. Limits warn; going past them by block_factor blocks.
Works with 3D actors (anything with .head.point(), .head_r, .scale, .stage) and with plain objects and points.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from . import core

DEFAULTS = {
    "max_speed_m_s": 6.0, "max_accel_m_s2": 15.0, "max_ang_speed_deg_s": 80.0, "max_ang_accel_deg_s2": 300.0, "whip_dur_s": [0.25, 0.5],
    "min_view_s": 0.7, "max_static_share": 0.4, "min_clearance_m": 0.3, "block_clearance_m": 0.1, "block_factor": 2.0, "subject_out_s": 0.5,
    "face_hidden_s": 0.4, "jerk_angle_deg": [70, 120],
}
SPHERE = [Vector(v).normalized() for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0),
                                           (1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1))]     # no downward rays except the floor test: the floor is not an obstacle
INSIDE = [Vector(v) for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]


# ----------------------------------------------------------------------------- helpers
def _sid(s) -> str:
    return str(getattr(s, "id", None) or getattr(s, "name", None) or (tuple(round(v, 2) for v in s) if hasattr(s, "__len__") else s))


def _is_actor(s) -> bool:
    return hasattr(s, "head") and hasattr(s, "stage")


def _own_names(s) -> set:
    names = set()
    coll = getattr(s, "coll", None)
    if coll is not None:
        try:
            names |= {o.name for o in coll.all_objects}
        except AttributeError:
            pass
    if hasattr(s, "name") and hasattr(s, "children_recursive"):
        names |= {s.name} | {c.name for c in s.children_recursive}
    return names


def _subject_point(s) -> Vector:
    """The point to keep in frame: an actor's head, an object's middle, or the point itself."""
    if _is_actor(s):
        return Vector(s.head.point())
    return core.point_of(s)


def _head_dims(s) -> float:
    return s.head_r * getattr(s, "scale", 1.0) if _is_actor(s) else 0.12


def _first_blocker(sc, dg, origin: Vector, target: Vector, skip: set):
    """The name of the first thing in the way between two points (ignoring `skip` and the FX collection), or None."""
    d = target - origin
    dist = d.length
    if dist < 1e-4:
        return None
    dn = d / dist
    start = origin.copy()
    for _ in range(8):
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, start, dn, distance=max(0.0, dist - 0.03 - (start - origin).length))
        if not hit or ob is None:
            return None
        if ob.name in skip or any(c.name == "FX" for c in ob.users_collection) or ob.display_type in ("WIRE", "BOUNDS"):
            start = loc + dn * 0.01
            continue
        return ob.name
    return None


def _runs(flags: list[bool], frames: list[int]):
    """Consecutive True runs as (first_frame, last_frame) (the run ends when the flag is False or the samples are not neighbours)."""
    out, cur = [], None
    for i, (fl, f) in enumerate(zip(flags, frames)):
        if fl:
            if cur is None:
                cur = [f, f]
            else:
                cur[1] = f
        elif cur is not None:
            out.append(tuple(cur))
            cur = None
    if cur is not None:
        out.append(tuple(cur))
    return out


# ----------------------------------------------------------------------------- the analysis
def analyse(shot=None, step: int = 2) -> dict:
    """Walk the whole shot and measure it. Returns the report (a plain dict, ready for json)."""
    shot = shot or core.current()
    cam = getattr(shot, "camera", None)
    if cam is None:
        return {"moves": [], "views": [], "issues": [{"level": "block", "code": "no_camera", "view": None, "frame": 1, "detail": "the shot has no camera"}]}
    cam.finish()
    cfg = {**DEFAULTS, **core.STYLE.get("camera", {})}
    fps = shot.fps
    sc = bpy.context.scene
    views = cam._views
    sa = core.STYLE["safe_area"]
    cap = core.STYLE["captions"]
    cap_half = cap["font_size_px"] * 0.75 / core.STYLE["video"]["height"]
    cap_top, cap_bot = cap["center_y_fraction"] - cap_half, cap["center_y_fraction"] + cap_half
    cuts = sorted({v["frame"] for v in views[1:] if v.get("cut")})
    frames = sorted({*range(1, shot.frames + 1, step), shot.frames, *cuts, *[c - 1 for c in cuts if c > 1]})
    issues: list[dict] = []

    def issue(level, code, view, frame, detail):
        issues.append({"level": level, "code": code, "view": view, "frame": int(frame), "detail": detail})

    whips = [(m["t0"], m["t1"]) for m in cam.moves if m["type"] == "whip"]

    def in_whip(f):
        t = (f - 1) / fps
        return any(a - 0.05 <= t <= b + 0.05 for a, b in whips)

    reveals = [(m["t0"], m["t1"], m.get("occluder")) for m in cam.moves if m["type"] == "reveal"]
    transit = [(m["t0"], m["t1"]) for m in cam.moves if m["type"] in ("whip", "through")]     # the subject of the old view may leave while the camera is on its way

    def in_transit(f):
        t = (f - 1) / fps
        return any(a - 0.02 <= t <= b + 0.02 for a, b in transit)

    # ---- sample the camera
    S = []                                                     # per sample: dict
    for f in frames:
        dg = core.at_frame(f)
        mw = cam.ob.matrix_world.copy()
        pos = mw.translation.copy()
        fwd = (mw.to_3x3() @ Vector((0, 0, -1))).normalized()
        v = cam.view_at(f)
        S.append({"f": f, "pos": pos, "fwd": fwd, "rot": mw.to_quaternion(), "lens": cam.data.lens, "view": v["id"] if v else None, "dg": dg})
        s = S[-1]
        # camera vs the world
        under_up, under_down = None, None
        hit_dn, *_r = sc.ray_cast(dg, pos, Vector((0, 0, -1)), distance=400.0)
        if not hit_dn:
            hit_up, *_r2 = sc.ray_cast(dg, pos, Vector((0, 0, 1)), distance=400.0)
            if hit_up:
                s["under_floor"] = True
        back = 0
        for d in INSIDE:
            h, loc, nrm, _i, ob, _m = sc.ray_cast(dg, pos, d, distance=60.0)
            if h and nrm.dot(d) > 0.0:
                back += 1
        s["inside"] = back >= 4
        near, near_ob = 9e9, None
        for d in SPHERE:
            h, loc, nrm, _i, ob, _m = sc.ray_cast(dg, pos, d, distance=cfg["min_clearance_m"])
            if h:
                dist = (loc - pos).length
                if dist < near:
                    near, near_ob = dist, ob.name
        s["near"], s["near_ob"] = near, near_ob

    # ---- kinematics between samples (a pair that straddles a cut is skipped)
    def straddles(fa, fb):
        return any(fa < c <= fb for c in cuts)

    kin = []                                                   # per pair: speed, ang speed, ...
    for a, b in zip(S, S[1:]):
        dt = (b["f"] - a["f"]) / fps
        if dt <= 0 or straddles(a["f"], b["f"]):
            kin.append(None)
            continue
        dv = b["pos"] - a["pos"]
        ang = math.degrees(a["fwd"].angle(b["fwd"], 0.0))
        q = a["rot"].rotation_difference(b["rot"])
        omega = q.axis * (q.angle if q.angle <= math.pi else 2 * math.pi - q.angle) / dt
        kin.append({"f0": a["f"], "f1": b["f"], "dt": dt, "vel": dv / dt, "speed": dv.length / dt, "ang": ang / dt, "omega": omega, "move": dv.length < 1e-4 and ang < 0.005})
    k_ok = [k for k in kin if k]
    for i, k in enumerate(kin):
        if not k:
            continue
        prev = kin[i - 1] if i > 0 else None
        if prev:
            k["acc"] = (k["vel"] - prev["vel"]).length / ((k["dt"] + prev["dt"]) / 2)
            k["ang_acc"] = math.degrees((k["omega"] - prev["omega"]).length) / ((k["dt"] + prev["dt"]) / 2)
            k["turn"] = math.degrees(k["vel"].angle(prev["vel"], 0.0)) if k["speed"] > 0.6 and prev["speed"] > 0.6 else 0.0
        else:
            k["acc"] = k["ang_acc"] = k["turn"] = 0.0

    def view_of(f):
        v = cam.view_at(f)
        return v["id"] if v else None

    bf = cfg["block_factor"]
    # ---- limits
    for k in k_ok:
        f = k["f1"]
        if in_whip(f) or in_whip(k["f0"]):
            continue
        vid = view_of(f)
        for key, lim, code, unit, what in (("speed", cfg["max_speed_m_s"], "speed", "m/s", "linear speed"), ("acc", cfg["max_accel_m_s2"], "accel", "m/s2", "acceleration"),
                                           ("ang", cfg["max_ang_speed_deg_s"], "ang_speed", "deg/s", "turning speed"), ("ang_acc", cfg["max_ang_accel_deg_s2"], "ang_accel", "deg/s2", "turning acceleration")):
            if k[key] > lim * bf:
                issue("block", f"{code}_over_limit", vid, f, f"{what} {k[key]:.1f} {unit} between frames {k['f0']} and {k['f1']} (limit {lim}; blocks above {lim * bf:g})")
            elif k[key] > lim:
                issue("warn", f"{code}_over_limit", vid, f, f"{what} {k[key]:.1f} {unit} between frames {k['f0']} and {k['f1']} (limit {lim})")
        w_lo, w_hi = cfg["jerk_angle_deg"]
        if k["turn"] > w_hi:
            issue("block", "jerk_spike", vid, f, f"the camera reverses direction by {k['turn']:.0f} degrees within {k['dt'] * 2:.2f} s (frames {k['f0']}-{k['f1']})")
        elif k["turn"] > w_lo:
            issue("warn", "jerk_spike", vid, f, f"the camera changes direction by {k['turn']:.0f} degrees within {k['dt'] * 2:.2f} s (frames {k['f0']}-{k['f1']})")

    # ---- the camera's step from each sample to the next, against the geometry AS IT STANDS at those frames (a door leaf that swings across
    # the path later in the shot must not block the camera's earlier move). One evaluation per frame: at frame f the step arriving at f
    # and the step leaving f are both cast; a step is blocked when it is blocked at both of its frames (something that stands in the way
    # for the whole step, not a door that is only there before or after it).
    seg = {}                                                   # pair index (the step S[i-1] -> S[i]) -> {"a": hit at frame i-1, "b": hit at frame i}

    def cast_step(dg, i):
        a, b = S[i - 1], S[i]
        d = b["pos"] - a["pos"]
        if d.length <= 1e-4 or straddles(a["f"], b["f"]):
            return None
        hit, loc, _nrm, _i, ob, _m = sc.ray_cast(dg, a["pos"], d.normalized(), distance=d.length)
        return (ob.name, loc.copy()) if hit and ob is not None else False

    for j, s in enumerate(S):
        dg = core.at_frame(s["f"])
        if j > 0:
            seg.setdefault(j, {})["b"] = cast_step(dg, j)
        if j + 1 < len(S):
            seg.setdefault(j + 1, {})["a"] = cast_step(dg, j + 1)
    through = {i: r["b"] for i, r in seg.items() if r.get("a") and r.get("b")}

    # ---- the camera against the world
    for i, s in enumerate(S):
        vid = s["view"]
        if s.get("under_floor"):
            issue("block", "camera_under_floor", vid, s["f"], "the camera is below the ground: there is nothing under it and the floor is above it")
        if s["inside"]:
            issue("block", "camera_inside_geometry", vid, s["f"], "the camera is inside a solid object (most rays leave through a back face)")
        elif s["near"] < cfg["block_clearance_m"]:
            issue("block", "camera_too_close", vid, s["f"], f"the camera is {s['near'] * 100:.0f} cm from {s['near_ob']}")
        elif s["near"] < cfg["min_clearance_m"]:
            issue("warn", "camera_close", vid, s["f"], f"the camera is {s['near'] * 100:.0f} cm from {s['near_ob']} (keep {cfg['min_clearance_m']} m)")
        th = through.get(i)
        if th is not None:
            a = S[i - 1]
            ob, loc = th
            issue("block", "camera_through_geometry", vid, s["f"], f"between frames {a['f']} and {s['f']} the camera passes through {ob} at ({loc.x:.2f}, {loc.y:.2f}, {loc.z:.2f})")

    # ---- subjects per view
    view_reports = []
    for vi, v in enumerate(views):
        f_end = (views[vi + 1]["frame"] - 1) if vi + 1 < len(views) else shot.frames
        subs = cam._view_on[vi] if vi < len(cam._view_on) else []
        vs = [s for s in S if v["frame"] <= s["f"] <= f_end]
        rep = {"id": v["id"], "t0": round((v["frame"] - 1) / fps, 3), "t1": round(f_end / fps, 3), "seconds": round((f_end - v["frame"] + 1) / fps, 3), "kind": v.get("kind", "cut"),
               "size": v.get("size"), "subjects": {}, "moves": sorted({m["type"] for m in cam.moves if m["view"] == v["id"]})}
        if rep["seconds"] < cfg["min_view_s"] and v.get("size") != "insert":
            issue("warn", "view_too_short", v["id"], v["frame"], f"the view lasts {rep['seconds']} s (under {cfg['min_view_s']} s nothing can be read)")
        for s_obj in subs:
            name = _sid(s_obj)
            actor = _is_actor(s_obj)
            skip = _own_names(s_obj)
            flags_in, flags_safe, flags_hid, flags_part, flags_cap = [], [], [], [], []
            worst_cap = 0.0
            for s in vs:
                if in_transit(s["f"]):
                    flags_in.append(False)
                    flags_safe.append(False)
                    flags_hid.append(False)
                    flags_part.append(False)
                    flags_cap.append(False)
                    continue
                core.at_frame(s["f"])
                p = _subject_point(s_obj)
                x, y, z = cam.project(p)
                inside = bool(-0.02 <= x <= 1.02 and -0.02 <= y <= 1.02 and z > 0)
                flags_in.append(not inside)
                flags_safe.append(inside and not (sa["left"] <= x <= 1 - sa["right"] and sa["bottom"] <= y <= 1 - sa["top"]))
                hid = part = False
                cap_flag = False
                if inside:
                    r = _head_dims(s_obj)
                    mw = cam.ob.matrix_world
                    right = (mw.to_3x3() @ Vector((1, 0, 0))).normalized()
                    pts = [p, p + UPV * r * 0.7, p - UPV * r * 0.7, p + right * r * 0.7, p - right * r * 0.7]
                    blocked = [_first_blocker(sc, s["dg"], s["pos"], q, skip) for q in pts]
                    nb = sum(1 for b in blocked if b)
                    if nb >= 4:
                        hid = not any(a <= (s["f"] - 1) / fps <= b for a, b, _o in reveals)      # a reveal starts behind its occluder on purpose
                    elif nb >= 1:
                        part = True
                    if actor:
                        yt, yb = cam.project(p + UPV * r)[1], cam.project(p - UPV * r)[1]
                        top_f, bot_f = 1 - max(yt, yb), 1 - min(yt, yb)
                        ov = max(0.0, min(bot_f, cap_bot) - max(top_f, cap_top)) / max(bot_f - top_f, 1e-6)
                        worst_cap = max(worst_cap, ov)
                        cap_flag = ov > 0.25
                        s.setdefault("cap", {})[name] = ov
                flags_hid.append(hid)
                flags_part.append(part)
                flags_cap.append(cap_flag)
            n = max(1, len(vs))
            rep["subjects"][name] = {"in_frame": round(1 - sum(flags_in) / n, 3), "in_safe_area": round(1 - (sum(flags_safe) + sum(flags_in)) / n, 3),
                                     "hidden": round(sum(flags_hid) / n, 3), "caption_overlap_max": round(worst_cap, 2)}
            fr = [s["f"] for s in vs]
            sec = lambda run: (run[1] - run[0] + step) / fps
            for run in _runs(flags_in, fr):
                if sec(run) >= cfg["subject_out_s"]:
                    issue("block", "subject_out_of_frame", v["id"], run[0], f"{name} is out of the frame for {sec(run):.1f} s (frames {run[0]}-{run[1]})")
                elif sec(run) >= 0.2:
                    issue("warn", "subject_out_of_frame", v["id"], run[0], f"{name} leaves the frame for {sec(run):.2f} s (frames {run[0]}-{run[1]})")
            for run in _runs(flags_safe, fr):
                if sec(run) >= cfg["subject_out_s"]:
                    issue("warn", "subject_outside_safe_area", v["id"], run[0], f"{name} sits under the Shorts UI for {sec(run):.1f} s (frames {run[0]}-{run[1]})")
            code = "face_hidden" if actor else "subject_hidden"
            for run in _runs(flags_hid, fr):
                if sec(run) >= cfg["face_hidden_s"]:
                    issue("block", code, v["id"], run[0], f"{name} is hidden behind geometry or another object for {sec(run):.1f} s (frames {run[0]}-{run[1]})")
                else:
                    issue("warn", code, v["id"], run[0], f"{name} is hidden for {sec(run):.2f} s (frames {run[0]}-{run[1]})")
            for run in _runs(flags_part, fr):
                if sec(run) >= 0.8:
                    issue("warn", f"{code}_partly", v["id"], run[0], f"part of {name} is behind something for {sec(run):.1f} s (frames {run[0]}-{run[1]})")
            for run in _runs(flags_cap, fr):
                if sec(run) >= 0.5:
                    issue("block" if worst_cap > 0.6 and sec(run) >= 0.8 else "warn", "face_under_captions", v["id"], run[0],
                          f"the caption line crosses {name}'s face for {sec(run):.1f} s (up to {int(worst_cap * 100)}%): raise the subject in frame")
        view_reports.append(rep)

    # ---- line of action at cuts
    line = getattr(cam, "_line", None)
    if line and line.get("side") is not None:
        for vi, v in enumerate(views):
            if vi == 0 or not v.get("cut"):
                continue
            s = next((q for q in S if q["f"] >= v["frame"]), None)
            if s and cam._side_of(s["pos"]) != line["side"]:
                issue("warn", "line_crossed", v["id"], v["frame"], "this cut puts the camera on the other side of the line of action")

    # ---- how much of the shot is a completely still camera
    pairs = [k for k in k_ok]
    static = sum(k["dt"] for k in pairs if k["move"])
    total = sum(k["dt"] for k in pairs) or 1.0
    static_share = static / total
    if static_share > cfg["max_static_share"]:
        lvl = "block" if static_share > 0.7 else "warn"
        issue(lvl, "static_share", None, 1, f"the camera is completely still for {static_share * 100:.0f}% of the shot (target at most {cfg['max_static_share'] * 100:.0f}%): add a slow push, drift or track")

    # ---- per move report
    def window(t0, t1):
        return [k for k in k_ok if k["f0"] >= round(t0 * fps) + 1 - 1 and k["f1"] <= round(t1 * fps) + 1 + 1]

    move_reports = []
    for m in cam.moves:
        ks = window(m["t0"], m["t1"])
        f0, f1 = round(m["t0"] * fps) + 1, round(m["t1"] * fps) + 1
        mine = [i for i in issues if i["frame"] is not None and f0 - 1 <= i["frame"] <= f1 + 1 and i["code"] != "static_share" and (i["view"] == m["view"] or i["view"] is None)]
        mr = {k_: m[k_] for k_ in ("type", "t0", "t1", "view", "amount", "ease") if k_ in m}
        mr["start"], mr["end"] = m["start"], m["end"]
        mr["peak_speed_m_s"] = round(max((k["speed"] for k in ks), default=0.0), 3)
        mr["peak_ang_speed_deg_s"] = round(max((k["ang"] for k in ks), default=0.0), 2)
        mr["peak_accel_m_s2"] = round(max((k["acc"] for k in ks), default=0.0), 2)
        mr["issues"] = sorted({i["code"] for i in mine})
        mr["blocking"] = sorted({i["code"] for i in mine if i["level"] == "block"})
        mr["pass"] = not mr["blocking"]
        if m["type"] == "whip":
            d = m["t1"] - m["t0"]
            lo, hi = cfg["whip_dur_s"]
            if not (lo - 0.02 <= d <= hi + 0.02):
                issue("warn", "whip_duration", m["view"], f0, f"the whip takes {d:.2f} s: a whip reads at {lo}-{hi} s")
                mr["issues"].append("whip_duration")
        move_reports.append(mr)

    uniq, seen = [], set()
    for i in sorted(issues, key=lambda i: (i["frame"], i["code"])):          # one line per code and frame
        key = (i["code"], i["frame"], i["view"])
        if key not in seen:
            seen.add(key)
            uniq.append(i)
    # collapse a long run of the same code in the same view into its first frame
    out, last = [], {}
    for i in uniq:
        k = (i["code"], i["view"], i["level"])
        if k in last and i["frame"] - last[k]["frame"] <= 6 and i["code"] in ("camera_inside_geometry", "camera_under_floor", "camera_close", "camera_too_close", "camera_through_geometry",
                                                                             "speed_over_limit", "accel_over_limit", "ang_speed_over_limit", "ang_accel_over_limit", "jerk_spike"):
            last[k]["count"] = last[k].get("count", 1) + 1
            last[k]["last_frame"] = i["frame"]
            continue
        last[k] = i
        out.append(i)
    report = {"shot": shot.id, "frames": shot.frames, "fps": fps, "step": step, "static_share": round(static_share, 3),
              "moves": move_reports, "views": view_reports, "issues": out,
              "blocking": sum(1 for i in out if i["level"] == "block"), "warnings": sum(1 for i in out if i["level"] == "warn")}
    core.at_frame(1)
    return report


UPV = Vector((0, 0, 1))


def blocking(report: dict) -> list[dict]:
    return [i for i in report["issues"] if i["level"] == "block"]


def write(report: dict, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path


def summary(report: dict) -> str:
    """A few lines a person can read."""
    lines = [f"campath {report['shot']}: {report['blocking']} blocking, {report['warnings']} warning(s), camera still {report['static_share'] * 100:.0f}% of the time"]
    for i in report["issues"]:
        lines.append(f"  [{i['level']}] {i['code']} in {i['view']} at frame {i['frame']}: {i['detail']}")
    return "\n".join(lines)
