"""cast3d - the 3D cast. One real model per character (stagekit.fig3d) that answers the SAME commands as the flat 2D
cast (stagekit.cast): pose, arm, reach, hold, walk, expr, speak, do("action") ... so shot files and the action library
do not change. The difference is what the camera may do: it can go anywhere round the figure, nothing is ever swapped.

    queen = cast.actor("queen", "Queen", at=(0, -3), face="right", view="3q")     # cast.actor builds a 3D actor when the
    queen.do("wave", t=0.5)                                                       # character has a sheet in config/cast3d.json

What `face` and `view` mean here: the figure turns its whole body. view="front" faces the camera, "3q" turns about 40
degrees toward the facing side, "side" turns to profile; face="left" / "right" is that side on screen. The heading is
taken from where the camera stands at that moment and then HELD in the world: when the camera moves on, the figure
does not turn with it.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import cast as cast2d
from . import core, fig3d

VIEW_YAW = {"front": 12.0, "3q": 42.0, "side": 84.0}
ARM_REST = (12.0, 4.0, "out")
GAITS = {    # per leg length: step, lift; then hips drop, bob, lean, arm swing, swing share of a step, cape, skirt, metres per second at speed 2
    "walk": dict(S=0.60, lift=0.14, drop=0.05, bob=0.028, lean=4.0, arm=24.0, sw=0.80, cape=7.0, skirt=3.0, mps=1.05),
    "run": dict(S=1.02, lift=0.33, drop=0.15, bob=0.08, lean=17.0, arm=52.0, sw=1.12, cape=30.0, skirt=10.0, mps=2.6),
    "sneak": dict(S=0.50, lift=0.30, drop=0.20, bob=0.03, lean=12.0, arm=10.0, sw=0.72, cape=3.0, skirt=2.0, mps=0.55),
}
POSE3D = {   # poses whose flat spec does not describe a body in the round
    "cross_arms": {"L": ("to", "cross"), "R": ("to", "cross"), "lean": -3, "hands": "fist"},
    "wave": {"R": (150, 34, "out"), "hands": {"R": "open"}},
    "carry": {"L": (48, 62), "R": (48, 62), "hands": "fist"},
    "sit": {"L": (30, 40), "R": (30, 40), "legs": (86, 84)},
    "lift": {"L": (120, 30), "R": (120, 30), "lean": -6, "hands": "fist"},
    "hands_up": {"L": (150, 12, "out"), "R": (150, 12, "out"), "hands": "open"},
    "cheer": {"L": (165, -10, "out"), "R": (165, -10, "out"), "lean": -5, "hands": "open"},
    "shrug": {"L": (30, 78, "out"), "R": (30, 78, "out"), "hands": "open", "tilt": 6},
    "hang": {"L": (176, 4, "out"), "R": (176, 4, "out"), "hands": "fist"},
    "throw_back": {"R": (150, 60, "out"), "L": (70, 10), "lean": -14, "hands": {"R": "fist", "L": "open"}},
    "laugh": {"L": (40, 96, "out"), "R": ("to", "belly"), "lean": -12, "tilt": -12, "hands": "open"},
}
_SHEETS = None


def _resolve(name: str, raw: dict, seen=()) -> dict:
    """A sheet as it will be built. A sheet may say "like": "<another character>" and then only what differs:
    colors / recolor (by the pack's colour names) / hide (part-name patterns) / add (flat drawings) / wear (wardrobe) /
    body / face. That is the quick way to make a new character."""
    if "like" not in raw:
        return raw
    if name in seen or raw["like"] not in raw["_all"]:
        raise KeyError(f"3D character '{name}': 'like' points at '{raw['like']}', which is not a character sheet")
    src = raw["_all"][raw["like"]]
    base = copy.deepcopy(_resolve(raw["like"], dict(src, _all=raw["_all"]), seen + (name,)))
    base.pop("_all", None)
    for k in ("label", "looks", "era", "group", "stand_in", "props", "hair", "beard"):
        if k in raw:
            base[k] = raw[k]
    base.setdefault("label", name)
    base["body"].update(raw.get("body", {}))
    base["colors"].update(raw.get("colors", {}))
    base.setdefault("face", {}).update(raw.get("face", {}))
    rec = raw.get("recolor", {})
    for role, key in base.get("keys", {}).items():
        if key in rec:
            base["colors"][role] = rec[key]
    hide = raw.get("hide", [])
    parts = []
    for q in base.get("parts", []):
        if any(fnmatch.fnmatchcase(q["name"], pat) for pat in hide):
            continue
        if q.get("key") in rec:
            q["color"] = rec[q["key"]]
        parts.append(q)
    base["parts"] = parts + list(raw.get("add", []))
    base["wear"] = list(base.get("wear", [])) + list(raw.get("wear", []))
    base["from"] = f"like {raw['like']}"
    return base


def sheets() -> dict:
    """Every 3D character sheet: config/cast3d.json (converted from the pack) plus config/cast3d_custom.json (made here)."""
    global _SHEETS
    if _SHEETS is None:
        raw = {}
        for fn in ("cast3d.json", "cast3d_custom.json"):
            p = core.PROJECT / "config" / fn
            if p.exists():
                raw.update(json.loads(p.read_text(encoding="utf-8")).get("characters", {}))
        _SHEETS = {n: _resolve(n, dict(v, _all=raw)) for n, v in raw.items()}
        for v in _SHEETS.values():
            v.pop("_all", None)
    return _SHEETS


def has(base: str) -> bool:
    return base in sheets()


class Actor3D:
    is3d = True
    rigs = {"Front": None}                                     # the wardrobe draws once, in the front view; the figure makes it 3D
    HAND_SHAPES = fig3d.HAND_SHAPES

    # shared with the 2D actor: they only use the stage / tilt / ctrl that both have
    _f = cast2d.Actor._f
    _f0 = cast2d.Actor._f0
    position = cast2d.Actor.position
    place = cast2d.Actor.place
    speak = cast2d.Actor.speak
    ctrl_pulse = cast2d.Actor.ctrl_pulse
    chew = cast2d.Actor.chew
    do = cast2d.Actor.do
    rock = cast2d.Actor.rock
    shake = cast2d.Actor.shake
    hop = cast2d.Actor.hop
    move = cast2d.Actor.move
    _grips = cast2d.Actor._grips

    def __init__(self, cid: str, base: str, sheet: dict, scale: float = 1.0):
        self.id, self.base, self.sheet = cid, base, sheet
        self.shot = core.current()
        self.coll = core.collection(f"CAST_{cid}") if hasattr(core, "collection") else None
        self.fig = fig3d.Fig(sheet, cid, self.coll)
        f = self.fig
        self.J, self.W, self.b = f.J, f.W, f.b
        self.ctrl = f.ctrl
        self.root = f.J["root"]
        self.scale = float(scale)
        self.stage = core.empty(cid, (0, 0, 0), "CAST", 0.3)
        self.tilt = core.empty(f"{cid}.tilt", (0, 0, 0), "CAST", 0.1)
        self.tilt.parent = self.stage
        self.root.parent = self.tilt
        self.root.location = (0, 0, 0)
        self.root.scale = (self.scale,) * 3
        self._face, self._view = 1, "3q"
        self._stage_yaw, self._rel = 0.0, 0.0
        self._olog = []
        self._pos = Vector((0, 0, 0))
        self._held, self._airborne = {}, []
        self._arm = {"L": ARM_REST, "R": ARM_REST}
        self._elbow = {"L": 0.0, "R": 0.0}
        self._hinge = {"L": Vector((1, 0, 0)), "R": Vector((1, 0, 0))}
        self._q = {}
        self._sink = (0.0, 0.0)
        self.floating = False
        self.body = {"legs": True, "gait": "walk"}
        self.parts = []
        self._fc = {}
        self.height = float(self.b.get("height", 1.6)) * self.scale
        self.head_z, self.head_r = self.b["head_z"], self.b["R"]
        self._hips_rest = self.J["hips"].location.copy()
        self.leg1 = self.b["leg_z"] - self.b["knee_z"]
        self.leg2 = self.b["knee_z"] - self.b["ankle_z"]
        self.palm = {}
        for s in "LR":
            e = bpy.data.objects.new(f"{cid}.palm.{s}", None)
            e.empty_display_size = 0.02
            f.coll.objects.link(e)
            e.parent = self.J[f"wr.{s}"]
            e.location = (0, 0, -self.b["hand_r"] * 0.95)
            self.palm[s] = e
        self.head = self._anchor("head", "head", (0, 0, self.b["head_z"]))
        self.chest = self._anchor("chest", "torso", (0, 0, self.b["hip_z"] + 0.68 * (self.b["neck_z"] - self.b["hip_z"])))
        self.feet = self._anchor("feet", "root", (0, 0, 0))
        self.top = self._anchor("top", "head", (0, 0, self.b.get("height", 1.6)))
        self.hand_anchor = {s: cast2d.Anchor(self, self.palm[s]) for s in "LR"}
        for s in "LR":
            self._set_arm(s, self._dirs(s, *ARM_REST), None, 0.0)
        self.shot.actors[cid] = self
        self.shot.subject(cid, self.head)

    # ------------------------------------------------------------------ plumbing
    def _anchor(self, name, joint, model):
        e = bpy.data.objects.new(f"{self.id}.{name}", None)
        e.empty_display_size = 0.04
        self.fig.coll.objects.link(e)
        e.parent = self.J[joint]
        e.location = Vector(model) - self.W[joint]
        return cast2d.Anchor(self, e)

    def _key(self, ob, path, t, blend, value, index=-1):
        if t is None:
            self._setv(ob, path, value, index)
            return
        f1 = self._f(t)
        f0 = self._f0(t, blend) if blend > 0 else f1
        if f0 < f1:
            ob.keyframe_insert(path, frame=f0, index=index)
        self._setv(ob, path, value, index)
        ob.keyframe_insert(path, frame=f1, index=index)

    @staticmethod
    def _setv(ob, path, value, index):
        if index < 0:
            setattr(ob, path, value)
        else:
            getattr(ob, path)[index] = value

    def _ckey(self, prop, t, blend, value):
        p = f'["{prop}"]'
        f1 = self._f(t)
        f0 = self._f0(t, blend) if blend > 0 else f1
        if f0 < f1:
            self.ctrl.keyframe_insert(p, frame=f0)
        self.ctrl[prop] = float(value)
        self.ctrl.keyframe_insert(p, frame=f1)

    def set_scale(self, s: float):
        self.scale = float(s)
        self.root.scale = (self.scale,) * 3
        self.height = float(self.b.get("height", 1.6)) * self.scale
        return self

    def _ink_scale(self):
        return None

    def arm_length(self) -> float:
        return (self.b["arm1"] + self.b["arm2"] + self.b["hand_r"]) * self.scale

    def shoulder_height(self) -> float:
        return self.position().z + self.b["sh_z"] * self.scale

    def hand_point(self, side: str, frame: int | None = None) -> Vector:
        dg = core.at_frame(frame) if frame is not None else bpy.context.evaluated_depsgraph_get()
        return self.palm[side].evaluated_get(dg).matrix_world.translation.copy()

    # ------------------------------------------------------------------ where it faces
    def _cam_yaw(self, frame: int) -> float:
        cam = getattr(self.shot, "camera", None)
        ob = getattr(cam, "ob", None) or bpy.context.scene.camera
        if ob is None:
            return 0.0
        v = [float(c) for c in ob.location]
        for fc in core.fcurves(ob):
            if fc.data_path == "location":
                v[fc.array_index] = fc.evaluate(frame)
        c = Vector(v) - self._pos
        if math.hypot(c.x, c.y) < 1e-6:
            return 0.0
        return math.atan2(c.x, -c.y)

    def _orient(self, t, turn: float = 0.2, world: float | None = None):
        """Turn the body. Without `world` the heading is face / view measured from where the camera stands at time t."""
        self._olog.append((t, turn, world, self._face, self._view))
        return self._apply_orient(t, turn, world)

    def _billboard(self, cam_ob):
        return None                                           # a 3D figure does not turn with the camera

    def _finalize(self):
        """Called once the whole shot is built: headings that were set before the camera views existed are worked out
        again from where the camera really stands at those moments."""
        log, self._olog = list(self._olog), []
        for ob in (self.stage, self.root):
            for fc in core.fcurves(ob):
                if fc.data_path == "rotation_euler" and fc.array_index == 2:
                    for i in range(len(fc.keyframe_points) - 1, -1, -1):
                        fc.keyframe_points.remove(fc.keyframe_points[i])
        face, view = self._face, self._view
        self._stage_yaw = self._rel = 0.0
        self.stage.rotation_euler.z = self.root.rotation_euler.z = 0.0
        for t, turn, world, f_, v_ in log:
            self._face, self._view = f_, v_
            self._apply_orient(t, turn, world)
        self._face, self._view = face, view
        self._olog = log

    def _apply_orient(self, t, turn: float = 0.2, world: float | None = None):
        f1 = self._f(t) if t is not None else 1
        yaw_s = self._cam_yaw(f1) if world is None else self._stage_yaw
        rel = (self._face * math.radians(VIEW_YAW[self._view])) if world is None else (world - self._stage_yaw)
        f0 = self._f0(t, turn) if (t is not None and turn > 0) else f1
        if abs(yaw_s - self._stage_yaw) > 1e-4:
            # the picture frame moved (the camera is somewhere else now): swap frames without the figure moving in the world
            old_world = self._stage_yaw + self._rel
            if t is not None and f0 > 1:
                core.key_frame(self.stage, "rotation_euler", f0 - 1, index=2, interp="CONSTANT")
                core.key_frame(self.root, "rotation_euler", f0 - 1, index=2, interp="CONSTANT")
            self.stage.rotation_euler.z = yaw_s
            self._rel = old_world - yaw_s
            self.root.rotation_euler.z = self._rel
            if t is not None:
                core.key_frame(self.stage, "rotation_euler", f0, index=2, interp="CONSTANT")
                self.root.keyframe_insert("rotation_euler", index=2, frame=f0)
            self._stage_yaw = yaw_s
        while rel - self._rel > math.pi:
            rel -= math.tau
        while rel - self._rel < -math.pi:
            rel += math.tau
        if t is None:
            self.root.rotation_euler.z = rel
        else:
            if f0 < f1:
                self.root.keyframe_insert("rotation_euler", index=2, frame=f0)
            self.root.rotation_euler.z = rel
            self.root.keyframe_insert("rotation_euler", index=2, frame=f1)
        self._rel = rel
        return self

    def face(self, side: str, t: float | None = None):
        """'right' or 'left' on screen: the side the figure turns to and gestures toward."""
        self._face = 1 if str(side).lower().startswith("r") else -1
        return self._orient(t)

    def view(self, name: str, t: float | None = None):
        """How far the figure is turned from the camera: 'front' (to camera), '3q' (the default), 'side' (profile)."""
        self._view = {0: "front", 1: "3q", 2: "side"}[cast2d.VIEW_INDEX[str(name).lower()]]
        return self._orient(t)

    def heading(self, to, t: float | None = None, turn: float = 0.25):
        """Turn to face a world point (x, y) or a compass angle in degrees (0 = toward -Y, 90 = toward +X), whatever the camera."""
        if isinstance(to, (int, float)):
            yaw = math.radians(float(to))
        else:
            d = Vector((to[0] - self._pos.x, to[1] - self._pos.y))
            yaw = math.atan2(d.x, -d.y)
        return self._orient(t, turn, world=yaw)

    def _view_key(self) -> str:
        return "Front"

    def _cull(self, frame=None):
        return None

    # ------------------------------------------------------------------ face
    # expression -> (eye opening, iris size, catch-light size, tears, face controls for the brows and the mouth)
    EXPR = {
        "neutral": ("rest", 1.0, 1.0, None, {}),
        "happy": ("happy", 1.0, 1.0, None, {"happy": 1.0}),
        "laugh": ("joy", 1.0, 1.0, None, {"laugh": 1.0}),
        "grin": ("joy", 1.0, 1.0, None, {"grin": 1.0}),
        "excited": ("wide", 1.12, 1.25, None, {"laugh": 1.0}),
        "surprised": ("wide", 0.72, 0.8, None, {"surprised": 1.0}),
        "worried": ("wide", 0.80, 0.9, None, {"worried": 1.0}),
        "scared": ("wide", 0.70, 0.8, None, {"worried": 1.0, "viseme_O": 0.6}),
        "angry": ("angry", 0.95, 0.8, None, {"angry": 1.0}),
        "sad": ("sad", 1.0, 1.1, None, {"sad": 1.0}),
        "weeping": ("sad", 1.05, 1.5, "drop", {"sad": 1.0}),
        "crying": ("closed", 1.0, 1.0, "stream", {"sad": 1.0, "viseme_A": 0.85}),
        "sly": ("sly", 1.0, 0.9, None, {"sly": 1.0}),
        "sleepy": ("half", 1.0, 0.8, None, {}),
        "wink": ("happy", 1.0, 1.0, None, {"happy": 1.0}),
    }
    EXPR_ALIAS = {"joyful": "laugh", "amazed": "surprised", "gasp": "surprised", "joker": "grin", "smile": "happy"}

    def _kval(self, kb, owner, f):
        for fc in core.fcurves(owner):
            if fc.data_path == f'key_blocks["{kb.name}"].value':
                return fc.evaluate(f)
        return kb.value

    def _eye_node(self, sfx, name, t, blend, value):
        o = self.fig.eye[f"eye.{sfx}"].data.materials[0].node_tree.nodes[name].outputs[0]
        if t is None:
            o.default_value = value
            return
        f1, f0 = self._f(t), self._f0(t, blend)
        if f0 < f1:
            o.keyframe_insert("default_value", frame=f0)
        o.default_value = value
        o.keyframe_insert("default_value", frame=f1)

    def expr(self, name: str, t: float = 0.0, blend: float = 0.12, amount: float = 1.0):
        """The whole face: eyes, lids, brows, mouth, tears. neutral, happy, laugh, grin, excited, surprised, worried, scared,
        angry, sad, weeping (a tear), crying (eyes shut, streaming), sly, sleepy, wink."""
        name = self.EXPR_ALIAS.get(name, name)
        if name not in self.EXPR:
            raise ValueError(f"unknown expression {name!r}: use one of {tuple(self.EXPR)}")
        key, sc, g, tear, ctrl = self.EXPR[name]
        f1, f0 = self._f(t), self._f0(t, blend)
        E = self.fig.eye
        for sfx in "LR":
            k_eye = "joy" if (name == "wink" and sfx == "L") else key
            for part, want in (("eye", k_eye), ("lash", k_eye), ("tear", tear)):
                sk = E[f"{part}.{sfx}"].data.shape_keys
                for kb in sk.key_blocks[1:]:
                    if f0 < f1:
                        kb.value = self._kval(kb, sk, f0)
                        kb.keyframe_insert("value", frame=f0)
                    kb.value = amount if kb.name == want else 0.0
                    kb.keyframe_insert("value", frame=f1)
            self._eye_node(sfx, "sc", t, blend, 1.0 + (sc - 1.0) * amount)
            self._eye_node(sfx, "g", t, blend, 1.0 + (g - 1.0) * amount)
        for k in list(fig3d.EXPRS) + [f"viseme_{v}" for v in fig3d.VISEMES]:
            if k.startswith("viseme_") and k not in ctrl and not any(k in c for c in (self.EXPR[self._expr_now][4],)):
                continue                                      # leave the speaking mouth alone unless this face uses it
            self._ckey(k, t, blend, float(ctrl.get(k, 0.0)) * amount)
        self._expr_now = name
        return self

    _expr_now = "neutral"

    def _lids(self, frames):
        """key the eyes shut for [(frame, shut?)...]; open frames restore whatever the expression had there"""
        for sfx in "LR":
            for part in ("eye", "lash"):
                sk = self.fig.eye[f"{part}.{sfx}"].data.shape_keys
                kbs = sk.key_blocks[1:]
                vals = [(fr, None if shut else {kb.name: self._kval(kb, sk, fr) for kb in kbs}) for fr, shut in frames]
                for fr, v in vals:
                    for kb in kbs:
                        kb.value = (1.0 if kb.name == "closed" else 0.0) if v is None else v[kb.name]
                        kb.keyframe_insert("value", frame=max(1, fr))

    def blink(self, t: float):
        f = self._f(t)
        self._lids([(f - 2, False), (f, True), (f + 1, True), (f + 4, False)])
        return self

    def eyes_closed(self, t0: float, t1: float):
        f0, f1 = self._f(t0), max(self._f(t0) + 3, self._f(t1))
        self._lids([(f0 - 1, False), (f0 + 1, True), (f1 - 1, True), (f1 + 2, False)])
        return self

    def eyes(self, dx: float = 0.0, dz: float = 0.0, t: float = 0.0, blend: float = 0.1):
        """Where the eyes look: dx +1 = toward the facing side, -1 = back; dz +1 = up, -1 = down."""
        for sfx in "LR":
            self._eye_node(sfx, "lx", t, blend, 0.020 * max(-1.0, min(1.0, dx)) * self._face)
            self._eye_node(sfx, "lz", t, blend, 0.018 * max(-1.0, min(1.0, dz)))
        self._ckey("look_x", t, blend, max(-1.0, min(1.0, dx)) * self._face)      # the brows follow a little
        self._ckey("look_z", t, blend, max(-1.0, min(1.0, dz)))
        return self

    def hand(self, side: str, shape: str, t: float = 0.0, blend: float = 0.1):
        if shape not in self.HAND_SHAPES:
            raise ValueError(f"unknown hand shape {shape!r}: use one of {self.HAND_SHAPES}")
        for h in self.HAND_SHAPES[1:]:
            self._ckey(f"hand_{side}_{h}", t, blend, 1.0 if h == shape else 0.0)
        return self

    # ------------------------------------------------------------------ arms
    def _dirs(self, side, raise_deg, bend_deg, plane="fwd"):
        """(upper arm, forearm) directions in the upper body's own space for a (raise, bend, plane) arm"""
        s = 1.0 if side == "L" else -1.0
        a1, a2 = math.radians(raise_deg), math.radians(raise_deg + bend_deg)
        if plane == "out":
            # a raised arm must clear the big head and the collar: past shoulder height it stops short of straight up and
            # comes forward, so the hands are beside and in front of the head, never behind it
            lim = lambda d: d if d <= 115.0 else 115.0 + (d - 115.0) * 0.45
            fw = lambda d: 0.42 * (lambda x: x * x * (3 - 2 * x))(max(0.0, min(1.0, (d - 80.0) / 60.0)))
            a1, a2 = math.radians(lim(raise_deg)), math.radians(lim(raise_deg + bend_deg))
            u = Vector((s * math.sin(a1), -fw(raise_deg), -math.cos(a1)))
            w = Vector((s * math.sin(a2), -fw(raise_deg + bend_deg) - 0.6 * max(0.0, -bend_deg) / 100.0 - 0.05, -math.cos(a2)))
        else:
            out = 0.10 * (1.0 - min(1.0, abs(raise_deg) / 90.0))
            u = Vector((s * out, -math.sin(a1), -math.cos(a1)))
            w = Vector((s * out * 0.4, -math.sin(a2), -math.cos(a2)))
        return u.normalized(), w.normalized()

    def _set_arm(self, side, dirs, t, blend):
        u, w = dirs
        h = u.cross(w)
        if h.length < 1e-4:
            h = self._hinge[side].copy()
            h = (h - u * h.dot(u))
            if h.length < 1e-4:
                h = Vector((1, 0, 0)) - u * u.x
        h.normalize()
        if h.dot(self._hinge[side]) < 0:
            h = -h
        self._hinge[side] = h
        z = -u
        y = z.cross(h).normalized()
        m = Matrix((h, y, z)).transposed()
        q = m.to_quaternion()
        wl = m.transposed() @ w
        th = math.atan2(wl.y, -wl.z)
        qe = Quaternion((1, 0, 0), th)
        self._elbow[side] = th
        for jn, qq in ((f"sh.{side}", q), (f"el.{side}", qe)):
            ob = self.J[jn]
            prev = self._q.get(jn)
            if prev is not None and qq.dot(prev) < 0:
                qq = -qq
            self._q[jn] = qq.copy()
            self._key(ob, "rotation_quaternion", t, blend, qq)

    def arm(self, side: str, raise_deg: float, bend_deg: float = 0.0, t: float = 0.0, blend: float = 0.25, plane: str = "fwd"):
        self._set_arm(side, self._dirs(side, raise_deg, bend_deg, plane), t, blend)
        self._arm[side] = (raise_deg, bend_deg, plane)
        return self

    def spot(self, side: str, name: str, dx: float = 0.0, dz: float = 0.0) -> Vector:
        """a named place on the figure's own body, in the upper body's space (where the palm should be)"""
        b = self.b
        s = 1.0 if side == "L" else -1.0
        R, hz = b["R"], b["head_z"]
        f = self.sheet.get("face", {})
        up = b["neck_z"] - b["hip_z"]
        tr = lambda z: self.fig.torso_r(z) * 0.76
        hr = b["hand_r"]
        P = {"chin": (s * 0.03, -R * 0.98 - hr * 0.5, hz - 0.70 * R), "mouth": (s * 0.02, -R * 1.0 - hr * 0.6, hz + f.get("mz", -0.385) * R),
             "brow": (s * 0.30 * R, -R * 0.92 - hr * 0.5, hz + 0.42 * R), "forehead": (s * 0.30 * R, -R * 0.92 - hr * 0.5, hz + 0.42 * R),
             "ear": (s * (R + hr * 0.7), -0.12 * R, hz - 0.05 * R), "beside_face": (s * (R + hr * 1.2), -0.35 * R, hz - 0.10 * R),
             "belly": (s * 0.03, -(tr(b["hip_z"] + 0.35 * up) + hr * 0.7), b["hip_z"] + 0.35 * up),
             "chest": (s * 0.03, -(tr(b["hip_z"] + 0.70 * up) + hr * 0.7), b["hip_z"] + 0.70 * up),
             "hip": ((s * (self.fig.torso_r(self.fig.waist - 0.03) + hr * 0.85), -0.03, self.fig.waist - 0.03) if self.fig.robe else
                     (s * (self.fig.torso_r(b["hip_z"] + 0.10) + hr * 0.75), -0.02, b["hip_z"] + 0.10)),
             "cheek": (s * 0.80 * R, -R * 0.62 - hr * 0.5, hz - 0.28 * R), "top": (s * 0.25 * R, -0.15 * R, hz + R + hr * 0.6),
             "nape": (s * 0.30 * R, R * 0.80 + hr * 0.4, hz - 0.65 * R),
             "heart": (0.05, -(tr(b["hip_z"] + 0.74 * up) + hr * 0.7), b["hip_z"] + 0.74 * up),
             "pocket": (s * (self.fig.torso_r(b["hip_z"] + 0.04) * 0.85), -(tr(b["hip_z"] + 0.04) * 0.6 + hr * 0.5), b["hip_z"] + 0.04),
             "belt": (s * 0.05, -(tr(b["hip_z"] + 0.14) + hr * 0.7), b["hip_z"] + 0.14),
             "cross": (-s * 0.07, -(tr(b["hip_z"] + 0.58 * up) + hr * 0.8), b["hip_z"] + (0.60 if side == "L" else 0.52) * up)}
        p = Vector(P.get(name, P["chest"])) + Vector((s * dx, 0.0, dz))
        return p - self.W["torso"]

    def _solve(self, side, target_local, elbow="auto"):
        """two-bone arm to a point in the upper body's space -> (upper, forearm) directions"""
        s = 1.0 if side == "L" else -1.0
        S = Vector(self.J[f"sh.{side}"].location)
        L1, L2 = self.b["arm1"], self.b["arm2"] + self.b["hand_r"] * 0.95
        d = target_local - S
        dist = max(abs(L1 - L2) + 0.01, min(L1 + L2 - 0.002, d.length))
        dn = d.normalized() if d.length > 1e-6 else Vector((0, 0, -1))
        pole = {"up": Vector((s * 0.5, 0.1, 1.0)), "down": Vector((s * 0.25, 0.25, -1.0))}.get(elbow, Vector((s * 0.90, 0.10, -0.45)))     # elbows out to the side, never back into a cape
        perp = pole - dn * pole.dot(dn)
        if perp.length < 1e-4:
            perp = Vector((s, 0, 0)) - dn * dn.x
        perp.normalize()
        a = (L1 * L1 + dist * dist - L2 * L2) / (2 * dist)
        hgt = math.sqrt(max(0.0, L1 * L1 - a * a))
        E = S + dn * a + perp * hgt
        T = S + dn * dist
        return (E - S).normalized(), (T - E).normalized()

    def _torso_inv(self, frame):
        dg = core.at_frame(frame)
        return self.J["torso"].evaluated_get(dg).matrix_world.inverted()

    def reach(self, side: str, target, t: float, blend: float = 0.3, elbow: str = "auto"):
        """Put the palm exactly on a world point, an object or an anchor at time t (a real reach in space)."""
        p = core.point_of(target)
        local = self._torso_inv(self._f(t)) @ p
        self._set_arm(side, self._solve(side, local, elbow), t, blend)
        self._arm[side] = (70.0, 30.0, "fwd")
        return self

    def aim(self, side: str, target, t: float, blend: float = 0.25, bend: float = 6.0):
        p = core.point_of(target)
        local = self._torso_inv(self._f(t)) @ p
        d = (local - Vector(self.J[f"sh.{side}"].location)).normalized()
        w = (d + Vector((0, 0, math.sin(math.radians(bend))))).normalized()
        self._set_arm(side, (d, w), t, blend)
        self._arm[side] = (88.0, bend, "fwd")
        return self

    def _wag(self, side: str, deg: float, t: float, blend: float = 0.12):
        ob = self.J[f"el.{side}"]
        self._key(ob, "rotation_quaternion", t, blend, Quaternion((1, 0, 0), self._elbow[side] + math.radians(deg)))
        return self

    def wrist(self, side: str, deg: float, t: float = 0.0, blend: float = 0.15):
        self._key(self.J[f"wr.{side}"], "rotation_euler", t, blend, math.radians(-deg), index=0)
        return self

    # ------------------------------------------------------------------ body
    def lean(self, deg: float, t: float = 0.0, blend: float = 0.3):
        self._key(self.J["torso"], "rotation_euler", t, blend, math.radians(deg), index=0)
        if self.fig.robe:                                     # a cape hangs straight down, it does not stick out behind a bow
            self._key(self.J["cape"], "rotation_euler", t, blend, math.radians(-deg * 0.8), index=0)
        return self

    def tilt_head(self, deg: float, t: float = 0.0, blend: float = 0.2):
        self._key(self.J["head"], "rotation_euler", t, blend, math.radians(deg), index=0)
        return self

    def head_turn(self, amount: float, t: float = 0.0, blend: float = 0.12):
        self._key(self.J["head"], "rotation_euler", t, blend, math.radians(38.0 * amount) * self._face, index=2)
        return self

    def _leg_fk(self, side, raise_deg, bend_deg, t, blend):
        for jn, v in ((f"hip.{side}", -raise_deg), (f"kn.{side}", bend_deg), (f"an.{side}", raise_deg - bend_deg)):
            self._key(self.J[jn], "rotation_euler", t, blend, math.radians(v), index=0)

    def _gown(self, t, blend, sink):
        if not self.fig.robe:
            return
        v = max(0.0, min(1.0, sink / fig3d.SQUAT_MAX))
        f1 = self._f(t)
        f0 = self._f0(t, blend) if blend > 0 else f1
        for obs in self.fig.parts.values():
            for ob in obs:
                sk = ob.data.shape_keys
                if sk and "squat" in sk.key_blocks:
                    kb = sk.key_blocks["squat"]
                    if f0 < f1:
                        kb.keyframe_insert("value", frame=f0)
                    kb.value = v
                    kb.keyframe_insert("value", frame=f1)

    def _sink_for(self, raise_deg, bend_deg):
        a1, a2 = math.radians(raise_deg), math.radians(raise_deg - bend_deg)
        b = self.b
        ext = max(self.leg1 * math.cos(a1) + self.leg2 * math.cos(a2) + b["ankle_z"], self.leg1 * math.cos(a1) + b["r_kn"], b["r_hip"])
        return max(0.0, b["leg_z"] - ext)

    def legs(self, raise_deg: float, bend_deg: float, t: float = 0.0, blend: float = 0.3, side: str = "LR", ground: bool = True):
        """Thighs forward by raise_deg, knees folded back by bend_deg (sit: 86, 84; kneel: 8, 98; crouch: 58, 104). The body
        sinks so the feet or the knees stay exactly on the ground on every frame of the move; a gown's hem stays down."""
        if not (ground and side == "LR"):
            for s in side:
                self._leg_fk(s, raise_deg, bend_deg, t, blend)
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
                for jn, v in ((f"hip.{s}", -r), (f"kn.{s}", bd), (f"an.{s}", r - bd)):
                    self.J[jn].rotation_euler.x = math.radians(v)
                    self.J[jn].keyframe_insert("rotation_euler", index=0, frame=f)
            sink = self._sink_for(r, bd)
            self.J["hips"].location.z = self._hips_rest.z - sink
            self.J["hips"].keyframe_insert("location", index=2, frame=f)
            if self.fig.robe:
                v = max(0.0, min(1.0, sink / fig3d.SQUAT_MAX))
                for obs in self.fig.parts.values():
                    for ob in obs:
                        sk = ob.data.shape_keys
                        if sk and "squat" in sk.key_blocks:
                            sk.key_blocks["squat"].value = v
                            sk.key_blocks["squat"].keyframe_insert("value", frame=f)
        self._legs_now = (raise_deg, bend_deg)
        sink = self._sink_for(raise_deg, bend_deg)
        self._sink = (sink * self.scale, sink * self.scale)
        return self

    def pose(self, name_or_spec, t: float = 0.0, blend: float = 0.25, side: str | None = None):
        if isinstance(name_or_spec, str) and name_or_spec not in cast2d.POSES:
            raise KeyError(f"unknown pose {name_or_spec!r}. Poses: {', '.join(cast2d.POSES)}")
        if isinstance(name_or_spec, str):
            spec = dict(POSE3D.get(name_or_spec, cast2d.POSES[name_or_spec]))
        else:
            spec = dict(name_or_spec)
        spec.pop("views", None)
        if side and side != "R" and "R" in spec and "L" not in spec:
            spec["L"] = spec.pop("R")
            if isinstance(spec.get("hands"), dict):
                spec["hands"] = {("L" if k == "R" else k): v for k, v in spec["hands"].items()}
        for s in "LR":
            if s not in spec:
                continue
            a = spec[s]
            if a == "rest" or a is None:
                self.arm(s, *ARM_REST[:2], t, blend, plane=ARM_REST[2])
            elif a[0] == "to":
                local = self.spot(s, a[1], *(a[2:4] if len(a) > 2 else ()))
                self._set_arm(s, self._solve(s, local), t, blend)
                self._arm[s] = (60.0, 60.0, "fwd")
            else:
                self.arm(s, a[0], a[1], t, blend, plane=a[2] if len(a) > 2 else "fwd")
        if "lean" in spec:
            self.lean(spec["lean"], t, blend)
        if "tilt" in spec:
            self.tilt_head(spec["tilt"], t, blend)
        if "legs" in spec:
            self.legs(spec["legs"][0], spec["legs"][1], t, blend)
        h = spec.get("hands")
        if isinstance(h, str):
            h = {"L": h, "R": h}
        for s, shape in (h or {}).items():
            if not self._grips(s):
                self.hand(s, shape, t, min(blend, 0.12))
        return self

    def squash(self, t: float, amount: float = 0.14, hold: float = 0.08, recover: float = 0.18):
        fps = self.shot.fps
        f = self._f(t)
        seq = ((f - 2, 1.0, 1.0), (f, 1.0 + amount * 0.6, 1.0 - amount), (f + max(1, int(hold * fps)), 1.0 + amount * 0.6, 1.0 - amount),
               (f + max(2, int((hold + recover * 0.5) * fps)), 1.0 - amount * 0.2, 1.0 + amount * 0.35), (f + max(3, int((hold + recover) * fps)), 1.0, 1.0))
        for fr, sx, sz in seq:
            self.tilt.scale = (sx, sx, sz)
            self.tilt.keyframe_insert("scale", frame=max(1, fr))
        return self

    # ------------------------------------------------------------------ walking
    def _solve_leg(self, df, du):
        L1, L2 = self.leg1, self.leg2
        d = max(0.06, min(L1 + L2 - 0.002, math.hypot(df, du)))
        a = math.atan2(df, -du)
        ch = max(-1.0, min(1.0, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)))
        ck = max(-1.0, min(1.0, (L1 * L1 + L2 * L2 - d * d) / (2 * L1 * L2)))
        return a + math.acos(ch), math.pi - math.acos(ck)

    def _legs_at(self, f, drop, ahead=(0.0, 0.0), lift=(0.0, 0.0), toe=(0.0, 0.0)):
        hips = self.J["hips"]
        hips.location.z = self._hips_rest.z - drop
        hips.keyframe_insert("location", index=2, frame=f)
        b = self.b
        for i, sfx in enumerate("LR"):
            th, kn = self._solve_leg(ahead[i], (b["ankle_z"] + lift[i]) - (b["leg_z"] - drop))
            for jn, val in ((f"hip.{sfx}", -th), (f"kn.{sfx}", kn), (f"an.{sfx}", th - kn + toe[i])):
                self.J[jn].rotation_euler.x = val
                self.J[jn].keyframe_insert("rotation_euler", index=0, frame=f)

    def _cloth(self, f, wave_a, wave_b, flare):
        """A skirt that has cloth keys (waveA / waveB: a ripple that travels round the hem; flare: the hem opening on each
        step) is moved with the gait. Figures without those keys are untouched."""
        if not hasattr(self, "_cloth_obs"):
            self._cloth_obs = [ob for obs in self.fig.parts.values() for ob in obs
                               if ob.data.shape_keys and "waveA" in ob.data.shape_keys.key_blocks]
        for ob in self._cloth_obs:
            kb = ob.data.shape_keys.key_blocks
            for name, v in (("waveA", wave_a), ("waveB", wave_b), ("flare", flare)):
                kb[name].value = v
                kb[name].keyframe_insert("value", frame=f)

    def walk(self, t0: float, to, speed: float = 2.0, view: str | None = None, face: str | None = None, then_view: str | None = None,
             cycle: str = "walk", arms: bool = True) -> float:
        """Go to (x, y) on a gait with planted feet: cycle = "walk" | "run" | "sneak". speed: 1 = stroll, 2 = brisk.
        The figure turns to where it is going; then_view= turns it back to a view of the camera on arrival.
        Returns the arrival time. arms=False leaves the arms as posed."""
        g = GAITS.get(cycle, GAITS["walk"])
        start = Vector((self._pos.x, self._pos.y))
        goal = Vector((to[0], to[1]))
        dist = (goal - start).length
        if dist < 1e-3:
            return t0
        leg = (self.leg1 + self.leg2) * self.scale
        fps = self.shot.fps
        self.heading(to, t0, 0.2)
        S0 = g["S"] * leg
        n = max(2, int(round(dist / S0)))
        S = dist / n
        T = max(0.14, S / (g["mps"] * speed / 2.0 * max(0.55, leg / 0.48)))
        dur = n * T
        f0, f1 = self._f(t0), self._f(t0 + dur)
        z = self._pos.z
        self.stage.location = (start.x, start.y, z)
        core.key_frame(self.stage, "location", f0, interp="LINEAR")
        self.stage.location = (goal.x, goal.y, z)
        core.key_frame(self.stage, "location", f1, interp="LINEAR")
        steps, at = [], [0.0, 0.0]
        for k in range(1, n + 2):
            foot = (k + 1) % 2
            ts = t0 + (k - 1) * T
            te = ts + T * g["sw"]
            land = min(dist, (k - 1 + g["sw"]) * S + 0.5 * S) if k <= n else dist
            steps.append((foot, ts, te, at[foot], land))
            at[foot] = land
        f_end = self._f(max(st[2] for st in steps))
        self.lean(g["lean"], t0 + 0.2, 0.2)
        self._key(self.J["skirt"], "rotation_euler", t0 + 0.3, 0.3, math.radians(g["skirt"]), index=0)
        if not self.fig.robe:
            self._key(self.J["cape"], "rotation_euler", t0 + 0.3, 0.3, math.radians(g["cape"]), index=0)
        sc = self.scale
        for f in range(f0, f_end + 1):
            t = (f - 1) / fps
            sb = dist * max(0.0, min(1.0, (t - t0) / dur))
            ahead, lift, toe = [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]
            for foot in (0, 1):
                pos = 0.0
                for (ft, ts, te, a, b_) in steps:
                    if ft != foot:
                        continue
                    if t >= te:
                        pos = b_
                    elif t > ts:
                        u = (t - ts) / (te - ts)
                        pos = a + (b_ - a) * (u * u * (3 - 2 * u))
                        lift[foot] = g["lift"] * (0.6 if self.fig.robe else 1.0) * leg / sc * math.sin(math.pi * u)
                        toe[foot] = 0.5 * math.sin(math.pi * u) * (1 - u)
                        break
                    else:
                        pos = a
                        break
                ahead[foot] = (pos - sb) / sc
            ph = math.tau * (t - t0) / T
            ramp = min(1.0, (t - t0) / 0.2, max(0.0, (t0 + dur - t) / 0.2 + 0.25))
            drop = (g["drop"] * ramp + g["bob"] * ramp * (0.5 + 0.5 * math.cos(ph))) * leg / sc
            self._legs_at(f, drop, tuple(ahead), tuple(lift), tuple(toe))
            self._cloth(f, ramp * math.sin(ph * 0.5), ramp * math.cos(ph * 0.5), ramp * (0.5 + 0.5 * math.cos(ph)) * (1.0 if cycle == "run" else 0.45))
            if arms:
                sw = g["arm"] * ramp * math.sin(ph / 2)
                for sfx, sg in (("L", 1.0), ("R", -1.0)):
                    if self._grips(sfx):
                        continue
                    self._set_arm(sfx, self._dirs(sfx, sg * sw, 18 + (30 if cycle == "run" else 6) * ramp + max(0.0, sg * sw) * 0.5, "fwd"), None, 0)
                    self.J[f"sh.{sfx}"].keyframe_insert("rotation_quaternion", frame=f)
                    self.J[f"el.{sfx}"].keyframe_insert("rotation_quaternion", frame=f)
        self._pos = Vector((goal.x, goal.y, z))
        t_end = (f_end - 1) / fps
        self.lean(0, t_end + 0.25, 0.25)
        self._key(self.J["skirt"], "rotation_euler", t_end + 0.4, 0.4, 0.0, index=0)
        if not self.fig.robe:
            self._key(self.J["cape"], "rotation_euler", t_end + 0.4, 0.4, 0.0, index=0)
        self._legs_at(self._f(t_end + 0.12), 0.0)
        self._cloth(self._f(t_end + 0.35), 0.0, 0.0, 0.0)
        if arms:
            for sfx in "LR":
                if not self._grips(sfx):
                    self.arm(sfx, *ARM_REST[:2], t_end + 0.3, 0.3, plane=ARM_REST[2])
        d = goal - start
        cy = self._cam_yaw(self._f(t_end))
        right = Vector((math.cos(cy), math.sin(cy)))
        sx = d.normalized().dot(right)
        if abs(sx) > 0.25:
            self._face = 1 if sx > 0 else -1
        if face:
            self._face = 1 if str(face).lower().startswith("r") else -1
        if then_view or view:
            self._view = {0: "front", 1: "3q", 2: "side"}[cast2d.VIEW_INDEX[str(then_view or view).lower()]]
            self._orient(t_end + 0.3, 0.3)
        else:
            self._view = "side" if abs(sx) > 0.7 else "3q"
        return t_end

    # ------------------------------------------------------------------ props
    def hold(self, prop, side: str = "R", t: float = 0.0, offset=(0.0, 0.0, 0.0), front: bool = True, grip: bool = True, turn: bool = False):
        """From time t the prop sits in the palm and goes with the hand. offset: metres from the palm (x toward the facing
        side, y depth, z up). turn=True: it also turns with the hand (a tool, a sword, a cup that tips)."""
        f = self._f(t)
        if prop.name in self._held:
            self._drop_holds(prop, f)
        tgt = bpy.data.objects.new(f"{self.id}.hold.{prop.name}", None)
        tgt.empty_display_size = 0.02
        self.fig.coll.objects.link(tgt)
        tgt.parent = self.palm[side]
        tgt.location = (offset[0] * self._face, offset[1], offset[2]) if not turn else tuple(offset)
        cons = []
        c = prop.constraints.new("COPY_LOCATION")
        c.target = tgt
        cons.append(c)
        if turn:
            r = prop.constraints.new("COPY_ROTATION")
            r.target = tgt
            cons.append(r)
        for c in cons:
            c.influence = 0.0
            if f > 1:
                c.keyframe_insert("influence", frame=f - 1)
            c.influence = 1.0
            c.keyframe_insert("influence", frame=f)
        self._held[prop.name] = (cons, tgt, side, dict(offset=offset, front=front, grip=grip, turn=turn))
        if grip:
            self.hand(side, "grip", t, 0.06)
        return self

    def _drop_holds(self, prop, f: int):
        h = self._held.get(prop.name)
        if not h:
            return
        for c in h[0]:
            c.influence = 1.0
            c.keyframe_insert("influence", frame=max(1, f - 1))
            c.influence = 0.0
            c.keyframe_insert("influence", frame=f)

    def release(self, prop, t: float, hand: str | None = "open"):
        f = self._f(t)
        dg = core.at_frame(max(1, f - 1))
        pe = prop.evaluated_get(dg)
        world = pe.matrix_world.translation.copy()
        rot = pe.matrix_world.to_euler()
        held = self._held.get(prop.name)
        turned = bool(held) and len(held[0]) > 1
        self._drop_holds(prop, f)
        self._held.pop(prop.name, None)
        prop.location = world if prop.parent is None else prop.parent.matrix_world.inverted() @ world
        core.key_frame(prop, "location", f)
        if turned and prop.parent is None:
            if f > 1:
                prop.keyframe_insert("rotation_euler", frame=f - 1)
            prop.rotation_euler = rot
            core.key_frame(prop, "rotation_euler", f, interp="CONSTANT")
        if held and hand and not self._grips(held[2]):
            self.hand(held[2], hand, t, 0.08)
        return world

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
            tj = self.J["torso"]
            for i in range(n + 1):
                tj.scale = (1.0 + 0.012 * breathe * (i % 2), 1.0 + 0.020 * breathe * (i % 2), 1.0)
                tj.keyframe_insert("scale", frame=self._f(t0 + i * period / 2))
        return self

    # ------------------------------------------------------------------ costume
    def recolor(self, **colors):
        self.fig.recolor(**colors)
        return self

    def hide(self, *patterns):
        if not self.fig.hide(*patterns):
            self.shot.notes.append(f"{self.id}: hide{patterns} matched no part of {self.base}")
        return self

    def wear(self, item: str, **opts):
        from . import wardrobe
        wardrobe.wear(self, item, **opts)
        return self

    def head_box(self, view=None):
        return 0.0, self.b["head_z"], self.b["R"]

    def torso_box(self, view=None):
        b = self.b
        z1 = b["neck_z"]
        z0 = b["hip_z"] if self.fig.robe else min(p[1] for p in b["torso"])
        hw = max((p[0] for p in b["torso"] if p[1] >= z0), default=0.15)
        return 0.0, z0, z1, hw

    def add_part(self, name: str, view, pts, color, bone: str = "torso", layer: float = 10.0, outline: bool = True, wire: bool = False):
        """One flat front drawing (x, z in metres in the figure's own space) made 3D on the body: see fig3d.Fig.add_flat."""
        if wire:
            return None
        obs = self.fig.add_flat(name, bone, pts, color, layer)
        return obs[0] if obs else None

    def add_flat(self, name, on, pts, color, layer=10.0, **opts):
        return self.fig.add_flat(name, on, pts, color, layer, **opts)


def actor(cid: str, base: str, at=(0, 0), face: str = "right", view: str = "3q", scale: float = 1.0, costume: dict | None = None) -> Actor3D:
    """Bring a 3D character on stage. base: a name in config/cast3d.json. costume: the same dict the plan's cast uses."""
    sh = sheets()
    if base not in sh:
        raise KeyError(f"no 3D character '{base}'. config/cast3d.json has: {', '.join(sorted(sh))}")
    a = Actor3D(cid, base, sh[base], scale)
    a.place(at)
    a._face = 1 if str(face).lower().startswith("r") else -1
    a.view(view)
    a.pose("rest", 0.0, 0.0)
    for w in sh[base].get("wear", []) or []:                  # wardrobe pieces that are part of the character's own sheet
        w = dict(w)
        a.wear(w.pop("item"), **w)
    if costume:
        if costume.get("hide"):
            a.hide(*costume["hide"])
        if costume.get("recolor"):
            a.recolor(**costume["recolor"])
        for w in costume.get("wear", []) or []:
            w = dict(w)
            a.wear(w.pop("item"), **w)
    return a
