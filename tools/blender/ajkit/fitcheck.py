# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/fitcheck.py (Aj pack, 2026-11-26).
# Unchanged: not one line of the pack copy is edited (tools/tests/cast/test_fit_limits.py compares the code and the
# limit constants with the pack original and fails on any difference).
"""Automatic clothing-fit check and the 'hide skin under clothes' mask. See scripts/FITCHECK.md.

Order (fixed, so the mask can never hide a bad fit):
  1. rest_check()   on the UNMASKED body: skin through cloth, cloth floating or tight compared with how it sat on
                    the asset's own body, stretched or ragged edges.
  2. build_mask()   hides body faces well inside the covered area (inset from every garment opening).
  3. pose_check()   on the MASKED body in a set of poses: skin through cloth, hidden skin exposed (a hollow gap),
                    cloth stretch against the fitted rest shape.
All measurements use the evaluated (deformed) meshes and real surface tests (triangle/triangle crossings and
rays against triangles), not vertex-to-vertex distances. Every failure names the garment, the body part and the
place, so an agent can act on the report without anyone pointing at the picture.

A garment must carry two vertex attributes written by the fitter: `fit_asset_co` (its vertex positions on the
asset's body) and `fit_asset_clear` (its distance to the asset's body there)."""
import bpy, math
import numpy as np
from mathutils import Vector, Euler
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

P = "mixamorig:"
MASK_ATTR = "under_clothes"
MASK_MOD = "HideUnderClothes"
# Owner-approved 2026-11-26 (the only exception to the limits below): body faces that the build hides INSIDE A BOOT
# on purpose are not counted as skin crossing or showing through cloth. The build marks them with the face attribute
# BOOT_ATTR and hides them with the modifier BOOT_MOD; both must be present or nothing is excused. All other checks
# (clearance, floating, stretch, hollow gaps) still see these faces.
BOOT_ATTR = "in_boot"
BOOT_MOD = "HideInBoot"

LIMITS = dict(
    # ---- rest pose, unmasked body
    rest_crossings=0,              # body triangles crossing cloth triangles
    rest_skin_through_mm=0.5,      # deepest skin standing in front of cloth
    rest_skin_through_mm2=5.0,     # area of skin in front of cloth
    rest_min_clearance_mm=1.5,     # cloth vertex to skin, at least
    float_abs_mm=10.0,             # cloth may stand off at most max(float_abs, float_rel x asset clearance) more than
    float_rel=0.6,                 #   it did on the asset's body
    float_cluster=3,               # ...judged on connected groups of at least this many vertices
    misplace_s=0.30,               # cloth lying on the body may shift this far along it, in bone lengths, from where it
    misplace_cluster=5,            #   sat on the asset (connected groups of at least this many vertices)
    edge_ratio=(0.5, 2.0),         # edge length against the asset, relative to the cloth around it
    edge_share=0.01,               # share of edges allowed outside edge_ratio
    kink_deg=50.0,                 # change of angle along an open edge (hem, neckline, armhole) against the asset
    kink_share=0.02,
    # ---- poses, masked body
    pose_skin_through_mm=3.0,      # deepest skin in front of cloth
    pose_skin_count_mm=1.0,        # skin counts towards the area below once it stands this far in front
    pose_skin_through_mm2=300.0,
    pose_hole_mm2=20.0,            # hidden skin with no cloth in front of it
    pose_stretch=(0.5, 1.8),       # edge length against the fitted rest shape
    pose_stretch_share=0.05,       # share of the cloth (by edge length) allowed outside that; a deep sit folds the lap
    # ---- mask
    mask_inset_m=0.045,            # hidden faces stay this far from every garment opening
    mask_cover_m=0.08,             # cloth counts as covering skin when it is within this distance in front of it
)


# ------------------------------------------------------------------------------------------------ skeleton
JOINT_AFTER = {"Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "Neck": "Head",
               "LeftShoulder": "LeftArm", "LeftArm": "LeftForeArm", "LeftForeArm": "LeftHand",
               "RightShoulder": "RightArm", "RightArm": "RightForeArm", "RightForeArm": "RightHand",
               "LeftUpLeg": "LeftLeg", "LeftLeg": "LeftFoot", "RightUpLeg": "RightLeg", "RightLeg": "RightFoot"}
CHAINS = [["Hips", "Spine", "Spine1", "Spine2", "Neck"], ["LeftShoulder", "LeftArm", "LeftForeArm"],
          ["RightShoulder", "RightArm", "RightForeArm"], ["LeftUpLeg", "LeftLeg"], ["RightUpLeg", "RightLeg"]]


def bone_axes(armature, posed=False):
    """{bone: (start, end)} in world space. A bone runs from its joint to the next joint of its chain (not to
    Blender's display tail); a chain's last bone uses its tail when the rig has no further joint."""
    if posed:
        pos = {b.name.split(":")[-1]: (armature.matrix_world @ b.head, armature.matrix_world @ b.tail) for b in armature.pose.bones}
    else:
        pos = {b.name.split(":")[-1]: (armature.matrix_world @ b.head_local, armature.matrix_world @ b.tail_local)
               for b in armature.data.bones}
    ax = {}
    for n, nxt in JOINT_AFTER.items():
        if n not in pos:
            continue
        h = np.array(pos[n][0]); e = np.array(pos[nxt][0]) if nxt in pos else np.array(pos[n][1])
        ax[n] = (h, e)
    return ax


def chain_address(pts, axes, chain=None):
    """Where along the body a point sits: (chain index, s). s counts bones along the chain: 0 at the chain's first
    joint, 1 at the second, and so on (it may run past either end). With `chain` given, s is measured on those
    chains; otherwise each point takes the chain whose bones it is nearest to."""
    pts = np.asarray(pts, float)
    best_d = np.full(len(pts), np.inf); best_c = np.zeros(len(pts), dtype=int)
    S = np.zeros((len(CHAINS), len(pts)))
    for ci, names in enumerate(CHAINS):
        names = [n for n in names if n in axes]
        dmin = np.full(len(pts), np.inf); s = np.zeros(len(pts))
        for k, n in enumerate(names):
            h, e = axes[n]; w = e - h; L2 = max(float(w @ w), 1e-12)
            t = ((pts - h) @ w) / L2
            lo = -np.inf if k == 0 else 0.0
            hi = np.inf if k == len(names) - 1 else 1.0
            tc = np.clip(t, 0.0, 1.0)
            d = np.linalg.norm(pts - (h + np.outer(tc, w)), axis=1)
            upd = d < dmin
            dmin[upd] = d[upd]; s[upd] = k + np.clip(t, lo, hi)[upd]
        S[ci] = s
        u = dmin < best_d
        best_d[u] = dmin[u]; best_c[u] = ci
    if chain is None:
        chain = best_c
    chain = np.asarray(chain, dtype=int)
    return chain, S[chain, np.arange(len(pts))]


def weld_map(co, tol=1e-5):
    """Vertices that share a position (split seams) are one point of the cloth: index of a representative."""
    kd = KDTree(len(co))
    for i, p in enumerate(co):
        kd.insert(p, i)
    kd.balance()
    rep = np.arange(len(co))
    for i, p in enumerate(co):
        if rep[i] != i:
            continue
        for (_, j, _) in kd.find_range(p, tol):
            if j > i:
                rep[j] = i
    return rep


def open_edges(ob, ref_co):
    """Edges on a real opening of the garment (hem, neckline, armhole): used by one face only, counting split
    seams as closed. ref_co: the positions that define which vertices coincide."""
    rep = weld_map(ref_co)
    cnt = {}; first = {}
    for p in ob.data.polygons:
        for a, b in p.edge_keys:
            k = (int(min(rep[a], rep[b])), int(max(rep[a], rep[b])))
            if k[0] == k[1]:
                continue
            cnt[k] = cnt.get(k, 0) + 1; first.setdefault(k, (a, b))
    return [first[k] for k, c in cnt.items() if c == 1]


# ------------------------------------------------------------------------------------------------ meshes
def _eval(ob):
    """World-space evaluated mesh: vertices, triangles, triangle->polygon, triangle normals, triangle areas."""
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    oe = ob.evaluated_get(dg); me = oe.data
    me.calc_loop_triangles()
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get("co", co)
    M = np.array(oe.matrix_world)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    nt = len(me.loop_triangles)
    tri = np.empty(nt * 3, dtype=np.int32); me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(-1, 3)
    tp = np.empty(nt, dtype=np.int32); me.loop_triangles.foreach_get("polygon_index", tp)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    cr = np.cross(b - a, c - a)
    area = np.linalg.norm(cr, axis=1) / 2
    nrm = cr / np.maximum(np.linalg.norm(cr, axis=1), 1e-12)[:, None]
    ib = np.zeros(len(me.polygons), dtype=bool)                   # the build's in-boot flag, carried through modifiers
    at = me.attributes.get(BOOT_ATTR)
    if at is not None and at.domain == "FACE" and ob.modifiers.get(BOOT_MOD) is not None:
        at.data.foreach_get("value", ib)
    return {"co": co, "tri": tri, "tp": tp, "nrm": nrm, "area": area, "cen": (a + b + c) / 3, "npoly": len(me.polygons),
            "in_boot": ib[tp]}


def _bvh(m):
    return BVHTree.FromPolygons([Vector(p) for p in m["co"]], [tuple(t) for t in m["tri"]])


def _attr(ob, name, width):
    a = ob.data.attributes.get(name)
    if a is None:
        return None
    v = np.empty(len(ob.data.vertices) * width)
    a.data.foreach_get("vector" if width == 3 else "value", v)
    return v.reshape(-1, 3) if width == 3 else v


def boot_hidden(body):
    """Per body polygon: hidden inside a boot on purpose by the build (owner-approved exception, 2026-11-26)."""
    a = body.data.attributes.get(BOOT_ATTR)
    if a is None or a.domain != "FACE" or body.modifiers.get(BOOT_MOD) is None:
        return np.zeros(len(body.data.polygons), dtype=bool)
    v = np.zeros(len(body.data.polygons), dtype=bool); a.data.foreach_get("value", v)
    return v


def _boot_mod(body, on):
    m = body.modifiers.get(BOOT_MOD)
    if m is not None:
        m.show_viewport = m.show_render = bool(on)
        bpy.context.view_layer.update()


def set_mask(body, on):
    m = body.modifiers.get(MASK_MOD)
    if m:
        m.show_viewport = m.show_render = bool(on)
    bpy.context.view_layer.update()
    return m is not None


class Where:
    """Names a place on the body: which bone's skin it is on, which side, front or back, and the height."""

    def __init__(self, body, arm):
        keep = set_mask(body, False)
        m = _eval(body)
        self.co = m["co"]
        names = {g.index: g.name.split(":")[-1] for g in body.vertex_groups}
        dom = []
        for v in body.data.vertices:
            best = max(v.groups, key=lambda g: g.weight) if v.groups else None
            dom.append(names[best.group] if best else "")
        self.dom = dom
        self.kd = KDTree(len(self.co))
        for i, p in enumerate(self.co):
            self.kd.insert(p, i)
        self.kd.balance()
        hips = arm.matrix_world @ arm.pose.bones[P + "Hips"].head
        self.cx, self.cy = hips.x, hips.y
        if keep:
            set_mask(body, True)

    def __call__(self, p):
        _, i, _ = self.kd.find(Vector(p))
        side = "left" if p[0] - self.cx > 0.02 else ("right" if p[0] - self.cx < -0.02 else "centre")
        fb = "front" if p[1] - self.cy < 0 else "back"
        return {"body_part": self.dom[i], "side": side, "face": fb, "xyz_m": [round(float(x), 3) for x in p]}


def _clusters(points, values, where, radius=0.035, top=6):
    """Group failing points that lie together; report the worst groups."""
    if len(points) == 0:
        return []
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(p, i)
    kd.balance()
    lab = -np.ones(len(points), dtype=int); k = 0
    for i in range(len(points)):
        if lab[i] >= 0:
            continue
        stack = [i]; lab[i] = k
        while stack:
            j = stack.pop()
            for (_, q, _) in kd.find_range(points[j], radius):
                if lab[q] < 0:
                    lab[q] = k; stack.append(q)
        k += 1
    out = []
    for c in range(k):
        m = lab == c
        w = int(np.argmax(values[m])); pw = points[m][w]
        e = where(pw); e.update({"points": int(m.sum()), "worst": round(float(values[m].max()), 2)})
        out.append(e)
    out.sort(key=lambda e: -e["worst"] * math.sqrt(e["points"]))
    return out[:top]


# ------------------------------------------------------------------------------------------------ surface tests
def _directions(n):
    """The normal and 22 directions spread over the half-space in front of a surface point (out to 80 degrees)."""
    n = Vector(n); t1 = n.orthogonal().normalized(); t2 = n.cross(t1)
    out = [n]
    for tilt, count in ((35, 6), (60, 8), (80, 8)):
        ct, st = math.cos(math.radians(tilt)), math.sin(math.radians(tilt))
        for k in range(count):
            a = 2 * math.pi * k / count
            out.append((n * ct + (t1 * math.cos(a) + t2 * math.sin(a)) * st).normalized())
    return out


def can_be_seen(p, n, cloth_bvh, skin_bvh):
    """True when some line from this skin point reaches open space without meeting cloth or visible skin."""
    p = Vector(p)
    for d in _directions(n):
        o = p + d * 1e-3
        if cloth_bvh.ray_cast(o, d, 3.0)[0] is None and skin_bvh.ray_cast(o, d, 3.0)[0] is None:
            return True
    return False


def _cloth_bvh(gms):
    allv = np.concatenate([m["co"] for m in gms]); tris = []; off = 0
    for m in gms:
        tris += [tuple(int(x) + off for x in t) for t in m["tri"]]; off += len(m["co"])
    return BVHTree.FromPolygons([Vector(p) for p in allv], tris)


def _write_mask(body, flags):
    me = body.data
    att = me.attributes.get(MASK_ATTR)
    if att is None or att.domain != "FACE" or att.data_type != "BOOLEAN":
        if att is not None:
            me.attributes.remove(att)
        att = me.attributes.new(MASK_ATTR, "BOOLEAN", "FACE")
    att.data.foreach_set("value", [bool(x) for x in flags])
    me.update()


def _unsee(body, flags, um, cloth):
    """Clear the flag of every hidden face that can be seen in the current pose. um: the unmasked evaluated body."""
    flags = np.array(flags, dtype=bool)
    vis_t = ~flags[um["tp"]]
    skin = BVHTree.FromPolygons([Vector(p) for p in um["co"]], [tuple(t) for t in um["tri"][vis_t]])
    cleared = 0
    for i in np.nonzero(~vis_t)[0]:
        if flags[um["tp"][i]] and can_be_seen(um["cen"][i], um["nrm"][i], cloth, skin):
            flags[um["tp"][i]] = False; cleared += 1
    return flags, cleared
def _skin_through(bm, bbvh, gms, cover=0.08):
    """Skin standing in front of cloth. Samples: every body triangle centre. A sample is 'through' when cloth lies
    just beneath it (nearer than the body's own far side) and no cloth lies in front of it."""
    res = {}
    for name, gm, gbvh in gms:
        depth = np.zeros(len(bm["cen"]))
        for i, (p, n) in enumerate(zip(bm["cen"], bm["nrm"])):
            p = Vector(p); n = Vector(n)
            hin = gbvh.ray_cast(p - n * 1e-4, -n, 0.03)
            if hin[0] is None:
                continue
            if gbvh.ray_cast(p + n * 1e-4, n, cover)[0] is not None:
                continue                                           # cloth in front as well: skin is covered
            hself = bbvh.ray_cast(p - n * 2e-4, -n, 0.06)
            if hself[0] is not None and hin[3] > 0.5 * hself[3]:
                continue                                           # that was the cloth on the far side of a thin limb
            depth[i] = hin[3]
        res[name] = depth
    return res


def _crossings(bbvh, bm, gms):
    out = {}
    for name, gm, gbvh in gms:
        pairs = bbvh.overlap(gbvh)
        out[name] = sorted({i for i, _ in pairs})
    return out


def _fail(lst, check, garment, value, limit, unit, where=None):
    lst.append({"check": check, "garment": garment, "value": round(float(value), 2), "limit": limit, "unit": unit,
                "where": where or []})


# ------------------------------------------------------------------------------------------------ 1. rest pose
def rest_check(arm, body, garments, limits=None):
    """Unmasked body, armature in rest position."""
    L = dict(LIMITS, **(limits or {}))
    keep_pp = arm.data.pose_position
    arm.data.pose_position = 'REST'
    had_mask = set_mask(body, False)
    _boot_mod(body, False)
    bpy.context.view_layer.update()
    bm = _eval(body); bbvh = _bvh(bm)
    inboot = bm["in_boot"]                                         # owner-approved boot exception, per triangle
    where = Where(body, arm)
    gms = [(g.name, _eval(g), None) for g in garments]
    gms = [(n, m, _bvh(m)) for n, m, _ in gms]
    R = {"garments": {}, "failures": []}
    F = R["failures"]
    cross = _crossings(bbvh, bm, gms)
    through = _skin_through(bm, bbvh, gms, L["mask_cover_m"])
    for g, (name, gm, gbvh) in zip(garments, gms):
        e = {}
        # --- skin through cloth (faces hidden inside a boot by the build are excused: owner-approved 2026-11-26)
        ci = [i for i in cross[name] if not inboot[i]]
        through[name] = np.where(inboot, 0.0, through[name])
        e["boot_hidden_triangles_excused"] = int(len(cross[name]) - len(ci))
        e["crossing_body_triangles"] = len(ci)
        if len(ci) > L["rest_crossings"]:
            pts = bm["cen"][ci]
            _fail(F, "skin crosses cloth", name, len(ci), L["rest_crossings"], "triangles",
                  _clusters(pts, np.ones(len(pts)), where))
        d = through[name]; m = d * 1000 > L["rest_skin_through_mm"]
        e["skin_through_deepest_mm"] = round(float(d.max() * 1000), 2)
        e["skin_through_mm2"] = round(float(bm["area"][m].sum() * 1e6), 1)
        if d.max() * 1000 > L["rest_skin_through_mm"] or e["skin_through_mm2"] > L["rest_skin_through_mm2"]:
            _fail(F, f"skin shows through cloth ({e['skin_through_mm2']} mm2)", name, d.max() * 1000, L["rest_skin_through_mm"], "mm deep",
                  _clusters(bm["cen"][m], d[m] * 1000, where))
        # --- clearance against the asset
        ca = _attr(g, "fit_asset_clear", 1); a_co = _attr(g, "fit_asset_co", 3)
        co = gm["co"]
        if ca is None or a_co is None or len(ca) != len(co):
            _fail(F, "garment has no fit record (fit_asset_co / fit_asset_clear)", name, 0, 0, "")
            R["garments"][name] = e
            continue
        cb = np.zeros(len(co)); inside = np.zeros(len(co), dtype=bool)
        for i, p in enumerate(co):
            hit, nrm, fi, dist = bbvh.find_nearest(Vector(p))
            cb[i] = dist
            inside[i] = (Vector(p) - hit).dot(nrm) < 0
        cb = np.where(inside, -cb, cb)
        e["min_clearance_mm"] = round(float(cb.min() * 1000), 2)
        tight = cb * 1000 < L["rest_min_clearance_mm"]
        e["tight_vertices"] = int(tight.sum())
        if tight.any():
            _fail(F, "cloth too close to or inside the skin", name, cb.min() * 1000, L["rest_min_clearance_mm"], "mm",
                  _clusters(co[tight], (L["rest_min_clearance_mm"] - cb[tight] * 1000), where))
        allow = np.maximum(L["float_abs_mm"] / 1000, L["float_rel"] * ca)
        extra = cb - ca
        fl = extra > allow
        # connected groups only: a single vertex over the line is not a floating strap
        nb = [[] for _ in range(len(co))]
        for ed in g.data.edges:
            i, j = ed.vertices
            nb[i].append(j); nb[j].append(i)
        seen = np.zeros(len(co), dtype=bool); groups = []
        for i in np.nonzero(fl)[0]:
            if seen[i]:
                continue
            st = [i]; seen[i] = True; grp = []
            while st:
                j = st.pop(); grp.append(j)
                for q in nb[j]:
                    if fl[q] and not seen[q]:
                        seen[q] = True; st.append(q)
            if len(grp) >= L["float_cluster"]:
                groups.append(grp)
        fv = np.array([i for grp in groups for i in grp], dtype=int)
        e["floating_vertices"] = int(len(fv))
        e["floating_worst_extra_mm"] = round(float(extra[fv].max() * 1000), 1) if len(fv) else 0.0
        e["clearance_change_mm"] = {"median": round(float(np.median(extra) * 1000), 1),
                                    "p95": round(float(np.percentile(extra, 95) * 1000), 1)}
        if len(fv):
            _fail(F, "cloth floats off the body (it lay closer on the asset)", name, extra[fv].max() * 1000,
                  L["float_abs_mm"], "mm more than on the asset", _clusters(co[fv], extra[fv] * 1000, where))
        # --- the place on the body: cloth must sit where it sat on the asset (a strap on the shoulder, not the arm)
        a_ch = g.data.attributes.get("fit_asset_chain"); a_s = _attr(g, "fit_asset_s", 1)
        if a_ch is not None and a_s is not None:
            ch = np.empty(len(co), dtype=np.int32); a_ch.data.foreach_get("value", ch)
            _, s_now = chain_address(co, bone_axes(arm), ch)
            ds = np.abs(s_now - a_s)
            near = ca < 0.03                                       # cloth that lies on the body, not a loose flare
            mis = near & (ds > L["misplace_s"])
            seen = np.zeros(len(co), dtype=bool); mv = []
            for i in np.nonzero(mis)[0]:
                if seen[i]:
                    continue
                st = [i]; seen[i] = True; grp = []
                while st:
                    j = st.pop(); grp.append(j)
                    for q in nb[j]:
                        if mis[q] and not seen[q]:
                            seen[q] = True; st.append(q)
                if len(grp) >= L["misplace_cluster"]:
                    mv += grp
            mv = np.array(mv, dtype=int)
            e["misplaced_vertices"] = int(len(mv))
            e["place_shift_bone_lengths"] = {"median": round(float(np.median(ds[near])), 3) if near.any() else 0.0,
                                             "max": round(float(ds[near].max()), 3) if near.any() else 0.0}
            if len(mv):
                _fail(F, "cloth sits at a different place along the body than on the asset", name, ds[mv].max(),
                      L["misplace_s"], "bone lengths", _clusters(co[mv], ds[mv], where))
        # --- edges against the asset
        ed = np.array([e_.vertices[:] for e_ in g.data.edges])
        ed = ed[np.linalg.norm(a_co[ed[:, 0]] - a_co[ed[:, 1]], axis=1) > 0.002] if len(ed) else ed
        if len(ed):
            lo = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
            la = np.maximum(np.linalg.norm(a_co[ed[:, 0]] - a_co[ed[:, 1]], axis=1), 1e-9)
            r = lo / la
            rv = np.zeros(len(co)); cnt = np.zeros(len(co))
            np.add.at(rv, ed[:, 0], r); np.add.at(rv, ed[:, 1], r); np.add.at(cnt, ed[:, 0], 1); np.add.at(cnt, ed[:, 1], 1)
            rv = rv / np.maximum(cnt, 1)
            for _ in range(2):                                     # the usual stretch of the cloth around each vertex
                s = np.zeros(len(co)); np.add.at(s, ed[:, 0], rv[ed[:, 1]]); np.add.at(s, ed[:, 1], rv[ed[:, 0]])
                rv = (rv + s / np.maximum(cnt, 1)) / 2
            rel = r / np.maximum((rv[ed[:, 0]] + rv[ed[:, 1]]) / 2, 1e-9)
            bad = (rel < L["edge_ratio"][0]) | (rel > L["edge_ratio"][1])
            share = float(la[bad].sum() / la.sum())                # by length: a row of tiny button edges is not the cloth
            e["edge_stretch"] = {"median": round(float(np.median(r)), 3), "min": round(float(r.min()), 3),
                                 "max": round(float(r.max()), 3), "uneven_share": round(share, 4)}
            if share > L["edge_share"]:
                mid = (co[ed[bad, 0]] + co[ed[bad, 1]]) / 2
                _fail(F, "cloth unevenly stretched or crumpled against the asset", name, share * 100,
                      L["edge_share"] * 100, "% of edge length", _clusters(mid, np.abs(np.log(rel[bad])) * 10, where))
            # --- open edges (hems, neckline, armholes): kinks that the asset does not have
            be = open_edges(g, a_co)
            bn = {}
            for i, j in be:
                bn.setdefault(int(i), []).append(int(j)); bn.setdefault(int(j), []).append(int(i))
            kv, kp, kl = [], [], []
            for v, ns in bn.items():
                if len(ns) != 2:
                    continue
                def ang(C):
                    u = C[v] - C[ns[0]]; w = C[ns[1]] - C[v]
                    c = (u @ w) / max(np.linalg.norm(u) * np.linalg.norm(w), 1e-12)
                    return math.degrees(math.acos(max(-1.0, min(1.0, c))))
                dlt = abs(ang(co) - ang(a_co))
                kv.append(dlt); kp.append(co[v])
                kl.append((np.linalg.norm(co[v] - co[ns[0]]) + np.linalg.norm(co[ns[1]] - co[v])) / 2)
            kv = np.array(kv); kp = np.array(kp); kl = np.array(kl)
            if len(kv):
                kb = kv > L["kink_deg"]
                kshare = float(kl[kb].sum() / max(kl.sum(), 1e-9))    # by length of edge, so stitches and zips do not count as hems
                e["open_edge"] = {"length_m": round(float(kl.sum()), 3), "kinked_share": round(kshare, 4),
                                  "worst_deg": round(float(kv.max()), 1)}
                if kshare > L["kink_share"]:
                    _fail(F, "ragged open edge (hem, neckline or armhole)", name, kshare * 100, L["kink_share"] * 100,
                          "% of open-edge length", _clusters(kp[kb], kv[kb], where))
        R["garments"][name] = e
    R["pass"] = not F
    if had_mask:
        set_mask(body, True)
    arm.data.pose_position = keep_pp
    bpy.context.view_layer.update()
    return R


# ------------------------------------------------------------------------------------------------ 3. the mask
def _mask_group():
    ng = bpy.data.node_groups.get(MASK_MOD)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(MASK_MOD, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    ng.is_modifier = True
    gi = ng.nodes.new("NodeGroupInput"); go = ng.nodes.new("NodeGroupOutput")
    na = ng.nodes.new("GeometryNodeInputNamedAttribute")
    na.data_type = "BOOLEAN"
    na.inputs["Name"].default_value = MASK_ATTR
    dl = ng.nodes.new("GeometryNodeDeleteGeometry")
    dl.domain = "FACE"; dl.mode = "ALL"
    sel = next(o for o in na.outputs if o.enabled and o.name == "Attribute")
    ng.links.new(gi.outputs[0], dl.inputs["Geometry"])
    ng.links.new(sel, dl.inputs["Selection"])
    ng.links.new(dl.outputs[0], go.inputs[0])
    return ng


def build_mask(arm, body, garments, limits=None, poses=None):
    """Mark the body faces that lie under cloth AND well away from every garment opening, and add the modifier that
    leaves them out of display and render. Nothing is deleted. Thin parts (straps) are never masked: all the skin
    under them is nearer to an opening than the inset."""
    L = dict(LIMITS, **(limits or {}))
    keep_pp = arm.data.pose_position
    arm.data.pose_position = 'REST'
    set_mask(body, False)
    bpy.context.view_layer.update()
    bm = _eval(body)
    me = body.data
    if bm["npoly"] != len(me.polygons):
        raise RuntimeError("the body's evaluated mesh does not match its faces; cannot build the mask")
    gms = [(g.name, _eval(g)) for g in garments]
    # every open edge of every garment, sampled along its length
    open_pts = []
    for g, (name, gm) in zip(garments, gms):
        ref = _attr(g, "fit_asset_co", 3)
        for i, j in open_edges(g, ref if ref is not None and len(ref) == len(gm["co"]) else gm["co"]):
            a, b = gm["co"][i], gm["co"][j]
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                open_pts.append(a + (b - a) * t)
    kd = KDTree(len(open_pts))
    for i, p in enumerate(open_pts):
        kd.insert(p, i)
    kd.balance()
    allv = np.concatenate([m["co"] for _, m in gms])
    tris, off = [], 0
    for _, m in gms:
        tris += [tuple(int(x) + off for x in t) for t in m["tri"]]; off += len(m["co"])
    gbvh = BVHTree.FromPolygons([Vector(p) for p in allv], tris)
    # vertex normals of the body (area-weighted)
    vn = np.zeros_like(bm["co"])
    for k in range(3):
        np.add.at(vn, bm["tri"][:, k], bm["nrm"] * bm["area"][:, None])
    vn /= np.maximum(np.linalg.norm(vn, axis=1), 1e-12)[:, None]

    def covered(p, n):
        p = Vector(p); n = Vector(n)
        return gbvh.ray_cast(p + n * 1e-4, n, L["mask_cover_m"])[0] is not None

    vcov = np.array([covered(p, n) for p, n in zip(bm["co"], vn)])
    vfar = np.array([kd.find(Vector(p))[2] >= L["mask_inset_m"] for p in bm["co"]])
    vok = vcov & vfar
    # one more ring of safety: a vertex counts only if all its neighbours do
    nbr_ok = vok.copy()
    for ed in me.edges:
        i, j = ed.vertices
        if not vok[i]:
            nbr_ok[j] = False
        if not vok[j]:
            nbr_ok[i] = False
    flags = [bool(all(nbr_ok[v] for v in p.vertices)) for p in me.polygons]
    # ...and never a face that can be seen through an opening (up a wide trouser leg, down a loose neckline):
    # first in the rest pose, then in every standard pose
    cleared = {}
    flags, cleared["rest"] = _unsee(body, flags, bm, gbvh)
    arm.data.pose_position = 'POSE'
    for pname, pose in (poses or standard_poses(arm)).items():
        apply_pose(arm, pose)
        um = _eval(body)
        flags, cleared[pname] = _unsee(body, flags, um, _cloth_bvh([_eval(g) for g in garments]))
    _reset(arm)
    flags = [bool(x) for x in flags]
    _write_mask(body, flags)
    m = body.modifiers.get(MASK_MOD)
    if m is None:
        m = body.modifiers.new(MASK_MOD, "NODES")
        m.node_group = _mask_group()
    m.show_viewport = m.show_render = True
    arm.data.pose_position = keep_pp
    bpy.context.view_layer.update()
    tot = sum(p.area for p in me.polygons)
    hid = sum(p.area for p, f in zip(me.polygons, flags) if f)
    return {"hidden_faces": int(sum(flags)), "faces": len(flags), "hidden_share_of_skin": round(hid / tot, 3),
            "faces_kept_visible_because_seen": cleared,
            "covered_vertices": int(vcov.sum()), "inset_m": L["mask_inset_m"]}


# ------------------------------------------------------------------------------------------------ poses
def _best_axis(arm, bone, mover, want, deg=20.0):
    """Which local axis and sign of `bone` moves `mover`'s head most in the world direction `want`."""
    pb = arm.pose.bones[P + bone]; mv = arm.pose.bones[P + mover]
    pb.rotation_mode = "XYZ"
    base = arm.matrix_world @ mv.head.copy()
    best = (0, 1, -1e9)
    for ax in range(3):
        for sg in (1, -1):
            e = [0.0, 0.0, 0.0]; e[ax] = math.radians(deg * sg)
            pb.rotation_euler = Euler(e)
            bpy.context.view_layer.update()
            d = ((arm.matrix_world @ mv.head) - base).dot(Vector(want))
            if d > best[2]:
                best = (ax, sg, d)
    pb.rotation_euler = Euler((0, 0, 0))
    bpy.context.view_layer.update()
    return best[0], best[1]


def _reset(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = Euler((0, 0, 0)); pb.location = (0, 0, 0); pb.rotation_quaternion = (1, 0, 0, 0)


def standard_poses(arm):
    """Poses every outfit is checked in. Axes are found by trying them, so this works on any Mixamo-named rig."""
    arm.data.pose_position = 'POSE'
    _reset(arm)
    ax = {}
    for s in ("Left", "Right"):
        ax[s + "ArmDown"] = _best_axis(arm, s + "Arm", s + "ForeArm", (0, 0, -1))
        ax[s + "ArmFwd"] = _best_axis(arm, s + "Arm", s + "ForeArm", (0, -1, 0))
        ax[s + "ThighFwd"] = _best_axis(arm, s + "UpLeg", s + "Leg", (0, -1, 0))
        ax[s + "KneeBack"] = _best_axis(arm, s + "Leg", s + "Foot", (0, 1, 0))
        ax[s + "ElbowFwd"] = _best_axis(arm, s + "ForeArm", s + "Hand", (0, -1, 0))
    ax["SpineFwd"] = _best_axis(arm, "Spine", "Neck", (0, -1, 0))
    ax["SpineSide"] = _best_axis(arm, "Spine", "Neck", (1, 0, 0))

    def R(key, deg):
        a, s = ax[key]
        e = [0.0, 0.0, 0.0]; e[a] = math.radians(deg * s)
        return e

    def add(e1, e2):
        return [x + y for x, y in zip(e1, e2)]

    poses = {
        "arms_down": {"LeftArm": R("LeftArmDown", 68), "RightArm": R("RightArmDown", 68)},
        "arms_up": {"LeftArm": R("LeftArmDown", -55), "RightArm": R("RightArmDown", -55)},
        "arms_forward": {"LeftArm": R("LeftArmFwd", 75), "RightArm": R("RightArmFwd", 75),
                         "LeftForeArm": R("LeftElbowFwd", 30), "RightForeArm": R("RightElbowFwd", 30)},
        "stride": {"LeftArm": R("LeftArmDown", 68), "RightArm": R("RightArmDown", 68),
                   "LeftUpLeg": R("LeftThighFwd", 32), "RightUpLeg": R("RightThighFwd", -22),
                   "LeftLeg": R("LeftKneeBack", 15), "RightLeg": R("RightKneeBack", 25)},
        "sit": {"LeftArm": R("LeftArmDown", 60), "RightArm": R("RightArmDown", 60),
                "LeftUpLeg": R("LeftThighFwd", 80), "RightUpLeg": R("RightThighFwd", 80),
                "LeftLeg": R("LeftKneeBack", 80), "RightLeg": R("RightKneeBack", 80)},
        "bend": {"LeftArm": R("LeftArmDown", 68), "RightArm": R("RightArmDown", 68),
                 "Spine": add(R("SpineFwd", 18), R("SpineSide", 10)), "Spine1": R("SpineFwd", 14), "Spine2": R("SpineFwd", 10)},
    }
    return poses


def apply_pose(arm, pose):
    arm.data.pose_position = 'POSE'
    _reset(arm)
    for b, e in pose.items():
        pb = arm.pose.bones[P + b]
        pb.rotation_mode = "XYZ"; pb.rotation_euler = Euler(e)
    bpy.context.view_layer.update()


def pose_check(arm, body, garments, poses=None, limits=None):
    """Masked body in each pose. Also checks that no hidden skin has lost its cover (a hollow gap)."""
    L = dict(LIMITS, **(limits or {}))
    poses = poses or standard_poses(arm)
    # fitted rest edge lengths
    arm.data.pose_position = 'REST'; bpy.context.view_layer.update()
    rest_len = {}
    for g in garments:
        m = _eval(g)
        ed = np.array([e.vertices[:] for e in g.data.edges])
        ln = np.linalg.norm(m["co"][ed[:, 0]] - m["co"][ed[:, 1]], axis=1)
        ed, ln = ed[ln > 0.003], ln[ln > 0.003]                    # buttons and stitches are not cloth
        rest_len[g.name] = (ed, ln)
    arm.data.pose_position = 'POSE'
    att = body.data.attributes.get(MASK_ATTR)
    hidden = np.zeros(len(body.data.polygons), dtype=bool)
    if att is not None:
        att.data.foreach_get("value", hidden)
    R = {"poses": {}, "failures": []}
    for pname, pose in poses.items():
        apply_pose(arm, pose)
        F = []
        where = Where(body, arm)
        set_mask(body, True)
        _boot_mod(body, False)
        bm = _eval(body); bbvh = _bvh(bm)
        gms = [(g.name, _eval(g)) for g in garments]
        gms = [(n, m, _bvh(m)) for n, m in gms]
        e = {}
        through = _skin_through(bm, bbvh, gms, L["mask_cover_m"])
        inboot = bm["in_boot"]                                     # owner-approved boot exception, per triangle
        for g, (name, gm, gbvh) in zip(garments, gms):
            d = np.where(inboot, 0.0, through[name]); m = d * 1000 > L["pose_skin_count_mm"]
            ge = {"skin_through_deepest_mm": round(float(d.max() * 1000), 2),
                  "skin_through_mm2": round(float(bm["area"][m].sum() * 1e6), 1)}
            if d.max() * 1000 > L["pose_skin_through_mm"] or ge["skin_through_mm2"] > L["pose_skin_through_mm2"]:
                _fail(F, f"skin shows through cloth ({ge['skin_through_mm2']} mm2, limit {L['pose_skin_through_mm2']})", name, d.max() * 1000, L["pose_skin_through_mm"], "mm deep",
                      _clusters(bm["cen"][m], d[m] * 1000, where))
            ed, l0 = rest_len[name]
            r = np.linalg.norm(gm["co"][ed[:, 0]] - gm["co"][ed[:, 1]], axis=1) / l0
            bad = (r < L["pose_stretch"][0]) | (r > L["pose_stretch"][1])
            share = float(l0[bad].sum() / l0.sum())               # by length of cloth, not by count of edges
            ge["stretch"] = {"min": round(float(r.min()), 3), "max": round(float(r.max()), 3), "bad_share": round(share, 4)}
            if share > L["pose_stretch_share"]:
                mid = (gm["co"][ed[bad, 0]] + gm["co"][ed[bad, 1]]) / 2
                _fail(F, "cloth stretched or crushed in this pose", name, share * 100, L["pose_stretch_share"] * 100,
                      "% of edge length", _clusters(mid, np.abs(np.log(r[bad])) * 10, where))
            e[name] = ge
        # hidden skin that has lost its cover
        if hidden.any():
            set_mask(body, False)
            um = _eval(body)
            allv = np.concatenate([m["co"] for _, m, _ in gms]); tris = []; off = 0
            for _, m, _ in gms:
                tris += [tuple(int(x) + off for x in t) for t in m["tri"]]; off += len(m["co"])
            gb = BVHTree.FromPolygons([Vector(p) for p in allv], tris)
            hid_t = hidden[um["tp"]]
            ex = np.zeros(len(um["cen"]), dtype=bool)
            for i in np.nonzero(hid_t)[0]:
                p = Vector(um["cen"][i]); n = Vector(um["nrm"][i])
                # exposed = it could be seen from outside: some line from it reaches open space without meeting
                # cloth or visible skin. (Hidden skin that has pushed through the cloth, or sits in a closed fold
                # such as the back of a bent knee, cannot be seen and is what the mask is for.)
                if can_be_seen(p, n, gb, bbvh):
                    ex[i] = True
            area = float(um["area"][ex].sum() * 1e6)
            e["hidden_skin_exposed_mm2"] = round(area, 1)
            if area > L["pose_hole_mm2"]:
                _fail(F, "hidden skin exposed (a hollow gap would show)", "body mask", area, L["pose_hole_mm2"], "mm2",
                      _clusters(um["cen"][ex], np.sqrt(um["area"][ex]) * 1000, where))
            set_mask(body, True)
        e["pass"] = not F
        R["poses"][pname] = e
        for f in F:
            f["pose"] = pname
        R["failures"] += F
    _reset(arm)
    bpy.context.view_layer.update()
    R["pass"] = not R["failures"]
    return R


# ------------------------------------------------------------------------------------------------ report text
def summary(rest, mask, posed):
    ok = rest["pass"] and (posed is None or posed["pass"])
    lines = ["# Fit check: " + ("PASS" if ok else "FAIL"), ""]
    lines.append("## Rest pose, unmasked body: " + ("pass" if rest["pass"] else "FAIL"))
    for n, e in rest["garments"].items():
        lines.append(f"- {n}: {json_short(e)}")
    for f in rest["failures"]:
        lines.append(_line(f))
    if mask:
        lines += ["", f"## Skin hidden under clothes: {mask['hidden_faces']} of {mask['faces']} faces "
                      f"({mask['hidden_share_of_skin'] * 100:.0f}% of the skin), inset {mask['inset_m'] * 1000:.0f} mm from openings"]
    if posed is None:
        lines += ["", "## Poses: not run (the rest-pose check must pass first)"]
    else:
        lines += ["", "## Poses, masked body: " + ("pass" if posed["pass"] else "FAIL")]
        for n, e in posed["poses"].items():
            lines.append(f"- {n}: {'pass' if e['pass'] else 'FAIL'}")
        for f in posed["failures"]:
            lines.append(_line(f))
    return "\n".join(lines) + "\n"


def json_short(e):
    keys = ("crossing_body_triangles", "skin_through_deepest_mm", "min_clearance_mm", "floating_vertices", "misplaced_vertices",
            "floating_worst_extra_mm")
    return ", ".join(f"{k} {e[k]}" for k in keys if k in e)


def _line(f):
    s = f"- FAIL {f.get('pose', 'rest')} / {f['garment']}: {f['check']}: {f['value']} {f['unit']} (limit {f['limit']})"
    for w in f["where"][:4]:
        s += f"\n    - at {w['body_part']} ({w['side']}, {w['face']}), {w['xyz_m']}: {w['points']} points, worst {w['worst']}"
    return s
