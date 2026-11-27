"""ajkit.templates - garments generated from each Aj body's own surface (run inside Blender 5.3).

A garment here is not fitted from somewhere else: it is cut out of the body it will be worn on, so it follows that
body by construction. The steps are the same for every template:

  1. cut     the body's skin (rest pose, shape keys as set on the body) is copied, cut finer, and cut again exactly
             along the iso-line of a field (sleeve end, neckline, hem, waist ...): clean, straight hems instead of
             the body's face staircase. Each vertex keeps the body's own bone weights, interpolated at the cut.
  2. shape   pushed off the skin by an ease that grows towards the hems (looseness), smoothed without shrinking
             (Taubin), hollows bridged, and hung: below its widest part a garment may not go inwards faster than a
             slope (a shirt hangs straight off the chest, a trouser leg straight off the calf; a negative slope
             flares it). Then every vertex is pushed out to at least its minimum clearance from the skin.
  3. finish  every opening gets a rolled rim and a turned-in hem facing (the cloth's thickness shows at every
             edge), collars and cuffs are built from the openings, plackets and buttons are added as geometry.
  4. bind    bone weights (the body's, lightly smoothed across the cloth) and an Armature modifier; a fit record
             for fitcheck (`fit_asset_co`, `fit_asset_clear`, `fit_asset_chain`, `fit_asset_s`).

The fit record of a generated garment is the garment itself on this body: the checks that compare against an asset
(floating, place along the body, stretch and ragged edges at rest) therefore see no change by construction. The
checks that matter for a generated garment are measured for real: skin crossing or showing through the cloth,
cloth closer than 1.5 mm to the skin, and in the six standard poses skin through the cloth, hidden skin exposed and
cloth stretch. fitcheck is not changed.

Names: garment objects are D_<Piece>; each carries custom properties `slot`, `palette_slot`, `template`.
"""
import math
import bpy, bmesh
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import fitcheck
from . import paths as _paths

P = "mixamorig:"
TORSO = ("Hips", "Spine", "Spine1", "Spine2")
ARM_CH = {"Left": 1, "Right": 2}       # fitcheck.CHAINS index: Shoulder, Arm, ForeArm  (s: 1 shoulder joint, 2 elbow, 3 wrist)
LEG_CH = {"Left": 3, "Right": 4}       # UpLeg, Leg                                      (s: 0 hip joint, 1 knee, 2 ankle)
SPINE_CH = 0                           # Hips, Spine, Spine1, Spine2, Neck               (s: 0 hips, 4 neck base, 5 head)


def smooth01(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ================================================================================================ the body
class Body:
    """Everything a template needs to know about one Aj body in its rest pose (world metres, front -Y, left +X)."""

    def __init__(self, arm, body):
        self.arm, self.body = arm, body
        keep = arm.data.pose_position
        arm.data.pose_position = "REST"
        mods = {}
        for m in body.modifiers:                               # the fit masks must not remove faces from the copy
            if m.type != "ARMATURE":
                mods[m.name] = m.show_viewport
                m.show_viewport = False
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = body.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        if n != len(body.data.vertices):
            raise RuntimeError("the body's evaluated mesh does not match its vertices")
        co = np.empty(n * 3); me.vertices.foreach_get("co", co)
        M = np.array(body.matrix_world)
        self.co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        self.polys = [tuple(p.vertices) for p in me.polygons]
        self.pmat = np.array([p.material_index for p in me.polygons])
        ev.to_mesh_clear()
        for k, v in mods.items():
            body.modifiers[k].show_viewport = v
        arm.data.pose_position = keep
        bpy.context.view_layer.update()
        self.groups = [g.name for g in body.vertex_groups]
        gi = {g.index: g.name.split(":")[-1] for g in body.vertex_groups}
        self.w = []
        for v in body.data.vertices:
            self.w.append({gi[g.group]: g.weight for g in v.groups if g.weight > 0})
        self.dom = [max(w, key=w.get) if w else "" for w in self.w]
        self.bvh = BVHTree.FromPolygons([Vector(p) for p in self.co], self.polys)
        # vertex normals, area weighted
        vn = np.zeros_like(self.co)
        for f in self.polys:
            a, b, c = self.co[f[0]], self.co[f[1]], self.co[f[2]]
            nr = np.cross(b - a, c - a)
            if len(f) == 4:
                nr = nr + np.cross(c - a, self.co[f[3]] - a)
            for i in f:
                vn[i] += nr
        self.vn = vn / np.maximum(np.linalg.norm(vn, axis=1), 1e-12)[:, None]
        # skeleton
        self.bone = {}
        for b in arm.data.bones:
            self.bone[b.name.split(":")[-1]] = (np.array(arm.matrix_world @ b.head_local), np.array(arm.matrix_world @ b.tail_local))
        self.axes = fitcheck.bone_axes(arm)
        self.bvh_soft = self._soft_body()
        self.S = self.chain_s(self.co)
        self.marks = self._landmarks()

    def _soft_body(self, iters=12):
        """The skin with its small dents and bumps smoothed away (navel, back dimples, ribs, knuckles of the spine),
        same size (Taubin). Cloth is shaped against this; only the final clearance is measured on the real skin."""
        n = len(self.co)
        nb = [set() for _ in range(n)]
        for f in self.polys:
            for k in range(len(f)):
                a, b = f[k], f[(k + 1) % len(f)]
                nb[a].add(b); nb[b].add(a)
        nb = [list(x) for x in nb]
        head = np.array([d in ("Head", "Neck", "HeadTop_End") or "Hand" in d for d in self.dom])
        X = self.co.copy()
        for _ in range(iters):
            for lam in (0.5, -0.53):
                A = np.array([X[x].mean(axis=0) if x else X[i] for i, x in enumerate(nb)])
                D = (A - X) * lam
                D[head] = 0
                X = X + D
        self.co_soft = X
        return BVHTree.FromPolygons([Vector(p) for p in X], self.polys)

    # ---- addresses
    def chain_s(self, pts):
        pts = np.asarray(pts, float)
        return np.stack([fitcheck.chain_address(pts, self.axes, np.full(len(pts), c))[1] for c in range(len(fitcheck.CHAINS))])

    def head(self, name):
        return self.bone[name][0]

    def weight_of(self, i, names):
        w = self.w[i]
        return sum(w.get(n, 0.0) for n in names)

    def _landmarks(self):
        h = self.head
        L = {"height": float(self.co[:, 2].max()), "hips_z": float(h("Hips")[2]), "spine_z": float(h("Spine")[2]),
             "spine1_z": float(h("Spine1")[2]), "spine2_z": float(h("Spine2")[2]), "neck_z": float(h("Neck")[2]),
             "head_z": float(h("Head")[2]), "sh_z": float(h("LeftArm")[2]), "sh_x": float(h("LeftArm")[0]),
             "cl_x": float(h("LeftShoulder")[0]), "elbow_x": float(h("LeftForeArm")[0]), "wrist_x": float(h("LeftHand")[0]),
             "hipj_z": float(h("LeftUpLeg")[2]), "hipj_x": float(h("LeftUpLeg")[0]), "knee_z": float(h("LeftLeg")[2]),
             "ankle_z": float(h("LeftFoot")[2]), "neck_y": float(h("Neck")[1])}
        # crotch: a ray up the middle from below
        hit = self.bvh.ray_cast(Vector((0.0, float(h("Hips")[1]), 0.05)), Vector((0, 0, 1)), 2.0)
        L["crotch_z"] = float(hit[0].z) if hit[0] is not None else L["hipj_z"] - 0.06
        # the neck's radius at its base and the torso's half width at the chest
        nk = self.co[(np.abs(self.co[:, 2] - (L["neck_z"] + 0.02)) < 0.012) & (np.abs(self.co[:, 0]) < 0.12)]
        L["neck_r"] = float(np.median(np.linalg.norm(nk[:, :2] - [0, L["neck_y"]], axis=1))) if len(nk) else 0.06
        # armpit: the lowest skin under the shoulder joint, at the side of the chest
        side = self.co[(np.abs(self.co[:, 0] - (L["sh_x"] - 0.01)) < 0.015) & (self.co[:, 2] < L["sh_z"]) & (self.co[:, 2] > L["spine1_z"])]
        L["armpit_z"] = float(side[:, 2].max()) if len(side) else L["sh_z"] - 0.08
        L["arm_r"] = float(np.median(np.abs(self.co[(np.abs(self.co[:, 0] - (L["sh_x"] + 0.08)) < 0.01), 2] - L["sh_z"]))) \
            if np.any(np.abs(self.co[:, 0] - (L["sh_x"] + 0.08)) < 0.01) else 0.05
        return L


# ================================================================================================ 1. cut
def _dl(bm):
    return bm.verts.layers.deform.verify()


def sheet(B, field, allow, subdiv=1, keep=1):
    """A bmesh of the body skin where field > 0, cut exactly along field == 0.

    field(B, co[n,3], src[n]) -> values per vertex (metres: + inside the garment). allow(B, i) -> body vertex may be
    covered at all (keeps hands, feet, head out unless the template wants them). The field is evaluated again on the
    subdivided points (positions interpolated), so cut lines are smooth."""
    use = np.array([allow(B, i) for i in range(len(B.co))])
    faces = [f for f, m in zip(B.polys, B.pmat) if m == 0 and all(use[i] for i in f)]
    bm = bmesh.new()
    dl = _dl(bm)
    gidx = {n.split(":")[-1]: k for k, n in enumerate(B.groups)}
    vmap = {}
    for f in faces:
        for i in f:
            if i not in vmap:
                v = bm.verts.new(Vector(B.co[i]))
                for b, w in B.w[i].items():
                    v[dl][gidx[b]] = w
                vmap[i] = v
    for f in faces:
        try:
            bm.faces.new([vmap[i] for i in f])
        except ValueError:
            pass
    bm.verts.ensure_lookup_table()
    if subdiv:
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdiv, use_grid_fill=True)
    fl = bm.verts.layers.float.new("f")
    co = np.array([tuple(v.co) for v in bm.verts])
    vals = field(B, co)
    vals = np.where(np.abs(vals) < 1e-6, 1e-6, vals)
    for v, x in zip(bm.verts, vals):
        v[fl] = float(x)
    # split every edge that crosses the iso-line at the crossing
    cross = [e for e in bm.edges if (e.verts[0][fl] > 0) != (e.verts[1][fl] > 0)]
    zero = set()
    for e in cross:
        a, b = e.verts
        fa, fb = a[fl], b[fl]
        t = fa / (fa - fb)
        ne, nv = bmesh.utils.edge_split(e, a, t)
        nv.co = a.co.lerp(b.co, t)
        nv[fl] = 0.0
        zero.add(nv)
    for f in list(bm.faces):
        zs = [v for v in f.verts if v in zero]
        if len(zs) == 2:
            a, b = zs
            if b not in [e.other_vert(a) for e in a.link_edges]:
                try:
                    bmesh.utils.face_split(f, a, b)
                except ValueError:
                    pass
    dead = [f for f in bm.faces if sum(v[fl] for v in f.verts) / len(f.verts) <= 0 or any(v[fl] < 0 for v in f.verts)]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    _keep_largest(bm, keep)
    bm.normal_update()
    return bm


def _keep_largest(bm, keep=1):
    seen = set(); comps = []
    for f in bm.faces:
        if f in seen:
            continue
        st = [f]; seen.add(f); comp = []
        while st:
            g = st.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h); st.append(h)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    dead = [f for c in comps[keep:] for f in c]
    if dead:
        bmesh.ops.delete(bm, geom=dead, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")


# ================================================================================================ 2. shape
def _nbrs(bm):
    bm.verts.ensure_lookup_table()
    return [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]


def _boundary_nbrs(bm):
    return [[e.other_vert(v).index for e in v.link_edges if e.is_boundary] if v.is_boundary else None for v in bm.verts]


def taubin(X, nb, bnb, iters=6, lam=0.5, mu=-0.53, fixed=None):
    """Smooth positions without shrinking. Boundary points are smoothed along their boundary only."""
    X = X.copy()
    for _ in range(iters):
        for k in (lam, mu):
            A = np.empty_like(X)
            for i in range(len(X)):
                ns = bnb[i] if bnb[i] is not None else nb[i]
                A[i] = X[ns].mean(axis=0) if ns else X[i]
            D = A - X
            if fixed is not None:
                D[fixed] = 0
            X = X + k * D
    return X


def push_out(B, X, min_clear, iters=3, soft=False):
    """Every point at least min_clear (per point) outside the skin, moved along the skin normal at its nearest point.
    soft: against the smoothed skin (shaping), not the real one (clearance)."""
    X = X.copy()
    tree = B.bvh_soft if soft else B.bvh
    for _ in range(iters):
        moved = 0
        for i in range(len(X)):
            hit, nrm, fi, d = tree.find_nearest(Vector(X[i]))
            if hit is None:
                continue
            s = (Vector(X[i]) - hit).dot(nrm)
            sd = d if s >= 0 else -d
            if sd < min_clear[i]:
                X[i] = np.array(hit + nrm * float(min_clear[i]))
                moved += 1
        if not moved:
            break
    return X


def clearance(B, X):
    out = np.empty(len(X))
    for i in range(len(X)):
        hit, nrm, fi, d = B.bvh.find_nearest(Vector(X[i]))
        out[i] = d if (Vector(X[i]) - hit).dot(nrm) >= 0 else -d
    return out


def drape(X, wgt, origin, axis, slope, nth=64, dh=0.01, keep_side=None):
    """Hang cloth off its widest part above: along `axis` (pointing the way the cloth hangs), at each angle round it,
    the radius may shrink at most `slope` per metre of hanging (negative: it must grow - a flare).
    wgt[n] 0..1: how much each point belongs to this column (0 = untouched). Returns new positions."""
    o = np.asarray(origin, float); ax = np.asarray(axis, float); ax = ax / np.linalg.norm(ax)
    ref = np.array([0, -1.0, 0]) if abs(ax[1]) < 0.9 else np.array([1.0, 0, 0])
    e1 = ref - ax * (ref @ ax); e1 /= np.linalg.norm(e1); e2 = np.cross(ax, e1)
    R = X - o
    h = R @ ax
    rv = R - np.outer(h, ax)
    r = np.linalg.norm(rv, axis=1)
    th = np.arctan2(rv @ e2, rv @ e1)
    sel = wgt > 1e-3
    if not sel.any():
        return X
    h0, h1 = h[sel].min(), h[sel].max()
    nh = int((h1 - h0) / dh) + 2
    ti = ((th + math.pi) / (2 * math.pi) * nth).astype(int) % nth
    hi = np.clip(((h - h0) / dh).astype(int), 0, nh - 1)
    T = np.full((nth, nh), -1.0)
    for i in np.nonzero(sel)[0]:
        T[ti[i], hi[i]] = max(T[ti[i], hi[i]], r[i])
    # hang: walk down the column
    for a in range(nth):
        cur = -1.0
        for k in range(nh):
            if cur >= 0:
                cur = cur - slope * dh
            if T[a, k] > cur:
                cur = T[a, k]
            T[a, k] = cur
    # a little blur round the column so neighbouring angles agree
    for _ in range(2):
        T = np.maximum(T, (np.roll(T, 1, 0) + np.roll(T, -1, 0) + 2 * T) / 4)
    want = T[ti, hi]
    newr = np.where(sel, np.maximum(r, r + (want - r) * wgt), r)
    newr = np.where(want < 0, r, newr)
    scale = np.where(r > 1e-6, newr / np.maximum(r, 1e-9), 1.0)
    return o + np.outer(h, ax) + rv * scale[:, None]


# ================================================================================================ 3. finish
def boundary_loops(bm):
    """Closed runs of boundary edges as ordered vertex lists."""
    bnd = {e for e in bm.edges if e.is_boundary}
    loops = []
    used = set()
    for e0 in bnd:
        if e0 in used:
            continue
        loop = [e0.verts[0]]; used.add(e0); cur = e0.verts[1]; prev_e = e0
        while cur is not loop[0]:
            loop.append(cur)
            nxt = [e for e in cur.link_edges if e in bnd and e not in used]
            if not nxt:
                break
            prev_e = nxt[0]; used.add(prev_e); cur = prev_e.other_vert(cur)
        loops.append(loop)
    return loops


def _copy_w(dl, src, dst, scale=1.0):
    for k, w in src[dl].items():
        dst[dl][k] = w


def hem(bm, thick=0.003, depth=0.018, loops=None, rim_segments=2, B=None):
    """Roll every opening over: a rounded rim of `thick` and a facing of `depth` turned in under the cloth. The
    facing's inner edge is the garment's open edge (what fitcheck calls the opening), hidden under the cloth."""
    dl = _dl(bm)
    bm.normal_update()
    loops = loops if loops is not None else boundary_loops(bm)
    made = []
    for loop in loops:
        n = len(loop)
        if n < 3:
            continue
        P0 = [v.co.copy() for v in loop]
        N = [v.normal.copy() for v in loop]
        if B is not None:                     # never thicker than the room under the edge (a facing must stay under the cloth)
            cl = clearance(B, np.array([tuple(p) for p in P0]))
            TK = [float(np.clip(c_ - 0.0027, 0.0012, thick)) for c_ in cl]
        else:
            TK = [thick] * n
        # direction from the edge into the cloth, in the surface: away from the opening
        Tin = []
        for k, v in enumerate(loop):
            tan = (P0[(k + 1) % n] - P0[k - 1]).normalized()
            inw = N[k].cross(tan).normalized()
            # pick the sign that points into the cloth (towards the face centres next to the edge)
            fc = [f.calc_center_median() for f in v.link_faces]
            c = sum(fc, Vector()) / max(len(fc), 1)
            if inw.dot(c - P0[k]) < 0:
                inw = -inw
            Tin.append(inw)
        rings = []
        for s in range(1, rim_segments + 1):
            a = math.pi * s / rim_segments                      # half turn round the rim
            ring = []
            for k in range(n):
                p = P0[k] - N[k] * (TK[k] * (1 - math.cos(a)) / 2) - Tin[k] * (-TK[k] * 0.5 * math.sin(a))
                ring.append(p)
            rings.append(ring)
        rings.append([P0[k] - N[k] * TK[k] + Tin[k] * depth for k in range(n)])
        prev = loop
        for ring in rings:
            cur = []
            for k in range(n):
                nv = bm.verts.new(ring[k]); _copy_w(dl, loop[k], nv); cur.append(nv)
            for k in range(n):
                a, b = prev[k], prev[(k + 1) % n]
                c, d = cur[(k + 1) % n], cur[k]
                try:
                    bm.faces.new((a, b, c, d))
                except ValueError:
                    pass
            prev = cur
        made.append(prev)
    bm.normal_update()
    return made


def _bm_tree(bm):
    bm.verts.ensure_lookup_table()
    return BVHTree.FromBMesh(bm)


def _nearest_weights(bm, verts, src):
    """New vertices take the bone weights of the nearest vertex of `src` (the cloth they lie on)."""
    dl = _dl(bm)
    kd = KDTree(len(src))
    for i, v in enumerate(src):
        kd.insert(v.co, i)
    kd.balance()
    for v in verts:
        _, i, _ = kd.find(v.co)
        _copy_w(dl, src[i], v)


def collar(bm, B, depth=0.03, gap_x=0.012, lift=0.0028, rows=4, point=0.9):
    """A turned-down collar from the neckline: the cloth folds over at the neck edge and lies on the shoulders and
    chest `lift` off the shirt, `depth` deep, open at the front by `gap_x` each side of the middle."""
    bm.normal_update()
    tree = _bm_tree(bm)
    old = list(bm.verts)
    loops = boundary_loops(bm)
    neck = max(loops, key=lambda l: sum(v.co.z for v in l) / len(l))
    n = len(neck)
    keep = [not (abs(v.co.x) < gap_x and v.co.y < B.marks["neck_y"]) for v in neck]
    if all(keep):
        start = 0
    else:                                               # start the strip just after the front gap
        start = next(k for k in range(n) if keep[k] and not keep[k - 1])
    order = [(start + k) % n for k in range(n)]
    order = [k for k in order if keep[k]]
    P0 = [neck[k].co.copy() for k in order]
    Tin = []
    for j, k in enumerate(order):
        v = neck[k]
        tan = (neck[(k + 1) % n].co - neck[k - 1].co).normalized()
        inw = v.normal.cross(tan).normalized()
        fc = [f.calc_center_median() for f in v.link_faces]
        c = sum(fc, Vector()) / max(len(fc), 1)
        if inw.dot(c - v.co) < 0:
            inw = -inw
        Tin.append(inw)
    prev = [neck[k] for k in order]
    made = []
    new_faces = []
    for r in range(1, rows + 1):
        d = depth * r / rows
        cur = []
        for j in range(len(order)):
            # the points: longer at the front ends, as a shirt collar's
            fr = float(smooth01((B.marks["neck_y"] - P0[j].y) / 0.05) * smooth01((0.07 - abs(P0[j].x)) / 0.05))
            q = P0[j] + Tin[j] * d * (1.0 + point * fr)
            hit = tree.find_nearest(q, 0.1)
            if hit[0] is not None:
                h = lift * min(1.0, r / 1.5)
                q = hit[0] + hit[1].normalized() * h
            nv = bm.verts.new(q); cur.append(nv)
        for j in range(len(order) - 1):
            try:
                new_faces.append(bm.faces.new((prev[j], prev[j + 1], cur[j + 1], cur[j])))
            except ValueError:
                pass
        made += cur
        prev = cur
    _nearest_weights(bm, made, old)
    # wind the collar the same way as the shirt across the fold (one consistent surface)
    a, b = neck[order[0]], neck[order[1]]
    e = next((e for e in a.link_edges if e.other_vert(a) is b), None)
    shirt_f = next((f for f in e.link_faces if f not in new_faces), None) if e else None
    if shirt_f is not None:
        ls = list(shirt_f.verts)
        i = ls.index(a)
        same = ls[(i + 1) % len(ls)] is b                   # the shirt face runs a -> b
        if same:                                            # the collar's first face runs a -> b too: flip it
            bmesh.ops.reverse_faces(bm, faces=new_faces)
    bm.normal_update()
    return made


def buttons(bm, B, z_top, z_bottom, count, radius=0.0045, thick=0.0018, x=0.0, segments=10):
    """`count` round buttons down the front at x, standing on the cloth (closed little discs, own material index 1)."""
    bm.normal_update()
    tree = _bm_tree(bm)
    old = list(bm.verts)
    made = []
    for z in np.linspace(z_top, z_bottom, count):
        hit = tree.ray_cast(Vector((x, -1.0, float(z))), Vector((0, 1, 0)), 2.0)
        if hit[0] is None:
            continue
        p, nr = hit[0], hit[1].normalized()
        if nr.y > 0:
            nr = -nr
        u = nr.cross(Vector((0, 0, 1))).normalized(); w = nr.cross(u).normalized()
        base = p + nr * 0.0015
        rings = []
        for h in (0.0, thick):
            ring = []
            for k in range(segments):
                a = 2 * math.pi * k / segments
                ring.append(bm.verts.new(base + nr * h + (u * math.cos(a) + w * math.sin(a)) * radius * (1.0 if h == 0 else 0.85)))
            rings.append(ring)
        fs = [bm.faces.new(list(reversed(rings[0]))), bm.faces.new(rings[1])]
        for k in range(segments):
            k2 = (k + 1) % segments
            fs.append(bm.faces.new((rings[0][k], rings[0][k2], rings[1][k2], rings[1][k])))
        for f in fs:
            f.material_index = 1
        made += rings[0] + rings[1]
    _nearest_weights(bm, made, old)
    bm.normal_update()
    return made


def ridge(bm, tree, pts, direction, w=0.003, h=0.002, closed=False, mat=0, reach=0.4, accept=None, rigid=False, base=True):
    """A raised stitched line (placket edge, pocket, hem line, belt loop, lace): `pts` are laid on the cloth by a ray
    along `direction` from `reach` in front of them, and a small closed rounded bar `w` wide and `h` high is built along
    them (closed, so it adds no open edge for the fit mask). accept(point, normal) may refuse a hit. Returns the new
    vertices. rigid: every ring takes the weights under the middle of the run (a short bar moves as one piece, so it
    cannot stretch), otherwise each ring takes the cloth's own weights under it. base=False leaves the underside open
    (a bar on cloth that the body moves under: a closed underside would be a second surface facing the skin)."""
    d = Vector(direction).normalized()
    hits = []
    bm.faces.ensure_lookup_table()
    dl = _dl(bm)
    for p in pts:
        hit = tree.ray_cast(Vector(p) - d * reach, d, reach * 2.5)
        if hit[0] is None or (accept is not None and not accept(hit[0], hit[1])):
            hits.append(None)
            continue
        n = hit[1].normalized()
        if n.dot(d) > 0:
            n = -n
        hits.append((hit[0].copy(), n, bm.faces[hit[2]]))
    runs, cur = [], []
    for k in hits:
        if k is None:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
        else:
            cur.append(k)
    if len(cur) >= 2:
        runs.append(cur)
    made = []
    for run in runs:
        rings = []
        for i, (p, n, fc) in enumerate(run):
            t = (run[min(i + 1, len(run) - 1)][0] - run[max(i - 1, 0)][0]).normalized()
            s = n.cross(t).normalized()
            ring = [bm.verts.new(p - s * w * 0.5 + n * 0.0004), bm.verts.new(p - s * w * 0.28 + n * h),
                    bm.verts.new(p + s * w * 0.28 + n * h), bm.verts.new(p + s * w * 0.5 + n * 0.0004)]
            acc = {}                                           # one set of weights for the whole ring: the cloth's under its centre
            if rigid:
                p, fc = run[len(run) // 2][0], run[len(run) // 2][2]
            iw = [1.0 / max((v.co - p).length, 1e-5) for v in fc.verts]
            tot = sum(iw)
            for v, wi in zip(fc.verts, iw):
                for k, wk in v[dl].items():
                    acc[k] = acc.get(k, 0.0) + wk * wi / tot
            for v in ring:
                for k, wk in acc.items():
                    v[dl][k] = wk
            rings.append(ring)
        fs = []
        for a, b in zip(rings[:-1], rings[1:]):
            for j in range(4 if base else 3):
                try:
                    fs.append(bm.faces.new((a[j], a[(j + 1) % 4], b[(j + 1) % 4], b[j])))
                except ValueError:
                    pass
        for ring in (rings[0], rings[-1]):
            try:
                fs.append(bm.faces.new(ring))
            except ValueError:
                pass
        bm.normal_update()
        p0, n0, _f = run[len(run) // 2]
        # wind the bar so that the top faces point out of the cloth
        top = [f for f in fs if len(f.verts) == 4 and f.calc_center_median().dot(n0) > p0.dot(n0) + h * 0.5]
        if top and sum(f.normal.dot(n0) for f in top) < 0:
            bmesh.ops.reverse_faces(bm, faces=fs)
        for f in fs:
            f.material_index = mat
        for ring in rings:
            made += ring
    bm.normal_update()
    return made


def disc_at(bm, p, nr, radius, thick, up=None, segments=10, mat=1):
    """One round button standing on the cloth at p (normal nr), closed, own material index."""
    nr = Vector(nr).normalized()
    u = nr.cross(Vector(up) if up is not None else Vector((0, 0, 1)))
    u = (u if u.length > 1e-4 else nr.cross(Vector((1, 0, 0)))).normalized()
    w = nr.cross(u).normalized()
    base = Vector(p) + nr * 0.0015
    rings = []
    for hh in (0.0, thick):
        rings.append([bm.verts.new(base + nr * hh + (u * math.cos(2 * math.pi * k / segments) + w * math.sin(2 * math.pi * k / segments)) * radius
                                   * (1.0 if hh == 0 else 0.85)) for k in range(segments)])
    fs = [bm.faces.new(list(reversed(rings[0]))), bm.faces.new(rings[1])]
    for k in range(segments):
        k2 = (k + 1) % segments
        fs.append(bm.faces.new((rings[0][k], rings[0][k2], rings[1][k2], rings[1][k])))
    for f in fs:
        f.material_index = mat
    return rings[0] + rings[1]


def _move_weights(ob, src_names, dst_name, k_of_vertex):
    """Move the fraction k(v) of the weight a vertex has on the `src_names` groups (short names) to group `dst_name`."""
    me = ob.data
    short = {g.index: g.name.split(":")[-1] for g in ob.vertex_groups}
    dst = next((g for g in ob.vertex_groups if g.name.split(":")[-1] == dst_name), None) or ob.vertex_groups.new(name=P + dst_name)
    for v in me.vertices:
        k = float(k_of_vertex(v))
        if k <= 1e-4:
            continue
        moved = 0.0
        cur = 0.0
        for g in v.groups:
            if short.get(g.group) in src_names:
                moved += g.weight * k
                g.weight = g.weight * (1 - k)
            if g.group == dst.index:
                cur = g.weight
        if moved > 0:
            dst.add([v.index], cur + moved, "REPLACE")


def follow_pelvis(ob, B, z_hi, z_lo, frac):
    """Below z_hi a top follows the pelvis, not the thighs: the share `frac` (growing to full at z_lo) of the weight on
    the upper legs goes to Hips. Sitting, the hem then stays with the seat instead of being dragged forward."""
    def k(v):
        z = ob.matrix_world @ v.co
        return frac * float(smooth01((z_hi - z.z) / max(z_hi - z_lo, 1e-3)))
    _move_weights(ob, {"LeftUpLeg", "RightUpLeg"}, "Hips", k)


# ================================================================================================ 4. bind
def _rebind(ob, B):
    """Weights from the skin nearest each cloth point as it now stands (not from the skin it was cut from): where
    the cloth bridges a crease (seat, small of the back) it then follows the skin under it."""
    me = ob.data
    gi = {g.name.split(":")[-1]: g.index for g in ob.vertex_groups}
    for g in ob.vertex_groups:
        g.remove(list(range(len(me.vertices))))
    for v in me.vertices:
        hit, nrm, fi, d = B.bvh.find_nearest(v.co, 0.2)
        if hit is None:
            continue
        f = B.polys[fi]
        P = B.co[list(f)]
        iw = 1.0 / np.maximum(np.linalg.norm(P - np.array(hit), axis=1), 1e-5)
        iw /= iw.sum()
        acc = {}
        for k, wk in zip(f, iw):
            for n, w in B.w[k].items():
                acc[n] = acc.get(n, 0.0) + w * wk
        s = sum(acc.values()) or 1.0
        for n, w in acc.items():
            if w / s > 1e-3 and n in gi:
                ob.vertex_groups[gi[n]].add([v.index], w / s, "REPLACE")


def to_object(bm, B, name, col=None, smooth_weights=0, rebind=False):
    """The bmesh (world coordinates) as a mesh object skinned to the body's armature, with the body's group names."""
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    for g in B.groups:
        ob.vertex_groups.new(name=g)
    if rebind:
        _rebind(ob, B)
    if smooth_weights:
        _smooth_weights(ob, smooth_weights)
    # drop empty groups
    used = set()
    for v in me.vertices:
        for g in v.groups:
            if g.weight > 1e-4:
                used.add(g.group)
    for g in [g for g in ob.vertex_groups if g.index not in used]:
        ob.vertex_groups.remove(g)
    ob.parent = B.arm
    ob.matrix_parent_inverse = B.arm.matrix_world.inverted()
    ob.matrix_world = Matrix.Identity(4)
    am = ob.modifiers.new("Armature", "ARMATURE"); am.object = B.arm
    bm_ = B.body.modifiers.get("Armature")                   # deform the way the skin does (the body uses dual quaternions)
    am.use_deform_preserve_volume = bool(bm_.use_deform_preserve_volume) if bm_ else True
    for p in me.polygons:
        p.use_smooth = True
    return ob


def _smooth_weights(ob, iters):
    """Average each vertex's weights with its neighbours': cloth bends more softly than skin at a crease."""
    me = ob.data
    n = len(me.vertices); G = len(ob.vertex_groups)
    W = np.zeros((n, G))
    for v in me.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    nb = [[] for _ in range(n)]
    for e in me.edges:
        a, b = e.vertices
        nb[a].append(b); nb[b].append(a)
    for _ in range(iters):
        W2 = W.copy()
        for i in range(n):
            if nb[i]:
                W2[i] = 0.5 * W[i] + 0.5 * W[nb[i]].mean(axis=0)
        W = W2
    W[W < 1e-3] = 0
    W /= np.maximum(W.sum(axis=1, keepdims=True), 1e-9)
    for g in ob.vertex_groups:
        idx = np.nonzero(W[:, g.index])[0]
        g.remove(list(range(n)))
        for i in idx:
            g.add([int(i)], float(W[i, g.index]), "REPLACE")


def fit_record(ob, B):
    """What fitcheck compares against: the garment as generated on this body (rest pose)."""
    me = ob.data
    X = np.array([tuple(ob.matrix_world @ v.co) for v in me.vertices])
    clear = clearance(B, X)
    ch, s = fitcheck.chain_address(X, B.axes)
    for nm, tp in (("fit_asset_co", "FLOAT_VECTOR"), ("fit_asset_clear", "FLOAT"), ("fit_asset_chain", "INT"), ("fit_asset_s", "FLOAT")):
        a = me.attributes.get(nm)
        if a is not None:
            me.attributes.remove(a)
        me.attributes.new(nm, tp, "POINT")
    me.attributes["fit_asset_co"].data.foreach_set("vector", X.astype(np.float32).ravel())
    me.attributes["fit_asset_clear"].data.foreach_set("value", np.abs(clear).astype(np.float32))
    me.attributes["fit_asset_chain"].data.foreach_set("value", ch.astype(np.int32))
    me.attributes["fit_asset_s"].data.foreach_set("value", s.astype(np.float32))
    return {"min_clear_mm": round(float(clear.min() * 1000), 2), "verts": len(X)}


# ================================================================================================ the generic builder
def vertex_weights(bm, B):
    """(n, groups) matrix of the bone weights each sheet vertex carries, and short group names."""
    dl = _dl(bm)
    names = [g.split(":")[-1] for g in B.groups]
    W = np.zeros((len(bm.verts), len(names)))
    for v in bm.verts:
        for k, w in v[dl].items():
            W[v.index, k] = w
    return W, names


def wsum(W, names, want):
    idx = [k for k, n in enumerate(names) if n in want]
    return W[:, idx].sum(axis=1) if idx else np.zeros(len(W))


class Piece:
    """One garment piece being built: the sheet, its points X (world), and per-point context for ease rules."""

    def __init__(self, B, bm):
        self.B, self.bm = B, bm
        bm.verts.ensure_lookup_table(); bm.normal_update()
        self.X0 = np.array([tuple(v.co) for v in bm.verts])
        self.N0 = np.array([tuple(v.normal) for v in bm.verts])
        self.W, self.names = vertex_weights(bm, B)
        self.S = B.chain_s(self.X0)

    def w(self, *bones):
        return wsum(self.W, self.names, set(bones))

    def side_w(self, side, parts):
        return wsum(self.W, self.names, {side + p for p in parts})

    def room(self, reach=0.08):
        """Free space in front of each point of the skin, along its normal, before other skin (the arm against the
        chest, thigh against thigh). Cloth may take a share of it, never more."""
        out = np.full(len(self.X0), reach)
        for i, (p, n) in enumerate(zip(self.X0, self.N0)):
            hit = self.B.bvh.ray_cast(Vector(p) + Vector(n) * 1e-3, Vector(n), reach)
            if hit[0] is not None:
                out[i] = hit[3] + 1e-3
        return out


def laplace(X, nb, bnb, lam):
    A = np.empty_like(X)
    for i in range(len(X)):
        ns = bnb[i] if bnb[i] is not None else nb[i]
        A[i] = X[ns].mean(axis=0) if ns else X[i]
    return X + lam * (A - X)


def shape_piece(pc, ease, min_clear, drapes=(), smooth=6, keep_out=(), gap=0.004, fair=8):
    """Offset by ease along the skin normal, smooth, hang the drapes, keep clear of the skin (and outside inner
    garments by `gap`), and write the result into the bmesh."""
    B, bm = pc.B, pc.bm
    nb = _nbrs(bm); bnb = _boundary_nbrs(bm)
    if keep_out:
        # over an inner garment the cloth stands off at least that garment plus a gap, and eases back to its own
        # ease above and below it at a gentle slope (no lip at the inner garment's edge)
        trees = [_tree(o) for o in keep_out]
        req = np.zeros(len(pc.X0))
        for i, (p_, n_) in enumerate(zip(pc.X0, pc.N0)):
            for t in trees:
                h = t.ray_cast(Vector(p_) + Vector(n_) * 1e-4, Vector(n_), 0.06)
                if h[0] is not None:
                    req[i] = max(req[i], h[3] + gap + 0.003)
        L = [[float(np.linalg.norm(pc.X0[i] - pc.X0[j])) for j in nb[i]] for i in range(len(nb))]
        for _ in range(10):                                  # fill the dips (rays that slipped past the inner hem)
            req = np.maximum(req, np.array([req[n].mean() if n else 0.0 for n in nb]))
        for _ in range(40):
            new = req.copy()
            for i in range(len(req)):
                for j, l in zip(nb[i], L[i]):
                    new[i] = max(new[i], req[j] - 0.12 * l)
            if np.allclose(new, req):
                break
            req = new
        ease = np.maximum(ease, req)
    room = pc.room()
    ease = np.minimum(ease, np.maximum(0.45 * room, 0.0022))
    min_clear = np.minimum(np.minimum(min_clear, ease), np.maximum(0.45 * room, 0.0020))
    pc.ease_used = ease
    X = pc.X0 + pc.N0 * ease[:, None]
    nb = _nbrs(bm); bnb = _boundary_nbrs(bm)
    # a balloon from outside: smooth (which pulls hollows out and bumps in), then no point nearer the skin than its
    # ease. The result is the offset surface where the body is convex, bridged over navel, spine and cleavage.
    for _ in range(smooth):
        X = laplace(X, nb, bnb, 0.6)
        X = push_out(B, X, ease, iters=1, soft=True)
    for d in drapes:
        X = drape(X, d["w"], d["origin"], d["axis"], d.get("slope", 0.0))
        for _ in range(2):
            X = laplace(X, nb, bnb, 0.5)
            X = push_out(B, X, ease, iters=1, soft=True)
    # then take the body's small bumps out (back dimples, navel rim, ribs): smoothing that does not shrink, kept
    # only clear of the skin, not at full ease
    if fair:
        X = taubin(X, nb, bnb, iters=fair)
    X = push_out(B, X, min_clear)
    if keep_out:
        trees = [_tree(o) for o in keep_out]
        for _ in range(4):                                   # over an inner garment: eased over its edge, no step
            for t in trees:
                X = _outside_of(X, t, gap, pc.N0)
            X = laplace(X, nb, bnb, 0.5)
        for t in trees:
            X = _outside_of(X, t, gap, pc.N0)
    X = push_out(B, X, min_clear, iters=1)
    for v, p in zip(bm.verts, X):
        v.co = Vector(p)
    bm.normal_update()
    return X


def _tree(inner):
    me = inner.data
    V = [inner.matrix_world @ v.co for v in me.vertices]
    return BVHTree.FromPolygons(V, [tuple(p.vertices) for p in me.polygons])


def _outside_of(X, bvh, gap, N, reach=0.06):
    """Keep points at least `gap` outside another garment (its rest surface): a shirt over trousers. Measured along
    the skin normal N from outside in (the inner garment's outermost layer), and moved only along it: the nearest
    point would be the rim on top of the waistband, whose normal points up, and push the cloth up into a step."""
    X = X.copy()
    for i in range(len(X)):
        n = Vector(N[i])
        far = Vector(X[i]) + n * reach
        hit = bvh.ray_cast(far, -n, 2 * reach)
        if hit[0] is None:
            continue
        if reach > hit[3] - gap:
            X[i] = np.array(far - n * (hit[3] - gap))
    return X


def settle(bm, B, least=0.0024):
    """After rims and facings: nothing nearer the skin than `least` (fitcheck fails cloth within 1.5 mm)."""
    bm.verts.ensure_lookup_table()
    X = np.array([tuple(v.co) for v in bm.verts])
    X = push_out(B, X, np.full(len(X), least))
    for v, p in zip(bm.verts, X):
        v.co = Vector(p)
    bm.normal_update()


def lerp(a, b, t):
    return a + (b - a) * np.clip(t, 0.0, 1.0)


# ------------------------------------------------------------------------------------------------ allow rules
def allow_bones(names, below=None, above=None):
    names = set(names)

    def f(B, i):
        if B.dom[i] not in names:
            return False
        z = B.co[i][2]
        return (below is None or z < below) and (above is None or z > above)
    return f


def ellipsoid(X, c, r):
    """Signed distance-like value: < 0 inside the ellipsoid (centre c, radii r), in metres of the smallest radius."""
    q = (X - np.asarray(c)) / np.asarray(r)
    return (np.linalg.norm(q, axis=1) - 1.0) * min(r)


# ================================================================================================ templates
# Every template: f(B, col, p) -> list of objects. p: the parameters (defaults below, overridable from fit.py).
UPPER = TORSO + ("Neck", "LeftShoulder", "RightShoulder", "LeftArm", "RightArm", "LeftForeArm", "RightForeArm")
LOWER = ("Hips", "Spine", "LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg")
FEET = ("LeftFoot", "RightFoot", "LeftToeBase", "RightToeBase", "LeftToe_End", "RightToe_End")


def _arm_len(B):
    return float(np.linalg.norm(B.head("LeftForeArm") - B.head("LeftArm")))


def top(B, col, p, name="D_Top"):
    """A top cut from the torso and arms: T-shirt, long-sleeve shirt, blouse, pullover, tunic body.
    p: sleeve (arm-chain s: 1 = shoulder joint, 2 = elbow, 3 = wrist), hem_z (fraction between crotch 0 and hips joint
    1, may be negative: below the crotch), neck (crew|scoop|v|boat|high), ease_* in metres, drape slope."""
    M = B.marks
    sl = p.get("sleeve", 1.55)
    hem_z = M["crotch_z"] + (M["hipj_z"] - M["crotch_z"]) * p.get("hem", 1.4)
    if "hem_mark" in p:                                      # or: a landmark plus an offset (a mantle ends at the chest)
        hem_z = M[p["hem_mark"]] + p.get("hem_off", 0.0) * M["height"] / 1.8
    L = _arm_len(B)
    neck = p.get("neck", "crew")
    nr = M["neck_r"]
    nc = np.array([0.0, M["neck_y"], M["neck_z"]])
    if neck == "crew":
        c, r = nc + [0, -0.004, 0.012], (nr + 0.020, nr + 0.024, 0.055)
    elif neck == "high":                                    # a collar stand will sit on it
        c, r = nc + [0, -0.002, 0.020], (nr + 0.012, nr + 0.014, 0.045)
    elif neck == "scoop":
        c, r = nc + [0, -0.030, -0.005], (nr + 0.040, nr + 0.060, 0.095)
    elif neck == "v":
        c, r = nc + [0, -0.040, -0.030], (nr + 0.030, nr + 0.050, 0.120)
    elif neck == "boat":
        c, r = nc + [0, 0.000, 0.000], (nr + 0.070, nr + 0.025, 0.050)
    else:
        raise ValueError("neck: crew, high, scoop, v or boat")

    op = p.get("open")                                      # (half gap at the hem, half gap at the neck) in metres: a jacket, a cardigan
    hb = p.get("hem_back", 0.0) * M["height"] / 1.8             # the hem rides this much higher at the back (an untucked top)
    ay = float(B.head("Hips")[1])

    def field(B_, X):
        S = B_.chain_s(X)
        f = np.minimum(X[:, 2] - (hem_z + hb * smooth01((X[:, 1] - ay) / 0.10)), ellipsoid(X, c, r))
        if op:                                              # an open front: no cloth within `gap` of the middle, in front
            zt = np.clip((X[:, 2] - hem_z) / max(M["neck_z"] - hem_z, 0.1), 0, 1)
            gap = (op[0] + (op[1] - op[0]) * zt) * M["height"] / 1.8
            f = np.minimum(f, np.where(X[:, 1] < ay, np.abs(X[:, 0]) - gap, 1.0))
        for s_ in ("Left", "Right"):
            f = np.minimum(f, (sl - S[ARM_CH[s_]]) * L)
        if neck == "v":                                     # the V: two planes meeting at the front
            pass
        return f
    allow = allow_bones(UPPER + ("LeftUpLeg", "RightUpLeg"), above=hem_z - 0.02)
    bm = sheet(B, field, allow, subdiv=p.get("subdiv", 1))
    pc = Piece(B, bm)
    X = pc.X0
    arm_w = pc.side_w("Left", ("Arm", "ForeArm")) + pc.side_w("Right", ("Arm", "ForeArm"))
    sarm = np.maximum(pc.S[ARM_CH["Left"]], pc.S[ARM_CH["Right"]])
    down = np.clip((M["armpit_z"] - X[:, 2]) / max(M["armpit_z"] - hem_z, 0.05), 0, 1)     # 0 at the armpit, 1 at the hem
    e_sh, e_hem = p.get("ease_shoulder", 0.006), p.get("ease_hem", 0.020)
    e_cuff = p.get("ease_cuff", 0.016 if sl < 2.2 else 0.010)
    ease = lerp(e_sh, e_hem, smooth01(down) ** 0.8)
    t_sl = np.clip((sarm - 1.0) / max(sl - 1.0, 0.2), 0, 1)
    ease = ease * (1 - arm_w) + arm_w * lerp(e_sh + 0.002, e_cuff, t_sl)
    # near the neckline the cloth hugs a little closer
    nd = np.clip(-ellipsoid(X, c, r) / 0.04, 0, 1)
    ease = lerp(ease, p.get("ease_neck", 0.005), 1 - smooth01(nd * 2.5))
    min_clear = np.maximum(0.0035, ease * 0.5)
    # hang off the chest and shoulder blades at front and back; the sides stay close (the arms rest there)
    torso_w = pc.w(*TORSO) * (1 - arm_w) * smooth01((M["armpit_z"] + 0.02 - X[:, 2]) / 0.06) * smooth01((np.abs(pc.N0[:, 1]) - 0.35) / 0.4)
    drapes = [dict(w=torso_w, origin=(0, float(B.head("Spine")[1]), M["armpit_z"]), axis=(0, 0, -1), slope=p.get("slope", 0.0))]
    for s_ in ("Left", "Right"):
        aw = pc.side_w(s_, ("Arm", "ForeArm")) * smooth01((pc.S[ARM_CH[s_]] - 1.15) / 0.2)
        drapes.append(dict(w=aw, origin=B.head(s_ + "Arm"), axis=B.head(s_ + "ForeArm") - B.head(s_ + "Arm"),
                           slope=p.get("sleeve_slope", -0.03)))
    shape_piece(pc, ease, min_clear, drapes, keep_out=p.get("over", ()), gap=p.get("gap", 0.004))
    if p.get("collar"):
        sc = M["height"] / 1.8
        cv = set(collar(bm, B, depth=p.get("collar_depth", 0.038) * sc, gap_x=p.get("collar_gap", 0.012) * sc))
        loops = boundary_loops(bm)
        hem(bm, thick=0.002, depth=0.004, loops=[l for l in loops if any(v in cv for v in l)], rim_segments=2, B=B)
        hem(bm, thick=p.get("thick", 0.003), depth=p.get("hem_depth", 0.007), loops=[l for l in loops if not any(v in cv for v in l)], B=B)
    else:
        hem(bm, thick=p.get("thick", 0.003), depth=p.get("hem_depth", 0.007), B=B)
    settle(bm, B)
    sc = M["height"] / 1.8
    if p.get("cuffs"):
        _cuffs(bm, B, sl, p["cuffs"] * sc)
    old = list(bm.verts)
    detail = []
    if p.get("buttons"):
        front = [v.co.z for v in bm.verts if v.is_boundary and abs(v.co.x) < 0.03 and v.co.y < M["neck_y"] and v.co.z > M["spine1_z"]]
        z_top = (min(front) if front else M["neck_z"] - 0.04) - 0.018 * sc
        z_bot = hem_z + (0.05 if not p.get("tucked") else 0.03) * sc
        if p.get("placket", True):                          # a placket: two stitched edges, the buttons between them
            tree = _bm_tree(bm)
            hw = p.get("placket_w", 0.016) * sc
            zs = np.linspace(z_top + 0.012 * sc, z_bot, 24)
            for sx in (-1, 1):
                rv = ridge(bm, tree, [(sx * hw, -0.3, float(z)) for z in zs], (0, 1, 0), w=0.0032 * sc, h=0.0022 * sc)
        buttons(bm, B, z_top, z_bot, int(p["buttons"]), radius=p.get("button_r", 0.0062) * sc, thick=0.0028 * sc)
    if p.get("cuffs"):
        tree = _bm_tree(bm)
        for sgn, nm in ((1, "Left"), (-1, "Right")):
            ax0, ax1 = B.head(nm + "ForeArm"), B.head(nm + "Hand")
            q = ax0 + (ax1 - ax0) * (sl - 2.0 - p["cuffs"] * sc / max(_arm_len(B), 1e-3) * 0.5)
            for dirn in ((sgn, 0, 0),):
                hit = tree.ray_cast(Vector(q) + Vector(dirn) * 0.3, -Vector(dirn), 0.6)
                if hit[0] is not None:
                    _nearest_weights(bm, disc_at(bm, hit[0], hit[1], p.get("button_r", 0.0062) * sc * 0.85, 0.0026 * sc, up=(0, 0, 1)), old)
    if p.get("lapels"):                                      # lapels laid on the front of an open jacket
        tree = _bm_tree(bm)
        z_t, z_l = M["neck_z"] - 0.012 * sc, M["armpit_z"] - p["lapels"] * sc
        for sx in (-1, 1):
            rows = []
            for t in np.linspace(0, 1, 12):
                z = z_t + (z_l - z_t) * t
                zt_ = float(np.clip((z - hem_z) / max(M["neck_z"] - hem_z, 0.1), 0, 1))
                gap = (op[0] + (op[1] - op[0]) * zt_) * sc
                hw = 0.5 * 0.062 * sc * (1.0 - 0.80 * t ** 1.3) * (1.0 + 0.25 * math.sin(math.pi * min(t * 1.6, 1.0)))
                rows.append((sx * (gap + hw), z, hw, 0.0034 * sc))
            strip(bm, tree, rows, accept=lambda pt, nr: pt.y < float(B.head("Hips")[1]) - 0.01)
    if p.get("hem_line"):                                    # a stitched hem line round the body, as a T-shirt has
        tree = _bm_tree(bm)
        cy = float(B.head("Hips")[1])
        zz = hem_z + 0.016 * sc
        detail += _ring_ridge(bm, tree, cy, zz, sc)
    if detail:
        _nearest_weights(bm, detail, old)
    bm.normal_update()
    ob = to_object(bm, B, name, col, rebind=p.get("rebind", False))
    if p.get("pelvis"):
        follow_pelvis(ob, B, M["hipj_z"] + 0.05 * sc, M["crotch_z"] - 0.04 * sc, p["pelvis"])
    bm.free()
    return ob


def _ring_ridge(bm, tree, cy, z, sc, w=0.0028, h=0.0018):
    """A closed ring of stitching round the body at height z (rays in from outside at 120 angles)."""
    pts, norms = [], []
    for k in range(120):
        a = 2 * math.pi * k / 120
        d = Vector((math.sin(a), -math.cos(a), 0.0))
        hit = tree.ray_cast(Vector((0.0, cy, z)) + d * 0.7, -d, 0.7)
        if hit[0] is None:
            return []
        pts.append(hit[0].copy()); norms.append(hit[1].normalized() if hit[1].dot(d) > 0 else -hit[1].normalized())
    n = len(pts)
    rings = []
    for i in range(n):
        t = (pts[(i + 1) % n] - pts[i - 1]).normalized()
        s_ = norms[i].cross(t).normalized() * w * sc
        nn = norms[i]
        rings.append([bm.verts.new(pts[i] - s_ * 0.5 + nn * 0.0004), bm.verts.new(pts[i] - s_ * 0.28 + nn * h * sc),
                      bm.verts.new(pts[i] + s_ * 0.28 + nn * h * sc), bm.verts.new(pts[i] + s_ * 0.5 + nn * 0.0004)])
    fs = []
    for i in range(n):
        a, b = rings[i], rings[(i + 1) % n]
        for j in range(4):
            try:
                fs.append(bm.faces.new((a[j], a[(j + 1) % 4], b[(j + 1) % 4], b[j])))
            except ValueError:
                pass
    bm.normal_update()
    top = [f for f in fs if sum(1 for v in f.verts if v is rings[0][1] or v in [r[1] for r in rings]) >= 2]
    if sum(f.normal.dot(f.calc_center_median() - Vector((0, cy, z))) for f in top) < 0:
        bmesh.ops.reverse_faces(bm, faces=fs)
    return [v for r in rings for v in r]


def _cuffs(bm, B, sl, length):
    """A cuff: the last `length` metres of each sleeve stand 2.4 mm proud of the sleeve above, with a clean step."""
    bm.verts.ensure_lookup_table()
    X = np.array([tuple(v.co) for v in bm.verts])
    S = B.chain_s(X)
    L = max(_arm_len(B), 1e-3)
    bm.normal_update()
    for nm in ("Left", "Right"):
        s_ = S[ARM_CH[nm]]
        side = (X[:, 0] > 0) if nm == "Left" else (X[:, 0] < 0)
        for v, sv, sd in zip(bm.verts, s_, side):
            if sd and abs(v.co.x) > 0.12 and sv > sl - length / L:
                k = float(smooth01((sv - (sl - length / L)) / (0.006 / L)))
                v.co = v.co + v.normal * 0.0024 * k
    bm.normal_update()


def trousers(B, col, p, name="D_Trousers"):
    """Trousers, shorts, breeches, hose: cut from hips and legs. p: waist (metres above the hip joint), leg (leg-chain
    s of the hem: 1 = knee, 2 = ankle), ease_*, slope (how straight the leg hangs)."""
    M = B.marks
    waist_z = M["hipj_z"] + p.get("waist", 0.11) * (M["height"] / 1.8)
    leg = p.get("leg", 1.99)
    Lleg = float(np.linalg.norm(B.head("LeftLeg") - B.head("LeftUpLeg")))

    def field(B_, X):
        S = B_.chain_s(X)
        f = waist_z - X[:, 2]
        for s_ in ("Left", "Right"):
            f = np.minimum(f, (leg - S[LEG_CH[s_]]) * Lleg)
        return f
    allow = allow_bones(LOWER + ("Spine1",) + FEET, above=0.02)
    bm = sheet(B, field, allow, subdiv=p.get("subdiv", 1))
    pc = Piece(B, bm)
    X = pc.X0
    sleg = np.maximum(pc.S[LEG_CH["Left"]], pc.S[LEG_CH["Right"]])
    legw = pc.side_w("Left", ("UpLeg", "Leg")) + pc.side_w("Right", ("UpLeg", "Leg"))
    e_w, e_hip, e_knee, e_hem = p.get("ease_waist", 0.008), p.get("ease_hip", 0.009), p.get("ease_knee", 0.014), p.get("ease_hem", 0.018)
    t = np.clip(sleg / max(leg, 0.5), 0, 1)
    ease_leg = np.where(sleg < 1, lerp(e_hip, e_knee, sleg), lerp(e_knee, e_hem, (sleg - 1) / max(leg - 1, 0.2)))
    up = np.clip((X[:, 2] - M["crotch_z"]) / max(waist_z - M["crotch_z"], 0.05), 0, 1)
    ease_top = lerp(e_hip, e_w, smooth01(up))
    ease = np.where(X[:, 2] > M["crotch_z"], ease_top, ease_leg)
    min_clear = np.maximum(0.0035, ease * 0.5)
    drapes = []
    for s_ in ("Left", "Right"):
        sg = 1.0 if s_ == "Left" else -1.0
        outer = smooth01((sg * (X[:, 0] - B.head(s_ + "UpLeg")[0]) + 0.01) / 0.03)     # the inside leg hugs: the other leg is there
        w_ = pc.side_w(s_, ("UpLeg", "Leg")) * smooth01((M["crotch_z"] - 0.03 - X[:, 2]) / 0.06) * np.maximum(outer, smooth01((M["knee_z"] - X[:, 2]) / 0.1))
        drapes.append(dict(w=w_, origin=B.head(s_ + "UpLeg"), axis=B.head(s_ + "Foot") - B.head(s_ + "UpLeg"),
                           slope=p.get("slope", 0.04)))
    X = shape_piece(pc, ease, min_clear, drapes, keep_out=p.get("over", ()), gap=p.get("gap", 0.004))
    sc = M["height"] / 1.8
    if p.get("waistband", True):                              # a waistband: the top 33 mm stand proud of the cloth below
        bw = 0.033 * sc
        bm.normal_update()
        for v in bm.verts:
            if v.co.z > waist_z - bw - 0.004 and v.co.z < waist_z + 0.002:
                v.co = v.co + v.normal * 0.0024 * float(smooth01((v.co.z - (waist_z - bw - 0.004)) / 0.004))
    hem(bm, thick=p.get("thick", 0.003), depth=p.get("hem_depth", 0.02), B=B)
    settle(bm, B)
    old = list(bm.verts)
    detail = []
    if p.get("waistband", True) and p.get("loops", False):
        tree = _bm_tree(bm)
        cy = float(B.head("Hips")[1])
        zz = np.linspace(waist_z - 0.006 * sc, waist_z - 0.034 * sc, 4)
        for deg in (-32, 32, -140, 140, 180):
            a = math.radians(deg)
            d = Vector((math.sin(a), -math.cos(a), 0.0))
            rv = ridge(bm, tree, [(0.0, cy, float(z)) for z in zz], (-d.x, -d.y, 0), w=0.0085 * sc, h=0.0030 * sc, reach=0.7, rigid=True, base=False,
                       accept=lambda pt, nr, d=d, cy=cy: (pt.x * d.x + (pt.y - cy) * d.y) > 0.03)
    if p.get("pockets", True):
        tree = _bm_tree(bm)
        hx = abs(M["hipj_x"])
        for sx in (-1, 1):
            # front slash pocket: from the waist at the hip's side, curving in and down
            ts = np.linspace(0, 1, 16) if p.get("pocket_front", True) else []
            pts = [(sx * (hx * 1.18 - 0.55 * hx * t ** 1.4), -0.4, waist_z - 0.012 * sc - 0.085 * sc * t) for t in ts]
            if pts:
                rv = ridge(bm, tree, pts, (0, 1, 0), w=0.0028 * sc, h=0.0018 * sc, rigid=True, base=False,
                           accept=lambda pt, nr: pt.y < float(B.head("Hips")[1]) - 0.01)
            # back pocket: a rectangle outline, rays from behind
            if not p.get("pocket_back", True):
                continue
            x0, x1, z0, z1 = sx * hx * 0.30, sx * hx * 0.92, waist_z - 0.055 * sc, waist_z - 0.135 * sc
            edge = []
            for t in np.linspace(0, 1, 8):
                edge.append((x0 + (x1 - x0) * t, 0.5, z0))
            for t in np.linspace(0, 1, 8)[1:]:
                edge.append((x1, 0.5, z0 + (z1 - z0) * t))
            for t in np.linspace(0, 1, 8)[1:]:
                edge.append((x1 + (x0 - x1) * t, 0.5, z1))
            for t in np.linspace(0, 1, 8)[1:]:
                edge.append((x0, 0.5, z1 + (z0 - z1) * t))
            rv = ridge(bm, tree, edge, (0, -1, 0), w=0.0026 * sc, h=0.0016 * sc, rigid=True, base=False, accept=lambda pt, nr: pt.y > float(B.head("Hips")[1]) + 0.01)
    bm.normal_update()
    ob = to_object(bm, B, name, col, rebind=p.get("rebind", False))
    bm.free()
    return ob


def shoes(B, col, p, name="D_Shoes"):
    """Trainers, shoes, boots: the foot below the ankle as a shell, with a flat sole band under it (own material index 1,
    standing out as a welt with a ledge), a heel block, a toe box, and stitched detail by `style`: trainer (lace panel,
    tongue, toe cap), office (vamp seam, toe cap). p: top (metres above the ankle joint), ease, sole (how far the bottom
    lies below the floor: the skin's own sole is at z = 0 and the check wants 1.5 mm of cloth below it), sole_h (height of
    the band), welt, heel (extra height of the band at the heel), style."""
    M = B.marks
    sc = M["height"] / 1.8
    top_z = M["ankle_z"] + p.get("top", 0.012) * sc
    ay = float(B.head("LeftFoot")[1])
    tilt = p.get("tilt", 0.35)                               # the collar runs lower at the front, over the instep

    def field(B_, X):
        return top_z + tilt * (X[:, 1] - ay) - X[:, 2]
    allow = allow_bones(FEET + ("LeftLeg", "RightLeg"), below=top_z + 0.06)
    bm = sheet(B, field, allow, subdiv=p.get("subdiv", 2), keep=2)
    pc = Piece(B, bm)
    style = p.get("style")
    ease = np.full(len(pc.X0), p.get("ease", 0.006))
    ease = ease + p.get("toe", 0.010 if style else 0.006) * smooth01((-pc.X0[:, 1] - 0.0) / 0.15)       # room at the toe: a toe box
    min_clear = np.full(len(pc.X0), 0.004)
    X = shape_piece(pc, ease, min_clear, (), smooth=4, keep_out=p.get("over", ()), gap=p.get("gap", 0.004))
    sole = p.get("sole", 0.0026)
    sole_h = p.get("sole_h", 0.022) * sc
    welt = p.get("welt", 0.0034) * sc
    heel = p.get("heel", 0.0) * sc
    # each foot's own frame: toe at low y, heel at high y
    frames = {}
    for sg in (1.0, -1.0):
        pts = np.array([tuple(v.co) for v in bm.verts if v.co.x * sg > 0 and v.co.z < 0.04])
        if len(pts):
            frames[sg] = (float(pts[:, 0].mean()), float(pts[:, 1].min()), float(pts[:, 1].max()),
                          float(np.abs(pts[:, 0] - pts[:, 0].mean()).max()))
    for v in bm.verts:
        if v.co.z < 0.012 * sc:                              # a flat bottom
            v.co.z = -sole + (v.co.z + sole) * 0.25 if v.co.z > -sole else -sole
    for v in bm.verts:
        sg = 1.0 if v.co.x > 0 else -1.0
        if sg not in frames:
            continue
        xc, ylo, yhi, hw = frames[sg]
        t = (v.co.y - ylo) / max(yhi - ylo, 1e-3)
        top = sole_h + heel * float(smooth01((t - 0.70) / 0.10))
        k = 1.0 - float(smooth01((v.co.z - (top - 0.002)) / 0.008))        # the welt: full to the ledge, gone just above it
        if k > 0:
            gx, gy = (v.co.x - xc) / max(hw, 1e-3) ** 2, (v.co.y - (ylo + yhi) / 2) / max((yhi - ylo) / 2, 1e-3) ** 2
            gl = max(math.hypot(gx, gy), 1e-6)
            v.co.x += gx / gl * welt * k
            v.co.y += gy / gl * welt * k
    hem(bm, thick=p.get("thick", 0.005 if style else 0.004), depth=p.get("hem_depth", 0.015), B=B)
    settle(bm, B)
    for f in bm.faces:
        c = f.calc_center_median()
        sg = 1.0 if c.x > 0 else -1.0
        top = sole_h
        if sg in frames:
            xc, ylo, yhi, hw = frames[sg]
            top = sole_h + heel * float(smooth01(((c.y - ylo) / max(yhi - ylo, 1e-3) - 0.70) / 0.10))
        f.material_index = 1 if c.z < top else 0
    if style:
        old = list(bm.verts)
        tree = _bm_tree(bm)
        up = (0, 0, -1)
        keep = lambda pt, nr: pt.z > 0.026 * sc and nr.z > 0.25
        for sg, (xc, ylo, yhi, hw) in frames.items():
            L_ = yhi - ylo
            Y = lambda t: ylo + t * L_
            if style == "trainer":
                for sx in (-1, 1):                           # the lace panel's two edges
                    ridge(bm, tree, [(xc + sx * 0.016 * sc, Y(t), 0.5) for t in np.linspace(0.30, 0.62, 9)], up,
                          w=0.0032 * sc, h=0.0022 * sc, accept=keep, rigid=True)
                for t in (0.36, 0.43, 0.50, 0.57):           # laces across it
                    ridge(bm, tree, [(xc + u * 0.016 * sc, Y(t), 0.5) for u in np.linspace(-1, 1, 5)], up,
                          w=0.0030 * sc, h=0.0022 * sc, accept=keep, rigid=True)
                ridge(bm, tree, [(xc, Y(t), 0.5) for t in np.linspace(0.63, 0.72, 4)], up,          # the tongue
                      w=0.017 * sc, h=0.0030 * sc, accept=keep, rigid=True)
            if style in ("trainer", "office"):                  # toe cap seam
                ridge(bm, tree, [(xc + u * hw * 0.62, Y(0.20), 0.5) for u in np.linspace(-1, 1, 9)], up,
                      w=0.0030 * sc, h=0.0020 * sc, accept=keep, rigid=True)
            if style == "office":                               # vamp seam
                ridge(bm, tree, [(xc + u * hw * 0.62, Y(0.43), 0.5) for u in np.linspace(-1, 1, 9)], up,
                      w=0.0030 * sc, h=0.0020 * sc, accept=keep, rigid=True)
    ob = to_object(bm, B, name, col)
    bm.free()
    return ob


# ================================================================================================ fabrics
# kind -> (registry material id, file under paths.FABRICS, material name) for the BlenderKit scans the pack holds, or
# None for our own procedural shader (licence own). Every fabric is recoloured through its palette slot: the scan's
# colour texture is turned grey and multiplied by the palette colour (the node named "Palette").
FABRIC_SRC = {
    "cotton": ("mat_white_cotton", "white-cotton/white-cotton_2K.blend", "White Cotton"),
    "linen": ("mat_white_linen_fabric", "white-linen-fabr/white-linen-fabric_2K.blend", "White linen fabric"),
    "woven": ("mat_navy_woven_fabric_pbr_material", "navy-woven-fabri/navy-woven-fabric-pbr-material_2K.blend", "Navy Woven Fabric PBR Material"),
    "leather": ("mat_worn_leather_dark_brown_leather", "worn-leather-dar/worn-leather-dark-brown-leather_2K.blend", "Worn Leather (Dark Brown Leather)"),
    "fur": ("mat_fur_white", "fur-white/fur-white_2K.blend", "Fur white"),
    "gold": ("mat_gold_metal", "gold-metal/gold-metal_2K.blend", "Gold metal"),
    "velvet": None, "steel": None, "iron": None, "rubber": None, "felt": None,
}
OWN = {"velvet": dict(rough=0.85, sheen=1.0, metal=0.0), "steel": dict(rough=0.28, sheen=0.0, metal=1.0),
       "iron": dict(rough=0.45, sheen=0.0, metal=0.9), "rubber": dict(rough=0.75, sheen=0.0, metal=0.0),
       "felt": dict(rough=0.95, sheen=0.4, metal=0.0)}
USED_SOURCES = set()


def _load_scan(kind):
    reg, rel, mname = FABRIC_SRC[kind]
    key = "SRC_" + kind
    m = bpy.data.materials.get(key)
    if m is not None:
        return m
    path = str(_paths.FABRICS / rel)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.materials = [mname]
    m = dst.materials[0]
    m.name = key
    USED_SOURCES.add(reg)
    return m


# metres of cloth per texture repeat: fine enough that a weave reads at a medium shot, and how hard the scan's normal map bites
FABRIC_TILE = {"cotton": 0.16, "linen": 0.16, "woven": 0.18, "leather": 0.18, "fur": 0.25, "gold": 0.2}
FABRIC_NORMAL = {"cotton": 1.2, "linen": 1.2, "woven": 1.3, "leather": 1.1}
FABRIC_SHEEN = {"cotton": 0.35, "linen": 0.25, "woven": 0.3}


def fabric(kind, colour, slot, tile=None):
    """A recolourable material: `kind` from FABRIC_SRC, `colour` (r, g, b) linear, `slot` the palette slot name.
    `tile` metres of cloth per texture repeat (the garments get world-scale box UVs)."""
    tile = tile or FABRIC_TILE.get(kind, 0.25)
    name = f"F_{slot}_{kind}"
    m = bpy.data.materials.get(name)
    if m is not None:
        m.node_tree.nodes["Palette"].outputs[0].default_value = (*colour, 1)
        return m
    if FABRIC_SRC.get(kind) is None:
        o = OWN[kind]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        pal = nt.nodes.new("ShaderNodeRGB"); pal.name = pal.label = "Palette"
        pal.outputs[0].default_value = (*colour, 1)
        nt.links.new(pal.outputs[0], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = o["rough"]; b.inputs["Metallic"].default_value = o["metal"]
        if o["sheen"]:
            b.inputs["Sheen Weight"].default_value = o["sheen"]
            b.inputs["Sheen Tint"].default_value = (*colour, 1)
        # a fine weave or grain in the bump, so a flat colour still reads as a material
        tc = nt.nodes.new("ShaderNodeTexCoord"); nz = nt.nodes.new("ShaderNodeTexNoise"); bp = nt.nodes.new("ShaderNodeBump")
        nz.inputs["Scale"].default_value = 900.0 if kind in ("velvet", "felt") else 300.0
        bp.inputs["Strength"].default_value = 0.08 if kind in ("steel", "iron") else 0.15
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"]); nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
        m["fabric_source"] = "own"
    else:
        src = _load_scan(kind)
        m = src.copy(); m.name = name
        nt = m.node_tree
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
        for l in list(out.inputs["Displacement"].links):
            nt.links.remove(l)
        b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        bc = b.inputs["Base Color"]
        pal = nt.nodes.new("ShaderNodeRGB"); pal.name = pal.label = "Palette"
        pal.outputs[0].default_value = (*colour, 1)
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        if bc.is_linked and kind != "gold":
            hs = nt.nodes.new("ShaderNodeHueSaturation"); hs.inputs["Saturation"].default_value = 0.0
            nt.links.new(bc.links[0].from_socket, hs.inputs["Color"])
            soft = nt.nodes.new("ShaderNodeMix"); soft.data_type = "RGBA"; soft.blend_type = "MIX"
            soft.inputs["Factor"].default_value = 0.5                   # keep half of the weave's light and dark
            soft.inputs["A"].default_value = (0.85, 0.85, 0.85, 1)
            nt.links.new(hs.outputs["Color"], soft.inputs["B"])
            nt.links.new(soft.outputs["Result"], mix.inputs["A"])
        elif bc.is_linked:
            nt.links.new(bc.links[0].from_socket, mix.inputs["A"])
        else:
            mix.inputs["A"].default_value = bc.default_value
        nt.links.new(pal.outputs[0], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], bc)
        # texture scale: every image node reads a mapping we control
        tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1.0 / tile, 1.0 / tile, 1.0 / tile)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        for n in nt.nodes:
            if n.bl_idname == "ShaderNodeTexImage":
                for l in list(n.inputs["Vector"].links):
                    nt.links.remove(l)
                nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        for n in nt.nodes:                                    # the scan's own normal and roughness maps, made to show
            if n.bl_idname == "ShaderNodeNormalMap" and kind in FABRIC_NORMAL:
                n.inputs["Strength"].default_value = FABRIC_NORMAL[kind]
        if kind in FABRIC_SHEEN:
            b.inputs["Sheen Weight"].default_value = FABRIC_SHEEN[kind]
            b.inputs["Sheen Roughness"].default_value = 0.5
        m["fabric_source"] = FABRIC_SRC[kind][0]
    m["palette_slot"] = slot
    m["fabric_kind"] = kind
    return m


def dress(ob, slot, palette_slot, mats, template, uv_size=1.0):
    """Materials (one per material index of the piece), box UVs, and the registry labels on the object."""
    idx = [p.material_index for p in ob.data.polygons]      # clearing the slots resets every face to slot 0
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(m)
    ob.data.polygons.foreach_set("material_index", [min(i, len(mats) - 1) for i in idx])
    ob.data.update()
    _box_uv(ob, uv_size)
    ob["slot"] = slot; ob["palette_slot"] = palette_slot; ob["template"] = template


def _box_uv(ob, size):
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    uv = me.uv_layers.new(name="UVMap")
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            u, v = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
            uv.data[li].uv = (u / size, v / size)


# ================================================================================================ outfits
def _ring_radius(B, c, z, cols, reach=0.7):
    """Outermost skin at height z for each of `cols` directions round centre c (x, y): rays from outside in."""
    out = np.zeros(cols)
    for k in range(cols):
        a = 2 * math.pi * k / cols
        d = Vector((math.sin(a), -math.cos(a), 0.0))
        start = Vector((c[0], c[1], z)) + d * reach
        hit = B.bvh.ray_cast(start, -d, reach)
        out[k] = reach - hit[3] if hit[0] is not None else 0.0
    return out


def skirt(B, col, p, name="D_Skirt"):
    """A skirt, the skirt of a gown or robe, an apron's body: a tube hung from the waist, not cut from the skin (it
    bridges the legs). p: waist (metres above the hip joint, scaled), length (leg-chain s of the hem: 1 knee, 2 ankle),
    ease, flare (outward per metre of drop), front_only (an apron: the front arc only, angle in degrees), over."""
    M = B.marks
    sc = M["height"] / 1.8
    waist_z = M["hipj_z"] + p.get("waist", 0.11) * sc
    ln = p.get("length", 1.1)
    hem_z = lerp(M["hipj_z"], M["knee_z"], ln) if ln <= 1 else lerp(M["knee_z"], M["ankle_z"] + 0.03 * sc, ln - 1)
    hem_z = float(hem_z)
    cols = p.get("cols", 72)
    rows = max(8, int((waist_z - hem_z) / (0.014 * sc)))
    cx, cy = 0.0, float(B.head("Hips")[1])
    inner = [_tree(o) for o in p.get("over", ())]
    ease, flare = p.get("ease", 0.012) * sc, p.get("flare", 0.25)
    R = np.zeros((rows + 1, cols))
    Z = np.linspace(waist_z, hem_z, rows + 1)
    for i, z in enumerate(Z):
        r = _ring_radius(B, (cx, cy), float(z), cols)
        for t in inner:                                       # over trousers / an inner skirt: outside them too
            for k in range(cols):
                a = 2 * math.pi * k / cols
                d = Vector((math.sin(a), -math.cos(a), 0.0))
                h = t.ray_cast(Vector((cx, cy, float(z))) + d * 0.7, -d, 0.7)
                if h[0] is not None:
                    r[k] = max(r[k], 0.7 - h[3] + p.get("gap", 0.004))
        e = ease * (0.6 + 0.4 * smooth01((waist_z - z) / max(waist_z - M["crotch_z"], 0.05)))
        R[i] = r + e
        if i:
            R[i] = np.maximum(R[i], R[i - 1] + flare * (Z[i - 1] - z) * smooth01((M["hipj_z"] - z) / 0.08 + 0.3))
    # round it off: no dents between the legs, smooth round the ring
    for i in range(rows + 1):
        for _ in range(6):
            R[i] = np.maximum(R[i], 0.5 * (np.roll(R[i], 1) + np.roll(R[i], -1)))
    bm = bmesh.new()
    arc = p.get("front_only")
    ks = range(cols) if not arc else [k for k in range(cols) if abs(((k / cols * 360 + 180) % 360) - 180) <= arc / 2]
    ks = list(ks)
    V = {}
    for i, z in enumerate(Z):
        for k in ks:
            a = 2 * math.pi * k / cols
            V[i, k] = bm.verts.new((cx + R[i, k] * math.sin(a), cy - R[i, k] * math.cos(a), float(z)))
    closed = not arc
    vent = p.get("vent", 0.0) * sc                           # a back vent: no cloth in the back column up to this height above the hem
    z_vent = hem_z + vent
    for i in range(rows):
        for j in range(len(ks) if closed else len(ks) - 1):
            k, k2 = ks[j], ks[(j + 1) % len(ks)]
            if vent and k == cols // 2 and Z[i + 1] < z_vent:
                continue
            bm.faces.new((V[i, k], V[i, k2], V[i + 1, k2], V[i + 1, k]))
    bm.normal_update()
    _orient_out(bm, B)
    hem(bm, thick=p.get("thick", 0.003), depth=p.get("hem_depth", 0.006), B=B)
    settle(bm, B)
    if p.get("panel_arc"):                                  # an apron as a front panel of the skirt (material index 1)
        half = math.radians(p["panel_arc"]) / 2
        for f in bm.faces:
            c = f.calc_center_median()
            ang = math.atan2(c.x - cx, -(c.y - cy))
            if abs(ang) <= half and c.z > hem_z + p.get("panel_up", 0.03) * sc:
                f.material_index = 1
    ob = to_object(bm, B, name, col, rebind=True, smooth_weights=p.get("smooth_w", 14))
    bm.free()
    if p.get("back_leg", 1.0) < 1.0:
        _scale_leg_weights(ob, B, cy, p["back_leg"])
    if p.get("lap", 0.0):
        _lap_weights(ob, B, cy, p["lap"])
    if p.get("panels", 0.0):
        _panel_weights(ob, B, cy, p["panels"])
    return ob


def _lap_weights(ob, B, cy, strength):
    """The front of the skirt below the hip joint goes with the thighs (half to each upper leg, taken from Hips): sitting,
    the front panel lies over the lap instead of staying behind the thighs that have moved through it."""
    M = B.marks
    me = ob.data
    names = {g.index: g.name.split(":")[-1] for g in ob.vertex_groups}
    idx = {names[g.index]: g.index for g in ob.vertex_groups}
    for n in ("LeftUpLeg", "RightUpLeg"):
        if n not in idx:
            idx[n] = ob.vertex_groups.new(name=P + n).index
    hip = idx.get("Hips")
    for v in me.vertices:
        front = smooth01((cy - v.co.y) / 0.05)
        k = strength * float(front * smooth01((M["hipj_z"] + 0.03 - v.co.z) / 0.08))
        if k <= 1e-3 or hip is None:
            continue
        w = {g.group: g.weight for g in v.groups}
        h = w.get(hip, 0.0)
        if h <= 0:
            continue
        take = h * k
        ob.vertex_groups[hip].add([v.index], h - take, "REPLACE")
        for n in ("LeftUpLeg", "RightUpLeg"):
            ob.vertex_groups[idx[n]].add([v.index], w.get(idx[n], 0.0) + take / 2, "REPLACE")


def _panel_weights(ob, B, cy, strength):
    """Centre front and centre back panels follow the average of both thighs, not the nearer one: a skirt does not
    scissor with the legs. Sitting, the front panel then rides over both thighs instead of opening into a bowl. The
    two sides of the skirt keep following their own leg."""
    me = ob.data
    names = {g.index: g.name.split(":")[-1] for g in ob.vertex_groups}
    idx = {n: g.index for g in ob.vertex_groups for n in [names[g.index]]}
    for v in me.vertices:
        r = max(math.hypot(v.co.x, v.co.y - cy), 1e-6)
        c = strength * float(smooth01(1.0 - abs(v.co.x) / (0.62 * r)))
        if c <= 1e-3:
            continue
        w = {names[g.group]: g.weight for g in v.groups}
        for part in ("UpLeg", "Leg", "Foot"):
            a, b = w.get("Left" + part, 0.0), w.get("Right" + part, 0.0)
            if a == 0.0 and b == 0.0:
                continue
            m = 0.5 * (a + b)
            for side, cur in (("Left", a), ("Right", b)):
                gname = side + part
                if gname not in idx:
                    ob.vertex_groups.new(name=P + gname)
                    idx[gname] = ob.vertex_groups[P + gname].index
                ob.vertex_groups[idx[gname]].add([v.index], cur + (m - cur) * c, "REPLACE")


def _scale_leg_weights(ob, B, cy, back):
    """Behind the body the skirt follows the legs only `back` as much (the rest goes to Hips): sitting, the thighs go
    forward and the back of the skirt stays behind the seat instead of being dragged under it."""
    me = ob.data
    names = {g.index: g.name.split(":")[-1] for g in ob.vertex_groups}
    hips = next((g for g in ob.vertex_groups if g.name.split(":")[-1] == "Hips"), None)
    if hips is None:
        return
    for v in me.vertices:
        dy = (cy - v.co.y)
        r = max(math.hypot(v.co.x, dy), 1e-6)
        k = lerp(back, 1.0, smooth01((dy / r + 0.3) / 0.9))
        moved = 0.0
        for g in v.groups:
            if "Leg" in names[g.group] or "Foot" in names[g.group]:
                moved += g.weight * (1 - k)
                g.weight *= k
        if moved > 0:
            hips.add([v.index], moved + sum(g.weight for g in v.groups if g.group == hips.index), "REPLACE")


def _orient_out(bm, B):
    """Faces pointing away from the skin (a generated tube has no winding of its own)."""
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()
    if not any(e.is_boundary for e in bm.edges):             # a closed solid: recalc already points it outwards
        return
    s = 0.0
    for f in bm.faces:
        c = f.calc_center_median()
        hit = B.bvh.find_nearest(c, 0.5)
        if hit[0] is not None:
            s += (c - hit[0]).dot(f.normal)
    if s < 0:
        bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.normal_update()


def belt(B, col, p, name="D_Belt"):
    """A belt or sash: a band round the waist over everything under it, `width` tall, standing `thick` proud, with a
    buckle block at the front (material index 1). p: z (metres above the hip joint, scaled), width, over, buckle."""
    M = B.marks
    sc = M["height"] / 1.8
    zc = M["hipj_z"] + p.get("z", 0.09) * sc
    w = p.get("width", 0.035) * sc
    cols = 72
    cx, cy = 0.0, float(B.head("Hips")[1])
    inner = [_tree(o) for o in p.get("over", ())]
    Z = np.linspace(zc + w / 2, zc - w / 2, 4)
    R = np.zeros((len(Z), cols))
    for i, z in enumerate(Z):
        r = _ring_radius(B, (cx, cy), float(z), cols)
        for t in inner:
            for k in range(cols):
                a = 2 * math.pi * k / cols
                d = Vector((math.sin(a), -math.cos(a), 0.0))
                h = t.ray_cast(Vector((cx, cy, float(z))) + d * 0.7, -d, 0.7)
                if h[0] is not None:
                    r[k] = max(r[k], 0.7 - h[3])
        R[i] = r + p.get("gap", 0.004)
    Rm = R.max(axis=0)
    for _ in range(4):
        Rm = np.maximum(Rm, 0.5 * (np.roll(Rm, 1) + np.roll(Rm, -1)))
    th = p.get("thick", 0.004)
    bm = bmesh.new()
    rings = []
    for z, dr in ((Z[0], th), (Z[-1], th), (Z[-1], 0.0), (Z[0], 0.0)):    # a closed band: outer top, outer bottom, inner
        ring = []
        for k in range(cols):
            a = 2 * math.pi * k / cols
            r_ = Rm[k] + dr
            ring.append(bm.verts.new((cx + r_ * math.sin(a), cy - r_ * math.cos(a), float(z))))
        rings.append(ring)
    for j in range(4):
        A, Bn = rings[j], rings[(j + 1) % 4]
        for k in range(cols):
            bm.faces.new((A[k], A[(k + 1) % cols], Bn[(k + 1) % cols], Bn[k]))
    if p.get("buckle", True):
        bw = w * 1.15
        y0 = cy - Rm[0] - th
        res = bmesh.ops.create_cube(bm, size=1.0)
        for v in res["verts"]:
            v.co = Vector((v.co.x * bw * 0.9, y0 + (v.co.y - 0.5) * 0.005, zc + v.co.z * bw))
        for f in {f for v in res["verts"] for f in v.link_faces}:
            f.material_index = 1
    bm.normal_update()
    _orient_out(bm, B)
    ob = to_object(bm, B, name, col, rebind=True, smooth_weights=4)
    bm.free()
    return ob


def _rigid(bm, B, bone):
    """Every vertex 100% on one bone: a rigid piece (crown, plate) that moves with it and does not bend."""
    dl = _dl(bm)
    gi = next(i for i, g in enumerate(B.groups) if g.split(":")[-1] == bone)
    for v in bm.verts:
        v[dl].clear()
        v[dl][gi] = 1.0


def crown(B, col, p, name="D_Crown"):
    """A crown or circlet: a band round the skull above the ears, `points` spikes (0: a plain circlet), rigid on the
    Head bone; it sits on the head and changes nothing of it. p: height (band, metres scaled), points, spike, low."""
    sc = B.marks["height"] / 1.8
    top = float(B.co[:, 2].max())
    hz = float(B.head("Head")[2])
    z0 = top - p.get("low", 0.30) * (top - hz)
    h = p.get("height", 0.03) * sc
    spike = p.get("spike", 0.03) * sc
    npts = int(p.get("points", 5))
    cols = 60 if npts == 0 else npts * 12
    hy = float(B.head("Head")[1])
    sel = np.abs(B.co[:, 2] - z0) < 0.01
    cy = float(B.co[sel, 1].mean()) if sel.any() else hy
    R = np.max([_ring_radius(B, (0.0, cy), float(z), cols, reach=0.5) for z in np.linspace(z0, z0 + h, 4)], axis=0)
    R = R + p.get("gap", 0.004)
    for _ in range(4):
        R = np.maximum(R, 0.5 * (np.roll(R, 1) + np.roll(R, -1)))
    th = p.get("thick", 0.004) * sc
    bm = bmesh.new()

    def tip(k):
        if npts == 0:
            return 0.0
        ph = (k % 12) / 12.0
        return spike * max(0.0, 1 - abs(ph - 0.5) * 4)     # a spike in the middle of every twelfth
    rings = []
    for zf, dr, up in ((0, th, False), (1, th, True), (1, 0.0, True), (0, 0.0, False)):
        ring = []
        for k in range(cols):
            a = 2 * math.pi * k / cols
            z = z0 + h * zf + (tip(k) if up else 0.0)
            r_ = R[k] + dr + (0.15 * (tip(k)) if up else 0.0)     # spikes lean out a little
            ring.append(bm.verts.new((r_ * math.sin(a), cy - r_ * math.cos(a), z)))
        rings.append(ring)
    for j in range(4):
        A, Bn = rings[j], rings[(j + 1) % 4]
        for k in range(cols):
            bm.faces.new((A[k], A[(k + 1) % cols], Bn[(k + 1) % cols], Bn[k]))
    bm.normal_update()
    _orient_out(bm, B)
    _rigid(bm, B, "Head")
    ob = to_object(bm, B, name, col)
    bm.free()
    return ob


TEMPLATES = {"top": top, "trousers": trousers, "shoes": shoes, "skirt": skirt, "belt": belt, "crown": crown}


def _pc(name, fn, slot, palette, fabric, colour, p=None, over=(), template=None):
    return dict(name=name, fn=fn, slot=slot, palette=palette, fabric=fabric, colour=colour, p=p or {}, over=list(over),
                template=template or fn)


NAVY, DENIM, CHARCOAL, WHITE, CREAM, BROWN, BLACK = (0.05, 0.07, 0.16), (0.12, 0.2, 0.38), (0.09, 0.09, 0.1), \
    (0.85, 0.85, 0.83), (0.8, 0.72, 0.55), (0.22, 0.12, 0.06), (0.03, 0.03, 0.03)
# per body, per template: what the fit check showed each body needs (found by running it; see the fit reports).
# Seniors: the seat in `sit` moves the cloth bridged over it unless it takes its weights from the skin under it.
# Female_Adult: finer cloth over the bust (coarse triangles cut the skin between the breasts).
BODY_TUNE = {
    "top": {"Male_Senior": {"rebind": True}, "Female_Senior": {"rebind": True}, "Female_Adult": {"subdiv": 2},
            "Male_Kid": {"subdiv": 2}},          # Male_Kid: arms_forward brought the shoulder blade through coarse cloth
    "skirt": {"Male_Adult": {"ease": 0.016}},
    "trousers": {"Male_Senior": {"rebind": True}, "Female_Senior": {"rebind": True}},
    "lanyard": {"Female_Adult": {"drop": 0.04}, "Male_Kid": {"drop": 0.04}},
    "tie": {"Female_Senior": {"end": 0.15}, "Male_Kid": {"end": 0.15}},
}
OUTFITS = {
    "casual_tshirt_trousers": dict(
        title="T-shirt, trousers and trainers (generated from each body)", era=["modern"],
        tags=["casual", "t-shirt", "trousers", "trainers", "everyday"],
        pieces=[_pc("D_Trousers", "trousers", "bottom", "secondary", "woven", DENIM),
                _pc("D_Tshirt", "top", "top", "primary", "cotton", (0.7, 0.18, 0.12),
                    {"neck": "crew", "sleeve": 1.55, "hem_back": 0.035, "pelvis": 0.9, "hem_line": True}, over=["D_Trousers"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["cotton", "rubber"], [WHITE, (0.16, 0.16, 0.18)], {"style": "trainer"})]),
    "shirt_trousers": dict(
        per_body={"Male_Kid": {"D_Trousers": {"loops": False}}, "Male_Adult": {"D_Trousers": {"loops": False}}},   # sit: skin through the bars
        title="Long-sleeved collared shirt with buttons, trousers and leather shoes (office, generated per body)",

        era=["modern"], tags=["office", "shirt", "collar", "buttons", "trousers", "shoes", "smart"],
        pieces=[_pc("D_Shirt", "top", "top", "primary", ["cotton", "rubber"], [(0.42, 0.56, 0.82), (0.93, 0.93, 0.9)],
                    {"neck": "high", "sleeve": 2.93, "collar": True, "buttons": 6, "hem_mark": "hipj_z", "hem_off": 0.085,
                     "ease_hem": 0.009, "ease_cuff": 0.011, "cuffs": 0.045, "tucked": True}),
                _pc("D_Trousers", "trousers", "bottom", "secondary", "woven", CHARCOAL, {"ease_hem": 0.016, "loops": True}, over=["D_Shirt"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["leather", "rubber"], [(0.10, 0.05, 0.025), (0.03, 0.03, 0.03)],
                    {"tilt": 0.3, "style": "office", "heel": 0.008})]),
    "blouse_skirt": dict(
        per_body={"Female_Kid": {"D_Skirt": {"lap": 0.6, "smooth_w": 30}}, "Female_Senior": {"D_Skirt": {"lap": 0.8}}},
        title="Tucked blouse, pencil skirt with a back vent to just above the knee, and court shoes (office, generated per body)",
        era=["modern"], tags=["office", "blouse", "skirt", "pencil", "shoes", "smart"],
        pieces=[_pc("D_Blouse", "top", "top", "primary", ["cotton", "rubber"], [(0.92, 0.88, 0.8), (0.95, 0.95, 0.93)],
                    {"neck": "high", "sleeve": 2.6, "collar": True, "buttons": 5, "hem_mark": "hipj_z", "hem_off": 0.085,
                     "ease_hem": 0.009, "ease_cuff": 0.013, "cuffs": 0.04, "tucked": True}),
                _pc("D_Skirt", "skirt", "bottom", "secondary", "woven", NAVY,
                    {"length": 0.7, "flare": -0.5, "vent": 0.12, "panels": 0.95, "lap": 1.0}, over=["D_Blouse"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["leather", "rubber"], [(0.14, 0.05, 0.05), BLACK],
                    {"tilt": 0.45, "style": "office", "heel": 0.008})]),
    "blouse_trousers": dict(
        title="Tucked blouse, tailored trousers and court shoes (office, generated per body; the office outfit for women when a skirt is not wanted)",
        era=["modern"], tags=["office", "blouse", "trousers", "tailored", "shoes", "smart"],
        pieces=[_pc("D_Blouse", "top", "top", "primary", ["cotton", "rubber"], [(0.92, 0.88, 0.8), (0.95, 0.95, 0.93)],
                    {"neck": "high", "sleeve": 2.6, "collar": True, "buttons": 5, "hem_mark": "hipj_z", "hem_off": 0.085,
                     "ease_hem": 0.009, "ease_cuff": 0.013, "cuffs": 0.04, "tucked": True}),
                _pc("D_Trousers", "trousers", "bottom", "secondary", "woven", NAVY, {"ease_hem": 0.018, "loops": True}, over=["D_Blouse"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["leather", "rubber"], [(0.14, 0.05, 0.05), BLACK],
                    {"tilt": 0.45, "style": "office", "heel": 0.008})]),
    "dress_simple": dict(
        title="Simple dress (fitted bodice, short sleeves, skirt to above the knee) and shoes, generated per body",
        era=["modern"], tags=["dress", "casual", "summer", "shoes"],
        pieces=[_pc("D_DressSkirt", "skirt", "bottom", "primary", "cotton", (0.6, 0.12, 0.2), {"length": 0.85, "waist": 0.15, "flare": 0.3}),
                _pc("D_DressBodice", "top", "top", "primary", "cotton", (0.6, 0.12, 0.2),
                    {"neck": "scoop", "sleeve": 1.35, "hem_mark": "hipj_z", "hem_off": 0.12}, over=["D_DressSkirt"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["leather", "rubber"], [(0.35, 0.05, 0.08), BLACK], {"tilt": 0.5})]),
    # ---- the royal court (period: medieval). Rigid pieces (crown) sit on one bone.
    "king_robes": dict(
        title="King: velvet robe (skirt to the knee over wide velvet legs: reads as a long robe standing, parts when striding) with belt, ermine mantle, gold crown, boots (generated per body)",
        era=["medieval", "early_modern", "fairy_tale"], tags=["royal", "king", "court", "robe", "crown", "ermine"],
        pieces=[_pc("D_RobeLegs", "trousers", "bottom", "primary", "velvet", (0.13, 0.02, 0.17), {"ease_knee": 0.024, "ease_hem": 0.04, "slope": -0.05, "leg": 1.97}),
                _pc("D_Robe", "skirt", "bottom", "primary", "velvet", (0.13, 0.02, 0.17), {"length": 0.85, "flare": 0.3, "ease": 0.016}, over=["D_RobeLegs"]),
                _pc("D_Tunic", "top", "top", "primary", "velvet", (0.13, 0.02, 0.17), {"neck": "crew", "sleeve": 2.93, "hem": 1.7, "ease_cuff": 0.016}, over=["D_Robe"]),
                _pc("D_Belt", "belt", "belt", "accent", ["leather", "gold"], [BROWN, (1.0, 0.75, 0.3)], {"z": 0.12}, over=["D_Tunic", "D_Robe"]),
                _pc("D_Mantle", "top", "cloak", "fur", "fur", WHITE, {"neck": "crew", "sleeve": 1.25, "hem_mark": "armpit_z", "hem_off": -0.04,
                                                                     "ease_shoulder": 0.012, "ease_hem": 0.02, "thick": 0.005}, over=["D_Tunic"]),
                _pc("D_Crown", "crown", "head", "metal", "gold", (1.0, 0.78, 0.3), {"points": 5}),
                _pc("D_Boots", "shoes", "feet", "shoes", ["leather", "leather"], [BROWN, (0.1, 0.05, 0.02)], {"tilt": 0.3})]),
    "queen_gown": dict(
        per_body={"Female_Adult": {"D_Mantle": {"sleeve": 1.1}}, "Female_Senior": {"D_Mantle": {"neck": "crew"}}},   # arms_forward stretch
        title="Queen: gown (skirt to the knee over wide legs in the same velvet: reads long standing, parts when striding) with fitted bodice, ermine mantle, circlet crown, shoes (generated per body)",
        era=["medieval", "early_modern", "fairy_tale"], tags=["royal", "queen", "court", "gown", "crown", "ermine"],
        pieces=[_pc("D_GownLegs", "trousers", "bottom", "primary", "velvet", (0.05, 0.12, 0.4), {"ease_knee": 0.024, "ease_hem": 0.04, "slope": -0.05, "leg": 1.97}),
                _pc("D_Gown", "skirt", "bottom", "primary", "velvet", (0.05, 0.12, 0.4), {"length": 0.85, "flare": 0.4, "ease": 0.016, "waist": 0.14}, over=["D_GownLegs"]),
                _pc("D_Bodice", "top", "top", "primary", "velvet", (0.05, 0.12, 0.4), {"neck": "boat", "sleeve": 2.93, "hem_mark": "hipj_z", "hem_off": 0.13, "ease_cuff": 0.02}, over=["D_Gown"]),
                _pc("D_Belt", "belt", "belt", "accent", ["gold", "gold"], [(1.0, 0.78, 0.3), (1.0, 0.78, 0.3)], {"z": 0.14, "width": 0.02, "buckle": False}, over=["D_Bodice", "D_Gown"]),
                _pc("D_Mantle", "top", "cloak", "fur", "fur", WHITE, {"neck": "boat", "sleeve": 1.25, "hem_mark": "armpit_z", "hem_off": -0.03,
                                                                     "ease_shoulder": 0.012, "ease_hem": 0.02, "thick": 0.005}, over=["D_Bodice"]),
                _pc("D_Crown", "crown", "head", "metal", "gold", (1.0, 0.78, 0.3), {"points": 7, "spike": 0.02, "height": 0.02}),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["velvet", "leather"], [(0.05, 0.12, 0.4), BROWN], {"tilt": 0.5})]),
    "guard_tabard": dict(
        title="Castle guard: long-sleeved shirt, red tabard, hose, belt, boots (generated per body)",
        era=["medieval", "fairy_tale"], tags=["guard", "soldier", "court", "tabard", "medieval"],
        pieces=[_pc("D_Hose", "trousers", "legs", "tertiary", "woven", (0.12, 0.12, 0.14), {"ease_knee": 0.008, "ease_hem": 0.008, "slope": 0.0}),
                _pc("D_Shirt", "top", "top", "secondary", "linen", (0.55, 0.5, 0.42), {"neck": "crew", "sleeve": 2.93, "hem": 1.3}, over=["D_Hose"]),
                _pc("D_Tabard", "top", "over", "primary", "woven", (0.55, 0.05, 0.05), {"neck": "crew", "sleeve": 0.95, "hem": 0.3, "ease_hem": 0.03, "ease_shoulder": 0.010}, over=["D_Shirt", "D_Hose"]),
                _pc("D_Belt", "belt", "belt", "accent", ["leather", "iron"], [BROWN, (0.6, 0.6, 0.62)], {"z": 0.10}, over=["D_Tabard", "D_Shirt", "D_Hose"]),
                _pc("D_Boots", "shoes", "feet", "shoes", ["leather", "leather"], [BROWN, (0.1, 0.05, 0.02)], {"top": 0.12, "tilt": 0.0}, over=["D_Hose"])]),
    "knight_armour": dict(
        title="Knight: grey padded shirt (gambeson), steel breastplate (skinned plate, not bone-rigid), hose, belt, steel boots",
        era=["medieval", "fairy_tale"], tags=["knight", "armour", "court", "soldier", "medieval"],
        pieces=[_pc("D_Hose", "trousers", "legs", "tertiary", "woven", (0.15, 0.15, 0.17), {"ease_knee": 0.008, "ease_hem": 0.008, "slope": 0.0}),
                _pc("D_Mail", "top", "top", "secondary", "woven", (0.3, 0.3, 0.33), {"neck": "crew", "sleeve": 2.93, "hem": 0.9}, over=["D_Hose"]),
                _pc("D_Breastplate", "top", "armour", "metal", "steel", (0.75, 0.76, 0.8), {"neck": "crew", "sleeve": 0.95, "hem": 1.9, "ease_hem": 0.02, "ease_shoulder": 0.012, "thick": 0.004, "slope": -0.02}, over=["D_Mail"]),
                _pc("D_Belt", "belt", "belt", "accent", ["leather", "iron"], [BROWN, (0.6, 0.6, 0.62)], {"z": 0.04}, over=["D_Breastplate", "D_Mail", "D_Hose"]),
                _pc("D_Boots", "shoes", "feet", "shoes", ["steel", "iron"], [(0.75, 0.76, 0.8), (0.3, 0.3, 0.32)], {"top": 0.14, "tilt": 0.0}, over=["D_Hose"])]),
    "peasant_man": dict(
        title="Peasant man: linen shirt, breeches, rope-style belt, leather boots (generated per body)",
        era=["medieval", "early_modern", "fairy_tale"], tags=["peasant", "farmer", "villager", "medieval"],
        pieces=[_pc("D_Breeches", "trousers", "bottom", "secondary", "woven", (0.3, 0.22, 0.12), {"leg": 1.3, "ease_knee": 0.018}),
                _pc("D_Shirt", "top", "top", "primary", "linen", (0.75, 0.68, 0.52), {"neck": "boat", "sleeve": 2.9, "hem": 0.9, "ease_hem": 0.024}, over=["D_Breeches"]),
                _pc("D_Belt", "belt", "belt", "accent", ["leather", "leather"], [(0.3, 0.2, 0.1), (0.3, 0.2, 0.1)], {"z": 0.08, "width": 0.02, "buckle": False}, over=["D_Shirt", "D_Breeches"]),
                _pc("D_Boots", "shoes", "feet", "shoes", ["leather", "leather"], [(0.25, 0.14, 0.07), (0.1, 0.05, 0.02)], {"top": 0.2, "tilt": 0.0}, over=["D_Breeches"])]),
    "peasant_woman": dict(
        title="Peasant woman: linen blouse, skirt with apron panel over wide legs (reads long standing), shoes (generated per body)",
        era=["medieval", "early_modern", "fairy_tale"], tags=["peasant", "villager", "medieval", "apron"],
        pieces=[_pc("D_SkirtLegs", "trousers", "bottom", "secondary", "woven", (0.3, 0.22, 0.12), {"ease_knee": 0.024, "ease_hem": 0.04, "slope": -0.05, "leg": 1.97}),
                _pc("D_Skirt", "skirt", "bottom", "secondary", ["woven", "linen"], [(0.3, 0.22, 0.12), (0.8, 0.75, 0.62)], {"length": 0.85, "flare": 0.4, "ease": 0.016, "panel_arc": 110}, over=["D_SkirtLegs"]),
                _pc("D_Blouse", "top", "top", "primary", "linen", (0.75, 0.68, 0.52), {"neck": "boat", "sleeve": 2.6, "hem": 1.6}, over=["D_Skirt"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["leather", "leather"], [(0.25, 0.14, 0.07), (0.1, 0.05, 0.02)], {"tilt": 0.4})]),
    "kitchen_maid": dict(
        title="Kitchen maid: blouse, skirt with white apron panel over wide legs, apron band, shoes (generated per body)",
        era=["medieval", "early_modern", "fairy_tale"], tags=["maid", "servant", "kitchen", "court", "apron"],
        pieces=[_pc("D_SkirtLegs", "trousers", "bottom", "secondary", "woven", (0.2, 0.25, 0.35), {"ease_knee": 0.024, "ease_hem": 0.04, "slope": -0.05, "leg": 1.97}),
                _pc("D_Skirt", "skirt", "bottom", "secondary", ["woven", "cotton"], [(0.2, 0.25, 0.35), WHITE], {"length": 0.85, "flare": 0.4, "ease": 0.016, "panel_arc": 130, "panel_up": 0.01}, over=["D_SkirtLegs"]),
                _pc("D_Blouse", "top", "top", "primary", "linen", (0.82, 0.78, 0.7), {"neck": "crew", "sleeve": 2.4, "hem": 1.6}, over=["D_Skirt"]),
                _pc("D_Belt", "belt", "belt", "accent", ["cotton", "cotton"], [(0.55, 0.45, 0.3), (0.55, 0.45, 0.3)], {"z": 0.12, "width": 0.025, "buckle": False}, over=["D_Blouse", "D_Skirt"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["leather", "leather"], [(0.15, 0.08, 0.04), (0.08, 0.04, 0.02)], {"tilt": 0.4})]),
    "kid_tshirt_shorts": dict(
        title="T-shirt, shorts and trainers (generated per body; made for kids, fits every body)", era=["modern"],
        tags=["casual", "t-shirt", "shorts", "trainers", "kid", "summer"],
        pieces=[_pc("D_Shorts", "trousers", "bottom", "secondary", "woven", (0.25, 0.32, 0.18), {"leg": 0.8, "ease_knee": 0.02, "ease_hem": 0.022}),
                _pc("D_Tshirt", "top", "top", "primary", "cotton", (0.95, 0.75, 0.1),
                    {"neck": "crew", "sleeve": 1.5, "hem_back": 0.03, "pelvis": 0.9, "hem_line": True}, over=["D_Shorts"]),
                _pc("D_Shoes", "shoes", "feet", "shoes", ["cotton", "rubber"], [(0.1, 0.3, 0.7), (0.93, 0.93, 0.93)], {"style": "trainer"})]),
}


def build(outfit, B, col, params=None, body_key=None):
    """Build every piece of an outfit on body B, in order (inner layers first), dressed and labelled."""
    spec = OUTFITS[outfit]
    params = params or {}
    made = {}
    for pc in spec["pieces"]:
        p = dict(BODY_TUNE.get(pc["fn"], {}).get(body_key, {}))
        p.update(pc["p"])
        p.update((spec.get("per_body", {}).get(body_key, {}) or {}).get(pc["name"], {}))
        p.update({k.split(".", 1)[1]: v for k, v in params.items() if k.startswith(pc["name"] + ".")})
        p["over"] = [made[n] for n in pc["over"] if n in made]
        ob = TEMPLATES[pc["fn"]](B, col, p, name=pc["name"])
        kinds = pc["fabric"] if isinstance(pc["fabric"], list) else [pc["fabric"]]
        cols = pc["colour"] if isinstance(pc["colour"], list) else [pc["colour"]]
        mats = [fabric(k, c, pc["palette"] if i == 0 else f"{pc['palette']}_{i}") for i, (k, c) in enumerate(zip(kinds, cols))]
        dress(ob, pc["slot"], pc["palette"], mats, pc["template"])
        made[pc["name"]] = ob
    return list(made.values())


def registry_meta(outfit):
    spec = OUTFITS[outfit]
    deps = set()
    for pc in spec["pieces"]:
        for k in (pc["fabric"] if isinstance(pc["fabric"], list) else [pc["fabric"]]):
            if FABRIC_SRC.get(k):
                deps.add(FABRIC_SRC[k][0])
    return {"title": spec["title"],
            "pieces": {pc["name"]: {"slot": pc["slot"], "palette_slot": pc["palette"], "template": pc["template"],
                                    "fabric": pc["fabric"]} for pc in spec["pieces"]},
            "source": {"kind": "generated", "generator": "tools/blender/ajkit/templates.py", "command":
                       f"blender -b --factory-startup --python tools/chars_aj/fit.py -- custom {outfit} --bodies <list>",
                       "how": "cut from each body's own skin, offset with ease, hems and rims as geometry; fit-checked per body"},
            "licence": "own", "licence_evidence": "geometry generated by our own code; materials listed in depends_on",
            "depends_on": sorted(deps), "era": spec["era"], "tags": spec["tags"], "usable": True, "why_not": ""}


def rigged_meta(outfit, source):
    return {"title": outfit, "source": {"kind": "blenderkit_rigged", "prepared": str(source)}, "usable": True}


def limit_textures(px=2048):
    """No packed texture larger than px on its long side (the fit files carry their own textures)."""
    for im in bpy.data.images:
        w, h = im.size[:]
        if max(w, h) > px:
            k = px / max(w, h)
            im.scale(int(w * k), int(h * k))
            if im.packed_file:
                im.pack()


# ================================================================================================ add-ons
# An add-on is built over the outfit it goes with (that outfit is built first, checked together with it, and not kept
# in the add-on's file): library/wardrobe/addons/<Sex>_<Age>/<item>.blend holds only the add-on's own objects in this
# body's rest-pose frame, which is how aj_wardrobe._wear appends them (no armature, no body in the file).
def _face_weights(dl, fc, p):
    """Bone weights under point p: those of the cloth face fc, by inverse distance."""
    acc = {}
    iw = [1.0 / max((v.co - p).length, 1e-5) for v in fc.verts]
    tot = sum(iw)
    for v, wi in zip(fc.verts, iw):
        for k, wk in v[dl].items():
            acc[k] = acc.get(k, 0.0) + wk * wi / tot
    return acc


class _Cloth:
    """Another garment (an object already built) as something to lay bands on: a BVH of its surface and its vertex weights,
    keyed by this body's group order, so that a new vertex can take the weights of the cloth under it."""

    def __init__(self, ob, B):
        self.bvh = _tree(ob)
        me = ob.data
        self.polys = [tuple(p_.vertices) for p_ in me.polygons]
        self.co = [ob.matrix_world @ v.co for v in me.vertices]
        gmap = {g.index: B.groups.index(g.name) for g in ob.vertex_groups}
        self.w = [{gmap[g.group]: g.weight for g in v.groups} for v in me.vertices]

    def ray_cast(self, *a):
        return self.bvh.ray_cast(*a)

    def find_nearest(self, *a):
        return self.bvh.find_nearest(*a)

    def weights(self, fi, p):
        vs = self.polys[fi]
        iw = [1.0 / max((self.co[v] - p).length, 1e-5) for v in vs]
        tot = sum(iw)
        acc = {}
        for v, wi in zip(vs, iw):
            for k, wk in self.w[v].items():
                acc[k] = acc.get(k, 0.0) + wk * wi / tot
        return acc


def _w_under(tree, bm, dl, fi, p):
    if isinstance(tree, _Cloth):
        return tree.weights(fi, p)
    return _face_weights(dl, bm.faces[fi], p)


def strip(bm, tree, rows, direction=(0, 1, 0), reach=0.7, accept=None, mat=0, ncol=7):
    """A closed band laid on the cloth: top (standing `lift` off it), underside, edges. rows: [(centre_x, z, half_width,
    lift)] from top to bottom; each point is cast onto the cloth along `direction` from `reach` away. Every vertex takes the
    weights of the cloth under it, so the band moves with the chest and belly. Returns its vertices."""
    d = Vector(direction).normalized()
    bm.faces.ensure_lookup_table()
    dl = _dl(bm)
    T, Bm = [], []
    for cx, z, hw, lift in rows:
        tr, br = [], []
        for u in np.linspace(-1, 1, ncol):
            x = cx + u * hw
            hit = tree.ray_cast(Vector((x, -reach if d.y > 0 else reach, z)), d, reach * 2.5)
            if hit[0] is None or hit[1].dot(d) > -0.05 or (accept is not None and not accept(hit[0], hit[1])):
                tr.append(None); br.append(None)                 # nothing, or the inside of the far side seen through an opening
                continue
            n = hit[1].normalized()
            acc = _w_under(tree, bm, dl, hit[2], hit[0])
            a, b = bm.verts.new(hit[0] + n * lift), bm.verts.new(hit[0] + n * 0.0004)
            for v in (a, b):
                for k, wk in acc.items():
                    v[dl][k] = wk
            tr.append(a); br.append(b)
        T.append(tr); Bm.append(br)
    fs = []

    def quad(*vs):
        if all(v is not None for v in vs):
            try:
                fs.append(bm.faces.new(vs))
            except ValueError:
                pass
    for i in range(len(rows) - 1):
        for j in range(ncol - 1):
            quad(T[i][j], T[i + 1][j], T[i + 1][j + 1], T[i][j + 1])
            quad(Bm[i][j], Bm[i][j + 1], Bm[i + 1][j + 1], Bm[i + 1][j])
        quad(T[i][0], Bm[i][0], Bm[i + 1][0], T[i + 1][0])
        quad(T[i][-1], T[i + 1][-1], Bm[i + 1][-1], Bm[i][-1])
    for j in range(ncol - 1):
        quad(T[0][j], T[0][j + 1], Bm[0][j + 1], Bm[0][j])
        quad(T[-1][j], Bm[-1][j], Bm[-1][j + 1], T[-1][j + 1])
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    for f in fs:
        f.material_index = mat
    bm.normal_update()
    return [v for r in T + Bm for v in r if v is not None]


def _addon_bm():
    bm = bmesh.new()
    _dl(bm)
    return bm


def tie(B, col, p, name="D_Tie"):
    """A necktie: a knot under the collar, a blade that widens and ends in a point above the belt, laid on the shirt (cast
    onto it, standing 7 mm off it so the buttons stay under) so that it follows the chest and belly. p: over = [shirt]."""
    M = B.marks
    sc = M["height"] / 1.8
    tr = _Cloth(p["over"][0], B)
    bm = _addon_bm()
    z0 = M["neck_z"] - 0.022 * sc
    z1 = M["hipj_z"] + p.get("end", 0.100) * sc
    rows = []
    for t in np.linspace(0.0, 1.0, 24):
        z = z0 - t * (z0 - z1)
        if t < 0.09:                                          # the knot
            hw, lift = (0.011 + 0.018 * t) * sc, 0.0120 * sc
        elif t < 0.16:                                        # under the knot
            hw, lift = 0.0092 * sc, 0.0085 * sc
        else:                                                 # the blade widens, then comes to a point
            u = (t - 0.16) / 0.84
            hw = (0.0092 + 0.0165 * min(1.0, u / 0.45)) * sc * (1.0 - 0.85 * max(0.0, (u - 0.88) / 0.12))
            lift = 0.0078 * sc
        rows.append((0.0, z, hw, lift))
    strip(bm, tr, rows, accept=lambda pt, nr: pt.y < float(B.head("Hips")[1]) + 0.05)
    ob = to_object(bm, B, name, col)
    bm.free()
    return ob


def _band(bm, tree, run, w, h, dl):
    """A flat strap along a run of (point, normal) on the cloth; closed; weights of the cloth under each point."""
    if len(run) < 2:
        return
    bm.faces.ensure_lookup_table()
    rings = []
    for i, (p_, n) in enumerate(run):
        t = (run[min(i + 1, len(run) - 1)][0] - run[max(i - 1, 0)][0]).normalized()
        s_ = n.cross(t).normalized()
        ring = [bm.verts.new(p_ - s_ * w * 0.5 + n * 0.0004), bm.verts.new(p_ - s_ * w * 0.5 + n * h),
                bm.verts.new(p_ + s_ * w * 0.5 + n * h), bm.verts.new(p_ + s_ * w * 0.5 + n * 0.0004)]
        hit = tree.find_nearest(p_)
        acc = _w_under(tree, bm, dl, hit[2], p_) if hit[0] is not None else {}
        for v in ring:
            for k, wk in acc.items():
                v[dl][k] = wk
        rings.append(ring)
    fs = []
    for a, b in zip(rings[:-1], rings[1:]):
        for j in range(4):
            try:
                fs.append(bm.faces.new((a[j], a[(j + 1) % 4], b[(j + 1) % 4], b[j])))
            except ValueError:
                pass
    for ring in (rings[0], rings[-1]):
        try:
            fs.append(bm.faces.new(ring))
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    bm.normal_update()


def lanyard(B, col, p, name="D_Lanyard"):
    """A neck strap and the ID card at the chest: the strap runs round the back of the neck and comes down the chest in a V
    (skinned to the chest like the shirt under it); the card hangs from the point of the V, flat on the chest."""
    M = B.marks
    sc = M["height"] / 1.8
    tr = _Cloth(p["over"][0], B)
    bm = _addon_bm()
    dl = _dl(bm)
    cy = float(M["neck_y"])
    nr = M["neck_r"] + 0.030 * sc
    z_nk = M["neck_z"] + 0.004 * sc
    z_ct = M["armpit_z"] - p.get("drop", 0.075) * sc                         # the card's top edge
    w = 0.0135 * sc
    front = lambda pt, nr_: pt.y < float(B.head("Hips")[1]) + 0.05
    run = []                                                  # round the neck over the collar and shoulders: rays from above on a circle
    rc = M["neck_r"] + 0.042 * sc
    for a_ in np.linspace(48, 312, 40):
        a = math.radians(a_)
        pt = Vector((math.sin(a) * rc * 1.15, cy - math.cos(a) * rc, M["neck_z"] + 0.15))
        hit = tr.ray_cast(pt, Vector((0, 0, -1)), 0.5)
        if hit[0] is not None and hit[1].z > 0.35:
            run.append((hit[0].copy(), hit[1].normalized()))
    if p.get("neck_ring", False):                             # the strap round the back of the neck (fails the check near the nape on most bodies)
        _band(bm, tr, run, w, 0.0030 * sc, dl)
    for sx in (-1, 1):                                        # down the chest: neck corner to the top of the card
        x0 = sx * math.sin(math.radians(48)) * nr
        z0 = M["neck_z"] - 0.020 * sc
        strip(bm, tr, [(x0 * (1 - t), z0 - t * (z0 - z_ct), w * 0.5, 0.0024 * sc) for t in np.linspace(0, 1, 14)], accept=front, ncol=3)
    strip(bm, tr, [(0.0, z_ct - t * 0.088 * sc, 0.029 * sc, 0.0038 * sc) for t in np.linspace(0, 1, 8)], mat=1, accept=front)
    strip(bm, tr, [(0.0, z_ct + 0.012 * sc, 0.0055 * sc, 0.0030 * sc), (0.0, z_ct - 0.004 * sc, 0.0055 * sc, 0.0030 * sc)], accept=front, ncol=3)
    ob = to_object(bm, B, name, col)
    bm.free()
    return ob


def _tube(bm, pts, r, seg=8, closed=False):
    """A round tube along the points `pts`, capped at both ends (rigid pieces: frames, temples, bridges)."""
    P_ = [Vector(p) for p in pts]
    n = len(P_)
    rings = []
    for i, p_ in enumerate(P_):
        t = (P_[(i + 1) % n] - P_[i - 1]).normalized() if closed else (P_[min(i + 1, n - 1)] - P_[max(i - 1, 0)]).normalized()
        ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        u = t.cross(ref).normalized(); v_ = t.cross(u).normalized()
        rings.append([bm.verts.new(p_ + (u * math.cos(2 * math.pi * k / seg) + v_ * math.sin(2 * math.pi * k / seg)) * r) for k in range(seg)])
    fs = []
    for i in range(n if closed else n - 1):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(seg):
            fs.append(bm.faces.new((a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k])))
    if not closed:
        fs.append(bm.faces.new(list(reversed(rings[0])))); fs.append(bm.faces.new(rings[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    return fs


def _plain_object(bm, name, col):
    """A mesh object without armature or weights: a rigid add-on, which the loader bone-parents."""
    old = bpy.data.objects.get(name)
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    for p_ in me.polygons:
        p_.use_smooth = True
    return ob


def head_marks(B):
    """Top of the head and the chin (lowest point of the head in front of the neck), from the skin."""
    sel = np.array([d in ("Head", "HeadTop_End") for d in B.dom])
    pts = B.co[sel]
    front = pts[pts[:, 1] < B.marks["neck_y"] - 0.07]
    return float(B.co[:, 2].max()), float(front[:, 2].min())


def glasses(B, col, p, name="D_Glasses"):
    """Spectacles for this head: two round-cornered frames in front of the eyes, a bridge over the nose, temples that run
    along the side of the head to the ears. Placed from the head's own surface (rays at the eyes and round the skull at eye
    height) and rigid on the Head bone; the head is not touched. The eyes of every Aj head sit 38.5% of the way from the chin
    to the top and 0.0715 m either side of the middle at a head 0.336 m tall (measured on the front views), scaled by head size."""
    top, chin = head_marks(B)
    k = (top - chin) / 0.336
    ez = chin + 0.385 * (top - chin)
    ex = 0.0715 * k
    head = BVHTree.FromPolygons([Vector(v) for v in B.co], B.polys)
    bm = bmesh.new()
    tube_r = 0.0032 * k
    hw, hh = 0.049 * k, 0.037 * k
    centres = []
    ymin = 9.0
    for xs in np.linspace(-(ex + hw), ex + hw, 9):               # the front-most skin behind the lens plane: nose, brow, cheeks
        for zs in np.linspace(ez - hh, ez + hh + 0.02 * k, 6):
            hit = head.ray_cast(Vector((float(xs), -1.0, float(zs))), Vector((0, 1, 0)), 2.0)
            if hit[0] is not None:
                ymin = min(ymin, hit[0].y)
    yf = ymin - 0.007 * k
    for sx in (-1, 1):
        centres.append((sx * ex, yf, ez))
    fs = []
    for sx, (cx, cy_, cz) in zip((-1, 1), centres):
        ring = []
        for j in range(32):
            a = 2 * math.pi * j / 32
            ca, sa = math.cos(a), math.sin(a)
            ring.append((cx + hw * math.copysign(abs(ca) ** 0.75, ca), cy_, cz + 0.002 + hh * math.copysign(abs(sa) ** 0.75, sa)))
        fs += _tube(bm, ring, tube_r, 8, closed=True)
        c = bm.verts.new((cx, cy_, cz + 0.002))
        vs = [bm.verts.new(q) for q in ring]
        for j in range(32):
            bm.faces.new((c, vs[(j + 1) % 32], vs[j])).material_index = 1
    xi = ex - hw
    yb = centres[0][1]
    fs += _tube(bm, [(-xi, yb, ez + 0.012 * k), (-xi * 0.5, yb, ez + 0.019 * k), (0.0, yb, ez + 0.020 * k),
                     (xi * 0.5, yb, ez + 0.019 * k), (xi, yb, ez + 0.012 * k)], tube_r * 0.9, 8)
    zt = ez + 0.012 * k
    cy_h = float(B.head("Head")[1])
    for sx, (cx, cy_, cz) in zip((-1, 1), centres):
        pts = [(sx * (ex + hw), cy_, cz + 0.002 + hh * 0.35)]
        for a_ in np.linspace(math.degrees(math.asin(min(0.95, (ex + hw) / 0.20))), 80, 16):
            a = math.radians(a_)
            d = Vector((sx * math.sin(a), -math.cos(a), 0.0))
            hit = head.ray_cast(Vector((0.0, cy_h, zt)) + d * 0.8, -d, 0.8)
            if hit[0] is not None:
                q = hit[0] + d * (tube_r * 1.35)
                pts.append((q.x, q.y, zt))
        fs += _tube(bm, pts, tube_r * 0.85, 6)
    for f in fs:
        f.material_index = 0
    bm.normal_update()
    ob = _plain_object(bm, name, col)
    bm.free()
    return ob


def wrist_watch(B, col, p, name="D_Watch"):
    """A wrist watch on the left wrist, over the sleeve cuff: a strap round the forearm and a round case with a dark face on
    its outer side. Rigid on the LeftForeArm bone. The ring is measured from the skin and from the shirt under it (over)."""
    M = B.marks
    sc = M["height"] / 1.8
    a0, a1 = B.head("LeftForeArm"), B.head("LeftHand")
    ax = (a1 - a0) / np.linalg.norm(a1 - a0)
    c = a0 + (a1 - a0) * 0.84
    trees = [B.bvh] + [_tree(o) for o in p.get("over", ())]
    ref = np.array([1.0, 0.0, 0.0]); ref = ref - ax * (ref @ ax); ref /= np.linalg.norm(ref)
    side = np.cross(ax, ref)
    n = 28
    rad = np.zeros(n)
    for j in range(n):
        a = 2 * math.pi * j / n
        dirn = ref * math.cos(a) + side * math.sin(a)
        for t in trees:
            hit = t.ray_cast(Vector(c + dirn * 0.4), Vector(-dirn), 0.4)
            if hit[0] is not None:
                rad[j] = max(rad[j], float(np.dot(np.array(hit[0]) - c, dirn)))
    rad = np.maximum(rad, 0.02) + 0.0035 * sc
    for _ in range(3):
        rad = np.maximum(rad, 0.5 * (np.roll(rad, 1) + np.roll(rad, -1)))
    bm = bmesh.new()
    w, th = 0.0125 * sc, 0.0032 * sc
    rings = []
    for off, dr in ((-w, th), (w, th), (w, 0.0), (-w, 0.0)):
        rings.append([bm.verts.new(Vector(c + ax * off + (ref * math.cos(2 * math.pi * j / n) + side * math.sin(2 * math.pi * j / n)) * (rad[j] + dr)))
                      for j in range(n)])
    fs = []
    for j in range(4):
        a, b = rings[j], rings[(j + 1) % 4]
        for k in range(n):
            fs.append(bm.faces.new((a[k], a[(k + 1) % n], b[(k + 1) % n], b[k])))
    cen = c + ref * (rad[0] + th)
    R, h1, h2, seg = 0.0185 * sc, 0.0085 * sc, 0.0095 * sc, 24
    circ = lambda off, rr: [bm.verts.new(Vector(cen + ref * off + (ax * math.cos(2 * math.pi * j / seg) + side * math.sin(2 * math.pi * j / seg)) * rr))
                            for j in range(seg)]
    ba, bb, bc = circ(-0.002, R), circ(h1, R), circ(h2, R * 0.84)
    for j in range(seg):
        j2 = (j + 1) % seg
        fs.append(bm.faces.new((ba[j], ba[j2], bb[j2], bb[j])))
        fs.append(bm.faces.new((bb[j], bb[j2], bc[j2], bc[j])))
    fs.append(bm.faces.new(list(reversed(ba))))
    top = bm.faces.new(bc)
    fs.append(top)
    bmesh.ops.recalc_face_normals(bm, faces=fs)
    for f in fs:
        f.material_index = 0
    top.material_index = 1
    bm.normal_update()
    ob = _plain_object(bm, name, col)
    bm.free()
    return ob


# ---- the add-on table: base = the outfit it is built over (and checked with); kind rigid|skinned; bone for rigid ones
BELT_BROWN = (0.16, 0.08, 0.04)
ADDONS = {
    "belt": dict(
        title="Leather belt with a buckle, over trousers (tucked shirt)", base="shirt_trousers", kind="skinned", bone=None,
        covers=[], palette_slot="accent", era=["modern"], tags=["belt", "office", "smart"],
        pieces=[_pc("D_Belt", "belt", "belt", "accent", ["leather", "gold"], [BELT_BROWN, (0.85, 0.72, 0.35)],
                    {"z": 0.093, "width": 0.028}, over=["D_Trousers", "D_Shirt"])]),
    "tie": dict(
        title="Necktie, hanging from the collar down the placket over a shirt_trousers shirt", base="shirt_trousers",
        kind="skinned", bone=None, covers=[], palette_slot="accent", era=["modern"], tags=["tie", "office", "smart"],
        pieces=[_pc("D_Tie", "tie", "tie", "accent", "woven", (0.55, 0.05, 0.10), over=["D_Shirt"])]),
    "blazer": dict(
        title="Open blazer with lapels over a shirt", base="shirt_trousers", kind="skinned", bone=None, covers=[],
        palette_slot="jacket", era=["modern"], tags=["blazer", "jacket", "office", "smart"],
        pieces=[_pc("D_Blazer", "top", "jacket", "jacket", "woven", (0.07, 0.09, 0.17),
                    {"neck": "v", "sleeve": 2.97, "hem_mark": "hipj_z", "hem_off": 0.012, "ease_hem": 0.024, "ease_shoulder": 0.012,
                     "ease_cuff": 0.020, "thick": 0.0045, "hem_depth": 0.01, "open": (0.040, 0.085), "lapels": 0.14,
                     "pelvis": 1.0, "rebind": True},
                    over=["D_Shirt", "D_Trousers"], template="top")]),
    "cardigan": dict(
        title="Knitted cardigan, open at the front, over a shirt", base="shirt_trousers", kind="skinned", bone=None, covers=[],
        palette_slot="jacket", era=["modern"], tags=["cardigan", "knit", "casual", "warm"],
        pieces=[_pc("D_Cardigan", "top", "jacket", "jacket", "woven", (0.30, 0.38, 0.30),
                    {"neck": "v", "sleeve": 2.97, "hem_mark": "hipj_z", "hem_off": 0.012, "ease_hem": 0.030, "ease_shoulder": 0.014,
                     "ease_cuff": 0.024, "thick": 0.0055, "hem_depth": 0.012, "open": (0.014, 0.040), "pelvis": 1.0, "rebind": True},
                    over=["D_Shirt", "D_Trousers"], template="top")]),
    "lanyard_badge": dict(
        title="Neck lanyard with an ID card at the chest (strap and card skinned to the chest)", base="shirt_trousers",
        kind="skinned", bone=None, covers=[], palette_slot="accent", era=["modern"], tags=["lanyard", "badge", "office", "id"],
        pieces=[_pc("D_Lanyard", "lanyard", "lanyard", "accent", ["woven", "cotton"], [(0.05, 0.30, 0.65), (0.95, 0.95, 0.95)], over=["D_Shirt"])]),
    "glasses": dict(
        title="Round-cornered glasses, rigid on the Head bone, placed from each head's own surface", base=None, kind="rigid", bone="Head",
        covers=[], palette_slot="frame", era=["modern"], tags=["glasses", "spectacles", "face"],
        pieces=[_pc("D_Glasses", "glasses", "face", "frame", ["steel", "steel"], [(0.04, 0.04, 0.05), (0.7, 0.8, 0.9)])]),
    "wrist_watch": dict(
        title="Wrist watch on the left wrist, rigid on the LeftForeArm bone", base="shirt_trousers", kind="rigid", bone="LeftForeArm",
        covers=[], palette_slot="metal", era=["modern"], tags=["watch", "wrist", "accessory"],
        pieces=[_pc("D_Watch", "wrist_watch", "wrist", "metal", ["steel", "rubber"], [(0.62, 0.64, 0.68), (0.03, 0.03, 0.04)], over=["D_Shirt"])]),
}
TEMPLATES.update({"tie": tie, "lanyard": lanyard, "glasses": glasses, "wrist_watch": wrist_watch})


def _glass_material():
    m = bpy.data.materials.get("F_lens_glass")
    if m is not None:
        return m
    m = bpy.data.materials.new("F_lens_glass")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    gl = nt.nodes.new("ShaderNodeBsdfGlass"); gl.inputs["Roughness"].default_value = 0.02; gl.inputs["IOR"].default_value = 1.15
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader"); mx.inputs["Fac"].default_value = 0.35
    nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(gl.outputs[0], mx.inputs[2]); nt.links.new(mx.outputs[0], out.inputs["Surface"])
    m["fabric_source"] = "own"
    return m


def build_addon(item, B, col, params=None, body_key=None):
    """The add-on's base outfit first (inner layers, not kept), then the add-on's pieces over it. Returns (addon objects,
    base objects)."""
    spec = ADDONS[item]
    params = params or {}
    base = build(spec["base"], B, col, params, body_key) if spec.get("base") else []
    made = {o.name: o for o in base}
    mine = []
    for pc in spec["pieces"]:
        p = dict(BODY_TUNE.get(pc["fn"], {}).get(body_key, {}))
        p.update(pc["p"])
        p.update({k.split(".", 1)[1]: v for k, v in params.items() if k.startswith(pc["name"] + ".")})
        p["over"] = [made[n] for n in pc["over"] if n in made]
        ob = TEMPLATES[pc["fn"]](B, col, p, name=pc["name"])
        kinds = pc["fabric"] if isinstance(pc["fabric"], list) else [pc["fabric"]]
        cols = pc["colour"] if isinstance(pc["colour"], list) else [pc["colour"]]
        mats = [fabric(k, c, pc["palette"] if i == 0 else f"{pc['palette']}_{i}") for i, (k, c) in enumerate(zip(kinds, cols))]
        if pc["fn"] == "glasses":                             # the lens is glass, not a Principled colour (recolouring leaves it alone)
            mats[1] = _glass_material()
        dress(ob, pc["slot"], pc["palette"], mats, pc["template"])
        made[pc["name"]] = ob
        mine.append(ob)
    return mine, base


def addon_meta(item):
    spec = ADDONS[item]
    deps = set()
    for pc in spec["pieces"]:
        for k in (pc["fabric"] if isinstance(pc["fabric"], list) else [pc["fabric"]]):
            if FABRIC_SRC.get(k):
                deps.add(FABRIC_SRC[k][0])
    return {"title": spec["title"], "kind": spec["kind"], "bone": spec["bone"] or "Head", "covers": spec["covers"],
            "palette_slot": spec["palette_slot"], "built_over": spec.get("base"),
            "pieces": {pc["name"]: {"slot": pc["slot"], "palette_slot": pc["palette"], "template": pc["template"], "fabric": pc["fabric"]}
                       for pc in spec["pieces"]},
            "source": {"kind": "generated", "generator": "tools/blender/ajkit/templates.py",
                       "command": f"blender -b --factory-startup --python tools/chars_aj/fit.py -- addon {item} --bodies <list>",
                       "how": "built over its base outfit on each body and measured against it; the file holds only the add-on's own objects"},
            "licence": "own", "licence_evidence": "geometry generated by our own code; materials listed in depends_on",
            "depends_on": sorted(deps), "era": spec["era"], "tags": spec["tags"], "usable": True, "why_not": ""}
