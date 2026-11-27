"""anchors - named grip points on fixtures, and the actor's way to them.

    handle = furnish.anchor(doors, "handle_R_in")            # a named place ON a fixture, authored with c.anchor(name, at, normal=...)
    maya.walk(t, to=handle.stand())                          # the floor point in front of it, on the side the hand can reach from
    maya.interact(handle, hit=shot.t("held"), kind="hold_door", hold_until=t_end)

Why it exists: shots used to type leaf-local coordinates for a handle or a button, and nothing checked the result. A hand went through a
door stile, a card was tapped 73 cm from the reader. An AnchorRef is the measured point on the fixture's own surface (it follows the
part it rides on, so a swinging leaf carries its handle), and interact() puts the palm on it only when the actor is where a person
could: on the surface's side, within reach, facing it. The arm is solved with the elbow where the fixture is not (five elbow
positions are tried against the fixture's meshes). check_walk() is the other half: a walk through a door leaf or a gate flap that is
not open wide enough is written down (shot.passages) and reported by physical.sweep.

An interact failure is an exception with a sentence that names the actor, the anchor and the measured value; run_shot.py prints it and the
build fails (exit 3). Nothing here runs for a shot that uses no anchors, except the walk check (it only looks at parts tagged
ob["sk_barrier"]).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import core, record

REACH_MIN = 0.28            # a palm nearer than this (horizontally, from the shoulder) folds the arm into the chest
REACH_MAX = 0.90            # ... farther than this fraction of the arm's length is a stretch the arm cannot hold
FACING_MAX = 35.0           # degrees: more than this away from the anchor and the actor turns first
SIDE_MIN = 0.05             # metres on the anchor's side of its surface the actor must stand
SETTLE = 0.45               # seconds after a walk ends before a hand can land: the blend out sways the stage ~10 cm for about 0.4 s
IDLE_MARGIN = 6             # frames after an interaction in which the idle clip stays off the spine and the acting arm
TORSO_RADIUS = 0.22         # a walking body (arms swinging) needs this much clear of a barrier, metres
TORSO_ZS = (0.28, 0.50, 0.72, 0.95, 1.18, 1.40, 1.62)
TORSO_Z = (0.25, 1.65)
UPPER_R, FORE_R = 0.042, 0.035       # arm radii for the obstacle test, metres
TRACK_STEP = 0.10          # seconds between the keys that follow a moving anchor (a leaf swinging 40 degrees in half a second needs this many)
WRIST_MAX = 75.0            # degrees a wrist bends back
CLEAR_PEN = 0.01            # a pose that sinks less than this into the fixture is clear


class AnchorError(ValueError):
    """Base of the errors here: a sentence with the actor, the anchor and the measured value."""


class InteractionError(AnchorError):
    """An actor cannot do what the shot asks at an anchor: wrong side, out of reach, or the arm would pass through the fixture."""


# ----------------------------------------------------------------------------------------------- the reference
@dataclass
class EvaluatedAnchor:
    """An anchor at one frame, in world space."""
    piece: Any
    name: str
    label: str
    part: str | None
    point: Vector            # the surface point the palm goes to (clearance is added by interact)
    normal: Vector           # the way the surface faces: where the actor stands
    axis: Vector | None      # the long direction of what is gripped
    stand_pos: Vector        # the floor point to stand on (z = 0)
    hand: str
    grip: str
    clearance: float


def _part_of(piece, name: str):
    for o in piece.children_recursive:
        if o.get("sk_part") == name:
            return o
    return None


def _specs_of(piece) -> dict:
    raw = piece.get("sk_anchor_specs")
    return json.loads(raw) if raw else {}


class AnchorRef:
    """A named grip point on a fixture piece (furnish.anchor(piece, name)). `.eval(frame)` is its world pose at a frame (it rides on its part,
    so a swinging leaf carries its handle), `.point()` the world point now (what core.point_of and the physical checks read), `.stand()` the
    floor point in front of it."""

    def __init__(self, piece, name: str):
        specs = _specs_of(piece)
        if name not in specs:
            have = ", ".join(sorted(specs)) or "none: author them in the piece with c.anchor(name, at, normal=...)"
            raise KeyError(f"{piece.name} has no grip point '{name}'. It has: {have}")
        self.piece, self.anchor_name, self.name = piece, name, f"{piece.name}.{name}"
        self.spec = specs[name]
        self.part_ob = None
        if self.spec.get("part"):
            self.part_ob = _part_of(piece, self.spec["part"])
            if self.part_ob is None:
                raise KeyError(f"{piece.name}: grip point '{name}' rides on part '{self.spec['part']}', which the piece does not have")

    def __repr__(self):
        return f"<AnchorRef {self.name}>"

    @property
    def children_recursive(self):
        """The part this anchor rides on and what hangs on it: the physical checks do not call the hand's own door an obstacle."""
        return [self.part_ob, *self.part_ob.children_recursive] if self.part_ob is not None else []

    def eval(self, frame: int | None = None) -> EvaluatedAnchor:
        if frame is not None:
            dg = core.at_frame(int(frame))
        else:
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
        sp = self.spec
        root_mw = self.piece.evaluated_get(dg).matrix_world
        mw = self.part_ob.evaluated_get(dg).matrix_world if self.part_ob is not None else root_mw
        rot = mw.to_3x3().normalized()
        point = mw @ Vector(sp["point"])
        normal = (rot @ Vector(sp["normal"])).normalized()
        axis = (rot @ Vector(sp["axis"])).normalized() if sp.get("axis") is not None else None
        if sp.get("stand_at") is not None:
            st = root_mw @ Vector(sp["stand_at"])
        else:
            n_xy = Vector((normal.x, normal.y, 0.0))
            n_xy = n_xy.normalized() if n_xy.length > 1e-4 else Vector((0.0, -1.0, 0.0))
            st = point + n_xy * float(sp.get("stand_dist", 0.38))
        return EvaluatedAnchor(self.piece, self.anchor_name, self.name, sp.get("part"), point, normal, axis, Vector((st.x, st.y, 0.0)),
                               str(sp.get("hand", "auto")), str(sp.get("grip", "open")), float(sp.get("clearance", 0.015)))

    def point(self, frame: int | None = None) -> Vector:
        """The world point (core.point_of calls this with no frame: the frame the scene is at)."""
        return self.eval(frame).point

    def stand(self, frame: int | None = 1) -> tuple:
        """(x, y) on the floor in front of the anchor: where an actor stands to use it (walk to this, then interact)."""
        p = self.eval(frame).stand_pos
        return (p.x, p.y)


# ----------------------------------------------------------------------------------------------- meshes, cached per shot
_CACHE: dict = {"shot": None, "bvh": {}}


def _local_meshes(root) -> list:
    """[(mesh object, BVHTree in its own space)] for every visible mesh of `root` and what hangs on it. Built once per shot: a fixture's
    geometry does not change, only the matrices that carry it."""
    shot = core.current()
    if _CACHE["shot"] is not shot:
        _CACHE["shot"], _CACHE["bvh"] = shot, {}
    key = root.name
    if key in _CACHE["bvh"]:
        return _CACHE["bvh"][key]
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in [root, *root.children_recursive]:
        if o.type != "MESH" or o.hide_render:
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        if me is None or not me.vertices or not me.polygons:
            if me is not None:
                ev.to_mesh_clear()
            continue
        me.calc_loop_triangles()
        verts = [v.co.copy() for v in me.vertices]
        tris = [tuple(t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
        if tris:
            out.append((o, BVHTree.FromPolygons(verts, tris)))
    _CACHE["bvh"][key] = out
    return out


def _penetration(p0: Vector, p1: Vector, radius: float, meshes: list, dg, skip_at: Vector | None = None, skip_r: float = 0.0, n: int = 8):
    """Deepest a capsule (p0 to p1, radius) sits in the meshes, metres, and the name of the mesh. Samples near `skip_at` are the touch itself."""
    worst, name = 0.0, None
    mats = [(o, bvh, o.evaluated_get(dg).matrix_world) for o, bvh in meshes]
    for i in range(n):
        pt = p0.lerp(p1, i / max(1, n - 1))
        if skip_at is not None and (pt - skip_at).length < skip_r:
            continue
        for o, bvh, mw in mats:
            loc, _nrm, _idx, _d = bvh.find_nearest(mw.inverted_safe() @ pt)
            if loc is None:
                continue
            pen = radius - ((mw @ loc) - pt).length
            if pen > worst:
                worst, name = pen, o.name
    return worst, name


# ----------------------------------------------------------------------------------------------- where the actor is
def _xy(actor, f: int) -> Vector:
    p = actor.stage.evaluated_get(core.at_frame(f)).matrix_world.translation
    return Vector((p.x, p.y))


def _fwd(actor, f: int) -> Vector:
    from . import aj_clips
    y = aj_clips._yaw(actor, f)
    return Vector((math.sin(y), -math.cos(y)))


def _angle_to(actor, f: int, point: Vector) -> float:
    to = Vector((point.x, point.y)) - _xy(actor, f)
    if to.length < 1e-4:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, _fwd(actor, f).dot(to.normalized())))))


def _shoulder(actor, side: str, f: int) -> Vector:
    return actor.J[f"sh.{side}"].evaluated_get(core.at_frame(f)).matrix_world.translation.copy()


def _pick_hand(actor, ev: EvaluatedAnchor, f: int) -> str:
    """The hand an anchor names, or for "auto" the one on the side of the anchor when the actor faces the surface."""
    if ev.hand in ("L", "R"):
        return ev.hand
    n = Vector((ev.normal.x, ev.normal.y))
    if n.length < 1e-4:
        return "R"
    y = math.atan2(-n.x, n.y)                                   # facing into the surface
    left = Vector((math.cos(y), math.sin(y)))
    off = (Vector((ev.point.x, ev.point.y)) - _xy(actor, f)).dot(left)
    return "L" if off > 0.05 else "R"


# ----------------------------------------------------------------------------------------------- the obstacle-aware arm solve
def _poles(side: str) -> list:
    s = 1.0 if side == "L" else -1.0
    return [("natural", Vector((s * 0.90, 0.10, -0.45))), ("low", Vector((s * 0.35, 0.20, -1.00))), ("wide", Vector((s * 1.00, 0.00, 0.00))),
            ("high", Vector((s * 0.70, 0.10, 0.70))), ("fwd_low", Vector((s * 0.50, -0.55, -0.70)))]


def solve_arm(actor, side: str, target_w: Vector, want_w: Vector, frame: int, piece, contact_w: Vector, check: bool = True,
              prev_elbow: Vector | None = None):
    """The arm that puts the palm on target_w with the palm facing want_w, with the elbow wherever the fixture is not.
    Five elbow positions are solved (the kit's own two-bone solve, one pole each) and the upper arm and forearm are tested against the
    fixture's meshes; the clear one nearest the previous elbow wins, so a held arm does not flip. The forearm is not tested within 5.5 cm
    of the contact (that is the touch). Returns (dirs, want_local, elbow_world, penetration_m, mesh_name)."""
    dg = core.at_frame(int(frame))
    Mt = actor.J["torso"].evaluated_get(dg).matrix_world.copy()
    inv = Mt.inverted()
    target_l = inv @ target_w
    want_l = (inv.to_3x3() @ want_w).normalized()
    meshes = _local_meshes(piece) if (check and piece is not None) else []
    if prev_elbow is None:
        prev_elbow = actor.J[f"el.{side}"].evaluated_get(dg).matrix_world.translation.copy()
    L1, L2 = actor.b["arm1"], actor.b["arm2"]
    cands = []
    was = actor._want[side]
    try:
        for pname, pole in _poles(side):
            actor._want[side] = want_l
            u, w = actor._solve(side, target_l, pole)
            S = actor._shoulder(side, u)
            E, T = S + u * L1, S + u * L1 + w * L2
            Ew, Sw, Tw = Mt @ E, Mt @ S, Mt @ T
            pen_u, m_u = _penetration(Sw, Ew, UPPER_R, meshes, dg, None, 0.0, 7) if meshes else (0.0, None)
            pen_f, m_f = _penetration(Ew, Tw, FORE_R, meshes, dg, contact_w, 0.055, 8) if meshes else (0.0, None)
            cands.append((max(pen_u, pen_f), (Ew - prev_elbow).length, pname, (u, w), Ew, m_u if pen_u >= pen_f else m_f))
    finally:
        actor._want[side] = was
    clear = [c for c in cands if c[0] < CLEAR_PEN]
    pen, _d, _n, dirs, Ew, mesh = min(clear, key=lambda c: (round(c[0], 3), c[1])) if clear else min(cands, key=lambda c: c[0])
    return dirs, want_l, Ew, pen, mesh


def _put_arm(actor, side: str, dirs, want_l, t: float, blend: float):
    actor._want[side] = want_l
    try:
        actor._set_arm(side, dirs, t, blend)
    finally:
        actor._want[side] = None


# ----------------------------------------------------------------------------------------------- interact
def interact(actor, ref: AnchorRef, t: float | None = None, hit: float | None = None, kind: str | None = None, side: str | None = None,
             grip: str | None = None, auto_move: bool = False, hold: float = 0.0, hold_until: float | None = None, withdraw: float = 0.0,
             lead: float = 0.35, blend: float = 0.18, speed: float = 2.4, check_obstacles: bool = True, wrist: float | None = None) -> float:
    """ActorAj.interact: see its docstring. Returns the end time."""
    if not isinstance(ref, AnchorRef):
        raise TypeError(f"{actor.id}.interact needs a grip point from furnish.anchor(piece, name), not {type(ref).__name__}")
    t_hit = float(hit) if hit is not None else ((float(t) + lead) if t is not None else lead)
    t_start = max(0.0, float(t) if t is not None else t_hit - lead)
    ev = ref.eval(actor._f(t_start))

    # 1. go there: unless it stands within 15 cm of its place, a walk takes it to the stand point first and gives the walk's settle time
    if auto_move:
        here = _xy(actor, actor._f(t_start))
        if (here - Vector((ev.stand_pos.x, ev.stand_pos.y))).length > 0.15:
            t_arr = actor.walk(t_start, (ev.stand_pos.x, ev.stand_pos.y), speed=speed)
            t_start = t_arr
            t_hit = max(t_hit, t_arr + SETTLE)
    walked = getattr(actor, "_walk_end", None)
    if walked is not None and 0.0 <= t_hit - walked < SETTLE and not auto_move:
        actor.shot.notes.append(f"{actor.id}: {kind or 'interact'} on {ref.name} lands {t_hit - walked:.2f}s after the walk ends; the walk's settle still sways the body "
                                f"for about {SETTLE:.2f}s and moves the hand with it: hit later than {walked + SETTLE:.2f}s")
    f_start, f_hit = actor._f(t_start), actor._f(t_hit)

    # 2. the right side of the surface
    ev = ref.eval(f_start)
    where = _xy(actor, f_start)
    n_xy = Vector((ev.normal.x, ev.normal.y))
    if n_xy.length > 1e-4:
        dot = (where - Vector((ev.point.x, ev.point.y))).dot(n_xy.normalized())
        if dot <= SIDE_MIN:
            raise InteractionError(
                f"{actor.id} cannot use {ev.label} at t={t_start:.2f}s: it stands on the wrong side of it ({dot * 100:.0f} cm along the surface's normal, "
                f"needs more than {SIDE_MIN * 100:.0f}); the anchor is used from ({ev.stand_pos.x:.2f}, {ev.stand_pos.y:.2f}) and its side")

    # 3. face it before anything is measured (the shoulder that matters moves with the turn), then check the reach at the hit
    ev_hit = ref.eval(f_hit)
    if _angle_to(actor, f_hit, ev_hit.point) > FACING_MAX:
        t_turn = max(t_start, t_hit - min(0.18, lead * 0.5))
        actor.heading((ev_hit.point.x, ev_hit.point.y), t_turn, turn=min(0.25, max(0.08, t_turn - t_start)) if t_turn > t_start else 0.18)
    ev_hit = ref.eval(f_hit)
    use = side or _pick_hand(actor, ev_hit, f_hit)
    arm = actor.arm_length()
    lo, hi = REACH_MIN, REACH_MAX * arm
    sh = _shoulder(actor, use, f_hit)
    d_xy = math.hypot(ev_hit.point.x - sh.x, ev_hit.point.y - sh.y)
    d_3d = (ev_hit.point - sh).length
    if d_xy < lo or d_xy > hi or d_3d > 1.05 * arm:
        raise InteractionError(
            f"{actor.id} cannot reach {ev_hit.label} at t={t_hit:.2f}s: the {use} shoulder is {d_xy * 100:.0f} cm from it across the floor ({d_3d * 100:.0f} cm in space); "
            f"the arm manages {lo * 100:.0f} to {hi * 100:.0f} cm (arm {arm * 100:.0f} cm). Stand at ({ev_hit.stand_pos.x:.2f}, {ev_hit.stand_pos.y:.2f}) or pass auto_move=True")
    ang = _angle_to(actor, f_hit, ev_hit.point)
    if ang > FACING_MAX:
        raise InteractionError(f"{actor.id} is turned {ang:.0f} degrees away from {ev_hit.label} at t={t_hit:.2f}s (the most is {FACING_MAX:.0f}); the turn was cut short, give it more time before the hit")

    # 4. written down for the physical checks, then the arm: pre-contact 10 cm out, contact at the clearance, palm against the surface
    record.action(actor, kind or "interact", use, ref, t_hit)
    # the hand lies along the surface: an arm reaching straight at a wall would push its fingers into it, so the wrist is bent back by the
    # angle between the arm and the surface (90 degrees when the arm points straight at it, none when it runs along it), up to what a wrist allows
    shape = grip or ev_hit.grip
    if wrist is None and shape in ("grip", "fist"):             # a hand closed round a bar is straight on the wrist
        wrist = 0.0
    if wrist is None:
        to_palm = (ev_hit.point + ev_hit.normal * ev_hit.clearance) - _shoulder(actor, use, f_hit)
        cos = max(-1.0, min(1.0, to_palm.normalized().dot(-ev_hit.normal))) if to_palm.length > 1e-4 else 0.0
        wrist = max(0.0, min(WRIST_MAX, 90.0 - math.degrees(math.acos(cos))))
    actor._wflex[use] = float(wrist)
    pre_w = ev_hit.point + ev_hit.normal * 0.10
    contact_w = ev_hit.point + ev_hit.normal * ev_hit.clearance
    want_w = -ev_hit.normal
    t_pre = max(0.0, t_hit - min(0.14, max(0.08, lead * 0.45)))
    f_pre = actor._f(t_pre)
    elbow = None
    if f_pre < f_hit:
        dirs, want_l, elbow, _pen, _m = solve_arm(actor, use, pre_w, want_w, f_pre, ev_hit.piece, ev_hit.point, check_obstacles)
        _put_arm(actor, use, dirs, want_l, t_pre, min(blend, max(0.08, t_pre - t_start)) if t_pre > t_start else blend)
    dirs, want_l, elbow, pen, mesh = solve_arm(actor, use, contact_w, want_w, f_hit, ev_hit.piece, ev_hit.point, check_obstacles, elbow)
    if check_obstacles and pen >= CLEAR_PEN:
        raise InteractionError(f"{actor.id}'s arm goes through '{mesh}' ({pen * 100:.1f} cm) on all five elbow positions when it reaches {ev_hit.label} at t={t_hit:.2f}s; "
                               f"stand elsewhere or reach with the other hand")
    _put_arm(actor, use, dirs, want_l, t_hit, max(0.06, t_hit - t_pre) if f_pre < f_hit else blend)
    actor._arm[use] = (70.0, 30.0, "fwd")
    if not actor._grips(use):                                   # a hand that holds a card or a bag keeps its grip
        actor.hand(use, shape if shape in ("grip", "pinch", "point", "open", "fist") else "open", t_hit, 0.10)

    # 5. stay on it: an anchor that moves (a leaf being swung) is followed every 0.1 s, one that does not gets a single closing key
    t_end = t_hit
    t_hold = hold_until if hold_until is not None else (t_hit + hold if hold > 0.0 else None)
    if t_hold is not None and t_hold > t_hit + 1e-3:
        f_end = actor._f(t_hold)
        pts = [ref.eval(f).point for f in (f_hit, (f_hit + f_end) // 2, f_end)]
        if max((p - pts[0]).length for p in pts) < 0.005:
            _put_arm(actor, use, dirs, want_l, t_hold, min(0.16, t_hold - t_hit))
        else:
            tk = t_hit + TRACK_STEP
            while tk < t_hold - 1e-3:
                elbow = _track(actor, use, ref, tk, TRACK_STEP, elbow, check_obstacles)
                tk += TRACK_STEP
            _track(actor, use, ref, t_hold, min(TRACK_STEP, t_hold - t_hit), elbow, check_obstacles)
        t_end = t_hold
    if withdraw > 0.0:                                          # the hand comes off the surface, ten cm out
        t_wd = t_end + withdraw
        fw = actor._f(t_wd)
        ew = ref.eval(fw)
        dw, ww, _e, _p, _m = solve_arm(actor, use, ew.point + ew.normal * 0.10, -ew.normal, fw, ew.piece, ew.point, False)
        _put_arm(actor, use, dw, ww, t_wd, withdraw)
        t_end = t_wd
    actor._wflex[use] = 0.0                                     # the keys keep the bend; the next arm pose starts straight again
    _busy(actor, use, t_start, t_end)
    return t_end


def _track(actor, side: str, ref: AnchorRef, t: float, blend: float, elbow, check: bool):
    f = actor._f(t)
    e = ref.eval(f)
    dirs, want_l, elbow, pen, mesh = solve_arm(actor, side, e.point + e.normal * e.clearance, -e.normal, f, e.piece, e.point, check, elbow)
    if check and pen >= 1.5 * CLEAR_PEN:
        raise InteractionError(f"{actor.id}'s arm goes through '{mesh}' ({pen * 100:.1f} cm) while it follows {e.label} at t={t:.2f}s")
    _put_arm(actor, side, dirs, want_l, t, blend)
    return elbow


# ----------------------------------------------------------------------------------------------- idle stays off the acting arm and the spine
def _busy(actor, side: str, t0: float, t1: float):
    w = getattr(actor, "_interact_windows", None)
    if w is None:
        w = actor._interact_windows = []
    w.append({"side": side, "f0": actor._f(t0), "f1": actor._f(t1) + IDLE_MARGIN})


def busy(actor, group: str, f: int) -> bool:
    """Is this joint group inside an interaction window at frame f? The idle clip (aj_clips._idle_fill) leaves the spine and the acting arm
    alone then: a weight shift in the spine moves the shoulder and pulls a palm that is on a button 2 cm off it."""
    for w in getattr(actor, "_interact_windows", ()):
        if w["f0"] <= f <= w["f1"] and (group == "spine" or group == f"arm.{w['side']}"):
            return True
    return False


# ----------------------------------------------------------------------------------------------- walks and barriers
def barriers() -> list:
    """Every door leaf, gate flap and lift door in the scene (objects tagged ob["sk_barrier"] by furnish and arch.door)."""
    return [o for o in bpy.data.objects if o.get("sk_barrier") and not o.hide_render]


def check_walk(actor, f0: int, f1: int):
    """Sweep the walking body (a 22 cm cylinder, 0.25 to 1.65 m up) along frames f0..f1 against every barrier at its animated pose. A barrier the
    body meets (it is not open wide enough: its own geometry is in the way on that frame) is written down, once per barrier at its closest
    frame, in shot.passages and shot.notes (record.passage); physical.sweep turns that into a through_closed_leaf item. The walk is still
    animated: a shut leaf on the path is a finding to fix, not a reason to produce nothing."""
    bars = [(b, _local_meshes(b)) for b in barriers()]
    bars = [(b, ms) for b, ms in bars if ms]
    if not bars or f1 <= f0:
        return
    frames = list(range(f0, f1 + 1, 2))
    if frames[-1] != f1:
        frames.append(f1)
    fps = actor.shot.fps
    found: dict = {}
    for f in frames:
        dg = core.at_frame(f)
        pos = actor.stage.evaluated_get(dg).matrix_world.translation
        cx, cy, cz = pos.x, pos.y, pos.z
        for b, ms in bars:
            for o, bvh in ms:
                mw = o.evaluated_get(dg).matrix_world
                ws = [mw @ Vector(c) for c in o.bound_box]
                if (cx + TORSO_RADIUS < min(p.x for p in ws) or cx - TORSO_RADIUS > max(p.x for p in ws) or cy + TORSO_RADIUS < min(p.y for p in ws)
                        or cy - TORSO_RADIUS > max(p.y for p in ws) or cz + TORSO_Z[1] < min(p.z for p in ws) or cz + TORSO_Z[0] > max(p.z for p in ws)):
                    continue
                inv = mw.inverted_safe()
                for z in TORSO_ZS:
                    loc, _n, _i, _d = bvh.find_nearest(inv @ Vector((cx, cy, cz + z)))
                    if loc is None:
                        continue
                    hit = mw @ loc
                    d = math.hypot(hit.x - cx, hit.y - cy)
                    if cz + TORSO_Z[0] <= hit.z <= cz + TORSO_Z[1] and d < TORSO_RADIUS:
                        deg = round(math.degrees(b.evaluated_get(dg).rotation_euler.z), 1) + 0.0
                        if b.name not in found or d < found[b.name][2]:
                            found[b.name] = (f, deg, d)
    for name, (f, deg, d) in found.items():
        record.passage(actor, name, f, deg, d * 100.0)
        actor.shot.notes.append(f"{actor.id} walks through '{name}' at {(f - 1) / fps:.2f}s: it is at {deg:.1f} degrees and the body passes {d * 100:.0f} cm from it "
                                f"(a body needs {TORSO_RADIUS * 100:.0f} cm); open it before then or walk round it")
