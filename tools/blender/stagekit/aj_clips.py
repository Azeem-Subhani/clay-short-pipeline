"""aj_clips - Mixamo motion clips on Aj actors: the registry, loading by time, retargeting, analysis and baking.

    a.play_clip("Stand_To_Sit", t0=1.2)                       # the clip takes over the body; returns its end time
    a.play_clip("Standard_Walk", 0.5, groups=("legs", "spine", "arm.L", "head"), loop=True, until=3.0)
    a.walk(0.5, (2, 0))                                       # Standard_Walk, feet planted, ease in and out
    aj_clips.require("Jump")                                  # MissingClip(name, ask) when the file is not there

How a clip drives the figure (the choice and why). The bones of an Aj actor follow a hidden control rig of empties
(stagekit.aj_rig). A clip does NOT switch those bindings off: while it owns a group of joints, the empties of that
group are keyed from the clip, one key per pipeline frame. So
  * there is never a pop: a clip blends in from whatever the empties were doing (a slerp over `blend` seconds) and,
    when it ends, the empties simply hold its last pose; whatever is keyed next starts from there;
  * aj_rig.binding_error keeps its meaning (the bones are where the empties are, clip or not), and every measuring
    call of the actor (reach, hold, _torso_inv, hand_point) sees the clip's body, because it IS the rig;
  * the procedural layers keep working: the face, the eyes and the fingers are other channels; an arm the clip does
    not own (groups without "arm.R") is posed by the actor API on top of the clip's spine, so a character can carry,
    point or wave while walking; head_turn / tilt_head are ADDED to the clip's head and neck (the actor records them
    on its control empty as head_turn / head_tilt and the layer composes them at _finalize).
A layer is written at once (so the rest of the build sees it) and written again at _finalize, in the order the
layers were made, so a procedural key that landed inside a clip's range afterwards cannot leave a spike.

Retargeting is variants.retarget's: bone rotations are the clip's own local rotations on the actor's own rest pose
(so a senior keeps his bent stance), the Hips translation is scaled by the leg-length ratio (aj_root_scale) and lives
in model space, which the actor's world scale then scales; a constant shift puts the feet on the floor (measured on
Standing_Idle for that body). Clips are sampled by TIME: clip seconds = (pipeline frame - start) / 24 * rate, so a
30 fps clip plays at its real speed at 24 fps.

Root motion: in-place clips (walks, idles) keep their hip sway; clips that travel (sitting down moves the hips back,
a fall, getting up) give their horizontal hip travel to the stage, so after the clip the actor's position is where
its body is and the next clip starts from there.

Not handled: uneven or stepped floors (every clip assumes a flat floor at the actor's own height), turning while
walking (the figure turns on the spot first, then walks straight), a forward fall (there is only a backward one).
"""
from __future__ import annotations

import importlib.util
import json
import os
import math
import statistics

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import aj_rig, core

P = "mixamorig:"
JOINTS = aj_rig.JOINTS
BONES = [v[0] for v in JOINTS.values()]                    # the 24 bones the control rig drives
BONE_JOINT = {v[0]: k for k, v in JOINTS.items()}
GROUP_JOINTS = {g: [j for j, v in JOINTS.items() if v[2] == g] for g in aj_rig.GROUPS}
ALL_GROUPS = ("legs", "spine", "arm.L", "arm.R", "head")
TEEN_LEG = None                                            # hip joint height of the clips' own (upload) skeleton
CONTACT = 0.015                                            # a foot point this close to its standing height is on the floor (native m)
SWING = 0.03                                               # a foot this far up is in the air
DEFAULT_SPEED = {"walk": 2.0, "run": 1.0, "sneak": 1.0}    # walk(speed=) at this value plays the clip at its own rate (as actions._Perf.go)
CYCLES = {"walk": "Standard_Walk", "run": "Standard_Run", "sneak": "Sneak_Walk"}
EXIT_IDLE = "Standing_Idle"
FLOOR_CLIPS = ("Laying_Idle", "Sleeping_Idle", "Getting_Up", "Falling_Back", "Stumble_Backwards")   # the body is on the floor
HEAD_SPLIT = {"neck": 0.35, "head": 0.65}                  # how head_turn / tilt_head share the turn (as cast_aj)
_CLIPS: dict = {}                                          # name -> Clip, imported once per Blender session
_REG = None
_REGMOD = None


# ------------------------------------------------------------------------------------------------- the registry
def _regmod():
    """tools/chars_aj/clips.py (plain Python): the registry file, the asks, the scanner."""
    global _REGMOD
    if _REGMOD is None:
        p = core.PROJECT / "tools" / "chars_aj" / "clips.py"
        spec = importlib.util.spec_from_file_location("aj_clips_registry", p)
        _REGMOD = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_REGMOD)
    return _REGMOD


def registry(refresh: bool = False) -> dict:
    global _REG
    if _REG is None or refresh:
        _REG = _regmod().load()
    return _REG


class MissingClip(Exception):
    """A motion clip the build needs is not registered or its file is not on disk. `ask` is the exact request for the
    owner (Mixamo search words and title, download settings, target path)."""

    def __init__(self, name: str, ask: str):
        super().__init__(f"motion clip '{name}' is missing.\n{ask}")
        self.name, self.ask = name, ask


def path_of(name: str):
    reg = registry()
    return _regmod().clip_path(reg, name)


def require(name: str) -> dict:
    """The registry entry of a clip whose file is on disk, else MissingClip."""
    reg = registry()
    c = reg["clips"].get(name)
    if c is None or not path_of(name).exists():
        raise MissingClip(name, _regmod().ask(name, reg))
    return c


# ----------------------------------------------------------------------------------------------- importing a clip
class Clip:
    """One Mixamo clip as plain tables: per bone and clip frame its local rotation (and the Hips location), plus the
    clip skeleton's rest matrices (armature space) and its object transform."""

    def __init__(self, name):
        self.name = name
        self.fps = 30.0
        self.q = {}            # bone -> [Quaternion per frame]
        self.loc = []          # Hips location per frame (armature units, bone space)
        self.rest = {}         # bone -> Matrix (armature space)
        self.parent = {}       # bone -> parent bone or None
        self.basis = Matrix.Identity(4)
        self.n = 0
        self.checks = {}

    @property
    def duration(self) -> float:
        return (self.n - 1) / self.fps

    def sample(self, s: float, loop: bool = False):
        """(bone -> Quaternion, Hips location) at clip second s (between frames: normalised lerp)."""
        x = s * self.fps
        if loop and self.n > 1:
            x = x % (self.n - 1)
        x = max(0.0, min(self.n - 1.0, x))
        i = int(math.floor(x))
        u = x - i
        j = min(self.n - 1, i + 1)
        out = {}
        for b, qs in self.q.items():
            a, c = qs[i], qs[j]
            if a.dot(c) < 0:
                c = -c
            q = Quaternion((a.w + (c.w - a.w) * u, a.x + (c.x - a.x) * u, a.y + (c.y - a.y) * u, a.z + (c.z - a.z) * u))
            q.normalize()
            out[b] = q
        loc = self.loc[i].lerp(self.loc[j], u)
        return out, loc


def _channelbag(act):
    return act.layers[0].strips[0].channelbags[0]


def _import(name: str) -> Clip:
    """Import the FBX once (in the open scene, removed again at once; the scene's frame rate is restored) and read it
    into a Clip."""
    if name in _CLIPS:
        return _CLIPS[name]
    require(name)
    sc = bpy.context.scene
    keep = (sc.render.fps, sc.render.fps_base, sc.frame_start, sc.frame_end, sc.frame_current)
    before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
    before_d = {k: set(getattr(bpy.data, k)) for k in ("armatures", "meshes", "materials", "images", "collections")}
    active = bpy.context.view_layer.objects.active
    bpy.ops.import_scene.fbx(filepath=str(path_of(name)), ignore_leaf_bones=False, automatic_bone_orientation=False)
    new_o = [o for o in bpy.data.objects if o not in before_o]
    clip = Clip(name)
    clip.fps = float(sc.render.fps) / float(sc.render.fps_base)     # the importer sets the scene to the file's rate
    arms = [o for o in new_o if o.type == "ARMATURE"]
    clip.checks = {"objects": [(o.name, o.type) for o in new_o], "armatures": len(arms)}
    try:
        if len(arms) != 1:
            raise RuntimeError(f"{name}: {len(arms)} armatures in the file (want 1)")
        ia = arms[0]
        act = ia.animation_data.action if ia.animation_data else None
        if act is None:
            raise RuntimeError(f"{name}: the armature has no animation")
        f0, f1 = (int(round(v)) for v in act.frame_range)
        clip.n = f1 - f0 + 1
        clip.basis = ia.matrix_basis.copy()
        for b in ia.data.bones:
            clip.rest[b.name[len(P):]] = b.matrix_local.copy()
            clip.parent[b.name[len(P):]] = b.parent.name[len(P):] if b.parent else None
        fcs = {}
        for fc in _channelbag(act).fcurves:
            fcs[(fc.data_path, fc.array_index)] = fc
        frames = range(f0, f1 + 1)
        for bn in BONES:
            pb = ia.pose.bones.get(P + bn)
            if pb is None:
                raise RuntimeError(f"{name}: bone {P}{bn} is missing")
            path = f'pose.bones["{P}{bn}"].rotation_quaternion'
            cs = [fcs.get((path, i)) for i in range(4)]
            qs = []
            prev = None
            for f in frames:
                q = Quaternion([cs[i].evaluate(f) if cs[i] else (1.0, 0, 0, 0)[i] for i in range(4)]).normalized()
                if prev is not None and q.dot(prev) < 0:
                    q = -q
                qs.append(q)
                prev = q
            clip.q[bn] = qs
        lp = f'pose.bones["{P}Hips"].location'
        cs = [fcs.get((lp, i)) for i in range(3)]
        clip.loc = [Vector([cs[i].evaluate(f) if cs[i] else 0.0 for i in range(3)]) for f in frames]
        # what else is keyed: other bones' locations and every scale must be constant (rotations + Hips location only)
        worst_loc, worst_scale, other = 0.0, 0.0, []
        for (path, i), fc in fcs.items():
            prop = path.rsplit(".", 1)[-1]
            if not path.startswith("pose.bones"):
                vals = [fc.evaluate(f) for f in (f0, (f0 + f1) // 2, f1)]
                if max(vals) - min(vals) > 1e-4:
                    other.append(path)
                continue
            if prop == "location" and "Hips" not in path:
                vals = [fc.evaluate(f) for f in frames]
                worst_loc = max(worst_loc, max(vals) - min(vals))
            elif prop == "scale":
                vals = [fc.evaluate(f) for f in frames]
                worst_scale = max(worst_scale, max(abs(v - 1.0) for v in vals))
        clip.checks.update(frames=clip.n, fps=clip.fps, bones=len(ia.data.bones),
                           missing=[b for b in BONES if (P + b) not in ia.data.bones],
                           mixamo=all(b.name.startswith(P) for b in ia.data.bones),
                           other_bone_loc_range=round(worst_loc, 4), scale_dev=round(worst_scale, 5),
                           object_keys=other, skin=[o.name for o in new_o if o.type == "MESH"])
    finally:
        acts = [a for a in bpy.data.actions if a not in before_a]
        for o in new_o:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in acts:
            bpy.data.actions.remove(a)
        for k, old in before_d.items():
            coll = getattr(bpy.data, k)
            for d in [d for d in coll if d not in old]:
                if d.users == 0:
                    coll.remove(d)
        sc.render.fps, sc.render.fps_base = keep[0], keep[1]
        sc.frame_start, sc.frame_end = keep[2], keep[3]
        sc.frame_set(keep[4])
        if active is not None and active.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = active
    _CLIPS[name] = clip
    return clip


# ---------------------------------------------------------------------------------------- forward kinematics
def _bone_fk(rest, parent, q, hips_loc, k_root=1.0):
    """Armature-space pose matrices of the driven bones for local rotations q and a Hips location (bone space)."""
    M = {}
    for bn in BONES:
        p = parent.get(bn)
        B = q[bn].to_matrix().to_4x4()
        if bn == "Hips":
            B = Matrix.Translation(hips_loc * k_root) @ B
        if p is None or p not in M:
            M[bn] = rest[bn] @ B
        else:
            M[bn] = M[p] @ (rest[p].inverted() @ rest[bn]) @ B
    return M


class Body:
    """What a clip needs to know about one actor: its own rest matrices, the reference-pose rotations of the control
    rig, the root scale (leg-length ratio) and the floor shift."""

    def __init__(self, actor):
        self.actor = actor
        arm = actor.rig
        self.rest = {bn: arm.data.bones[P + bn].matrix_local.copy() for bn in BONES}
        self.parent = {}
        for bn in BONES:
            b = arm.data.bones[P + bn]
            self.parent[bn] = b.parent.name[len(P):] if b.parent else None
        self.basis = arm.matrix_basis.copy()                  # armature -> model (turn X 90 and the 0.01 scale)
        self.A3 = self.basis.to_3x3().normalized()
        self.refT = {bn: actor._aj_ref[bn][1].transposed() for bn in BONES}
        self.W = actor.W
        k = arm.get("aj_root_scale")
        if k is None:
            k = actor.W["hip.L"].z / _teen_leg()
        self.k_root = float(k)
        self.dz = 0.0
        self.leg = float(actor.W["hip.L"].z)                  # hip joint above the floor at rest, native m

    def joints(self, q, hips_loc):
        """Clip local rotations -> control-rig joint values: {joint: local Quaternion}, hips location (model)."""
        M = _bone_fk(self.rest, self.parent, q, hips_loc, self.k_root)
        E = {"root": Matrix.Identity(3)}
        for jn, (bn, _p, _g) in JOINTS.items():
            E[jn] = (self.A3 @ M[bn].to_3x3()).normalized() @ self.refT[bn]
        out = {jn: (E[JOINTS[jn][1]].transposed() @ E[jn]).to_quaternion() for jn in JOINTS}
        hl = (self.basis @ M["Hips"]).translation.copy()
        hl.z += self.dz
        return out, hl

    def fk(self, J, hips):
        """Joint values -> model positions and rotations of every joint (the control rig's own tree)."""
        pos, rot = {"root": Vector((0, 0, 0))}, {"root": Matrix.Identity(3)}
        for jn, (bn, par, _g) in JOINTS.items():
            R = J[jn].to_matrix()
            if jn == "hips":
                pos[jn] = hips.copy()
                rot[jn] = R
            else:
                pos[jn] = pos[par] + rot[par] @ (self.W[jn] - self.W[par])
                rot[jn] = rot[par] @ R
        return pos, rot


def _teen_leg() -> float:
    global TEEN_LEG
    if TEEN_LEG is None:
        c = _import(EXIT_IDLE)
        TEEN_LEG = ((c.basis @ c.rest["LeftUpLeg"]).translation).z
    return TEEN_LEG


def body(actor) -> Body:
    b = getattr(actor, "_clip_body", None)
    if b is None:
        b = actor._clip_body = Body(actor)
        b.dz = _floor_shift(actor, b)
    return b


def _lift(b: Body, pos) -> float:
    """How far the lower foot is above where a standing foot is (native m): ankle or ball, whichever is lower."""
    W = b.W
    return min(min(pos[f"an.{s}"].z - W[f"an.{s}"].z, pos[f"toe.{s}"].z - W[f"toe.{s}"].z) for s in "LR")


def _floor_shift(actor, b: Body) -> float:
    """The constant hip shift that puts the feet on the floor for this body (median over Standing_Idle), as
    variants.retarget does for the bent-knee seniors; measured for every body and applied when over 1 mm."""
    try:
        c = _import(EXIT_IDLE)
    except MissingClip:
        return 0.0
    lifts = []
    for i in range(0, c.n, 3):
        q, loc = c.sample(i / c.fps)
        J, hl = b.joints(q, loc)
        pos, _r = b.fk(J, hl)
        lifts.append(_lift(b, pos))
    dz = -statistics.median(lifts)
    actor._clip_floor_mm = dz * 1000.0
    return dz if abs(dz) > 0.001 else 0.0


# ------------------------------------------------------------------------------------------------ skin points
class Skin:
    """The body mesh as rigid points per control joint, so the lowest point of the skin can be found for any pose
    without evaluating the scene: each vertex follows its dominant bone's joint (fingers and toes follow the hand and
    the ball of the foot): position = pos[joint] + rot[joint] @ offset (see Body.fk)."""

    def __init__(self, actor, bd: Body):
        import numpy as np
        arm, me = actor.rig, actor.mesh
        k = {}
        for b in arm.data.bones:                          # every bone -> the driven bone it rides
            c = b
            while c is not None and c.name[len(P):] not in BONE_JOINT:
                c = c.parent
            k[b.name] = c.name[len(P):] if c is not None else "Hips"
        groups = {g.index: g.name for g in me.vertex_groups}
        M = actor.root.matrix_world.inverted() @ me.matrix_world
        cols = {jn: [] for jn in JOINTS}
        fcols = {jn: [] for jn in JOINTS}                  # finger skin: the fingers curl by the hand shape, which is
        for v in me.data.vertices:                         # not known here, so it counts with a margin (FINGER_MARGIN)
            best, wb = None, 0.0
            for g in v.groups:
                if g.weight > wb and groups.get(g.group) in k:
                    best, wb = groups[g.group], g.weight
            if best is None:
                continue
            bn = k[best]
            jn = BONE_JOINT[bn]
            R_rest = (bd.A3 @ bd.rest[bn].to_3x3()).normalized()
            head_rest = bd.basis @ bd.rest[bn].translation
            o = bd.refT[bn].transposed() @ R_rest.transposed() @ ((M @ v.co) - head_rest)
            (fcols if ((wb < 0.8 and any(w in best for w in ARM_WORDS)) or any(w in best for w in FINGER_WORDS)) else cols)[jn].append(tuple(o))
        self.pts = {jn: np.array(c, dtype=float) for jn, c in cols.items() if c}
        self.fpts = {jn: np.array(c, dtype=float) for jn, c in fcols.items() if c}
        self.n = sum(len(c) for c in cols.values()) + sum(len(c) for c in fcols.values())

    def points(self, pos, rot):
        """All skin points (model metres) for joint positions and rotations from Body.fk."""
        import numpy as np
        out = []
        for jn, O in list(self.pts.items()) + list(self.fpts.items()):
            R = np.array([list(r) for r in rot[jn]])
            out.append(O @ R.T + np.array(pos[jn]))
        return np.vstack(out)

    def low(self, pos, rot, joints=None) -> float:
        """The lowest skin point (model metres above the floor); joints: only the skin riding these joints."""
        import numpy as np
        z = 9.0
        for jn, O in self.pts.items():
            if joints is not None and jn not in joints:
                continue
            R = rot[jn]
            row = np.array([R[2][0], R[2][1], R[2][2]])
            z = min(z, float((O @ row).min()) + pos[jn].z)
        for jn, O in self.fpts.items():
            if joints is not None and jn not in joints:
                continue
            R = rot[jn]
            row = np.array([R[2][0], R[2][1], R[2][2]])
            z = min(z, float((O @ row).min()) + pos[jn].z - FINGER_MARGIN)
        return z


def skin(actor) -> Skin:
    s = getattr(actor, "_clip_skin", None)
    if s is None:
        s = actor._clip_skin = Skin(actor, body(actor))
    return s


ARM_WORDS = ("Arm", "Shoulder", "Hand")
FINGER_WORDS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
FINGER_MARGIN = 0.028     # finger skin, and skin blended between bones (shoulders), counts this much lower than the rigid model says (the fingers curl, shoulders bulge: measured up to 2.6 cm)
SKIN_EPS = 0.004          # a body resting on the floor has its skin this far above it (native m)
YAW_MAX = math.radians(25.0)   # a planted foot is held at its touch-down yaw within this much (a foot that turns more is let go)
COLLAR_EASE = 8             # frames the collar takes to go from a clip's to the procedural one after the clip ends
REACH = 0.12                 # a planted foot the leg misses by more than this (native m) is let go instead of dragged
DWELL = 6                 # frames a foot stays low before it counts as planted even when it moves (a kneeling foot drags)
FLOOR_NEAR = 0.07         # a body whose lowest skin is this near the floor, or under it, is resting on it


# ------------------------------------------------------------------------------------------- channel plumbing
def _is_quat(jn):
    return jn.startswith(aj_rig.QUAT)


def _fc(ob, path, index):
    for fc in core.fcurves(ob):
        if fc.data_path == path and fc.array_index == index:
            return fc
    ob.keyframe_insert(path, index=index, frame=1)
    for fc in core.fcurves(ob):
        if fc.data_path == path and fc.array_index == index:
            return fc
    raise RuntimeError(f"no F-curve {path}[{index}] on {ob.name}")


def _value(ob, path, n, f):
    """A channel's value at frame f (keyed or static)."""
    v = list(getattr(ob, path))
    for fc in core.fcurves(ob):
        if fc.data_path == path and fc.array_index < n:
            v[fc.array_index] = fc.evaluate(f)
    return v


def joint_now(actor, jn, f) -> Quaternion:
    ob = actor.J[jn]
    if _is_quat(jn):
        return Quaternion(_value(ob, "rotation_quaternion", 4, f)).normalized()
    from mathutils import Euler
    return Euler(_value(ob, "rotation_euler", 3, f), "XYZ").to_quaternion()


def hips_now(actor, f) -> Vector:
    return Vector(_value(actor.J["hips"], "location", 3, f))


def _write(ob, path, frames, values, n):
    """Replace a channel's keys on frames[0]..frames[-1] by one LINEAR key per frame; keys outside stay."""
    fa, fb = frames[0], frames[-1]
    for i in range(n):
        fc = _fc(ob, path, i)
        kps = fc.keyframe_points
        for k in range(len(kps) - 1, -1, -1):
            if fa - 0.5 <= kps[k].co.x <= fb + 0.5:
                kps.remove(kps[k], fast=True)
        for f, v in zip(frames, values):
            kp = kps.insert(f, float(v[i]), options={"FAST"})
            kp.interpolation = "LINEAR"
        fc.update()
    setattr(ob, path, values[-1])


def _to_channel(jn, q, prev):
    if _is_quat(jn):
        if prev is not None and q.dot(Quaternion(prev)) < 0:
            q = -q
        return tuple(q)
    from mathutils import Euler
    e = q.to_euler("XYZ", Euler(prev, "XYZ")) if prev is not None else q.to_euler("XYZ")
    return tuple(e)


def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------------------------------------------- layers
class Layer:
    """One clip (or a built sequence) on one actor: per pipeline frame the joint values it wants, the weight it has
    over what was there before, and the procedural values it blends from."""

    def __init__(self, actor, name, joints, frames):
        self.actor, self.name = actor, name
        self.joints = list(joints)
        self.frames = list(frames)
        self.want = {}         # f -> {joint: Quaternion}
        self.hips = {}         # f -> Vector (model) or None when the layer does not own the legs
        self.w = {}            # f -> weight over the procedural value
        self.base = {}         # f -> {joint: Quaternion}, hips: the values blended from (read when the layer is made)
        self.stage = {}        # f -> world location of the stage (root motion, walking) or nothing
        self.look = "head" in self.joints or "neck" in self.joints
        self.hold_from = None  # frame after which the last pose is held (kept by later keys)

    def owns(self, jn, f):
        return jn in self.joints and f in self.w


def _layers(actor):
    if not hasattr(actor, "_clip_layers"):
        actor._clip_layers = []
    return actor._clip_layers


def _look_angles(actor, f):
    """(turn, tilt) radians the actor's head_turn / tilt_head asked for at frame f (cast_aj keys them on ctrl)."""
    out = []
    for prop in ("head_turn", "head_tilt"):
        v = float(actor.ctrl.get(prop, 0.0))
        for fc in core.fcurves(actor.ctrl):
            if fc.data_path == f'["{prop}"]':
                v = fc.evaluate(f)
        out.append(v)
    return out[0] * math.radians(38.0), math.radians(out[1])


def _compose(L: Layer, jn, f, final=False):
    q = L.want[f][jn]
    if final and L.look and jn in HEAD_SPLIT:
        turn, tilt = _look_angles(L.actor, f)
        if turn or tilt:
            from mathutils import Euler
            k = HEAD_SPLIT[jn]
            q = q @ Euler((tilt * k, 0.0, turn * k), "XYZ").to_quaternion()
    w = L.w[f]
    if w >= 0.9999:
        return q
    b = L.base[f][jn]
    if b.dot(q) < 0:
        b = -b
    return b.slerp(q, w)


def write_layer(L: Layer, final=False):
    """Key the layer into the actor's control empties (and its stage)."""
    a = L.actor
    frames = L.frames
    for jn in L.joints:
        ob = a.J[jn]
        path = "rotation_quaternion" if _is_quat(jn) else "rotation_euler"
        prev = None
        f_before = frames[0] - 1
        if f_before >= 1:
            prev = tuple(getattr(ob, path)) if not core.fcurves(ob) else tuple(_value(ob, path, 4 if _is_quat(jn) else 3, f_before))
        vals = []
        for f in frames:
            v = _to_channel(jn, _compose(L, jn, f, final), prev)
            vals.append(v)
            prev = v
        _write(ob, path, frames, vals, 4 if _is_quat(jn) else 3)
        if _is_quat(jn):
            a._q[jn] = Quaternion(vals[-1])
    if any(L.hips.get(f) is not None for f in frames):
        vals = []
        for f in frames:
            h = L.hips[f]
            w = L.w[f]
            vals.append(tuple(L.base[f]["__hips"].lerp(h, w)) if w < 0.9999 else tuple(h))
        _write(a.J["hips"], "location", frames, vals, 3)
    if L.stage:
        fs = sorted(L.stage)
        _write(a.stage, "location", fs, [tuple(L.stage[f]) for f in fs], 3)


def collars(actor, frames):
    """After aj_rig.apply_collars: on the frames a clip owns an arm, the collar is the clip's and the shoulder empty
    sits at the tip of that collar (blended with the procedural collar where the clip blends in)."""
    fset = set(frames)
    for L in _layers(actor):
        for s in "LR":
            cl = f"cl.{s}"
            if cl not in L.joints:
                continue
            fs = [f for f in L.frames if f in fset]
            if not fs:
                continue
            ob, sh = actor.J[cl], actor.J[f"sh.{s}"]
            qs, locs, prev = [], [], None
            for f in fs:
                q = L.want[f][cl]
                w = L.w[f]
                if w < 0.9999:
                    b = Quaternion(_value(ob, "rotation_quaternion", 4, f)).normalized()
                    if b.dot(q) < 0:
                        b = -b
                    q = b.slerp(q, w)
                if prev is not None and q.dot(prev) < 0:
                    q = -q
                prev = q
                qs.append(tuple(q))
                locs.append(tuple(aj_rig.shoulder_point(actor, s, q)))
            if not getattr(L, "idle", False) and L.w[fs[-1]] >= 0.9999:
                # hand-back: after the clip the procedural collar (from the arm) takes over; it eases in over a third
                # of a second from the collar the clip ended with, so the shoulders do not jump
                qlast = Quaternion(qs[-1])
                tail = [f for f in range(fs[-1] + 1, fs[-1] + COLLAR_EASE + 1) if f in fset]
                for i, f in enumerate(tail, 1):
                    qp = Quaternion(_value(ob, "rotation_quaternion", 4, f)).normalized()
                    if qp.dot(qlast) < 0:
                        qp = -qp
                    q = qlast.slerp(qp, _smooth(i / (COLLAR_EASE + 1)))
                    qs.append(tuple(q))
                    locs.append(tuple(aj_rig.shoulder_point(actor, s, q)))
                fs = fs + tail
            _write(ob, "rotation_quaternion", fs, qs, 4)
            _write(sh, "location", fs, locs, 3)


def _yaw(actor, f) -> float:
    y = 0.0
    for ob in (actor.stage, actor.root):
        y += _value(ob, "rotation_euler", 3, f)[2]
    return y


def _to_world(actor, f, v: Vector) -> Vector:
    """A horizontal model-space offset (native m) as a world offset at frame f."""
    y = _yaw(actor, f)
    c, s = math.cos(y), math.sin(y)
    k = actor.scale
    return Vector((c * v.x - s * v.y, s * v.x + c * v.y, 0.0)) * k


# ------------------------------------------------------------------------------------------- building a layer
def _groups_joints(actor, groups):
    js = []
    for g in groups:
        if g not in GROUP_JOINTS:
            raise ValueError(f"unknown group {g!r}: use {ALL_GROUPS}")
        js += GROUP_JOINTS[g]
    for s in "LR":                                         # an arm holding a prop stays with the actor API
        if f"arm.{s}" in groups and actor._grips(s):
            js = [j for j in js if j not in GROUP_JOINTS[f"arm.{s}"]]
    return js


def new_layer(actor, name, groups, f_first, f_last):
    shot = actor.shot
    f_last = min(int(f_last), int(max(bpy.context.scene.frame_end, shot.frames)))
    f_first = max(1, int(f_first))
    js = _groups_joints(actor, groups)
    L = Layer(actor, name, js, range(f_first, max(f_first, f_last) + 1))
    L.owns_legs = "hips" in js
    for f in L.frames:
        b = {jn: joint_now(actor, jn, f) for jn in js}
        b["__hips"] = hips_now(actor, f)
        L.base[f] = b
    return L


def finish_layer(L: Layer, hold_state=None):
    """Write a finished layer, remember it, leave the empties holding its last pose."""
    write_layer(L)
    _layers(L.actor).append(L)
    a = L.actor
    if hold_state:
        a._clip_state = hold_state
    if L.owns_legs:
        a._legs_now = {"standing": (0.0, 0.0), "sitting": (86.0, 84.0), "kneeling": (8.0, 98.0)}.get(getattr(a, "_clip_state", "standing"), (0.0, 0.0))
        a._sink = (0.0, 0.0) if a._legs_now == (0.0, 0.0) else (0.2 * a.scale, 0.2 * a.scale)
    return L


def play(actor, name, t0, groups=ALL_GROUPS, rate=1.0, blend=0.25, loop=None, until=None, start=0.0, extract=None,
         hips_dz=None, state=None, end_at=None, reverse=False, floor=None, ground=True):
    """Put a clip on an actor from time t0 (see ActorAj.play_clip). start: clip seconds to begin at; extract: give
    the horizontal hip travel to the stage (default: clips that are not in place); hips_dz(frame, u) -> metres to add
    to the hip height with the feet kept where the clip has them (a seat height); end_at: clip seconds to stop at;
    reverse: play from end_at back to start (getting up played backward is lying down). floor: the body rests on the
    floor in this clip (default: the clips in FLOOR_CLIPS); ground=False skips grounding (ground_layer). Returns the
    end time."""
    c = require(name)
    clip = _import(name)
    bd = body(actor)
    loop = c.get("loop", False) if loop is None else loop
    rate = max(0.05, float(rate))
    shot = actor.shot
    fps = shot.fps
    clip_end = clip.duration if end_at is None else min(clip.duration, end_at)
    t_end = until if until is not None else (t0 + (clip_end - start) / rate if not loop else t0 + (clip.duration - start) / rate)
    f0, f1 = actor._f(t0), max(actor._f(t0) + 1, actor._f(t_end))
    L = new_layer(actor, name, groups, f0, f1)
    extract = (not c.get("in_place", False)) if extract is None else extract
    nb = max(1, int(round(blend * fps)))
    loop = loop and not reverse
    q0, l0 = clip.sample(clip_end if reverse else start, loop)
    _J0, h_first = bd.joints(q0, l0)
    stage0 = Vector(_value(actor.stage, "location", 3, f0))
    Tm = {}
    for f in L.frames:
        s = start + (f - f0) / fps * rate
        if reverse:
            s = max(start, clip_end - (f - f0) / fps * rate)
        elif not loop:
            s = min(s, clip_end)
        q, loc = clip.sample(s, loop)
        J, hl = bd.joints(q, loc)
        hor = Vector((hl.x - h_first.x, hl.y - h_first.y, 0.0))
        if extract:
            hl = Vector((h_first.x * 0 + bd.W["hips"].x, bd.W["hips"].y, hl.z))
            L.stage[f] = stage0 + _to_world(actor, f, hor)
            Tm[f] = hor
        else:
            hl = Vector((bd.W["hips"].x + hor.x, bd.W["hips"].y + hor.y, hl.z))
        if hips_dz is not None and L.owns_legs:
            u = (f - f0) / max(1, f1 - f0)
            dz = hips_dz(f, u)
            if abs(dz) > 1e-5:
                J, hl = _raise_hips(bd, J, hl, dz)
        L.want[f] = J
        L.hips[f] = hl if L.owns_legs else None
        L.w[f] = _smooth((f - f0 + 1) / nb) if blend > 0 else 1.0
    if ground:
        ground_layer(L, Tm or None, FLOOR_CLIPS.__contains__(name) if floor is None else floor)
    if extract and L.frames:
        actor._pos = Vector((L.stage[L.frames[-1]].x, L.stage[L.frames[-1]].y, actor._pos.z))
    finish_layer(L, state)
    return (L.frames[-1] - 1) / fps


def _raise_hips(bd: Body, J, hl, dz):
    """Move the hips up by dz (native m) and bend the legs so the ankles stay where they were (two-bone IK in the
    plane of each leg; the feet keep their turn in the world)."""
    pos, rot = bd.fk(J, hl)
    J = dict(J)
    hl2 = hl + Vector((0, 0, dz))
    for s in "LR":
        _leg_to(J, pos, rot, s, pos[f"hip.{s}"] + Vector((0, 0, dz)), pos[f"an.{s}"])
    return J, hl2


def _leg_to(J, pos, rot, s, H2, target, foot_yaw=0.0, foot=None):
    """Two-bone IK for one leg in place in J: the hip joint at H2 (the hips' rotation unchanged), the ankle at target,
    the knee kept in the plane it bends in, the foot keeping its turn. Returns how far the ankle stays from the target
    (native m) when the leg cannot reach."""
    H, K, A = pos[f"hip.{s}"], pos[f"kn.{s}"], pos[f"an.{s}"]
    a, b = (K - H).length, (A - K).length
    d = target - H2
    L = max(abs(a - b) + 1e-4, min(a + b - 1e-4, d.length))
    u = d.normalized()
    pole = (K - H) - u * (K - H).dot(u)
    if pole.length < 1e-6:
        pole = (K - H).orthogonal()
    v = pole.normalized()
    ca = max(-1.0, min(1.0, (a * a + L * L - b * b) / (2 * a * L)))
    K2 = H2 + a * (ca * u + math.sqrt(max(0.0, 1 - ca * ca)) * v)
    A2 = H2 + u * L
    R1 = (K - H).rotation_difference(K2 - H2).to_matrix()
    Rt = R1 @ rot[f"hip.{s}"]
    R2 = (R1 @ (A - K)).rotation_difference(A2 - K2).to_matrix()
    Rs = R2 @ R1 @ rot[f"kn.{s}"]
    Rf = rot[f"an.{s}"]                                       # the foot keeps its turn (or is turned about the vertical)
    if foot is not None:
        Rf = foot
    if foot_yaw:
        Rf = Matrix.Rotation(foot_yaw, 3, "Z") @ Rf
    J[f"hip.{s}"] = (rot["hips"].transposed() @ Rt).to_quaternion()
    J[f"kn.{s}"] = (Rt.transposed() @ Rs).to_quaternion()
    J[f"an.{s}"] = (Rs.transposed() @ Rf).to_quaternion()
    return (A2 - target).length


def finalize(actor, frames):
    """At _finalize: idle fill, every layer written again in order (head turns composed in), the collars, and the
    procedural collars of the arms no clip owns. Replaces the plain aj_rig.apply_collars call."""
    from . import aj_rig as R
    for req in getattr(actor, "_idle_requests", []):
        _idle_fill(actor, *req)
    for L in _layers(actor):
        write_layer(L, final=True)
    R.apply_collars(actor, frames)
    collars(actor, frames)


def after_collars(actor, frames):
    """aj_rig.apply_collars was run during the build (a hold measures the hand): put the clips' collars back."""
    if _layers(actor):
        collars(actor, frames)


# ------------------------------------------------------------------------------------------------- analysis
def _clip_body_fk(clip: Clip, s: float, loop=False):
    """Bone positions (model metres) of the clip's own skeleton at clip second s."""
    q, loc = clip.sample(s, loop)
    M = _bone_fk(clip.rest, clip.parent, q, loc)
    return {bn: (clip.basis @ M[bn]).translation for bn in BONES}


def classify(pos, leg) -> str:
    """standing, sitting, kneeling, lying or crouching from bone positions (model metres) and the leg length."""
    h = pos["Hips"].z
    up = (pos["Neck"] - pos["Hips"]).normalized().z
    knee = min(pos["LeftLeg"].z, pos["RightLeg"].z)
    thigh = max(abs(pos["LeftLeg"].z - pos["LeftUpLeg"].z), abs(pos["RightLeg"].z - pos["RightUpLeg"].z))
    if up < 0.55 and h < 0.45 * leg:
        return "lying"
    if knee < 0.12 * leg and h > 0.30 * leg:
        return "kneeling"
    if h > 0.82 * leg:
        return "standing"
    if thigh < 0.35 * leg and h > 0.35 * leg:
        return "sitting"
    return "crouching"


def analyse(name: str) -> dict:
    """The registry's analysis of one clip, measured on the clip's own skeleton (leg = hip joint height at rest)."""
    c = require(name)
    clip = _import(name)
    leg = ((clip.basis @ clip.rest["LeftUpLeg"]).translation).z
    fps = clip.fps
    P0 = [_clip_body_fk(clip, i / fps) for i in range(clip.n)]
    rest = {bn: (clip.basis @ clip.rest[bn]).translation for bn in BONES}
    hips = [p["Hips"] for p in P0]
    trav = math.hypot(hips[-1].x - hips[0].x, hips[-1].y - hips[0].y)
    sway = max(math.hypot(h.x - hips[0].x, h.y - hips[0].y) for h in hips)
    # when the body starts and stops moving (a clip can open and close on a held pose)
    dev = []
    for i in range(clip.n):
        dev.append(max(math.degrees(clip.q[bn][i].rotation_difference(clip.q[bn][0]).angle) for bn in BONES))
    dev_end = [max(math.degrees(clip.q[bn][i].rotation_difference(clip.q[bn][-1]).angle) for bn in BONES) for i in range(clip.n)]
    moves = next((i for i in range(clip.n) if dev[i] > 4.0), 0)
    settles = next((i for i in range(clip.n - 1, -1, -1) if dev_end[i] > 4.0), clip.n - 1) + 1
    out = {"duration_s": round(clip.duration, 3), "fps": fps, "frames": clip.n, "leg_m": round(leg, 4),
           "hips_travel_m": round(trav, 4), "hips_sway_m": round(sway, 4),
           "moves_s": round(moves / fps, 3), "settles_s": round(min(settles, clip.n - 1) / fps, 3),
           "hips_end_dxdy_m": [round(hips[-1].x - hips[0].x, 4), round(hips[-1].y - hips[0].y, 4)],
           "start_pose": classify(P0[0], leg), "end_pose": classify(P0[-1], leg),
           "hips_start_per_leg": round(hips[0].z / leg, 4), "hips_end_per_leg": round(hips[-1].z / leg, 4)}
    feet = {}
    for s, side in (("L", "Left"), ("R", "Right")):
        an_r, toe_r = rest[side + "Foot"].z, rest[side + "ToeBase"].z
        lifts = [min(p[side + "Foot"].z - an_r, p[side + "ToeBase"].z - toe_r) for p in P0]
        lo = min(lifts)
        feet[s] = [li - lo for li in lifts]
    if c.get("kind") == "locomotion":
        planted = {s: [i for i in range(clip.n) if feet[s][i] < CONTACT] for s in "LR"}
        dbl = [i for i in range(clip.n) if i in planted["L"] and i in planted["R"]]
        vy = []
        for s, side in (("L", "Left"), ("R", "Right")):
            for i in planted[s]:
                if i + 1 in planted[s]:
                    a0, a1 = P0[i], P0[i + 1]
                    pt = "ToeBase" if (a0[side + "ToeBase"].z - rest[side + "ToeBase"].z) < (a0[side + "Foot"].z - rest[side + "Foot"].z) else "Foot"
                    vy.append((a1[side + pt].y - a0[side + pt].y) * fps)
        v = statistics.median(vy) if vy else 0.0
        out.update(planted_frames={s: _runs(planted[s]) for s in "LR"}, double_support_frames=_runs(dbl),
                   planted_speed_per_leg_s=round(v / leg, 4), planted_speed_m_s=round(v, 4),
                   stride_per_leg=round(v * clip.duration / leg, 4), cycle_s=round(clip.duration, 3))
    ev = {}
    hz = [h.z for h in hips]
    if name == "Stand_To_Sit":
        ev["seat"] = next(i for i in range(clip.n) if abs(hz[i] - hz[-1]) < 0.01 and i > 3) / fps
    if name in ("Kneeling_Down",):
        kn = [min(p["LeftLeg"].z, p["RightLeg"].z) for p in P0]
        ev["knee_down"] = next(i for i in range(clip.n) if kn[i] < min(kn) + 0.015) / fps
    if name in ("Sit_To_Stand", "Kneel_To_Stand", "Getting_Up"):
        ev["rise"] = next((i for i in range(clip.n) if hz[i] > hz[0] + 0.03), 0) / fps
        ev["up"] = next((i for i in range(clip.n) if classify(P0[i], leg) == "standing" and i > 2), clip.n - 1) / fps
    if name in ("Falling_Back", "Stumble_Backwards"):
        ev["ground"] = next(i for i in range(clip.n) if hz[i] < min(hz) + 0.02) / fps
        ev["slip"] = next((i for i in range(clip.n) if max(feet["L"][i], feet["R"][i]) > 0.05), 0) / fps
    if name == "Jump":
        air = [i for i in range(clip.n) if feet["L"][i] > 0.02 and feet["R"][i] > 0.02]
        if air:
            ev["takeoff"], ev["land"] = air[0] / fps, (air[-1] + 1) / fps
        ev["crouch"] = min(range(clip.n), key=lambda i: hz[i] if not air or i < air[0] else 9) / fps
    if name.startswith("Salute"):
        side = "Right" if name == "Salute" else "Left"
        ev["hand_up"] = max(range(clip.n), key=lambda i: P0[i][side + "Hand"].z) / fps
    if ev:
        out["events_s"] = {k: round(v, 3) for k, v in ev.items()}
    return out


def _runs(idx):
    out = []
    for i in idx:
        if out and out[-1][1] == i - 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def register(names=None) -> dict:
    """Import, check and analyse clips (all registered ones when names is None) and write the registry."""
    regm = _regmod()
    reg = registry(refresh=True)
    rep = {}
    for name in (names or list(reg["clips"])):
        c = reg["clips"].get(name)
        r = {"problems": []}
        rep[name] = r
        if c is None:
            r["problems"].append("not in the registry")
            continue
        p = path_of(name)
        if not p.exists():
            r["problems"].append(f"file missing: {p}")
            continue
        _CLIPS.pop(name, None)
        try:
            clip = _import(name)
        except Exception as ex:
            r["problems"].append(f"import: {ex}")
            continue
        ch = clip.checks
        if ch["armatures"] != 1:
            r["problems"].append(f"{ch['armatures']} armatures")
        if ch.get("skin"):
            r["problems"].append(f"has skin meshes {ch['skin']}")
        if ch.get("missing"):
            r["problems"].append(f"bones missing {ch['missing']}")
        if not ch.get("mixamo"):
            r["problems"].append("bones without the mixamorig: prefix")
        if ch.get("other_bone_loc_range", 0) > 0.05:
            r["problems"].append(f"bones other than Hips are moved ({ch['other_bone_loc_range']} units)")
        if ch.get("scale_dev", 0) > 1e-3:
            r["problems"].append(f"bones are scaled ({ch['scale_dev']})")
        if ch.get("object_keys"):
            r["problems"].append(f"the object itself is animated: {ch['object_keys']}")
        if abs(clip.fps - float(reg.get("fps_expected", 30))) > 1e-3:
            r["problems"].append(f"{clip.fps} fps (expected {reg.get('fps_expected', 30)})")
        try:
            an = analyse(name)
        except Exception as ex:
            r["problems"].append(f"analysis: {type(ex).__name__}: {ex}")
            an = {}
        if c.get("in_place") and an.get("hips_travel_m", 0) > 0.02:
            r["problems"].append(f"in place but the hips travel {an['hips_travel_m'] * 100:.1f} cm")
        c["duration_s"] = an.get("duration_s", round(clip.duration, 3))
        c["fps"] = clip.fps
        c["sha256"] = regm.sha256(p)
        c["analysis"] = an
        c["checks"] = {k: v for k, v in ch.items() if k not in ("objects",)}
        r["summary"] = f"{an.get('duration_s')} s, {an.get('start_pose')} -> {an.get('end_pose')}"
    regm.save(reg)
    registry(refresh=True)
    return rep


# ----------------------------------------------------------------------------------------- clip-backed walking


def _planted_point(bd: Body, pos):
    """{side: (point, lift)} for both feet: the ankle or the ball, whichever is nearer its standing height."""
    W = bd.W
    r = {}
    for s in "LR":
        la = pos[f"an.{s}"].z - W[f"an.{s}"].z
        lt = pos[f"toe.{s}"].z - W[f"toe.{s}"].z
        r[s] = (pos[f"toe.{s}"].copy(), lt) if lt < la else (pos[f"an.{s}"].copy(), la)
    return r


LOCK_LOW = 0.03          # a foot point this close to its standing height can carry weight (native m)
LOCK_STILL = 0.012       # ... when it moves less than this per frame in the world (native m)
CLEARANCE = 0.035        # a foot that travels while low is lifted on an arc this high at least (native m)


def kleg(bd: Body) -> float:
    """How long this body's legs are against the Male_Teen the thresholds above were measured on."""
    return bd.leg / 0.7844


def _lock_feet(bd: Body, poses, T, still=None, low=None, dwell=0, anchor_end=True, hold_yaw=False, released=None, reach=0.012, lift=None):
    """Keep planted feet where they are in the world: per foot, the frames where the lower point of the foot (ball or
    ankle) is low and still are contacts; in a contact the point is held where it touched down (two-bone IK on the
    leg), between contacts the correction eases back to none, and a foot that moves while low (the blends) is lifted
    on a small arc. poses: [(J, hips, travel)], T: model travel per frame. Returns {"J": [...], "max_offset", "unreached"}
    (native m)."""
    n = len(poses)
    still = LOCK_STILL * kleg(bd) if still is None else still
    low = LOCK_LOW * kleg(bd) if low is None else low
    clearance = CLEARANCE * kleg(bd)
    P = [bd.fk(p[0], p[1]) for p in poses]
    Js = [dict(p[0]) for p in poses]
    forced = [p[3] if len(p) > 3 else None for p in poses]     # the foot that carries the body in a blend
    W = bd.W
    max_off = 0.0
    unreached = 0.0
    bad = set()
    for s in "LR":
        an = [P[j][0][f"an.{s}"] for j in range(n)]
        to = [P[j][0][f"toe.{s}"] for j in range(n)]
        la = [an[j].z - W[f"an.{s}"].z for j in range(n)]
        lt = [to[j].z - W[f"toe.{s}"].z for j in range(n)]
        kind = ["toe" if lt[j] < la[j] else "an" for j in range(n)]
        fw0 = Vector((W[f"toe.{s}"].x - W[f"an.{s}"].x, W[f"toe.{s}"].y - W[f"an.{s}"].y, 0.0))
        yaw = []
        for j in range(n):
            v = P[j][1][f"an.{s}"] @ fw0
            yaw.append(math.atan2(v.y, v.x))
        dy = [0.0] * n                                       # turn that puts the foot back to its yaw at touch-down

        def world(j, kd):
            p = to[j] if kd == "toe" else an[j]
            if dy[j]:
                v = Matrix.Rotation(dy[j], 3, "Z") @ (p - an[j])
                p = an[j] + v
            return Vector((p.x + T[j].x, p.y + T[j].y))
        sp = []
        for j in range(n):
            a, b = max(0, j - 1), min(n - 1, j + 1)
            sp.append((world(b, kind[j]) - world(a, kind[j])).length / max(1, b - a))
        pl = [forced[j] == s or (min(la[j], lt[j]) < low and sp[j] < still) for j in range(n)]
        if dwell:                                            # a foot that stays low for a while is on the floor, scraping or not
            j = 0
            while j < n:
                if min(la[j], lt[j]) < low:
                    e = j
                    while e < n and min(la[e], lt[e]) < low:
                        e += 1
                    if e - j >= dwell:
                        for i in range(j, e):
                            pl[i] = True
                    j = e
                else:
                    j += 1
        if released:                                         # contacts the leg could not hold on a first pass are let go
            pl = [pl[j] and (s, j) not in released for j in range(n)]
        if hold_yaw:
            y0 = None
            for j in range(n):
                if pl[j]:
                    y0 = yaw[j] if y0 is None else y0
                    d = (y0 - yaw[j] + math.pi) % math.tau - math.pi
                    dy[j] = max(-YAW_MAX, min(YAW_MAX, d))
                else:
                    y0 = None
            j = 0
            while j < n:                                      # between contacts the turn eases from one to the next
                if pl[j]:
                    j += 1
                    continue
                a0 = j
                while j < n and not pl[j]:
                    j += 1
                da = dy[a0 - 1] if a0 > 0 else (dy[j] if j < n else 0.0)
                db = dy[j] if j < n else da
                for i in range(a0, j):
                    dy[i] = da + (db - da) * _smooth((i - a0 + 1) / (j - a0 + 1))
        O = [None] * n
        lock = None
        for j in range(n):
            if pl[j]:
                p = world(j, kind[j])
                if lock is None:
                    lock = (kind[j], p.copy())
                elif lock[0] != kind[j]:
                    lock = (kind[j], p + O[j - 1])            # heel off (or heel down): the other point takes over
                O[j] = lock[1] - p
            else:
                lock = None
        # the last contact holds the foot where the walk leaves it (what comes next starts from there), so it is
        # measured back from the end
        if pl[n - 1] and anchor_end:
            lock = None
            for j in range(n - 1, -1, -1):
                if not pl[j]:
                    break
                p = world(j, kind[j])
                if lock is None:
                    lock = (kind[j], p.copy())
                elif lock[0] != kind[j]:
                    lock = (kind[j], p + O[j + 1])
                O[j] = lock[1] - p
        # between contacts the correction eases from the last contact's to the next one's (none at a touch-down)
        j = 0
        while j < n:
            if O[j] is not None:
                j += 1
                continue
            a = j
            while j < n and O[j] is None:
                j += 1
            b = j                                            # O[a-1] and O[b] are contacts (when inside)
            oa = O[a - 1] if a > 0 else (O[b] if b < n else Vector((0.0, 0.0)))
            ob = O[b] if b < n else oa
            seg = (world(b - 1, "an") - world(a, "an")).length if b - 1 > a else 0.0
            for i in range(a, b):
                u = (i - a + 1) / (b - a + 1)
                O[i] = oa.lerp(ob, _smooth(u))
                if seg > 0.04 * kleg(bd):
                    want = clearance * math.sin(math.pi * u)
                    lowv = min(la[i], lt[i])
                    if lowv < want:
                        O[i] = Vector((O[i].x, O[i].y, want - lowv))
        for j in range(n):
            o = O[j]
            dz = o.z if len(o) == 3 else 0.0
            lowv = min(la[j], lt[j])
            if lowv + dz < -0.002:
                dz = -lowv                                     # never through the floor (the blends lower the hips)
            if lift is not None:
                dz += lift[s][j]                               # the skin of the foot (the toes) kept out of the floor
            if o.xy.length < 5e-4 and dz < 5e-4 and not dy[j]:
                continue
            max_off = max(max_off, o.xy.length)
            pos, rot = P[j]
            tgt = an[j] + Vector((o.x, o.y, dz))
            miss = _leg_to(Js[j], pos, rot, s, pos[f"hip.{s}"], tgt, dy[j])
            if pl[j]:
                unreached = max(unreached, miss)
                if miss > reach:
                    bad.add((s, j))
    return {"J": Js, "max_offset": max_off, "unreached": unreached, "bad": bad}


def foot_lift(bd: Body, sk: Skin, poses):
    """Per foot and frame how far the foot's skin (ankle, foot and toes) is under the floor, smoothed: the ankle is lifted
    by this much so a toe that points down at heel strike or push-off does not go through the floor."""
    out = {}
    for s in "LR":
        raw = []
        for p in poses:
            pos, rot = bd.fk(p[0], p[1])
            raw.append(max(0.0, SKIN_EPS - sk.low(pos, rot, (f"an.{s}", f"toe.{s}"))))
        out[s] = _smooth_series(raw, 1)
        out[s] = [max(a, b) for a, b in zip(out[s], raw)]
    return out


def _composed(L: Layer, f):
    """The joint values and hips the layer's frame f actually shows: the clip blended over what was there, every joint
    the layer does not own as it is keyed now."""
    a = L.actor
    J = {jn: (_compose(L, jn, f) if jn in L.joints else joint_now(a, jn, f)) for jn in JOINTS}
    w = L.w[f]
    hb = L.hips[f]
    h = L.base[f]["__hips"].lerp(hb, w) if w < 0.9999 else hb.copy()
    return J, h


def _smooth_series(v, r=2):
    n = len(v)
    return [sum(v[max(0, i - r):min(n, i + r + 1)]) / (min(n, i + r + 1) - max(0, i - r)) for i in range(n)]


def ground_layer(L: Layer, T=None, floor=False):
    """Put a finished clip layer on the ground. Frame by frame the pose the layer shows is worked out, then
      * the body is kept out of the floor: the lowest skin point is never lower than SKIN_EPS under it; while the body
        rests on the floor (floor=True and the skin is within FLOOR_NEAR of it) it is held ON it, so a lying body neither
        sinks nor hovers; the lift is smoothed over a few frames and only ever raises the hips rigidly;
      * the feet that carry weight are held where they touched down (_lock_feet: contact = the foot low and nearly
        still, thresholds scaled to this body's legs), so entering and leaving the clip do not slide either.
    T: per frame the model travel the stage gives (None = none). Writes the result back into the layer (weight 1) and
    keeps its numbers in L.ground."""
    a = L.actor
    if not L.owns_legs or not L.frames:
        return
    bd = body(a)
    sk = skin(a)
    fr = list(L.frames)
    comp = [_composed(L, f) for f in fr]
    Tm = [Vector((0.0, 0.0)) if T is None else Vector((T[f].x, T[f].y)) for f in fr]
    dz = [0.0] * len(fr)
    low0 = []
    for i, (J, h) in enumerate(comp):
        pos, rot = bd.fk(J, h)
        low0.append(sk.low(pos, rot))
    need = [SKIN_EPS - z for z in low0]
    want = [(need[i] if (floor and low0[i] < FLOOR_NEAR) else max(0.0, need[i])) for i in range(len(fr))]
    dz = [max(x, need[i]) for i, x in enumerate(_smooth_series(want))]
    stat = {"lift_max_cm": 0.0, "lift_min_cm": 0.0}

    def pose_list(dz):
        return [(J, h + Vector((0.0, 0.0, dz[i])), Tm[i]) for i, (J, h) in enumerate(comp)]
    for _it in range(3):
        poses = pose_list(dz)
        lift = foot_lift(bd, sk, poses)
        res = _lock_feet(bd, poses, Tm, dwell=DWELL, anchor_end=False, hold_yaw=True, reach=REACH, lift=lift)
        rel = set()
        for _r in range(2):                                  # a foot the leg cannot reach is not planted there: let it go
            if not res["bad"]:
                break
            rel |= res["bad"]
            res = _lock_feet(bd, poses, Tm, dwell=DWELL, anchor_end=False, hold_yaw=True, released=rel, reach=REACH, lift=lift)
        low1 = []
        for i, p in enumerate(poses):
            pos, rot = bd.fk(res["J"][i], p[1])
            low1.append(sk.low(pos, rot))
        miss = [SKIN_EPS - z for z in low1]
        if max(miss) < 0.0015:
            break
        dz = [dz[i] + max(0.0, miss[i]) for i in range(len(fr))]
        dz = [max(x, dz[i]) for i, x in enumerate(_smooth_series(dz, 1))]
    pre = getattr(a, "_pre_steps", None)
    if pre is None:
        pre = a._pre_steps = {}
    for i in range(1, len(fr)):                              # how far each joint turns per frame in the clip itself
        for jn in JOINTS:
            q0, q1 = comp[i - 1][0][jn], comp[i][0][jn]
            d = math.degrees(q0.rotation_difference(q1).angle)
            pre[(fr[i], jn)] = min(d, 360.0 - d)
    k = a.scale * 100.0
    stat.update(lift_max_cm=round(max(dz) * k, 2), lift_min_cm=round(min(dz) * k, 2), low_after_cm=round(min(low1) * k, 2),
                foot_ik_max_cm=round(res["max_offset"] * k, 2), unreached_cm=round(res["unreached"] * k, 2))
    for i, f in enumerate(fr):
        Jn = res["J"][i]
        for jn in L.joints:
            L.want[f][jn] = Jn[jn]
        L.hips[f] = poses[i][1]
        L.w[f] = 1.0
    L.ground = stat
    a._ground_log = getattr(a, "_ground_log", []) + [dict(stat, clip=L.name, f0=fr[0], f1=fr[-1])]
    if res["unreached"] * a.scale > 0.015:
        a.shot.notes.append(f"{a.id}: {L.name}: a planted foot is {res['unreached'] * k:.1f} cm from where it should stay "
                            "(the leg cannot reach); it slides that much")


def body_override(actor, cycle):
    """config/mixamo_clips.json body_overrides: where a cycle's clip does not suit a body, the entry for that body and cycle
    ({"clip", "rate", "crouch": {"spine_deg", "thigh_deg"}, "why"}), else None."""
    body = (getattr(actor, "entry", None) or {}).get("body")
    ov = (registry().get("body_overrides") or {}).get(body, {}).get(cycle)
    if ov:
        require(ov["clip"])
    return ov


def crouch(J, spec):
    """A crouch laid over a pose: the spine bent forward and the thighs lifted with the knees folded twice as far (the
    hips follow the floor afterwards). spec: spine_deg (shared over the three spine joints as lean() does), thigh_deg."""
    J = dict(J)
    sd, td = float(spec.get("spine_deg", 0.0)), float(spec.get("thigh_deg", 0.0))
    for jn, k in (("spine", 0.30), ("spine1", 0.35), ("torso", 0.35)):
        J[jn] = J[jn] @ Quaternion((1, 0, 0), math.radians(sd * k))
    for s in "LR":
        J[f"hip.{s}"] = J[f"hip.{s}"] @ Quaternion((1, 0, 0), -math.radians(td))
        J[f"kn.{s}"] = J[f"kn.{s}"] @ Quaternion((1, 0, 0), math.radians(2.0 * td))
        J[f"an.{s}"] = J[f"an.{s}"] @ Quaternion((1, 0, 0), math.radians(td - 2.0 * td))
    return J


def walk(actor, t0, to, speed=None, view=None, face=None, then_view=None, cycle="walk", arms=True, blend_in=0.25, blend_out=0.32):
    """ActorAj.walk on a clip: turn to the goal, ease in from the current pose, walk on the clip with the stage moving
    exactly as the planted foot does (no sliding), ease out to Standing_Idle's first pose with the feet together, land
    on the goal (a whole number of steps; the rate is adjusted a little, the rest spread over the walk). Returns the
    arrival time."""
    from . import cast as cast2d
    ov = body_override(actor, cycle)
    name = ov["clip"] if ov else CYCLES.get(cycle, CYCLES["walk"])
    require(name)
    require(EXIT_IDLE)
    clip = _import(name)
    idle = _import(EXIT_IDLE)
    bd = body(actor)
    shot = actor.shot
    fps = shot.fps
    start = Vector((actor._pos.x, actor._pos.y))
    goal = Vector((to[0], to[1]))
    D = goal - start
    dist = D.length
    if dist < 1e-3:
        return t0
    dirw = D.normalized()
    actor.heading(to, t0, 0.2)
    sp = DEFAULT_SPEED.get(cycle, 2.0) if speed is None else float(speed)
    rate0 = max(0.7, min(1.4, sp / DEFAULT_SPEED.get(cycle, 2.0)))
    if ov:                                                   # another clip stands in for this body: its own pace
        rate0 = max(0.3, min(1.4, float(ov.get("rate", 1.0)) * sp / DEFAULT_SPEED.get(cycle, 2.0)))
        actor.shot.notes.append(f"{actor.id}: {cycle} on {actor.entry['body']} plays {name} at {rate0:.2f}x"
                                f"{' with a crouch' if ov.get('crouch') else ''} ({ov.get('why', 'config/mixamo_clips.json body_overrides')})")
    k = actor.scale
    # the cycle on this body, densely: joint values, positions, planted points
    N = max(2, clip.n - 1)
    cyc = clip.duration
    samp = []
    for i in range(N):
        q, loc = clip.sample(i / clip.fps, True)
        J, hl = bd.joints(q, loc)
        pos, _r = bd.fk(J, hl)
        samp.append((J, hl, pos, _planted_point(bd, pos)))
    mid_x = sum(s[1].x for s in samp) / N
    mid_y = sum(s[1].y for s in samp) / N
    lo = {s: min(p[3][s][1] for p in samp) for s in "LR"}

    def planted(pp, s):
        return pp[s][1] - lo[s] < CONTACT

    # entry phase: the first frame where one foot is high in its swing and the other planted
    swing_h = [max(p[3]["L"][1] - lo["L"], p[3]["R"][1] - lo["R"]) for p in samp]
    singles = [i for i in range(N) if (planted(samp[i][3], "L") != planted(samp[i][3], "R"))]

    def stance_left(i):
        """Clip frames the foot that carries the body at frame i stays planted from there (looping)."""
        sd = "L" if planted(samp[i][3], "L") else "R"
        c = 0
        while c < N and planted(samp[(i + c) % N][3], sd):
            c += 1
        return c
    # the blends ease the clip's clock in and out, so it moves about half a blend's worth of clip frames in them:
    # the foot carrying the body must stay planted that long
    nb_in_ = max(1, int(round(blend_in * fps)))
    nb_out_ = max(2, int(round(blend_out * fps)))
    adv_in_ = sum(_smooth((j + 1) / nb_in_) for j in range(nb_in_ + 1))
    adv_out_ = sum(1.0 - _smooth(u / nb_out_) for u in range(1, nb_out_ + 1))
    m_in = adv_in_ * rate0 * clip.fps / fps + 1.5
    m_out = adv_out_ * rate0 * clip.fps / fps + 1.5
    ok_in = [i for i in singles if stance_left(i) >= m_in]
    i_in = (max(ok_in, key=lambda i: swing_h[i]) if ok_in else max(singles, key=stance_left)) if singles else 0
    s_in = i_in / clip.fps
    plant_in = "L" if planted(samp[i_in][3], "L") else "R"
    exits = set(i for i in singles if stance_left(i) >= m_out) or set(singles)
    # standing pose to ease out to: Standing_Idle's first frame
    qi, li = idle.sample(0.0)
    J_stand, h_stand = bd.joints(qi, li)
    h_stand = Vector((bd.W["hips"].x, bd.W["hips"].y, h_stand.z))
    js = _groups_joints(actor, ("legs", "spine", "head") + (("arm.L", "arm.R") if arms else ()))
    nb_in = max(1, int(round(blend_in * fps)))
    nb_out = max(2, int(round(blend_out * fps)))

    def clip_at(s):
        q, loc = clip.sample(s, True)
        J, hl = bd.joints(q, loc)
        if ov and ov.get("crouch"):
            J = crouch(J, ov["crouch"])
        return J, Vector((bd.W["hips"].x + hl.x - mid_x, bd.W["hips"].y + hl.y - mid_y, hl.z))

    def mix(Ja, ha, Jb, hb, w):
        J = {}
        for jn in JOINTS:
            a, b = Ja[jn], Jb[jn]
            if a.dot(b) < 0:
                b = -b
            J[jn] = a.slerp(b, w)
        return J, ha.lerp(hb, w)

    f0 = actor._f(t0)
    base0 = {jn: joint_now(actor, jn, f0) for jn in JOINTS}
    hips0 = hips_now(actor, f0)

    # how fast the planted foot moves back on this body (native m per clip second): the body travels at that speed
    # times the clip's clock, so the stage is smooth and the feet only need small corrections (see _lock_feet)
    vx, vy = [], []
    for i in range(N):
        for sd in "LR":
            a_, b_ = samp[i][3], samp[(i + 1) % N][3]
            if planted(a_, sd) and planted(b_, sd):
                kd = "toe" if (samp[i][2][f"toe.{sd}"] - a_[sd][0]).length < 1e-9 else "an"
                d = samp[(i + 1) % N][2][f"{kd}.{sd}"] - samp[i][2][f"{kd}.{sd}"]
                vx.append(d.x * clip.fps)
                vy.append(d.y * clip.fps)
    # straight ahead only: a clip that drifts a little sideways would walk the figure off its line
    v_clip = Vector((0.0, statistics.median(vy))) if vy else Vector((0.0, 1.0))

    def phase_support(s):
        i = int(round((s % cyc) * clip.fps)) % N
        pp = samp[i][3]
        if planted(pp, "L") != planted(pp, "R"):
            return "L" if planted(pp, "L") else "R"
        return min("LR", key=lambda sd: pp[sd][1])

    def simulate(rate, n_cyc_frames):
        """Per-frame poses of a walk with n_cyc_frames frames on the clip between the entry and the exit:
        (joints, hips, model travel, the foot that carries the body in a blend or None)."""
        poses = []
        s = s_in
        sup_out = None
        travel = Vector((0.0, 0.0))
        prev_pos, prev_s = None, s
        nf = nb_in + n_cyc_frames + nb_out
        for j in range(nf + 1):
            if j <= nb_in:
                w = _smooth(j / nb_in)
                Jc, hc = clip_at(s)
                J, h = mix(base0, hips0, Jc, hc, w)
                sup = plant_in
                ds = rate / fps * _smooth((j + 1) / nb_in)        # the clip's clock speeds up as it blends in
            elif j <= nb_in + n_cyc_frames:
                J, h = clip_at(s)
                sup = None
                ds = rate / fps
            else:
                u = (j - nb_in - n_cyc_frames) / nb_out
                w = _smooth(u)
                Jc, hc = clip_at(s)
                J, h = mix(Jc, hc, J_stand, h_stand, w)
                if sup_out is None:
                    sup_out = phase_support(s)
                sup = sup_out
                ds = rate / fps * (1.0 - w)
            pos, _r = bd.fk(J, h)
            if j > 0:
                if sup is not None:
                    # in a blend the pose changes under the foot that carries the body: it stays put, the body
                    # moves by minus its motion (the same point of the foot on both frames)
                    kd = "toe" if pos[f"toe.{sup}"].z - bd.W[f"toe.{sup}"].z < pos[f"an.{sup}"].z - bd.W[f"an.{sup}"].z else "an"
                    d = pos[f"{kd}.{sup}"] - prev_pos[f"{kd}.{sup}"]
                    travel = travel - Vector((d.x, d.y))
                else:
                    travel = travel - v_clip * (s - prev_s)
            poses.append((J, h, travel.copy(), sup))
            prev_pos, prev_s = pos, s
            s += ds
        return poses

    # how long on the clip, and the rate. The clip's clock fixes the distance (travel = speed x clip seconds), so it
    # also fixes the phase the walk ends in: the clip time is moved a little (delta) to end with the foot that carries
    # the body planted long enough for the other to come down beside it; the small difference that makes is spread
    # over the walk and taken up by the feet (see _lock_feet). Then the number of cycle frames and the rate.
    need = dist / k
    v = max(1e-4, v_clip.length)
    a_in = sum(_smooth((j + 1) / nb_in) for j in range(nb_in + 1))
    a_out = sum(1.0 - _smooth(u / nb_out) for u in range(1, nb_out + 1))

    def plan(S_target):
        best = None
        step = 0.25 / clip.fps
        for m in range(-int(0.3 / step), int(0.3 / step) + 1):
            S = S_target + m * step
            if S <= 0:
                continue
            n = int(round(S * fps / rate0 - a_in - a_out))
            if n < 0:
                continue
            r = S * fps / (a_in + n + a_out)
            if not (0.8 * rate0 <= r <= 1.25 * rate0):
                continue
            off = (a_in + n) * r / fps
            i = int(round(((s_in + off) % cyc) * clip.fps)) % N
            if i not in exits:
                continue
            key = (abs(m * step), abs(r / rate0 - 1.0))
            if best is None or key < best[0]:
                best = (key, n, r, m * step)
        return best

    best = plan(need / v)
    if best is None:
        n = 0
        S = a_in + a_out
        rate = max(0.3, min(1.6 * rate0, need / v * fps / S))
        actor.shot.notes.append(f"{actor.id}: walk of {dist:.2f} m on {name} is shorter than one clean step; "
                                f"the clip plays at {rate:.2f}x")
        delta = 0.0
        poses = simulate(rate, n)
    else:
        _key, n, rate, delta = best
        poses = simulate(rate, n)
        # the blends travel as the planted foot does, not quite as the clock: plan again on what they did, keep the
        # closest
        keep = (abs(-poses[-1][2].y - need), n, rate, delta, poses)
        for _it in range(3):
            got = -poses[-1][2].y
            S_done = (a_in + n + a_out) * rate / fps
            extra = got - v * S_done
            b2 = plan((need - extra) / v)
            if b2 is None:
                break
            _key, n, rate, delta = b2
            poses = simulate(rate, n)
            if abs(-poses[-1][2].y - need) < keep[0]:
                keep = (abs(-poses[-1][2].y - need), n, rate, delta, poses)
        _e, n, rate, delta, poses = keep
    fwd = Vector((0.0, -1.0))
    nf = len(poses)
    f_first = f0
    f_last = f0 + nf - 1
    L = new_layer(actor, name, ("legs", "spine", "head") + (("arm.L", "arm.R") if arms else ()), f_first, f_last)
    stage0 = Vector(_value(actor.stage, "location", 3, f0))
    # the heading is held during the walk: model travel is the world travel turned by it and scaled by the actor
    yaw = _yaw(actor, f_first)
    c, s_ = math.cos(-yaw), math.sin(-yaw)
    D_model = Vector((c * D.x - s_ * D.y, s_ * D.x + c * D.y)) / k
    miss = D_model - poses[-1][2]
    T = [p[2] + miss * (j / max(1, nf - 1)) for j, p in enumerate(poses)]
    # "still" scales with the pace: a planted foot creeps a little with the spread miss, a swinging one moves at
    # about twice the body's speed
    sk = skin(actor)
    # the lower foot stands on the floor: the hips follow it up or down by what is missing (a hover of a few cm in a
    # crouch, a toe through the floor), eased over a few frames; a foot far off the floor (a run's flight) is left
    raw = []
    for J_, h_, _tr, _sp in poses:
        pos_, rot_ = bd.fk(J_, h_)
        need_ = SKIN_EPS - sk.low(pos_, rot_, ("an.L", "toe.L", "an.R", "toe.R"))
        raw.append(need_ if (ov and ov.get("crouch")) or abs(need_) < FLOOR_NEAR * kleg(bd) else 0.0)
    dzw = _smooth_series(raw, 2)
    poses = [(J_, h_ + Vector((0.0, 0.0, dzw[i])), tr_, sp_) for i, (J_, h_, tr_, sp_) in enumerate(poses)]
    pre = getattr(actor, "_pre_steps", None)
    if pre is None:
        pre = actor._pre_steps = {}
    for j in range(1, nf):                                   # how far each joint turns per frame in the clip itself
        for jn in JOINTS:
            d = math.degrees(poses[j - 1][0][jn].rotation_difference(poses[j][0][jn]).angle)
            pre[(f_first + j, jn)] = min(d, 360.0 - d)
    locks = _lock_feet(bd, poses, T, still=max(LOCK_STILL * kleg(bd), 0.25 * v * rate / fps), lift=foot_lift(bd, sk, poses))
    for j, (J, h, tr, _sup) in enumerate(poses):
        f = f_first + j
        if f not in L.base:
            continue
        L.want[f] = locks["J"][j]
        L.hips[f] = h
        L.w[f] = 1.0
        L.stage[f] = Vector((stage0.x, stage0.y, stage0.z)) + _to_world(actor, f, Vector((T[j].x, T[j].y, 0.0)))
    L.frames = [f for f in L.frames if f in L.w]
    finish_layer(L, "standing")
    actor._last_walk = {"clip": name, "rate": round(rate, 3), "frames": nf, "cycle_frames": n,
                        "miss_cm": round(miss.length * k * 100, 2), "entry_phase_s": round(s_in, 3),
                        "foot_ik_max_cm": round(locks["max_offset"] * k * 100, 2), "v_native_m_s": round(v, 3),
                        "unreached_cm": round(locks["unreached"] * k * 100, 2)}
    if locks["unreached"] * k > 0.015:
        actor.shot.notes.append(f"{actor.id}: walk on {name}: a planted foot is {locks['unreached'] * k * 100:.1f} cm from where "
                                "it should stay (the leg cannot reach); it slides that much")
    z = actor._pos.z
    actor._pos = Vector((goal.x, goal.y, z))
    actor._legs_now = (0.0, 0.0)
    t_end = (f_last - 1) / fps
    # where it faces afterwards: as Actor3D.walk
    cy = actor._cam_yaw(actor._f(t_end))
    right = Vector((math.cos(cy), math.sin(cy)))
    sx = dirw.dot(right)
    if abs(sx) > 0.25:
        actor._face = 1 if sx > 0 else -1
    if face:
        actor._face = 1 if str(face).lower().startswith("r") else -1
    if then_view or view:
        actor._view = {0: "front", 1: "3q", 2: "side"}[cast2d.VIEW_INDEX[str(then_view or view).lower()]]
        actor._orient(t_end + 0.3, 0.3)
    else:
        actor._view = "side" if abs(sx) > 0.7 else "3q"
    return t_end


# ------------------------------------------------------------------------------------------------------ idle
def idle_request(actor, t0, t1, clip=EXIT_IDLE):
    """ActorAj.idle: from t0 to t1, wherever nothing else moves the body, it breathes and shifts its weight on a
    standing idle clip (filled in at _finalize, when every other key is known)."""
    try:
        require(clip)
    except MissingClip:
        actor.shot.notes.append(f"{actor.id}: idle clip {clip} is missing; the figure stands still")
        return
    if not hasattr(actor, "_idle_requests"):
        actor._idle_requests = []
    actor._idle_requests.append((t0, t1, clip))


def _plant_idle(bd: Body, L: Layer, f):
    """An idle layer on the legs: blend it with what was there here (not at write time) and put the ankles back where
    the standing figure has them, so the weight shift and the blends in and out never move the feet."""
    w = L.w[f]
    base = L.base[f]
    J = {}
    for jn in JOINTS:
        q = L.want[f].get(jn)
        b = base.get(jn)
        if q is None or b is None:
            J[jn] = q if q is not None else b
            continue
        if b.dot(q) < 0:
            b = -b
        J[jn] = b.slerp(q, w) if jn in L.joints else b
    if any(v is None for v in J.values()):
        return
    hb = base["__hips"]
    h = hb.lerp(L.hips[f], w)
    Jb = {jn: base.get(jn, J[jn]) for jn in JOINTS}
    pos_b, rot_b = bd.fk(Jb, hb)
    pos, rot = bd.fk(J, h)
    for s in "LR":                                           # ankle AND foot turn stay as they were: the toes do not slide
        _leg_to(J, pos, rot, s, pos[f"hip.{s}"], pos_b[f"an.{s}"], foot=rot_b[f"an.{s}"])
    L.want[f] = J
    L.hips[f] = h
    L.w[f] = 1.0


def holding(actor, side, f) -> bool:
    """Is a prop in this hand at frame f (its hold constraint on)?"""
    for _name, (cons, _tgt, s, _o) in getattr(actor, "_held", {}).items():
        if s != side or not cons:
            continue
        c = cons[0]
        v = c.influence
        owner = c.id_data
        for fc in core.fcurves(owner):
            if fc.data_path == f'constraints["{c.name}"].influence':
                v = fc.evaluate(f)
        if v > 0.5:
            return True
    return False


def _static(actor, jn, f, k=3, tol_deg=0.6):
    """The joint does not move around frame f (a pose being held, not a gesture)."""
    q = joint_now(actor, jn, f)
    for g in (max(1, f - k), f + k):
        if math.degrees(q.rotation_difference(joint_now(actor, jn, g)).angle) > tol_deg:
            return False
    return True


def _idle_fill(actor, t0, t1, clipname):
    """Fill the frames of [t0, t1] where the body is standing still (legs held, hips at standing height, no clip on
    them) with the idle clip, blending in and out over a quarter second; the spine and each free arm idle with them."""
    clip = _import(clipname)
    bd = body(actor)
    fps = actor.shot.fps
    fa, fb = actor._f(t0), min(actor._f(t1), int(bpy.context.scene.frame_end))
    owned = set()
    for L in _layers(actor):
        if not getattr(L, "idle", False):
            owned.update(L.frames)
    def free(group, f):
        if f in owned:
            return False
        if group == "legs":
            if abs(hips_now(actor, f).z - actor._hips_rest.z) > 0.03:
                return False
            return all(_static(actor, j, f) for j in ("hip.L", "hip.R", "kn.L", "kn.R"))
        if group == "spine":
            return all(_static(actor, j, f) for j in ("spine", "spine1", "torso"))
        s = group[-1]
        if holding(actor, s, f):
            return False
        return all(_static(actor, j, f, tol_deg=1.0) for j in (f"sh.{s}", f"el.{s}"))

    groups = ["legs", "spine", "arm.L", "arm.R"]
    mask = {g: [free(g, f) for f in range(fa, fb + 1)] for g in groups}
    # the spine idles only with the legs (a weight shift goes through both); arms only when the legs idle too
    for g in ("spine", "arm.L", "arm.R"):
        mask[g] = [m and lg for m, lg in zip(mask[g], mask["legs"])]
    nb = max(2, int(round(0.25 * fps)))
    for g in groups:
        runs = _runs([fa + i for i, m in enumerate(mask[g]) if m])
        for r0, r1 in runs:
            if r1 - r0 < 2 * nb + 4:
                continue
            L = new_layer(actor, clipname, (g,), r0, r1)
            L.idle = True
            for f in L.frames:
                s = (f - 1) / fps
                q, loc = clip.sample(s, True)
                J, hl = bd.joints(q, loc)
                L.want[f] = J
                if L.owns_legs:
                    q0, l0 = clip.sample(0.0)
                    _J0, h0 = bd.joints(q0, l0)
                    L.hips[f] = Vector((bd.W["hips"].x + hl.x - h0.x, bd.W["hips"].y + hl.y - h0.y, hl.z))
                else:
                    L.hips[f] = None
                L.w[f] = min(_smooth((f - r0) / nb), _smooth((r1 - f) / nb))
                if L.owns_legs:
                    _plant_idle(bd, L, f)
            write_layer(L)
            _layers(actor).append(L)


# ------------------------------------------------------------------------------------- clip-backed named actions
# actions.run sends these names here for Aj figures (family "aj"). Each keeps the action's name, arguments and hit
# contract: `hit` lands on the clip's own event (the seat, the knee down, the ground, the hand up) and `t` is the
# start; each returns the end time. Anything a clip cannot do (jump to a place, a fall to a place) goes back to the
# procedural action (returns None).
SEAT_UNDER = 0.13        # hip joint above the seat surface when seated, in leg lengths (thigh and buttock: a measured
                         # estimate on the Male_Teen sheet, not a mesh measurement per body)


def _ev(name, key, default=0.0):
    return float(((require(name).get("analysis") or {}).get("events_s") or {}).get(key, default))


def _start(t, hit, lead, k=1.0):
    return max(0.0, (float(hit) - lead / k) if hit is not None else float(t))


def _state(actor):
    return getattr(actor, "_clip_state", "standing")


def _seat_top(seat):
    """World height of the top of a seat object (its evaluated bounding box), or a number given directly."""
    if seat is None:
        return None
    if isinstance(seat, (int, float)):
        return float(seat)
    ob = getattr(seat, "obj", None) or getattr(seat, "root", None) or seat
    try:
        from mathutils import Vector as V
        obs = [ob] + list(getattr(ob, "children_recursive", []))
        zs = [(o.matrix_world @ V(c)).z for o in obs if getattr(o, "type", "") == "MESH" for c in o.bound_box]
        return max(zs) if zs else None
    except Exception:
        return None


def act_sit_down(A, t, hit=None, on=None, **_kw):
    a = A.a
    name = "Stand_To_Sit"
    seat_t = _ev(name, "seat", 1.5)
    t0 = _start(t, hit, seat_t, A.k)
    hips_dz = None
    top = _seat_top(on)
    if top is not None:
        bd = body(a)
        leg = bd.leg
        clip_seat = (require(name)["analysis"]["hips_end_per_leg"] - SEAT_UNDER) * leg      # native, as the clip sits
        want = (top - a.stage.matrix_world.translation.z) / a.scale                         # native
        dz = want - clip_seat
        k_seat = seat_t / max(1e-3, require(name)["duration_s"])

        def hips_dz(f, u, dz=dz, k_seat=k_seat):
            return dz * _smooth(u / max(1e-3, k_seat))
        a._seat_dz = dz
    t1 = play(a, name, t0, rate=A.k, state="sitting", hips_dz=hips_dz)
    return t1


def act_sit_idle(A, t, until=None, **_kw):
    a = A.a
    if _state(a) != "sitting":
        return None                    # not seated by sit_down: Sitting_Idle from standing would sit in the air
    t1 = until if until is not None else t + 2.0 / A.k
    dz = getattr(a, "_seat_dz", None)
    return play(a, "Sitting_Idle", t, loop=True, until=t1, state="sitting", blend=0.4,
                hips_dz=(lambda f, u, dz=dz: dz) if dz else None)


def act_stand_up(A, t, hit=None, **_kw):
    a = A.a
    st = _state(a)
    if st == "sitting":
        name, ev = "Sit_To_Stand", "up"
    elif st == "kneeling":
        name, ev = "Kneel_To_Stand", "up"
    elif st == "lying":
        name, ev = "Getting_Up", "up"
    else:
        return t
    t0 = _start(t, hit, _ev(name, ev), A.k)
    dz = getattr(a, "_seat_dz", None) if st == "sitting" else None
    rise = _ev(name, "rise", 0.5) / max(1e-3, require(name)["duration_s"])
    hd = (lambda f, u, dz=dz, rise=rise: dz * (1.0 - _smooth(u / max(1e-3, rise * 1.6)))) if dz else None
    a._seat_dz = None
    return play(a, name, t0, rate=A.k, state="standing", hips_dz=hd)


def act_kneel(A, t, hit=None, **_kw):
    a = A.a
    name = "Kneeling_Down"
    t0 = _start(t, hit, _ev(name, "knee_down", 2.4), A.k)
    return play(a, name, t0, rate=A.k, state="kneeling")


LIE_RATE = 1.6           # Getting_Up played backward, this much faster than the clip (it is a slow, careful get-up)


def act_lie_down(A, t, hit=None, **_kw):
    """Getting_Up played backward from standing to lying, then Laying_Idle. (Tried first: Kneeling_Down then a 0.8 s
    pose blend into Laying_Idle; the blend swings the legs through the floor, about 36 cm on Male_Teen.)
    hit = the back touches the floor."""
    a = A.a
    name = "Getting_Up"
    up, s0 = _ev(name, "up", 5.5), float(require(name)["analysis"].get("moves_s", 0.7))
    k = LIE_RATE * A.k
    t0 = _start(t, hit, (up - s0) / k, 1.0)
    t1 = play(a, name, t0, rate=k, start=s0, end_at=up, reverse=True, state="lying")
    return play(a, "Laying_Idle", t1, blend=0.4, loop=True, until=t1 + 0.6, state="lying")


def act_sleep(A, t, until=None, **_kw):
    a = A.a
    if _state(a) != "lying":
        return None                                      # nodding off upright: the procedural action
    t1 = until if until is not None else t + 3.0 / A.k
    a.eyes_closed(t, t1)
    return play(a, "Sleeping_Idle", t, loop=True, until=t1, state="lying", blend=0.5)


def act_get_up(A, t, hit=None, **_kw):
    a = A.a
    if _state(a) != "lying":
        return act_stand_up(A, t, hit)
    name = "Getting_Up"
    s0 = max(0.0, _ev(name, "rise", 3.8) - 1.2)        # the clip lies still for its first seconds: start nearer the rise
    up = _ev(name, "up", 5.5) - s0
    t0 = _start(t, hit, up, A.k)
    return play(a, name, t0, rate=A.k, start=s0, state="standing")


def act_wake_up(A, t, hit=None, **_kw):
    a = A.a
    a.expr("surprised", t + 0.1, 0.06)
    if _state(a) == "lying":
        return act_get_up(A, t, hit)
    return None


def act_fall(A, t, hit=None, to=None, forward=True, **_kw):
    a = A.a
    if to is not None:
        return None
    name = "Falling_Back"
    t0 = _start(t, hit, _ev(name, "ground", 1.5), A.k)
    a.expr("surprised", t0, 0.06)
    if forward:
        a.shot.notes.append(f"{a.id}: fall on an Aj figure falls backward (Falling_Back is the only fall clip)")
    return play(a, name, t0, rate=A.k, state="lying")


def act_slip(A, t, hit=None, **_kw):
    a = A.a
    name = "Stumble_Backwards"
    t0 = _start(t, hit, _ev(name, "ground", 1.533), A.k)
    a.expr("surprised", t0, 0.05)
    return play(a, name, t0, rate=A.k, state="sitting")


def act_jump(A, t, hit=None, to=None, height=None, **_kw):
    if to is not None:
        return None
    a = A.a
    name = "Jump"
    t0 = _start(t, hit, _ev(name, "takeoff", 0.833), A.k)
    return play(a, name, t0, rate=A.k, state="standing")


def act_salute(A, t, hit=None, target=None, hold=0.4, **_kw):
    a = A.a
    name = "Salute"
    t0 = _start(t, hit, _ev(name, "hand_up", 0.9), A.k)
    if target is not None and hasattr(a, "look_at"):
        try:
            a.look_at(target, t0, 0.3)
        except Exception:
            pass
    return play(a, name, t0, groups=("spine", "arm.L", "arm.R", "head"), rate=A.k)


ACTIONS = {
    "sit_down": act_sit_down, "sit_idle": act_sit_idle, "stand_up": act_stand_up, "kneel": act_kneel,
    "lie_down": act_lie_down, "sleep": act_sleep, "get_up": act_get_up, "wake_up": act_wake_up,
    "fall": act_fall, "slip": act_slip, "slip_banana": None, "jump": act_jump, "salute": act_salute,
}
# walk, pace, step_forward, chase, run, sneak and tiptoe need nothing here: they go through actor.walk, which is the
# clip walk on an Aj figure. slip_banana keeps its procedural staging (the peel) and its own slip.


def dispatch(actor, name, t, hit, k, kw):
    """actions.run's hook for Aj figures: the clip-backed action, or None to run the procedural one."""
    fn = ACTIONS.get(name)
    if fn is None:
        return None

    class _A:
        pass
    A = _A()
    A.a, A.k = actor, k
    return fn(A, t, hit=hit, **kw)
