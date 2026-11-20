"""stagekit.camera - one camera per shot, keyed in seconds: position, aim, lens, focus and background blur.

A shot is one continuous take. Inside it the camera can hold, dolly, crane, pan/tilt (by moving the aim), zoom the
lens a little, and shift focus. Every move eases in and out. One move at a time; a move needs a story reason.

    cam = camera.Camera(lens=50, blur="medium")
    cam.at(0.0, pos=(0, -6.5, 1.5), aim=dad.head, focus=dad.head)   # opening frame
    cam.at(7.0, pos=(0, -3.8, 1.55))                                 # slow dolly in over 7 s (everything else holds)
    cam.rack(8.2, boy.head, duration=0.7)                            # focus shift: attention moves without a cut
    cam.hold(9.0)                                                    # stay put until 9.0 ...
    cam.at(12.0, pos=(1.2, -4.2, 2.4), aim=(0, 0, 1.0))              # ... then crane up and across

Blur is asked for by what the viewer should notice, not by f-stop:
    none | light | medium | strong | macro   ->  the kit solves the f-stop for the lens and focus distance,
and never lets the sharp zone get thinner than the subject's head.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import core

# far-background blur disc as a fraction of the frame height
BLUR = {"none": 0.0, "light": 0.004, "medium": 0.010, "strong": 0.020, "macro": 0.035}
SENSOR_MM = 36.0
SHARP_COC = 0.0011          # blur (fraction of frame height) still read as sharp
MIN_SHARP_DEPTH = 0.34      # metres that must stay sharp around the focus point (a head and a bit)


class Camera:
    def __init__(self, lens: float = 50.0, blur: str = "medium", name: str = "CAM"):
        shot = core.current()
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.sensor_width = SENSOR_MM
        cd.sensor_fit = "AUTO"
        cd.clip_start, cd.clip_end = 0.05, 400.0
        self.ob = bpy.data.objects.new(name, cd)
        core.link(self.ob, "RIG")
        bpy.context.scene.camera = self.ob
        self.aim = core.empty(f"{name}_aim", coll="RIG")
        self.focus = core.empty(f"{name}_focus", coll="RIG")
        tr = self.ob.constraints.new("TRACK_TO")
        tr.target = self.aim
        tr.track_axis = "TRACK_NEGATIVE_Z"
        tr.up_axis = "UP_Y"
        cd.dof.use_dof = blur != "none"
        cd.dof.focus_object = self.focus
        cd.dof.aperture_blades = 0
        self.blur = blur
        self._pos = None
        self._aim = None
        self._focus = None
        self._lens = float(lens)
        self._focus_follow = None
        self.keys: list[dict] = []
        shot.camera = self

    # ------------------------------------------------------------------ keys
    def _pt(self, target, t):
        if hasattr(target, "point") or hasattr(target, "matrix_world"):
            bpy.context.scene.frame_set(core.current().f(t))
        return core.point_of(target)

    def at(self, t: float, pos=None, aim=None, lens: float | None = None, focus=None, blur: str | None = None, linear: bool = False):
        """Key the camera at time t. Anything you leave out keeps its last value, so two calls describe one move.
        pos: where the camera is. aim: what it looks at (point, object, or character anchor like actor.head).
        focus: what is sharp (defaults to the aim on the first key). lens: focal length in mm. blur: change the blur level."""
        first = self._pos is None
        if first and (pos is None or aim is None):
            raise ValueError("the first camera key needs pos and aim")
        if pos is not None:
            self._pos = Vector(pos)
        if aim is not None:
            self._aim = self._pt(aim, t)
        if focus is not None:
            self._focus_follow = None
            self._focus = self._pt(focus, t)
        elif first:
            self._focus = self._aim.copy()
        if lens is not None:
            self._lens = float(lens)
        if blur is not None:
            self.blur = blur
            self.ob.data.dof.use_dof = True
        core.key(self.ob, "location", t, self._pos, linear=linear)
        core.key(self.aim, "location", t, self._aim, linear=linear)
        if self._focus_follow is None:
            core.key(self.focus, "location", t, self._focus, linear=linear)
        core.key(self.ob.data, "lens", t, self._lens, linear=linear)
        self._key_fstop(t)
        self.keys.append({"t": t, "pos": tuple(self._pos), "aim": tuple(self._aim), "lens": self._lens, "blur": self.blur})
        return self

    def hold(self, t: float):
        """Repeat the current framing at t: the camera stays still until here, and the next key starts a move from here."""
        return self.at(t)

    def push(self, t0: float, t1: float, amount: float = 0.12):
        """Dolly toward the aim by a fraction of the distance (0.05-0.15 is felt but not noticed; 0.3+ is a statement)."""
        self.hold(t0)
        return self.at(t1, pos=self._pos + (self._aim - self._pos) * amount)

    def pull(self, t0: float, t1: float, amount: float = 0.15):
        """Dolly away from the aim: reveal context, isolation, release."""
        self.hold(t0)
        return self.at(t1, pos=self._pos - (self._aim - self._pos) * amount)

    def rack(self, t: float, target, duration: float = 0.6):
        """Shift focus to another subject, finishing at t. A cut without cutting: use it when the story's attention
        moves between two things already in frame."""
        self._focus_follow = None
        core.key(self.focus, "location", max(0.0, t - duration), self._focus)
        self._focus = self._pt(target, t)
        core.key(self.focus, "location", t, self._focus)
        self._key_fstop(max(0.0, t - duration), prev=True)
        self._key_fstop(t)
        return self

    def follow(self, target, t0: float = 0.0, t1: float | None = None, aim: bool = True, focus: bool = True, lag: float = 0.0, offset=(0, 0, 0)):
        """Keep a moving subject framed and sharp between t0 and t1 (baked every 2 frames).
        lag 0..1 lets the subject lead in frame a little (0.3 feels like an operator, 0 is locked on)."""
        shot = core.current()
        sc = bpy.context.scene
        t1 = shot.seconds if t1 is None else t1
        f0, f1 = shot.f(t0), shot.f(t1)
        prev = None
        off = Vector(offset)
        for f in list(range(f0, f1, 2)) + [f1]:
            sc.frame_set(f)
            p = core.point_of(target) + off
            if prev is not None and lag > 0:
                p = prev.lerp(p, 1.0 - lag)
            prev = p.copy()
            if aim:
                self.aim.location = p
                self.aim.keyframe_insert("location", frame=f)
                self._aim = p.copy()
            if focus:
                self.focus.location = core.point_of(target)
                self.focus.keyframe_insert("location", frame=f)
                self._focus = self.focus.location.copy()
        return self

    def track(self, target, t0: float, t1: float, keep_offset: bool = True):
        """Travel WITH a moving subject: the camera keeps its offset from the subject between t0 and t1 (walk-and-follow)."""
        shot = core.current()
        sc = bpy.context.scene
        f0, f1 = shot.f(t0), shot.f(t1)
        sc.frame_set(f0)
        base = core.point_of(target)
        self.hold(t0)
        cam0 = self._pos.copy()
        for f in list(range(f0, f1, 2)) + [f1]:
            sc.frame_set(f)
            p = core.point_of(target)
            self.ob.location = cam0 + (p - base)
            self.ob.keyframe_insert("location", frame=f)
            self.aim.location = p
            self.aim.keyframe_insert("location", frame=f)
            self.focus.location = p
            self.focus.keyframe_insert("location", frame=f)
        self._pos, self._aim, self._focus = self.ob.location.copy(), self.aim.location.copy(), self.focus.location.copy()
        return self

    # ------------------------------------------------------------------ blur
    def fstop_for(self, blur: str, lens_mm: float, focus_m: float) -> float:
        b = BLUR[blur]
        f, s = lens_mm, max(0.2, focus_m) * 1000.0
        if b <= 0:
            return 22.0
        n = f * f / (b * s * SENSOR_MM)
        n_min = MIN_SHARP_DEPTH * 1000.0 * f * f / (2.0 * SHARP_COC * SENSOR_MM * s * s)   # keep a head sharp
        return round(max(0.35, n, n_min), 3)

    def _key_fstop(self, t: float, prev: bool = False):
        if self._pos is None or self._focus is None:
            return
        d = (self._focus - self._pos).length
        n = self.fstop_for(self.blur, self._lens, d)
        core.key(self.ob.data.dof, "aperture_fstop", t, n)

    # ------------------------------------------------------------------ queries used by checks
    def project(self, point, frame: int | None = None):
        """World point -> (x, y) in frame fractions (0,0 = bottom-left, 1,1 = top-right) and depth in metres."""
        from bpy_extras.object_utils import world_to_camera_view
        sc = bpy.context.scene
        if frame is not None:
            sc.frame_set(frame)
        bpy.context.view_layer.update()
        v = world_to_camera_view(sc, self.ob, Vector(point))
        return v.x, v.y, v.z
