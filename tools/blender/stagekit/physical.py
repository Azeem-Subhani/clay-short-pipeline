"""stagekit.physical - the physical faults a still cannot show you: hands through doors, props nobody holds, people walking through closed gates.

The checks in review.py measure what a frame looks like (framing, exposure, feet). This module measures what the scene does, with no render:
it steps through the built shot and tests geometry against what the shot code declared (stagekit.record: shot.holds, shot.interactions,
shot.wears). `sweep(shot)` is called by review.stills next to the camera path analysis and returns findings in the same item shape.

    interpenetration  through_closed_leaf  rain_under_cover               bodies and props inside each other, bodies through a door leaf or
                                                                          gate flap that is shut, rain falling through a canopy
    grip_open  grip_impaled  prop_backwards                               a held prop with no finger on it, cutting through the hand, turned wrong
    loose_attachment  attachment_in_body                                  a prop fixed to a body by hand that nothing carries, or sunk into it
    carry_tilt  carry_behind  carry_flung                                 a prop that should ride upright in front of the chest and does not
    not_facing_target  reach_miss  reach_short  arm_through_obstacle      a reach, press or wave that does not face, touch or clear its target
    floating_prop                                                         a loose prop in the air with no hand on it
    untargeted_action                                                     an action that needs a target was called without one: it cannot be checked

Findings are merged across frames: one item per (code, actor, object) with its frame range and its worst frame. A fault the camera never
sees (outside the frame at the worst on-screen moment) is a warning, not a block: the viewer cannot see it. Numbers live in
style/style.json under "physical"; the values below are the defaults when that key is missing.
"""
from __future__ import annotations

import math
import time
from collections import Counter, defaultdict

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import core

DEFAULTS = {
    "step": 6,                                   # frames between sweep frames for everything except passage (which looks at every frame)
    "interp": {"warn_cm": 2.5, "block_cm": 5.0, "hand_cm": 2.5, "hand_radius_m": 0.13, "pierce_cm": 0.8},
    "passage": {"torso_radius_m": 0.13, "block_open_deg": 45.0, "warn_open_deg": 60.0, "block_depth_cm": 5.0},
    "rain": {"warn_pct": 1.0, "block_pct": 5.0, "max_streaks": 400, "max_distance_m": 16.0},
    "grip": {"tip_m": 0.015, "palm_m": 0.025, "block_mm": 14.0, "warn_mm": 8.0, "backwards_dot": -0.25, "settle_s": 0.3},
    "attach": {"hand_m": 0.04, "shoulder_m": 0.07, "block_mm": 22.0, "warn_mm": 12.0},
    "carry": {"tilt_deg": 22.0, "behind_m": -0.05, "flung_m": 0.42},
    "reach": {"facing_block_deg": 75.0, "facing_warn_deg": 55.0, "head_warn_deg": 60.0, "miss_block_cm": 14.0, "miss_warn_cm": 8.0},
    "float": {"gap_cm": 4.0, "hand_cm": 5.0, "grace_frames": 3},
}

FLOOR_WORDS = ("floor", "ground", "pavement", "road", "carpet", "apron", "curb", "kerb", "sidewalk", "puddle", "mat", "rug", "crosswalk", "marking", "asphalt")
FLOOR_TYPES = {"floor", "floor_detail", "mat", "rug", "puddle", "carpet", "road", "pavement", "ground"}
SEAT_WORDS = ("chair", "bench", "sofa", "stool")
SEAT_TYPES = {"chair_office", "chair", "bench", "sofa", "stool", "seat"}
SHELL_WORDS = ("door", "leaf", "wall", "glass", "gate", "stile", "flap")        # thin architectural shells, where passing through the sheet is the fault
COVER_WORDS = ("canopy", "awning", "ceiling", "roof", "overhang", "eave")      # overhead cover that rain must not fall through
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")
P = "mixamorig:"
NO_CHECK = ("phone", "card", "printout")                                       # thin or hand-sized things that are not carried upright

CODES = ("interpenetration", "through_closed_leaf", "rain_under_cover", "grip_open", "grip_impaled", "prop_backwards", "loose_attachment",
         "attachment_in_body", "carry_tilt", "carry_behind", "carry_flung", "not_facing_target", "reach_miss", "reach_short",
         "arm_through_obstacle", "floating_prop", "untargeted_action")


def config() -> dict:
    """The thresholds: the defaults, with whatever style.json's "physical" key overrides one level down."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in (core.STYLE.get("physical") or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


# ----------------------------------------------------------------------------- merging
def merge_flags(flags: list[dict]) -> list[dict]:
    """One merged record per (code, actor, object) from per-frame flags. A flag is {code, actor, object, frame, level, value, unit, extra}.
    The record keeps the frame range, the worst frame (largest value; frames whose flag is a block win over warnings so an off-screen
    frame never hides the on-screen one), and the highest level seen."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for fl in flags:
        groups[(fl["code"], fl.get("actor") or "", fl.get("object") or "")].append(fl)
    out = []
    for (code, actor, obj), lst in groups.items():
        top = "block" if any(x["level"] == "block" for x in lst) else "warn"
        pool = [x for x in lst if x["level"] == top]
        worst = max(pool, key=lambda x: x["value"])
        frames = [x["frame"] for x in lst]
        out.append({"code": code, "actor": actor, "object": obj, "level": top, "frame": worst["frame"], "frames": [min(frames), max(frames)],
                    "value": worst["value"], "unit": worst.get("unit", ""), "extra": worst.get("extra") or {}, "count": len(lst)})
    return sorted(out, key=lambda r: (r["level"] != "block", r["frames"][0], r["code"]))


def _span(frames) -> str:
    return f"frame {frames[0]}" if frames[0] == frames[1] else f"frames {frames[0]}-{frames[1]}"


def _text(r: dict) -> str:
    """One plain sentence: what is wrong, the number, and the kit call that fixes it."""
    c, a, o, v, ex = r["code"], r["actor"], r["object"], r["value"], r["extra"]
    sp = _span(r["frames"])
    if c == "interpenetration":
        sub = ex.get("sub", "")
        who = {"actor_set": f"{a} is inside {o}", "actor_actor": f"{a} is inside {o}", "actor_own_prop": f"{a}'s body is inside the {o} they carry",
               "actor_other_prop": f"{a} is inside {o}", "prop_set": f"{a}'s {ex.get('prop', '')} is inside {o}"}.get(sub, f"{a} and {o} overlap")
        fix = {"actor_own_prop": "hold it further out with hold(prop, side, offset=...) or wear it on the body so it hangs outside the torso",
               "prop_set": "release or place it clear of the set piece",
               "actor_actor": "move one of them on their mark"}.get(sub, "move the figure or the set piece so they only touch at the hands and feet")
        return f"{who} by {v:.1f} cm ({sp}): {fix}."
    if c == "through_closed_leaf":
        return (f"{a} walks through {o} while it is open only {v:.0f} degrees ({sp}): open it before the body reaches it "
                f"(actor.do(\"open_door\", ..., door=leaf) or a core.move of the leaf) or send the figure round it.")
    if c == "rain_under_cover":
        return (f"{v:.1f}% of the rain the camera sees falls through {o} ({sp}): call fx.rain(...) after the architecture exists with cover=\"auto\", "
                "and keep the emitter's area off the sheltered ground.")
    if c == "grip_open":
        return (f"{a} holds {o} with no finger on it: the nearest fingertip is {v:.1f} cm away ({sp}): hold it with the grip solver "
                "(actor.hold(prop, side, grip=True)) and check the prop is within reach of the hand when the hold starts.")
    if c == "grip_impaled":
        return f"{o} cuts {v:.0f} mm into {a}'s hand or forearm ({sp}): shift actor.hold(prop, side, offset=...) so the hand wraps the prop instead of passing through it."
    if c == "prop_backwards":
        return (f"The screen of {o} faces {v:.0f} degrees away from {a}'s head ({sp}): turn the phone before it is held "
                "(actor.hold(prop, side, turn=True) after rotating the prop) so the screen is toward the face.")
    if c == "loose_attachment":
        return (f"{o} is fixed to {a}'s body by hand but no hand or shoulder is within reach of it: nearest hand {v:.0f} cm ({sp}): "
                "hang it through the kit (actor.wear / hold with a strap anchor) so a hand or shoulder carries it.")
    if c == "attachment_in_body":
        return f"{o} sinks {v:.0f} mm into {a}'s body ({sp}): move its parent point out, or hold it with actor.hold(prop, side, offset=...) instead of parenting it to the torso."
    if c == "carry_tilt":
        return f"{o} tips {v:.0f} degrees off upright in {a}'s hand ({sp}): hold it with turn=False so it stays level, or release it onto a surface."
    if c == "carry_behind":
        return f"{o} rides {v:.0f} cm behind {a}'s chest ({sp}): hold it in front (actor.hold(prop, side, front=True)) instead of letting the arm swing it back."
    if c == "carry_flung":
        return f"{o} is flung {v:.0f} cm out to the side of {a} ({sp}): the arm swing carries it away from the body; hold it nearer with offset=... or in both hands."
    if c == "not_facing_target":
        return f"{a} reaches for {o} while their body faces {v:.0f} degrees away from it ({sp}): turn them first (actor.face(target) or actor.turn_to) before the reach."
    if c == "reach_miss":
        return f"{a}'s hand ends {v:.0f} cm from {o} when it should touch it ({sp}): move the figure within reach on its mark, or give the reach a target that is where the hand lands."
    if c == "reach_short":
        return f"{a}'s hand stops {v:.0f} cm short of {o} ({sp}): close the gap with actor.reach(side, target, t) or step in."
    if c == "arm_through_obstacle":
        return f"{a}'s forearm passes through {o} on the way to the target ({sp}): reach round it (elbow=\"up\" or \"down\") or move the figure."
    if c == "floating_prop":
        return f"{o} hangs {v:.0f} cm in the air with no hand on it ({sp}): rest it on its support, or hold it with actor.hold(prop, side) while it moves."
    if c == "untargeted_action":
        return f"{a} does \"{o}\" with no target ({sp}), so its reach cannot be checked: pass target=... to actor.do."
    return f"{c}: {a} {o} ({sp})"


# ----------------------------------------------------------------------------- scene helpers
_CATS: dict | None = None                        # names of the objects in the FX/RIG/LIGHTS and CAST collections, built once per sweep (users_collection is slow)


def _load_cats():
    global _CATS
    fx, cast = set(), set()
    for c in bpy.data.collections:
        if c.name in ("FX", "RIG", "LIGHTS"):
            fx.update(o.name for o in c.objects)
        if c.name == "CAST" or c.name.startswith("CAST_"):
            cast.update(o.name for o in c.objects)
    _CATS = {"fx": fx, "cast": cast}


def _is_fx_or_rig(ob) -> bool:
    if _CATS is not None:
        return ob.name in _CATS["fx"]
    return any(c.name in ("FX", "RIG", "LIGHTS") for c in ob.users_collection)


def _is_cast_obj(ob) -> bool:
    if _CATS is not None:
        return ob.name in _CATS["cast"]
    return any(c.name == "CAST" or c.name.startswith("CAST_") for c in ob.users_collection)


def _chain_has(ob, words, types=None) -> bool:
    cur, hops = ob, 0
    while cur is not None and hops < 16:
        if types and str(cur.get("sk_type", "")).lower() in types:
            return True
        nm = cur.name.lower()
        if any(w in nm for w in words):
            return True
        cur, hops = cur.parent, hops + 1
    return False


def _is_floor(ob) -> bool:
    return _chain_has(ob, FLOOR_WORDS, FLOOR_TYPES)


def _is_seat(ob) -> bool:
    return _chain_has(ob, SEAT_WORDS, SEAT_TYPES)


def _is_shell(ob) -> bool:
    return _chain_has(ob, SHELL_WORDS)


def logical_root_name(ob, actor_names=()) -> str:
    """A readable name for what a mesh belongs to: the door leaf or gate flap it is part of, or the prop or set piece above it. Stops at the actor."""
    def is_actor(o) -> bool:
        if o.type == "ARMATURE" or o.name.endswith("_lift"):
            return True
        return any(o.name == an or o.name.startswith(f"{an}.") for an in actor_names)

    cur = ob
    while cur is not None:
        part = str(cur.get("sk_part", ""))
        if part.startswith("leaf") or part.startswith("flap"):
            if cur.parent is not None and ("bag" in cur.parent.name.lower() or "prop" in cur.parent.name.lower()):
                return cur.parent.name.split(".")[0]
            return cur.name
        if ".leaf" in cur.name.lower():
            return cur.parent.name if cur.parent is not None and ".leaf" in cur.parent.name.lower() else cur.name
        if cur.parent is None or is_actor(cur.parent):
            base = cur.name.split(".")[0]
            return base if any(k in base.lower() for k in ("messenger_bag", "cup_carrier", "desk_box", "keycard")) else cur.name
        if cur.get("sk_type"):
            return cur.name
        cur = cur.parent
    return ob.name


def _in_view(shot, pt) -> bool:
    cam = getattr(shot, "camera", None)
    if cam is None:
        return True
    x, y, z = cam.project(Vector(pt))
    return bool(-0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 and z > 0.0)


def _hidden(ob, dg) -> bool:
    try:
        return bool(ob.evaluated_get(dg).hide_render)
    except (ReferenceError, RuntimeError):
        return True


def _mesh_children(root, dg) -> list:
    return [o for o in [root, *root.children_recursive] if o.type == "MESH" and not _hidden(o, dg) and len(o.data.polygons) > 0]


# ----------------------------------------------------------------------------- evaluated meshes
class EvalMesh:
    """An evaluated mesh at one frame: world vertices and triangles (numpy), a local BVH, and the world box."""
    __slots__ = ("name", "mw", "inv_mw", "verts_w", "tris", "aabb", "co", "_bvh", "_tb")

    def __init__(self, name, mw, inv_mw, verts_w, tris, aabb, co):
        self.name, self.mw, self.inv_mw, self.verts_w, self.tris, self.aabb, self.co = name, mw, inv_mw, verts_w, tris, aabb, co
        self._bvh = None
        self._tb = None

    @property
    def local_bvh(self):
        """The BVH in the mesh's own space, built on first use: most pairs never get as far as needing it."""
        if self._bvh is None:
            self._bvh = BVHTree.FromPolygons(self.co.tolist(), self.tris.tolist())
        return self._bvh

    def tri_bounds(self):
        """(low, high) corners of every triangle's box, worked out once: a set mesh is tested against many figures and frames."""
        if self._tb is None:
            tv = self.verts_w[self.tris]
            self._tb = (tv.min(axis=1), tv.max(axis=1))
        return self._tb


def build_eval_mesh(ob, dg) -> EvalMesh | None:
    ev = ob.evaluated_get(dg)
    if ev.hide_render:
        return None
    try:
        me = ev.to_mesh()
    except RuntimeError:
        return None
    if me is None or len(me.vertices) == 0 or len(me.polygons) == 0:
        ev.to_mesh_clear()
        return None
    me.calc_loop_triangles()
    n_v, n_t = len(me.vertices), len(me.loop_triangles)
    if n_t == 0:
        ev.to_mesh_clear()
        return None
    co = np.empty(n_v * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    tris = np.empty(n_t * 3, dtype=np.int32)
    me.loop_triangles.foreach_get("vertices", tris)
    mw = ev.matrix_world.copy()
    m = np.array(mw, dtype=np.float32)
    verts_w = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    lo, hi = verts_w.min(axis=0), verts_w.max(axis=0)
    ev.to_mesh_clear()
    return EvalMesh(ob.name, mw, mw.inverted(), verts_w, tris.reshape(-1, 3), tuple(float(x) for x in (*lo, *hi)), co.reshape(-1, 3))


def _aabb_overlap(a, b, pad: float = 0.0) -> bool:
    return (a[0] - pad <= b[3] and a[3] + pad >= b[0] and a[1] - pad <= b[4] and a[4] + pad >= b[1] and a[2] - pad <= b[5] and a[5] + pad >= b[2])


def _aabb_of(ob) -> tuple:
    mw = ob.matrix_world
    pts = [mw @ Vector(c) for c in ob.bound_box]
    return (min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts), max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))


def _cropped_bvh(em: EvalMesh, box6, pad: float = 0.015):
    """A small world BVH of only the triangles of `em` whose box meets box6: what two meshes can actually touch."""
    lo, hi = em.tri_bounds()
    keep = ((hi[:, 0] >= box6[0] - pad) & (lo[:, 0] <= box6[3] + pad) & (hi[:, 1] >= box6[1] - pad) & (lo[:, 1] <= box6[4] + pad)
            & (hi[:, 2] >= box6[2] - pad) & (lo[:, 2] <= box6[5] + pad))
    sel = np.nonzero(keep)[0]
    if len(sel) == 0:
        return None, None, None
    sub = em.tris[sel]
    uniq, inv = np.unique(sub, return_inverse=True)
    verts = em.verts_w[uniq]
    polys = inv.reshape(-1, 3).tolist()
    return BVHTree.FromPolygons([tuple(r) for r in verts.tolist()], polys), verts, polys


def _ray_parity(bvh: BVHTree, origin: Vector, direction: Vector, max_steps: int = 16) -> int:
    hits, pos = 0, origin
    for _ in range(max_steps):
        loc, _n, _i, _d = bvh.ray_cast(pos, direction, 50.0)
        if loc is None:
            break
        hits += 1
        pos = loc + direction * 1e-4
    return hits


def _depth_of_points_in(pts_w: np.ndarray, target: EvalMesh, hands=None):
    """(deepest non-hand cm, point, deepest hand cm, point): how far world points sit inside the closed mesh `target`."""
    if len(pts_w) == 0:
        return 0.0, None, 0.0, None
    if len(pts_w) > 350:
        pts_w = pts_w[::max(1, len(pts_w) // 350)]
    inv, mw, bvh = target.inv_mw, target.mw, target.local_bvh
    up_local = (inv.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    best_n, pt_n, best_h, pt_h = 0.0, None, 0.0, None
    for row in pts_w:
        vw = Vector((float(row[0]), float(row[1]), float(row[2])))
        vl = inv @ vw
        loc_l, norm_l, _i, dist_l = bvh.find_nearest(vl)
        if loc_l is None or dist_l is None or (vl - loc_l).dot(norm_l) >= -1e-4:
            continue
        d_m = (vw - mw @ loc_l).length
        if d_m < 0.004 or _ray_parity(bvh, vl, up_local) % 2 != 1:
            continue
        d_cm = d_m * 100.0
        if hands and any((vw - hp).length <= rad for hp, rad in hands):
            if d_cm > best_h:
                best_h, pt_h = d_cm, vw
        elif d_cm > best_n:
            best_n, pt_n = d_cm, vw
    return best_n, pt_n, best_h, pt_h


def penetration_depth_cm(em_a: EvalMesh, em_b: EvalMesh, hands=None, hand_cm: float = 2.5, shell: bool = False, pierce_min_cm: float = 0.8) -> dict | None:
    """How deep two evaluated meshes sit inside each other, in cm, or None when they do not overlap. Depth is the deepest vertex of one
    inside the other. Where `em_b` is a thin shell (a door leaf, a wall, a pane: shell=True) the vertices of A on both sides of the sheet
    count too, because a hand through a 4 cm stile has no vertex inside it. Points of A within `hands` (centre, radius) pressing less than
    hand_cm into B are a grip, not a fault."""
    if not _aabb_overlap(em_a.aabb, em_b.aabb):
        return None
    inter = (max(em_a.aabb[0], em_b.aabb[0]), max(em_a.aabb[1], em_b.aabb[1]), max(em_a.aabb[2], em_b.aabb[2]),
             min(em_a.aabb[3], em_b.aabb[3]), min(em_a.aabb[4], em_b.aabb[4]), min(em_a.aabb[5], em_b.aabb[5]))
    bvh_a, _va, pa = _cropped_bvh(em_a, inter)
    if bvh_a is None:
        return None
    bvh_b, vb_sub, pb = _cropped_bvh(em_b, inter)
    if bvh_b is None:
        return None
    pairs = bvh_a.overlap(bvh_b)
    if not pairs:
        return None
    tris_b = {p[1] for p in pairs}
    ov_a = np.array([_va[vi] for ti in {p[0] for p in pairs} for vi in pa[ti]])
    ov_center = Vector(tuple(ov_a.mean(axis=0).tolist()))

    def in_box(v):
        return ((v[:, 0] >= inter[0]) & (v[:, 0] <= inter[3]) & (v[:, 1] >= inter[1]) & (v[:, 1] <= inter[4]) & (v[:, 2] >= inter[2]) & (v[:, 2] <= inter[5]))

    va, vb = em_a.verts_w, em_b.verts_w
    nh_ab, pt_nh_ab, h_ab, pt_h_ab = _depth_of_points_in(va[in_box(va)], em_b, hands)
    nh_ba, pt_nh_ba, h_ba, pt_h_ba = _depth_of_points_in(vb[in_box(vb)], em_a, hands)

    pierce = 0.0
    ext = np.array([em_b.aabb[3] - em_b.aabb[0], em_b.aabb[4] - em_b.aabb[1], em_b.aabb[5] - em_b.aabb[2]])
    if shell and ext.min() < 0.08 and sorted(ext)[1] > 0.12:
        normals = []
        for ti in list(tris_b)[:40]:
            p = pb[ti]
            n = np.cross(vb_sub[p[1]] - vb_sub[p[0]], vb_sub[p[2]] - vb_sub[p[0]])
            ln = np.linalg.norm(n)
            if ln > 1e-8:
                n = n / ln
                normals.append(-n if normals and np.dot(n, normals[0]) < 0 else n)
        if normals:
            nm = np.mean(normals, axis=0)
            ln = np.linalg.norm(nm)
            if ln > 1e-5 and abs(nm[2] / ln) < 0.7:                 # a vertical or tilted sheet, not a tabletop or a ledge
                nm = nm / ln
                centre = vb_sub.mean(axis=0)
                ref = np.array([1.0, 0.0, 0.0]) if abs(nm[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                u = np.cross(nm, ref)
                u /= np.linalg.norm(u)
                w = np.cross(nm, u)
                db = vb_sub - centre
                bu, bw = db @ u, db @ w
                da = va - centre
                au, aw = da @ u, da @ w
                in_fp = ((da * da).sum(axis=1) < 0.09 ** 2) & (au >= bu.min()) & (au <= bu.max()) & (aw >= bw.min()) & (aw <= bw.max())
                if in_fp.any():
                    proj = da[in_fp] @ nm
                    pos, neg = float(proj.max()), float(-proj.min())
                    if pos > 0.008 and neg > 0.008:
                        cand = min(pos, neg) * 100.0
                        near_hand = bool(hands) and any((ov_center - hp).length <= rad for hp, rad in hands)
                        if not (near_hand and cand < hand_cm):
                            pierce = cand
    non_hand = max(nh_ab, nh_ba, pierce)
    hand = max(h_ab, h_ba)
    if hand < hand_cm:
        hand = 0.0
    depth = max(non_hand, hand)
    if depth < pierce_min_cm:
        return None
    pt = next((q for q in (pt_nh_ab, pt_nh_ba, pt_h_ab, pt_h_ba) if q is not None), ov_center)
    return {"depth_cm": round(depth, 2), "at": (float(pt.x), float(pt.y), float(pt.z))}


# ----------------------------------------------------------------------------- passage through a closed leaf
def collect_barriers() -> list[dict]:
    """Every door leaf and gate flap of the set with its size in its own frame: what a body must not pass through unless it is open."""
    out, seen = [], set()
    for ob in bpy.data.objects:
        if _is_fx_or_rig(ob) or _is_cast_obj(ob):
            continue
        part = str(ob.get("sk_part", ""))
        is_leaf = part.startswith("leaf") or ".leaf" in ob.name.lower()
        is_flap = part.startswith("flap")
        if not (is_leaf or is_flap) or ob.name in seen:
            continue
        par = ob.parent
        if par is not None and (str(par.get("sk_part", "")).startswith(("leaf", "flap")) or ".leaf" in par.name.lower()):
            continue
        meshes = [o for o in [ob, *ob.children_recursive] if o.type == "MESH" and not o.hide_render]
        if not meshes:
            continue
        inv = ob.matrix_world.inverted()
        lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
        for m in meshes:
            for c in m.bound_box:
                q = inv @ (m.matrix_world @ Vector(c))
                lo = Vector((min(lo.x, q.x), min(lo.y, q.y), min(lo.z, q.z)))
                hi = Vector((max(hi.x, q.x), max(hi.y, q.y), max(hi.z, q.z)))
        ext = (hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
        if ext[2] < 0.4 or max(ext[0], ext[1]) < 0.25:
            continue
        seen.add(ob.name)
        out.append({"ob": ob, "name": ob.name, "kind": "turnstile_gate" if is_flap else "door_leaf", "lo": lo, "hi": hi, "thin_axis": 0 if ext[0] < ext[1] else 1})
    return out


def leaf_penetration(points_local, lo, hi, thin: int, torso_r: float = 0.13) -> float:
    """Deepest a body (each point a sphere of torso_r) sits in a leaf's slab, metres, given points in the leaf's own frame; 0 when clear."""
    wide = 1 - thin
    best = 0.0
    for lp in points_local:
        if lp.z < lo.z - 0.08 or lp.z > hi.z + 0.08 or lp[wide] < lo[wide] - 0.05 or lp[wide] > hi[wide] + 0.05:
            continue
        if lo[thin] <= lp[thin] <= hi[thin]:
            pen = torso_r
        else:
            pen = torso_r - min(abs(lp[thin] - lo[thin]), abs(lp[thin] - hi[thin]))
        best = max(best, pen)
    return best


def open_degrees(ob) -> float:
    return round(abs(math.degrees(ob.rotation_euler.z)), 1)


def _actor_bones(actor, dg) -> dict:
    """World head/tail positions of the spine, hips and hands of one figure at the current frame."""
    arm = getattr(actor, "rig", None) or next((o for o in actor.coll.all_objects if o.type == "ARMATURE"), None)
    bones = {}
    if arm is not None:
        ev = arm.evaluated_get(dg)
        mw = ev.matrix_world
        for pb in ev.pose.bones:
            nm = pb.name.lower()
            if nm.endswith("hips"):
                bones["hips"] = mw @ pb.head
            elif nm.endswith("spine"):
                bones["spine"] = mw @ pb.head
            elif nm.endswith("spine1"):
                bones["spine1"] = mw @ pb.head
            elif nm.endswith("spine2"):
                bones["spine2"] = mw @ pb.head
            elif nm.endswith("lefthand"):
                bones["hand_L"], bones["wrist_L"] = mw @ pb.tail, mw @ pb.head
            elif nm.endswith("righthand"):
                bones["hand_R"], bones["wrist_R"] = mw @ pb.tail, mw @ pb.head
    if "hips" not in bones:
        base = actor.stage.evaluated_get(dg).matrix_world.translation.copy()
        bones["hips"] = base + Vector((0, 0, 0.90))
        bones["spine2"] = base + Vector((0, 0, 1.35))
    return bones


# ----------------------------------------------------------------------------- rain under cover
def rain_cover_hits(sc, dg, pts_w: np.ndarray, words=COVER_WORDS) -> tuple[int, Counter]:
    """For streak points, how many have overhead cover (a ray straight up meets a canopy, awning, ceiling or roof) and which cover. Fixtures
    and figures do not count as cover, and neither do distant trees or houses: only what the viewer would call shelter."""
    covered, names = 0, Counter()
    for row in pts_w:
        origin = Vector((float(row[0]), float(row[1]), float(row[2]) + 0.02))
        hit, loc, _n, _i, hob, _m = sc.ray_cast(dg, origin, Vector((0.0, 0.0, 1.0)), distance=15.0)
        tries = 0
        while hit and hob is not None and (_is_fx_or_rig(hob) or _is_cast_obj(hob)) and tries < 6:
            hit, loc, _n, _i, hob, _m = sc.ray_cast(dg, loc + Vector((0.0, 0.0, 0.01)), Vector((0.0, 0.0, 1.0)), distance=15.0)
            tries += 1
        if not hit or hob is None:
            continue
        cur, name = hob, None
        while cur is not None:
            if any(w in cur.name.lower() for w in words):
                name = cur.name
                break
            cur = cur.parent
        if name:
            covered += 1
            names[name] += 1
    return covered, names


def streaks_under_boxes(pts: np.ndarray, boxes: list) -> np.ndarray:
    """The streak points that lie below and inside the plan of some cover box (x0, y0, z0, x1, y1, z1): only those can have cover over them,
    so only those need a ray."""
    keep = np.zeros(len(pts), dtype=bool)
    for b in boxes:
        keep |= (pts[:, 0] >= b[0]) & (pts[:, 0] <= b[3]) & (pts[:, 1] >= b[1]) & (pts[:, 1] <= b[4]) & (pts[:, 2] < b[5])
    return pts[keep]


def _rain_frame(shot, rain_obs, dg, cfg, cover_boxes) -> list[dict]:
    sc = bpy.context.scene
    cam = getattr(shot, "camera", None)
    out = []
    if cam is None or not rain_obs:
        return out
    cam_inv = np.array(cam.ob.evaluated_get(dg).matrix_world.inverted(), dtype=np.float32)
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    half = (cam.data.sensor_width * 0.5) / cam.data.lens
    tan_y, tan_x = (half, half * rx / ry) if ry >= rx else (half * ry / rx, half)
    for rob in rain_obs:
        ev = rob.evaluated_get(dg)
        if ev.hide_render:
            continue
        try:
            me = ev.to_mesh()
        except RuntimeError:
            continue
        n = len(me.polygons)
        if n == 0:
            ev.to_mesh_clear()
            continue
        cen = np.empty(n * 3, dtype=np.float32)
        me.polygons.foreach_get("center", cen)
        ev.to_mesh_clear()
        m = np.array(ev.matrix_world, dtype=np.float32)
        pts = cen.reshape(-1, 3)[::2] @ m[:3, :3].T + m[:3, 3]            # two crossed quads per streak: one sample each
        pts = pts[pts[:, 2] > 0.05]
        if len(pts) == 0:
            continue
        pc = pts @ cam_inv[:3, :3].T + cam_inv[:3, 3]
        d = -pc[:, 2]
        vis = pts[(d >= 0.8) & (d <= cfg["rain"]["max_distance_m"]) & (np.abs(pc[:, 0]) <= d * tan_x) & (np.abs(pc[:, 1]) <= d * tan_y)]
        if len(vis) == 0:
            continue
        cand = streaks_under_boxes(vis, cover_boxes)
        cap = int(cfg["rain"]["max_streaks"])
        if len(cand) > cap:
            cand = cand[::max(1, len(cand) // cap)]
        covered, names = rain_cover_hits(sc, dg, cand) if len(cand) else (0, Counter())
        pct = 100.0 * covered / len(vis)
        if pct >= cfg["rain"]["warn_pct"]:
            out.append({"pct": pct, "cover": names.most_common(1)[0][0] if names else "cover"})
    return out


# ----------------------------------------------------------------------------- bodies, hands, props
def _actor_rig_names(actor) -> set:
    names = {actor.stage.name, actor.tilt.name, actor.root.name, actor.ctrl.name, actor.rig.name}
    names.update(j.name for j in actor.J.values())
    names.update(p.name for p in actor.palm.values())
    names.update(a.ob.name for a in (actor.head, actor.chest, actor.feet, actor.top))
    return names


def _is_aj(actor) -> bool:
    return all(hasattr(actor, k) for k in ("palm", "J", "rig", "mesh", "chest", "head", "parts"))


def _vgroup_sets(actor) -> dict:
    """The triangles of the body mesh that belong to each hand and forearm (by bone weight), for the hand-through-prop measurement.
    Read from the EVALUATED mesh: a dressed body carries a mask that hides the skin under its clothes, so the mesh the sweep measures
    has fewer vertices than the stored one and its numbering differs (indices taken from the stored mesh put the "hand" all over the
    torso). The mask does not change during a shot, so one reading holds for every frame."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = actor.mesh.evaluated_get(dg)
    names = {vg.index: vg.name for vg in actor.mesh.vertex_groups}
    tris = {"L": [], "R": []}
    try:
        me = ev.to_mesh()
    except RuntimeError:
        return tris
    try:
        hand = {"L": set(), "R": set()}
        for v in me.vertices:
            best, bw = "", 0.0
            for g in v.groups:
                if g.weight > bw:
                    bw, best = g.weight, names.get(g.group, "")
            if "LeftHand" in best or "LeftForeArm" in best:
                hand["L"].add(v.index)
            elif "RightHand" in best or "RightForeArm" in best:
                hand["R"].add(v.index)
        me.calc_loop_triangles()
        for t in me.loop_triangles:
            vs = tuple(t.vertices)
            for s in "LR":
                if any(i in hand[s] for i in vs):
                    tris[s].append(vs)
    finally:
        ev.to_mesh_clear()
    return tris


def _combined(obs, dg):
    """One world BVH over several objects: (bvh, vertices, lo, hi) or (None, ...)."""
    verts, polys, off = [], [], 0
    for o in obs:
        em = build_eval_mesh(o, dg)
        if em is None:
            continue
        verts.append(em.verts_w)
        polys.append(em.tris + off)
        off += len(em.verts_w)
    if not polys:
        return None, np.zeros((0, 3), np.float32), None, None
    v, p = np.concatenate(verts), np.concatenate(polys)
    return BVHTree.FromPolygons([tuple(r) for r in v.tolist()], p.tolist()), v, Vector(v.min(axis=0).tolist()), Vector(v.max(axis=0).tolist())


def _sub_bvh(actor, dg, tri_list):
    """World BVH of a subset of triangles of the actor's body mesh (a hand and forearm)."""
    if not tri_list:
        return None, np.zeros((0, 3), np.float32), None, None
    em = build_eval_mesh(actor.mesh, dg)
    if em is None:
        return None, np.zeros((0, 3), np.float32), None, None
    tri = np.array(tri_list, dtype=np.int32)
    uniq, inv = np.unique(tri, return_inverse=True)
    v = em.verts_w[uniq]
    return BVHTree.FromPolygons([tuple(r) for r in v.tolist()], inv.reshape(-1, 3).tolist()), v, Vector(v.min(axis=0).tolist()), Vector(v.max(axis=0).tolist())


def max_penetration_mm(bvh_a, verts_a, lo_a, hi_a, bvh_b, verts_b, lo_b, hi_b) -> float:
    """Deepest vertex of one mesh inside the other, in mm (box-filtered, at most 400 vertices each way)."""
    if bvh_a is None or bvh_b is None or lo_a is None or lo_b is None:
        return 0.0
    if not (lo_a.x <= hi_b.x and hi_a.x >= lo_b.x and lo_a.y <= hi_b.y and hi_a.y >= lo_b.y and lo_a.z <= hi_b.z and hi_a.z >= lo_b.z):
        return 0.0
    worst = 0.0
    for verts, bvh, lo, hi in ((verts_a, bvh_b, lo_b, hi_b), (verts_b, bvh_a, lo_a, hi_a)):
        sel = verts[(verts[:, 0] >= lo.x) & (verts[:, 0] <= hi.x) & (verts[:, 1] >= lo.y) & (verts[:, 1] <= hi.y) & (verts[:, 2] >= lo.z) & (verts[:, 2] <= hi.z)]
        if len(sel) > 400:
            sel = sel[::len(sel) // 400]
        for row in sel:
            v = Vector((float(row[0]), float(row[1]), float(row[2])))
            loc, nor, _i, dist = bvh.find_nearest(v)
            if dist is None or dist <= worst or (v - loc).dot(nor) >= 0.0:
                continue
            if _ray_parity(bvh, v, Vector((0.137, 0.291, 0.947)).normalized(), 16) % 2 == 1:
                worst = dist
    return worst * 1000.0


def _dist(bvh, pt) -> float:
    _l, _n, _i, d = bvh.find_nearest(pt)
    return float(d) if d is not None else 9.99


def _tips(actor, side: str, dg) -> dict:
    sn = "Left" if side == "L" else "Right"
    ev = actor.rig.evaluated_get(dg)
    mw = ev.matrix_world
    out = {}
    for f in FINGERS:
        pb = ev.pose.bones.get(f"{P}{sn}Hand{f}4")
        if pb is not None:
            out[f] = mw @ pb.head
        else:
            pb3 = ev.pose.bones.get(f"{P}{sn}Hand{f}3")
            if pb3 is not None:
                out[f] = mw @ pb3.tail
    return out


def _angle(a: Vector, b: Vector) -> float:
    if a.length < 1e-6 or b.length < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, a.normalized().dot(b.normalized())))))


def _fwd_xy(actor, dg) -> Vector:
    f = actor.J["torso"].evaluated_get(dg).matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))
    f.z = 0.0
    if f.length < 1e-4:
        f = actor.root.evaluated_get(dg).matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))
        f.z = 0.0
    return f.normalized() if f.length > 1e-4 else Vector((0.0, -1.0, 0.0))


def _find_attachments(shot, holds_by_prop: set, worn: set) -> dict:
    """{actor id: [prop root, ...]}: objects parented or constrained to a figure's rig by hand (not through hold, not listed in shot.wears)."""
    out = {}
    for aid, a in shot.actors.items():
        if not _is_aj(a):
            continue
        rig = _actor_rig_names(a)
        part = {o.name for o in a.parts.values()}
        found = []
        for ob in bpy.data.objects:
            if ob.name in rig or ob.name in part or ob.name in holds_by_prop or ob.name in worn or ob.name.startswith(f"{aid}."):
                continue
            att = ob.parent is not None and ob.parent.name in rig
            if not att:
                att = any(getattr(c, "target", None) is not None and c.target.name in rig for c in ob.constraints)
            if att and any(o.type == "MESH" for o in [ob, *ob.children_recursive]):
                found.append(ob)
        out[aid] = found
    return out


def _movable_props(shot, hold_props: set, own: set) -> list:
    """Loose props that could float: everything ever held, anything registered as a prop asset, and animated stand-alone objects."""
    cand = {}
    for pn in hold_props:
        ob = bpy.data.objects.get(pn)
        if ob is not None:
            cand[ob.name] = ob
    for ob in bpy.data.objects:
        if ob.name in own or ob.type in ("CAMERA", "LIGHT", "ARMATURE") or any(c.name in ("FX", "LIGHTS", "CAMERA") for c in ob.users_collection):
            continue
        if ob.parent is not None and ob.parent.name in cand:
            continue
        has_loc = any(fc.data_path == "location" for fc in core.fcurves(ob))
        if str(ob.get("asset_id") or "").startswith("prop_"):
            cand[ob.name] = ob
        elif has_loc and not any(k in ob.name.lower() for k in ("drawer", "leaf", "door", "flap", "cam", "light", "handle", "edge")):
            if any(o.type == "MESH" for o in [ob, *ob.children_recursive]):
                cand[ob.name] = ob
        elif str(ob.get("sk_type") or "") in ("laptop", "papers_stack", "mugs") and has_loc:
            cand[ob.name] = ob
    roots = []
    for ob in cand.values():
        p, under = ob.parent, False
        while p is not None:
            if p.name in cand:
                under = True
                break
            p = p.parent
        if not under:
            roots.append(ob)
    return roots


def _group_targets(events: list[dict], fps: float, nframes: int) -> list[dict]:
    """Dense per-frame reach and aim loops to one target become one event, checked at its start, middle and end. A reach made inside a named
    action is covered by that action's own event; actions that are not aimed at anything (walk, carry, read...) are left out."""
    groups = []
    for c in events:
        if c.get("target") is None:
            continue
        if c["kind"] == "reach" and c.get("action") is not None:
            continue
        if c["kind"] == "action" and c.get("action") in ("read", "phone", "sit_idle", "walk", "run", "carry"):
            continue
        for g in reversed(groups):
            if g["actor"] == c["actor"] and g["side"] == c["side"] and g["kind"] == c["kind"] and abs(c["t"] - g["t1"]) <= 0.45:
                same = c["label"] == g["label"]
                if not same and isinstance(c["target"], (tuple, list, Vector)) and isinstance(g["target"], (tuple, list, Vector)):
                    same = (Vector(c["target"]) - Vector(g["target"])).length < 0.18
                if same:
                    g["t1"] = max(g["t1"], c["t"])
                    break
        else:
            groups.append({"kind": c["kind"], "action": c.get("action"), "actor": c["actor"], "side": c["side"], "target": c["target"], "label": c["label"], "t0": c["t"], "t1": c["t"]})
    out = []
    for g in groups:
        ts = [g["t0"]] + ([0.5 * (g["t0"] + g["t1"]), g["t1"]] if g["t1"] - g["t0"] > 0.3 else [])
        for t in ts:
            out.append({**g, "t": t, "frame": max(1, min(nframes, int(round(t * fps)) + 1))})
    return out


# ----------------------------------------------------------------------------- the sweep
class _Run:
    """State of one sweep: the shot, the thresholds, the flags found, the time spent and what broke."""

    def __init__(self, shot, cfg):
        self.shot, self.cfg = shot, cfg
        self.flags: list[dict] = []
        self.seconds: dict = defaultdict(float)
        self.failed: dict = {}
        self.fails: Counter = Counter()

    def flag(self, code, actor, obj, frame, level, value, unit, extra=None, point=None):
        """Record one finding at one frame. A fault whose place is outside the camera's view at this frame is only a warning."""
        if level == "block" and point is not None and not _in_view(self.shot, point):
            level = "warn"
        self.flags.append({"code": code, "actor": actor or "", "object": obj or "", "frame": int(frame), "level": level, "value": float(value), "unit": unit, "extra": extra or {}})

    def guard(self, name, fn, *args):
        """Run one check on one frame; an error in it is recorded once, the check is switched off after three, and the sweep goes on."""
        if self.fails[name] >= 3:
            return
        t0 = time.perf_counter()
        try:
            fn(*args)
        except Exception as ex:                      # noqa: BLE001 - one bad object must not stop the other checks
            self.fails[name] += 1
            self.failed.setdefault(name, f"{type(ex).__name__}: {ex}")
        self.seconds[name] += time.perf_counter() - t0


def sweep(shot, step=None) -> dict:
    """Run every physical check on a built shot (after build_shot and actor._finalize) and return the merged findings.

    Passage through leaves and gates is looked at on every frame (it is cheap and a crossing lasts a few frames); everything else on every
    `step`-th frame plus the frame of every recorded reach, press or aim. Returns {items, blocking, warnings, seconds, frames_checked,
    holds, interactions}; items match the findings in checks.json (source "physical")."""
    cfg = config()
    step = int(step or cfg["step"])
    _load_cats()
    sc = bpy.context.scene
    n, fps = int(shot.frames), float(shot.fps)
    run = _Run(shot, cfg)
    holds = list(getattr(shot, "holds", []))
    inter = list(getattr(shot, "interactions", []))
    worn = {w["prop"] for w in getattr(shot, "wears", [])}
    hold_props = {h["prop"] for h in holds}
    actors = {k: a for k, a in shot.actors.items() if _is_aj(a)}
    actor_names = set(shot.actors)

    # what the shot code asked for
    for e in inter:
        if e["kind"] == "action" and e.get("action") in _targeted() and e.get("target") is None:
            run.flag("untargeted_action", e["actor"], e["action"], shot.f(e["t"]), "warn", 0.0, "")
    events = _group_targets(inter, fps, n)
    event_frames = {e["frame"] for e in events}
    # an event frame (a reach, a press, a wave) always gets its target check; the costly body-and-prop checks join it only when that figure is
    # carrying something at that frame, otherwise they run on the regular steps (a row of typists would otherwise add a hundred frames)
    steps = {*range(1, n + 1, step), n}
    carrying = {e["frame"] for e in events if any(h["actor"] == e["actor"] and h["f0"] <= e["frame"] and (h["f1"] is None or e["frame"] < h["f1"]) for h in holds)}
    sweep_frames = sorted(steps | carrying)
    sweep_set = set(sweep_frames)

    # one-time setup (cached for the whole sweep)
    t0 = time.perf_counter()
    lap = {"t": t0}

    def mark(name):
        now = time.perf_counter()
        run.seconds[name] = now - lap["t"]
        lap["t"] = now

    vg = {}
    for aid, a in actors.items():
        try:
            vg[aid] = _vgroup_sets(a)
        except Exception as ex:                      # noqa: BLE001
            run.failed.setdefault("setup_vertex_groups", f"{type(ex).__name__}: {ex}")
    mark("setup_vertex_groups")
    attach = _find_attachments(shot, hold_props, worn)
    attached = {p.name for lst in attach.values() for p in lst}
    own_all = set()
    for a in actors.values():
        own_all |= _actor_rig_names(a) | {o.name for o in a.parts.values()}
    movable = [p for p in _movable_props(shot, hold_props, own_all) if p.name not in attached and p.name not in worn]
    mark("setup_scan")
    barriers = collect_barriers()
    rain_obs = [o for o in bpy.data.objects if o.type == "MESH" and o.get("sk_atmo") == "rain"]
    mark("setup_barriers")
    core.at_frame(1)
    # what belongs to each figure: its own body meshes, and every other mesh in its collection or held or hung on it (its props)
    body, props = {}, {}
    all_cast = set()
    for aid, a in shot.actors.items():
        b, pg, seen = [], defaultdict(list), set()
        for ob in a.coll.all_objects:
            if ob.type != "MESH":
                continue
            all_cast.add(ob.name)
            if ob.name.startswith(f"{aid}."):
                b.append(ob)
            else:
                pg[logical_root_name(ob, actor_names)].append(ob)
                seen.add(ob.name)
        extra_roots = [bpy.data.objects.get(h["prop"]) for h in holds if h["actor"] == aid] + list(attach.get(aid, []))
        for root in extra_roots:
            if root is None:
                continue
            for o in [root, *root.children_recursive]:
                if o.type == "MESH" and o.name not in seen:
                    pg[logical_root_name(o, actor_names)].append(o)
                    seen.add(o.name)
                    all_cast.add(o.name)
        body[aid], props[aid] = b, dict(pg)
    set_obs = [o for o in bpy.data.objects if o.type == "MESH" and o.name not in all_cast and not _is_fx_or_rig(o) and not _is_cast_obj(o)]
    meta = {o.name: {"ob": o, "root": logical_root_name(o, actor_names), "floor": _is_floor(o), "seat": _is_seat(o), "shell": _is_shell(o), "em": None, "key": None,
                     "anim": _animated(o)} for o in set_obs}
    static_boxes = [(o.name, _aabb_of(o)) for o in set_obs if not meta[o.name]["anim"] and not o.hide_render]
    dynamic = [o.name for o in set_obs if meta[o.name]["anim"]]
    cover_boxes = [_aabb_of(o) for o in set_obs if rain_obs and not o.hide_render and _chain_has(o, COVER_WORDS)]
    mark("setup_meta")
    ctx = {"vg": vg, "attach": attach, "movable": movable, "barriers": barriers, "rain": rain_obs, "cover_boxes": cover_boxes, "body": body, "props": props, "meta": meta,
           "static_boxes": static_boxes, "dynamic": dynamic, "holds": holds, "worn": worn, "actors": actors, "prev_sides": {}}
    by_frame: dict[int, list] = defaultdict(list)
    for e in events:
        by_frame[e["frame"]].append(e)

    for f in range(1, n + 1):
        dg = core.at_frame(f)
        bones = {aid: _actor_bones(a, dg) for aid, a in shot.actors.items()}
        run.guard("passage", _passage, run, ctx, dg, f, bones)
        if f in sweep_set:
            run.guard("interpenetration", _interpenetration, run, ctx, dg, f, bones)
            if rain_obs:
                run.guard("rain", _rain, run, ctx, dg, f)
            run.guard("holds", _hold_checks, run, ctx, dg, f)
            run.guard("attachments", _attachment_checks, run, ctx, dg, f)
            run.guard("floating", _floating, run, ctx, dg, f)
        for e in by_frame.get(f, []):
            run.guard("targets", _target_check, run, ctx, dg, f, e)

    for p in getattr(shot, "passages", []):                  # walks the build found going through a shut barrier (anchors.check_walk): same item, same merge
        a = shot.actors.get(p["actor"])
        pt = (a.stage.evaluated_get(core.at_frame(p["frame"])).matrix_world.translation + Vector((0.0, 0.0, 1.0))) if a is not None else None
        run.flag("through_closed_leaf", p["actor"], p["barrier"], p["frame"], "block", p["open_deg"], "deg", {"depth_cm": round(run.cfg["passage"]["torso_radius_m"] * 100.0 - p["clearance_cm"], 1)}, point=pt)

    cam = getattr(shot, "camera", None)
    items = []
    for r in merge_flags(run.flags):
        v = cam.view_at(r["frame"]) if cam else None
        items.append({"level": r["level"], "code": r["code"], "source": "physical", "view": v["id"] if v else None, "frame": r["frame"], "frames": r["frames"],
                      "actor": r["actor"], "object": r["object"], "value": round(r["value"], 1), "unit": r["unit"], "text": _text(r)})
    for name, msg in run.failed.items():
        items.append({"level": "warn", "code": "physical_check_failed", "source": "physical", "view": None, "frame": None, "frames": None, "actor": "", "object": name,
                      "value": 0.0, "unit": "", "text": f"the physical check '{name}' failed and was skipped ({msg}): the rest of the physical checks ran."})
    return {"items": items, "blocking": sum(1 for i in items if i["level"] == "block"), "warnings": sum(1 for i in items if i["level"] == "warn"),
            "seconds": {k: round(v, 2) for k, v in run.seconds.items()}, "frames_checked": len(sweep_set | event_frames), "holds": len(holds), "interactions": len(inter)}


def _targeted() -> tuple:
    try:
        from . import actions
        return tuple(actions.TARGETED)
    except Exception:                                # noqa: BLE001
        return ()


def _animated(ob) -> bool:
    cur = ob
    while cur is not None:
        ad = cur.animation_data
        if ad is not None and (ad.action or ad.drivers):
            return True
        cur = cur.parent
    return False


def _held_at(ctx, aid, prop, f, settle) -> bool:
    return any(h["actor"] == aid and h["prop"] == prop and h["f0"] + settle <= f and (h["f1"] is None or f < h["f1"]) for h in ctx["holds"])


def _any_held(ctx, prop, f, grace=0) -> bool:
    return any(h["prop"] == prop and h["f0"] <= f and (h["f1"] is None or f < h["f1"] + grace) for h in ctx["holds"])


def _passage(run, ctx, dg, f, bones):
    cfg = run.cfg["passage"]
    r = cfg["torso_radius_m"]
    for aid, b in bones.items():
        pts = [b[k] for k in ("hips", "spine", "spine1", "spine2") if k in b]
        hips = b["hips"]
        for bar in ctx["barriers"]:
            ob = bar["ob"].evaluated_get(dg)
            if ob.hide_render:
                continue
            inv = ob.matrix_world.inverted()
            lo, hi, thin = bar["lo"], bar["hi"], bar["thin_axis"]
            wide = 1 - thin
            pen = leaf_penetration([inv @ p for p in pts], lo, hi, thin, r)
            lh = inv @ hips
            mid = 0.5 * (lo[thin] + hi[thin])
            in_span = (lo.z - 0.15 <= lh.z <= hi.z + 0.25) and (lo[wide] - 0.05 <= lh[wide] <= hi[wide] + 0.05)
            side = 1 if lh[thin] >= mid else -1
            key = (aid, bar["name"])
            prev = ctx["prev_sides"].get(key)
            crossed = bool(prev and in_span and prev[1] and side != prev[0])
            ctx["prev_sides"][key] = (side, in_span)
            if pen <= 0.0 and not crossed:
                continue
            deg = open_degrees(ob)
            depth_cm = pen * 100.0 if pen > 0 else r * 100.0
            if deg >= cfg["warn_open_deg"]:
                continue                                       # open wide enough to walk through
            level = "block" if (deg < cfg["block_open_deg"] or depth_cm >= cfg["block_depth_cm"]) else "warn"
            run.flag("through_closed_leaf", aid, bar["name"], f, level, deg, "deg", {"depth_cm": round(depth_cm, 1)}, point=hips)


def _interpenetration(run, ctx, dg, f, bones):
    cfg = run.cfg["interp"]
    shot = run.shot
    cache: dict[str, EvalMesh | None] = {}

    def cast_em(ob):
        if ob.name not in cache:
            cache[ob.name] = build_eval_mesh(ob, dg)
        return cache[ob.name]

    def set_em(name):
        m = ctx["meta"][name]
        if m["anim"]:
            ev = m["ob"].evaluated_get(dg)
            key = tuple(round(v, 5) for row in ev.matrix_world for v in row)
            if m["key"] != key:
                m["em"], m["key"] = build_eval_mesh(m["ob"], dg), key
        elif m["key"] is None:
            m["em"], m["key"] = build_eval_mesh(m["ob"], dg), "static"
        return m["em"]

    def set_candidates(box):
        out = [nm for nm, sb in ctx["static_boxes"] if _aabb_overlap(box, sb, 0.02)]
        for nm in ctx["dynamic"]:
            ev = ctx["meta"][nm]["ob"].evaluated_get(dg)
            if not ev.hide_render and _aabb_overlap(box, _aabb_of(ev), 0.02):
                out.append(nm)
        return out

    best: dict[tuple, dict] = {}

    def record(sub, actor, obj, res, extra=None):
        key = (sub, actor, obj)
        if res["depth_cm"] >= cfg["warn_cm"] and (key not in best or res["depth_cm"] > best[key]["depth_cm"]):
            best[key] = {**res, "sub": sub, **(extra or {})}

    boxes, overall, hands = {}, {}, {}
    for aid, a in shot.actors.items():
        b = bones[aid]
        hands[aid] = [(b[k], cfg["hand_radius_m"]) for k in ("hand_L", "hand_R", "wrist_L", "wrist_R") if k in b]
        bl, lo, hi = [], [1e9] * 3, [-1e9] * 3
        for ob in ctx["body"].get(aid, []):
            ev = ob.evaluated_get(dg)
            if ev.hide_render:
                continue
            ab = _aabb_of(ev)
            bl.append((ob, ab))
            for k in range(3):
                lo[k], hi[k] = min(lo[k], ab[k]), max(hi[k], ab[k + 3])
        boxes[aid] = bl
        if bl:
            overall[aid] = (*lo, *hi)
    seated = {aid: bool(getattr(a, "floating", False) or (bones[aid]["hips"].z < 0.72)) for aid, a in shot.actors.items()}
    pboxes = {}
    for aid in shot.actors:
        for pname, pobs in ctx["props"].get(aid, {}).items():
            pl = [(o, _aabb_of(o.evaluated_get(dg))) for o in pobs if not o.evaluated_get(dg).hide_render]
            if pl:
                pboxes[(aid, pname)] = pl

    for aid, bl in boxes.items():                                              # a figure against the set
        if aid not in overall:
            continue
        for sn in set_candidates(overall[aid]):
            m = ctx["meta"][sn]
            if seated[aid] and m["seat"]:
                continue
            ev = m["ob"].evaluated_get(dg)
            if ev.hide_render:
                continue
            sab, em_s = _aabb_of(ev), None
            for aob, aab in bl:
                if m["floor"] and (aob.name.endswith(".shoes") or aob.name.endswith(".trousers")):
                    continue                                                    # soles stand on the floor
                if not _aabb_overlap(aab, sab, 0.02):
                    continue
                em_s = em_s or set_em(sn)
                em_a = cast_em(aob)
                if em_s is None or em_a is None:
                    continue
                res = penetration_depth_cm(em_a, em_s, shell=m["shell"], pierce_min_cm=cfg["pierce_cm"])
                if res:
                    record("actor_set", aid, m["root"], res)
    ids = list(boxes)
    for i in range(len(ids)):                                                  # a figure against another figure
        for j in range(i + 1, len(ids)):
            a1, a2 = ids[i], ids[j]
            if a1 not in overall or a2 not in overall or not _aabb_overlap(overall[a1], overall[a2]):
                continue
            for o1, b1 in boxes[a1]:
                for o2, b2 in boxes[a2]:
                    if _aabb_overlap(b1, b2):
                        e1, e2 = cast_em(o1), cast_em(o2)
                        res = penetration_depth_cm(e1, e2) if e1 and e2 else None
                        if res:
                            record("actor_actor", a1, a2, res)
    for aid, bl in boxes.items():                                              # a figure against the props held or hung on any figure
        if aid not in overall:
            continue
        for (owner, pname), pl in pboxes.items():
            own = owner == aid
            for pob, pab in pl:
                if not _aabb_overlap(overall[aid], pab):
                    continue
                em_p = None
                for aob, aab in bl:
                    if not _aabb_overlap(aab, pab):
                        continue
                    em_p = em_p or cast_em(pob)
                    em_a = cast_em(aob)
                    if em_p is None or em_a is None:
                        continue
                    res = penetration_depth_cm(em_a, em_p, hands=hands[aid] if own else None, hand_cm=cfg["hand_cm"])
                    if res:
                        record("actor_own_prop" if own else "actor_other_prop", aid, pname, res)
    for (owner, pname), pl in pboxes.items():                                  # a prop against the set
        for pob, pab in pl:
            em_p = None
            for sn in set_candidates(pab):
                m = ctx["meta"][sn]
                if m["floor"]:
                    continue
                em_s = set_em(sn)
                if em_s is None:
                    continue
                em_p = em_p or cast_em(pob)
                if em_p is None:
                    break
                res = penetration_depth_cm(em_p, em_s, shell=m["shell"], pierce_min_cm=cfg["pierce_cm"])
                if res:
                    record("prop_set", owner, m["root"], res, {"prop": pname})
    for (sub, actor, obj), r in best.items():
        level = "block" if r["depth_cm"] >= cfg["block_cm"] else "warn"
        run.flag("interpenetration", actor, obj, f, level, r["depth_cm"], "cm", {"sub": sub, "prop": r.get("prop", "")}, point=r["at"])


def _rain(run, ctx, dg, f):
    cfg = run.cfg["rain"]
    for r in _rain_frame(run.shot, ctx["rain"], dg, run.cfg, ctx["cover_boxes"]):
        run.flag("rain_under_cover", "", r["cover"], f, "block" if r["pct"] >= cfg["block_pct"] else "warn", r["pct"], "%")


def _hold_checks(run, ctx, dg, f):
    g, cr = run.cfg["grip"], run.cfg["carry"]
    settle = int(g["settle_s"] * run.shot.fps)
    for h in ctx["holds"]:
        if not (h["f0"] + settle <= f and (h["f1"] is None or f < h["f1"])):
            continue
        a = ctx["actors"].get(h["actor"])
        prop = bpy.data.objects.get(h["prop"])
        if a is None or prop is None or _hidden(prop, dg):
            continue
        pbvh, pverts, plo, phi = _combined(_mesh_children(prop, dg), dg)
        if pbvh is None:
            continue
        side, aid, pname = h["side"], h["actor"], prop.name
        palm = a.palm[side].evaluated_get(dg).matrix_world.translation.copy()
        palm_d = _dist(pbvh, palm)
        tip_d = [_dist(pbvh, p) for p in _tips(a, side, dg).values()]
        other = "L" if side == "R" else "R"
        other_near = sum(1 for p in _tips(a, other, dg).values() if _dist(pbvh, p) <= g["tip_m"])
        near = sum(1 for d in tip_d if d <= g["tip_m"]) + other_near
        min_tip = min(tip_d) if tip_d else 9.99
        centre = (plo + phi) * 0.5
        if near == 0 and palm_d > g["palm_m"]:
            run.flag("grip_open", aid, pname, f, "block", min_tip * 100.0, "cm", {"palm_cm": palm_d * 100.0}, point=centre)
        sets = ctx["vg"].get(aid)
        if sets:
            hb = _sub_bvh(a, dg, sets[side])
            pen = max_penetration_mm(pbvh, pverts, plo, phi, *hb)
            if pen >= g["warn_mm"]:
                run.flag("grip_impaled", aid, pname, f, "block" if pen >= g["block_mm"] else "warn", pen, "mm", point=centre)
        if "phone" in pname.lower() or "smartphone" in str(prop.get("asset_id", "")).lower():
            pe = prop.evaluated_get(dg)
            to_head = (a.head.ob.evaluated_get(dg).matrix_world.translation - pe.matrix_world.translation).normalized()
            screen = (pe.matrix_world.to_3x3() @ Vector((0.0, -1.0, 0.0))).normalized()
            dot = float(screen.dot(to_head))
            if dot < g["backwards_dot"]:
                run.flag("prop_backwards", aid, pname, f, "warn", math.degrees(math.acos(max(-1.0, min(1.0, dot)))), "deg", point=centre)
        # carry stability: a plain hold keeps the prop level in front of the chest; a prop turned with the hand is meant to move with it
        held = a._held.get(pname)
        upright = (not held[3].get("turn", True)) if held else (not h["solved"])
        upright = upright or any(k in pname.lower() for k in ("carrier", "cup", "tray", "box", "mug"))
        if upright and not any(k in pname.lower() for k in NO_CHECK):
            fwd = _fwd_xy(a, dg)
            left = Vector((-fwd.y, fwd.x, 0.0))
            rel = centre - a.chest.ob.evaluated_get(dg).matrix_world.translation
            fo, so = float(rel.dot(fwd)), float(rel.dot(left))
            up = (prop.evaluated_get(dg).matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, up.z))))
            if fo < cr["behind_m"]:
                run.flag("carry_behind", aid, pname, f, "block", -fo * 100.0, "cm", point=centre)
            elif abs(so) > cr["flung_m"]:
                run.flag("carry_flung", aid, pname, f, "block", abs(so) * 100.0, "cm", point=centre)
            if tilt > cr["tilt_deg"]:
                run.flag("carry_tilt", aid, pname, f, "block", tilt, "deg", point=centre)


def _attachment_checks(run, ctx, dg, f):
    c = run.cfg["attach"]
    for aid, plist in ctx["attach"].items():
        a = ctx["actors"][aid]
        ev = a.rig.evaluated_get(dg)
        mw = ev.matrix_world
        shoulder = []
        for sn in ("Left", "Right"):
            for bn in ("Shoulder", "Arm"):
                pb = ev.pose.bones.get(f"{P}{sn}{bn}")
                if pb is not None:
                    shoulder += [mw @ pb.head, mw @ pb.tail]
        hand = []
        for s in "LR":
            hand.append(a.palm[s].evaluated_get(dg).matrix_world.translation.copy())
            hand += list(_tips(a, s, dg).values())
        for prop in plist:
            pbvh, pverts, plo, phi = _combined(_mesh_children(prop, dg), dg)
            if pbvh is None:
                continue
            min_hand = min((_dist(pbvh, p) for p in hand), default=9.99)
            min_sh = min((_dist(pbvh, p) for p in shoulder), default=9.99)
            centre = (plo + phi) * 0.5
            if min_hand > c["hand_m"] and min_sh > c["shoulder_m"]:
                run.flag("loose_attachment", aid, prop.name, f, "block", min_hand * 100.0, "cm", point=centre)
            parts = [o for role, o in a.parts.items() if o.type == "MESH" and role not in ("hair", "facial_hair", "shoes") and not _hidden(o, dg)]
            box = (plo.x, plo.y, plo.z, phi.x, phi.y, phi.z)
            tv, tp, off = [], [], 0
            for o in parts:
                if not _aabb_overlap(_aabb_of(o.evaluated_get(dg)), box, 0.02):
                    continue
                em = build_eval_mesh(o, dg)
                if em is None:
                    continue
                bv, vs, pl = _cropped_bvh(em, box, 0.02)
                if bv is None:
                    continue
                tv.append(vs)
                tp += [(x + off, y + off, z + off) for x, y, z in pl]
                off += len(vs)
            if not tp:
                continue
            vs = np.concatenate(tv)
            bbvh = BVHTree.FromPolygons([tuple(r) for r in vs.tolist()], tp)
            pen = max_penetration_mm(pbvh, pverts, plo, phi, bbvh, vs, Vector(vs.min(axis=0).tolist()), Vector(vs.max(axis=0).tolist()))
            if pen >= c["warn_mm"]:
                run.flag("attachment_in_body", aid, prop.name, f, "block" if pen >= c["block_mm"] else "warn", pen, "mm", point=centre)


def _floating(run, ctx, dg, f):
    c = run.cfg["float"]
    sc = bpy.context.scene
    hands = []
    for a in ctx["actors"].values():
        for s in "LR":
            hands.append(a.palm[s].evaluated_get(dg).matrix_world.translation.copy())
            hands += list(_tips(a, s, dg).values())
    for prop in ctx["movable"]:
        if _any_held(ctx, prop.name, f, int(c["grace_frames"])) or _hidden(prop, dg):
            continue
        pbvh, _v, plo, phi = _combined(_mesh_children(prop, dg), dg)
        if pbvh is None:
            continue
        own = {prop.name} | {o.name for o in prop.children_recursive}
        cx, cy = 0.5 * (plo.x + phi.x), 0.5 * (plo.y + phi.y)
        dx, dy = 0.35 * (phi.x - plo.x), 0.35 * (phi.y - plo.y)
        gap, sup = 9.99, None
        for px, py in ((cx, cy), (cx - dx, cy - dy), (cx + dx, cy - dy), (cx - dx, cy + dy), (cx + dx, cy + dy)):
            orig = Vector((px, py, plo.z + 0.015))
            for _ in range(12):
                hit, hloc, _n, _i, hob, _m = sc.ray_cast(dg, orig, Vector((0, 0, -1)), distance=3.0)
                if not hit or hob is None:
                    break
                if hob.name in own or any(cc.name == "FX" for cc in hob.users_collection):
                    orig = hloc - Vector((0, 0, 0.001))
                    continue
                if plo.z - hloc.z < gap:
                    gap, sup = plo.z - hloc.z, hob.name
                break
        if sup is None or gap <= c["gap_cm"] / 100.0:
            continue
        hand_d = min((_dist(pbvh, p) for p in hands), default=9.99)
        if hand_d > c["hand_cm"] / 100.0:
            run.flag("floating_prop", "", prop.name, f, "block", gap * 100.0, "cm", {"over": sup}, point=(plo + phi) * 0.5)


def _target_check(run, ctx, dg, f, e):
    c = run.cfg["reach"]
    a = ctx["actors"].get(e["actor"])
    if a is None:
        return
    tgt = e["target"]
    try:
        tpos = core.point_of(tgt)
    except Exception:                                # noqa: BLE001 - a target that is not a place cannot be measured
        return
    side, aid, label = e["side"] or "R", e["actor"], e["label"]
    if label.startswith("pt("):
        label = "a point in space"                                                  # keystrokes and posed reaches name a point, and a row of them is one fault
    chest = a.chest.ob.evaluated_get(dg).matrix_world.translation.copy()
    head = a.head.ob.evaluated_get(dg).matrix_world
    to_xy = Vector((tpos.x - chest.x, tpos.y - chest.y, 0.0))
    facing = _angle(_fwd_xy(a, dg), to_xy) if to_xy.length > 0.05 else 0.0
    head_fwd = head.to_3x3() @ Vector((0.0, -1.0, 0.0))
    head_deg = _angle(head_fwd, tpos - head.translation) if (tpos - head.translation).length > 0.05 else 0.0
    palm = a.palm[side].evaluated_get(dg).matrix_world.translation.copy()
    pts = [palm, *_tips(a, side, dg).values()]
    if facing >= c["facing_block_deg"]:
        run.flag("not_facing_target", aid, label, f, "block", facing, "deg", {"head": head_deg}, point=chest)
    elif facing >= c["facing_warn_deg"] and head_deg >= c["head_warn_deg"]:
        run.flag("not_facing_target", aid, label, f, "warn", facing, "deg", {"head": head_deg}, point=chest)
    if e["kind"] in ("reach", "action") and e.get("action") not in ("point", "wave"):
        if hasattr(tgt, "type") and tgt.type == "MESH" and not _hidden(tgt, dg):
            tb, *_ = _combined([tgt], dg)
            dist = min(_dist(tb, p) for p in pts) if tb else min((p - tpos).length for p in pts)
        else:
            dist = min((p - tpos).length for p in pts)
        cm = dist * 100.0
        if cm >= c["miss_block_cm"]:
            run.flag("reach_miss", aid, label, f, "block", cm, "cm", point=palm)
        elif cm >= c["miss_warn_cm"]:
            run.flag("reach_short", aid, label, f, "warn", cm, "cm", point=palm)
    # the forearm from elbow to palm must not pass through anything solid on the way
    elbow = a.J[f"el.{side}"].evaluated_get(dg).matrix_world.translation.copy()
    arm = palm - elbow
    if arm.length > 0.05:
        skip = _actor_rig_names(a) | {o.name for o in a.coll.all_objects}
        if hasattr(tgt, "name"):
            skip.add(tgt.name)
            skip.update(o.name for o in getattr(tgt, "children_recursive", []))
        d, orig, rem = arm.normalized(), elbow + arm.normalized() * 0.04, arm.length - 0.06
        sc = bpy.context.scene
        for _ in range(8):
            if rem <= 0.01:
                break
            hit, hloc, _n, _i, hob, _m = sc.ray_cast(dg, orig, d, distance=rem)
            if not hit or hob is None:
                break
            if hob.name in skip or any(cc.name in ("FX", "CAST") or cc.name.startswith("CAST_") for cc in hob.users_collection):
                rem -= (hloc - orig).length + 0.002
                orig = hloc + d * 0.002
                continue
            run.flag("arm_through_obstacle", aid, hob.name, f, "warn", (hloc - elbow).length * 100.0, "cm", point=palm)
            break
