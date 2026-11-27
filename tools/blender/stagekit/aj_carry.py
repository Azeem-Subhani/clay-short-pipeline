"""aj_carry - a level carry for an Aj actor: the thing stays upright in front of the chest, whatever the body does under it.

    a.carry(tray, "R", t0=0.0)          # in the shot file; the arm and the prop are solved at the end of the build

Why it exists: an arm posed with arm()/reach() is keyed in the torso's own frame, and a run clip pitches and twists the spine under it, so
a tray held that way swings out to the side and behind the shoulder. The carry is therefore solved late, in _finalize, after the clips
have baked the spine: on every frame the tray's place is worked out in the actor's horizontal heading frame (chest + forward + sideways +
height), the arm is solved to put the palm under it, the wrist is levelled to the world, and the prop is seated on the palm and keyed
upright. Nothing here runs for an actor that never calls carry().
"""
from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Quaternion, Vector

from . import aj_clips, aj_rig, core

P = "mixamorig:"
FINGERS = ("Index", "Middle", "Ring", "Pinky")
WRIST_LEVEL_MAX = math.radians(38.0)       # how far the wrist may turn to bring the palm level; the rest is left to the arm


def specs(actor) -> list:
    """The carries this actor was asked for (empty for an actor that never called carry)."""
    return getattr(actor, "_carries", [])


def busy(actor, side: str, f: int) -> bool:
    """Is this arm inside a carry at frame f? (aj_clips.holding asks, so idle and locomotion leave the arm alone.)"""
    return any(c["side"] == side and c["f0"] <= f <= c["f1"] for c in specs(actor))


def tray_hand_angles(side: str) -> dict:
    """An open, slightly cupped hand that supports a flat thing from below: fingers long, thumb tucked low so it does not lift the tray."""
    rad = math.radians
    sgn = 1.0 if side == "R" else -1.0
    sn = "Left" if side == "L" else "Right"
    flex = {"Index": (6, 8, 6), "Middle": (6, 8, 6), "Ring": (8, 10, 6), "Pinky": (10, 12, 8)}
    spread = {"Index": -5, "Middle": -1, "Ring": 3, "Pinky": 7}
    out = {}
    for F in FINGERS:
        for j, a in enumerate(flex[F], 1):
            out[f"{P}{sn}Hand{F}{j}"] = (rad(a), 0.0, rad(spread[F]) * sgn if j == 1 else 0.0)
    th = [rad(v) for v in (-24, 0, -28, 0, 0)]
    out[f"{P}{sn}HandThumb1"] = (th[0], th[1] * sgn, th[2] * sgn)
    out[f"{P}{sn}HandThumb2"] = (-th[3], 0.0, 0.0)
    out[f"{P}{sn}HandThumb3"] = (-th[4], 0.0, 0.0)
    return out


def register(actor, prop, side, t0, t1, height, forward, side_offset, elbow, palm_clearance):
    """Store one carry (called by ActorAj.carry) and make the prop a plain, level hold the bake can move."""
    if side_offset is None:
        side_offset = -0.19 if side == "R" else 0.19
    if t1 is None:
        t1 = float(actor.shot.seconds)
    for o in [prop, *prop.children_recursive]:
        if o.name not in actor.coll.all_objects:
            actor.coll.objects.link(o)
    if prop.name not in actor._held:
        actor.hold(prop, side=side, t=t0, grip=False, turn=False)
    else:                                          # already in the hand: keep it level (position only), whatever the earlier hold did
        cons, tgt, hside, meta = actor._held[prop.name]
        kept = []
        for c in list(cons):
            if c.type == "COPY_ROTATION":
                prop.constraints.remove(c)
            else:
                kept.append(c)
        meta["turn"] = False
        actor._held[prop.name] = (kept, tgt, hside, meta)
    f0 = max(1, actor._f(t0))
    f1 = max(f0, actor._f(t1))
    # the cupped hand is a finger layer like a grip's, so aj_hands.bake closes the fingers under the tray
    actor._grip_layers.append({"side": side, "f0": f0, "f1": f1, "ramp": 2, "angles": tray_hand_angles(side), "prop": prop.name})
    actor._carries.append({"prop": prop, "side": side, "f0": f0, "f1": f1, "height": float(height), "forward": float(forward),
                           "side_offset": float(side_offset), "elbow": elbow, "palm_clearance": float(palm_clearance)})
    return actor


def _root_frame(actor, dg):
    """The actor's horizontal heading: (forward, left, yaw). Model front is -Y, left is +X, up is +Z."""
    rmw = actor.root.evaluated_get(dg).matrix_world
    fwd = rmw.to_3x3() @ Vector((0.0, -1.0, 0.0))
    fwd.z = 0.0
    if fwd.length < 1e-4:
        fwd = Vector((0.0, -1.0, 0.0))
    else:
        fwd.normalize()
    left = Vector((-fwd.y, fwd.x, 0.0))
    return fwd, left, math.atan2(fwd.x, -fwd.y)      # yaw: the Z turn that takes local (0, -1, 0) to fwd


def _quat_series(ob, frames):
    """The joint's rotation as it is keyed now, one quaternion per frame (frames outside a carry keep it)."""
    fcs = {fc.array_index: fc for fc in core.fcurves(ob) if fc.data_path == "rotation_quaternion"}
    out = []
    for f in frames:
        if len(fcs) == 4:
            out.append(Quaternion(tuple(fcs[i].evaluate(f) for i in range(4))).normalized())
        else:
            out.append(ob.rotation_quaternion.copy().normalized())
    return out


def _local_min_z(root):
    """Lowest point of the prop's visible meshes in its own local space (where its underside is)."""
    bpy.context.view_layer.update()
    inv = root.matrix_world.inverted()
    lo, found = 1e9, False
    for o in [root, *root.children_recursive]:
        if o.type != "MESH" or o.hide_render:
            continue
        found = True
        for c in o.bound_box:
            lo = min(lo, (inv @ (o.matrix_world @ Vector(c))).z)
    return lo if found else 0.0


class _only_this_actor:
    """While it is open, the view layer evaluates only this actor's own collection (and the ones above it). A carry steps through every frame
    twice and a frame step re-evaluates everything animated in the scene: in a finished set that is thousands of objects (rain, lights, other
    figures) that the arm does not depend on, and it made the bake cost tens of seconds. The collections are switched back on at the end."""

    def __init__(self, actor):
        self.actor, self.off = actor, []

    def _walk(self, lc, path):
        if lc.collection is self.actor.coll:
            return path + [lc]
        for ch in lc.children:
            found = self._walk(ch, path + [lc])
            if found:
                return found
        return None

    def __enter__(self):
        root = bpy.context.view_layer.layer_collection
        keep = self._walk(root, [])
        if keep is None:                                     # the actor's collection is not in this view layer: leave the scene alone
            return self
        keep_ids = {id(lc.collection) for lc in keep}
        for lc in keep:
            for ch in lc.children:
                if id(ch.collection) not in keep_ids and not ch.exclude:
                    ch.exclude = True
                    self.off.append(ch)
        return self

    def __exit__(self, *exc):
        for lc in self.off:
            lc.exclude = False
        return False


def bake_arms(actor, frames):
    """Pass 1, after the clips have baked the spine and before the hands are baked: solve the carrying arm on every frame so the palm is
    under the tray's place in the heading frame, with the wrist levelled; then the collars again for the new arm."""
    if not specs(actor):
        return
    with _only_this_actor(actor):
        _bake_arms(actor, frames)


def _bake_arms(actor, frames):
    cs = specs(actor)
    sc = bpy.context.scene
    f_min, f_max = frames[0], frames[-1]
    sides = sorted({c["side"] for c in cs})
    series = {jn: _quat_series(actor.J[jn], frames) for side in sides for jn in (f"sh.{side}", f"el.{side}", f"wr.{side}")}
    actor._carry_seat = {}                           # (prop name, frame) -> the heading the prop is turned to, for the seating pass
    for c in cs:
        side, prop = c["side"], c["prop"]
        f0, f1 = max(f_min, c["f0"]), min(f_max, c["f1"])
        s = actor.scale
        clear = c["palm_clearance"] * s
        hinge = actor._hinge[side].copy()
        prev = {f"sh.{side}": None, f"el.{side}": None, f"wr.{side}": None}
        for f in range(f0, f1 + 1):
            sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            fwd, left, yaw = _root_frame(actor, dg)
            chest = actor.chest.ob.evaluated_get(dg).matrix_world.translation.copy()
            tray = chest + fwd * (c["forward"] * s) + left * (c["side_offset"] * s) + Vector((0.0, 0.0, c["height"] * s))
            actor._carry_seat[(prop.name, f)] = yaw
            torso = actor.J["torso"].evaluated_get(dg).matrix_world
            want = (torso.to_3x3().normalized().inverted() @ Vector((0.0, 0.0, 1.0))).normalized()
            target = torso.inverted() @ (tray - Vector((0.0, 0.0, clear)))
            actor._want[side] = want
            actor._hinge[side] = hinge
            u, w = actor._solve(side, target, elbow=c["elbow"])
            q_sh, th, tau, R_hand, hinge = actor._frame(side, u, w, want, hinge)
            actor._want[side] = None
            # the wrist brings the palm the last few degrees to level
            swing = (R_hand @ actor._pn[side]).normalized().rotation_difference(want)
            axis, ang = swing.to_axis_angle()
            if ang > WRIST_LEVEL_MAX:
                swing = Quaternion(axis, WRIST_LEVEL_MAX)
            lvl = (R_hand.transposed() @ swing.to_matrix() @ R_hand).to_quaternion().normalized()
            q_el = (Quaternion((1, 0, 0), th) @ Quaternion((0, 0, 1), 0.6 * tau)).normalized()
            q_wr = (Quaternion((0, 0, 1), 0.4 * tau) @ lvl).normalized()
            for jn, q in ((f"sh.{side}", q_sh), (f"el.{side}", q_el), (f"wr.{side}", q_wr)):
                if prev[jn] is not None and q.dot(prev[jn]) < 0.0:
                    q = -q                           # the shorter way round, so the key does not flip between frames
                prev[jn] = q.copy()
                series[jn][f - f_min] = q
    for jn, vals in series.items():
        aj_rig._write_dense(actor.J[jn], "rotation_quaternion", frames, vals, 4)
    aj_rig.apply_collars(actor, frames)
    aj_clips.after_collars(actor, frames)


def seat_props(actor, frames):
    """Pass 2, after the hands are baked: put each carried prop on the palm and fingers of the baked hand, 1.5 mm clear of the skin, at the
    place pass 1 chose, upright, turned with the actor's heading."""
    if not specs(actor):
        return
    with _only_this_actor(actor):
        _seat_props(actor, frames)


def _seat_props(actor, frames):
    cs = specs(actor)
    sc = bpy.context.scene
    f_min, f_max = frames[0], frames[-1]
    s = actor.scale
    for c in cs:
        prop, side = c["prop"], c["side"]
        if prop.name not in actor._held:
            continue
        tgt = actor._held[prop.name][1]
        under = _local_min_z(prop)
        sn = "Left" if side == "L" else "Right"
        prop.rotation_mode = "XYZ"
        frs = list(range(max(f_min, c["f0"]), min(f_max, c["f1"]) + 1))
        locs, rots = [], []
        for f in frs:
            sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            palm = actor.palm[side].evaluated_get(dg).matrix_world.translation.copy()
            rig = actor.rig.evaluated_get(dg)
            amw = rig.matrix_world
            pts, tips = [palm], []
            for fn in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
                for j in (1, 2, 3, 4):
                    pb = rig.pose.bones.get(f"{P}{sn}Hand{fn}{j}")
                    if pb is None:
                        continue
                    pts.append(amw @ pb.head)
                    if j == 4:
                        tips.append(amw @ pb.head)
                    elif j == 3:
                        pts.append(amw @ pb.tail)
            hb = rig.pose.bones.get(f"{P}{sn}Hand")
            wrist_z = (amw @ hb.head).z if hb is not None else palm.z
            top = max(max(p.z for p in pts) + 0.011 * s, wrist_z + 0.022 * s)    # from the bones; the skin below refines it
            if tips:                                 # the tray is centred between palm and fingertips so every finger carries it
                cx = 0.45 * palm.x + 0.55 * sum(p.x for p in tips) / len(tips)
                cy = 0.45 * palm.y + 0.55 * sum(p.y for p in tips) / len(tips)
            else:
                cx, cy = palm.x, palm.y
            body = actor.mesh.evaluated_get(dg)
            me = body.to_mesh()
            co = np.empty(len(me.vertices) * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            body.to_mesh_clear()
            w = co.reshape(-1, 3) @ np.array(body.matrix_world.to_3x3(), dtype=np.float32).T + np.array(body.matrix_world.translation, dtype=np.float32)
            near = w[(w[:, 2] >= palm.z - 0.05) & (w[:, 2] <= palm.z + 0.045) & (np.abs(w[:, 0] - cx) <= 0.105) & (np.abs(w[:, 1] - cy) <= 0.06)]
            if len(near):                            # the highest skin under the tray, found with numpy: a Python loop over the body costs seconds a shot
                top = max(top, float(near[:, 2].max()) + 0.0015)
            wr = actor.J[f"wr.{side}"].evaluated_get(dg).matrix_world
            locs.append(wr.inverted() @ Vector((cx, cy, top - under)))
            rots.append(Vector((0.0, 0.0, actor._carry_seat[(prop.name, f)])))
        aj_rig._write_dense(tgt, "location", frs, locs, 3)
        aj_rig._write_dense(prop, "rotation_euler", frs, rots, 3)
