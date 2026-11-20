"""stagekit.cast - characters from the clay character pack (packs/release_1), placed and animated by time.

The pack does the hard part (rig, clothes, hair, colour rule, walk retarget, brows, blink). This module adds what a
shot needs: put a character somewhere, face something, walk to a mark, hit a pose, look, react, hold a prop -
all keyed in seconds so the action lines up with the narration.

Facing: 0 = toward the default camera side (-Y), 90 = screen-right (+X), -90 = screen-left, 180 = away (+Y).

What is reliable: standing, walking between marks, sitting, lying, simple arm poses, head turns, brows, blinks,
a prop in a hand. What to stage around (see the style guide): two characters touching, finger acting, climbing,
fighting, subtle mouth acting (the characters have no mouth).
"""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import core

_SRC = {}                 # cached Mixamo walk samples
_AXIS = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}

# Poses are armature-space rotations applied on top of the relaxed stand, parent bones first.
# X+ leans forward/down, X- raises a limb forward; Y drops/raises arms sideways (as the pack's A-pose); Z twists.
# ("torso", "drop", metres) lowers the hips.  Sides: .L is the character's left (screen-right when facing camera).
POSES = {
    "relaxed": [],
    "hand_up_R": [("upper_arm_fk.R", "X", -30), ("forearm_fk.R", "X", -115)],
    "hand_up_L": [("upper_arm_fk.L", "X", -30), ("forearm_fk.L", "X", -115)],
    "reach_R": [("upper_arm_fk.R", "X", -78), ("forearm_fk.R", "X", -8)],
    "reach_L": [("upper_arm_fk.L", "X", -78), ("forearm_fk.L", "X", -8)],
    "point_R": [("upper_arm_fk.R", "X", -88)],
    "point_L": [("upper_arm_fk.L", "X", -88)],
    "arms_up": [("upper_arm_fk.R", "X", -160), ("upper_arm_fk.L", "X", -160)],
    "hands_to_face": [("upper_arm_fk.R", "X", -55), ("forearm_fk.R", "X", -120), ("upper_arm_fk.L", "X", -55), ("forearm_fk.L", "X", -120)],
    "carry": [("upper_arm_fk.R", "X", -18), ("forearm_fk.R", "X", -62), ("upper_arm_fk.L", "X", -18), ("forearm_fk.L", "X", -62)],
    "lean_forward": [("torso", "X", 16)],
    "lean_back": [("torso", "X", -10)],
    "bow_head": [("neck", "X", 12), ("head", "X", 22)],
    "head_up": [("head", "X", -22)],
    "slump": [("torso", "X", 10), ("neck", "X", 10), ("head", "X", 18)],
    "crouch": [("torso", "drop", 0.42), ("torso", "X", 22), ("thigh_fk.L", "X", -95), ("thigh_fk.R", "X", -95),
               ("shin_fk.L", "X", 120), ("shin_fk.R", "X", 120), ("foot_fk.L", "X", -25), ("foot_fk.R", "X", -25)],
    "sit": [("torso", "drop", "seat"), ("thigh_fk.L", "X", -86), ("thigh_fk.R", "X", -86), ("shin_fk.L", "X", 86), ("shin_fk.R", "X", 86),
            ("upper_arm_fk.R", "X", -18), ("forearm_fk.R", "X", -40), ("upper_arm_fk.L", "X", -18), ("forearm_fk.L", "X", -40)],
}


class Anchor:
    """A point on a character that follows the animation (head, chest, hands, feet). Use it as a camera aim or
    focus target, or as a place to attach a prop."""

    def __init__(self, actor, bone: str, rest_offset=(0, 0, 0)):
        self.actor, self.bone = actor, bone
        b = actor.rig.data.bones[bone]
        # offset is given in armature space at rest (x left, -y front, z up) and stored bone-local so it rides the bone
        self.local = b.matrix_local.inverted() @ (b.head_local + Vector(rest_offset))
        self._empty = None

    def point(self) -> Vector:
        bpy.context.view_layer.update()
        rig = self.actor.rig
        return rig.matrix_world @ (rig.pose.bones[self.bone].matrix @ self.local)

    def object(self):
        """An empty riding on the bone, for constraints and depth-of-field focus."""
        if self._empty is None or self._empty.name not in bpy.data.objects:
            _, cf, _ = core.pack_modules()
            e = core.empty(f"{self.actor.name}_{self.bone.replace('.', '_')}_anchor", coll="RIG", size=0.05)
            cf.rigid_parent(e, self.actor.rig, self.bone, Matrix.Translation(self.point()))
            self._empty = e
        return self._empty


class Actor:
    def __init__(self, name: str, ch):
        self.name, self.ch, self.rig = name, ch, ch.rig
        self.head = Anchor(self, "head", (0, -0.075, 0.12))      # between the eyes
        self.chest = Anchor(self, "chest", (0, 0, 0.1))
        self.hips = Anchor(self, "torso")
        self.hand_R = Anchor(self, "hand_fk.R", (-0.07, 0, 0))   # palm
        self.hand_L = Anchor(self, "hand_fk.L", (0.07, 0, 0))
        self.feet = Anchor(self, "root")
        self._cycle = None
        self._facing = 0.0
        self._look = (0.0, 0.0)
        self._s = self.rig.matrix_world.to_scale().x
        self._reset_to_idle()

    # ------------------------------------------------------------------ basics
    @property
    def meshes(self):
        return [o for o in self.ch.objs.values() if o.type == "MESH"] + [o for o in self.ch.accessories.values() if getattr(o, "type", "") == "MESH"]

    @property
    def position(self) -> Vector:
        bpy.context.view_layer.update()
        return self.rig.matrix_world.translation.copy()

    def height(self) -> float:
        lo, hi = core.world_bbox(self.meshes)
        return hi.z - lo.z

    def place(self, at, facing: float | None = None, t: float | None = None):
        """Stand at (x, y[, z]). With t, the placement is keyed (a jump between two holds reads as a cut-in-place: avoid)."""
        at = Vector((at[0], at[1], at[2] if len(at) > 2 else 0.0))
        self.rig.location = at
        if facing is not None:
            self._facing = float(facing)
            self.rig.rotation_euler = (self.rig.rotation_euler.x, 0.0, math.radians(self._facing))
        if t is not None:
            core.key(self.rig, "location", t)
            core.key(self.rig, "rotation_euler", t)
        bpy.context.view_layer.update()
        return self

    def appear(self, t: float):
        """Keep the character out of the render until time t (it is in the set but must not be seen yet, e.g. while the
        camera holds on something else). Use it for fair hiding, never for a pop-in inside the frame."""
        f = core.current().f(t)
        for o in self.meshes:
            o.hide_render = True
            o.keyframe_insert("hide_render", frame=max(1, f - 1))
            o.hide_render = False
            o.keyframe_insert("hide_render", frame=f)
        return self

    def face(self, target, t: float | None = None, duration: float = 0.5):
        """Turn the whole body toward a point/object/anchor, or to an angle in degrees. With t it turns over `duration`."""
        if isinstance(target, (int, float)):
            ang = float(target)
        else:
            if t is not None:
                bpy.context.scene.frame_set(core.current().f(t))
            d = core.point_of(target) - self.position
            ang = math.degrees(math.atan2(d.x, -d.y))
        if t is None:
            self._facing = ang
            self.rig.rotation_euler.z = math.radians(ang)
        else:
            cur = self._facing
            ang = cur + ((ang - cur + 180) % 360 - 180)        # shortest way round
            core.key(self.rig, "rotation_euler", max(0.0, t - duration), index=2)
            self.rig.rotation_euler.z = math.radians(ang)
            core.key(self.rig, "rotation_euler", t, index=2)
            self._facing = ang
        bpy.context.view_layer.update()
        return self

    # ------------------------------------------------------------------ animation plumbing
    def _action(self):
        rig = self.rig
        if rig.animation_data is None or rig.animation_data.action is None:
            rig.keyframe_insert("location", frame=1)
        return rig.animation_data.action

    def _write(self, bone: str, prop: str, frames, values, linear: bool = True):
        """Replace keys of pose.bones[bone].prop over the given frames. values: list of tuples."""
        act = self._action()
        path = f'pose.bones["{bone}"].{prop}'
        f0, f1 = frames[0], frames[-1]
        for i in range(len(values[0])):
            fc = act.fcurve_ensure_for_datablock(self.rig, path, index=i)
            for kp in reversed(list(fc.keyframe_points)):
                if f0 <= kp.co.x <= f1:
                    fc.keyframe_points.remove(kp, fast=True)
            for f, v in zip(frames, values):
                kp = fc.keyframe_points.insert(f, v[i], options={"FAST"})
                kp.interpolation = "LINEAR" if linear else "BEZIER"
            fc.update()

    def _read(self, bone: str, prop: str):
        return tuple(getattr(self.rig.pose.bones[bone], prop))

    def _rot_prop(self, bone: str) -> str:
        return "rotation_quaternion" if self.rig.pose.bones[bone].rotation_mode == "QUATERNION" else "rotation_euler"

    def _reset_to_idle(self):
        _, cf, mr = core.pack_modules()
        mr.clear_pose(self.rig)
        hs = float(self.rig.get("clay_head_scale", 1.0))
        if abs(hs - 1.0) > 1e-6:
            self.rig.pose.bones["head"].scale = (hs, hs, hs)
        mr.pose_arms_fk(self.rig, 79.0)
        for side in "LR":                                        # a soft elbow: straight arms read as a mannequin
            pb = self.rig.pose.bones[f"forearm_fk.{side}"]
            piv = pb.head.copy()
            pb.matrix = Matrix.Translation(piv) @ Matrix.Rotation(math.radians(-14), 4, "X") @ Matrix.Translation(-piv) @ pb.matrix
            bpy.context.view_layer.update()
        mr.apply_brows(self.rig, self.rig.get("clay_brow_preset", "neutral"))
        bpy.context.view_layer.update()

    def _apply_spec(self, spec, seat_height: float = 0.45):
        """Apply armature-space pose steps on top of the relaxed stand (pose is left on the rig, un-keyed)."""
        rig = self.rig
        self._reset_to_idle()
        touched = []
        for bone, axis, val in spec:
            pb = rig.pose.bones[bone]
            if axis == "drop":
                if val == "seat":
                    hip_z = (rig.matrix_world @ rig.pose.bones["thigh_fk.L"].head).z - rig.matrix_world.translation.z
                    val = max(0.0, hip_z - (seat_height + 0.10 * self._s / 1.2))
                pb.matrix = Matrix.Translation((0, 0, -float(val) / self._s)) @ pb.matrix
            else:
                piv = pb.head.copy()
                pb.matrix = Matrix.Translation(piv) @ Matrix.Rotation(math.radians(val), 4, _AXIS[axis]) @ Matrix.Translation(-piv) @ pb.matrix
            bpy.context.view_layer.update()
            if bone not in touched:
                touched.append(bone)
        return touched

    def _snapshot(self, bones):
        out = {}
        for b in bones:
            rp = self._rot_prop(b)
            out[(b, rp)] = self._read(b, rp)
            if b in ("torso",):
                out[(b, "location")] = self._read(b, "location")
        return out

    def _key_snapshot(self, snap_from: dict, snap_to: dict, t: float, blend: float):
        shot = core.current()
        f1 = shot.f(t)
        f0 = max(1, f1 - max(1, int(round(blend * shot.fps))))
        for (b, prop), v1 in snap_to.items():
            v0 = snap_from[(b, prop)]
            if prop == "rotation_quaternion" and sum(a * c for a, c in zip(v0, v1)) < 0:
                v1 = tuple(-c for c in v1)
            if f0 < f1:
                self._write(b, prop, [f0, f1], [v0, v1], linear=False)
            else:
                self._write(b, prop, [f1], [v1], linear=False)

    # ------------------------------------------------------------------ poses
    def pose(self, name_or_spec, t: float = 0.0, blend: float = 0.4, seat_height: float = 0.45):
        """Reach a named pose (see cast.POSES) or a custom spec at time t, easing in over `blend` seconds.
        Poses are absolute (built on the relaxed stand), so the second pose replaces the first.
        Custom spec example: [("upper_arm_fk.R", "X", -60), ("forearm_fk.R", "X", -45)]."""
        spec = POSES[name_or_spec] if isinstance(name_or_spec, str) else name_or_spec
        sc = bpy.context.scene
        shot = core.current()
        f1 = shot.f(t)
        f0 = max(1, f1 - max(1, int(round(blend * shot.fps))))
        # every pose keys the same full set of body bones, so poses never leak into each other
        body = ["torso", "neck", "head"] + [f"{b}.{s}" for s in "LR" for b in ("upper_arm_fk", "forearm_fk", "hand_fk", "thigh_fk", "shin_fk", "foot_fk")]
        sc.frame_set(f0)
        before = self._snapshot(body)
        self._apply_spec(spec, seat_height)
        after = self._snapshot(body)
        self._key_snapshot(before, after, t, blend if t > 0 else 0.0)
        sc.frame_set(f1)
        self._look = (0.0, 0.0)
        return self

    def sit(self, at, facing: float = 0.0, seat_height: float = 0.45, t: float = 0.0, blend: float = 0.0):
        """Sit on a seat whose top is seat_height above `at` z (a chair() is 0.45, a bed mattress 0.5, a crate its size)."""
        self.place(at, facing)
        return self.pose("sit", t, blend, seat_height=seat_height)

    def lie(self, at, head_toward: float = 180.0, z: float = 0.5):
        """Lie on the back at height z (bed mattress top = 0.5), head pointing toward `head_toward` degrees (180 = +Y)."""
        self.rig.rotation_euler = (math.radians(-90.0), 0.0, math.radians(head_toward - 180.0))
        self.rig.location = (at[0], at[1], z + 0.12 * self._s / 1.2)
        self._facing = head_toward - 180.0
        bpy.context.view_layer.update()
        lo, hi = core.world_bbox(self.meshes)
        c = (lo + hi) / 2
        self.rig.location.x += at[0] - c.x                      # centre the body on the mark
        self.rig.location.y += at[1] - c.y
        self.rig.location.z += z - lo.z
        bpy.context.view_layer.update()
        return self

    def look(self, target, t: float = 0.0, blend: float = 0.3):
        """Turn the head (not the body) toward a point/object/anchor, or pass (yaw, pitch) degrees
        (yaw + = to the character's left, pitch + = down). Eyes lead: look ~0.3 s before the body acts."""
        rig = self.rig
        sc = bpy.context.scene
        shot = core.current()
        f1 = shot.f(t)
        f0 = max(1, f1 - max(1, int(round(blend * shot.fps))))
        if isinstance(target, tuple) and len(target) == 2:
            yaw, pitch = target
        else:
            sc.frame_set(f1)
            d = rig.matrix_world.inverted().to_3x3() @ (core.point_of(target) - self.head.point())
            yaw = math.degrees(math.atan2(d.x, -d.y))
            pitch = -math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
        yaw = max(-75.0, min(75.0, yaw))
        pitch = max(-35.0, min(40.0, pitch))
        bones = ["neck", "head"]
        sc.frame_set(f0)
        before = self._snapshot(bones)
        for b in bones:                                         # a look is absolute: start from the neutral head
            pb = rig.pose.bones[b]
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.rotation_euler = (0, 0, 0)
        bpy.context.view_layer.update()
        for b, share in (("neck", 0.4), ("head", 0.6)):
            pb = rig.pose.bones[b]
            piv = pb.head.copy()
            R = Matrix.Rotation(math.radians(yaw * share), 4, "Z") @ Matrix.Rotation(math.radians(pitch * share), 4, "X")
            pb.matrix = Matrix.Translation(piv) @ R @ Matrix.Translation(-piv) @ pb.matrix
            bpy.context.view_layer.update()
        after = self._snapshot(bones)
        self._key_snapshot(before, after, t, blend if t > 0 else 0.0)
        self._look = (yaw, pitch)
        sc.frame_set(f1)
        return self

    # ------------------------------------------------------------------ face
    def brows(self, preset: str, t: float = 0.0, blend: float = 0.15):
        """neutral | calm | worried | stern | shocked | arched | cocky | concerned | proud. The fastest readable emotion."""
        _, _, mr = core.pack_modules()
        shot = core.current()
        f1 = shot.f(t)
        if t > 0 and blend > 0:
            f0 = max(1, f1 - max(1, int(round(blend * shot.fps))))
            bpy.context.scene.frame_set(f0)
            for side in "LR":
                for suf in ("", ".001", ".002", ".003"):
                    self.rig.pose.bones[f"DEF_brow_{side}{suf}"].keyframe_insert("location", frame=f0, group="face_brows")
        mr.key_brows(self.rig, f1, preset)
        self.rig["clay_brow_preset"] = preset if isinstance(preset, str) else self.rig.get("clay_brow_preset", "neutral")
        return self

    def blink(self, t: float):
        _, _, mr = core.pack_modules()
        mr.key_blink(self.rig, start=core.current().f(t))
        return self

    def eyes_closed(self, closed: bool = True, t: float | None = None):
        """Hold the eyes shut (sleeping) or open them at t."""
        _, _, mr = core.pack_modules()
        mr.set_blink_pose(self.rig, 1.0 if closed else 0.0)
        f = core.current().f(t or 0.0)
        for n in ("eye_L", "eye_R"):
            self.rig.pose.bones[n].keyframe_insert("scale", frame=f, group="face_blink")
        for n in ("upper_eyelid_L", "upper_eyelid_R", "lower_eyelid_L", "lower_eyelid_R"):
            self.rig.pose.bones[n].keyframe_insert("location", frame=f, group="face_blink")
        return self

    def idle(self, t0: float = 0.0, t1: float | None = None, seed: int | None = None, blinks: bool = True, breathe: float = 1.0):
        """Never let a character freeze: slow breathing, a blink every few seconds, tiny weight shifts.
        Call it once per character per shot, AFTER walks and poses (it layers on bones those do not own)."""
        shot = core.current()
        t1 = shot.seconds if t1 is None else t1
        rnd = random.Random(seed if seed is not None else hash(self.name) % 1000)
        if blinks:
            t = t0 + rnd.uniform(0.6, 2.0)
            while t < t1 - 0.3:
                self.blink(t)
                t += rnd.uniform(2.2, 4.6)
        if breathe > 0:
            pb = self.rig.pose.bones["chest"]
            period = rnd.uniform(3.2, 4.0)
            t = t0
            k = 0
            frames, vals = [], []
            while t <= t1 + period:
                s = 1.0 + 0.016 * breathe * (k % 2)
                frames.append(shot.f(min(t, shot.seconds)) if t <= shot.seconds else shot.frames + int((t - shot.seconds) * shot.fps))
                vals.append((1.0 + (s - 1.0) * 0.5, s, s))
                t += period / 2
                k += 1
            self._write("chest", "scale", frames, vals, linear=False)
        return self

    # ------------------------------------------------------------------ walking
    def _capture_cycle(self):
        """Bake the pack's Mixamo walk once on this rig and keep it as a reusable pose cycle."""
        if self._cycle is not None:
            return self._cycle
        cl, cf, mr = core.pack_modules()
        from bpy_extras import anim_utils
        rig = self.rig
        sc = bpy.context.scene
        if "S" not in _SRC:
            src = mr.import_mixamo_fbx(cf.PACK_ROOT / cf.asset("walk_mixamo_24fps")["file"])
            _SRC["S"] = mr.sample_source(src)
            for c in bpy.data.collections:
                if c.name.startswith("MIXAMO_SRC"):
                    c.hide_render = True
                    c.hide_viewport = True
        S = _SRC["S"]
        frame = sc.frame_current
        ad = rig.animation_data
        saved_action = ad.action if ad else None
        saved_slot = ad.action_slot if ad and ad.action else None
        loc, rot = rig.location.copy(), rig.rotation_euler.copy()
        rig.location, rig.rotation_euler = (0, 0, 0), (0, 0, 0)
        bpy.context.view_layer.update()
        cyc = int(S["cycle"])
        rep = mr.retarget(rig, S, nframes=cyc + 1, base_xy=(0.0, 0.0), fit_scale=True, action_name=f"{self.name}_walk_tmp")
        act = rig.animation_data.action
        cb = anim_utils.action_get_channelbag_for_slot(act, rig.animation_data.action_slot)
        chan = {}
        for fc in cb.fcurves:
            if not fc.data_path.startswith("pose.bones"):
                continue
            bone = fc.data_path.split('"')[1]
            prop = fc.data_path.rsplit(".", 1)[1]
            chan.setdefault((bone, prop), {})[fc.array_index] = [fc.evaluate(f) for f in range(1, cyc + 2)]
        poses = {k: [tuple(v[i][f] for i in sorted(v)) for f in range(cyc + 1)] for k, v in chan.items()}
        k = float(rep["travel_scale"])
        prog = [0.0]
        for f in range(2, cyc + 2):
            tr, _, _ = mr._travel(S, f, 0)
            prog.append(k * math.hypot(tr.x, tr.y))
        tr_end, _, _ = mr._travel(S, cyc + 1, 0)
        fwd = Vector((tr_end.x, tr_end.y, 0)).normalized()
        rig.animation_data.action = None
        bpy.data.actions.remove(act)
        if saved_action is not None:
            rig.animation_data.action = saved_action
            if saved_slot is not None:
                rig.animation_data.action_slot = saved_slot
        rig.location, rig.rotation_euler = loc, rot
        self._reset_to_idle()
        idle = {key: self._read(*key) for key in poses}
        sc.frame_set(frame)
        self._cycle = {"poses": poses, "prog": prog, "cyc": cyc, "stride": prog[-1], "fwd": fwd, "idle": idle}
        return self._cycle

    def walk(self, t0: float, to=None, distance: float | None = None, speed: float = 1.0, settle: float = 0.25, arms: bool = True):
        """Walk in a straight line from where the character stands at t0 to the mark `to` (x, y) - or `distance` metres
        the way it faces. speed 1.0 is a normal walk (about 1.3 m/s); 0.55 is a careful sneak; 1.35 hurries.
        The body turns to the heading first. arms=False keeps the arms in their current pose (carrying, holding a torch).
        Returns the arrival time in seconds, so the next action can follow it."""
        C = self._capture_cycle()
        shot = core.current()
        sc = bpy.context.scene
        rig = self.rig
        F0 = shot.f(t0)
        sc.frame_set(F0)
        start = rig.matrix_world.translation.copy()
        if to is not None:
            d = Vector((to[0] - start.x, to[1] - start.y, 0.0))
            dist = d.length
            heading = math.degrees(math.atan2(d.x, -d.y)) if dist > 1e-4 else self._facing
        else:
            dist = float(distance)
            heading = self._facing
        if dist < 0.05:
            return t0
        heading = self._facing + ((heading - self._facing + 180) % 360 - 180)
        hv = Vector((math.sin(math.radians(heading)), -math.cos(math.radians(heading)), 0.0))
        cyc, stride, prog = C["cyc"], C["stride"], C["prog"]

        def travelled(u):                       # u = cycle frames elapsed (float)
            n, r = divmod(u, cyc)
            i = int(r)
            fr = r - i
            return n * stride + prog[i] + (prog[min(i + 1, cyc)] - prog[i]) * fr

        N = 1
        while travelled(N * speed) < dist and N < 20000:
            N += 1
        scale = dist / max(travelled(N * speed), 1e-6)
        blend = max(1, int(round(settle * shot.fps)))
        frames = list(range(F0, F0 + N + 1))

        def sample(key, u):
            seq = C["poses"][key]
            r = u % cyc
            i = int(r)
            fr = r - i
            a, b = seq[i], seq[(i + 1) % cyc] if i + 1 >= cyc else seq[i + 1]
            return a, b, fr

        for key in C["poses"]:
            bone, prop = key
            if not arms and any(k in bone for k in ("upper_arm", "forearm", "hand", "shoulder", "f_", "thumb", "palm")):
                continue
            quat = prop == "rotation_quaternion"
            idle = C["idle"][key]
            vals, prev = [], None
            for j in range(N + 1):
                a, b, fr = sample(key, j * speed)
                if quat and sum(x * y for x, y in zip(a, b)) < 0:
                    b = tuple(-x for x in b)
                v = tuple(x + (y - x) * fr for x, y in zip(a, b))
                w = min(1.0, min(j, N - j) / blend)
                w = w * w * (3 - 2 * w)
                base = idle
                if quat and sum(x * y for x, y in zip(base, v)) < 0:
                    base = tuple(-x for x in base)
                v = tuple(x + (y - x) * w for x, y in zip(base, v))
                if quat:
                    n = math.sqrt(sum(x * x for x in v)) or 1.0
                    v = tuple(x / n for x in v)
                    if prev is not None and sum(x * y for x, y in zip(prev, v)) < 0:
                        v = tuple(-x for x in v)
                    prev = v
                vals.append(v)
            self._write(bone, prop, frames, vals, linear=True)
        # body turn into the heading, then the travel itself
        act = self._action()
        if abs(heading - self._facing) > 0.5:
            turn = max(1, int(round(0.3 * shot.fps)))
            fc = act.fcurve_ensure_for_datablock(rig, "rotation_euler", index=2)
            fc.keyframe_points.insert(max(1, F0 - turn), math.radians(self._facing), options={"FAST"})
            fc.keyframe_points.insert(F0 + 2, math.radians(heading), options={"FAST"})
            fc.update()
        self._facing = heading
        rig.rotation_euler.z = math.radians(heading)
        for i in range(3):
            fc = act.fcurve_ensure_for_datablock(rig, "location", index=i)
            for kp in reversed(list(fc.keyframe_points)):
                if F0 <= kp.co.x <= F0 + N:
                    fc.keyframe_points.remove(kp, fast=True)
            for j in range(N + 1):
                p = start + hv * (travelled(j * speed) * scale)
                kp = fc.keyframe_points.insert(F0 + j, p[i], options={"FAST"})
                kp.interpolation = "LINEAR"
            fc.update()
        sc.frame_set(min(F0 + N, shot.frames))
        return (F0 + N - 1) / shot.fps

    def carry(self, other, t: float = 0.0, tilt: float = 32.0, forward: float = 0.34, drop: float = 0.14, turn_in: float = 35.0):
        """Carry a smaller character in both arms (cradle): `other` lies across this character's forearms, head by
        this character's left shoulder, and rides the chest from now on. turn_in > 0 turns the carried face toward the
        carrier, < 0 toward where the carrier is facing (usually the camera). Made for a child carried by an adult.
        Walk with arms=False afterwards so the arms keep holding. It is a 'needs care' build: keep it mid or wide,
        or frame the two faces; never show the pick-up itself."""
        _, cf, _ = core.pack_modules()
        sc = bpy.context.scene
        sc.frame_set(core.current().f(t))
        self.pose("carry", t, blend=0.0)
        other.pose([("thigh_fk.L", "X", -62), ("thigh_fk.R", "X", -62), ("shin_fk.L", "X", 80), ("shin_fk.R", "X", 80),
                    ("upper_arm_fk.L", "X", -12), ("forearm_fk.L", "X", -70), ("upper_arm_fk.R", "X", -12), ("forearm_fk.R", "X", -70)], t, blend=0.0)
        bpy.context.view_layer.update()
        a = math.radians(self._facing)
        fwd = Vector((math.sin(a), -math.cos(a), 0.0))            # where the carrier faces
        left = Vector((math.cos(a), math.sin(a), 0.0))            # the carrier's left
        up = Vector((0.0, 0.0, 1.0))
        tl = math.radians(tilt)
        U = (left * math.cos(tl) + up * math.sin(tl)).normalized()            # feet -> head of the carried body
        F = (up * math.cos(tl) - left * math.sin(tl)).normalized()            # its face direction: up ...
        Fa = Matrix.Rotation(math.radians(abs(turn_in)), 3, U) @ F
        Fb = Matrix.Rotation(math.radians(-abs(turn_in)), 3, U) @ F
        toward_carrier = Fa if Fa.dot(-fwd) > Fb.dot(-fwd) else Fb            # ... turned in toward the carrier,
        F = toward_carrier if turn_in >= 0 else (Fb if toward_carrier is Fa else Fa)   # or out toward the camera
        Y = -F
        X = Y.cross(U).normalized()
        R = Matrix((X, Y, U)).transposed().to_4x4()
        scl = other.rig.scale.copy()
        body = 1.76 * other._s / 1.2                                          # standing height of the carried character
        centre = self.chest.point() + fwd * (forward * self._s / 1.2) - up * drop
        origin = centre - U * (body * 0.58)                                   # so that its hips sit at the carrier's centre line
        W = Matrix.Translation(origin) @ R @ Matrix.Diagonal((*scl, 1.0))
        cf.rigid_parent(other.rig, self.rig, "chest", W)
        other._facing = self._facing
        other.carried_by = self
        bpy.context.view_layer.update()
        return self

    # ------------------------------------------------------------------ props
    def hold(self, prop, hand: str = "R", offset=(0, 0, 0), rotation_deg=(0, 0, 0)):
        """Attach a prop to a hand so it follows the arm (a key, a torch, a bag). Position it with offset (metres, world axes
        at the current pose) and rotation_deg. For a pick-up or put-down, cut or hide the hand at the moment of contact."""
        _, cf, _ = core.pack_modules()
        anchor = self.hand_R if hand.upper() == "R" else self.hand_L
        M = Matrix.Translation(anchor.point() + Vector(offset)) @ Matrix.Rotation(math.radians(rotation_deg[2]), 4, "Z") \
            @ Matrix.Rotation(math.radians(rotation_deg[1]), 4, "Y") @ Matrix.Rotation(math.radians(rotation_deg[0]), 4, "X")
        cf.rigid_parent(prop, self.rig, anchor.bone, M)
        return prop


# ----------------------------------------------------------------------------- spawning
def cast(name: str, preset: str | None = None, base: str | None = None, at=(0, 0), facing: float = 0.0, proportions: str | None = None,
         hair: str | None = None, hair_color: str | None = None, skin: str | None = None, palette: dict | None = None, outerwear: str | None = None,
         beard: str | None = None, brows: str | None = None, chin: str | None = None, hat: str | None = None, body_female: float | None = None) -> Actor:
    """Spawn a character from the pack and return an Actor.

    preset: preset_father | preset_boy | preset_king | preset_female | preset_police | preset_pirate   (ready-made people)
    base:   base_hoodie | base_shirt_tie | base_tshirt   (build someone new: add proportions, hair, skin, palette ...)
    proportions: adult | female | child      hair: one of cf.hair_styles() (e.g. swept_fringe, ponytail, long_fringe, female_long)
    palette: {"top": "#hex", "pants": "#hex", "shoes_upper": "#hex", "jacket": "#hex", ...}   outerwear: jacket | vest | coat
    beard: full | mustache | goatee     hat: hat_police_cap | hat_crown | hat_pirate     brows: a brow preset
    Give every character one clear colour that separates it from the set and from the other characters."""
    _, cf, mr = core.pack_modules()
    kw = {}
    if skin:
        kw["skin"] = skin
    if beard:
        kw["beard"] = beard
    if hair:
        kw["hair"] = hair
    if outerwear:
        kw["outerwear"] = outerwear
    if chin:
        kw["chin_morph"] = chin
    if body_female is not None:
        kw["body_female"] = body_female
    if preset:
        ch = cf.spawn_preset(preset, name, **kw)
        if proportions:
            cf.set_proportions(ch, proportions)
    else:
        ch = cf.spawn_base(base or "base_tshirt", name, proportions=proportions or "adult", brows=brows, **kw)
    pal = dict(palette or {})
    if hair_color:
        pal["hair"] = hair_color
    if pal:
        cf.apply_palette(ch, pal)
    if hat:
        cf.attach_accessory(ch, hat)
    if brows and preset:
        mr.apply_brows(ch.rig, brows)
        ch.rig["clay_brow_preset"] = brows
    a = Actor(name, ch)
    a.place(at, facing)
    core.current().subject(name, a.head)
    return a


def from_plan(cast_id: str, at=(0, 0), facing: float = 0.0, **overrides) -> Actor:
    """Spawn a character exactly as the shot plan's cast list describes it (same person in every shot).
    Overrides are for this shot only, e.g. brows="concerned"."""
    import json
    shot = core.current()
    plan_path = getattr(shot, "clip_dir", None)
    if plan_path is None:
        raise RuntimeError("from_plan needs a clip (run through tools/clip.py)")
    plan = json.loads((plan_path / "shotplan.json").read_text(encoding="utf-8"))
    entry = next((c for c in plan.get("cast", []) if c.get("id") == cast_id), None)
    if entry is None:
        raise KeyError(f"cast id {cast_id!r} is not in shotplan.json (has {[c.get('id') for c in plan.get('cast', [])]})")
    spec = dict(entry.get("spec") or {})
    spec.update(overrides)
    return cast(cast_id, at=at, facing=facing, **spec)
