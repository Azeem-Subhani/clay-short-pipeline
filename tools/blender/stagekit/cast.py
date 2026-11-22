"""stagekit.cast - the flat 2D character pack, staged in a 3D world.

A character is a stack of flat cut-out parts in one plane, with three drawn views (front, three-quarter, side), five
face expressions, talking mouth shapes, three hand shapes and a walk cycle. On the stage it is a cardboard figure that
always turns its flat side to the camera, stands on the ground and throws a real shadow.

    queen = cast.from_plan("queen", at=(1.2, 0.4), face="left", view="3q")
    queen.expr("surprised", t)            # happy | worried | angry | sad | surprised | neutral
    queen.pose("gasp", t)                 # a named pose, or arms/lean/tilt by hand: queen.arm("R", 120, 30, t)
    queen.reach("R", ring, t)             # the hand goes exactly to a point or object (two-bone IK in the picture plane)
    queen.hold(ring, "R", t)              # a prop follows the hand until queen.release(ring, t)
    queen.speak("Bring it back", "is yours")    # mouth shapes on the narrator's words, from the first phrase to the last
    arrive = gardener.walk(t, to=(4, 2))  # walk cycle with planted feet; returns the arrival time
    queen.idle()                          # blinks and breathing so nothing freezes

Every time is seconds from the start of the shot. The pack has no back view: stage people facing the camera or in profile.
"""
from __future__ import annotations

import fnmatch
import json
import math
import os
import random
import re

import bpy
from mathutils import Vector

from . import core

VIEWS = ("Front", "ThreeQuarter", "Side")
VIEW_INDEX = {"front": 0, "3q": 1, "three_quarter": 1, "threequarter": 1, "side": 2}
EXPRS = ("happy", "worried", "angry", "sad", "surprised")
VISEMES = ("A", "E", "I", "O", "U", "MBP")
DEPTH = 0.08                 # the 0.7 m layer stack of the pack is pressed to about 5 cm so a moving camera sees one flat figure
ARM_REST = 15.0

# Named poses. Arms are (raise, bend): raise = upper arm away from hanging (outward in the front view, forward in
# three-quarter and side); bend = elbow, positive folds the forearm further the same way. lean / tilt in degrees, positive forward.
POSES = {
    "rest": {"L": (ARM_REST, 0), "R": (ARM_REST, 0), "lean": 0, "tilt": 0, "hands": "mitten"},
    "gasp": {"L": (55, 105), "R": (55, 105), "lean": -4, "tilt": -4, "hands": "open"},          # both hands fly to the face
    "hands_up": {"L": (150, 12), "R": (150, 12), "hands": "open"},
    "cheer": {"L": (165, -10), "R": (165, -10), "lean": -5, "hands": "open"},
    "point": {"R": (88, 4), "hands": {"R": "pinch"}},
    "point_up": {"R": (112, 16), "hands": {"R": "pinch"}},                                       # one finger raised beside the face: a rule, a warning
                                                                                                  # (a hand folded in close to the head is drawn behind it)
    "offer": {"R": (70, 25), "hands": {"R": "open"}},
    "hips": {"L": (42, -100), "R": (42, -100), "lean": -3},                                       # proud, hands on hips
    "proud": {"L": (42, -100), "R": (42, -100), "lean": -8, "tilt": -6},
    "shrug": {"L": (38, 70), "R": (38, 70), "hands": "open", "tilt": 6},
    "think": {"R": (72, 112), "L": (20, 0), "tilt": 6, "hands": {"R": "pinch"}},
    "facepalm": {"R": (80, 118), "tilt": 14, "lean": 6},
    "hang": {"L": (176, 4), "R": (176, 4)},                                                       # arms straight up: hanging from something
    "carry": {"L": (48, 62), "R": (48, 62)},                                                      # holding something in front of the chest
    "reach_down": {"R": (62, 10), "L": (24, 0), "lean": 48, "tilt": 12, "hands": {"R": "open"}},
    "pull": {"L": (70, 40), "R": (58, 55), "lean": -14},
    "lift": {"L": (120, 30), "R": (120, 30), "lean": -6},
    "slump": {"L": (8, 0), "R": (8, 0), "lean": 14, "tilt": 16},
    "laugh": {"L": (40, 96), "R": (30, -60), "lean": -12, "tilt": -12, "hands": "open"},
    "wave": {"R": (118, 44), "hands": {"R": "open"}},
    "sit": {"L": (30, 40), "R": (30, 40), "legs": (86, 84)},
    "kneel": {"legs": (50, 115), "lean": 12},
    "hold_pole": {"L": (62, 58), "R": (84, 22)},                                                  # both hands on a long tool
}

_REG = None


def registry() -> dict:
    """config/cast.json: what the pack offers (base characters, their period, parts that can come off) and the wardrobe."""
    global _REG
    if _REG is None:
        _REG = json.loads((core.PROJECT / "config" / "cast.json").read_text(encoding="utf-8"))
    return _REG


class Anchor:
    """A named point on a character (head, chest, feet, a hand). Cameras aim at it, checks measure it."""

    def __init__(self, actor, ob):
        self.actor = actor
        self.ob = ob

    def point(self) -> Vector:
        bpy.context.view_layer.update()
        return self.ob.matrix_world.translation.copy()

    def object(self):
        return self.ob


# ----------------------------------------------------------------------------- materials: flat colour that still sits in the light
_LOOK = {"tint": (1.0, 1.0, 1.0), "lit": 0.22, "gain": 1.0}


def _lookify(mat, outline: bool = False):
    """Pack materials are pure emission (flat colour). Rebuild them as flat colour x scene tint, plus a little real diffuse
    so cast shadows and the colour of the light reach the figure and it stops looking pasted on."""
    if mat.get("sk_look"):
        return mat
    nt = mat.node_tree
    em = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeEmission"), None)
    col = tuple(em.inputs["Color"].default_value) if em else tuple(mat.diffuse_color)
    nt.nodes.clear()
    rgb = nt.nodes.new("ShaderNodeRGB")
    rgb.name = "base"
    rgb.outputs[0].default_value = col
    tint = nt.nodes.new("ShaderNodeRGB")
    tint.name = "tint"
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(rgb.outputs[0], mul.inputs["A"])
    nt.links.new(tint.outputs[0], mul.inputs["B"])
    e = nt.nodes.new("ShaderNodeEmission")
    e.name = "flat"
    nt.links.new(mul.outputs["Result"], e.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if outline:
        nt.links.new(e.outputs[0], out.inputs["Surface"])
    else:
        d = nt.nodes.new("ShaderNodeBsdfDiffuse")
        d.name = "lit"
        nt.links.new(rgb.outputs[0], d.inputs["Color"])
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.name = "lit_mix"
        nt.links.new(e.outputs[0], mix.inputs[1])
        nt.links.new(d.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    mat["sk_look"] = 2 if outline else 1
    mat.diffuse_color = col
    _apply_look(mat)
    return mat


def _apply_look(mat):
    nt = mat.node_tree
    nt.nodes["tint"].outputs[0].default_value = (*_LOOK["tint"], 1.0)
    nt.nodes["flat"].inputs["Strength"].default_value = _LOOK["gain"]
    if mat["sk_look"] == 1:
        nt.nodes["lit_mix"].inputs[0].default_value = _LOOK["lit"]


def look(tint="#FFFFFF", lit: float = 0.22, gain: float = 1.0):
    """How the cast sits in this set's light. tint: the colour of the light on them (warm sunset "#FFD9B8", moonlight
    "#B9C6E8"); lit: how much real scene light and shadow reach them (0 = sticker, 0.2-0.35 = belongs in the place);
    gain: overall brightness (0.6 at night). Call it once in the set file, with the light rig."""
    _LOOK["tint"] = tuple(core.hex_rgba(tint)[:3])
    _LOOK["lit"] = float(lit)
    _LOOK["gain"] = float(gain)
    for m in bpy.data.materials:
        if m.get("sk_look"):
            _apply_look(m)
    bpy.context.scene["cast_look"] = json.dumps({"tint": tint if isinstance(tint, str) else list(tint), "lit": lit, "gain": gain})


def flat_material(color, name: str | None = None):
    """A new flat character-style colour (for wardrobe pieces and 2D props)."""
    name = name or f"SK_flat_{color}"
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        m.node_tree.nodes.clear()
        e = m.node_tree.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = core.hex_rgba(color)
        o = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
        m.node_tree.links.new(e.outputs[0], o.inputs["Surface"])
        _lookify(m)
    return m


def _outline_ids():
    ng = bpy.data.node_groups.get("CL_Outline2D")
    if ng is None:
        raise RuntimeError("the pack's outline node group is missing: load a character first")
    return ng, {it.name: it.identifier for it in ng.interface.items_tree if getattr(it, "in_out", None) == "INPUT"}


# ----------------------------------------------------------------------------- the actor
class Actor:
    def __init__(self, cid: str, base: str, coll, scale: float = 1.0):
        self.id = cid
        self.base = base
        self.coll = coll
        self.shot = core.current()
        obs = list(coll.all_objects)
        self.root = next(o for o in obs if o.type == "EMPTY" and "view" in o.keys() and "character" in o.keys())
        self.ctrl = next(o for o in obs if o.type == "EMPTY" and "happy" in o.keys())
        self.rigs = {o["view"]: o for o in obs if o.type == "ARMATURE" and "walk_action" in o.keys()}
        self.parts = [o for o in obs if o.type == "MESH" and "cl_part" in o.keys()]
        self.scale = float(scale)
        for o in obs:                                              # one readable name per object: "<cast id>.<part>"
            tail = re.sub(r"\.\d{3}$", "", o.name)
            tail = tail[len(base) + 1:] if tail.startswith(base + "_") else tail
            o.name = f"{cid}.{tail}"
        for o in (self.root, self.ctrl):                           # the library ships with a preview animation: drop it
            if o.animation_data:
                o.animation_data.action = None
        for rig in self.rigs.values():
            if rig.animation_data:
                for tr in list(rig.animation_data.nla_tracks):
                    rig.animation_data.nla_tracks.remove(tr)
                rig.animation_data.action = None
            for pb in rig.pose.bones:
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = (0, 0, 0)
                pb.location = (0, 0, 0)
                pb.scale = (1, 1, 1)
        for e in EXPRS:
            self.ctrl[e] = 0.0
        self.ctrl["expression"] = 0
        for v in VISEMES:
            self.ctrl[f"viseme_{v}"] = 0.0
        # stage (position + billboard) > tilt (rotation in the picture plane) > pack root (scale, mirror, depth)
        self.stage = core.empty(cid, (0, 0, 0), "CAST", 0.3)
        self.tilt = core.empty(f"{cid}.tilt", (0, 0, 0), "CAST", 0.1)
        self.tilt.parent = self.stage
        self.root.parent = self.tilt
        self.root.location = (0, 0, 0)
        self.root.rotation_euler = (0, 0, 0)
        self.root.scale = (self.scale, DEPTH, self.scale)
        self._mats = {}
        for o in self.parts:
            self._own_materials(o)
        ng, ids = _outline_ids()
        for o in self.parts:
            md = o.modifiers.get("Outline")
            if md:
                m = getattr(md.properties.inputs, ids["Material"]).value
                if m:
                    _lookify(m, outline=True)
        self._calib = {v: self._calibrate(r) for v, r in self.rigs.items()}
        head = self._part("Head", "Front")
        self.head_z = float(head.location.z) if head else 1.3
        self.head_r = (float(head.dimensions.z) / 2 if head else 0.27)
        bpy.context.view_layer.update()
        zs = [(o.matrix_world @ Vector(c)).z for o in self.parts if o["cl_view"] == "Front" for c in o.bound_box]
        self.height = (max(zs) - self.stage.matrix_world.translation.z) if zs else 1.7 * self.scale
        self.head = self._anchor("head", (0, 0, self.head_z))
        self.chest = self._anchor("chest", (0, 0, 0.8))
        self.feet = self._anchor("feet", (0, 0, 0.0))
        self.top = self._anchor("top", (0, 0, self.height / max(self.scale, 1e-6)))
        self._pos = Vector((0, 0, 0))
        self._view = "3q"
        self._face = 1
        self._held = {}
        self._arm = {"L": (ARM_REST, 0.0), "R": (ARM_REST, 0.0)}
        self._airborne = []
        self.view(self._view)
        self.shot.actors[cid] = self
        self.shot.subject(cid, self.head)
        cam = getattr(self.shot, "camera", None)
        if cam is not None:
            self._billboard(cam.ob)

    # ------------------------------------------------------------------ plumbing
    def _own_materials(self, o):
        for i, m in enumerate(o.data.materials):
            if m is None:
                continue
            key = m.name
            if key not in self._mats:
                c = m.copy()
                c.name = f"{self.id}.{re.sub(r'^CL_', '', re.sub(r'[.][0-9]{3}$', '', key))}"
                self._mats[key] = _lookify(c)
            o.data.materials[i] = self._mats[key]

    def _part(self, name: str, view: str):
        return next((o for o in self.parts if o["cl_part"] == name and o["cl_view"] == view), None)

    def _anchor(self, name: str, local):
        e = core.empty(f"{self.id}.{name}", local, "CAST", 0.05)
        e.parent = self.root
        return Anchor(self, e)

    def _billboard(self, cam_ob):
        c = self.stage.constraints.get("face_camera") or self.stage.constraints.new("LOCKED_TRACK")
        c.name = "face_camera"
        c.target = cam_ob
        c.track_axis = "TRACK_NEGATIVE_Y"
        c.lock_axis = "LOCK_Z"

    @staticmethod
    def _calibrate(rig) -> dict:
        """Per bone: which local axis turns it in the picture plane, the sign, the rest angle (0 = down, +90 = +X) and length."""
        out = {}
        for b in rig.data.bones:
            m = b.matrix_local.to_3x3()
            ys = [abs(m.col[k].y) for k in range(3)]
            k = ys.index(max(ys))
            sigma = 1.0 if m.col[k].y > 0 else -1.0
            d = b.tail_local - b.head_local
            out[b.name] = (k, -sigma, math.degrees(math.atan2(d.x, -d.z)), d.length)
        return out

    def _f(self, t) -> int:
        return self.shot.f(t)

    def _f0(self, t: float, blend: float) -> int:
        """The frame where a change starts. The value before it is held there, so a change never drifts in from an older
        key. blend=0 is a pop on one frame (for a cut); at the very start of the shot there is nothing to hold."""
        f1 = self._f(t)
        return max(1, min(f1 - 1, self._f(t - blend))) if f1 > 1 else f1

    def _key_bone(self, bone: str, deg_by_view: dict, t: float, blend: float):
        """Turn a bone to a rotation (degrees, counter-clockwise in the picture) in every view rig, eased over `blend` seconds."""
        f1 = self._f(t)
        f0 = self._f0(t, blend)
        for v, rig in self.rigs.items():
            pb = rig.pose.bones.get(bone)
            if pb is None:
                continue
            k, s, _a0, _l = self._calib[v][bone]
            if f0 < f1:
                pb.keyframe_insert("rotation_euler", index=k, frame=f0)
            e = list(pb.rotation_euler)
            e[k] = math.radians(deg_by_view[v] / s)
            pb.rotation_euler = e
            pb.keyframe_insert("rotation_euler", index=k, frame=f1)

    def _dir(self, view: str, side: str) -> float:
        """+1 if 'away from the body' is counter-clockwise for this arm in this view."""
        if view == "Front":
            return 1.0 if side == "L" else -1.0
        return 1.0

    # ------------------------------------------------------------------ where, which way, which drawing
    def position(self) -> Vector:
        return self._pos.copy()

    def place(self, at, t: float | None = None):
        """Stand at (x, y) or (x, y, z). With t the jump is a cut-like pop at that time (no slide)."""
        p = Vector((at[0], at[1], at[2] if len(at) > 2 else 0.0))
        self.stage.location = p
        if t is not None:
            f = self._f(t)
            core.key_frame(self.stage, "location", f, interp="CONSTANT")
            if f > 1:
                self.stage.location = self._pos
                core.key_frame(self.stage, "location", f - 1, interp="CONSTANT")
                self.stage.location = p
        self._pos = p.copy()
        return self

    def face(self, side: str, t: float | None = None):
        """'right' or 'left' on screen (three-quarter and side views look that way; the front view just mirrors)."""
        if t is not None and self._f(t) > 1:                  # hold the old facing up to the frame before the turn
            core.key_frame(self.root, "scale", self._f(t) - 1, index=0, interp="CONSTANT")
        self._face = 1 if str(side).lower().startswith("r") else -1
        self.root.scale = (self._face * self.scale, DEPTH, self.scale)
        if t is not None:
            core.key_frame(self.root, "scale", self._f(t), index=0, interp="CONSTANT")
        return self

    def view(self, name: str, t: float | None = None):
        """Which drawing shows: 'front' (to camera), '3q' (the default: most alive), 'side' (profile, walking, pulling)."""
        idx = VIEW_INDEX[str(name).lower()]
        if t is not None and self._f(t) > 1:                  # hold the old drawing up to the frame before the switch
            core.key_frame(self.root, '["view"]', self._f(t) - 1, interp="CONSTANT")
        self._view = {0: "front", 1: "3q", 2: "side"}[idx]
        self.root["view"] = idx
        if t is not None:
            core.key_frame(self.root, '["view"]', self._f(t), interp="CONSTANT")
        self.root.update_tag()
        self._cull(self._f(t) if t is not None else None)
        return self

    def _cull(self, frame: int | None = None):
        """Give the renderer only the drawing that shows. A character is three complete drawings (front, three-quarter,
        side); the two that are switched off would still be deformed and outlined on every frame, which costs render
        time and memory for nothing. Review checks are not affected: they use the viewport, where everything stays."""
        if os.environ.get("CAST_CULL_VIEWS", "0") != "1":
            return
        key = self._view_key()
        for o in self.parts:
            v = o.get("cl_view")
            if v is None or o.get("sk_off"):
                continue
            if frame is not None and frame > 1:
                o.keyframe_insert("hide_render", frame=frame - 1)
            o.hide_render = v != key
            if frame is not None:
                o.keyframe_insert("hide_render", frame=frame)

    def set_scale(self, s: float):
        self.scale = float(s)
        self.root.scale = (self._face * self.scale, DEPTH, self.scale)
        return self

    def _view_key(self) -> str:
        return {"front": "Front", "3q": "ThreeQuarter", "side": "Side"}[self._view]

    # ------------------------------------------------------------------ face
    def expr(self, name: str, t: float = 0.0, blend: float = 0.12, amount: float = 1.0):
        """happy | worried | angry | sad | surprised | neutral. Change the face 2-4 frames BEFORE the body reacts."""
        if name not in EXPRS and name != "neutral":
            raise ValueError(f"unknown expression {name!r}: use one of {EXPRS + ('neutral',)}")
        f1 = self._f(t)
        f0 = self._f0(t, blend)
        for e in EXPRS:
            if f0 < f1:
                self.ctrl.keyframe_insert(f'["{e}"]', frame=f0)
            self.ctrl[e] = float(amount) if e == name else 0.0
            self.ctrl.keyframe_insert(f'["{e}"]', frame=f1)
        return self

    def speak(self, first: str | float, last: str | float | None = None, nth: int = 1, strength: float = 1.0):
        """Move the mouth while the narrator speaks this character's line. Give the first and last words of the line
        (speak("Bring it back", "is yours")) or two times in seconds. One mouth shape per spoken word."""
        if isinstance(first, str):
            t0 = self.shot.t(first, nth)
            t1 = self.shot.t(last, edge="end") if isinstance(last, str) else self.shot.t(first, nth, edge="end")
        else:
            t0, t1 = float(first), float(last)
        words = [w for w in self.shot.words if w["end"] > t0 - 1e-3 and w["start"] < t1 + 1e-3]
        if not words:
            n = max(1, int((t1 - t0) / 0.22))
            words = [{"text": "aeiou"[i % 5], "start": t0 + i * (t1 - t0) / n, "end": t0 + (i + 0.8) * (t1 - t0) / n} for i in range(n)]
        for w in words:
            txt = re.sub(r"[^a-z]", "", w["text"].lower())
            shapes = []
            if txt[:1] in "mbp":
                shapes.append("MBP")
            shapes += [c.upper() for c in txt if c in "aeiou"][:2] or ["E"]
            a, b = w["start"], max(w["end"], w["start"] + 0.08)
            step = (b - a) / len(shapes)
            for i, v in enumerate(shapes):
                fa, fb = self._f(a + i * step), self._f(a + (i + 1) * step)
                fm = max(fa + 1, (fa + fb) // 2)
                p = f'["viseme_{v}"]'
                for f, val in ((fa, 0.0), (fm, strength), (max(fm + 1, fb), 0.0)):
                    self.ctrl[f"viseme_{v}"] = val
                    self.ctrl.keyframe_insert(p, frame=f)
        return t1

    def blink(self, t: float):
        f = self._f(t)
        for o in self.parts:
            if o["cl_part"].startswith("Eye"):
                for fr, z in ((f - 1, 1.0), (f + 1, 0.12), (f + 2, 0.12), (f + 4, 1.0)):
                    o.delta_scale.z = z
                    o.keyframe_insert("delta_scale", index=2, frame=max(1, fr))
        return self

    def eyes(self, dx: float = 0.0, dz: float = 0.0, t: float = 0.0, blend: float = 0.1):
        """Where the eyes point: dx +1 = toward the facing side, -1 = back; dz +1 = up, -1 = down (the ring in the water).
        Eyes lead: look at a thing 0.2-0.3 s before reaching for it or reacting to it."""
        f1, f0 = self._f(t), self._f0(t, blend)
        for o in self.parts:
            if o["cl_part"].startswith(("Eye", "Brow")):
                k = 1.0 if o["cl_part"].startswith("Eye") else 0.5
                if f0 < f1:
                    o.keyframe_insert("delta_location", frame=f0)
                o.delta_location = (0.02 * dx * k, 0.0, 0.016 * dz * k)
                o.keyframe_insert("delta_location", frame=f1)
        return self

    def hand(self, side: str, shape: str, t: float = 0.0, blend: float = 0.1):
        """'mitten' (closed), 'open' (spread fingers: surprise, reaching, letting go), 'pinch' (holding something small, pointing)."""
        keys = [f"hand_{side}_open", f"hand_{side}_pinch"]
        f1, f0 = self._f(t), self._f0(t, blend)
        for k in keys:
            if f0 < f1:
                self.ctrl.keyframe_insert(f'["{k}"]', frame=f0)
        self.ctrl[keys[0]] = 1.0 if shape == "open" else 0.0
        self.ctrl[keys[1]] = 1.0 if shape == "pinch" else 0.0
        for k in keys:
            self.ctrl.keyframe_insert(f'["{k}"]', frame=f1)
        return self

    # ------------------------------------------------------------------ body
    def arm(self, side: str, raise_deg: float, bend_deg: float = 0.0, t: float = 0.0, blend: float = 0.25):
        """One arm. raise_deg: 0 hangs, 90 straight out (sideways in the front view, forward in 3q/side), 180 straight up.
        bend_deg: elbow; positive folds the forearm further up, negative folds it back toward the body."""
        up, lo = {}, {}
        for v in self.rigs:
            c = self._calib[v]
            d = self._dir(v, side)
            a_u = d * raise_deg
            a_l = d * (raise_deg + bend_deg)
            a0u, a0l = c[f"arm_upper.{side}"][2], c[f"arm_lower.{side}"][2]
            up[v] = a_u - a0u
            lo[v] = (a_l - a0l) - (a_u - a0u)
        self._key_bone(f"arm_upper.{side}", up, t, blend)
        self._key_bone(f"arm_lower.{side}", lo, t, blend)
        self._arm[side] = (raise_deg, bend_deg)
        return self

    def lean(self, deg: float, t: float = 0.0, blend: float = 0.3):
        """Bend at the hips: positive = forward (toward the facing side), negative = back. Legs stay planted."""
        self._key_bone("torso", {v: -deg for v in self.rigs}, t, blend)
        return self

    def tilt_head(self, deg: float, t: float = 0.0, blend: float = 0.2):
        """Positive = chin down / toward the facing side, negative = head back (laughing, looking up)."""
        self._key_bone("head", {v: -deg for v in self.rigs}, t, blend)
        return self

    def legs(self, raise_deg: float, bend_deg: float, t: float = 0.0, blend: float = 0.3, side: str = "LR"):
        """Thighs forward by raise_deg, knees folded back by bend_deg (sit: 86, 84). Reads in 3q and side views;
        the front view cannot show a forward leg, so seat people in three-quarter view."""
        for s in side:
            up, lo = {}, {}
            for v in self.rigs:
                k = 0.3 * (1 if s == "L" else -1) if v == "Front" else 1.0
                up[v] = k * raise_deg
                lo[v] = -k * bend_deg
            self._key_bone(f"leg_upper.{s}", up, t, blend)
            self._key_bone(f"leg_lower.{s}", lo, t, blend)
        return self

    def pose(self, name_or_spec, t: float = 0.0, blend: float = 0.25, side: str | None = None):
        """A named pose from POSES, or your own dict {"L": (raise, bend), "R": ..., "lean": d, "tilt": d, "hands": ..., "legs": (r, b)}.
        `side` swaps a one-armed pose to the other arm ("point", side="L")."""
        spec = dict(POSES[name_or_spec]) if isinstance(name_or_spec, str) else dict(name_or_spec)
        if side and side != "R" and "R" in spec and "L" not in spec:
            spec["L"] = spec.pop("R")
            if isinstance(spec.get("hands"), dict):
                spec["hands"] = {("L" if k == "R" else k): v for k, v in spec["hands"].items()}
        for s in "LR":
            if s in spec:
                self.arm(s, spec[s][0], spec[s][1], t, blend)
        if "lean" in spec:
            self.lean(spec["lean"], t, blend)
        if "tilt" in spec:
            self.tilt_head(spec["tilt"], t, blend)
        if "legs" in spec:
            self.legs(spec["legs"][0], spec["legs"][1], t, blend)
        h = spec.get("hands")
        if isinstance(h, str):
            for s in "LR":
                self.hand(s, h, t, min(blend, 0.12))
        elif isinstance(h, dict):
            for s, shape in h.items():
                self.hand(s, shape, t, min(blend, 0.12))
        return self

    def reach(self, side: str, target, t: float, blend: float = 0.3, elbow: str = "auto"):
        """Put a hand exactly on a world point, an object or an anchor at time t (the pose eases in over `blend`).
        If it is out of reach the arm stretches fully toward it; move the feet closer or lean first."""
        f = self._f(t)
        if bpy.context.scene.camera is None and not getattr(self.shot, "_reach_noted", False):
            self.shot._reach_noted = True
            self.shot.notes.append("reach() was called before the shot had a camera: flat figures turn to face the camera, so add the "
                                   "camera views first and the hand is solved for the real view")
        dg = core.at_frame(f)
        v = self._view_key()
        rig = self.rigs[v].evaluated_get(dg)
        c = self._calib[v]
        inv = rig.matrix_world.inverted()
        p = inv @ core.point_of(target)
        pb_u = rig.pose.bones[f"arm_upper.{side}"]
        s_pt = Vector((pb_u.head.x, pb_u.head.z))
        tgt = Vector((p.x, p.z))
        l1, l2 = c[f"arm_upper.{side}"][3], c[f"arm_lower.{side}"][3] + 0.8 * c[f"hand.{side}"][3]
        d = tgt - s_pt
        dist = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, d.length))
        phi = math.atan2(d.x, -d.y)
        alpha = math.acos(max(-1.0, min(1.0, (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist))))
        best = None
        for sgn in (1.0, -1.0):
            a_u = phi + sgn * alpha
            e_pt = s_pt + Vector((math.sin(a_u), -math.cos(a_u))) * l1
            tip = s_pt + Vector((math.sin(phi), -math.cos(phi))) * dist
            a_l = math.atan2(tip.x - e_pt.x, -(tip.y - e_pt.y))
            score = e_pt.y if elbow in ("auto", "down") else -e_pt.y           # prefer the lower elbow
            if best is None or score < best[0]:
                best = (score, a_u, a_l)
        _, a_u, a_l = best
        tb = rig.pose.bones["torso"]
        td = tb.tail - tb.head
        torso_delta = math.degrees(math.atan2(td.x, -td.z)) - c["torso"][2]
        torso_delta = (torso_delta + 180) % 360 - 180
        a_u_rel = math.degrees(a_u) - torso_delta
        a_l_rel = math.degrees(a_l) - torso_delta
        d_sign = self._dir(v, side)
        raise_deg = d_sign * ((a_u_rel + 180) % 360 - 180)
        bend = d_sign * (((a_l_rel - a_u_rel) + 180) % 360 - 180)
        self.arm(side, raise_deg, bend, t, blend)
        return self

    def rock(self, deg: float, t: float = 0.0, blend: float = 0.2, pivot: float | None = None):
        """Rotate the whole figure in the picture plane (positive = tips toward the facing side). pivot: height in metres
        of the turning point (0 = feet: tipping over; actor.height = hands overhead: swinging from a branch)."""
        if pivot is not None:
            self.tilt.location.z = pivot
            self.root.location.z = -pivot
        f1, f0 = self._f(t), self._f0(t, blend)
        if f0 < f1:
            self.tilt.keyframe_insert("rotation_euler", index=1, frame=f0)
        self.tilt.rotation_euler.y = math.radians(deg) * self._face
        self.tilt.keyframe_insert("rotation_euler", index=1, frame=f1)
        return self

    def squash(self, t: float, amount: float = 0.14, hold: float = 0.08, recover: float = 0.18):
        """A quick squash (landing, a jolt, a gulp) and spring back. Negative amount = stretch (anticipation, a startle)."""
        fps = self.shot.fps
        f = self._f(t)
        seq = ((f - 2, 1.0, 1.0), (f, 1.0 + amount * 0.6, 1.0 - amount), (f + max(1, int(hold * fps)), 1.0 + amount * 0.6, 1.0 - amount),
               (f + max(2, int((hold + recover * 0.5) * fps)), 1.0 - amount * 0.2, 1.0 + amount * 0.35), (f + max(3, int((hold + recover) * fps)), 1.0, 1.0))
        for fr, sx, sz in seq:
            self.tilt.scale = (sx, 1.0, sz)
            self.tilt.keyframe_insert("scale", frame=max(1, fr))
        return self

    def shake(self, t0: float, t1: float, amount: float = 2.5, rate: float = 9.0):
        """Small fast rocking: laughing, shivering, straining."""
        n = max(2, int((t1 - t0) * rate))
        self.tilt.keyframe_insert("rotation_euler", index=1, frame=self._f(t0))
        base = self.tilt.rotation_euler.y
        for i in range(1, n + 1):
            self.tilt.rotation_euler.y = base + (0.0 if i == n else math.radians(amount) * (1 if i % 2 else -1))
            self.tilt.keyframe_insert("rotation_euler", index=1, frame=self._f(t0 + (t1 - t0) * i / n))
        self.tilt.rotation_euler.y = base
        return self

    def hop(self, t: float, height: float = 0.18, dur: float = 0.32):
        """A small jump on the spot (surprise, joy)."""
        return self.move(t, t + dur, self._pos, arc=height)

    def move(self, t0: float, t1: float, to, arc: float = 0.0, linear: bool = False, land: bool = True):
        """Slide or fly the figure to a point without walking (a jump, a fall, being carried by something). arc = extra
        height at the middle of the path. For walking use walk()."""
        a = self._pos.copy()
        b = Vector((to[0], to[1], to[2] if len(to) > 2 else a.z))
        f0, f1 = self._f(t0), max(self._f(t0) + 1, self._f(t1))
        interp = "LINEAR" if linear else None
        self.stage.location = a
        core.key_frame(self.stage, "location", f0, interp=interp)
        if arc:
            fm = (f0 + f1) // 2
            m = (a + b) / 2
            m.z = max(a.z, b.z) + arc
            self.stage.location = m
            core.key_frame(self.stage, "location", fm)
            self._airborne.append((t0, t1))
            self.shot.airborne.append((self.id, t0, t1))
        self.stage.location = b
        core.key_frame(self.stage, "location", f1, interp=interp)
        self._pos = b.copy()
        if arc and land:
            self.squash(t1, 0.12)
        return t1

    def walk(self, t0: float, to, speed: float = 2.0, view: str | None = None, face: str | None = None, then_view: str | None = None):
        """Walk to (x, y) on the pack's walk cycle with planted feet. speed: 1 = the pack's stroll, 2 = brisk (default),
        3+ = a scurry. Returns the arrival time: key what happens next from it. Long walks eat screen time: start the walk,
        cut, and show the arrival."""
        a = self._pos.copy()
        b = Vector((to[0], to[1], to[2] if len(to) > 2 else a.z))
        dist = (b - a).length
        if dist < 1e-3:
            return t0
        fps = self.shot.fps
        f0 = self._f(t0)
        front = next(iter(self.rigs.values()))
        n_cycle = float(front["walk_cycle_frames"])
        stride = float(front["walk_stride"]) * self.scale
        cycles = max(0.5, round(dist / stride * 2) / 2)
        frames = max(2, int(round(cycles * n_cycle / speed)))
        f1 = f0 + frames
        t1 = (f1 - 1) / fps
        # which way on screen: decided from the camera at the start of the walk
        if face is None or view is None:
            cam = getattr(self.shot, "camera", None)
            right, fwd = Vector((1, 0, 0)), Vector((0, 1, 0))
            if cam is not None:
                core.at_frame(f0)
                m = cam.ob.matrix_world.to_3x3()
                right, fwd = m @ Vector((1, 0, 0)), m @ Vector((0, 0, -1))
            d = (b - a).normalized()
            sx, sy = d.dot(right), d.dot(fwd)
            if face is None:
                face = "right" if sx >= 0 else "left"
            if view is None:
                view = "front" if abs(sx) < 0.3 and sy < 0 else ("side" if abs(sx) > 0.85 else "3q")
        self.face(face, t0)
        self.view(view, t0)
        self.stage.location = a
        core.key_frame(self.stage, "location", f0, interp="LINEAR")
        self.stage.location = b
        core.key_frame(self.stage, "location", f1, interp="LINEAR")
        self._pos = b.copy()
        for rig in self.rigs.values():
            self._bake_cycle(rig, bpy.data.actions[rig["walk_action"]], f0, f1, speed, n_cycle)
        if then_view:
            self.view(then_view, t1)
        return t1

    def _bake_cycle(self, rig, action, f0: int, f1: int, speed: float, n_cycle: float):
        """Copy a looping pack action into the rig's own keys between two frames (so poses before and after stay editable)."""
        fcs = []
        try:
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        fcs.extend(bag.fcurves)
        except AttributeError:
            fcs = list(action.fcurves)
        chans = {}
        for fc in fcs:
            chans.setdefault(fc.data_path, []).append(fc)
        step = 2 if (f1 - f0) > 8 else 1
        frames = list(range(f0, f1, step)) + [f1]
        for path, group in chans.items():
            try:
                owner = rig.path_resolve(path.rsplit(".", 1)[0])
            except ValueError:
                continue
            prop = path.rsplit(".", 1)[1]
            if f0 > 1:
                for fc in group:
                    owner.keyframe_insert(prop, index=fc.array_index, frame=f0 - 1)
            rest = [0.0, 0.0, 0.0] if prop != "scale" else [1.0, 1.0, 1.0]
            for f in frames:
                src = ((f - f0) * speed) % n_cycle
                cur = list(getattr(owner, prop))
                for fc in group:
                    cur[fc.array_index] = rest[fc.array_index] if f == f1 else fc.evaluate(src)
                setattr(owner, prop, cur)
                for fc in group:
                    owner.keyframe_insert(prop, index=fc.array_index, frame=f)
        for fc in core.fcurves(rig):
            for kp in fc.keyframe_points:
                if f0 <= kp.co.x < f1:
                    kp.interpolation = "LINEAR"

    # ------------------------------------------------------------------ props in hands
    def hold(self, prop, side: str = "R", t: float = 0.0, offset=(0.0, 0.0, 0.0), front: bool = True):
        """From time t the prop follows the hand (in the view showing at that time: call again after a view change).
        offset: metres in the picture (x toward the facing side, y extra depth, z up) from the palm; front=False tucks the
        prop behind the figure. Turn the prop with its own rotation keys."""
        f = self._f(t)
        v = self._view_key()
        self._drop_holds(prop, f)
        grip = core.empty(f"{self.id}.grip.{side}.{len(self._held)}", (0, 0, 0), "CAST", 0.04)
        grip.parent = self.rigs[v]
        grip.parent_type = "BONE"
        grip.parent_bone = f"hand.{side}"
        dg = core.at_frame(f)
        gm = grip.evaluated_get(dg).matrix_world.to_3x3()
        sm = self.stage.evaluated_get(dg).matrix_world.to_3x3()
        depth = (-0.07 if front else 0.06) + offset[1]
        grip.location = gm.inverted() @ (sm @ Vector((offset[0] * self._face, depth, offset[2])))
        c = prop.constraints.new("COPY_LOCATION")
        c.name = f"hold_{self.id}.{len(self._held)}"
        c.target = grip
        if f > 1:
            c.influence = 0.0
            c.keyframe_insert("influence", frame=f - 1)
        c.influence = 1.0
        c.keyframe_insert("influence", frame=f)
        self._const_keys(prop, c)
        self._held[prop.name] = (c, grip)
        self.shot.props.setdefault(prop.name, prop)
        return self

    @staticmethod
    def _const_keys(prop, c):
        for fc in core.fcurves(prop):
            if fc.data_path == f'constraints["{c.name}"].influence':
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"

    def _drop_holds(self, prop, f: int):
        for c in prop.constraints:
            if c.name.startswith("hold_") and c.influence > 0:
                c.influence = 1.0
                c.keyframe_insert("influence", frame=max(1, f - 1))
                c.influence = 0.0
                c.keyframe_insert("influence", frame=f)
                self._const_keys(prop, c)

    def release(self, prop, t: float):
        """Let go at time t. The prop stays where the hand left it (its own location is keyed there), ready to fall or be
        moved with core.move(). Returns that world position."""
        f = self._f(t)
        dg = core.at_frame(max(1, f - 1))
        world = prop.evaluated_get(dg).matrix_world.translation.copy()
        self._drop_holds(prop, f)
        prop.location = world if prop.parent is None else prop.parent.matrix_world.inverted() @ world
        core.key_frame(prop, "location", f)
        self._held.pop(prop.name, None)
        return world

    # ------------------------------------------------------------------ life
    def idle(self, t0: float = 0.0, t1: float | None = None, seed: int | None = None, breathe: float = 1.0):
        """Blinks every few seconds and a slow breath, so a waiting character is alive. Call once, after the acting is keyed."""
        t1 = self.shot.seconds if t1 is None else t1
        rnd = random.Random(seed if seed is not None else hash(self.id) % 9973)
        t = t0 + rnd.uniform(0.6, 1.8)
        while t < t1 - 0.2:
            self.blink(t)
            t += rnd.uniform(1.9, 3.6)
        if breathe > 0:
            period = rnd.uniform(2.6, 3.4)
            n = max(1, int((t1 - t0) / (period / 2)))
            for v, rig in self.rigs.items():
                pb = rig.pose.bones["torso"]
                for i in range(n + 1):
                    pb.scale = (1.0 + 0.012 * breathe * (i % 2), 1.0 + 0.016 * breathe * (i % 2), 1.0)
                    pb.keyframe_insert("scale", frame=self._f(t0 + i * period / 2))
        return self

    # ------------------------------------------------------------------ wardrobe
    def recolor(self, **colors):
        """Change a colour of the costume by its pack name: recolor(tunic_tan="#7A1F2B", belt="#3B2A1A"). The names of a
        character's colours are in config/cast.json and `python tools/clip.py cast <Name>`."""
        names = {re.sub(r"^CL_", "", re.sub(r"[.][0-9]{3}$", "", k)): m for k, m in self._mats.items()}
        for key, hexcol in colors.items():
            m = names.get(key)
            if m is None:
                raise KeyError(f"{self.id} ({self.base}) has no colour '{key}'. It has: {', '.join(sorted(names))}")
            col = core.hex_rgba(hexcol)
            m.node_tree.nodes["base"].outputs[0].default_value = col
            m.diffuse_color = col
        return self

    def hide(self, *patterns):
        """Take parts off: hide("Helmet*") , hide("Belt*", "Tunic_Lace*"). Part names are in config/cast.json."""
        hit = 0
        for o in self.parts:
            if any(fnmatch.fnmatchcase(o["cl_part"], p) for p in patterns):
                o.hide_render = o.hide_viewport = True
                o["sk_off"] = True                               # taken off for good: view switches leave it alone
                hit += 1
        if not hit:
            names = sorted({o["cl_part"] for o in self.parts})
            raise KeyError(f"{self.id} ({self.base}): no part matches {patterns}. Parts: {', '.join(names)}")
        return self

    def wear(self, item: str, **opts):
        """Add a wardrobe piece (straw_hat, beret, ruff, apron, hood, kerchief, cloak, sash, ...): see stagekit.wardrobe."""
        from . import wardrobe
        wardrobe.wear(self, item, **opts)
        return self

    def add_part(self, name: str, view: str, pts, color, bone: str, layer: float, outline: bool = True, wire: bool = False):
        """Low level: one flat outlined shape in a view's picture plane (rig coordinates x, z in metres before scaling),
        riding a bone. layer = stacking order in pack units (hat 22, head 16.5, torso 9, cape 0): higher is nearer the camera."""
        rig = self.rigs[view]
        ng, ids = _outline_ids()
        cx = sum(p[0] for p in pts) / len(pts)
        cz = sum(p[1] for p in pts) / len(pts)
        me = bpy.data.meshes.new(f"{self.id}.{view}.{name}")
        verts = [(x - cx, 0.0, z - cz) for x, z in pts]
        n = len(pts)
        if wire:
            me.from_pydata(verts, [(i, i + 1) for i in range(n - 1)], [])
        else:
            me.from_pydata(verts, [], [list(range(n))])
        me.update()
        mat = color if hasattr(color, "node_tree") else flat_material(color, f"{self.id}.w.{color}")
        me.materials.append(mat)
        ob = bpy.data.objects.new(me.name, me)
        self.coll.objects.link(ob)
        ob.parent = rig
        ob.parent_type = "BONE"
        ob.parent_bone = bone
        b = rig.data.bones[bone]
        from mathutils import Matrix
        ob.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted()
        ob.location = (cx, -layer * 0.03, cz)
        md = ob.modifiers.new("Outline", "NODES")
        md.node_group = ng
        getattr(md.properties.inputs, ids["Width"]).value = 0.011 if outline else 0.0
        getattr(md.properties.inputs, ids["Material"]).value = self._outline_mat()
        getattr(md.properties.inputs, ids["Offset"]).value = 0.0
        fc = getattr(md.properties.inputs, ids["Visible"]).driver_add("value")
        d = fc.driver
        d.type = "SCRIPTED"
        var = d.variables.new()
        var.name = "v"
        var.type = "SINGLE_PROP"
        var.targets[0].id_type = "OBJECT"
        var.targets[0].id = self.root
        var.targets[0].data_path = '["view"]'
        d.expression = f"1.0 if v == {VIEWS.index(view)} else 0.0"
        ob["cl_part"] = name
        ob["cl_view"] = view
        self.parts.append(ob)
        if os.environ.get("CAST_CULL_VIEWS", "0") == "1":
            ob.hide_render = view != self._view_key()
        return ob

    def _outline_mat(self):
        ng, ids = _outline_ids()
        for o in self.parts:
            md = o.modifiers.get("Outline")
            if md:
                m = getattr(md.properties.inputs, ids["Material"]).value
                if m:
                    return m
        return flat_material("#2B1B1B", "SK_outline")

    def head_box(self, view: str):
        """(centre x, centre z, radius) of the head in a view's rig coordinates: wardrobe pieces are drawn in head units."""
        h = self._part("Head", view) or self._part("Skull", view)
        if h is None:
            return 0.0, self.head_z, self.head_r
        return float(h.location.x) if view == "Front" else 0.0, float(h.location.z), float(h.dimensions.z) / 2

    def torso_box(self, view: str):
        """(centre x, bottom z, top z, half width) of the torso drawing in a view's rig coordinates."""
        tpart = self._part("Torso", view)
        if tpart is None:
            return 0.0, 0.5, 1.03, 0.2
        x, z = float(tpart.location.x), float(tpart.location.z)
        hw, hh = float(tpart.dimensions.x) / 2, float(tpart.dimensions.z) / 2
        return x, z - hh, z + hh, hw


# ----------------------------------------------------------------------------- making actors
def _append(base: str):
    lib = core.pack_blend()
    with bpy.data.libraries.load(str(lib), link=False) as (src, dst):
        name = "CH_" + base
        if name not in src.collections:
            have = sorted(c[3:] for c in src.collections if c.startswith("CH_"))
            raise KeyError(f"the character pack has no '{base}'. It has: {', '.join(have)}")
        dst.collections = [name]
    coll = dst.collections[0]
    core.collection("CAST").children.link(coll)
    return coll


def actor(cid: str, base: str, at=(0, 0), face: str = "right", view: str = "3q", scale: float = 1.0, costume: dict | None = None) -> Actor:
    """Bring a pack character on stage. base: a pack name (Queen, Soldier, AdultMan, Barista, ...).
    costume: {"recolor": {...}, "hide": [...], "wear": [{"item": "straw_hat", ...}]} (the same dict the plan's cast uses)."""
    coll = _append(base)
    coll.name = f"CAST_{cid}"
    a = Actor(cid, base, coll, scale)
    a.place(at)
    a.face(face)
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


def from_plan(cid: str, at=(0, 0), face: str = "right", view: str = "3q") -> Actor:
    """The character exactly as the shot plan casts and dresses it (shotplan.json > cast)."""
    shot = core.current()
    entry = shot.cast_plan.get(cid)
    if entry is None:
        raise KeyError(f"cast id '{cid}' is not in the plan's cast: {', '.join(shot.cast_plan) or '(no plan loaded)'}")
    return actor(cid, entry["base"], at, face, view, float(entry.get("scale", 1.0)), entry.get("costume"))
