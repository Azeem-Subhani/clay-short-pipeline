"""stagekit.audit - the set audit: pure measurement of a finished set, run inside Blender after it is built.

    res = audit.audit([WIDE, (pos, aim, lens), ...], room=R)       # cameras as (pos, aim, lens) or dicts; the first is the wide
    res["inventory"]    what a wide view shows: prop types, visible pieces, depth layers, practical lights, atmosphere, details
    res["issues"]       [{"level": "block"|"warn", "code", "object", "detail"}]

It builds one acceleration structure of every visible mesh (glass, light shafts and dust excluded: they do not stop a ray), then:
  * casts a grid of rays from the wide camera (frustum + occlusion), plus a ray at the centre of every piece, to find which
    pieces are really seen; counts their types, which of the four depth layers have something in them, the practical lights
    in frame, the atmosphere elements and the readable details (signs, banners, papers);
  * checks floating (lowest point more than float_tolerance_m above what is under it) and sunk objects, pieces that intersect
    each other or push through a wall, meshes with no material or a stand-in where a scan was expected, zero-area and
    flipped-normal geometry on visible pieces, rays from the cameras that leave the set and hit nothing (the void), and doors
    and windows with nothing behind them.
It reads its thresholds from style/style.json > sets and judges against them. It changes nothing in the scene.
"""
from __future__ import annotations

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import core

SHEET_TYPES = ("MESH", "FONT", "CURVE", "SURFACE")
FLAT_OK = {"rug", "carpet_runner", "floor_inlay", "floor_detail", "street", "plaza", "ceiling_beams", "ceiling_panel", "rock", "tree", "skyline", "treeline", "house_front", "ground"}   # contact is by design (rugs, rocks bedded in the ground)
NO_FLOAT_KINDS = {"wall", "wall_piece"}
LAYER_NAMES = ("foreground", "mid", "background", "beyond")


# ----------------------------------------------------------------------------- scene to arrays
def _root_of(ob):
    """The piece an object belongs to: the nearest ancestor (or itself) carrying sk_type; else the top of its chain."""
    o = ob
    while True:
        if "sk_type" in o.keys():
            return o
        if o.parent is None:
            return o
        o = o.parent


def _skip(ob) -> bool:
    if ob.type not in SHEET_TYPES or ob.hide_render or ob.hide_viewport:
        return True
    if ob.get("sk_kind") == "standin" or ob.get("sk_role") in ("atmosphere",):
        return True
    if any(c.name == "FX" for c in ob.users_collection):
        return True
    for m in getattr(ob.data, "materials", []):
        if m is not None and (m.name.startswith("SURF_glass") or m.name.startswith("SK_vista_glass")):
            return True
    return False


class World:
    """Evaluated geometry of the scene as numpy arrays plus a BVH of everything a ray can hit."""

    def __init__(self):
        dg = bpy.context.evaluated_depsgraph_get()
        self.objs: list = []
        V, T, O = [], [], []
        base = 0
        self.tris_by_obj: list = []
        for ob in bpy.context.scene.objects:
            if _skip(ob):
                continue
            ev = ob.evaluated_get(dg)
            try:
                me = ev.to_mesh()
            except RuntimeError:
                continue
            if me is None or not len(me.polygons):
                ev.to_mesh_clear()
                continue
            me.calc_loop_triangles()
            nv, nt = len(me.vertices), len(me.loop_triangles)
            co = np.empty(nv * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            tri = np.empty(nt * 3, dtype=np.int64)
            me.loop_triangles.foreach_get("vertices", tri)
            m = np.array(ob.matrix_world, dtype=np.float64)
            w = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
            oi = len(self.objs)
            self.objs.append(ob)
            V.append(w)
            T.append(tri.reshape(-1, 3) + base)
            O.append(np.full(nt, oi, dtype=np.int64))
            self.tris_by_obj.append((base, nv, len(T[-1])))
            base += nv
            ev.to_mesh_clear()
        self.V = np.concatenate(V) if V else np.zeros((0, 3))
        self.T = np.concatenate(T) if T else np.zeros((0, 3), dtype=np.int64)
        self.owner = np.concatenate(O) if O else np.zeros((0,), dtype=np.int64)
        self.bvh = BVHTree.FromPolygons(self.V.tolist(), self.T.tolist(), epsilon=0.0) if len(self.T) else None
        self.roots = [_root_of(o) for o in self.objs]
        self.n_tris = int(len(self.T))

    def cast(self, origin, direction, ignore_root=None, max_hops: int = 8):
        """First hit: (location, distance, object_index, normal) or None. Hits belonging to ignore_root are stepped through."""
        o = Vector(origin)
        d = Vector(direction).normalized()
        travelled = 0.0
        for _ in range(max_hops):
            loc, nrm, idx, dist = self.bvh.ray_cast(o, d)
            if idx is None:
                return None
            oi = int(self.owner[idx])
            if ignore_root is not None and self.roots[oi] is ignore_root:
                o = loc + d * 1e-4
                travelled += dist + 1e-4
                continue
            return loc, travelled + dist, oi, nrm
        return None


# ----------------------------------------------------------------------------- cameras
def _cam(c):
    if isinstance(c, dict):
        return Vector(c["pos"]), Vector(c["aim"]), float(c.get("lens", 28.0)), c.get("name", "cam")
    if hasattr(c, "matrix_world"):
        m = c.matrix_world
        return m.translation.copy(), m.translation + (m.to_3x3() @ Vector((0, 0, -1))), float(c.data.lens), c.name
    pos, aim, lens = c[:3]
    return Vector(pos), Vector(aim), float(lens), "cam"


class Frame:
    def __init__(self, pos, aim, lens):
        sc = bpy.context.scene
        self.pos = Vector(pos)
        f = (Vector(aim) - self.pos).normalized()
        r = f.cross(Vector((0, 0, 1)))
        r = r.normalized() if r.length > 1e-6 else Vector((1, 0, 0))
        self.f, self.r, self.u = f, r, r.cross(f).normalized()
        asp = sc.render.resolution_x / sc.render.resolution_y
        self.tv = 18.0 / lens
        self.th = self.tv * asp if asp < 1 else self.tv

    def ray(self, u: float, v: float) -> Vector:
        return (self.f + self.r * u * self.th + self.u * v * self.tv).normalized()

    def project(self, p):
        """(u, v, depth) of a world point; u, v in -1..1 inside the frame."""
        d = Vector(p) - self.pos
        z = d.dot(self.f)
        if z <= 1e-4:
            return None
        return d.dot(self.r) / z / self.th, d.dot(self.u) / z / self.tv, z


# ----------------------------------------------------------------------------- the audit
def audit(cams, room=None, exterior: bool = False, interior: bool | None = None, thresholds: dict | None = None, nx: int = 54, ny: int = 96, wide_index: int = 0) -> dict:
    th = dict(core.STYLE.get("sets", {}))
    th.update(thresholds or {})
    interior = (room is not None) if interior is None else interior
    bpy.context.view_layer.update()
    W = World()
    cs = [_cam(c) for c in cams]
    issues: list = []
    wide = Frame(*cs[wide_index][:3])
    stats = {"triangles": W.n_tris, "mesh_objects": len(W.objs)}

    # ---- visibility from the wide camera
    hits: dict = {}
    depths: dict = {}
    all_depth = []
    for j in range(ny):
        for i in range(nx):
            u, v = (i + 0.5) / nx * 2 - 1, (j + 0.5) / ny * 2 - 1
            h = W.cast(wide.pos, wide.ray(u, v))
            if h is None:
                continue
            r = W.roots[h[2]]
            hits[r] = hits.get(r, 0) + 1
            z = (h[0] - wide.pos).dot(wide.f)
            depths.setdefault(r, []).append(z)
            all_depth.append(z)
    visible = {r for r, n in hits.items() if n >= 2}
    pieces = [o for o in bpy.context.scene.objects if "sk_type" in o.keys() and o.get("sk_kind") != "standin" and not o.hide_render]
    for r in pieces:                                                      # a ray at the middle of each piece finds the small ones the grid missed
        if r in visible:
            continue
        try:
            lo, hi = _root_bbox(r, W)
        except ValueError:
            continue
        for p in (((lo + hi) / 2), Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z - 0.01)), Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + 0.01))):
            pr = wide.project(p)
            if pr is None or abs(pr[0]) > 1 or abs(pr[1]) > 1:
                continue
            h = W.cast(wide.pos, p - wide.pos)
            if h is not None and (W.roots[h[2]] is r or (h[0] - p).length < 0.15):
                visible.add(r)
                break
    prop_roots = [r for r in visible if r.get("sk_kind") == "prop"]
    types = {}
    for r in prop_roots:
        types[r["sk_type"]] = types.get(r["sk_type"], 0) + 1
    d95 = float(np.percentile(all_depth, 95)) if all_depth else 1.0
    layers = {k: 0 for k in LAYER_NAMES}
    bnds = _bounds(room)
    for r in prop_roots:
        z = float(np.median(depths[r])) if r in depths else _centre_depth(r, wide)
        lay = r.get("sk_layer")
        c = _root_centre(r)
        if r["sk_type"] in ("skyline", "treeline") or r.get("sk_layer") == "beyond" or (bnds and not _in(bnds, c, 0.3)):
            layers["beyond"] += 1
        elif z < 0.3 * d95:
            layers["foreground"] += 1
        elif z < 0.62 * d95:
            layers["mid"] += 1
        else:
            layers["background"] += 1
    beyond_hits = sum(n for r, n in hits.items() if "sk_vista" in r.keys() or r.get("sk_type") in ("skyline", "treeline") or any(c.get("sk_vista") for c in r.children_recursive))
    if beyond_hits >= 6:
        layers["beyond"] = max(layers["beyond"], 1)
    # lights in frame
    lights_all = [o for o in bpy.context.scene.objects if o.type == "LIGHT" and o.data.type != "SUN" and o.get("sk_role", "practical") == "practical" and not o.hide_render]
    pr_vis = 0
    for lo in lights_all:
        root = _root_of(lo)
        if root in visible:
            pr_vis += 1
            continue
        p = lo.matrix_world.translation
        pj = wide.project(p)
        if pj and abs(pj[0]) < 1.1 and abs(pj[1]) < 1.1:
            pr_vis += 1
    atmos = sorted({o.get("sk_atmo") for o in bpy.context.scene.objects if o.get("sk_role") == "atmosphere" and not o.hide_render and o.get("sk_atmo")} | ({"haze"} if bpy.data.objects.get("HAZE") else set()))
    details = [r for r in visible if r.get("sk_detail")]
    inv = {
        "prop_types": len(types), "types": dict(sorted(types.items())), "objects_visible": len(prop_roots), "pieces_visible_all": len(visible),
        "layers": layers, "practicals_visible": pr_vis, "practicals_total": len(lights_all), "atmosphere": atmos, "details": len(details),
        "detail_objects": sorted({r["sk_type"] for r in details}), "triangles": W.n_tris, "mesh_objects": len(W.objs),
    }

    def add(level, code, obj, detail):
        issues.append({"level": level, "code": code, "object": getattr(obj, "name", str(obj)), "detail": detail})

    # ---- thresholds
    if len(types) < th.get("min_prop_types_wide", 14):
        add("block", "few_prop_types", "wide", f"{len(types)} distinct prop types in the wide view, need {th.get('min_prop_types_wide', 14)}")
    if len(prop_roots) < th.get("min_objects_wide", 60):
        add("block", "few_objects", "wide", f"{len(prop_roots)} objects in the wide view, need {th.get('min_objects_wide', 60)}")
    pop = [k for k in LAYER_NAMES if layers[k] > 0]
    if len(pop) < th.get("layers_required", 4):
        add("block", "layers_missing", "wide", f"depth layers populated: {', '.join(pop) or 'none'}; missing {', '.join(k for k in LAYER_NAMES if k not in pop)}")
    if interior and pr_vis < th.get("min_practicals_interior", 3):
        add("block", "few_practicals", "wide", f"{pr_vis} practical lights in frame, need {th.get('min_practicals_interior', 3)}")
    if len(atmos) < th.get("min_atmosphere", 1):
        add("block", "no_atmosphere", "scene", "no haze, dust or light shaft in the set")
    if len(details) < th.get("min_details", 3):
        add("block", "few_details", "wide", f"{len(details)} readable details in frame (signs, banners, papers, boards), need {th.get('min_details', 3)}")

    # ---- per-piece defects
    tol = th.get("float_tolerance_m", 0.02)
    infos = {}
    for r in pieces:
        if r.get("sk_kind") == "shell":
            continue
        try:
            lo, hi = _root_bbox(r, W)
        except ValueError:
            continue
        infos[r] = (lo, hi)
        t = r.get("sk_type", "")
        if t in FLAT_OK or r.get("sk_mount") or r.get("sk_hang") or r.get("sk_piece_kind") in NO_FLOAT_KINDS or t in ("banner", "tapestry"):
            continue
        if r.get("sk_on"):                                                    # small things on a table: measured against the table top they were set on
            par = bpy.data.objects.get(r["sk_on"])
            g = None
            if par is not None and par.get("sk_tops"):
                tz = [par.location.z + t_["z"] for t_ in par["sk_tops"]]
                g = lo.z - min(tz, key=lambda z_: abs(z_ - lo.z))
        else:
            g = _float_gap(W, r, lo)
        if g is None:
            continue
        if g > tol:
            add("block", "floating", r, f"{t}: lowest point {g * 100:.1f} cm above what is under it")
        elif g < -tol:
            add("block", "sunk", r, f"{t}: sunk {-g * 100:.1f} cm into what it stands on")
    # intersections between pieces, and pieces through walls
    walls = [(o, _bbox_obj(o)) for o in bpy.context.scene.objects if o.get("sk_type") == "wall" and not o.hide_render]
    keys = [r for r in infos if r.get("sk_type") not in FLAT_OK and not r.get("sk_mount")]
    seen = set()
    for a_i, a in enumerate(keys):
        la, ha = infos[a]
        for b in keys[a_i + 1:]:
            lb, hb = infos[b]
            pen = _pen(la, ha, lb, hb)
            if pen is None or pen < 0.02:
                continue
            if a.get("sk_on") == b.name or b.get("sk_on") == a.name:
                continue
            if _bvh_overlap(W, a, b):
                key = tuple(sorted((a.name, b.name)))
                if key in seen:
                    continue
                seen.add(key)
                add("block" if pen > 0.04 else "warn", "intersect", a, f"{a.get('sk_type')} intersects {b.get('sk_type')} ({b.name}) by about {pen * 100:.0f} cm")
        for wo, (wl, wh) in walls:
            pen = _pen(la, ha, wl, wh)
            if pen is not None and pen > 0.04 and _bvh_overlap(W, a, wo, root_b=wo):
                add("block", "through_wall", a, f"{a.get('sk_type')} pushes through {wo.name} by about {pen * 100:.0f} cm")
    # materials and geometry on visible pieces
    cat = _catalog()
    mat_seen = set()
    for oi, ob in enumerate(W.objs):
        if ob.type != "MESH":
            continue
        ms = [m for m in ob.data.materials]
        if not ms or all(m is None for m in ms):
            add("block", "no_material", ob, "mesh has no material")          # anywhere in the set: it renders as default grey in some shot
        if W.roots[oi] not in visible:
            continue
        for m in ms:
            if m is None or m.name in mat_seen:
                continue
            mat_seen.add(m.name)
            sn = m.get("sk_surface")
            if sn and str(m.get("sk_source", "")).startswith("procedural") and cat.get(sn, {}).get("ambientcg"):
                add("warn", "stand_in", ob, f"surface '{sn}' is a procedural stand-in; its scan {cat[sn]['ambientcg'][0]} is not downloaded")
        _geometry_checks(W, oi, ob, add)
    # ---- the void: cameras inside the set must not see out of it
    for name_i, (pos, aim, lens, cname) in enumerate(cs):
        if bnds and not _in(bnds, pos, 0.05):
            continue                                                       # a camera outside the room sees a cutaway, not a void
        fr = Frame(pos, aim, lens)
        misses = 0
        first = None
        for j in range(30):
            for i in range(17):
                u, v = (i + 0.5) / 17 * 2 - 1, (j + 0.5) / 30 * 2 - 1
                d = fr.ray(u, v)
                if exterior and d.z > -0.03:                          # sky and the horizon band are not a void outdoors
                    continue
                if W.cast(pos, d) is None:
                    misses += 1
                    first = first or (u, v, d)
        if misses:
            add("block", "void", cname if cname != "cam" else f"camera {name_i}", f"{misses} of 510 view rays leave the set and hit nothing (first at frame u={first[0]:+.2f} v={first[1]:+.2f}, direction ({first[2].x:+.2f}, {first[2].y:+.2f}, {first[2].z:+.2f}))")
    if room is not None:
        for oid, hd in room.openings.items():
            if hd.get("kind") not in ("door", "window", "gap"):
                continue
            c, n = Vector(hd["inner_centre"]), Vector(hd["normal"])
            bad = 0
            for dx, dz in ((0, 0), (0.3, 0.3), (-0.3, 0.3), (0.3, -0.3), (-0.3, -0.3)):
                side = n.cross(Vector((0, 0, 1))).normalized()
                p = c + n * 0.4 + side * dx * hd["w"] / 2 + Vector((0, 0, dz * hd["h"] / 2))
                if W.cast(p, -n) is None:
                    bad += 1
            if bad:
                add("block", "opening_void", oid, f"{hd['kind']} '{oid}' on wall {hd['wall']}: {bad} of 5 rays through it hit nothing (add arch.vista or something behind it)")
    blocks = [i for i in issues if i["level"] == "block"]
    return {"inventory": inv, "issues": issues, "stats": stats, "thresholds": th, "ok": not blocks}


# ----------------------------------------------------------------------------- helpers
def _catalog():
    from . import mat
    try:
        return mat.catalog()
    except Exception:
        return {}


def _bounds(room):
    if room is None:
        return None
    return (room.lo[0], room.lo[1], 0.0, room.hi[0], room.hi[1], room.h + room.rise if hasattr(room, "rise") and room.rise else room.h)


def _in(b, p, pad: float = 0.0) -> bool:
    return b[0] - pad <= p[0] <= b[3] + pad and b[1] - pad <= p[1] <= b[4] + pad and b[2] - 0.5 <= p[2] <= b[5] + pad


def _bbox_obj(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))), Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))


def _root_bbox(root, W: World):
    idx = [i for i, r in enumerate(W.roots) if r is root]
    if not idx:
        raise ValueError("no geometry")
    lo = np.array([1e9] * 3)
    hi = np.array([-1e9] * 3)
    for i in idx:
        base, nv, _ = W.tris_by_obj[i]
        v = W.V[base:base + nv]
        lo = np.minimum(lo, v.min(axis=0))
        hi = np.maximum(hi, v.max(axis=0))
    return Vector(lo), Vector(hi)


def _root_centre(root) -> Vector:
    return root.matrix_world.translation.copy() + Vector((0, 0, 0))


def _centre_depth(root, fr: Frame) -> float:
    pr = fr.project(_root_centre(root))
    return pr[2] if pr else 0.0


def _pen(la, ha, lb, hb):
    ext = [min(ha[i], hb[i]) - max(la[i], lb[i]) for i in range(3)]
    return min(ext) if min(ext) > 0 else None


def _float_gap(W: World, root, lo):
    """Gap between a piece's lowest points and the surface it stands on: positive = floating, negative = sunk, None = unmeasurable.
    Samples a few of the lowest vertices; each is probed 3 cm outside the piece in four directions (so the piece's own faces are
    not in the way): a ray up from the bottom plane that leaves a solid means the support's top is above the bottom (sunk), else a
    ray down from just above the bottom finds the surface below. The highest support found is the one the piece stands on."""
    idx = [i for i, r in enumerate(W.roots) if r is root]
    pts = []
    for i in idx:
        base, nv, _ = W.tris_by_obj[i]
        v = W.V[base:base + nv]
        low = v[v[:, 2] < lo.z + 0.012]
        pts.extend(low.tolist())
    if not pts:
        return None
    step = max(1, len(pts) // 5)
    gaps = []
    for p in pts[::step][:5]:
        best = None
        for dx, dy in ((0.03, 0), (-0.03, 0), (0, 0.03), (0, -0.03)):
            q = Vector((p[0] + dx, p[1] + dy, lo.z))
            up = W.cast(q, Vector((0, 0, 1)), ignore_root=root)
            if up is not None and up[3].z > 0.2 and up[1] < 0.5:        # the ray left a solid going up: the bottom is inside it
                z = q.z + up[1]
            else:
                dn = W.cast(Vector((q.x, q.y, lo.z + 0.03)), Vector((0, 0, -1)), ignore_root=root)
                z = dn[0].z if dn is not None else None
            if z is not None and (best is None or z > best):
                best = z
        if best is not None:
            gaps.append(lo.z - best)
    if not gaps:
        return None
    return float(np.median(gaps))


def _bvh_overlap(W: World, a, b, root_b=None) -> bool:
    ia = [i for i, r in enumerate(W.roots) if r is a]
    ib = [i for i, r in enumerate(W.roots) if (r is b if root_b is None else W.objs[i] is root_b)]
    if not ia or not ib:
        return False
    ta = np.concatenate([np.arange(*_tri_range(W, i)) for i in ia])
    tb = np.concatenate([np.arange(*_tri_range(W, i)) for i in ib])
    A = BVHTree.FromPolygons(W.V.tolist(), W.T[ta].tolist(), epsilon=0.0)
    B = BVHTree.FromPolygons(W.V.tolist(), W.T[tb].tolist(), epsilon=0.0)
    return len(A.overlap(B)) > 0


def _tri_range(W: World, i):
    start = int(np.searchsorted(W.owner, i, side="left"))
    end = int(np.searchsorted(W.owner, i, side="right"))
    return start, end


def _geometry_checks(W: World, oi: int, ob, add):
    start, end = _tri_range(W, oi)
    if end <= start:
        return
    T = W.T[start:end]
    V = W.V
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    cr = np.cross(b - a, c - a)
    area = np.linalg.norm(cr, axis=1) * 0.5
    zero = int((area < 1e-9).sum())
    if zero:
        add("block" if zero > 0.25 * len(T) else "warn", "zero_area", ob, f"{zero} of {len(T)} triangles have no area")
    # closed volume sign: a closed mesh with negative volume has its normals inside out
    vol = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    me = ob.data
    if vol < -1e-4 and ob.type == "MESH":
        edges = {}
        for p in me.polygons:
            vs = p.vertices
            for k in range(len(vs)):
                e = tuple(sorted((vs[k], vs[(k + 1) % len(vs)])))
                edges[e] = edges.get(e, 0) + 1
        if all(n == 2 for n in edges.values()):
            add("block", "flipped_normals", ob, f"closed mesh with negative volume ({vol:.3f} m3): normals point inward")
    if ob.type == "MESH" and len(me.polygons) < 3000:
        counts = {}
        for p in me.polygons:
            vs = p.vertices
            for k in range(len(vs)):
                e = tuple(sorted((vs[k], vs[(k + 1) % len(vs)])))
                counts[e] = counts.get(e, 0) + 1
        nm = sum(1 for n in counts.values() if n > 2)
        if nm and nm > 0.02 * len(counts):
            add("warn", "non_manifold", ob, f"{nm} edges shared by more than two faces")
