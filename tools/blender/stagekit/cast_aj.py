"""cast_aj - the Aj characters (packs/aj_rebuild_v1: Mixamo-rigged, drawn mouth, real fingers) as pipeline actors.

    a = cast.actor("tom", "TeenBoy", at=(0, -2), face="right", view="3q")     # cast.actor dispatches here for an Aj
    a.do("wave", t=0.5); a.expr("happy", 0.4); a.speak("Hello", "there")      # the same API as every 3D actor

An Aj actor is a stagekit.cast3d.Actor3D whose figure is the pack's own body, clothes and hair, APPENDED (never linked;
the pack file is only read) and renamed per actor, with its own body mesh, shape keys and skin material (so two Aj have
two faces and two mouths). stagekit.aj_rig builds the control joints the Actor3D code animates and binds the real
bones to them. Only what must differ for a real skeleton is overridden here:

  arms      the elbow only flexes (the hinge follows the forearm); a forearm twist turns the palm to what it touches;
            the collar shrugs and comes forward with the arm (aj_rig.apply_collars at _finalize); reaches land the
            PALM (not the wrist) on the target, with the moved shoulder taken into account
  legs      measured thigh / shin lengths and rest angles (seniors stand with bent knees); a kneel points the feet back
  body      lean over three spine joints, head tilt and turn over neck and head; breathing lifts the collars a little
  face      config/aj_face.json: expressions -> brow / lid shape keys + a mouth cell, visemes -> mouth cells (aj_face)
  hands     six shapes on the finger bones; hold() solves a real grip on the prop when one fits (aj_hands)
  spots     hands go to points measured ON the skin or the clothes (library/characters/aj/bodies/<body>.json)

Not here yet (later tasks): motion clips (play_clip), the Aj wardrobe (wear), a casting command.
"""
from __future__ import annotations

import fnmatch
import json
import math
import random
import re
from types import SimpleNamespace

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from . import aj_face, aj_hands, aj_rig, cast3d, core
from .cast3d import ARM_REST

FAMILY = "aj"
HEAD_MARKS = ("chin", "mouth", "brow", "forehead", "ear", "cheek", "top", "nape", "beside_face")
PALM_HINTS = {   # pose -> side -> the way the palm faces (upper body space); poses not listed keep the natural turn
    "wave": {"R": (0.0, -1.0, 0.15), "L": (0.0, -1.0, 0.15)},
    "hands_up": {"R": (0.0, -1.0, 0.0), "L": (0.0, -1.0, 0.0)},
    "cheer": {"R": (0.0, -1.0, 0.0), "L": (0.0, -1.0, 0.0)},
    "shrug": {"R": (0.0, -0.3, 1.0), "L": (0.0, -0.3, 1.0)},
    "stop": {"R": (0.0, -1.0, 0.0), "L": (0.0, -1.0, 0.0)},
}
TWIST_MAX = math.radians(100.0)
SKIN_GAP = 0.012           # metres between the palm skin and the skin or cloth it rests on
_CAST = None


# ----------------------------------------------------------------------------------------------- the cast data
def cast_data() -> dict:
    global _CAST
    if _CAST is None:
        _CAST = json.loads((core.PROJECT / "config" / "cast.json").read_text(encoding="utf-8"))
    return _CAST


def entry(base: str) -> dict | None:
    """The cast entry for an Aj character ('TeenBoy') or a bare body ('Male_Teen' / 'Aj_Male_Teen'), else None."""
    d = cast_data()
    ch = d.get("characters", {}).get(base)
    if ch and ch.get("family") == FAMILY:
        return dict(ch, name=base)
    b = base[3:] if base.startswith("Aj_") else base
    body = d.get("bodies", {}).get(b)
    if body and body.get("family", FAMILY) == FAMILY:
        return {"name": base, "family": FAMILY, "body": b, "file": body["file"], "era": ["modern"], "height_m": None, "bare": True}
    return None


def has(base: str) -> bool:
    return entry(base) is not None


def family() -> dict:
    return cast_data().get("families", {}).get(FAMILY, {})


def measured(body: str) -> dict:
    from ajkit import paths
    p = paths.MEASURED / f"{body}.json"
    if not p.exists():
        raise FileNotFoundError(f"{p} is missing: run tools/chars_aj/measure_bodies.py")
    return json.loads(p.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------------------------- appending
def _append(path, coll, dressed: bool):
    """Append the armature, the body and (dressed) the D_* clothes and hair. Images the scene already has are shared."""
    have = {im.name for im in bpy.data.images}
    want = {"Armature", "Aj_Base_Body"}
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in want or (dressed and n.startswith("D_"))]
    obs = [o for o in dst.objects if o is not None]
    for o in obs:
        coll.objects.link(o)
    for im in list(bpy.data.images):
        if im.name in have:
            continue
        base = re.sub(r"\.\d{3}$", "", im.name)
        twin = bpy.data.images.get(base)
        if twin is not None and twin is not im and twin.name in have and tuple(twin.size) == tuple(im.size):
            im.user_remap(twin)
            bpy.data.images.remove(im)
    return obs


def _own_key_drivers(body):
    """After a mesh copy the shape-key drivers still read the OLD key: point them at this body's own key."""
    key = body.data.shape_keys
    if not key or not key.animation_data:
        return
    for fc in key.animation_data.drivers:
        for v in fc.driver.variables:
            for tg in v.targets:
                if tg.id_type == "KEY" and tg.id is not None and tg.id != key:
                    tg.id = key


def _ev(ob, path, index, f, default):
    for fc in core.fcurves(ob):
        if fc.data_path == path and fc.array_index == index:
            return fc.evaluate(f)
    return default


# ----------------------------------------------------------------------------------------------- the actor
class ActorAj(cast3d.Actor3D):
    family = FAMILY

    def __init__(self, cid: str, base: str, ent: dict, scale: float = 1.0):
        from ajkit import paths
        self.id, self.base, self.sheet = cid, base, {"face": {}, "label": base}
        self.entry = ent
        self.shot = core.current()
        self.coll = core.collection(f"CAST_{cid}")
        m = measured(ent["body"])
        self.meas = m
        self.b = b = dict(m["b"])
        self.dressed = not ent.get("bare")
        self.marks = m["landmarks"]["dressed" if self.dressed and "dressed" in m["landmarks"] else "bare"]
        root = bpy.data.objects.new(f"{cid}.j.root", None)
        root.empty_display_size = 0.05
        self.coll.objects.link(root)
        ctrl = bpy.data.objects.new(f"{cid}.ctrl", None)
        ctrl.empty_display_size = 0.02
        self.coll.objects.link(ctrl)
        ctrl.parent = root
        ctrl.hide_render = True
        for e in cast3d.fig3d.EXPRS:
            ctrl[e] = 0.0
        for v in cast3d.fig3d.VISEMES:
            ctrl[f"viseme_{v}"] = 0.0
        for k in ("blink", "look_x", "look_z", "breath"):
            ctrl[k] = 0.0
        for s in "LR":
            for h in cast3d.fig3d.HAND_SHAPES[1:]:
                ctrl[f"hand_{s}_{h}"] = 0.0
        self.root, self.ctrl = root, ctrl
        aj_face.setup(self)
        # the figure
        path = paths.PACK / ent["file"]
        obs = _append(path, self.coll, self.dressed)
        arm = next(o for o in obs if o.type == "ARMATURE")
        body = next(o for o in obs if o.name.startswith("Aj_Base_Body"))
        self.parts = {}
        for o in obs:
            if o.type != "MESH":
                continue
            if o.parent is None:
                bpy.context.view_layer.update()
                o.parent = arm
                o.matrix_parent_inverse = arm.matrix_world.inverted()
            role = "body" if o is body else re.sub(r"\.\d{3}$", "", o.name)[2:].lower()
            o.name = f"{cid}.{role}"
            self.parts[role] = o
        arm.name, arm.data.name = f"{cid}.rig", f"{cid}.rig"
        if body.data.users > 1:
            body.data = body.data.copy()
        body.data.name = f"{cid}.body"
        _own_key_drivers(body)
        self._skin_mat = None
        for slot in body.material_slots:
            if slot.material and slot.material.name.startswith("Aj_Skin_MAT"):
                if slot.material.users > 1:
                    slot.material = slot.material.copy()
                slot.material.name = f"{cid}.skin"
                self._skin_mat = slot.material
        self.rig, self.mesh = arm, body
        self.J, self.W, _ref = aj_rig.build(self, arm, body)
        self.fig = SimpleNamespace(robe=False, parts={}, coll=self.coll, waist=b["hip_z"], torso_r=self._torso_r, eye={})
        # the rest of Actor3D's state
        self.scale = float(scale)
        self.stage = core.empty(cid, (0, 0, 0), "CAST", 0.3)
        self.tilt = core.empty(f"{cid}.tilt", (0, 0, 0), "CAST", 0.1)
        self.tilt.parent = self.stage
        root.parent = self.tilt
        root.location = (0, 0, 0)
        root.scale = (self.scale,) * 3
        self._face, self._view = 1, "3q"
        self._stage_yaw, self._rel = 0.0, 0.0
        self._olog = []
        self._pos = Vector((0, 0, 0))
        self._held, self._airborne = {}, []
        self._arm = {"L": ARM_REST, "R": ARM_REST}
        self._elbow = {"L": 0.0, "R": 0.0}
        self._hinge = {"L": Vector((1, 0, 0)), "R": Vector((1, 0, 0))}
        self._tw = {"L": 0.0, "R": 0.0}
        self._wflex = {"L": 0.0, "R": 0.0}
        self._want = {"L": None, "R": None}
        self._grip_layers = []
        self._q = {}
        self._sink = (0.0, 0.0)
        self.floating = False
        self.body = {"legs": True, "gait": "walk"}         # what the actions read: legs and gait
        self._fc = {}
        self.height = float(b["height"]) * self.scale
        self.head_z, self.head_r = b["head_z"], b["R"]
        self._hips_rest = self.J["hips"].location.copy()
        lg = m["legs"]["L"]
        self.leg1, self.leg2 = lg["L1"], lg["L2"]
        self._a1, self._a2, self._ankle_fwd = lg["a1"], lg["a2"], lg["ankle_fwd"]
        self._poff = {s: Vector(m["palm"][s]["point"]) for s in "LR"}
        self._pn = {s: Vector(m["palm"][s]["normal"]).normalized() for s in "LR"}
        self.palm = {}
        for s in "LR":
            e = bpy.data.objects.new(f"{cid}.palm.{s}", None)
            e.empty_display_size = 0.02
            self.coll.objects.link(e)
            e.parent = self.J[f"wr.{s}"]
            e.location = self._poff[s]
            e.hide_render = True
            self.palm[s] = e
        self.head = self._anchor("head", "head", (0, b["head_y"], b["head_z"]))
        ch = self.marks.get("chest", {}).get("at", (0, -0.08, b["hip_z"] + 0.7 * (b["neck_z"] - b["hip_z"])))
        self.chest = self._anchor("chest", "torso", (0, ch[1] + 0.06, ch[2]))
        self.feet = self._anchor("feet", "root", (0, 0, 0))
        self.top = self._anchor("top", "head", (0, b["head_y"], b["head_top"]))
        self.hand_anchor = {s: cast3d.cast2d.Anchor(self, self.palm[s]) for s in "LR"}
        for s in "LR":
            self._set_arm(s, self._dirs(s, *ARM_REST), None, 0.0)
        self.shot.actors[cid] = self
        self.shot.subject(cid, self.head)

    def _anchor(self, name, joint, model):
        e = bpy.data.objects.new(f"{self.id}.{name}", None)
        e.empty_display_size = 0.04
        self.coll.objects.link(e)
        e.parent = self.J[joint]
        e.location = Vector(model) - self.W[joint]
        e.hide_render = True
        return cast3d.cast2d.Anchor(self, e)

    def _torso_r(self, z):
        prof = self.b["torso"]
        if not prof:
            return 0.15
        if z <= prof[0][1]:
            return prof[0][0]
        for (w0, z0), (w1, z1) in zip(prof, prof[1:]):
            if z0 <= z <= z1:
                return w0 + (w1 - w0) * (z - z0) / max(1e-6, z1 - z0)
        return prof[-1][0]

    def set_scale(self, s: float):
        self.scale = float(s)
        self.root.scale = (self.scale,) * 3
        self.height = float(self.b["height"]) * self.scale
        return self

    # ------------------------------------------------------------------ arms
    def _frame(self, side, u, w, want=None, hinge_prev=None):
        """(q_sh, th, tau, hand rotation, hinge) for an upper arm along u and a forearm along w (torso space): the
        elbow only flexes; tau turns the forearm so the palm faces `want` (when given) within its range."""
        h = w.cross(u)
        if h.length < 0.05:
            hp = hinge_prev if hinge_prev is not None else self._hinge[side]
            h = hp - u * hp.dot(u)
            if h.length < 1e-4:
                h = Vector((1, 0, 0)) - u * u.x
        h.normalize()
        z = -u
        y = z.cross(h).normalized()
        m = Matrix((h, y, z)).transposed()
        wl = m.transposed() @ w
        th = math.atan2(wl.y, -wl.z)
        R_el = m @ Matrix.Rotation(th, 3, "X")
        tau = 0.0
        if want is not None:
            v = R_el.transposed() @ Vector(want).normalized()
            n = self._pn[side]
            if math.hypot(v.x, v.y) > 1e-3:
                tau = math.atan2(v.y, v.x) - math.atan2(n.y, n.x)
                tau = (tau + math.pi) % math.tau - math.pi
                tau = max(-TWIST_MAX, min(TWIST_MAX, tau))
        R_hand = R_el @ Matrix.Rotation(tau, 3, "Z")
        return m.to_quaternion(), th, tau, R_hand, h

    def _set_arm(self, side, dirs, t, blend):
        u, w = dirs
        want = self._want.get(side)
        q, th, tau, _R, h = self._frame(side, u, w, want)
        self._hinge[side] = h
        self._elbow[side] = th
        self._tw[side] = tau
        qe = Quaternion((1, 0, 0), th) @ Quaternion((0, 0, 1), 0.6 * tau)
        qw = Quaternion((0, 0, 1), 0.4 * tau) @ Quaternion((1, 0, 0), math.radians(-self._wflex[side]))
        for jn, qq in ((f"sh.{side}", q), (f"el.{side}", qe), (f"wr.{side}", qw)):
            ob = self.J[jn]
            prev = self._q.get(jn)
            if prev is not None and qq.dot(prev) < 0:
                qq = -qq
            self._q[jn] = qq.copy()
            self._key(ob, "rotation_quaternion", t, blend, qq)

    def _shoulder(self, side, u):
        return aj_rig.shoulder_point(self, side, aj_rig.collar_rotation(side, u, 0.0))

    def _solve(self, side, target_local, elbow="auto"):
        """Two-bone arm that puts the PALM on a point in the upper body's space, with the shoulder where the collar
        will carry it -> (upper arm, forearm) directions."""
        s = 1.0 if side == "L" else -1.0
        L1, L2 = self.b["arm1"], self.b["arm2"]
        want = self._want.get(side)
        q0 = self._q.get(f"sh.{side}")
        u = aj_rig.arm_dir(q0) if q0 is not None else Vector((0, 0, -1))
        wr_t = Vector(target_local) - self._poff[side] * 0.0
        pole = {"up": Vector((s * 0.5, 0.1, 1.0)), "down": Vector((s * 0.25, 0.25, -1.0))}.get(elbow, Vector((s * 0.90, 0.10, -0.45)))
        hp = self._hinge[side].copy()
        w = u
        palm_off = None
        for _ in range(5):
            S = self._shoulder(side, u)
            if palm_off is not None:
                wr_t = Vector(target_local) - palm_off
            d = wr_t - S
            dist = max(abs(L1 - L2) + 0.01, min(L1 + L2 - 0.002, d.length))
            dn = d.normalized() if d.length > 1e-6 else Vector((0, 0, -1))
            perp = pole - dn * pole.dot(dn)
            if perp.length < 1e-4:
                perp = Vector((s, 0, 0)) - dn * dn.x
            perp.normalize()
            a = (L1 * L1 + dist * dist - L2 * L2) / (2 * dist)
            hgt = math.sqrt(max(0.0, L1 * L1 - a * a))
            E = S + dn * a + perp * hgt
            T = S + dn * dist
            u, w = (E - S).normalized(), (T - E).normalized()
            _q, _th, _tau, R_hand, hp = self._frame(side, u, w, want, hp)
            palm_off = R_hand @ self._poff[side]
        return u, w

    def reach(self, side: str, target, t: float, blend: float = 0.3, elbow: str = "auto"):
        """Put the palm exactly on a world point, an object or an anchor at time t; the palm turns toward it."""
        p = core.point_of(target)
        local = self._torso_inv(self._f(t)) @ p
        S = self._shoulder(side, Vector((0, -0.7, -0.7)).normalized())
        if self._want.get(side) is None:
            self._want[side] = (local - S).normalized()
            dirs = self._solve(side, local, elbow)
            self._set_arm(side, dirs, t, blend)
            self._want[side] = None
        else:
            self._set_arm(side, self._solve(side, local, elbow), t, blend)
        self._arm[side] = (70.0, 30.0, "fwd")
        return self

    def aim(self, side: str, target, t: float, blend: float = 0.25, bend: float = 6.0):
        """Point the arm at a target (palm down)."""
        p = core.point_of(target)
        local = self._torso_inv(self._f(t)) @ p
        S = self._shoulder(side, (local - Vector(self.J[f"sh.{side}"].location)).normalized())
        d = (local - S).normalized()
        w = (d + Vector((0, 0, math.sin(math.radians(bend))))).normalized()
        self._want[side] = Vector((0, 0, -1))
        self._set_arm(side, (d, w), t, blend)
        self._want[side] = None
        self._arm[side] = (88.0, bend, "fwd")
        return self

    def _wag(self, side: str, deg: float, t: float, blend: float = 0.12):
        qe = Quaternion((1, 0, 0), self._elbow[side] + math.radians(deg)) @ Quaternion((0, 0, 1), 0.6 * self._tw[side])
        self._key(self.J[f"el.{side}"], "rotation_quaternion", t, blend, qe)
        return self

    def wrist(self, side: str, deg: float, t: float = 0.0, blend: float = 0.15):
        self._wflex[side] = float(deg)
        qw = Quaternion((0, 0, 1), 0.4 * self._tw[side]) @ Quaternion((1, 0, 0), math.radians(-deg))
        self._key(self.J[f"wr.{side}"], "rotation_quaternion", t, blend, qw)
        return self

    def arm(self, side: str, raise_deg: float, bend_deg: float = 0.0, t: float = 0.0, blend: float = 0.25, plane: str = "fwd"):
        self._set_arm(side, self._dirs(side, raise_deg, bend_deg, plane), t, blend)
        self._arm[side] = (raise_deg, bend_deg, plane)
        return self

    # ------------------------------------------------------------------ places on the body
    def _head_rot(self, f):
        """The head's turn relative to the upper body at frame f (neck then head, from their keys)."""
        R = Matrix.Identity(3)
        for jn in ("neck", "head"):
            ob = self.J[jn]
            e = Euler([_ev(ob, "rotation_euler", i, f, ob.rotation_euler[i]) if f is not None else ob.rotation_euler[i] for i in range(3)])
            R = R @ e.to_matrix()
        return R

    def spot_normal(self, side, name):
        mk = self.marks.get("ear" if name == "beside_face" else name) or self.marks["chest"]
        n = Vector(mk["n"])
        if side == "R":
            n.x = -n.x
        return n

    def spot(self, side: str, name: str, dx: float = 0.0, dz: float = 0.0, frame: int | None = None) -> Vector:
        """A named place on the figure's own body (on the skin or the clothes, measured), in the upper body's space:
        where the palm should be to touch it. Head places follow the head's tilt and turn at `frame`."""
        s = 1.0 if side == "L" else -1.0
        key = "ear" if name == "beside_face" else name
        if key == "cross":
            mk = self.marks.get("cross")
        else:
            mk = self.marks.get(key) or self.marks["chest"]
        at, n = Vector(mk["at"]), Vector(mk["n"])
        if side == "R":
            at.x, n.x = -at.x, -n.x
        if name == "cross":
            at.z += 0.0 if side == "L" else -0.05
        p = at + n * SKIN_GAP
        if key in ("mouth", "chin"):
            p.z -= 0.3 * self.b["hand_r"]                   # the palm centre a little low: the fingers reach up over the lips
        if name == "beside_face":
            p = at + Vector((s * 0.06, -0.35 * self.b["R"], -0.02))
        p += Vector((s * dx, 0.0, dz))
        if key in HEAD_MARKS:
            W = self.W
            R = self._head_rot(frame)
            rel = (W["neck"] - W["torso"]) + R @ (p - W["neck"])
            return rel
        return p - self.W["torso"]

    def pose(self, name_or_spec, t: float = 0.0, blend: float = 0.25, side: str | None = None):
        if isinstance(name_or_spec, str) and name_or_spec not in cast3d.cast2d.POSES:
            raise KeyError(f"unknown pose {name_or_spec!r}. Poses: {', '.join(cast3d.cast2d.POSES)}")
        pname = name_or_spec if isinstance(name_or_spec, str) else None
        if pname:
            spec = dict(cast3d.POSE3D.get(pname, cast3d.cast2d.POSES[pname]))
        else:
            spec = dict(name_or_spec)
        spec.pop("views", None)
        hints = dict(PALM_HINTS.get(pname, {}))
        if side and side != "R" and "R" in spec and "L" not in spec:
            spec["L"] = spec.pop("R")
            if isinstance(spec.get("hands"), dict):
                spec["hands"] = {("L" if k == "R" else k): v for k, v in spec["hands"].items()}
            if "R" in hints:
                hints = {"L": hints["R"]}
        f = self._f(t)
        # the head first: hand spots on the head follow its tilt
        if "lean" in spec:
            self.lean(spec["lean"], t, blend)
        if "tilt" in spec:
            self.tilt_head(spec["tilt"], t, blend)
        for s in "LR":
            if s not in spec:
                continue
            a = spec[s]
            if a == "rest" or a is None:
                self.arm(s, *ARM_REST[:2], t, blend, plane=ARM_REST[2])
            elif a[0] == "to":
                local = self.spot(s, a[1], *(a[2:4] if len(a) > 2 else ()), frame=f)
                n = self.spot_normal(s, a[1])
                if a[1] in HEAD_MARKS:
                    n = self._head_rot(f) @ n
                self._want[s] = -n
                self._set_arm(s, self._solve(s, local), t, blend)
                self._want[s] = None
                self._arm[s] = (60.0, 60.0, "fwd")
            else:
                if s in hints:
                    v = Vector(hints[s])
                    if s == "R":
                        v.x = -v.x
                    self._want[s] = v
                self.arm(s, a[0], a[1], t, blend, plane=a[2] if len(a) > 2 else "fwd")
                self._want[s] = None
        if "legs" in spec:
            self.legs(spec["legs"][0], spec["legs"][1], t, blend)
        h = spec.get("hands")
        if isinstance(h, str):
            h = {"L": h, "R": h}
        for s, shape in (h or {}).items():
            if not self._grips(s):
                self.hand(s, shape, t, min(blend, 0.12))
        return self

    # ------------------------------------------------------------------ body
    def lean(self, deg: float, t: float = 0.0, blend: float = 0.3):
        for jn, k in (("spine", 0.30), ("spine1", 0.35), ("torso", 0.35)):
            self._key(self.J[jn], "rotation_euler", t, blend, math.radians(deg * k), index=0)
        return self

    def tilt_head(self, deg: float, t: float = 0.0, blend: float = 0.2):
        for jn, k in (("neck", 0.35), ("head", 0.65)):
            self._key(self.J[jn], "rotation_euler", t, blend, math.radians(deg * k), index=0)
        return self

    def head_turn(self, amount: float, t: float = 0.0, blend: float = 0.12):
        for jn, k in (("neck", 0.35), ("head", 0.65)):
            self._key(self.J[jn], "rotation_euler", t, blend, math.radians(38.0 * amount * k) * self._face, index=2)
        return self

    def squash(self, t: float, amount: float = 0.14, hold: float = 0.08, recover: float = 0.18):
        """A landing or a start as a real body does it: a quick dip at the knees and back (no stretching: a non-uniform
        scale over the rig shears the bones away from their joints, 27 mm at a 3.5% squash). Skipped while the legs
        are already bent (sitting, kneeling)."""
        if getattr(self, "_legs_now", (0.0, 0.0)) != (0.0, 0.0) or self.floating:
            return self
        r = 60.0 * amount
        self.legs(r, 2.0 * r, t, 0.06)
        self.legs(r, 2.0 * r, t + hold, hold)
        self.legs(0.0, 0.0, t + hold + recover, recover)
        return self

    # ------------------------------------------------------------------ legs
    def _solve_leg(self, df, du):
        """(thigh, knee) values for the hip / knee joints that put the ankle `df` ahead of and `du` above the hip
        (native metres), measured from the rest pose: the legs' rest angles are taken out."""
        L1, L2 = self.leg1, self.leg2
        df = df + self._ankle_fwd
        d = max(0.06, min(L1 + L2 - 0.002, math.hypot(df, du)))
        a = math.atan2(df, -du)
        ch = max(-1.0, min(1.0, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)))
        ck = max(-1.0, min(1.0, (L1 * L1 + L2 * L2 - d * d) / (2 * L1 * L2)))
        p1 = a + math.acos(ch)
        p2 = p1 - (math.pi - math.acos(ck))
        th = p1 - self._a1
        return th, th - (p2 - self._a2)

    def _sink_for(self, raise_deg, bend_deg):
        p1 = self._a1 + math.radians(raise_deg)
        p2 = self._a2 + math.radians(raise_deg - bend_deg)
        b = self.b
        ext = max(self.leg1 * math.cos(p1) + self.leg2 * math.cos(p2) + b["ankle_z"], self.leg1 * math.cos(p1) + b["r_kn"], b["r_hip"])
        return max(0.0, b["leg_z"] - ext)

    def _foot_point(self, raise_deg, bend_deg):
        """extra ankle turn (degrees) that points the foot back along a shin that lies on the floor (a kneel)"""
        shin = bend_deg - raise_deg
        k = max(0.0, min(1.0, (shin - 45.0) / 40.0))
        k = k * k * (3 - 2 * k)
        return k * 62.0

    def legs(self, raise_deg: float, bend_deg: float, t: float = 0.0, blend: float = 0.3, side: str = "LR", ground: bool = True):
        """Thighs forward by raise_deg, knees folded by bend_deg (from the standing pose); the body sinks so the feet
        or the knees stay on the ground on every frame; a kneel points the feet back."""
        if not (ground and side == "LR"):
            for s in side:
                for jn, v in ((f"hip.{s}", -raise_deg), (f"kn.{s}", bend_deg), (f"an.{s}", raise_deg - bend_deg + self._foot_point(raise_deg, bend_deg))):
                    self._key(self.J[jn], "rotation_euler", t, blend, math.radians(v), index=0)
            return self
        r0, b0 = getattr(self, "_legs_now", (0.0, 0.0))
        f1 = self._f(t)
        f0 = self._f0(t, blend) if blend > 0 else f1
        n = max(1, f1 - f0)
        for k in range(0 if f0 < f1 else 1, n + 1):
            u = k / n
            u = u * u * (3 - 2 * u)
            r, bd = r0 + (raise_deg - r0) * u, b0 + (bend_deg - b0) * u
            f = f0 + k if f0 < f1 else f1
            for s in "LR":
                for jn, v in ((f"hip.{s}", -r), (f"kn.{s}", bd), (f"an.{s}", r - bd + self._foot_point(r, bd))):
                    self.J[jn].rotation_euler.x = math.radians(v)
                    self.J[jn].keyframe_insert("rotation_euler", index=0, frame=f)
            sink = self._sink_for(r, bd)
            self.J["hips"].location.z = self._hips_rest.z - sink
            self.J["hips"].keyframe_insert("location", index=2, frame=f)
        self._legs_now = (raise_deg, bend_deg)
        sink = self._sink_for(raise_deg, bend_deg)
        self._sink = (sink * self.scale, sink * self.scale)
        return self

    # ------------------------------------------------------------------ face
    EXPR = {e: None for e in aj_face.names()}

    def expr(self, name: str, t: float = 0.0, blend: float = 0.12, amount: float = 1.0):
        """The whole face: brows, lids and the drawn mouth (config/aj_face.json). neutral, happy, laugh, grin, excited,
        surprised, worried, scared, angry, sad, weeping, crying, sly, sleepy, wink."""
        cfg = aj_face.config()
        name = cfg["aliases"].get(name, name)
        if name not in cfg["expressions"]:
            raise ValueError(f"unknown expression {name!r}: use one of {tuple(cfg['expressions'])}")
        for e in cfg["expressions"]:
            if e == name:
                v = amount if e != "neutral" else 1.0
            elif e == "neutral":
                v = 1.0 - amount
            else:
                v = 0.0
            self._ckey(f"x_{e}", t, blend, v)
        self._expr_now = name
        return self

    def _blink_keys(self, frames):
        for fr, v in frames:
            self.ctrl["blink"] = float(v)
            self.ctrl.keyframe_insert('["blink"]', frame=max(1, fr))

    def blink(self, t: float):
        f = self._f(t)
        self._blink_keys([(f - 2, 0.0), (f, 1.0), (f + 1, 1.0), (f + 4, 0.0)])
        return self

    def eyes_closed(self, t0: float, t1: float):
        f0, f1 = self._f(t0), max(self._f(t0) + 3, self._f(t1))
        self._blink_keys([(f0 - 1, 0.0), (f0 + 1, 1.0), (f1 - 1, 1.0), (f1 + 2, 0.0)])
        return self

    def eyes(self, dx: float = 0.0, dz: float = 0.0, t: float = 0.0, blend: float = 0.1):
        """Where the eyes look: dx +1 = toward the facing side, -1 = back; dz +1 = up, -1 = down."""
        self._ckey("look_x", t, blend, max(-1.0, min(1.0, dx)) * self._face)
        self._ckey("look_z", t, blend, max(-1.0, min(1.0, dz)))
        return self

    # ------------------------------------------------------------------ props
    def hold(self, prop, side: str = "R", t: float = 0.0, offset=(0.0, 0.0, 0.0), front: bool = True, grip: bool = True, turn: bool = False):
        """From time t the prop goes with the hand (rigidly, turning with it, when a grip was solved or turn=True;
        otherwise it only follows, so a cup stays upright). A prop the hand is already at stays where it is (no jump)
        and the fingers close on its real surface when the grip solver can read it (a handle, a small thing); a prop
        far from the hand is put into the palm (offset: metres, x toward the facing side, y depth, z up)."""
        f = self._f(t)
        if prop.name in self._held:
            self._drop_holds(prop, f)
        self._prepare(f + 1)
        sc = bpy.context.scene
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        palm_w = self.palm[side].evaluated_get(dg).matrix_world.translation.copy()
        P0 = prop.evaluated_get(dg).matrix_world.copy()
        near = (P0.translation - palm_w).length < 0.12 * max(0.6, self.scale)
        angles, rep = (None, "grip=False")
        if grip:
            angles, rep = aj_hands.solve_grip(self, prop, side, f)
            if angles is not None and near and rep["moved_cm"] > 2.5:
                # the hand is not quite where the grip wants it: move the palm by the difference and solve again
                hb0 = self.rig.matrix_world @ self.rig.pose.bones[aj_rig.P + ("Left" if side == "L" else "Right") + "Hand"].matrix
                shift = P0.translation - (hb0 @ rep["rel"]).translation
                self.reach(side, palm_w + shift, t, 0.0)
                self._prepare(f + 1)
                a2, r2 = aj_hands.solve_grip(self, prop, side, f)
                if a2 is not None:
                    angles, rep = a2, r2
        sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        wr = self.J[f"wr.{side}"].evaluated_get(dg).matrix_world
        hb = self.rig.matrix_world @ self.rig.pose.bones[aj_rig.P + ("Left" if side == "L" else "Right") + "Hand"].matrix
        tgt = bpy.data.objects.new(f"{self.id}.hold.{prop.name}", None)
        tgt.empty_display_size = 0.02
        tgt.hide_render = True
        self.coll.objects.link(tgt)
        tgt.parent = self.J[f"wr.{side}"]
        tgt.rotation_mode = "QUATERNION"
        if angles is not None:
            grip_w = hb @ rep["rel"]                          # where the solver put the prop in this hand
        elif near:
            grip_w = P0
        else:
            ofs = Vector((offset[0] * self._face, offset[1], offset[2]))
            grip_w = Matrix.Translation(palm_w + ofs) @ P0.to_3x3().normalized().to_4x4()
        start_w = P0 if near else grip_w
        inv = wr.inverted()
        keys = [(f, start_w)]
        if start_w is not grip_w:                            # the prop settles into the grip over a quarter second
            keys.append((f + max(1, int(0.25 * self.shot.fps)), grip_w))
        for fr, Mw in keys:
            L = inv @ Mw
            tgt.location = L.translation
            tgt.rotation_quaternion = L.to_quaternion().normalized()
            if len(keys) > 1:
                tgt.keyframe_insert("location", frame=fr)
                tgt.keyframe_insert("rotation_quaternion", frame=fr)
        cons = []
        rigid = angles is not None or turn                    # a solved grip (or turn=True) turns with the hand;
        for kind in ("COPY_LOCATION", "COPY_ROTATION")[:2 if rigid else 1]:   # a plain hold keeps a cup upright
            c = prop.constraints.new(kind)
            c.target = tgt
            cons.append(c)
        for c in cons:
            c.influence = 0.0
            if f > 1:
                c.keyframe_insert("influence", frame=f - 1)
            c.influence = 1.0
            c.keyframe_insert("influence", frame=f)
        self._held[prop.name] = (cons, tgt, side, dict(offset=offset, front=front, grip=grip, turn=rigid))
        if angles is not None:
            self._grip_layers.append({"side": side, "f0": f, "f1": 10 ** 7, "ramp": 3, "angles": angles, "prop": prop.name})
        elif grip:
            self.hand(side, "grip", t, 0.06)
            self.shot.notes.append(f"{self.id}: hold {prop.name} with the plain grip shape ({rep})")
        return self

    def release(self, prop, t: float, hand: str | None = "open"):
        f = self._f(t)
        for L in self._grip_layers:
            if L["prop"] == prop.name and L["f1"] > f:
                L["f1"] = f
        return cast3d.Actor3D.release(self, prop, t, hand)

    def _prepare(self, upto: int):
        """Make the scene show the arms (collars included) as keyed so far: needed before measuring a hand."""
        frames = list(range(1, max(2, upto) + 1))
        aj_rig.apply_collars(self, frames)

    # ------------------------------------------------------------------ life
    def idle(self, t0: float = 0.0, t1: float | None = None, seed: int | None = None, breathe: float = 1.0):
        t1 = self.shot.seconds if t1 is None else t1
        rnd = random.Random(seed if seed is not None else hash(self.id) % 9973)
        t = t0 + rnd.uniform(0.6, 1.8)
        while t < t1 - 0.2:
            self.blink(t)
            t += rnd.uniform(1.9, 3.6)
        if breathe > 0:
            period = rnd.uniform(2.6, 3.4)
            n = max(1, int((t1 - t0) / (period / 2)))
            for i in range(n + 1):
                self.ctrl["breath"] = float(breathe * (i % 2))
                self.ctrl.keyframe_insert('["breath"]', frame=self._f(t0 + i * period / 2))
        return self

    # ------------------------------------------------------------------ costume
    def recolor(self, **colors):
        """Recolour clothes and hair by part: top, pants, shoes, hair (a '#rrggbb' each). The texture's light and
        shade stay; its colour is replaced."""
        for role, hexc in colors.items():
            ob = self.parts.get(role)
            if ob is None:
                self.shot.notes.append(f"{self.id}: recolor {role}: {self.base} has no part '{role}' (it has {', '.join(sorted(self.parts))})")
                continue
            rgba = core.hex_rgba(hexc)
            for slot in ob.material_slots:
                mt = slot.material
                if mt is None or not mt.use_nodes:
                    continue
                if mt.users > 1:
                    mt = slot.material = mt.copy()
                nt = mt.node_tree
                bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
                if bsdf is None:
                    continue
                inp = bsdf.inputs["Base Color"]
                if not inp.is_linked:
                    inp.default_value = rgba
                    continue
                mix = nt.nodes.get("aj_recolor")
                if mix is None:
                    src = inp.links[0].from_socket
                    mix = nt.nodes.new("ShaderNodeMix")
                    mix.name = "aj_recolor"
                    mix.data_type = "RGBA"
                    mix.blend_type = "COLOR"
                    mix.inputs[0].default_value = 1.0
                    nt.links.new(src, mix.inputs[6])
                    nt.links.new(mix.outputs[2], inp)
                mix.inputs[7].default_value = rgba
        return self

    def hide(self, *patterns):
        hit = False
        for role, ob in self.parts.items():
            if role == "body":
                continue
            if any(fnmatch.fnmatchcase(role, p) or fnmatch.fnmatchcase(ob.name, p) for p in patterns):
                ob.hide_render = ob.hide_viewport = True
                hit = True
        if not hit:
            self.shot.notes.append(f"{self.id}: hide{patterns} matched no part of {self.base} (parts: {', '.join(sorted(self.parts))})")
        return self

    def wear(self, item: str, **opts):
        raise NotImplementedError(f"{self.id}: wear({item!r}) - the Aj wardrobe is not built yet (a later task). "
                                  "Use one of the dressed Aj characters, recolor() and hide() for now.")

    def play_clip(self, name: str, t0: float, groups=("legs", "spine", "arm.L", "arm.R", "head"), rate: float = 1.0, blend: float = 0.3):
        raise NotImplementedError(f"{self.id}: play_clip({name!r}) - motion clips on Aj actors are a later task; "
                                  "walk() uses the procedural gait for now.")

    def head_box(self, view=None):
        return 0.0, self.b["head_z"], self.b["R"]

    def torso_box(self, view=None):
        b = self.b
        z0 = b["hip_z"] - 0.08
        hw = max((p[0] for p in b["torso"] if p[1] >= z0), default=0.15)
        return 0.0, z0, b["neck_z"], hw

    def add_part(self, *a, **k):
        raise NotImplementedError(f"{self.id}: flat drawn parts do not go on an Aj actor")

    add_flat = add_part

    # ------------------------------------------------------------------ the end of the build
    def _frames(self):
        sc = bpy.context.scene
        end = max(sc.frame_end, self.shot.f(self.shot.seconds))
        return list(range(1, end + 1))

    def _finalize(self):
        """Headings from the real camera (Actor3D), then the collars, the face and the fingers, one key per frame."""
        cast3d.Actor3D._finalize(self)
        fr = self._frames()
        aj_rig.apply_collars(self, fr)
        aj_face.bake(self, fr)
        aj_hands.bake(self, fr)


def actor(cid: str, base: str, at=(0, 0), face: str = "right", view: str = "3q", scale: float = 1.0, costume: dict | None = None) -> ActorAj:
    """Bring an Aj character (config/cast.json, family "aj") or a bare Aj body on stage. Its size: height_m from the
    cast entry when given, otherwise the family's world_scale (0.90) of the pack's own size; `scale` multiplies that."""
    ent = entry(base)
    if ent is None:
        raise KeyError(f"no Aj character or body '{base}'")
    m = measured(ent["body"])
    k = float(family().get("world_scale", 0.90))
    if ent.get("height_m"):
        k = float(ent["height_m"]) / float(m.get("b_dressed", m["b"])["height"])
    a = ActorAj(cid, base, ent, k * float(scale))
    a.place(at)
    a._face = 1 if str(face).lower().startswith("r") else -1
    a.view(view)
    a.pose("rest", 0.0, 0.0)
    if costume:
        if costume.get("hide"):
            a.hide(*costume["hide"])
        if costume.get("recolor"):
            a.recolor(**costume["recolor"])
        for w in costume.get("wear", []) or []:
            w = dict(w)
            a.wear(w.pop("item"), **w)
    return a
