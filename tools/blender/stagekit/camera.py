"""stagekit.camera - one camera per shot, showing the staged action through views.

A view is what the viewer is given to look at for a few seconds: a framing chosen because the story needs it now.
The camera reaches a new view by a cut, or by travelling there (a whip, a push, a follow, a trip through a doorway).
Inside a view it moves (dolly, truck, pan, tilt, orbit, crane ...) or, if it does nothing else, drifts a little.
Every time is seconds from the start of the shot; key them to words with shot.t("phrase").

    cam = camera.Camera()
    cam.view("ring_drops", 0.0, on=[queen, ring], size="medium", side=-25)          # framed for you around the subjects
    cam.dolly(0.0, 2.0, 0.08)                                                       # lean in while she gasps (push() is the same)
    cam.view("ring_sinks", shot.t("into the deep"), on=[ring], size="insert", high=35)   # a cut to the object
    cam.follow(ring, shot.t("into the deep"), shot.t("pond", edge="end"))           # the camera travels with it
    cam.view("wide", shot.t("Bring it back"), pos=(0, -9, 2.2), aim=(0, 2, 1.0), lens=28)   # or place it by hand
    cam.view("gate", shot.t("At the far end"), on=[P["gate"]], size="full", travel=0.35)    # travel= moves instead of cutting

Framing keeps the subject in the upper-middle of the 9:16 frame: the caption line sits at 70% down and the Shorts UI
covers the bottom and right edge. `size`: "insert" (an object), "close" (a face), "medium" (waist up, hands in frame),
"full" (whole figure with room), "wide" (the place, figures small).

How the motion is made. Every move is a function of eased time that gives a whole camera pose (position, the point it
looks at, lens, focus point, f-stop, roll). It is written as a dense run of keys (every frame when the move is fast, every
second frame otherwise) and the rotation of each key is a look-at of that sample, so an orbit is a true arc, a crane is a
true boom and the horizon stays level unless roll is asked for. Ease profiles: linear, ease_in, ease_out, ease_in_out
(the default), settle (quick start, long soft landing, no overshoot), whip (fast in, sharp out). blend=0.3 on a move makes
it start 0.3 s before the previous one ends and mixes the two, so chained moves have no velocity jump.

Moves (all return the camera): dolly/push, truck, pan, tilt, orbit, crane, follow, track_with, whip, through, rack_focus,
dolly_zoom, handheld, reveal. Every move is logged in cam.moves. A view held for more than 1.2 s with no move of its own
gets a slow drift (style.json > camera > drift_default); view(..., still=True) or drift=False turns it off.
Framing helpers: ots, two_shot, reverse, low_hero, top_down, establish, insert, profile; cam.line(a, b) declares the line
of action and the helpers keep the camera on one side of it.
stagekit.campath measures the finished path (safe area, hidden faces, walls, speed, jerk, captions).
"""
from __future__ import annotations

import bisect
import math
import random

import bpy
from mathutils import Euler, Matrix, Vector

from . import core

SENSOR = 36.0
SIZES = {  # fraction of the frame HEIGHT the subject's height should fill, default lens, f-stop
    "insert": (0.30, 60, 2.8), "close": (0.36, 60, 2.8), "medium": (0.46, 45, 4.0), "full": (0.56, 38, 5.6), "wide": (0.34, 28, 8.0),
}
UP = Vector((0, 0, 1))


# ----------------------------------------------------------------------------- ease profiles
def _clamp01(u: float) -> float:
    return 0.0 if u < 0.0 else 1.0 if u > 1.0 else u


def _smoother(u: float) -> float:
    u = _clamp01(u)
    return u * u * u * (u * (6 * u - 15) + 10)


EASES = {
    "linear": lambda u: u,
    "ease_in": lambda u: 1.0 - math.cos(math.pi * u / 2),
    "ease_out": lambda u: math.sin(math.pi * u / 2),
    "ease_in_out": _smoother,
    "settle": lambda u: 1.0 - (1.0 - u) ** 3 * (1.0 + 3.0 * u),       # speed 12u(1-u)^2: soft start, long landing, never past 1
    "whip": lambda u: _smoother(_clamp01(u) ** 0.7),                  # off the mark at once, braking hard at the end
}


def ease_fn(ease):
    if callable(ease):
        return ease
    if ease in EASES:
        return EASES[ease]
    raise KeyError(f"unknown ease {ease!r}: use one of {', '.join(EASES)}")


# ----------------------------------------------------------------------------- pose
class Pose:
    """Everything the camera is at one instant: where it stands, the point it looks at, lens, the point in focus, f-stop, roll (deg)."""
    __slots__ = ("pos", "aim", "lens", "fstop", "roll", "focus")

    def __init__(self, pos, aim, lens=38.0, fstop=5.6, roll=0.0, focus=None):
        self.pos, self.aim = Vector(pos), Vector(aim)
        self.lens, self.fstop, self.roll = float(lens), float(fstop), float(roll)
        self.focus = None if focus is None else Vector(focus)

    def copy(self):
        return Pose(self.pos, self.aim, self.lens, self.fstop, self.roll, self.focus)

    def lerp(self, o: "Pose", s: float) -> "Pose":
        f0 = self.focus if self.focus is not None else self.aim
        f1 = o.focus if o.focus is not None else o.aim
        focus = None if (self.focus is None and o.focus is None) else f0.lerp(f1, s)
        return Pose(self.pos.lerp(o.pos, s), self.aim.lerp(o.aim, s), self.lens + (o.lens - self.lens) * s,
                    self.fstop + (o.fstop - self.fstop) * s, self.roll + (o.roll - self.roll) * s, focus)

    def brief(self) -> dict:
        return {"pos": [round(v, 3) for v in self.pos], "aim": [round(v, 3) for v in self.aim], "lens": round(self.lens, 2)}


class Framing(tuple):
    """What frame() and the framing helpers return: unpacks as (pos, aim, lens), and carries f-stop, focus point and roll too."""

    def __new__(cls, pos, aim, lens, fstop=5.6, roll=0.0, focus=None, kind="frame", size="manual", args=None):
        t = super().__new__(cls, (Vector(pos), Vector(aim), float(lens)))
        t.fstop, t.roll, t.kind, t.size, t.args = float(fstop), float(roll), kind, size, args or {}
        t.focus = None if focus is None else Vector(focus)
        return t

    def pose(self) -> Pose:
        return Pose(self[0], self[1], self[2], self.fstop, self.roll, self.focus)


def look_matrix(pos, aim, roll_deg: float = 0.0, hint: Vector | None = None) -> Matrix:
    """Camera orientation looking from pos at aim: screen-up stays towards world +Z (no flips); looking straight up or
    down, screen-up follows `hint` (a horizontal direction, default +Y). roll_deg turns the picture about the view axis."""
    f = Vector(aim) - Vector(pos)
    if f.length < 1e-6:
        f = Vector((0, 1, 0))
    f.normalize()
    r = f.cross(UP)
    if r.length < 0.02:
        h = Vector(hint) if hint is not None else Vector((0, 1, 0))
        h.z = 0.0
        if h.length < 1e-6:
            h = Vector((0, 1, 0))
        r = f.cross(h.normalized())
    r.normalize()
    u = r.cross(f).normalized()
    if roll_deg:
        c, s = math.cos(math.radians(roll_deg)), math.sin(math.radians(roll_deg))
        r, u = r * c + u * s, u * c - r * s
    return Matrix((r, u, -f)).transposed()


def _slerp_dir(a: Vector, b: Vector, w: float) -> Vector:
    a, b = a.normalized(), b.normalized()
    if a.dot(b) > 0.9999:
        return b.copy()
    return a.slerp(b, w)


# ----------------------------------------------------------------------------- the camera
class Camera:
    def __init__(self, lens: float = 38.0, name: str = "CAM", dof: bool = True):
        self.shot = core.current()
        self.data = bpy.data.cameras.new(name)
        self.data.lens = lens
        self.data.sensor_width = SENSOR
        self.data.clip_start = 0.05
        self.data.clip_end = 400.0
        self.ob = bpy.data.objects.new(name, self.data)
        core.link(self.ob, "RIG")
        self.ob.rotation_mode = "XYZ"
        self.focus = core.empty(f"{name}.focus", (0, 0, 1), "RIG", 0.05)
        self.data.dof.use_dof = dof
        self.data.dof.focus_object = self.focus
        self.data.dof.aperture_fstop = 5.6
        bpy.context.scene.camera = self.ob
        self.shot.camera = self
        self._views: list[dict] = []
        self._keys: list[dict] = []
        self.moves: list[dict] = []               # every move: {type, t0, t1, view, amount, ease, start, end, ...}
        self._last = None                         # (pos, aim, lens)
        self._pose: Pose | None = None            # the full pose of the last key
        self._samples: dict[int, Pose] = {}       # frame -> pose of every key written
        self._frames: list[int] = []              # sorted frames of _samples
        self._eul: dict[int, Euler] = {}
        self._view_on: list[list] = []            # per view: the things it was framed on (for campath)
        self._view_framing: dict[str, Framing] = {}
        self._line: dict | None = None            # the line of action
        self._hint = Vector((0, 1, 0))
        self._finishing = False
        self.step_fast = 1
        self.step_slow = 2
        for a in self.shot.actors.values():
            a._billboard(self.ob)

    # ------------------------------------------------------------------ what the rest of the kit reads
    @property
    def views(self) -> list[dict]:
        """The views in order. Reading it settles the automatic drift, so ask for it once the shot is built."""
        self.finish()
        return self._views

    @property
    def keys(self) -> list[dict]:
        self.finish()
        return self._keys

    # ------------------------------------------------------------------ geometry
    def fov(self, lens: float | None = None):
        """(vertical, horizontal) field of view in radians for the 9:16 frame."""
        lens = lens or self.data.lens
        r = bpy.context.scene.render
        asp = r.resolution_x / r.resolution_y
        v = 2 * math.atan(SENSOR / 2 / lens)
        return v, 2 * math.atan(SENSOR / 2 * asp / lens)

    @staticmethod
    def _subject_box(on, size: str):
        """World-space bounds of what must be in frame."""
        pts = []
        for s in on if isinstance(on, (list, tuple)) and not (len(on) == 3 and all(isinstance(v, (int, float)) for v in on)) else [on]:
            if hasattr(s, "stage") and hasattr(s, "head"):                      # an Actor
                bpy.context.view_layer.update()
                base = s.stage.matrix_world.translation.copy()
                h, r = s.height, s.head_r * s.scale
                top = base + Vector((0, 0, h))
                headc = s.head.point()
                if size == "close":
                    pts += [headc + Vector((0, 0, r * 1.25)), headc - Vector((0, 0, r * 1.7)), headc + Vector((r * 1.3, 0, 0)), headc - Vector((r * 1.3, 0, 0))]
                elif size == "medium":
                    pts += [top + Vector((0, 0, 0.05)), base + Vector((0, 0, h * 0.30)), headc + Vector((0.5, 0, 0)), headc - Vector((0.5, 0, 0))]
                else:
                    pts += [top + Vector((0, 0, 0.08)), base, base + Vector((0.45, 0, h / 2)), base - Vector((0.45, 0, -h / 2))]
            elif hasattr(s, "point"):
                p = s.point()
                pts += [p + Vector((0, 0, 0.12)), p - Vector((0, 0, 0.12))]
            elif hasattr(s, "matrix_world"):
                bpy.context.view_layer.update()
                fam = [s, *s.children_recursive]
                got = False
                for o in fam:
                    if o.type in ("MESH", "CURVE") and not o.hide_render:
                        pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
                        got = True
                if not got:
                    p = s.matrix_world.translation.copy()
                    pts += [p + Vector((0, 0, 0.15)), p - Vector((0, 0, 0.15))]
            else:
                p = Vector(s)
                pts += [p + Vector((0, 0, 0.1)), p - Vector((0, 0, 0.1))]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        return lo, hi

    def frame(self, on, size: str = "medium", side: float = 0.0, high: float = 6.0, lens: float | None = None, fill: float | None = None,
              place: float = 0.40, shift: float = 0.0):
        """Work out (pos, aim, lens) that frames the subjects. side: degrees the camera stands round to screen-right (+) or
        left (-) of the straight-on -Y position. high: degrees it looks down (negative looks up: power, threat).
        fill overrides how much of the frame height the subject fills. place: where its centre sits, 0 = top .. 1 = bottom
        (0.40 keeps faces above the captions). shift: slide the subject sideways in frame, -0.5 .. 0.5.
        Returns a Framing: unpack it as (pos, aim, lens), or give it to view(framing=...) / whip(to=...)."""
        frac, dlens, fst = SIZES[size]
        frac = fill or frac
        lens = lens or dlens
        lo, hi = self._subject_box(on, size)
        c = (lo + hi) / 2
        h = max(hi.z - lo.z, 0.05)
        az, el = math.radians(side), math.radians(high)
        to_cam = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        right = Vector((math.cos(az), math.sin(az), 0))
        w = max(abs((hi - lo).dot(right)), 0.05)
        fv, fh = self.fov(lens)
        sa = core.STYLE["safe_area"]
        usable_w = 1.0 - 2 * max(sa["left"], sa["right"])
        d = max(h / (2 * math.tan(fv / 2) * frac), w / (2 * math.tan(fh / 2) * usable_w * 0.92))
        depth = abs((hi - lo).dot(Vector((-to_cam.x, -to_cam.y, 0)))) / 2
        d += depth
        frame_h = 2 * d * math.tan(fv / 2)
        frame_w = 2 * d * math.tan(fh / 2)
        up = right.cross(-to_cam).normalized()
        if up.z < 0:
            up = -up
        aim = c - up * (0.5 - place) * frame_h - right * shift * frame_w
        pos = aim + to_cam * d
        if pos.z < 0.12:                                   # never put the camera in the ground
            pos.z = 0.12
        return Framing(pos, aim, lens, fst, 0.0, None, "frame", size, {"on": on, "size": size})

    # ------------------------------------------------------------------ keys
    def _interp(self, f: int, kind: str):
        for ob in (self.ob, self.focus, self.data):
            for fc in core.fcurves(ob):
                for kp in reversed(fc.keyframe_points):
                    if abs(kp.co.x - f) < 0.5:
                        kp.interpolation = kind
                        if kind not in ("CONSTANT", "LINEAR"):
                            kp.easing = "EASE_IN_OUT"
                        break
                    if kp.co.x < f - 0.5:
                        break

    def _forget(self, f: int):
        self._samples.pop(f, None)
        self._eul.pop(f, None)
        i = bisect.bisect_left(self._frames, f)
        if i < len(self._frames) and self._frames[i] == f:
            self._frames.pop(i)

    def _put(self, f: int, pose: Pose, interp: str | None = None):
        """Write one key of the camera: location, rotation (a look-at of this pose), focus point, lens, f-stop."""
        f = int(f)
        replace = f in self._samples
        idx = bisect.bisect_left(self._frames, f)
        prev_f = self._frames[idx - 1] if idx > 0 else None
        prev_e = self._eul.get(prev_f) if prev_f is not None else None
        d = pose.aim - pose.pos
        if d.length > 1e-6 and abs(d.normalized().z) < 0.995:
            self._hint = Vector((d.x, d.y, 0)).normalized()
        m = look_matrix(pose.pos, pose.aim, pose.roll, self._hint)
        e = m.to_euler("XYZ", prev_e) if prev_e is not None else m.to_euler("XYZ")
        self.ob.location = pose.pos
        self.ob.rotation_euler = e
        self.focus.location = pose.focus if pose.focus is not None else pose.aim
        self.data.lens = pose.lens
        self.data.dof.aperture_fstop = pose.fstop
        self.ob.keyframe_insert("location", frame=f)
        self.ob.keyframe_insert("rotation_euler", frame=f)
        self.focus.keyframe_insert("location", frame=f)
        self.data.keyframe_insert("lens", frame=f)
        self.data.keyframe_insert("dof.aperture_fstop", frame=f)
        if interp or replace:
            self._interp(f, interp or "BEZIER")
        entry = {"frame": f, "t": round((f - 1) / self.shot.fps, 3), "pos": tuple(round(v, 3) for v in pose.pos), "aim": tuple(round(v, 3) for v in pose.aim),
                 "rot": tuple(e), "lens": pose.lens}
        if replace:
            for k, old in enumerate(self._keys):
                if old["frame"] == f:
                    self._keys[k] = entry
                    break
        else:
            frames = [k["frame"] for k in self._keys]
            self._keys.insert(bisect.bisect_left(frames, f), entry)
            bisect.insort(self._frames, f)
        self._samples[f] = pose.copy()
        self._eul[f] = e.copy()
        if not self._frames or f >= self._frames[-1]:
            self._pose = pose.copy()
            self._last = (pose.pos.copy(), pose.aim.copy(), pose.lens)

    def _write(self, f: int, pos, aim, lens, interp=None, fstop=None, roll=0.0, focus=None):
        self._put(f, Pose(pos, aim, lens, fstop or self.data.dof.aperture_fstop, roll, focus), interp)

    def _pose_at(self, f: int) -> Pose:
        """The pose the written keys give at frame f (linear between keys)."""
        if f in self._samples:
            return self._samples[f]
        i = bisect.bisect_left(self._frames, f)
        if i <= 0:
            return self._samples[self._frames[0]]
        if i >= len(self._frames):
            return self._samples[self._frames[-1]]
        a, b = self._frames[i - 1], self._frames[i]
        return self._samples[a].lerp(self._samples[b], (f - a) / (b - a))

    def _pull_back(self, f: int):
        """A cut needs the old framing to END on the frame before it. If the last key (the end of a push or move) sits on
        or after the cut frame, slide it one frame earlier instead of letting it blend into the new view."""
        last = self._keys[-1]
        old = last["frame"]
        if old < f:
            return
        new = f - 1
        if len(self._keys) > 1 and self._keys[-2]["frame"] >= new:
            new = self._keys[-2]["frame"] + 1
        if new == old:
            return
        for ob in (self.ob, self.focus, self.data):
            for fc in core.fcurves(ob):
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - old) < 0.5:
                        d = new - kp.co.x
                        kp.co.x += d
                        kp.handle_left.x += d
                        kp.handle_right.x += d
                fc.update()
        last["frame"] = new
        last["t"] = round((new - 1) / self.shot.fps, 3)
        pose, e = self._samples.get(old), self._eul.get(old)
        self._forget(old)
        if pose is not None:
            self._samples[new] = pose
            self._eul[new] = e
            bisect.insort(self._frames, new)

    def _truncate(self, f: int):
        """A new view starts at frame f but keys of the old one run past it: the old view ends on the frame before the cut, in the pose it had there."""
        keep = self._pose_at(f - 1).copy()
        for ob in (self.ob, self.focus, self.data):
            for fc in core.fcurves(ob):
                for kp in reversed(list(fc.keyframe_points)):
                    if kp.co.x >= f - 0.5:
                        fc.keyframe_points.remove(kp)
                fc.update()
        for fr in [x for x in self._frames if x >= f - 1]:
            self._forget(fr)
        self._keys = [k for k in self._keys if k["frame"] < f - 1]
        self._put(f - 1, keep)

    def _resolve(self, pos, aim, lens, on, size, side, high, fill, place, shift):
        if on is not None and pos is None:
            return self.frame(on, size, side, high, lens, fill, place, shift)
        if pos is None or aim is None:
            if self._last is None:
                raise ValueError("the first view needs on=[...] or pos= and aim=")
            lp, la, ll = self._last
            pos = lp if pos is None else pos
            aim = la if aim is None else core.point_of(aim)
            lens = lens or ll
        return Vector(pos), core.point_of(aim) if not isinstance(aim, Vector) else aim, lens or self.data.lens

    def _as_pose(self, to, frame_no: int | None = None) -> Pose:
        """A Framing, a (pos, aim, lens) tuple, a dict of frame() arguments or of pos/aim/lens, or a subject -> a Pose."""
        if frame_no is not None:
            core.at_frame(frame_no)
        if isinstance(to, Pose):
            return to.copy()
        if isinstance(to, Framing):
            return to.pose()
        if isinstance(to, dict):
            if "pos" in to:
                return Pose(to["pos"], core.point_of(to["aim"]), to.get("lens", self.data.lens), to.get("fstop", 5.6), to.get("roll", 0.0))
            return self.frame(**to).pose()
        if isinstance(to, (tuple, list)) and len(to) == 3 and not all(isinstance(v, (int, float)) for v in to):
            return Pose(to[0], core.point_of(to[1]), to[2])
        return self.frame(on=to, size="medium").pose()

    # ------------------------------------------------------------------ views
    def _close_view(self, transition: str):
        """Called when the next view starts (cut or travel): the old view ends on the last key written, and a held view gets its drift now."""
        if self._views and self._keys:
            v = self._views[-1]
            v["end_frame"] = self._keys[-1]["frame"]
            v["end_interp"] = transition
            self._drift(len(self._views) - 1, v["end_frame"])

    def _add_view(self, vid, t, f, size, cut, why, on, subjects, drift, still, kind):
        shown = [getattr(s, "id", getattr(s, "name", str(s))) for s in (on if isinstance(on, (list, tuple)) else [on])] if on is not None else []
        self._views.append({"id": vid, "t": round(float(t), 3), "frame": f, "size": size, "cut": cut, "why": why, "on": shown,
                            "kind": kind, "drift": drift, "still": bool(still), "explicit_moves": 0})
        decl = []
        for s in ([*on] if isinstance(on, (list, tuple)) and not (len(on) == 3 and all(isinstance(v, (int, float)) for v in on)) else ([on] if on is not None else [])):
            decl.append(s)
        if subjects is not None:
            decl += list(subjects) if isinstance(subjects, (list, tuple)) and not (len(subjects) == 3 and all(isinstance(v, (int, float)) for v in subjects)) else [subjects]
        self._view_on.append(decl)
        self.shot.views = self._views

    def view(self, vid: str, t: float, on=None, size: str = "medium", side: float = 0.0, high: float = 6.0, pos=None, aim=None, lens: float | None = None,
             fill: float | None = None, place: float = 0.40, shift: float = 0.0, travel: float = 0.0, why: str = "", subject=None,
             drift=None, still: bool = False, framing=None, roll: float | None = None, fstop: float | None = None):
        """Start a view at time t. By default it is a CUT. travel=0.3 makes the camera fly there in 0.3 s instead (a whip:
        use it inside one place to carry the eye from one thing to the next; cut when the place or time jumps).
        Frame it with on=[things] + size/side/high, or by hand with pos= and aim=, or with a framing helper:
        view("x", t, framing=cam.ots(a, b)). why: the story reason (kept for review).
        subject: more things this view must keep in frame (checked by campath). drift: the automatic slow drift of a held
        view: None = the default, False = none, a number = that fraction of the distance, "in"/"out"/"left"/"right"/"up"/"down".
        still=True: this view must not move at all."""
        f = self.shot.f(t)
        core.at_frame(f)
        if framing is not None:
            pose = self._as_pose(framing)
            size = getattr(framing, "size", None) or size
            if roll is not None:
                pose.roll = roll
            if fstop is not None:
                pose.fstop = fstop
            self._view_framing[vid] = framing if isinstance(framing, Framing) else Framing(pose.pos, pose.aim, pose.lens, pose.fstop, pose.roll, pose.focus, "manual", "manual")
        else:
            res = self._resolve(pos, aim, lens, on, size, side, high, fill, place, shift)
            p, a, l = res
            fs = fstop or SIZES.get(size, (0, 0, 5.6))[2]
            pose = Pose(p, a, l, fs, roll or 0.0)
            self._view_framing[vid] = Framing(p, a, l, fs, roll or 0.0, None, getattr(res, "kind", "manual"), size if on is not None else "manual", getattr(res, "args", {}))
        if self._keys:
            if self._keys[-1]["frame"] >= f and f > 1:
                if sum(1 for k in self._keys if k["frame"] >= f) > 1:
                    self._truncate(f)                                     # a run-out or a long move reaches past the cut: drop the tail
                else:
                    self._pull_back(f)
            prev = self._keys[-1]
            if travel > 0:
                f0 = max(prev["frame"] + 1, self.shot.f(t - travel))
                if f0 > prev["frame"]:
                    self._put(f0, self._pose.copy())                       # hold the old view until the move starts
                self._close_view("SINE")
                self._interp(f0, "SINE")
            else:
                if f - 1 > prev["frame"]:
                    self._put(f - 1, self._pose.copy())
                self._close_view("CONSTANT")
                self._interp(self._keys[-1]["frame"], "CONSTANT")
        self._put(f, pose)
        vsize = size if (on is not None or size != "medium" or framing is not None) else "manual"
        self._add_view(vid, t, f, vsize, travel <= 0, why, on, subject, drift, still, "cut" if travel <= 0 else "travel")
        return self

    def view_at(self, frame: int) -> dict | None:
        cur = None
        for v in self._views:
            if v["frame"] <= frame:
                cur = v
        return cur

    # ------------------------------------------------------------------ the move engine
    def _count(self, f0: int):
        v = self.view_at(f0)
        if v is not None:
            v["explicit_moves"] += 1

    def _record(self, kind: str, f0: int, f1: int, p0: Pose, p1: Pose, amount, ease, view_id=None, **extra):
        v = self.view_at(f0)
        rec = {"type": kind, "t0": round((f0 - 1) / self.shot.fps, 3), "t1": round((f1 - 1) / self.shot.fps, 3),
               "view": view_id or (v["id"] if v else None), "amount": amount, "ease": ease if isinstance(ease, str) else "custom",
               "start": p0.brief(), "end": p1.brief()}
        rec.update(extra)
        self.moves.append(rec)
        return rec

    def _begin(self, t0: float, blend: float):
        """Hold the current pose until t0 (or, with blend, start inside the previous move): returns (f0, pose at f0, last key frame)."""
        if self._pose is None:
            raise ValueError("start a view first: cam.view(...)")
        f0 = self.shot.f(t0)
        last = self._frames[-1]
        if f0 > last:
            self._put(f0, self._pose.copy(), "LINEAR")
            if len(self._frames) > 1:
                self._interp(self._frames[-2], "LINEAR")
            last = f0
        elif f0 < last or (blend > 0 and f0 == last):
            if blend > 0 and f0 >= last - 1:
                f0 = max(self._frames[0], last - int(round(blend * self.shot.fps)))
            elif blend <= 0:
                f0 = last
        return f0, self._pose_at(f0).copy(), last

    def _run(self, kind: str, t0: float, t1: float, build, ease="ease_in_out", blend: float = 0.0, live: bool = False, amount=None,
             starts_view: bool = False, view_id=None, closes_view: str | None = None, **extra):
        """The one place moves are written. build(p0, f0) returns fn(s, f) -> Pose, with s the eased progress 0..1 and f the frame."""
        f0, p0, last = self._begin(t0, blend)
        if closes_view:
            self._close_view(closes_view)              # the old view's drift is settled here, so the move starts from where it really ended
            p0 = self._pose_at(f0).copy()
        f1 = max(self.shot.f(t1), f0 + 1)
        fn = build(p0, f0)
        easefn = ease_fn(ease)
        n = f1 - f0
        dur = n / self.shot.fps
        # fast moves (and anything following a live target) get a key on every frame, the rest on every second frame
        step = self.step_fast
        if not live and dur >= 1.0 and kind not in ("whip", "dolly_zoom"):
            peak, ang = 0.0, 0.0
            prev = fn(easefn(0.0), f0)
            for k in range(1, 25):
                cur = fn(easefn(k / 24), f0 + n * k / 24)
                dt = dur / 24
                peak = max(peak, (cur.pos - prev.pos).length / dt)
                da = (cur.aim - cur.pos).normalized().angle((prev.aim - prev.pos).normalized(), 0.0)
                ang = max(ang, math.degrees(da) / dt)
                prev = cur
            if peak < 1.5 and ang < 25:
                step = self.step_slow
        old = {f: self._pose_at(f).copy() for f in range(f0, last + 1)} if last > f0 else {}
        frames = list(range(f0 + 1, last + 1))
        k = max(last, f0)
        while k + step < f1:
            k += step
            frames.append(k)
        frames.append(f1)
        frames = sorted(set(x for x in frames if f0 < x <= f1))
        for f in frames:
            pose = fn(easefn((f - f0) / n), f)
            if f in old:
                w = _smoother((f - f0) / max(1, last - f0))
                pose = old[f].lerp(pose, w)
            self._put(f, pose, "LINEAR")
        p1 = self._pose_at(f1).copy()
        if not starts_view:
            self._count(f0)
        self._record(kind, f0, f1, p0, p1, amount, ease, view_id, blend=blend, **extra)
        return p1

    # ------------------------------------------------------------------ moves: the classics
    def dolly(self, t0: float, t1: float, amount: float = 0.08, ease="ease_in_out", blend: float = 0.0, metres: float | None = None):
        """Move along the view axis towards (amount > 0, a fraction of the distance to what it looks at) or away from (< 0) the subject.
        metres= says it in metres instead. Typical: slow push 1.5-3 s, +5-40% subject size."""
        def build(p0, f0):
            dist = (p0.aim - p0.pos).length
            frac = metres / dist if metres is not None and dist > 1e-6 else amount
            return lambda s, f: Pose(p0.aim + (p0.pos - p0.aim) * (1.0 - frac * s), p0.aim, p0.lens, p0.fstop, p0.roll, p0.focus)
        self._run("dolly", t0, t1, build, ease, blend, amount=amount if metres is None else metres)
        return self

    def push(self, t0: float, t1: float, amount: float = 0.08, ease="ease_in_out", blend: float = 0.0):
        """Slow lean in (amount = fraction of the distance; negative pulls back). Gives a held view life and weight. Same as dolly()."""
        return self.dolly(t0, t1, amount, ease, blend)

    def truck(self, t0: float, t1: float, right: float = 0.0, up: float = 0.0, ease="ease_in_out", blend: float = 0.0, turn: float = 0.0):
        """Slide sideways (right, metres, negative = left) and/or up (metres). The aim travels with the camera, so the
        picture slides with true parallax. turn=0..1 lets the camera keep looking at the old aim point instead (1 = fixed aim)."""
        def build(p0, f0):
            fwd = (p0.aim - p0.pos).normalized()
            r = fwd.cross(UP)
            r = r.normalized() if r.length > 0.02 else Vector((1, 0, 0))
            d = r * right + UP * up

            def fn(s, f):
                return Pose(p0.pos + d * s, p0.aim + d * (s * (1.0 - turn)), p0.lens, p0.fstop, p0.roll, p0.focus)
            return fn
        self._run("truck", t0, t1, build, ease, blend, amount={"right": right, "up": up})
        return self

    def pan(self, t0: float, t1: float, deg: float, ease="ease_in_out", blend: float = 0.0):
        """Turn on the spot about the vertical axis: deg > 0 turns right, < 0 left."""
        def build(p0, f0):
            v = p0.aim - p0.pos
            return lambda s, f: Pose(p0.pos, p0.pos + Matrix.Rotation(math.radians(-deg * s), 3, "Z") @ v, p0.lens, p0.fstop, p0.roll,
                                     None if p0.focus is None else p0.pos + Matrix.Rotation(math.radians(-deg * s), 3, "Z") @ (p0.focus - p0.pos))
        self._run("pan", t0, t1, build, ease, blend, amount=deg)
        return self

    def tilt(self, t0: float, t1: float, deg: float, ease="ease_in_out", blend: float = 0.0):
        """Turn on the spot about the sideways axis: deg > 0 looks up, < 0 down."""
        def build(p0, f0):
            v = p0.aim - p0.pos
            axis = v.cross(UP)
            axis = axis.normalized() if axis.length > 0.02 else Vector((1, 0, 0))
            return lambda s, f: Pose(p0.pos, p0.pos + Matrix.Rotation(math.radians(deg * s), 3, axis) @ v, p0.lens, p0.fstop, p0.roll, None)
        self._run("tilt", t0, t1, build, ease, blend, amount=deg)
        return self

    def orbit(self, t0: float, t1: float, around, deg: float = 28.0, rise: float = 0.0, to_distance: float | None = None, ease="ease_in_out", blend: float = 0.0):
        """Swing round a subject on a true arc, keeping the distance (or closing/opening to to_distance), the height (plus rise)
        and what it looks at relative to the subject. deg > 0 carries the camera to ITS right, < 0 to its left.
        Typical: about 3 s, 25-30 degrees. `around` is a point, an object or an actor (it may be moving)."""
        live = _is_live(around)

        def build(p0, f0):
            c0 = self._pt(around, f0)
            rel = p0.pos - c0
            r0 = math.hypot(rel.x, rel.y)
            a0 = math.atan2(rel.y, rel.x)
            aim_off = p0.aim - c0
            if r0 < 1e-3:
                raise ValueError("orbit: the camera is on the axis of the subject; put it some distance away first")

            def fn(s, f):
                c = self._pt(around, f) if live else c0
                a = a0 + math.radians(deg) * s
                r = r0 + ((to_distance - r0) * s if to_distance is not None else 0.0)
                pos = c + Vector((r * math.cos(a), r * math.sin(a), rel.z + rise * s))
                return Pose(pos, c + aim_off, p0.lens, p0.fstop, p0.roll, p0.focus)
            return fn
        self._run("orbit", t0, t1, build, ease, blend, live=live, amount=deg, rise=rise)
        return self

    def crane(self, t0: float, t1: float, rise: float = 0.0, back: float = 0.0, tilt_to: float | None = None, ease="ease_in_out", blend: float = 0.0):
        """Boom up (rise > 0, metres) or down, and/or back away along the ground (back > 0). The aim is held, so the camera
        tilts as it climbs; tilt_to=<degrees of pitch, negative = looking down> instead turns the view steadily to that pitch.
        Typical: 2.5-3 s, 35-75 degrees of pitch change."""
        def build(p0, f0):
            v = p0.aim - p0.pos
            dist = v.length
            hf = Vector((v.x, v.y, 0))
            hf = hf.normalized() if hf.length > 1e-6 else Vector((0, 1, 0))
            pitch0 = math.asin(max(-1.0, min(1.0, v.z / dist)))

            def fn(s, f):
                pos = p0.pos + UP * (rise * s) - hf * (back * s)
                if tilt_to is None:
                    return Pose(pos, p0.aim, p0.lens, p0.fstop, p0.roll, p0.focus)
                pitch = pitch0 + (math.radians(tilt_to) - pitch0) * s
                d = Vector((hf.x * math.cos(pitch), hf.y * math.cos(pitch), math.sin(pitch)))
                return Pose(pos, pos + d * dist, p0.lens, p0.fstop, p0.roll, None)
            return fn
        self._run("crane", t0, t1, build, ease, blend, amount={"rise": rise, "back": back, "tilt_to": tilt_to})
        return self

    def follow(self, target, t0: float, t1: float, keep: str = "offset", every: int = 2, lag: float = 0.0, smooth: float = 0.0, lead: float = 0.0,
               settle: float | None = None):
        """Travel with a moving thing from t0 to t1 (a falling ring, a thrown net, a walker).
        keep="offset": the camera keeps its distance and angle to the target; keep="aim": it stays put and turns to watch.
        lag: seconds the camera runs behind. smooth: seconds of smoothing of the target's path (a walker's bob and sway
        stay out of the picture). lead: metres of room kept IN FRONT of a walker (the aim runs ahead of it, eased in over 0.6 s).
        settle: seconds after t1 in which the camera runs on and glides to a stop (default 0.6 when smooth or lead is used, else 0:
        the old behaviour, which halts dead at the target's speed)."""
        f0, f1 = self.shot.f(t0), self.shot.f(t1)
        if self._pose is None:
            raise ValueError("start a view first: cam.view(...)")
        prev = self._keys[-1]
        if f0 > prev["frame"]:
            self._put(f0, self._pose.copy())
        pose0 = self._pose.copy()
        pos0, aim0, lens = pose0.pos, pose0.aim, pose0.lens
        start = self._pt(target, f0)
        off_p, off_a = pos0 - start, aim0 - start
        lagf = int(lag * self.shot.fps)
        alpha = 1.0 if smooth <= 0 else 1.0 - math.exp(-every / (smooth * self.shot.fps))
        sm = start.copy()
        f = f0 + every
        while f <= f1:
            p = self._pt(target, max(f0, f - lagf))
            sm = sm.lerp(p, alpha)
            ahead = Vector((0, 0, 0))
            if lead:
                q = self._pt(target, min(self.shot.frames, max(f0, f - lagf) + 3))
                dv = q - p
                dv.z = 0
                if dv.length > 1e-5:
                    ahead = dv.normalized() * (lead * _smoother((f - f0) / (0.6 * self.shot.fps)))
            self._interp(self._keys[-1]["frame"], "LINEAR")
            if keep == "offset":
                self._put(f, Pose(sm + off_p, sm + off_a + ahead, lens, pose0.fstop, pose0.roll, None))
            else:
                self._put(f, Pose(pos0, sm + off_a + ahead, lens, pose0.fstop, pose0.roll, None))
            f += every
        if (settle if settle is not None else (0.6 if (smooth > 0 or lead) else 0.0)) > 0:
            self._run_out(settle if settle is not None else 0.6)
        self._count(f0)
        self._record("follow", f0, self._keys[-1]["frame"], pose0, self._pose, {"keep": keep, "lag": lag, "smooth": smooth, "lead": lead}, "linear")
        return self

    def _run_out(self, settle: float):
        """After a follow or a track: keep going and glide to a stop over `settle` seconds, so the camera never halts dead at walking speed."""
        if len(self._frames) < 2 or settle <= 0:
            return
        fe, fp = self._frames[-1], self._frames[-2]
        last, prev = self._samples[fe], self._samples[fp]
        df = max(1, fe - fp)
        vel_p, vel_a = (last.pos - prev.pos) / df, (last.aim - prev.aim) / df          # metres per frame at the end
        n = int(settle * self.shot.fps)
        for k in range(1, n + 1):
            if fe + k > self.shot.frames:
                break
            u = k / n
            run = n * (u - u * u / 2)                                      # frames' worth of travel left in a linear slow-down to rest
            self._put(fe + k, Pose(last.pos + vel_p * run, last.aim + vel_a * run, last.lens, last.fstop, last.roll, None), "LINEAR")

    def track_with(self, target, t0: float, t1: float, side="right", distance: float = 3.5, height: float | None = None, aim_height: float | None = None,
                   lens: float | None = None, lead: float = 0.3, smooth: float = 0.45, join: float = 1.0, settle: float = 0.8):
        """Walk alongside a moving subject: the camera runs parallel to the subject's path at `distance` metres, on its
        `side` ("right"/"left" of the direction of travel, or degrees round from straight ahead), looking at it with `lead` metres
        of room in front. height: camera height (default: where it is now); aim_height: height of the point it looks at
        (default: where it looks now, relative to the subject). join: seconds it takes to settle into the track from the pose it was in.
        settle: seconds after t1 in which the camera runs on and glides to a stop (so it never halts dead at walking speed)."""
        if self._pose is None:
            raise ValueError("start a view first: cam.view(...)")
        f0, p0, _ = self._begin(t0, 0.0)
        f1 = max(self.shot.f(t1), f0 + 1)
        a = self._pt(target, f0)
        b = self._pt(target, f1)
        trav = b - a
        trav.z = 0
        if trav.length < 0.05:
            raise ValueError("track_with: the subject does not move between t0 and t1")
        trav.normalize()
        if isinstance(side, str):
            ang = 90.0 if side == "right" else -90.0
        else:
            ang = float(side)
        out = Matrix.Rotation(math.radians(-ang), 3, "Z") @ trav        # direction from subject to camera
        h = p0.pos.z if height is None else height
        ah = (p0.aim.z - a.z) if aim_height is None else aim_height
        lens = lens or p0.lens
        alpha = 1.0 - math.exp(-1.0 / (max(smooth, 1e-3) * self.shot.fps))
        sm = a.copy()
        join_f = max(1, int(join * self.shot.fps))
        start_pose = p0
        for f in range(f0 + 1, f1 + 1):
            p = self._pt(target, f)
            sm = sm.lerp(p, alpha)
            pos = Vector((sm.x + out.x * distance, sm.y + out.y * distance, h))
            aim = Vector((sm.x + trav.x * lead, sm.y + trav.y * lead, p.z + ah))
            want = Pose(pos, aim, lens, start_pose.fstop, 0.0, None)
            w = _smoother((f - f0) / join_f) if f - f0 < join_f else 1.0
            self._put(f, start_pose.lerp(want, w) if w < 1.0 else want, "LINEAR")
        self._run_out(settle)
        self._count(f0)
        self._record("track_with", f0, f1, p0, self._pose, distance, "linear", side=side)
        return self

    def whip(self, t: float, to, dur: float = 0.35, vid: str | None = None, why: str = "", subjects=None, ease="whip", **frame_kw):
        """Fast pan-travel to a new framing: the camera leaves at time t and lands dur seconds later (0.3-0.5 s reads as a whip).
        `to` is a Framing (cam.frame / ots / ...), a (pos, aim, lens) tuple, a dict of frame() arguments, or a subject. The new view
        `vid` begins when the camera lands. frame_kw (on=, size=, side= ...) frame the target when `to` is None."""
        if to is None:
            to = frame_kw
        f_land = self.shot.f(t + dur)
        target = self._as_pose(to, f_land)
        vid = vid or f"view{len(self._views) + 1}"

        def build(p0, f0):
            return lambda s, f: p0.lerp(target, s)
        self._run("whip", t, t + dur, build, ease, starts_view=True, amount=dur, view_id=None, closes_view="LINEAR")
        self._add_view(vid, t + dur, self._frames[-1], getattr(to, "size", frame_kw.get("size", "manual")), False, why, frame_kw.get("on", getattr(to, "args", {}).get("on")),
                       subjects, None, False, "whip")
        self.moves[-1]["to_view"] = vid
        self._view_framing[vid] = to if isinstance(to, Framing) else Framing(target.pos, target.aim, target.lens, target.fstop, target.roll, target.focus, "manual", "manual")
        return self

    def through(self, t0: float, t1: float, opening, to, vid: str | None = None, why: str = "", ease="ease_in_out", subjects=None, axis=None,
                lead_in: float = 0.8, **frame_kw):
        """Travel through a doorway, window or screen: the camera flies on a smooth curve that passes exactly through the point
        `opening`, going straight along `axis` (a direction; default: the horizontal line from where it starts to where it lands)
        for at least lead_in metres either side (more when the trip is long), then settles on the framing `to` beyond it. `to` is a Framing, a (pos, aim, lens) tuple, a
        dict of frame() arguments (use this for a moving subject: it is framed at the landing time) or a subject. The speed along
        the curve is exactly the ease. The new view `vid` begins on arrival."""
        if to is None:
            to = frame_kw
        f1 = self.shot.f(t1)
        target = self._as_pose(to, f1)
        o = self._pt(opening, f1)
        vid = vid or f"view{len(self._views) + 1}"

        def build(p0, f0):
            L1, L2 = (o - p0.pos).length, (target.pos - o).length
            if axis is not None:
                ax = Vector(axis)
            else:
                ax = target.pos - p0.pos
                ax.z = 0.0
            ax = ax.normalized() if ax.length > 1e-6 else (o - p0.pos).normalized()
            k = min(max(lead_in, 0.35 * min(L1, L2)), 0.45 * min(L1, L2))      # a long straight approach keeps the bend gentle at speed
            nodes = [p0.pos, o - ax * k, o, o + ax * k, target.pos]
            table, frac_open = _arc_spline(nodes, 2)
            d0 = (p0.aim - p0.pos)
            d1 = (target.aim - target.pos)
            l0, l1 = d0.length, d1.length

            def fn(s, f):
                pos = _arc_at(table, s)
                w = _smoother((s - frac_open * 0.6) / max(1.0 - frac_open * 0.6, 1e-6))
                d = _slerp_dir(d0, d1, w) * (l0 + (l1 - l0) * w)
                lens = p0.lens + (target.lens - p0.lens) * _smoother(s)
                return Pose(pos, pos + d, lens, p0.fstop + (target.fstop - p0.fstop) * s, p0.roll + (target.roll - p0.roll) * s, None)
            return fn
        self._run("through", t0, t1, build, ease, starts_view=True, amount=None, view_id=None, closes_view="LINEAR", opening=[round(v, 3) for v in o])
        self._add_view(vid, t1, self._frames[-1], getattr(to, "size", frame_kw.get("size", "manual")), False, why, frame_kw.get("on", getattr(to, "args", {}).get("on")),
                       subjects, None, False, "through")
        self.moves[-1]["to_view"] = vid
        self._view_framing[vid] = to if isinstance(to, Framing) else Framing(target.pos, target.aim, target.lens, target.fstop, target.roll, target.focus, "manual", "manual")
        return self

    def rack_focus(self, t0: float, t1: float, to, fstop: float | None = None, ease="ease_in_out"):
        """Move the focus (only the focus) from what is sharp now to `to` (a point, object or actor), laid over whatever the camera
        is doing. fstop= opens the lens for the shift (2.0 gives a clear blur) and it stays open. The focus stays on `to` afterwards."""
        if self._pose is None:
            raise ValueError("start a view first: cam.view(...)")
        f0, f1 = self.shot.f(t0), max(self.shot.f(t1), self.shot.f(t0) + 1)
        easefn = ease_fn(ease)
        live = _is_live(to)
        base = self._pose_at(f0)
        fa = base.focus.copy() if base.focus is not None else (base.aim.copy())
        fb0 = self._pt(to, f0)
        fst0 = base.fstop
        last_pt = fb0
        for f in range(f0, f1 + 1):
            s = easefn((f - f0) / (f1 - f0))
            last_pt = self._pt(to, f) if live else fb0
            pt = fa.lerp(last_pt, s)
            self.focus.location = pt
            self.focus.keyframe_insert("location", frame=f)
            if fstop:
                self.data.dof.aperture_fstop = fst0 + (fstop - fst0) * s
                self.data.keyframe_insert("dof.aperture_fstop", frame=f)
            for ob in (self.focus, self.data):
                for fc in core.fcurves(ob):
                    for kp in reversed(fc.keyframe_points):
                        if abs(kp.co.x - f) < 0.5:
                            kp.interpolation = "LINEAR"
                            break
                        if kp.co.x < f - 0.5:
                            break
            if f in self._samples:
                self._samples[f].focus = pt.copy()
                if fstop:
                    self._samples[f].fstop = self.data.dof.aperture_fstop
        for fr in self._frames:                                    # later keys keep the focus where the rack left it
            if fr > f1:
                self._samples[fr].focus = last_pt.copy()
                if fstop:
                    self._samples[fr].fstop = fstop
                self.focus.location = last_pt
                self.focus.keyframe_insert("location", frame=fr)
                if fstop:
                    self.data.dof.aperture_fstop = fstop
                    self.data.keyframe_insert("dof.aperture_fstop", frame=fr)
        if self._frames and f1 >= self._frames[-1]:
            self._pose.focus = last_pt.copy()
            if fstop:
                self._pose.fstop = fstop
        self._record("rack_focus", f0, f1, base, self._pose_at(f1), None, ease, fstop=fstop)
        return self

    def dolly_zoom(self, t0: float, t1: float, amount: float = 0.25, ease="ease_in_out"):
        """The vertigo effect: dolly in (amount > 0, fraction of the distance) while the lens widens so the subject keeps its
        size and the background stretches away; amount < 0 does it the other way."""
        def build(p0, f0):
            d0 = (p0.pos - p0.aim).length

            def fn(s, f):
                k = 1.0 - amount * s
                return Pose(p0.aim + (p0.pos - p0.aim) * k, p0.aim, p0.lens * k, p0.fstop, p0.roll, p0.focus)
            return fn
        self._run("dolly_zoom", t0, t1, build, ease, amount=amount)
        return self

    def handheld(self, t0: float, t1: float, amount: float = 0.012, seed: int | None = None):
        """Organic hand-held life laid over whatever the camera is doing from t0 to t1: slow, small, seeded noise (amount =
        metres of sway; the turn is about 20 degrees per metre of it). It fades in and out over the first and last quarter."""
        f0, f1 = self.shot.f(t0), self.shot.f(t1)
        if f1 <= f0 + 1:
            return self
        rnd = random.Random(seed if seed is not None else int(t0 * 100) + 17)
        freqs = (0.35, 0.8, 1.45)
        wts = (1.0, 0.55, 0.3)
        ph = [[rnd.uniform(0, math.tau) for _ in freqs] for _ in range(6)]

        def noise(axis, t):
            return sum(w * math.sin(math.tau * fq * t + ph[axis][i]) for i, (fq, w) in enumerate(zip(freqs, wts))) / sum(wts)

        base = {}
        for f in range(f0, f1 + 1):
            core.at_frame(f)
            base[f] = (self.ob.location.copy(), self.ob.rotation_euler.copy())
        rot = math.radians(amount * 20.0)
        p0 = self._pose_at(f0).copy()
        for f in range(f0, f1 + 1):
            u = (f - f0) / (f1 - f0)
            env = _smoother(min(u / 0.25, (1 - u) / 0.25, 1.0))
            t = (f - 1) / self.shot.fps
            loc, eul = base[f]
            self.ob.location = loc + Vector((noise(0, t), noise(1, t), noise(2, t))) * (amount * env)
            e = eul.copy()
            e.x += noise(3, t) * rot * env
            e.y += noise(4, t) * rot * env * 0.5
            e.z += noise(5, t) * rot * env
            self.ob.rotation_euler = e
            self.ob.keyframe_insert("location", frame=f)
            self.ob.keyframe_insert("rotation_euler", frame=f)
            self._interp(f, "LINEAR")
        self._count(f0)
        self._record("handheld", f0, f1, p0, self._pose_at(f1), amount, "linear", seed=seed)
        return self

    def reveal(self, t0: float, t1: float, from_behind, to, vid: str | None = None, why: str = "", ease="ease_in_out", subjects=None, **frame_kw):
        """Start a view (a cut at t0) with `from_behind` (a wall edge, a pillar, a back, a doorframe) filling the lens, then slide
        sideways past it by t1 to the framing `to`. The camera starts lined up with the occluder and trucks away from it,
        so the foreground wipes off with true parallax. The occluder must stand between the camera and the subject."""
        if to is None:
            to = frame_kw
        f0, f1 = self.shot.f(t0), self.shot.f(t1)
        end = self._as_pose(to, f1)
        core.at_frame(f1)
        lo, hi = core.world_bbox([from_behind, *getattr(from_behind, "children_recursive", [])]) if hasattr(from_behind, "matrix_world") else (None, None)
        oc = (lo + hi) / 2 if lo is not None else core.point_of(from_behind)
        fwd = (end.aim - end.pos).normalized()
        r = fwd.cross(UP).normalized()
        off = (oc - end.pos).dot(r)
        if abs(off) < 0.25:
            off = 0.25 + (((hi - lo).dot(Vector((abs(r.x), abs(r.y), 0))) / 2) if lo is not None else 0.4)
        shift = r * off
        start = Pose(end.pos + shift, end.aim + shift, end.lens, end.fstop, end.roll, None)
        vid = vid or f"view{len(self._views) + 1}"
        self.view(vid, t0, framing=Framing(start.pos, start.aim, start.lens, start.fstop, start.roll, None, "reveal", "manual"), why=why, subject=subjects)
        self._views[-1]["kind"] = "reveal"
        self._views[-1]["occluder"] = getattr(from_behind, "name", None)

        def build(p0, f):
            return lambda s, fr: p0.lerp(end, s)
        self._run("reveal", t0, t1, build, ease, starts_view=False, amount=round(off, 3), view_id=vid, occluder=getattr(from_behind, "name", None))
        self._view_framing[vid] = to if isinstance(to, Framing) else Framing(end.pos, end.aim, end.lens, end.fstop, end.roll, end.focus, "manual", "manual")
        return self

    # ------------------------------------------------------------------ the old moves
    def move(self, t0: float, t1: float, on=None, size: str = "medium", side: float = 0.0, high: float = 6.0, pos=None, aim=None, lens: float | None = None,
             fill: float | None = None, place: float = 0.40, shift: float = 0.0, ease: str = "SINE"):
        """Inside the current view: hold until t0, then travel to a new framing, arriving at t1 (reveal, tilt, track, crane).
        A straight blend between two framings; for arcs, booms and orbits use orbit() and crane()."""
        f0, f1 = self.shot.f(t0), self.shot.f(t1)
        prev = self._keys[-1]
        if f0 > prev["frame"]:
            self._put(f0, self._pose.copy())
        p_start = self._pose.copy()
        start_f = self._keys[-1]["frame"]
        self._interp(start_f, ease)
        core.at_frame(f1)
        p, a, l = self._resolve(pos, aim, lens, on, size, side, high, fill, place, shift)
        end = Pose(p, a, l, self._pose.fstop, self._pose.roll, None)
        end_f = max(f1, self._keys[-1]["frame"] + 1)
        self._put(end_f, end)
        self._count(f0)
        self._record("move", start_f, end_f, p_start, end, None, ease)
        return self

    def hold(self, t: float):
        """Keep the current framing exactly until t (a line landing, the last image)."""
        prev = self._keys[-1]
        f = self.shot.f(t)
        if f > prev["frame"]:
            self._interp(prev["frame"], "LINEAR")
            self._put(f, self._pose.copy())
        return self

    def shake(self, t: float, amount: float = 0.04, dur: float = 0.35):
        """A short jolt on an impact (a splash, a slam). amount in metres."""
        rnd = random.Random(int(t * 100))
        pose = self._pose.copy()
        n = max(3, int(dur * self.shot.fps / 2))
        f = self.shot.f(t)
        if f > self._keys[-1]["frame"]:
            self._put(f, pose)
        self._count(f)
        for i in range(1, n + 1):
            k = amount * (1 - i / n)
            j = Vector((rnd.uniform(-k, k), 0, rnd.uniform(-k, k)))
            self._interp(self._keys[-1]["frame"], "LINEAR")
            self._put(f + 2 * i, Pose(pose.pos + j, pose.aim + j * 0.6, pose.lens, pose.fstop, pose.roll, pose.focus))
        self._put(f + 2 * n + 1, pose)
        self._record("shake", f, f + 2 * n + 1, pose, pose, amount, "linear")
        return self

    # ------------------------------------------------------------------ line of action and framing helpers
    def line(self, a, b, side: int | None = None):
        """Declare the line of action between two things (the two people in a scene). Framing helpers keep the camera on
        one side of it: side=+1 the left of a->b, -1 the right; None = whichever side the first helper picks. Positions are
        taken now. A helper called with cross_line=True may cross it."""
        pa, pb = self._pt(a, bpy.context.scene.frame_current), self._pt(b, bpy.context.scene.frame_current)
        pa.z = pb.z = 0.0
        self._line = {"a": pa, "b": pb, "side": side}
        return self

    def _side_of(self, p: Vector) -> int:
        a, b = self._line["a"], self._line["b"]
        c = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
        return 1 if c >= 0 else -1

    def _mirror(self, p: Vector) -> Vector:
        a, b = self._line["a"], self._line["b"]
        d = Vector((b.x - a.x, b.y - a.y, 0)).normalized()
        n = Vector((-d.y, d.x, 0))
        k = (p.x - a.x) * n.x + (p.y - a.y) * n.y
        return Vector((p.x - 2 * k * n.x, p.y - 2 * k * n.y, p.z))

    def _keep_line(self, fr: Framing, cross_line: bool) -> Framing:
        """Put the framing on the declared side of the line of action (mirrors it across the line if it is on the wrong one)."""
        if self._line is None or cross_line:
            return fr
        s = self._side_of(fr[0])
        if self._line["side"] is None:
            self._line["side"] = s
            return fr
        if s == self._line["side"]:
            return fr
        out = Framing(self._mirror(fr[0]), self._mirror(fr[1]), fr[2], fr.fstop, fr.roll, None if fr.focus is None else self._mirror(fr.focus), fr.kind, fr.size, fr.args)
        return out

    def _who(self, x) -> dict:
        if hasattr(x, "stage") and hasattr(x, "head"):
            bpy.context.view_layer.update()
            return {"head": Vector(x.head.point()), "r": x.head_r * x.scale, "h": x.height, "base": x.stage.matrix_world.translation.copy(), "actor": x}
        p = self._pt(x, bpy.context.scene.frame_current)
        return {"head": p, "r": 0.12, "h": 0.3, "base": p, "actor": None}

    @staticmethod
    def _facing(x) -> Vector:
        """Horizontal direction an actor faces: its .facing (vector or degrees) or its stage turned from -Y."""
        f = getattr(x, "facing", None)
        if callable(f):
            f = f()
        if isinstance(f, (int, float)):
            a = math.radians(f)
            return Vector((-math.sin(a), math.cos(a), 0))
        if f is not None:
            v = Vector(f)
            v.z = 0
            return v.normalized()
        st = getattr(x, "stage", None)
        z = st.rotation_euler.z if st is not None else 0.0
        return Vector((math.sin(z), -math.cos(z), 0))

    def ots(self, over, on, side: str | None = None, back: float = 0.8, lateral: float = 0.34, head_frac: float = 0.2, place: float = 0.40,
            lens: float | None = None, cross_line: bool = False) -> Framing:
        """Over the shoulder: the camera stands behind and beside `over`, so that actor's head and shoulder make a soft dark
        foreground at one frame edge, and `on` is framed (head about head_frac of the frame height) on the other side of the
        frame. side="left"/"right": which edge the foreground shoulder is on (default: the one that keeps the line of action).
        back/lateral: metres behind and beside over's head. Use view(vid, t, framing=cam.ots(a, b))."""
        A, B = self._who(over), self._who(on)
        d = B["head"] - A["head"]
        d.z = 0
        d = d.normalized() if d.length > 1e-4 else Vector((0, 1, 0))
        R = d.cross(UP).normalized()
        sgn = {"left": 1, "right": -1, None: 1}[side]

        def build(sg):
            pos = A["head"] - d * back + R * (lateral * sg)
            pos.z = A["head"].z + 0.05
            L = (B["head"] - pos).length
            frame_h = 2 * B["r"] / head_frac
            ln = lens or max(28.0, min(100.0, SENSOR * L / frame_h))
            fh = SENSOR * L / ln
            fw = fh * (bpy.context.scene.render.resolution_x / bpy.context.scene.render.resolution_y)
            aim = B["head"] - UP * (0.5 - place) * fh - R * (0.14 * fw * sg)
            return Framing(pos, aim, ln, 2.8, 0.0, B["head"], "ots", "close", {"over": over, "on": on, "side": "left" if sg > 0 else "right"})
        fr = build(sgn)
        if self._line is not None and not cross_line:
            if self._line["side"] is None:
                self._line["side"] = self._side_of(fr[0])
            elif self._side_of(fr[0]) != self._line["side"]:
                fr = build(-sgn)
                if self._side_of(fr[0]) != self._line["side"]:
                    fr = self._keep_line(fr, False)
        fr.args["back"], fr.args["lateral"], fr.args["head_frac"], fr.args["place"] = back, lateral, head_frac, place
        return fr

    def two_shot(self, a, b, size: str = "medium", high: float = 6.0, side: str | None = None, lens: float | None = None, cross_line: bool = False,
                 fill: float | None = None) -> Framing:
        """Both of them in one frame, the camera square to the line between them. side="near"/"far" picks which of the two sides
        of that line (default: the -Y one, or the declared side of the line of action)."""
        A, B = self._who(a), self._who(b)
        d = B["head"] - A["head"]
        d.z = 0
        d = d.normalized() if d.length > 1e-4 else Vector((1, 0, 0))
        n = Vector((-d.y, d.x, 0))
        if n.y > 0:
            n = -n                                              # default: the camera on the -Y side
        if side == "far":
            n = -n
        az = math.degrees(math.atan2(n.x, -n.y))
        fr = self.frame([a, b], size, az, high, lens, fill)
        fr = Framing(*fr, fstop=fr.fstop, roll=0.0, focus=None, kind="two_shot", size=size, args={"a": a, "b": b, "size": size, "high": high})
        return self._keep_line(fr, cross_line)

    def reverse(self, of_view, cross_line: bool = False) -> Framing:
        """The matching reverse angle of an earlier view (its id, or a Framing): an ots becomes the over-the-shoulder from
        the other actor, anything else is the same framing seen from the other end of the line, on the SAME side of it."""
        fr = self._view_framing.get(of_view) if isinstance(of_view, str) else of_view
        if fr is None:
            raise KeyError(f"reverse: no view {of_view!r} was framed with a helper (view ids: {', '.join(self._view_framing)})")
        if fr.kind == "ots":
            ar = fr.args
            side = "right" if ar.get("side") == "left" else "left"
            out = self.ots(ar["on"], ar["over"], side=side, back=ar.get("back", 0.8), lateral=ar.get("lateral", 0.34), head_frac=ar.get("head_frac", 0.2),
                           place=ar.get("place", 0.4), cross_line=cross_line)
            if self._line is None and not cross_line:
                self.line(ar["over"], ar["on"], side=self._side_of_pair(fr[0], ar["over"], ar["on"]))
                out = self._keep_line(out, False)
            return out
        a = None
        subs = fr.args.get("a"), fr.args.get("b")
        if self._line is None:
            on = fr.args.get("on")
            seq = [x for x in (on if isinstance(on, (list, tuple)) else [on]) if x is not None]
            if len(seq) >= 2:
                self.line(seq[0], seq[1])
            elif subs[0] is not None and subs[1] is not None:
                self.line(subs[0], subs[1])
        if self._line is None:
            raise ValueError("reverse: this framing has no two subjects; declare the line of action first with cam.line(a, b)")
        if self._line["side"] is None:
            self._line["side"] = self._side_of(fr[0])
        mid = (self._line["a"] + self._line["b"]) / 2
        d = (self._line["b"] - self._line["a"])
        d.z = 0
        d.normalize()

        def refl(p):
            k = (p - mid).dot(d)
            return Vector((p.x - 2 * k * d.x, p.y - 2 * k * d.y, p.z))
        return Framing(refl(fr[0]), refl(fr[1]), fr[2], fr.fstop, fr.roll, None, "reverse", fr.size, fr.args)

    def _side_of_pair(self, pos, a, b) -> int:
        pa, pb = self._pt(a, bpy.context.scene.frame_current), self._pt(b, bpy.context.scene.frame_current)
        return 1 if (pb.x - pa.x) * (pos.y - pa.y) - (pb.y - pa.y) * (pos.x - pa.x) >= 0 else -1

    def low_hero(self, on, size: str = "full", high: float = -14.0, side: float = 0.0, lens: float = 26.0, fill: float | None = None, cross_line: bool = False) -> Framing:
        """A low camera looking up at someone: power, pride, threat. high = degrees looking up (negative)."""
        fr = self.frame(on, size, side, high, lens, fill, 0.46)
        fr = Framing(*fr, fstop=5.0, roll=0.0, kind="low_hero", size=size, args={"on": on})
        return self._keep_line(fr, cross_line)

    def insert(self, on, side: float = 8.0, high: float = 16.0, lens: float | None = None, fill: float | None = None) -> Framing:
        """A close look at an object (a ring, a note, a hand): size 'insert'."""
        fr = self.frame(on, "insert", side, high, lens, fill, 0.44)
        return Framing(*fr, fstop=fr.fstop, kind="insert", size="insert", args={"on": on})

    def profile(self, on, size: str = "medium", side: str = "right", high: float = 4.0, facing=None, cross_line: bool = False) -> Framing:
        """The camera square to where someone faces (their profile). facing: a direction vector or degrees; default: the actor's
        .facing, else its stage turned from -Y. side="right"/"left": which side of them the camera is on."""
        who = self._who(on if not isinstance(on, (list, tuple)) else on[0])
        if facing is None:
            fv = self._facing(on if not isinstance(on, (list, tuple)) else on[0])
        elif isinstance(facing, (int, float)):
            a = math.radians(facing)
            fv = Vector((-math.sin(a), math.cos(a), 0))
        else:
            fv = Vector(facing)
            fv.z = 0
            fv = fv.normalized()
        n = fv.cross(UP).normalized()
        if side == "left":
            n = -n
        az = math.degrees(math.atan2(n.x, -n.y))
        fr = self.frame(on, size, az, high)
        fr = Framing(*fr, fstop=fr.fstop, kind="profile", size=size, args={"on": on})
        return self._keep_line(fr, cross_line)

    def _fit(self, pts, to_cam: Vector, lens: float, margin: float, right_hint: Vector | None = None):
        """Smallest distance from the middle of pts, along to_cam, at which every point lies inside the frame (minus margin)."""
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = (lo + hi) / 2
        f = -to_cam.normalized()
        r = f.cross(UP)
        if r.length < 0.02:
            r = f.cross(right_hint if right_hint is not None else Vector((0, 1, 0)))
        r.normalize()
        u = r.cross(f).normalized()
        fv, fh = self.fov(lens)
        tv, th = math.tan(fv / 2), math.tan(fh / 2)
        lim = 1.0 - 2 * margin
        a, b = 0.3, 600.0
        for _ in range(60):
            d = (a + b) / 2
            ok = True
            for p in pts:
                rel = p - c
                zd = d + rel.dot(to_cam.normalized())
                if zd < 0.1:
                    ok = False
                    break
                if abs(rel.dot(r)) / (zd * th) > lim or abs(rel.dot(u)) / (zd * tv) > lim:
                    ok = False
                    break
            if ok:
                b = d
            else:
                a = d
        return c, b

    def establish(self, where, side: float = -15.0, high: float = 20.0, lens: float = 24.0, margin: float = 0.07, why: str = "") -> Framing:
        """A wide that fits the whole place. where: the set's marks (a dict name -> point/object, the set builder's MARK), a list of
        things, or bounds ((x0, y0, z0), (x1, y1, z1)). Picks the closest camera at that angle with everything inside the frame."""
        if isinstance(where, dict):
            things = list(where.values())
        elif isinstance(where, (list, tuple)) and len(where) == 2 and all(isinstance(q, (list, tuple, Vector)) and len(q) == 3 for q in where) \
                and all(isinstance(v, (int, float)) for q in where for v in q):
            lo, hi = Vector(where[0]), Vector(where[1])
            things = [lo, hi]
        else:
            things = list(where) if isinstance(where, (list, tuple)) else [where]
        lo, hi = self._subject_box(things, "wide")
        pts = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        az, el = math.radians(side), math.radians(high)
        to_cam = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
        c, d = self._fit(pts, to_cam, lens, margin)
        pos = c + to_cam * d
        pos.z = max(pos.z, 0.5)
        return Framing(pos, c, lens, 8.0, 0.0, None, "establish", "wide", {"where": where})

    def top_down(self, on, height: float | None = None, lens: float = 35.0, margin: float = 0.08, heading: float = 0.0, cross_line: bool = False) -> Framing:
        """Straight down on the subjects (the map view: geography, a chase, a plan). height: metres above them (default: the
        nearest height at which they fill the frame with the lens given). heading: degrees the picture is turned (0 = +Y is up the frame)."""
        lo, hi = self._subject_box(on, "full")
        c = (lo + hi) / 2
        hint = Vector((math.sin(math.radians(heading)), math.cos(math.radians(heading)), 0))
        if height is None:
            pts = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
            _c, d = self._fit(pts, Vector((0, 0, 1)), lens, margin, hint)
            height = d
        pos = c + Vector((0, 0, height))
        self._hint = hint
        return Framing(pos, c, lens, 8.0, 0.0, None, "top_down", "wide", {"on": on, "heading": heading})

    # ------------------------------------------------------------------ the automatic drift
    def _drift(self, i: int, fe: int):
        """The automatic slow drift of view i (keys from its first frame to fe) if it is held for more than 1.2 s with no move of its own."""
        v = self._views[i]
        if v.get("drift_applied") or v.get("explicit_moves") or v.get("still") or v.get("drift") is False or v.get("drift") == 0:
            return
        cfg = core.STYLE.get("camera", {})
        fs = v["frame"]
        if fs not in self._samples or (fe - fs + 1) / self.shot.fps <= 1.2:
            return
        p0 = self._samples[fs].copy()
        opt = v.get("drift")
        amt = float(opt) if isinstance(opt, (int, float)) and not isinstance(opt, bool) else float(cfg.get("drift_default", 0.03))
        direction = opt if isinstance(opt, str) else None
        if direction is None:
            direction = ("right" if i % 2 == 0 else "left") if v.get("size") == "wide" else "in"
        dist = (p0.aim - p0.pos).length
        fwd = (p0.aim - p0.pos).normalized()
        rr = fwd.cross(UP)
        rr = rr.normalized() if rr.length > 0.02 else Vector((1, 0, 0))
        shift = {"right": rr * (amt * 1.6 * dist), "left": -rr * (amt * 1.6 * dist), "up": UP * (amt * dist), "down": -UP * (amt * dist)}.get(direction)
        if shift is not None:
            p1 = Pose(p0.pos + shift, p0.aim + shift, p0.lens, p0.fstop, p0.roll, None if p0.focus is None else p0.focus + shift)
        else:
            k = 1.0 + amt if direction == "out" else 1.0 - amt
            p1 = Pose(p0.aim + (p0.pos - p0.aim) * k, p0.aim, p0.lens, p0.fstop, p0.roll, p0.focus)
        n = fe - fs
        for f in list(range(fs + 2, fe, 2)) + [fe]:
            pose = p0.lerp(p1, EASES["ease_in"]((f - fs) / n))
            old = self._samples.get(f)
            if old is not None:                                    # a rack focus laid over this view stays
                pose.focus, pose.fstop = (None if old.focus is None else old.focus.copy()), old.fstop
            self._put(f, pose, "LINEAR")
        v["drift_applied"] = direction
        self._record("drift", fs, fe, p0, p1, amt, "ease_in", v["id"], auto=True, direction=direction)
        self.moves.sort(key=lambda m: (m["t0"], m["t1"]))

    def finish(self):
        """Give the last view its drift (earlier views get theirs when the next one starts). Called for you when the views are read."""
        if self._finishing or not self._views or self._pose is None:
            return
        self._finishing = True
        try:
            self._drift(len(self._views) - 1, self.shot.frames)
        finally:
            self._finishing = False

    # ------------------------------------------------------------------ measuring
    def _pt(self, target, f: int) -> Vector:
        """World position of a point, object or actor at frame f (evaluated there if it moves)."""
        if _is_live(target):
            core.at_frame(f)
        if hasattr(target, "stage") and not hasattr(target, "point"):
            target = target.stage
        return core.point_of(target)

    def project(self, point, frame: int | None = None):
        """World point -> (x, y, depth): x, y are 0..1 from the bottom-left of the frame; depth in metres (negative = behind)."""
        from bpy_extras.object_utils import world_to_camera_view
        sc = bpy.context.scene
        if frame is not None and sc.frame_current != frame:
            core.at_frame(frame)
        v = world_to_camera_view(sc, self.ob, Vector(point))
        return v.x, v.y, v.z


def _arc_spline(nodes, mark: int, per: int = 48):
    """A centripetal Catmull-Rom curve through the nodes, as a table of (arclength fraction, point), and the arclength fraction of nodes[mark]."""
    pts = [Vector(n) for n in nodes]
    ext = [pts[0] * 2 - pts[1], *pts, pts[-1] * 2 - pts[-2]]
    table, acc, mark_len = [(0.0, pts[0].copy())], 0.0, 0.0
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length, 1e-6) ** 0.5
        t2 = t1 + max((p2 - p1).length, 1e-6) ** 0.5
        t3 = t2 + max((p3 - p2).length, 1e-6) ** 0.5
        for k in range(1, per + 1):
            t = t1 + (t2 - t1) * k / per
            a1 = p0 * ((t1 - t) / (t1 - t0)) + p1 * ((t - t0) / (t1 - t0))
            a2 = p1 * ((t2 - t) / (t2 - t1)) + p2 * ((t - t1) / (t2 - t1))
            a3 = p2 * ((t3 - t) / (t3 - t2)) + p3 * ((t - t2) / (t3 - t2))
            b1 = a1 * ((t2 - t) / (t2 - t0)) + a2 * ((t - t0) / (t2 - t0))
            b2 = a2 * ((t3 - t) / (t3 - t1)) + a3 * ((t - t1) / (t3 - t1))
            c = b1 * ((t2 - t) / (t2 - t1)) + b2 * ((t - t1) / (t2 - t1))
            acc += (c - table[-1][1]).length
            table.append((acc, c))
        if i == mark:
            mark_len = acc
    total = max(acc, 1e-9)
    return [(a / total, p) for a, p in table], mark_len / total


def _arc_at(table, frac: float) -> Vector:
    """The point at an arclength fraction of a table from _arc_spline."""
    if frac <= 0.0:
        return table[0][1].copy()
    if frac >= 1.0:
        return table[-1][1].copy()
    lo, hi = 0, len(table) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if table[mid][0] <= frac:
            lo = mid
        else:
            hi = mid
    a, b = table[lo], table[hi]
    k = (frac - a[0]) / max(b[0] - a[0], 1e-12)
    return a[1].lerp(b[1], k)


def _is_live(target) -> bool:
    """Does this thing move during the shot (an actor, or an object with animation on it or its parents)?"""
    if target is None or isinstance(target, (Vector, tuple, list)):
        return False
    if hasattr(target, "stage") or hasattr(target, "point"):
        return True
    ob = target
    while ob is not None:
        if getattr(ob, "animation_data", None) and (ob.animation_data.action or ob.animation_data.drivers):
            return True
        if getattr(ob, "constraints", None) and len(ob.constraints):
            return True
        ob = getattr(ob, "parent", None)
    return False
