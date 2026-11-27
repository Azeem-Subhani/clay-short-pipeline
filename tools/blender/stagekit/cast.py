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

# Named poses.
# An arm is (raise, bend) or (raise, bend, plane), or "rest" (the arm as the pack draws it standing).
#   raise  degrees from hanging: 0 hangs, 90 level, 180 straight up
#   bend   elbow, added to raise for the forearm: positive folds it further the same way, negative folds it back
#   plane  "fwd": the arm moves toward where the character FACES (forward in three-quarter and side; toward the facing
#                 side of the screen in the front view, where it is the arm on that side that reads)
#          "out": the arm moves SIDEWAYS, away from the body (elbows out, hands on hips, arms flung wide). In the front
#                 view that is left and right; in three-quarter and side it is drawn the way an artist would turn the same
#                 pose: the near arm opens toward the back, the far arm toward the front, foreshortened.
# One pose is therefore one idea in every view. "views" overrides single views where a turned drawing needs its own angles.
# lean / tilt in degrees, positive forward (toward the facing side).
POSES = {
    "rest": {"L": "rest", "R": "rest", "lean": 0, "tilt": 0, "hands": "mitten"},
    "gasp": {"L": ("to", "beside_face"), "R": ("to", "beside_face"), "lean": -4, "tilt": -4, "hands": "open"},   # both hands fly up beside the face
    "hands_up": {"L": (150, 12, "out"), "R": (150, 12, "out"), "hands": "open",
                 "views": {"side": {"R": (138, 22), "L": (158, 14)}}},
    "cheer": {"L": (165, -10, "out"), "R": (165, -10, "out"), "lean": -5, "hands": "open",
              "views": {"side": {"R": (146, 14), "L": (166, 8)}}},
    "point": {"R": (88, 4), "hands": {"R": "point"}},
    "point_up": {"R": (76, 104), "hands": {"R": "point"},                                        # one finger raised: a rule, a warning
                 "views": {"3q": {"R": (62, 78)}, "side": {"R": (62, 78)}}},                     # turned: held out in front, clear of the face
    "offer": {"R": (70, 25), "hands": {"R": "open"}},
    "hips": {"L": ("to", "hip"), "R": ("to", "hip"), "lean": -3, "hands": "fist"},              # proud, hands on hips
    "proud": {"L": ("to", "hip"), "R": ("to", "hip"), "lean": -8, "tilt": -6, "hands": "fist"},
    "shrug": {"L": (30, 78, "out"), "R": (30, 78, "out"), "hands": "open", "tilt": 6,
              "views": {"3q": {"R": (16, 82), "L": (30, 76)}, "side": {"R": (14, 84), "L": (28, 78)}}},
    "think": {"R": ("to", "chin"), "L": "rest", "tilt": 6, "hands": {"R": "pinch"}},            # hand to the chin
    "facepalm": {"R": ("to", "brow"), "tilt": 14, "lean": 6, "hands": {"R": "open"}},
    "hang": {"L": (176, 4, "out"), "R": (176, 4, "out"), "hands": "fist",                         # arms straight up: hanging from something
             "views": {"side": {"R": (174, 4), "L": (186, 2)}}},
    "carry": {"L": (48, 62), "R": (48, 62), "hands": "fist",                                    # holding something in front of the chest
              "views": {"front": {"L": (30, -115, "out"), "R": (30, -115, "out")}}},
    "reach_down": {"R": (62, 10), "L": (24, 0), "lean": 48, "tilt": 12, "hands": {"R": "open"}},
    "pull": {"L": (70, 40), "R": (58, 55), "lean": -14, "hands": "fist"},
    "lift": {"L": (120, 30), "R": (120, 30), "lean": -6, "hands": "fist",
             "views": {"front": {"L": (128, 24, "out"), "R": (128, 24, "out")}}},
    "slump": {"L": "rest", "R": "rest", "lean": 14, "tilt": 16},
    "laugh": {"L": (40, 96, "out"), "R": ("to", "belly"), "lean": -12, "tilt": -12, "hands": "open",
              "views": {"3q": {"L": (64, 84)}, "side": {"L": (64, 84)}}},
    # wave: in the front view the acting arm goes up and out; turned, the near shoulder sits behind the big head and a raised
    # near hand would cross the face, so the FAR arm waves in front of the face instead (the hand is clear on the facing side)
    "wave": {"R": (118, 44, "out"), "hands": {"R": "open", "L": "open"},
             "views": {"3q": {"L": ("to", "beside_face", 0.05, 0.30), "R": "rest"}, "side": {"L": ("to", "beside_face", 0.05, 0.30), "R": "rest"}}},
    "sit": {"L": (30, 40), "R": (30, 40), "legs": (86, 84),
            "views": {"front": {"L": (14, -42, "out"), "R": (14, -42, "out")}}},
    "kneel": {"legs": (8, 98), "lean": 8},
    "hold_pole": {"L": (62, 58), "R": (84, 22), "hands": "fist"},                                 # both hands on a long tool
    # --- added with the action library (beta 0.4)
    "cross_arms": {"L": (28, 96, "out"), "R": (34, 104, "out"), "lean": -3, "hands": "fist",
                   "views": {"front": {"L": (22, -108, "out"), "R": (30, -112, "out")}, "3q": {"R": (26, 96), "L": (34, 88)},
                             "side": {"R": (26, 96), "L": (34, 88)}}},
    "cower": {"L": (60, 118), "R": (52, 126), "lean": 22, "tilt": 18, "hands": "open", "legs": (24, 44)},
    "beg": {"L": (64, 70), "R": (58, 78), "lean": 10, "tilt": -8, "hands": "open"},
    "pray": {"L": ("to", "chest", 0.0, 0.03), "R": ("to", "chest"), "tilt": 10, "hands": "mitten"},
    "cover_mouth": {"R": ("to", "mouth"), "tilt": 4, "hands": {"R": "mitten"}},
    "shield_eyes": {"R": ("to", "forehead"), "tilt": -6, "hands": {"R": "open"}},
    "push": {"L": (84, 12), "R": (92, 8), "lean": 16, "hands": "open"},
    "hug": {"L": (74, 46), "R": (86, 38), "lean": 8, "hands": "open"},
    "crouch": {"L": (26, 52), "R": (22, 60), "lean": 30, "tilt": -14, "legs": (58, 104)},
    "salute": {"R": ("to", "brow"), "hands": {"R": "open"}},
    "write": {"R": (42, 78), "L": (36, 60), "lean": 12, "tilt": 16, "hands": {"R": "pinch", "L": "open"}},
    "read": {"L": (44, 82), "R": (46, 78), "tilt": 14, "hands": "fist"},
    "drink": {"R": ("to", "mouth"), "tilt": -14, "hands": {"R": "fist"}},
    "phone": {"R": ("to", "ear"), "tilt": 4, "hands": {"R": "fist"}},
    "throw_back": {"R": (150, 60, "out"), "L": (70, 10), "lean": -14, "hands": {"R": "fist", "L": "open"},
                   "views": {"3q": {"R": (-150, -70), "L": (70, 10)}, "side": {"R": (-150, -70), "L": (70, 10)}}},
    "throw_fwd": {"R": (96, 6), "L": (-20, 20), "lean": 16, "hands": {"R": "open", "L": "fist"}},
    "fists_up": {"L": (52, 110), "R": (44, 118), "lean": 4, "hands": "fist"},
    "sleep": {"L": "rest", "R": "rest", "lean": 8, "tilt": 26},
    "hand_out": {"R": (56, 42), "hands": {"R": "open"}},
    "stop": {"R": (92, 30), "hands": {"R": "open"}},
}
K_OUT = {"ThreeQuarter": 0.70, "Side": 0.30}     # how much of a sideways arm a turned view still shows


def _proj(a_deg: float, k: float) -> float:
    """A sideways angle (degrees from hanging) as it is drawn when the body is turned: narrower, same height."""
    a = math.radians(a_deg)
    p = math.degrees(math.atan2(k * math.sin(a), math.cos(a)))
    while p - a_deg > 180:
        p -= 360
    while p - a_deg < -180:
        p += 360
    return p


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
        for k in list(self.ctrl.keys()):
            if k.startswith("hand_"):
                self.ctrl[k] = 0.0
        self.v4 = all("palm.R" in r.pose.bones for r in self.rigs.values())     # beta 0.4 pack: rigid limbs, grip, probes
        if self.v4:
            for r in self.rigs.values():                           # a foreshortened thigh must not squash the shin below it
                for bn in ("leg_lower.L", "leg_lower.R", "foot.L", "foot.R", "arm_lower.L", "arm_lower.R", "hand.L", "hand.R"):
                    r.data.bones[bn].inherit_scale = "NONE"
        self._fc = {}
        # stage (position + billboard) > tilt (rotation in the picture plane) > pack root (scale, mirror, depth)
        self.stage = core.empty(cid, (0, 0, 0), "CAST", 0.3)
        self.tilt = core.empty(f"{cid}.tilt", (0, 0, 0), "CAST", 0.1)
        self.tilt.parent = self.stage
        self.root.parent = self.tilt
        self.root.location = (0, 0, 0)
        self.root.rotation_euler = (0, 0, 0)
        self.root.scale = (self.scale, DEPTH, self.scale)
        if "back" in self.root.keys():
            self.root["back"] = 0
        self._face = 1
        self._view = "3q"
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
        self._arm = {"L": "rest", "R": "rest"}
        self.floating = False
        self._sink = (0.0, 0.0)
        try:                                                       # what replaces legs, walking, sitting for unusual bodies
            self.body = dict(registry()["characters"].get(base, {}).get("body", {}))
        except Exception:
            self.body = {}
        self._airborne = []
        self.view(self._view)
        if abs(self.scale - 1.0) > 1e-4:
            self._ink_scale()
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

    def _curve(self, ob, path: str, index: int):
        """The F-curve of one channel, if it has keys (cached per object)."""
        key = (ob.name, path, index)
        fc = self._fc.get(key)
        if fc is None:
            for c in core.fcurves(ob):
                self._fc[(ob.name, c.data_path, c.array_index)] = c
            fc = self._fc.get(key)
        return fc

    def _bone_value(self, rig, bone: str, k: int, frame: int) -> float:
        """A bone's keyed rotation at a frame (radians). The value the animation really has there, not whatever was set
        last in the script: holds are keyed from this, so a pose keyed out of time order never drags in a stale value."""
        fc = self._curve(rig, f'pose.bones["{bone}"].rotation_euler', k)
        if fc is not None and len(fc.keyframe_points):
            return fc.evaluate(frame)
        return rig.pose.bones[bone].rotation_euler[k]

    def _key_bone(self, bone: str, deg_by_view: dict, t: float, blend: float, mid: dict | None = None):
        """Turn a bone to a rotation (degrees, counter-clockwise in the picture) in every view rig, eased over `blend` seconds.
        mid: extra degrees at the middle of the move per view (the forearm drags or folds on the way: an arc, not a swing)."""
        f1 = self._f(t)
        f0 = self._f0(t, blend)
        for v, rig in self.rigs.items():
            pb = rig.pose.bones.get(bone)
            if pb is None or v not in deg_by_view:
                continue
            k, s, _a0, _l = self._calib[v][bone]
            e = list(pb.rotation_euler)
            start = self._bone_value(rig, bone, k, f0)
            if f0 < f1:
                e[k] = start
                pb.rotation_euler = e
                pb.keyframe_insert("rotation_euler", index=k, frame=f0)
            end = math.radians(deg_by_view[v] / s)
            if mid and mid.get(v) and f1 - f0 >= 5:
                e[k] = (start + end) / 2 + math.radians(mid[v] / s)
                pb.rotation_euler = e
                pb.keyframe_insert("rotation_euler", index=k, frame=(f0 + f1) // 2)
            e[k] = end
            pb.rotation_euler = e
            pb.keyframe_insert("rotation_euler", index=k, frame=f1)
        self._fc.clear()

    def _dir(self, view: str, side: str) -> float:
        """+1 if 'away from the body' is counter-clockwise for this arm in this view (kept for old callers)."""
        if view == "Front":
            return 1.0 if side == "L" else -1.0
        return 1.0

    def _mirror(self, view: str | None = None) -> float:
        """Sign of the pack root's X scale. Three-quarter and side drawings face +X, so they are flipped to look left.
        The FRONT drawing is flipped the other way round: the pack draws the right arm (the arm every one-armed pose and
        most props use) on the picture's left, so unflipped it would gesture away from the side the character attends to.
        With this the acting arm is on the facing side in all three views and stays on it through a view change."""
        v = view or self._view
        return float(self._face) * (-1.0 if v == "front" else 1.0)

    def _toward(self, view: str) -> float:
        """+1 if the facing side is +X in this view's rig, -1 if it is -X (the front view, see _mirror)."""
        return -1.0 if view == "Front" else 1.0

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

    def _set_mirror(self, t: float | None, before: float | None = None):
        # hold the old drawing direction up to the frame before. Only when it really changes: face() followed by view() on
        # the same frame would otherwise write the NEW direction on the frame before and flip the figure one frame early
        if t is not None and self._f(t) > 1 and before is not None and before != self._mirror():
            self.root.scale.x = before * self.scale
            core.key_frame(self.root, "scale", self._f(t) - 1, index=0, interp="CONSTANT")
        self.root.scale = (self._mirror() * self.scale, DEPTH, self.scale)
        if t is not None:
            core.key_frame(self.root, "scale", self._f(t), index=0, interp="CONSTANT")

    def face(self, side: str, t: float | None = None):
        """'right' or 'left' on screen: where the figure looks and gestures (in the front view: which side it attends to)."""
        before = self._mirror()
        self._face = 1 if str(side).lower().startswith("r") else -1
        self._set_mirror(t, before)
        return self

    def view(self, name: str, t: float | None = None):
        """Which drawing shows: 'front' (to camera), '3q' (the default: most alive), 'side' (profile, walking, pulling)."""
        idx = VIEW_INDEX[str(name).lower()]
        before = self._mirror()
        if t is not None and self._f(t) > 1:                  # hold the old drawing up to the frame before the switch
            core.key_frame(self.root, '["view"]', self._f(t) - 1, interp="CONSTANT")
        self._view = {0: "front", 1: "3q", 2: "side"}[idx]
        self.root["view"] = idx
        if t is not None:
            core.key_frame(self.root, '["view"]', self._f(t), interp="CONSTANT")
        self._set_mirror(t, before)
        self.root.update_tag()
        self._cull(self._f(t) if t is not None else None)
        if t is not None and getattr(self, "_held", None) and not getattr(self, "_reholding", False):
            # each drawing has its own hands: whatever is held moves into the hand of the drawing that now shows
            self._reholding = True
            try:
                for pname, h in list(self._held.items()):
                    pr = bpy.data.objects.get(pname)
                    if pr is not None and len(h) > 3:
                        self.hold(pr, h[2], t, **h[3])
            finally:
                self._reholding = False
        return self

    def turnaround(self, heading=(0.0, -1.0), t0: float = 0.0, t1: float | None = None, camera=None):
        """Let the camera go all the way round this figure. heading: the direction the figure faces IN THE WORLD, as (x, y)
        or as degrees (0 = toward the camera side -Y, 90 = toward +X, 180 = away from the camera side).
        From t0 to t1 the drawing is chosen on every frame from where the camera stands: front, three-quarter, side,
        three-quarter from behind, back - eight directions, like a turnaround sheet. Call it LAST, after the camera moves and
        the acting: it replaces the view() and face() keys in that span. Needs a character with back drawings
        (root["turnaround"]; `clip.py cast <Name>` says so); others raise an error."""
        if not bool(self.root.get("turnaround")):
            raise ValueError(f"{self.base} has no back drawings: build them first (BACKS in the pack's build script)")
        cam = camera or getattr(self.shot, "camera", None)
        cam_ob = getattr(cam, "ob", cam)
        if cam_ob is None:
            raise ValueError("turnaround needs the shot camera: make the camera views first")
        if isinstance(heading, (int, float)):
            a = math.radians(float(heading))
            h = Vector((math.sin(a), -math.cos(a)))
        else:
            h = Vector((float(heading[0]), float(heading[1])))
        h.normalize()
        f0 = self._f(t0)
        f1 = self._f(self.shot.seconds if t1 is None else t1)

        def loc(ob, f):
            v = [float(c) for c in ob.location]
            for fc in core.fcurves(ob):
                if fc.data_path == "location":
                    v[fc.array_index] = fc.evaluate(f)
            return Vector(v)

        def choose(f, prev):
            c = loc(cam_ob, f) - loc(self.stage, f)
            c = Vector((c.x, c.y))
            if c.length < 1e-6:
                return prev or ("front", 0, 1)
            c.normalize()
            ang = math.degrees(math.acos(max(-1.0, min(1.0, h.dot(c)))))      # 0 = camera in front of her, 180 = behind
            right = h.dot(Vector((-c.y, c.x)))                                 # > 0: she looks toward screen right
            SECT = (("front", 0, 0.0), ("3q", 0, 45.0), ("side", 0, 90.0), ("3q", 1, 135.0), ("front", 1, 180.0))
            best = min(SECT, key=lambda s_: abs(ang - s_[2]))
            if prev is not None:                                               # hysteresis: no flicker on a boundary
                was = next((s_ for s_ in SECT if s_[0] == prev[0] and s_[1] == prev[1]), None)
                if was is not None and abs(ang - was[2]) < 22.5 + 3.0:
                    best = was
            face = 1 if right >= 0 else -1
            if best[0] == "front" and prev is not None:                        # straight on or straight behind: keep the side she had
                face = prev[2]
            return (best[0], best[1], face)

        states = []
        prev = None
        for f in range(f0, f1 + 1):
            prev = choose(f, prev)
            states.append(prev)
        # this span belongs to the turnaround: drop the view / mirror keys that acting put there
        for fc in core.fcurves(self.root):
            if fc.data_path in ('["view"]', '["back"]') or (fc.data_path == "scale" and fc.array_index == 0):
                for i in range(len(fc.keyframe_points) - 1, -1, -1):
                    if f0 <= fc.keyframe_points[i].co.x <= f1:
                        fc.keyframe_points.remove(fc.keyframe_points[i])
        last = None
        for f, st in zip(range(f0, f1 + 1), states):
            if st == last:
                continue
            view, back, face = st
            self._view, self._face = view, face
            core.key_frame(self.root, '["view"]', f, VIEW_INDEX[view], interp="CONSTANT")
            core.key_frame(self.root, '["back"]', f, int(back), interp="CONSTANT")
            self.root.scale = (self._mirror() * self.scale, DEPTH, self.scale)
            core.key_frame(self.root, "scale", f, index=0, interp="CONSTANT")
            last = st
        self.root.update_tag()
        self.shot.notes.append(f"{self.id}: turnaround, {len(set(states))} drawings used over frames {f0}-{f1}")
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
        """Size on stage. The ink keeps the weight of an unscaled figure, so a small and a big character standing
        together are drawn with the same line."""
        self.scale = float(s)
        self.root.scale = (self._mirror() * self.scale, DEPTH, self.scale)
        self._ink_scale()
        return self

    def _ink_scale(self):
        _ng, ids = _outline_ids()
        k = 1.0 / max(self.scale, 1e-3)
        for o in self.parts:
            md = o.modifiers.get("Outline")
            if md is None:
                continue
            w = getattr(md.properties.inputs, ids["Width"])
            if "sk_w0" not in o.keys():
                o["sk_w0"] = float(w.value)
            w.value = o["sk_w0"] * k

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
                o.delta_location = (0.02 * dx * k * self._toward(o["cl_view"]), 0.0, 0.016 * dz * k)
                o.keyframe_insert("delta_location", frame=f1)
        return self

    HAND_SHAPES = ("mitten", "open", "pinch", "fist", "point", "grip")

    def hand(self, side: str, shape: str, t: float = 0.0, blend: float = 0.1):
        """'mitten' (relaxed), 'open' (spread fingers: surprise, reaching, letting go), 'pinch' (something small between
        finger and thumb), 'point' (one finger out), 'fist' (closed: effort, anger, knocking), 'grip' (closed round a held
        thing: the fingers are drawn over the prop; hold() sets it for you)."""
        if shape not in self.HAND_SHAPES:
            raise ValueError(f"unknown hand shape {shape!r}: use one of {self.HAND_SHAPES}")
        have = [k for k in (f"hand_{side}_{n}" for n in self.HAND_SHAPES[1:]) if k in self.ctrl.keys()]
        if f"hand_{side}_{shape}" not in have and shape not in ("mitten",):
            shape = {"point": "pinch", "fist": "mitten", "grip": "mitten"}.get(shape, shape)      # an older pack
        f1, f0 = self._f(t), self._f0(t, blend)
        for k in have:
            pop = k.endswith("_grip")                              # the finger overlay switches on a frame, it cannot fade
            fc = self._curve(self.ctrl, f'["{k}"]', 0)
            if f0 < f1 and not pop:
                if fc is not None and len(fc.keyframe_points):
                    self.ctrl[k] = fc.evaluate(f0)
                self.ctrl.keyframe_insert(f'["{k}"]', frame=f0)
            elif pop and f1 > 1:
                if fc is not None and len(fc.keyframe_points):
                    self.ctrl[k] = fc.evaluate(f1 - 1)
                core.key_frame(self.ctrl, f'["{k}"]', f1 - 1, interp="CONSTANT")
            self.ctrl[k] = 1.0 if k == f"hand_{side}_{shape}" else 0.0
            if pop:
                core.key_frame(self.ctrl, f'["{k}"]', f1, interp="CONSTANT")
            else:
                self.ctrl.keyframe_insert(f'["{k}"]', frame=f1)
        self._fc.clear()
        return self

    # ------------------------------------------------------------------ body
    def _arm_angles(self, view: str, side: str, spec) -> tuple:
        """(upper arm, forearm) picture angles in a view's rig: degrees, 0 = hanging, +90 = the rig's +X."""
        c = self._calib[view]
        if spec == "rest" or spec is None:
            return c[f"arm_upper.{side}"][2], c[f"arm_lower.{side}"][2]
        if spec[0] == "to":
            return self._arm_to(view, side, spec[1], spec[2] if len(spec) > 2 else 0.0, spec[3] if len(spec) > 3 else 0.0)
        raise_deg, bend_deg = float(spec[0]), float(spec[1])
        plane = spec[2] if len(spec) > 2 else "fwd"
        out_sign = 1.0 if side == "L" else -1.0
        if view == "Front":
            sg = out_sign if plane == "out" else self._toward(view)
            return sg * raise_deg, sg * (raise_deg + bend_deg)
        if plane == "out":
            k = K_OUT[view]
            return out_sign * _proj(raise_deg, k), out_sign * _proj(raise_deg + bend_deg, k)
        return raise_deg, raise_deg + bend_deg

    # places on the own body a hand can go to: ("to", "chin") in a pose. Head places are in head radii from the head centre
    # (x toward the facing side in 3q/side, toward the arm's own side in the front view), body places in metres.
    _HEAD_SPOTS = {  # name: (front x, front z, side x, three-quarter x, profile z, extra x for the far hand)
        "chin": (0.30, -1.02, 0.80, 0.86, -0.92, 0.10), "mouth": (0.12, -0.60, 1.04, 0.98, -0.50, 0.08),
        "cheek": (0.98, -0.30, 0.62, 0.80, -0.40, 0.25), "beside_face": (1.30, -0.15, 1.34, 1.40, -0.30, 0.22),
        "brow": (0.55, 0.42, 0.92, 0.95, 0.42, 0.06), "forehead": (0.30, 0.55, 0.98, 1.00, 0.55, 0.06),
        "ear": (1.04, -0.08, -0.12, -0.62, -0.10, 0.0), "top": (0.50, 1.04, 0.10, 0.20, 1.06, 0.25),
        "nape": (0.85, -0.75, -0.80, -0.85, -0.70, 0.0),
    }
    _BODY_SPOTS = {"hip": (1.0, 0.10), "belly": (0.10, 0.36), "chest": (0.12, 0.68), "heart": (0.30, 0.74), "pocket": (0.85, 0.02),
                   "belt": (0.30, 0.16)}

    def spot(self, view: str, side: str, name: str, dx: float = 0.0, dz: float = 0.0):
        """A named place on the figure's own body in a view's rig coordinates (x, z)."""
        rig = self.rigs[view]
        B = rig.data.bones
        hz, R = (float(B["head_c"].head_local.z) if "head_c" in B else self.head_z), self.head_r
        own = 1.0 if side == "L" else -1.0
        near = side == "R"
        tw = self._toward(view)
        if name in self._HEAD_SPOTS:
            fx, fz, px, qx, pz, far = self._HEAD_SPOTS[name]
            if view == "Front":
                return own * (fx * R) + tw * dx, hz + fz * R + dz
            x = ((qx if view == "ThreeQuarter" else px) + (0.0 if near else far)) * R
            return x + dx, hz + pz * R + dz
        if name not in self._BODY_SPOTS:
            raise KeyError(f"unknown body spot {name!r}: {', '.join(list(self._HEAD_SPOTS) + list(self._BODY_SPOTS))}")
        hip = float(B["torso"].head_local.z)
        neck = float(B["torso"].tail_local.z)
        shx = float(B[f"arm_upper.{side}"].head_local.x)
        H = neck - hip
        fx, fz = self._BODY_SPOTS[name]
        if view == "Front":
            return own * abs(shx) * fx + tw * dx, hip + fz * H + dz
        front_edge = 0.11 if view == "ThreeQuarter" else 0.09
        if name in ("hip", "pocket"):
            return shx + (0.02 if near else 0.05) + dx, hip + fz * H + dz
        return front_edge * (0.6 + fx) + (0.0 if near else 0.03) + dx, hip + fz * H + dz

    def _arm_to(self, view: str, side: str, name: str, dx: float = 0.0, dz: float = 0.0) -> tuple:
        """Two-bone solve in one view's rig: the palm on a body spot. Returns (upper, forearm) picture angles."""
        c = self._calib[view]
        B = self.rigs[view].data.bones
        sh = B[f"arm_upper.{side}"].head_local
        tx, tz = self.spot(view, side, name, dx, dz)
        l1 = c[f"arm_upper.{side}"][3]
        l2 = c[f"arm_lower.{side}"][3] + (0.5 if self.v4 else 0.8) * c[f"hand.{side}"][3]
        d = Vector((tx - sh.x, tz - sh.z))
        dist = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, d.length))
        phi = math.atan2(d.x, -d.y)
        alpha = math.acos(max(-1.0, min(1.0, (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist))))
        own = 1.0 if side == "L" else -1.0
        tipx, tipz = math.sin(phi) * dist, -math.cos(phi) * dist
        best = None
        for sgn in (1.0, -1.0):
            a_u = phi + sgn * alpha
            ex, ez = math.sin(a_u) * l1, -math.cos(a_u) * l1
            a_l = math.atan2(tipx - ex, -(tipz - ez))
            if name in self._HEAD_SPOTS:
                score = ez                                          # hand to the head: the elbow hangs low, clear of the face
            elif view == "Front":
                score = -own * ex                                   # elbow out to the arm's own side
            else:
                score = -((a_l - a_u + math.pi) % math.tau - math.pi)      # the elbow folds forward
            if best is None or score < best[0]:
                best = (score, a_u, a_l)
        a_u = (math.degrees(best[1]) + 180) % 360 - 180
        a_l = a_u + ((math.degrees(best[2] - best[1]) + 180) % 360 - 180)
        return a_u, a_l

    def _arm_views(self, side: str, spec_by_view: dict, t: float, blend: float, arc: bool = True):
        """Key one arm from a spec per view rig ("Front" / "ThreeQuarter" / "Side")."""
        up, lo, mid = {}, {}, {}
        f1, f0 = self._f(t), self._f0(t, blend)
        if not hasattr(self, "_armv"):
            self._armv = {}
        self._armv[side] = dict(spec_by_view)
        for v, rig in self.rigs.items():
            c = self._calib[v]
            a_u, a_l = self._arm_angles(v, side, spec_by_view[v])
            a0u, a0l = c[f"arm_upper.{side}"][2], c[f"arm_lower.{side}"][2]
            up[v] = a_u - a0u
            lo[v] = (a_l - a0l) - (a_u - a0u)
            if arc and f1 - f0 >= 5:
                # the forearm does not swing round stiff with the upper arm: on a big move it drags behind (sideways moves)
                # or folds in (moves toward the facing side), so the hand travels a short arc close to the body
                ku, su = c[f"arm_upper.{side}"][0], c[f"arm_upper.{side}"][1]
                was = math.degrees(self._bone_value(rig, f"arm_upper.{side}", ku, f0)) * su
                swing = up[v] - was
                if abs(swing) >= 45:
                    amount = min(34.0, 0.26 * abs(swing))
                    spec = spec_by_view[v]
                    plane = spec[2] if (spec != "rest" and spec is not None and len(spec) > 2 and spec[0] != "to") else "fwd"
                    if v == "Front" and plane == "out":
                        mid[v] = -amount if swing > 0 else amount
                    else:
                        mid[v] = amount * self._toward(v)
        self._key_bone(f"arm_upper.{side}", up, t, blend)
        self._key_bone(f"arm_lower.{side}", lo, t, blend, mid=mid)

    def arm(self, side: str, raise_deg: float, bend_deg: float = 0.0, t: float = 0.0, blend: float = 0.25, plane: str = "fwd"):
        """One arm. raise_deg: 0 hangs, 90 level, 180 straight up. bend_deg: elbow; positive folds the forearm further the
        same way, negative folds it back. plane="fwd" (default): toward where the figure faces (forward in 3q and side,
        the facing side of the screen in the front view); plane="out": sideways, away from the body, in every view."""
        spec = (raise_deg, bend_deg, plane)
        self._arm_views(side, {v: spec for v in self.rigs}, t, blend)
        self._arm[side] = spec
        return self

    def lean(self, deg: float, t: float = 0.0, blend: float = 0.3):
        """Bend at the hips: positive = forward (toward the facing side), negative = back. Legs stay planted."""
        self._key_bone("torso", {v: -deg * self._toward(v) for v in self.rigs}, t, blend)
        return self

    def tilt_head(self, deg: float, t: float = 0.0, blend: float = 0.2):
        """Positive = chin down / toward the facing side, negative = head back (laughing, looking up)."""
        self._key_bone("head", {v: -deg * self._toward(v) for v in self.rigs}, t, blend)
        return self

    def legs(self, raise_deg: float, bend_deg: float, t: float = 0.0, blend: float = 0.3, side: str = "LR", ground: bool = True):
        """Thighs forward by raise_deg, knees folded back by bend_deg (sit: 86, 84; kneel: 8, 98; crouch: 58, 104).
        With both legs the body sinks until the feet (or knees) are on the ground again, so a sitting, kneeling or
        crouching figure never hangs in the air; ground=False leaves the body where it is (legs dangling from a wall,
        a kick). In the front view a leg that comes toward the camera is drawn shorter instead of sideways."""
        f1, f0 = self._f(t), self._f0(t, blend)
        if getattr(self, "body", None) and not self.body.get("legs", True):
            # no legs to fold (ghost, mermaid, a genie on smoke): sitting, kneeling and crouching settle the whole body
            # lower by up to a third of the hip height instead; the hem or tail stays as drawn
            if set(side) == {"L", "R"} and ground:
                for v, rig in self.rigs.items():
                    hip = float(rig.data.bones["leg_upper.L"].head_local.z)
                    pb = rig.pose.bones["body"]
                    if f0 < f1:
                        pb.keyframe_insert("location", index=1, frame=f0)
                    pb.location[1] = -0.33 * hip * min(1.0, max(abs(raise_deg), abs(bend_deg)) / 90.0)
                    pb.keyframe_insert("location", index=1, frame=f1)
            self._sink = (raise_deg, bend_deg)
            return self
        th, sh = math.radians(raise_deg), math.radians(raise_deg - bend_deg)
        robe = bool(self.root.get("robe")) and self.v4          # a long skirt hides the legs: it gets a lap instead (pack 'Sit' key)
        for v, rig in self.rigs.items():
            c = self._calib[v]
            B = rig.data.bones
            sy_t = sy_s = 1.0
            short = v == "Front" or robe                           # legs drawn shorter instead of swung forward
            for s_ in side:
                if short:
                    k = 0.22 * (1 if s_ == "L" else -1) if v == "Front" else 0.0
                    sy_t, sy_s = max(0.22, abs(math.cos(th))), max(0.22, abs(math.cos(sh)))
                    up, lo = k * raise_deg, -k * raise_deg          # knees a little apart, shins straight down again
                    if abs(sh) > math.radians(60):                  # kneeling: the shins go away behind the knees
                        lo = -k * raise_deg
                else:
                    up, lo = raise_deg, -bend_deg
                flat = -(up + lo) if abs(up + lo) < 40 else 0.0     # the foot stays flat while the shin is near upright
                for bone, deg in ((f"leg_upper.{s_}", up), (f"leg_lower.{s_}", lo), (f"foot.{s_}", flat)):
                    self._key_bone(bone, {v: deg}, t, blend)
                if self.v4:
                    for bone, sy in ((f"leg_upper.{s_}", sy_t), (f"leg_lower.{s_}", sy_s)):
                        pb = rig.pose.bones[bone]
                        if f0 < f1:
                            pb.keyframe_insert("scale", index=1, frame=f0)
                        pb.scale[1] = sy
                        pb.keyframe_insert("scale", index=1, frame=f1)
            if set(side) == {"L", "R"} and ground:
                lt, ls = c["leg_upper.L"][3], c["leg_lower.L"][3]
                lf = c["foot.L"][3]
                hip = float(B["leg_upper.L"].head_local.z)
                if short:
                    a_t = math.radians(0.22 * raise_deg) if v == "Front" else 0.0
                    knee = hip - lt * sy_t * math.cos(a_t)
                    foot = knee - ls * sy_s - lf
                    low = min(foot, knee - 0.05) if abs(sh) > math.radians(60) else foot
                else:
                    knee = hip - lt * math.cos(th)
                    ankle = knee - ls * math.cos(sh)
                    foot = ankle - (lf if abs(math.degrees(sh)) < 40 else lf * abs(math.cos(sh)))
                    low = min(foot, knee - 0.05, hip - 0.07)
                pb = rig.pose.bones["body"]
                if f0 < f1:
                    fc = self._curve(rig, 'pose.bones["body"].location', 1)
                    if fc is not None and len(fc.keyframe_points):
                        pb.location[1] = fc.evaluate(f0)
                    pb.keyframe_insert("location", index=1, frame=f0)
                pb.location[1] = -low
                pb.keyframe_insert("location", index=1, frame=f1)
        self._fc.clear()
        self._sink = (raise_deg, bend_deg)
        return self

    _VIEW_KEY = {"front": "Front", "3q": "ThreeQuarter", "side": "Side"}

    def pose(self, name_or_spec, t: float = 0.0, blend: float = 0.25, side: str | None = None):
        """A named pose from POSES, or your own dict {"L": (raise, bend[, plane]), "R": ..., "lean": d, "tilt": d,
        "hands": ..., "legs": (r, b), "views": {"side": {...}}}. `side` swaps a one-armed pose to the other arm
        ("point", side="L")."""
        if isinstance(name_or_spec, str) and name_or_spec not in POSES:
            raise KeyError(f"unknown pose {name_or_spec!r}. Poses: {', '.join(POSES)}")
        spec = dict(POSES[name_or_spec]) if isinstance(name_or_spec, str) else dict(name_or_spec)
        views = {self._VIEW_KEY[k]: dict(v) for k, v in (spec.get("views") or {}).items()}

        def swap(d):
            if side and side != "R" and "R" in d and "L" not in d:
                d["L"] = d.pop("R")
                if isinstance(d.get("hands"), dict):
                    d["hands"] = {("L" if k == "R" else k): v for k, v in d["hands"].items()}
            return d

        spec = swap(spec)
        views = {k: swap(v) for k, v in views.items()}
        for s in "LR":
            if s in spec or any(s in v for v in views.values()):
                per = {v: views.get(v, {}).get(s, spec.get(s, self._arm[s])) for v in self.rigs}
                self._arm_views(s, per, t, blend)
                self._arm[s] = spec.get(s, self._arm[s])
        if "lean" in spec:
            self.lean(spec["lean"], t, blend)
        if "tilt" in spec:
            self.tilt_head(spec["tilt"], t, blend)
        if "legs" in spec:
            self.legs(spec["legs"][0], spec["legs"][1], t, blend)
        h = spec.get("hands")
        if isinstance(h, str):
            for s in "LR":
                if not self._grips(s):
                    self.hand(s, h, t, min(blend, 0.12))
        elif isinstance(h, dict):
            for s, shape in h.items():
                if not self._grips(s):
                    self.hand(s, shape, t, min(blend, 0.12))
        return self

    def _grips(self, side: str) -> bool:
        """True while that hand holds a prop (a pose must not open a hand that is carrying something)."""
        return any(h[2] == side for h in self._held.values())

    def _on_plane(self, rig_eval, world: Vector) -> Vector:
        """Where a world point shows on the figure's flat plane AS THE CAMERA SEES IT (rig coordinates). The figure is a
        card facing the camera; a target in front of or behind the card must be met where the camera's line of sight
        through the target crosses the card, or the hand lands beside the thing on screen."""
        inv = rig_eval.matrix_world.inverted()
        p = inv @ world
        cam = bpy.context.scene.camera
        if cam is None:
            return p
        cm = cam.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world
        if cam.data.type == "ORTHO":
            d = (inv.to_3x3() @ (cm.to_3x3() @ Vector((0, 0, -1))))
            o = p - d
        else:
            o = inv @ cm.translation
            d = p - o
        if abs(d.y) < 1e-9:
            return p
        k = -o.y / d.y
        if k <= 0:
            return p
        return o + d * k

    def reach(self, side: str, target, t: float, blend: float = 0.3, elbow: str = "auto"):
        """Put a hand exactly on a world point, an object or an anchor at time t, as seen by the camera (the pose eases in
        over `blend`). If it is out of reach the arm stretches fully toward it; move the feet closer or lean first.
        elbow: "auto" bends the natural way (forward in 3q/side, the lower elbow in the front view), or "up" / "down"."""
        f = self._f(t)
        if bpy.context.scene.camera is None and not getattr(self.shot, "_reach_noted", False):
            self.shot._reach_noted = True
            self.shot.notes.append("reach() was called before the shot had a camera: flat figures turn to face the camera, so add the "
                                   "camera views first and the hand is solved for the real view")
        dg = core.at_frame(f)
        v = self._view_key()
        rig = self.rigs[v].evaluated_get(dg)
        c = self._calib[v]
        p = self._on_plane(rig, core.point_of(target))
        pb_u = rig.pose.bones[f"arm_upper.{side}"]
        s_pt = Vector((pb_u.head.x, pb_u.head.z))
        tgt = Vector((p.x, p.z))
        l1 = c[f"arm_upper.{side}"][3]
        l2 = c[f"arm_lower.{side}"][3] + (0.5 if self.v4 else 0.8) * c[f"hand.{side}"][3]      # the palm, not the wrist
        d = tgt - s_pt
        dist = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, d.length))
        phi = math.atan2(d.x, -d.y)
        alpha = math.acos(max(-1.0, min(1.0, (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist))))
        toward = self._toward(v)
        best = None
        for sgn in (1.0, -1.0):
            a_u = phi + sgn * alpha
            e_pt = s_pt + Vector((math.sin(a_u), -math.cos(a_u))) * l1
            tip = s_pt + Vector((math.sin(phi), -math.cos(phi))) * dist
            a_l = math.atan2(tip.x - e_pt.x, -(tip.y - e_pt.y))
            flex = ((a_l - a_u + math.pi) % math.tau - math.pi) * toward          # > 0: the elbow folds the way an elbow does
            if elbow == "up":
                score = -e_pt.y
            elif elbow == "down" or v == "Front":
                score = e_pt.y
            else:
                score = -flex
            if best is None or score < best[0]:
                best = (score, a_u, a_l)
        _, a_u, a_l = best
        tb = rig.pose.bones["torso"]
        td = tb.tail - tb.head
        torso_delta = math.degrees(math.atan2(td.x, -td.z)) - c["torso"][2]
        torso_delta = (torso_delta + 180) % 360 - 180
        a_u_rel = (math.degrees(a_u) - torso_delta + 180) % 360 - 180
        bend_rel = ((math.degrees(a_l - a_u)) + 180) % 360 - 180
        # the same angle can be written 360 apart: take the one nearest to where the arm is, inside what a shoulder can do,
        # so the blend never swings the long way round through the body
        ku, su = c[f"arm_upper.{side}"][0], c[f"arm_upper.{side}"][1]
        now = math.degrees(self._bone_value(self.rigs[v], f"arm_upper.{side}", ku, self._f0(t, blend))) * su + c[f"arm_upper.{side}"][2]
        while a_u_rel - now > 180:
            a_u_rel -= 360
        while a_u_rel - now < -180:
            a_u_rel += 360
        if a_u_rel * toward > 250 or a_u_rel * toward < -200:
            a_u_rel -= 360 * (1 if a_u_rel > 0 else -1)
        # written back as (raise, bend, plane) so the other two drawings take the matching pose
        if v == "Front":
            sg = 1.0 if side == "L" else -1.0
            spec = (sg * a_u_rel, sg * bend_rel, "out")
        else:
            spec = (a_u_rel, bend_rel, "fwd")
        self._arm_views(side, {vv: spec for vv in self.rigs}, t, blend, arc=False)
        self._arm[side] = spec
        return self

    def aim(self, side: str, target, t: float, blend: float = 0.25, bend: float = 6.0):
        """Straighten an arm toward a point, an object or an anchor, as seen by the camera (pointing, aiming a torch or a
        sword). Unlike reach() the hand does not have to get there: the arm just lines up with it."""
        f = self._f(t)
        dg = core.at_frame(f)
        v = self._view_key()
        rig = self.rigs[v].evaluated_get(dg)
        c = self._calib[v]
        p = self._on_plane(rig, core.point_of(target))
        pb_u = rig.pose.bones[f"arm_upper.{side}"]
        d = Vector((p.x - pb_u.head.x, p.z - pb_u.head.z))
        phi = math.degrees(math.atan2(d.x, -d.y))
        tb = rig.pose.bones["torso"]
        td = tb.tail - tb.head
        torso_delta = (math.degrees(math.atan2(td.x, -td.z)) - c["torso"][2] + 180) % 360 - 180
        a_u = (phi - torso_delta + 180) % 360 - 180
        toward = self._toward(v)
        a_u -= bend * 0.5 * toward
        if v == "Front":
            sg = 1.0 if side == "L" else -1.0
            spec = (sg * a_u, sg * bend * toward, "out")
        else:
            spec = (a_u, bend, "fwd")
        self._arm_views(side, {vv: spec for vv in self.rigs}, t, blend)
        self._arm[side] = spec
        return self

    def wrist(self, side: str, deg: float, t: float = 0.0, blend: float = 0.15):
        """Turn the hand at the wrist (positive tips it toward the facing side: pouring, turning a key). A prop held with
        hold(..., turn=True) turns with it."""
        self._key_bone(f"hand.{side}", {v: deg * self._toward(v) for v in self.rigs}, t, blend)
        return self

    def _wag(self, side: str, deg: float, t: float, blend: float = 0.12):
        """Swing the forearm a few degrees either side of the pose the arm is in (waving, writing, fiddling)."""
        lo = {}
        for v in self.rigs:
            c = self._calib[v]
            spec = getattr(self, "_armv", {}).get(side, {}).get(v, self._arm[side])
            if spec == "rest" or spec is None:
                continue                                           # that arm hangs in this view: leave it alone
            a_u, a_l = self._arm_angles(v, side, spec)
            lo[v] = (a_l - c[f"arm_lower.{side}"][2]) - (a_u - c[f"arm_upper.{side}"][2]) + deg * self._toward(v)
        self._key_bone(f"arm_lower.{side}", lo, t, blend)
        return self

    def head_turn(self, amount: float, t: float = 0.0, blend: float = 0.12):
        """A quick turn of the head left (-1) or right (+1) and back to 0: shaking the head, a double take."""
        self._key_bone("head", {v: -7.0 * amount for v in self.rigs}, t, blend)
        self.eyes(0.9 * amount * (1 if self._view != "front" else -1), 0.0, t, blend)
        return self

    def eyes_closed(self, t0: float, t1: float):
        """Eyes shut from t0 to t1 (sleeping, a long blink, a flinch)."""
        f0, f1 = self._f(t0), max(self._f(t0) + 3, self._f(t1))
        for o in self.parts:
            if o["cl_part"].startswith("Eye"):
                for fr, z in ((f0 - 1, 1.0), (f0 + 1, 0.12), (f1 - 1, 0.12), (f1 + 1, 1.0)):
                    o.delta_scale.z = z
                    o.keyframe_insert("delta_scale", index=2, frame=max(1, fr))
        return self

    def ctrl_pulse(self, prop: str, t0: float, t1: float, amount: float = 1.0):
        """A face control up and down again: ctrl_pulse("viseme_O", t0, t1) is an "oh!", a yawn, a blown breath."""
        if prop not in self.ctrl.keys():
            return self
        f0, f1 = self._f(t0), max(self._f(t0) + 3, self._f(t1))
        for fr, val in ((f0 - 1, 0.0), (f0 + 1, amount), (f1 - 1, amount), (f1 + 1, 0.0)):
            self.ctrl[prop] = val
            self.ctrl.keyframe_insert(f'["{prop}"]', frame=max(1, fr))
        return self

    def chew(self, t0: float, t1: float, rate: float = 4.5):
        """Closed-mouth chewing between two times."""
        n = max(1, int((t1 - t0) * rate))
        for i in range(n):
            a = t0 + (t1 - t0) * i / n
            self.ctrl_pulse("viseme_MBP" if i % 2 == 0 else "viseme_E", a, a + (t1 - t0) / n * 0.8, 0.8)
        return self

    def do(self, name: str, *args, **kw) -> float:
        """Perform a named action from stagekit.actions: a.do("pick_up", ring, hit=shot.t("picked up")),
        a.do("wave", t), a.do("hand_over", key, to=b, t=3.2). Returns the time it ends. `python tools/clip.py actions`
        lists them all."""
        from . import actions
        return actions.run(self, name, *args, **kw)

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

    def walk(self, t0: float, to, speed: float = 2.0, view: str | None = None, face: str | None = None, then_view: str | None = None,
             arms: bool = True, cycle: str = "walk"):
        """Walk to (x, y) on the pack's walk cycle with planted feet. speed: 1 = the pack's stroll, 2 = brisk (default),
        3+ = a scurry. Returns the arrival time: key what happens next from it. Long walks eat screen time: start the walk,
        cut, and show the arrival. cycle="run" / "sneak" use the pack's run and creeping cycles (speed 1 = their own pace).
        arms=False leaves the arms as posed (carrying, pointing, hands raised) and only the legs and body walk."""
        a = self._pos.copy()
        b = Vector((to[0], to[1], to[2] if len(to) > 2 else a.z))
        dist = (b - a).length
        if dist < 1e-3:
            return t0
        fps = self.shot.fps
        f0 = self._f(t0)
        front = next(iter(self.rigs.values()))
        if f"{cycle}_action" not in front.keys():
            cycle = "walk"                                        # an older pack has only the walk
        n_cycle = float(front[f"{cycle}_cycle_frames"])
        stride = float(front[f"{cycle}_stride"]) * self.scale
        cycles = max(0.5, round(dist / stride * 2) / 2)
        frames = max(2, int(round(cycles * n_cycle / speed)))
        # the cycle covers cycles x stride, the walk has to cover dist: the legs swing a little wider or narrower so the
        # planted foot stays exactly where it was put (no sliding), instead of the body skating the difference
        fit = max(0.7, min(1.35, dist / (cycles * stride)))
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
        # a walk that follows straight on another (pacing, a turn and back) carries on with the foot that is on the ground,
        # instead of starting the cycle again on the other foot
        last = getattr(self, "_walk_last", None)
        phase = last[1] if last and last[2] == cycle and 0 <= f0 - last[0] <= 4 else 0.0
        self._walk_last = (f1, (phase + cycles * n_cycle) % n_cycle, cycle)
        for rig in self.rigs.values():
            act_ = rig.get(f"{cycle}_ref") or bpy.data.actions[rig[f"{cycle}_action"]]
            self._bake_cycle(rig, act_, f0, f1, cycles * n_cycle / frames, n_cycle, arms=arms, fit=fit, phase=phase)
        self._fc.clear()
        if arms:
            self._arm = {"L": "rest", "R": "rest"}
        if then_view:
            self.view(then_view, t1)
        return t1

    def _bake_cycle(self, rig, action, f0: int, f1: int, speed: float, n_cycle: float, arms: bool = True, fit: float = 1.0,
                    settle: int = 4, phase: float = 0.0):
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
            if not arms and ('"arm_' in fc.data_path or '"hand.' in fc.data_path):
                continue                                           # the arms keep the pose they have (carrying, sneaking, pointing)
            chans.setdefault(fc.data_path, []).append(fc)
        step = 2 if (f1 - f0) > 8 else 1
        frames = list(range(f0, f1, step)) + [f1]
        for path, group in chans.items():
            try:
                owner = rig.path_resolve(path.rsplit(".", 1)[0])
            except ValueError:
                continue
            prop = path.rsplit(".", 1)[1]
            if f0 > 1:                                             # hold what the animation really has just before the walk
                cur = list(getattr(owner, prop))
                for fc in group:
                    old_fc = self._curve(rig, path, fc.array_index)
                    if old_fc is not None and len(old_fc.keyframe_points):
                        cur[fc.array_index] = old_fc.evaluate(f0 - 1)
                setattr(owner, prop, cur)
                for fc in group:
                    owner.keyframe_insert(prop, index=fc.array_index, frame=f0 - 1)
                self._fc.clear()
            # keys an earlier move left inside this walk (the settle of a walk that ended on this frame, a late pose key)
            # would pull the legs to rest for one frame in the middle of a step
            for fc in group:
                old_fc = self._curve(rig, path, fc.array_index)
                if old_fc is not None:
                    for i in range(len(old_fc.keyframe_points) - 1, -1, -1):
                        if f0 <= old_fc.keyframe_points[i].co.x <= f1 + settle:
                            old_fc.keyframe_points.remove(old_fc.keyframe_points[i])
            self._fc.clear()
            rest = [0.0, 0.0, 0.0] if prop != "scale" else [1.0, 1.0, 1.0]
            leg = prop == "rotation_euler" and ('"leg_' in path or '"foot.' in path)
            for f in frames:
                src = (phase + (f - f0) * speed) % n_cycle
                cur = list(getattr(owner, prop))
                for fc in group:
                    cur[fc.array_index] = fc.evaluate(src) * (fit if leg else 1.0)
                setattr(owner, prop, cur)
                for fc in group:
                    owner.keyframe_insert(prop, index=fc.array_index, frame=f)
            # the walk arrives on a passing position (one foot under the body, the other in the air above it): the last
            # step is that foot coming straight down over a few frames, not a foot dragged along the ground
            cur = list(getattr(owner, prop))
            for fc in group:
                cur[fc.array_index] = rest[fc.array_index]
            setattr(owner, prop, cur)
            for fc in group:
                owner.keyframe_insert(prop, index=fc.array_index, frame=f1 + settle)
        for fc in core.fcurves(rig):
            for kp in fc.keyframe_points:
                if f0 <= kp.co.x < f1:
                    kp.interpolation = "LINEAR"
                elif f1 <= kp.co.x <= f1 + settle:
                    kp.interpolation = "SINE"

    # ------------------------------------------------------------------ props in hands
    def hold(self, prop, side: str = "R", t: float = 0.0, offset=(0.0, 0.0, 0.0), front: bool = True, grip: bool = True,
             turn: bool = False):
        """From time t the prop sits in the PALM and follows the hand (in the view showing at that time: call again after
        a view change). The hand closes round it: the palm is drawn behind the prop and the fingers in front of it.
        offset: metres in the picture (x toward the facing side, y extra depth, z up) from the palm; front=False tucks the
        prop behind the figure (no fingers drawn); grip=False lays it on an open hand (a coin on a palm, a tray).
        turn=True makes the prop also turn with the hand (a tool, a sword, a cup that must tip); otherwise it keeps its
        own rotation and you turn it with its own keys."""
        f = self._f(t)
        v = self._view_key()
        self._drop_holds(prop, f)
        old = self._held.pop(prop.name, None)
        if old is not None and old[2] != side and not self._grips(old[2]):
            self._fingers(old[2], f, None)                         # it changes hands: the old hand opens
            self.hand(old[2], "mitten", t, 0.06)
        n = getattr(self, "_hold_n", 0)
        self._hold_n = n + 1
        rig0 = self.rigs[v]
        bone = f"palm.{side}" if self.v4 else f"hand.{side}"
        grip_e = core.empty(f"{self.id}.grip.{side}.{n}", (0, 0, 0), "CAST", 0.04)
        grip_e.parent = rig0
        grip_e.parent_type = "BONE"
        grip_e.parent_bone = bone
        dg = core.at_frame(f)
        ge = grip_e.evaluated_get(dg)
        gm = ge.matrix_world.to_3x3()
        sm = self.stage.evaluated_get(dg).matrix_world.to_3x3()
        # depth: just in front of the highest layer a hand can be lifted to (over the head), by half the prop's thickness
        thick = self._thickness(prop)
        d_prop = (-(0.066 + thick / 2) if front else 0.06) + offset[1]
        rig_e = rig0.evaluated_get(dg)
        pb = rig_e.pose.bones[bone]
        palm_w = rig_e.matrix_world @ (pb.head if self.v4 else (pb.head + pb.tail) / 2)
        want = palm_w + sm @ Vector((offset[0] * self._face, d_prop, offset[2]))
        grip_e.location = gm.inverted() @ (want - ge.matrix_world.translation)
        cons = []
        c = prop.constraints.new("COPY_LOCATION")
        c.name = f"hold_{self.id}.{n}"
        c.target = grip_e
        cons.append(c)
        if turn:
            # the prop keeps the angle it has now relative to the hand, then turns with it
            turn_e = core.empty(f"{self.id}.turn.{side}.{n}", (0, 0, 0), "CAST", 0.04)
            turn_e.parent = self.stage
            bpy.context.view_layer.update()
            c2 = turn_e.constraints.new("COPY_ROTATION")
            c2.target = rig0
            c2.subtarget = f"hand.{side}"
            c3 = prop.constraints.new("CHILD_OF")
            c3.name = f"hold_turn_{self.id}.{n}"
            c3.target = turn_e
            c3.use_location_x = c3.use_location_y = c3.use_location_z = False
            c3.use_scale_x = c3.use_scale_y = c3.use_scale_z = False
            core.at_frame(f)
            c3.inverse_matrix = turn_e.matrix_world.inverted()
            prop.constraints.move(len(prop.constraints) - 1, max(0, len(prop.constraints) - 2))     # rotate first, then sit in the palm
            cons.append(c3)
        for cc in cons:
            if f > 1:
                cc.influence = 0.0
                cc.keyframe_insert("influence", frame=f - 1)
            cc.influence = 1.0
            cc.keyframe_insert("influence", frame=f)
            self._const_keys(prop, cc)
        self._held[prop.name] = (cons, grip_e, side, {"offset": tuple(offset), "front": front, "grip": grip, "turn": turn})
        self.shot.props.setdefault(prop.name, prop)
        if front and grip and self.v4:
            self.hand(side, "grip", t, 0.0)
            self._fingers(side, f, -(0.066 + thick + 0.004) / DEPTH)
        elif grip is False:
            self.hand(side, "open", t, 0.06)
        return self

    @staticmethod
    def _thickness(prop) -> float:
        """How deep a prop is along the smallest side of its box (metres, clamped): the room the fingers must leave."""
        try:
            lo, hi = core.world_bbox([prop, *[o for o in prop.children_recursive if o.type == "MESH"]])
            return max(0.006, min(0.08, min(hi - lo)))
        except Exception:
            return 0.02

    def _fingers(self, side: str, frame: int, y: float | None):
        """Put the finger overlay of that hand at a depth (pack units, in every view) from a frame on; None = back home."""
        for o in self.parts:
            if o["cl_part"] != f"Hand_Grip.{side}":
                continue
            if "sk_y0" not in o.keys():
                o["sk_y0"] = float(o.location.y)
            if frame > 1:
                o.keyframe_insert("location", index=1, frame=frame - 1)
            o.location.y = o["sk_y0"] if y is None else min(o["sk_y0"], y)
            o.keyframe_insert("location", index=1, frame=frame)
            for fc in core.fcurves(o):
                if fc.data_path == "location" and fc.array_index == 1:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"

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

    def release(self, prop, t: float, hand: str | None = "open"):
        """Let go at time t. The prop stays where the hand left it (its own location and rotation are keyed there), ready to
        fall or be moved with core.move(). The hand opens (hand=None leaves it as it is). Returns that world position."""
        f = self._f(t)
        dg = core.at_frame(max(1, f - 1))
        pe = prop.evaluated_get(dg)
        world = pe.matrix_world.translation.copy()
        rot = pe.matrix_world.to_euler()
        held = self._held.pop(prop.name, None)
        turned = bool(held) and len(held[0]) > 1
        self._drop_holds(prop, f)
        prop.location = world if prop.parent is None else prop.parent.matrix_world.inverted() @ world
        core.key_frame(prop, "location", f)
        if turned and prop.parent is None:
            if f > 1:
                prop.keyframe_insert("rotation_euler", frame=f - 1)
            prop.rotation_euler = rot
            core.key_frame(prop, "rotation_euler", f, interp="CONSTANT")
        if held:
            side = held[2]
            if not self._grips(side):
                self._fingers(side, f, None)
                if hand:
                    self.hand(side, hand, t, 0.08)
        return world

    # ------------------------------------------------------------------ life
    def idle(self, t0: float = 0.0, t1: float | None = None, seed: int | None = None, breathe: float = 1.0):
        """Blinks every few seconds and a slow breath, so a waiting character is alive. Call once, after the acting is keyed."""
        t1 = self.shot.seconds if t1 is None else t1
        rnd = random.Random(seed if seed is not None else core.stable_seed(self.id))
        t = t0 + rnd.uniform(0.6, 1.8)
        while t < t1 - 0.2:
            self.blink(t)
            t += rnd.uniform(1.9, 3.6)
        # living parts the pack marks with cl_wiggle = [degrees, period, phase]: wings, tails, antennae, flames
        for o in self.parts:
            wg = o.get("cl_wiggle")
            if not wg:
                continue
            amp, per, ph = float(wg[0]), max(0.08, float(wg[1])), float(wg[2])
            n = max(2, int((t1 - t0) / (per / 2)))
            for i in range(n + 1):
                o.delta_rotation_euler[1] = math.radians(amp) * (1 if (i + int(round(ph * 2))) % 2 else -1)
                o.keyframe_insert("delta_rotation_euler", index=1, frame=self._f(t0 + i * per / 2))
        if self.body.get("hover"):                                  # a floating body bobs gently instead of standing
            hv = float(self.body.get("hover") if not isinstance(self.body.get("hover"), bool) else 0.035)
            n = max(2, int((t1 - t0) / 1.1))
            for rig in self.rigs.values():
                pb = rig.pose.bones["body"]
                for i in range(n + 1):
                    pb.location[1] = hv * (i % 2)
                    pb.keyframe_insert("location", index=1, frame=self._f(t0 + i * 1.1))
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
        z0, z1 = z - hh, z + hh
        rig = self.rigs.get(view)
        bones = rig.data.bones if rig is not None else {}
        if "leg_upper.L" in bones:
            hip = float(bones["leg_upper.L"].head_local.z) - 0.03
            if z0 < hip - 0.06 and hip < z1:
                # a gown or robe: wardrobe pieces are sized to the upper body (shoulders to hip), not to the whole skirt
                xs = [abs(float(v.co.x)) for v in tpart.data.vertices if z + float(v.co.z) >= hip]
                z0 = hip
                if xs:
                    hw = max(xs)
        return x, z0, z1, hw


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
    costume: {"recolor": {...}, "hide": [...], "wear": [{"item": "straw_hat", ...}]} (the same dict the plan's cast uses).
    A character with a sheet in config/cast3d.json comes on as a 3D figure (stagekit.cast3d); CAST_STYLE=2d in .env keeps the flat pack."""
    from . import cast_aj
    if cast_aj.has(base):                                     # an Aj character (config/cast.json, family "aj") or bare Aj body
        return cast_aj.actor(cid, base, at, face, view, scale, costume)
    if os.environ.get("CAST_STYLE", "3d").lower() != "2d":
        from . import cast3d
        if cast3d.has(base):
            return cast3d.actor(cid, base, at, face, view, scale, costume)
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
