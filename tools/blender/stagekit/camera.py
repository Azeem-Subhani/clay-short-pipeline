"""stagekit.camera - one camera per shot, showing the staged action through views.

A view is what the viewer is given to look at for a few seconds: a framing chosen because the story needs it now.
The camera reaches a new view by a cut, or by travelling there (a whip, a push, a follow). Inside a view it can hold
or drift a little. Every time is seconds from the start of the shot; key them to words with shot.t("phrase").

    cam = camera.Camera()
    cam.view("ring_drops", 0.0, on=[queen, ring], size="medium", side=-25)          # framed for you around the subjects
    cam.push(0.0, 2.0, 0.08)                                                        # lean in while she gasps
    cam.view("ring_sinks", shot.t("into the deep"), on=[ring], size="insert", high=35)   # a cut to the object
    cam.follow(ring, shot.t("into the deep"), shot.t("pond", edge="end"))           # the camera travels with it
    cam.view("wide", shot.t("Bring it back"), pos=(0, -9, 2.2), aim=(0, 2, 1.0), lens=28)   # or place it by hand
    cam.view("gate", shot.t("At the far end"), on=[P["gate"]], size="full", travel=0.35)    # travel= moves instead of cutting

Framing keeps the subject in the upper-middle of the 9:16 frame: the caption line sits at 70% down and the Shorts UI
covers the bottom and right edge. `size`: "insert" (an object), "close" (a face), "medium" (waist up, hands in frame),
"full" (whole figure with room), "wide" (the place, figures small).
"""
from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector

from . import core

SENSOR = 36.0
SIZES = {  # fraction of the frame HEIGHT the subject's height should fill, default lens, f-stop
    "insert": (0.30, 60, 2.8), "close": (0.36, 60, 2.8), "medium": (0.46, 45, 4.0), "full": (0.56, 38, 5.6), "wide": (0.34, 28, 8.0),
}


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
        self.views: list[dict] = []
        self.keys: list[dict] = []
        self._last = None                      # (pos, aim, lens)
        for a in self.shot.actors.values():
            a._billboard(self.ob)

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
        (0.40 keeps faces above the captions). shift: slide the subject sideways in frame, -0.5 .. 0.5."""
        frac, dlens, _f = SIZES[size]
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
        return pos, aim, lens

    # ------------------------------------------------------------------ keys
    def _write(self, f: int, pos, aim, lens, interp=None, fstop=None):
        pos, aim = Vector(pos), Vector(aim)
        self.ob.location = pos
        d = aim - pos
        e = d.to_track_quat("-Z", "Y").to_euler("XYZ")
        if self.keys:
            e.make_compatible(Euler(self.keys[-1]["rot"]))
        self.ob.rotation_euler = e
        self.focus.location = aim
        self.data.lens = lens
        if fstop:
            self.data.dof.aperture_fstop = fstop
        for ob, path in ((self.ob, "location"), (self.ob, "rotation_euler"), (self.focus, "location"), (self.data, "lens"), (self.data.dof, "aperture_fstop")):
            if ob is self.data.dof:
                self.data.keyframe_insert("dof.aperture_fstop", frame=f)
                continue
            ob.keyframe_insert(path, frame=f)
        if interp:
            self._interp(f, interp)
        self.keys.append({"frame": f, "t": round((f - 1) / self.shot.fps, 3), "pos": tuple(round(v, 3) for v in pos), "aim": tuple(round(v, 3) for v in aim),
                          "rot": tuple(e), "lens": lens})
        self._last = (pos.copy(), aim.copy(), lens)

    def _interp(self, f: int, kind: str):
        for ob in (self.ob, self.focus, self.data):
            for fc in core.fcurves(ob):
                for kp in fc.keyframe_points:
                    if abs(kp.co.x - f) < 0.5:
                        kp.interpolation = kind
                        if kind not in ("CONSTANT", "LINEAR"):
                            kp.easing = "EASE_IN_OUT"

    def _pull_back(self, f: int):
        """A cut needs the old framing to END on the frame before it. If the last key (the end of a push or move) sits on
        or after the cut frame, slide it one frame earlier instead of letting it blend into the new view."""
        last = self.keys[-1]
        old = last["frame"]
        if old < f:
            return
        new = f - 1
        if len(self.keys) > 1 and self.keys[-2]["frame"] >= new:
            new = self.keys[-2]["frame"] + 1
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

    def view(self, vid: str, t: float, on=None, size: str = "medium", side: float = 0.0, high: float = 6.0, pos=None, aim=None, lens: float | None = None,
             fill: float | None = None, place: float = 0.40, shift: float = 0.0, travel: float = 0.0, why: str = "", subject=None):
        """Start a view at time t. By default it is a CUT. travel=0.3 makes the camera fly there in 0.3 s instead (a whip:
        use it inside one place to carry the eye from one thing to the next; cut when the place or time jumps).
        Frame it with on=[things] + size/side/high, or by hand with pos= and aim=. why: the story reason (kept for review)."""
        f = self.shot.f(t)
        core.at_frame(f)
        p, a, l = self._resolve(pos, aim, lens, on, size, side, high, fill, place, shift)
        fstop = SIZES.get(size, (0, 0, 5.6))[2]
        if self.keys:
            if self.keys[-1]["frame"] >= f and f > 1:
                self._pull_back(f)
            prev = self.keys[-1]
            if travel > 0:
                f0 = max(prev["frame"] + 1, self.shot.f(t - travel))
                if f0 > prev["frame"]:
                    self._write(f0, prev["pos"], prev["aim"], prev["lens"])        # hold the old view until the move starts
                self._interp(f0, "SINE")
            else:
                if f - 1 > prev["frame"]:
                    self._write(f - 1, prev["pos"], prev["aim"], prev["lens"])
                self._interp(self.keys[-1]["frame"], "CONSTANT")
        self._write(f, p, a, l, fstop=fstop)
        self.views.append({"id": vid, "t": round(float(t), 3), "frame": f, "size": size if (on is not None or size != "medium") else "manual", "cut": travel <= 0,
                           "why": why, "on": [getattr(s, "id", getattr(s, "name", str(s))) for s in (on if isinstance(on, (list, tuple)) else [on])] if on is not None else []})
        self.shot.views = self.views
        return self

    def move(self, t0: float, t1: float, on=None, size: str = "medium", side: float = 0.0, high: float = 6.0, pos=None, aim=None, lens: float | None = None,
             fill: float | None = None, place: float = 0.40, shift: float = 0.0, ease: str = "SINE"):
        """Inside the current view: hold until t0, then travel to a new framing, arriving at t1 (reveal, tilt, track, crane)."""
        f0, f1 = self.shot.f(t0), self.shot.f(t1)
        prev = self.keys[-1]
        if f0 > prev["frame"]:
            self._write(f0, prev["pos"], prev["aim"], prev["lens"])
        self._interp(self.keys[-1]["frame"], ease)
        core.at_frame(f1)
        p, a, l = self._resolve(pos, aim, lens, on, size, side, high, fill, place, shift)
        self._write(max(f1, self.keys[-1]["frame"] + 1), p, a, l)
        return self

    def push(self, t0: float, t1: float, amount: float = 0.08):
        """Slow lean in (amount = fraction of the distance; negative pulls back). Gives a held view life and weight."""
        pos, aim, lens = self._last
        self.move(t0, t1, pos=aim + (pos - aim) * (1.0 - amount), aim=aim, lens=lens)
        return self

    def hold(self, t: float):
        """Keep the current framing exactly until t (a line landing, the last image)."""
        prev = self.keys[-1]
        f = self.shot.f(t)
        if f > prev["frame"]:
            self._interp(prev["frame"], "LINEAR")
            self._write(f, prev["pos"], prev["aim"], prev["lens"])
        return self

    def follow(self, target, t0: float, t1: float, keep: str = "offset", every: int = 2, lag: float = 0.0):
        """Travel with a moving thing from t0 to t1 (a falling ring, a thrown net, a walker).
        keep="offset": the camera keeps its distance and angle to the target; keep="aim": it stays put and turns to watch."""
        f0, f1 = self.shot.f(t0), self.shot.f(t1)
        prev = self.keys[-1]
        if f0 > prev["frame"]:
            self._write(f0, prev["pos"], prev["aim"], prev["lens"])
        pos0, aim0, lens = self._last
        core.at_frame(f0)
        start = core.point_of(target)
        off_p, off_a = pos0 - start, aim0 - start
        f = f0 + every
        while f <= f1:
            core.at_frame(max(f0, f - int(lag * self.shot.fps)))
            p = core.point_of(target)
            self._interp(self.keys[-1]["frame"], "LINEAR")
            if keep == "offset":
                self._write(f, p + off_p, p + off_a, lens)
            else:
                self._write(f, pos0, p + off_a, lens)
            f += every
        return self

    def shake(self, t: float, amount: float = 0.04, dur: float = 0.35):
        """A short jolt on an impact (a splash, a slam). amount in metres."""
        import random
        rnd = random.Random(int(t * 100))
        pos, aim, lens = self._last
        n = max(3, int(dur * self.shot.fps / 2))
        f = self.shot.f(t)
        if f > self.keys[-1]["frame"]:
            self._write(f, pos, aim, lens)
        for i in range(1, n + 1):
            k = amount * (1 - i / n)
            j = Vector((rnd.uniform(-k, k), 0, rnd.uniform(-k, k)))
            self._interp(self.keys[-1]["frame"], "LINEAR")
            self._write(f + 2 * i, pos + j, aim + j * 0.6, lens)
        self._write(f + 2 * n + 1, pos, aim, lens)
        return self

    def project(self, point, frame: int | None = None):
        """World point -> (x, y, depth): x, y are 0..1 from the bottom-left of the frame; depth in metres (negative = behind)."""
        from bpy_extras.object_utils import world_to_camera_view
        sc = bpy.context.scene
        if frame is not None and sc.frame_current != frame:
            core.at_frame(frame)
        v = world_to_camera_view(sc, self.ob, Vector(point))
        return v.x, v.y, v.z

    def view_at(self, frame: int) -> dict | None:
        cur = None
        for v in self.views:
            if v["frame"] <= frame:
                cur = v
        return cur
