# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/grips.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the armature and the body are function arguments (arm=, body=)
# instead of the fixed object names "Armature" / "Aj_Base_Body", so two Aj in one scene work. Without them the old
# names are used. No algorithm or limit constant is changed.
"""Hand grips for the Aj Mixamo rig: fingers that close on the real surface of the held object.

    import grips
    r = grips.hold("K_Scepter", side="Right", grip="power", at=0.30)   # handle across the palm, fist round it
    r = grips.hold("Pen", side="Right", grip="pen")                    # tripod: thumb + index pads, rests on middle
    r = grips.hold("Key", side="Right", grip="pinch")                  # between thumb and index pads
    grips.check("Pen", "Right")      # {"penetration_mm", "touching": [...], per finger gap/penetration}
    grips.release("Pen")             # un-parent; grips.open_hand("Right") relaxes the fingers

How it works (no physics engine, no helper objects):
- Finger joints flex about their local X axis (towards the palm, both hands) - measured on the rig.
  (The old pose.curl turned them about local Z, which bends the fingers sideways.)
- The object is put into the hand by a rule per grip type, computed from the posed hand bones
  (knuckle line, finger direction, palm normal), so it works in any arm pose and for both hands.
- Each finger then closes joint by joint, knuckle first, until its skin touches the object, the way a
  real hand wraps. The skin is the body's own vertices, skinned here with the same weights, and the
  object is its real mesh (BVH), so "touch" is exact and nothing passes through.
- The thumb is solved last: it reaches for the spot opposite the fingers without entering the object
  or the fingers.
- The object is bone-parented to the Hand bone, so it follows every pose and animation.
"""
import math
import bpy
import numpy as np
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree

P = "mixamorig:"
BODY = "Aj_Base_Body"
FINGERS = ("Index", "Middle", "Ring", "Pinky")
RAD = math.radians

# anatomical ranges, degrees. flex = local X; spread = local Z (sign mirrored on the left hand)
FLEX_MAX = {1: 88.0, 2: 108.0, 3: 78.0}
FLEX_MIN = {1: -20.0, 2: 0.0, 3: 0.0}
# thumb (right hand; Y and Z are mirrored for the left): Thumb1 x/y/z, Thumb2 x, Thumb3 x
# Thumb1 X lifts the thumb off the palm (palmar abduction), Z swings it across the palm towards the fingers,
# Y twists it (kept small: the web skin tears beyond ~25 degrees) - read off a rendered chart of the rig.
THUMB_LO = (-20.0, -25.0, -30.0, -10.0, -10.0)
THUMB_HI = (54.0, 25.0, 52.0, 72.0, 80.0)
SOFT = 0.0025        # metres the palm, the web and the ball of the thumb may press into a held object


def _arm(arm=None):
    return arm if arm is not None else bpy.data.objects["Armature"]


def _body(body=None):
    return body if body is not None else bpy.data.objects[BODY]


def _obj(o):
    return bpy.data.objects[o] if isinstance(o, str) else o


def _meshes(root):
    return [o for o in [root] + list(root.children_recursive) if o.type == "MESH" and not o.hide_render]


# --------------------------------------------------------------------------------------------- hand

class Hand:
    """Pure-math copy of one hand: finger FK and the hand's skin, so a grip can be solved without
    touching the scene. Finger angles live in self.q (bone -> [x, y, z] radians, XYZ euler)."""

    def __init__(self, side="Right", arm=None, body=None):
        self.side = side
        self.sgn = 1.0 if side == "Right" else -1.0
        arm = self.arm = _arm(arm)
        self.body = _body(body)
        bpy.context.view_layer.update()
        self.A = arm.matrix_world.copy()
        self.hand = P + side + "Hand"
        self.chains = {f: [P + f"{side}Hand{f}{i}" for i in (1, 2, 3, 4)] for f in ("Thumb",) + FINGERS}
        self.rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        self.pose0 = {b.name: b.matrix.copy() for b in arm.pose.bones}
        self.rel = {}
        for ch in self.chains.values():
            par = self.hand
            for n in ch:
                self.rel[n] = self.rest[par].inverted() @ self.rest[n]
                par = n
        self.q = {}
        for ch in self.chains.values():
            for n in ch[:3]:
                self.q[n] = list(arm.pose.bones[n].matrix_basis.to_euler("XYZ"))
        self.len = {n: arm.data.bones[n].length * self.A.to_scale()[0] for ch in self.chains.values() for n in ch}
        self._skin()

    # ---- kinematics
    def fk(self, q=None):
        """bone -> armature-space pose matrix for the hand and its fingers."""
        q = self.q if q is None else q
        M = {self.hand: self.pose0[self.hand]}
        for ch in self.chains.values():
            par = self.hand
            for n in ch:
                e = q.get(n)
                m = M[par] @ self.rel[n]
                if e is not None:
                    m = m @ Euler(e, "XYZ").to_matrix().to_4x4()
                M[n] = m
                par = n
        return M

    def world(self, M, bone):
        return self.A @ M[bone]

    def joint(self, M, bone):
        return (self.A @ M[bone]).translation

    def frame(self, M=None):
        """Hand frame in world: K (middle of the knuckle line), u (index -> pinky), f (along the fingers),
        n (out of the palm), plus the knuckle points."""
        M = M or self.fk()
        k = {F: self.joint(M, self.chains[F][0]) for F in FINGERS}
        w = self.joint(M, self.hand)
        u = (k["Pinky"] - k["Index"]).normalized()
        K = sum(k.values(), Vector()) / 4
        f = K - w
        f = (f - u * f.dot(u)).normalized()
        n = u.cross(f)
        if n.dot((self.A @ M[self.hand]).to_3x3().col[2]) < 0:
            n = -n
        return {"K": K, "u": u, "f": f, "n": n, "k": k, "wrist": w}

    # ---- skin (linear blend skinning, same weights as the Armature modifier)
    def _skin(self):
        body, arm = self.body, self.arm
        me = body.data
        deform = {b.name for b in arm.data.bones if b.use_deform}
        gname = {g.index: g.name for g in body.vertex_groups}
        mine = {self.hand} | {n for ch in self.chains.values() for n in ch}
        basis = me.shape_keys.key_blocks[0].data if me.shape_keys else me.vertices
        to_arm = self.A.inverted() @ body.matrix_world
        idx, co, wts = [], [], []
        bones = {}
        for v in me.vertices:
            ws = [(gname[g.group], g.weight) for g in v.groups if g.weight > 0 and gname.get(g.group) in deform]
            if not ws or not any(b in mine for b, _ in ws):
                continue
            tot = sum(w for _, w in ws)
            idx.append(v.index); co.append(tuple(to_arm @ basis[v.index].co))
            wts.append([(bones.setdefault(b, len(bones)), w / tot) for b, w in ws])
        self.vidx = np.array(idx)
        self.V = np.array(co)
        self.bones = list(bones)
        self.W = np.zeros((len(idx), len(bones)))
        K = max(len(ws) for ws in wts)
        self.slot_b = np.zeros((len(idx), K), dtype=int)      # influences in the vertex's own order
        self.slot_w = np.zeros((len(idx), K))                 # (dual-quaternion blending depends on it)
        for i, ws in enumerate(wts):
            for k, (b, w) in enumerate(ws):
                self.W[i, b] += w
                self.slot_b[i, k] = b; self.slot_w[i, k] = w
        am = next((m for m in body.modifiers if m.type == "ARMATURE"), None)
        self.dq = bool(am and am.use_deform_preserve_volume)   # the base body uses "Preserve Volume"
        self.dom = np.array([self.bones[j] for j in self.W.argmax(1)])
        self.Rinv = {b: self.rest[b].inverted() for b in self.bones}
        # per phalanx: vertices it dominates, and how far along the bone they sit (rest pose)
        self.seg = {}
        self.radius = {}
        self.tip_len = {}
        sc = self.A.to_scale()[0]
        for F, ch in self.chains.items():
            for j, n in enumerate(ch[:3], 1):
                ids = np.where(self.dom == n)[0]
                h = np.array(self.rest[n].translation); t = np.array((self.rest[n] @ Vector((0, self.arm.data.bones[n].length, 0))))
                ax = (t - h) / np.linalg.norm(t - h)
                s = (self.V[ids] - h) @ ax
                L = np.linalg.norm(t - h)
                perp = np.linalg.norm((self.V[ids] - h) - np.outer(s, ax), axis=1)
                self.seg[(F, j)] = (ids, s / L)
                self.radius[(F, j)] = float(np.median(perp)) * sc if len(ids) else 0.01
                if j == 3:
                    # leaf bones (Index4..Thumb4) are non-deforming, so phalanx-3 skin extends past the bone tail
                    self.tip_len[F] = float(s.max()) * sc if len(ids) else L * sc
        self.palm = np.where(self.dom == self.hand)[0]

    def skin(self, M, ids=None):
        """World positions of hand-skin vertices (all, or the given rows) for the pose matrices M."""
        V = self.V if ids is None else self.V[ids]
        A = np.array(self.A)
        chan = [(M[b] if b in M else self.pose0[b]) @ self.Rinv[b] for b in self.bones]
        if not self.dq:
            W = self.W if ids is None else self.W[ids]
            out = np.zeros_like(V)
            for j, D in enumerate(chan):
                w = W[:, j]
                if not w.any():
                    continue
                D = np.array(D)
                out += w[:, None] * (V @ D[:3, :3].T + D[:3, 3])
            return out @ A[:3, :3].T + A[:3, 3]
        # dual-quaternion skinning, as Blender's Armature modifier does with Preserve Volume
        Q = np.zeros((len(chan), 4)); T = np.zeros((len(chan), 4))
        for j, D in enumerate(chan):
            q = D.to_quaternion(); t = D.translation
            Q[j] = (q.w, q.x, q.y, q.z)
            T[j] = (-0.5 * (t.x * q.x + t.y * q.y + t.z * q.z),
                    0.5 * (t.x * q.w + t.y * q.z - t.z * q.y),
                    0.5 * (-t.x * q.z + t.y * q.w + t.z * q.x),
                    0.5 * (t.x * q.y - t.y * q.x + t.z * q.w))
        SB = self.slot_b if ids is None else self.slot_b[ids]
        SW = self.slot_w if ids is None else self.slot_w[ids]
        sq = np.zeros((len(V), 4)); st = np.zeros((len(V), 4))
        for k in range(SB.shape[1]):
            q = Q[SB[:, k]]; t = T[SB[:, k]]
            w = SW[:, k] * np.where((q * sq).sum(1) < 0, -1.0, 1.0)
            sq += w[:, None] * q; st += w[:, None] * t
        w, x, y, z = sq.T
        t0, t1, t2, t3 = st.T
        vx, vy, vz = V.T
        rx = (w * w + x * x - y * y - z * z) * vx + 2 * (x * y - w * z) * vy + 2 * (x * z + w * y) * vz
        ry = 2 * (x * y + w * z) * vx + (w * w - x * x + y * y - z * z) * vy + 2 * (y * z - w * x) * vz
        rz = 2 * (x * z - w * y) * vx + 2 * (y * z + w * x) * vy + (w * w - x * x - y * y + z * z) * vz
        tx = 2 * (-t0 * x + t1 * w - t2 * z + t3 * y)
        ty = 2 * (-t0 * y + t1 * z + t2 * w - t3 * x)
        tz = 2 * (-t0 * z - t1 * y + t2 * x + t3 * w)
        out = np.stack([rx + tx, ry + ty, rz + tz], 1) / (sq * sq).sum(1)[:, None]
        return out @ A[:3, :3].T + A[:3, 3]

    def closing_set(self, F, j):
        """Skin that must stop joint j of finger F: everything from that phalanx to the tip (the first
        third of the phalanx itself is left out - it is the knuckle web, not a contact surface)."""
        out = []
        for k in range(j, 4):
            ids, s = self.seg[(F, k)]
            out.append(ids[s > 0.33] if k == j else ids)
        return np.concatenate(out) if out else np.array([], dtype=int)

    def thumb_root(self):
        """Rows of the soft skin that moves with the thumb's first bone (ball of the thumb, web)."""
        t = self.chains["Thumb"]
        cols = [self.bones.index(b) for b in t[:3] if b in self.bones]
        w = self.W[:, cols].sum(1)
        hard = set(self.seg[("Thumb", 2)][0][self.seg[("Thumb", 2)][1] > 0.3]) | set(self.seg[("Thumb", 3)][0])
        return np.array([i for i in np.where(w > 0.25)[0] if i not in hard], dtype=int)

    def capsules(self, M, fingers=FINGERS):
        """[(a, b, radius)] world capsules of the given fingers' phalanges."""
        out = []
        for F in fingers:
            ch = self.chains[F]
            for j in (1, 2, 3):
                a = self.joint(M, ch[j - 1]); b = self.joint(M, ch[j])
                r = self.radius[(F, j)]
                if j == 3:
                    # extend the distal capsule to the actual fingertip skin length (minus endcap radius)
                    ab = b - a
                    if ab.length > 1e-6:
                        ext = max(ab.length, self.tip_len[F] - r)
                        b = a + ab.normalized() * ext
                out.append((np.array(a), np.array(b), r))
        return out

    # ---- pose in/out
    def set_flex(self, F, angles_deg, spread_deg=0.0):
        for j, a in enumerate(angles_deg, 1):
            n = self.chains[F][j - 1]
            self.q[n][0] = RAD(a)
            if j == 1:
                self.q[n][1] = 0.0
                self.q[n][2] = RAD(spread_deg) * self.sgn
            else:
                self.q[n][1] = self.q[n][2] = 0.0

    # Thumb pose = [lift, twist, swing, bend2, bend3] (radians):
    #   lift  = Thumb1 +X: off the palm (palmar abduction);  swing = Thumb1 Z: across the palm towards the fingers
    #   bend2/bend3 = the two end joints. On this rig +X there curls AWAY from the palm, so a bend is a turn
    #   about (-X) and Z mixed by self.thumb_axis = (towards the palm, towards the fingers).
    thumb_axis = (1.0, 0.0)

    def thumb_get(self):
        return list(getattr(self, "_thumb", [0.0] * 5))

    def thumb_set(self, x):
        t = self.chains["Thumb"]
        self._thumb = [float(a) for a in x]
        ax, az = self.thumb_axis
        self.q[t[0]] = [x[0], x[1] * self.sgn, x[2] * self.sgn]
        self.q[t[1]] = [-ax * x[3], 0.0, az * x[3] * self.sgn]
        self.q[t[2]] = [-ax * x[4], 0.0, az * x[4] * self.sgn]

    def apply(self):
        """Write the solved finger angles to the pose bones."""
        pb = self.arm.pose.bones
        for n, e in self.q.items():
            pb[n].rotation_mode = "XYZ"
            pb[n].rotation_euler = e
        bpy.context.view_layer.update()

    def angles_deg(self):
        return {n.replace(P, ""): [round(math.degrees(a), 1) for a in e] for n, e in self.q.items()}


# ----------------------------------------------------------------------------------------- collider

def _part_filter(o, me, part):
    """Return set of polygon indices matching `part` (object name or material name), or None for all."""
    if part is None or o.name == part or o.name.startswith(part + "."):
        return None
    mat_ids = {i for i, s in enumerate(o.material_slots) if s.material and s.material.name == part}
    if not mat_ids:
        return set()
    return {p.index for p in me.polygons if p.material_index in mat_ids}


_PARITY_AXES = (
    Vector((0.37, 0.61, 0.70)).normalized(),
    Vector((-0.71, 0.23, -0.67)).normalized(),
    Vector((0.12, -0.93, 0.35)).normalized(),
    Vector((0.88, -0.34, 0.33)).normalized(),
)
_RAY_DIRS = tuple(d for a in _PARITY_AXES for d in (a, -a))
_CLOSED_DIRS = _PARITY_AXES[:3]


def _ray_parity(bvh, q, rd, max_hits=64):
    """Return parity (0 even / 1 odd) of intersections along ray (q, rd)."""
    cnt = 0
    org = q
    for _ in range(max_hits):
        hl, _, _, _ = bvh.ray_cast(org, rd)
        if hl is None:
            break
        cnt += 1
        org = hl + rd * 1e-5
    return cnt & 1


def _antipodal_inside(bvh, q):
    """Strict-majority (>4/8) antipodal ray-parity inside test.

    A flat single-sided sheet gets at most 1 hit per antipodal pair (<=4/8 votes),
    while an inside point of an open cylinder/bowl gets odd parity along rays
    that hit the walls (>=5/8 when the walls enclose most solid angles).
    """
    votes = 0
    for r_i, rd in enumerate(_RAY_DIRS):
        votes += _ray_parity(bvh, q, rd)
        if votes >= 5:
            return True
        if votes + (7 - r_i) < 5:
            return False
    return votes >= 5


class Collider:
    """The held object as a signed-distance query: its real triangles (world space) plus optional
    solid cores (capsules).

    Detects penetration into closed, open, overlapping, unwelded, and inside-out meshes by
    welding split seams, splitting into connected islands, verifying surface normal orientation
    against antipodal ray parity, and checking per-island + combined ray parity."""

    def __init__(self, objs, cores=(), part=None):
        import bmesh
        dg = bpy.context.evaluated_depsgraph_get()
        all_verts, all_tris, tri_isl = [], [], []
        self.isl_bvhs, self.isl_closed, self.isl_orient = [], [], []
        isl_lo, isl_hi, open_lo, open_hi = [], [], [], []
        for o in objs:
            e = o.evaluated_get(dg)
            me = e.to_mesh()
            keep_polys = _part_filter(o, me, part)
            if keep_polys is not None and not keep_polys:
                e.to_mesh_clear()
                continue
            mw = o.matrix_world
            bm = bmesh.new()
            bm.from_mesh(me)
            e.to_mesh_clear()
            if keep_polys is not None:
                bm.faces.ensure_lookup_table()
                drop = [f for f in bm.faces if f.index not in keep_polys]
                if drop:
                    bmesh.ops.delete(bm, geom=drop, context="FACES")
            if not bm.faces:
                bm.free()
                continue
            bmesh.ops.transform(bm, matrix=mw, verts=bm.verts)
            # Weld UV/split-normal seams so open islands become closed where geometry actually meets
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
            degen = [f for f in bm.faces if f.calc_area() < 1e-12]
            if degen:
                bmesh.ops.delete(bm, geom=degen, context="FACES")
            if not bm.faces:
                bm.free()
                continue
            seen = set()
            islands = []
            for f in bm.faces:
                if f in seen:
                    continue
                stack = [f]
                isl = []
                seen.add(f)
                while stack:
                    cur = stack.pop()
                    isl.append(cur)
                    for ed in cur.edges:
                        for nf in ed.link_faces:
                            if nf not in seen:
                                seen.add(nf)
                                stack.append(nf)
                islands.append(isl)
            bm.verts.index_update()
            n_open_in_obj = 0
            obj_vs = []
            for isl in islands:
                isl_set = set(isl)
                edges = {ed for f in isl for ed in f.edges}
                nonman = any(len([lf for lf in ed.link_faces if lf in isl_set]) > 2 for ed in edges)
                bnd = any(len([lf for lf in ed.link_faces if lf in isl_set]) == 1 for ed in edges)
                is_cl = (not nonman) and (not bnd)
                if not nonman:
                    bmesh.ops.recalc_face_normals(bm, faces=isl)
                if not is_cl:
                    n_open_in_obj += 1
                vmap = {}
                ivs, itris = [], []
                for f in isl:
                    ifvs = []
                    for v in f.verts:
                        if v.index not in vmap:
                            vmap[v.index] = len(ivs)
                            ivs.append(v.co.copy())
                        ifvs.append(vmap[v.index])
                    for k in range(1, len(ifvs) - 1):
                        itris.append((ifvs[0], ifvs[k], ifvs[k + 1]))
                if not ivs or not itris:
                    continue
                ibvh = BVHTree.FromPolygons(ivs, itris)
                # Verify outward orientation on contiguous manifold islands for fast outside rejection
                orient = 0
                if not nonman:
                    contiguous = all(
                        ed.is_contiguous
                        for ed in edges
                        if len([lf for lf in ed.link_faces if lf in isl_set]) == 2
                    )
                    if contiguous:
                        if is_cl:
                            orient = 1
                        else:
                            step_f = max(1, len(isl) // 8)
                            eps = 0.0005
                            out_ok = flip_ok = tested = 0
                            for f in isl[::step_f][:8]:
                                f.normal_update()
                                c_f = f.calc_center_median()
                                n_f = f.normal
                                if n_f.length < 1e-6:
                                    continue
                                tested += 1
                                in_neg = _antipodal_inside(ibvh, c_f - n_f * eps)
                                in_pos = _antipodal_inside(ibvh, c_f + n_f * eps)
                                if in_neg and not in_pos:
                                    out_ok += 1
                                elif in_pos and not in_neg:
                                    flip_ok += 1
                            if tested >= 3 and out_ok == tested:
                                orient = 1
                            elif tested >= 3 and flip_ok == tested:
                                itris = [(a, c_, b_) for (a, b_, c_) in itris]
                                ibvh = BVHTree.FromPolygons(ivs, itris)
                                orient = 1
                isl_id = len(self.isl_bvhs)
                base = len(all_verts)
                all_verts.extend(ivs)
                obj_vs.extend(ivs)
                for a, b_, c_ in itris:
                    all_tris.append((a + base, b_ + base, c_ + base))
                    tri_isl.append(isl_id)
                arr = np.array([tuple(v) for v in ivs])
                isl_lo.append(arr.min(0) - 0.001)
                isl_hi.append(arr.max(0) + 0.001)
                self.isl_bvhs.append(ibvh)
                self.isl_closed.append(is_cl)
                self.isl_orient.append(orient)
            if n_open_in_obj >= 2 and obj_vs:
                arr = np.array([tuple(v) for v in obj_vs])
                open_lo.append(arr.min(0) - 0.001)
                open_hi.append(arr.max(0) + 0.001)
            bm.free()
        self.n_tris = len(all_tris)
        self.pts = np.array([tuple(v) for v in all_verts]) if all_verts else np.zeros((0, 3))
        self.tri_isl = tri_isl
        self.bvh = BVHTree.FromPolygons(all_verts, all_tris) if all_tris else None
        self._ilo = np.array(isl_lo) if isl_lo else np.zeros((0, 3))
        self._ihi = np.array(isl_hi) if isl_hi else np.zeros((0, 3))
        self._olo = np.array(open_lo) if open_lo else np.zeros((0, 3))
        self._ohi = np.array(open_hi) if open_hi else np.zeros((0, 3))
        self.bboxes = list(zip(isl_lo, isl_hi))
        self.cores = [(np.array(a), np.array(b), r) for a, b, r in cores]
        self.shift = Vector((0, 0, 0))        # the object has moved by this much since the BVH was built

    def _sd_q(self, q, cands, in_open_obj, best_so_far=1e9):
        loc, nor, idx, d = self.bvh.find_nearest(q)
        if loc is None:
            return 1e9
        if not cands and not in_open_obj:
            return d
        if len(cands) == 1 and not in_open_obj:
            cid = cands[0]
            if self.tri_isl[idx] == cid:
                if self.isl_orient[cid] == 1 and (q - loc).dot(nor) > 1e-6:
                    return d
                if best_so_far < 0.0 and -d >= best_so_far:
                    return d
            elif self.isl_orient[cid] == 1:
                iloc, inor, _, _ = self.isl_bvhs[cid].find_nearest(q)
                if iloc is not None and (q - iloc).dot(inor) > 1e-6:
                    return d
        active = []
        for cid in cands:
            if self.isl_orient[cid] == 1:
                if self.tri_isl[idx] == cid:
                    if (q - loc).dot(nor) > 1e-6:
                        continue
                else:
                    iloc, inor, _, _ = self.isl_bvhs[cid].find_nearest(q)
                    if iloc is not None and (q - iloc).dot(inor) > 1e-6:
                        continue
            active.append(cid)
        if not active and not in_open_obj:
            return d
        if active and not in_open_obj and all(self.isl_closed[i] for i in active):
            in_isls = []
            for cid in active:
                ibvh = self.isl_bvhs[cid]
                votes = 0
                for r_i, rd in enumerate(_CLOSED_DIRS):
                    votes += _ray_parity(ibvh, q, rd)
                    if votes >= 2:
                        in_isls.append(cid)
                        break
                    if votes + (2 - r_i) < 2:
                        break
            if in_isls:
                return -max(self.isl_bvhs[k].find_nearest(q)[3] for k in in_isls)
            return d
        in_isls = [cid for cid in active if _antipodal_inside(self.isl_bvhs[cid], q)]
        if in_isls:
            return -max(self.isl_bvhs[k].find_nearest(q)[3] for k in in_isls)
        if in_open_obj and _antipodal_inside(self.bvh, q):
            return -d
        return d

    def sd(self, p):
        """Signed distance of one world point (negative = inside)."""
        best = 1e9
        q = Vector(p) - self.shift
        if self.bvh is not None:
            qa = np.array(q)
            cands = list(np.where(((qa >= self._ilo) & (qa <= self._ihi)).all(1))[0]) if len(self._ilo) else []
            in_open = bool(len(self._olo) and ((qa >= self._olo) & (qa <= self._ohi)).all(1).any())
            best = self._sd_q(q, cands, in_open)
        if self.cores:
            qa = np.array(q)
            for a, b, r in self.cores:
                best = min(best, _seg_dist(qa, a, b) - r)
        return best

    def min_sd(self, X):
        if not len(X):
            return 1e9
        best = 1e9
        Q = X - np.array(self.shift)
        if self.bvh is not None:
            n = len(Q)
            imask = (
                ((Q[:, None, :] >= self._ilo[None, :, :]) & (Q[:, None, :] <= self._ihi[None, :, :])).all(2)
                if len(self._ilo)
                else np.zeros((n, 0), dtype=bool)
            )
            omask = (
                ((Q[:, None, :] >= self._olo[None, :, :]) & (Q[:, None, :] <= self._ohi[None, :, :])).all(2).any(1)
                if len(self._olo)
                else np.zeros(n, dtype=bool)
            )
            for i in range(n):
                cands = list(np.flatnonzero(imask[i])) if imask.shape[1] else []
                sd_i = self._sd_q(Vector(Q[i]), cands, bool(omask[i]), best)
                if sd_i < best:
                    best = sd_i
        if self.cores:
            for a, b, r in self.cores:
                ab = b - a
                t = np.clip((Q - a) @ ab / max(np.dot(ab, ab), 1e-12), 0.0, 1.0)
                d = float(np.linalg.norm(Q - (a + t[:, None] * ab), axis=1).min()) - r
                if d < best:
                    best = d
        return best


def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-12), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + t * ab)))


def _caps_sd(X, caps):
    """Smallest signed distance from points X to a set of capsules."""
    best = 1e9
    for a, b, r in caps:
        ab = b - a
        t = np.clip((X - a) @ ab / max(np.dot(ab, ab), 1e-12), 0.0, 1.0)
        d = np.linalg.norm(X - (a + t[:, None] * ab), axis=1) - r
        best = min(best, float(d.min()))
    return best


# ---------------------------------------------------------------------------------- object analysis

def shaft(root, at=0.5, axis=None, band=0.025, part=None):
    """Describe the long object `root` where it is held: {"g": grip point on the axis, "d": axis
    direction (world, towards the upper end), "radius", "length", "s": (min, max) along the axis}.

    at: 0..1 along the object from its lower end. axis: world direction, default = its longest direction.
    part: optional child mesh name or material name to isolate a handle inside a guarded/ornate prop."""
    root = _obj(root)
    dg = bpy.context.evaluated_depsgraph_get()
    pts, eds = [], []
    base = 0
    for o in _meshes(root):
        e = o.evaluated_get(dg); me = e.to_mesh()
        use_v = None
        if part is not None and o.name != part and not o.name.startswith(part + "."):
            mat_ids = {i for i, s in enumerate(o.material_slots) if s.material and s.material.name == part}
            if not mat_ids:
                e.to_mesh_clear()
                continue
            use_v = set()
            for poly in me.polygons:
                if poly.material_index in mat_ids:
                    use_v.update(poly.vertices)
            if not use_v:
                e.to_mesh_clear()
                continue
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co)
        ed = np.empty(len(me.edges) * 2, dtype=np.int32); me.edges.foreach_get("vertices", ed)
        e.to_mesh_clear()
        co = co.reshape(-1, 3)
        ed = ed.reshape(-1, 2)
        if use_v is not None:
            vlist = sorted(use_v)
            remap = {v: i for i, v in enumerate(vlist)}
            co = co[vlist]
            ed = np.array([[remap[a], remap[b]] for a, b in ed if a in remap and b in remap], dtype=np.int32)
            if not len(ed):
                ed = np.zeros((0, 2), dtype=np.int32)
        mw = np.array(o.matrix_world)
        pts.append(co @ mw[:3, :3].T + mw[:3, 3])
        eds.append(ed + base)
        base += len(co)
    if not pts:
        raise ValueError(f"{root.name}: no mesh geometry matched part={part!r}")
    X = np.concatenate(pts)
    E = np.concatenate(eds) if eds else np.zeros((0, 2), dtype=int)
    if axis is None:
        c = X.mean(0)
        _, _, vt = np.linalg.svd(X - c, full_matrices=False)
        d = vt[0]
        # orient: the end that is higher is "up"; for a level object, the end further from the lump of vertices
        if abs(d[2]) > 0.3:
            d = d if d[2] > 0 else -d
        else:
            s = (X - c) @ d
            d = d if (s.max() + s.min()) > 0 else -d
    else:
        d = np.array(Vector(axis).normalized())
    s = X @ d
    s0, s1 = float(s.min()), float(s.max())
    sa = s0 + at * (s1 - s0)
    e1 = np.cross(d, [0, 0, 1.0] if abs(d[2]) < 0.9 else [1.0, 0, 0]); e1 /= np.linalg.norm(e1)
    e2 = np.cross(d, e1)

    def section(sv):
        """Cross-section at height sv: where the mesh edges cross that plane (a long shaft has no
        vertices in its middle), plus the vertices lying within a few mm of it."""
        sa_, sb_ = s[E[:, 0]], s[E[:, 1]]
        m = ((sa_ - sv) * (sb_ - sv) < 0) & (np.abs(sa_ - sb_) > 1e-9)
        t = ((sv - sa_[m]) / (sb_[m] - sa_[m]))[:, None]
        Q = X[E[m, 0]] * (1 - t) + X[E[m, 1]] * t
        near = X[np.abs(s - sv) < 0.003]
        return np.concatenate([Q, near]) if len(near) else Q

    def centre(sv):
        Q = section(sv)
        if len(Q) < 3:
            return None, None
        a, b = Q @ e1, Q @ e2
        cen = e1 * (a.min() + a.max()) / 2 + e2 * (b.min() + b.max()) / 2 + d * sv
        return cen, 0.25 * ((a.max() - a.min()) + (b.max() - b.min()))
    g, R = centre(sa)
    if g is None:
        raise ValueError(f"{root.name}: nothing to hold at {at:.2f} of its length")
    # the handle's own direction where it is held (a bent or tilted handle differs from the whole object's axis)
    lo_c, _ = centre(max(s0 + 1e-4, sa - band)); hi_c, _ = centre(min(s1 - 1e-4, sa + band))
    if lo_c is not None and hi_c is not None and np.linalg.norm(hi_c - lo_c) > 1e-4:
        dl = (hi_c - lo_c) / np.linalg.norm(hi_c - lo_c)
        if dl @ d > 0.8:
            d = dl
    return {"g": Vector(g), "d": Vector(d), "radius": float(R), "length": s1 - s0, "s": (s0, s1), "sa": sa}


def roll_to_align(d0, ref0, d1, ref1):
    """Roll angle (degrees) about `d1` after minimal rotation `d0 -> d1` so vector `ref0` aligns with `ref1`
    in the plane perpendicular to `d1`. Useful for orienting sword guards, scepter faces, or mug handles."""
    d0 = Vector(d0).normalized(); d1 = Vector(d1).normalized()
    q = d0.rotation_difference(d1)
    r0 = q @ Vector(ref0)
    r0 = r0 - d1 * r0.dot(d1)
    r1 = Vector(ref1) - d1 * Vector(ref1).dot(d1)
    if r0.length < 1e-6 or r1.length < 1e-6:
        return 0.0
    r0.normalize(); r1.normalize()
    return math.degrees(math.atan2(d1.dot(r0.cross(r1)), r0.dot(r1)))


def _move(root, g0, d0, g1, d1, roll=0.0):
    """Rigidly move root so the line (g0, d0) lands on (g1, d1); roll (radians) about the new axis."""
    q = Vector(d0).rotation_difference(Vector(d1))
    Rm = q.to_matrix().to_4x4()
    if roll:
        Rm = Matrix.Rotation(roll, 4, Vector(d1)) @ Rm
    T = Matrix.Translation(Vector(g1)) @ Rm @ Matrix.Translation(-Vector(g0))
    root.matrix_world = T @ root.matrix_world
    bpy.context.view_layer.update()


def _unparent(root):
    bpy.context.view_layer.update()
    mw = root.matrix_world.copy()
    root.parent = None
    root.matrix_world = mw
    bpy.context.view_layer.update()


def _bone_parent(root, bone, arm=None):
    arm = _arm(arm)
    bpy.context.view_layer.update()
    mw = root.matrix_world.copy()
    root.parent = arm
    root.parent_type = "BONE"
    root.parent_bone = bone
    bpy.context.view_layer.update()
    root.matrix_world = mw
    bpy.context.view_layer.update()


# -------------------------------------------------------------------------------------- the closing

def close_finger(h, F, col, extra=None, margin=0.0, step=2.0, limits=None, joints=(1, 2, 3), couple=0.65):
    """Flex finger F joint by joint (knuckle first) until its skin is `margin` metres from the object.
    extra: optional function(points) -> signed distance to other things (the other fingers).
    Returns [(joint, degrees, touched)]."""
    limits = limits or FLEX_MAX
    ch = h.chains[F]
    out = []
    for j in joints:
        n = ch[j - 1]
        ids = h.closing_set(F, j)
        dip0 = math.degrees(h.q[ch[2]][0])

        def put(a):
            h.q[n][0] = RAD(a)
            if j == 2:                       # the last joint follows the middle one, as in a real finger
                h.q[ch[2]][0] = RAD(max(dip0, min(limits[3], couple * a)))

        def gap(a):
            put(a)
            X = h.skin(h.fk(), ids)
            d = col.min_sd(X)
            if extra is not None:
                d = min(d, extra(X))
            return d - margin
        a = math.degrees(h.q[n][0])
        hi = limits[j]
        touched = False
        if gap(a) <= 0:
            # already in contact: open until just free (or the joint's lower limit)
            lo = FLEX_MIN[j]
            b = a
            while b > lo and gap(b) <= 0:
                b = max(lo, b - step)
            a = b
            touched = True
            # then re-close precisely
            hi = min(hi, a + step)
        while a < hi:
            b = min(a + step, hi)
            if gap(b) <= 0:
                lo_, hi_ = a, b
                for _ in range(7):
                    m = (lo_ + hi_) / 2
                    if gap(m) <= 0:
                        hi_ = m
                    else:
                        lo_ = m
                a = lo_
                touched = True
                break
            a = b
        put(a)
        out.append((j, round(a, 1), touched))
    return out


def _nelder_mead(f, x0, step, iters=400):
    n = len(x0)
    S = [np.array(x0, float)] + [np.array(x0, float) + np.eye(n)[i] * step[i] for i in range(n)]
    fv = [f(x) for x in S]
    for _ in range(iters):
        o = np.argsort(fv); S = [S[i] for i in o]; fv = [fv[i] for i in o]
        c = sum(S[:-1]) / n
        xr = c + (c - S[-1]); fr = f(xr)
        if fr < fv[0]:
            xe = c + 2 * (c - S[-1]); fe = f(xe)
            S[-1], fv[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < fv[-2]:
            S[-1], fv[-1] = xr, fr
        else:
            xc = c + 0.5 * (S[-1] - c); fc = f(xc)
            if fc < fv[-1]:
                S[-1], fv[-1] = xc, fc
            else:
                S = [S[0]] + [S[0] + 0.5 * (x - S[0]) for x in S[1:]]
                fv = [fv[0]] + [f(x) for x in S[1:]]
    i = int(np.argmin(fv))
    return S[i], fv[i]


def thumb_pad(h, M, along=0.72):
    """World point on the pad of the thumb's last phalanx.

    On this rig Thumb2/Thumb3 curl toward local (-Z) for -X bend and (-X*sgn) for +Z*sgn bend,
    so the fleshy pad lies on the concave side (-az*sgn, 0, -ax), NOT +Z (which is the thumbnail side)."""
    t3 = h.chains["Thumb"][2]
    m = h.A @ M[t3]
    sc = h.A.to_scale()[0]
    L = h.tip_len["Thumb"] / sc
    r = h.radius[("Thumb", 3)] / sc
    ax, az = h.thumb_axis
    nrm = Vector((-az * h.sgn, 0.0, -ax))
    nrm = nrm.normalized() if nrm.length > 1e-6 else Vector((0.0, 0.0, -1.0))
    return m @ (Vector((0.0, L * along, 0.0)) + nrm * r)


def finger_pad(h, M, F, along=0.72):
    """World point on the palm-facing pad of finger F's last phalanx (local +Z)."""
    b = h.chains[F][2]
    m = h.A @ M[b]
    sc = h.A.to_scale()[0]
    L = h.tip_len[F] / sc
    r = h.radius[(F, 3)] / sc
    return m @ Vector((0.0, L * along, r))


def _tip_point(h, M, F, along=0.55):
    """World point on the axis of finger F's last phalanx, measured as a fraction of true skin length."""
    b = h.chains[F][2]
    m = h.A @ M[b]
    sc = h.A.to_scale()[0]
    L = h.tip_len[F] / sc
    return m @ Vector((0.0, L * along, 0.0))


def wrap_thumb(h, col, target, others=FINGERS, margin=0.0):
    """Power-grip thumb: wrap naturally across the palm and curl Thumb2/Thumb3 until the thumb tip
    rests cleanly on either the wrapped fingers or the object surface without penetrating either."""
    caps = [(a, b, r * 0.92) for a, b, r in h.capsules(h.fk(), others)]
    ids_dist = np.concatenate([h.seg[("Thumb", 2)][0][h.seg[("Thumb", 2)][1] > 0.3], h.seg[("Thumb", 3)][0]])
    ids_tip = h.seg[("Thumb", 3)][0]
    soft_ids = np.unique(np.concatenate([h.thumb_root(), h.seg[("Thumb", 1)][0]]))
    all_ids, inv = np.unique(np.concatenate([ids_dist, ids_tip, soft_ids]), return_inverse=True)
    n_d = len(ids_dist)
    n_t = len(ids_tip)
    idx_d = inv[:n_d]
    idx_t = inv[n_d:n_d + n_t]
    idx_s = inv[n_d + n_t:]
    sub_d = idx_d[::3]
    sub_t = idx_t[::2]
    sub_s = idx_s[::3]
    sub_u, sub_inv = np.unique(np.concatenate([all_ids[sub_d], all_ids[sub_t], all_ids[sub_s]]), return_inverse=True)
    sd_len = len(sub_d)
    st_len = len(sub_t)
    si_d = sub_inv[:sd_len]
    si_t = sub_inv[sd_len:sd_len + st_len]
    si_s = sub_inv[sd_len + st_len:]

    tgt = np.array(target)

    def put(x):
        h.thumb_axis = (math.sin(x[5]), math.cos(x[5]))
        h.thumb_set(x[:5])

    def eval_sub(x):
        put(x)
        M = h.fk()
        X = h.skin(M, sub_u)
        Xd = X[si_d]
        Xt = X[si_t]
        Xs = X[si_s]
        return (
            M,
            col.min_sd(Xd),
            col.min_sd(Xt),
            _caps_sd(Xd, caps) if caps else 1e9,
            _caps_sd(Xt, caps) if caps else 1e9,
            col.min_sd(Xs),
        )

    def eval_full(x):
        put(x)
        M = h.fk()
        X = h.skin(M, all_ids)
        Xd = X[idx_d]
        Xt = X[idx_t]
        Xs = X[idx_s]
        return (
            M,
            col.min_sd(Xd),
            col.min_sd(Xt),
            _caps_sd(Xd, caps) if caps else 1e9,
            _caps_sd(Xt, caps) if caps else 1e9,
            col.min_sd(Xs),
        )

    # First locate a guaranteed clear open pose so backoff never traps a wide handle against thumb root
    open_best = None
    for l0 in (52.0, 46.0, 38.0, 28.0):
        for z0 in (20.0, 35.0, 12.0, 6.0, 0.0, -5.0):
            cand = np.radians([l0, 0.0, z0, 8.0, 8.0, 75.0])
            _, d_od, _, d_cd, _, d_os = eval_full(cand)
            clear_dist = min(d_od - margin, d_cd)
            score = (0 if clear_dist >= 0 else 1, -min(clear_dist, d_os))
            if open_best is None or score < open_best[0]:
                open_best = (score, cand.copy(), d_os)
            if clear_dist >= 0 and d_os >= -0.0004:
                break
        if open_best[0][0] == 0 and open_best[2] >= -0.0004:
            break
    open_x = open_best[1]
    open_z_deg = math.degrees(open_x[2])
    soft_tol = max(0.0004, -open_best[2] + 0.0001)

    lo = np.radians([-15.0, -20.0, min(6.0, open_z_deg), 12.0, 12.0, 35.0])
    hi = np.radians([54.0, 20.0, 52.0, 72.0, 80.0, 90.0])

    def free_full(x):
        _, d_od, _, d_cd, _, d_os = eval_full(x)
        return min(d_od - margin, d_cd, d_os + soft_tol)

    def cost_sub(x):
        xc = np.clip(x, lo, hi)
        M, d_od, d_ot, d_cd, d_ct, d_os = eval_sub(xc)
        pad = np.array(thumb_pad(h, M))
        pen = min(d_od - margin, d_cd, d_os + soft_tol)
        tip_gap = max(0.0, min(d_ot - margin, d_ct))
        c = np.linalg.norm(pad - tgt) * 55.0
        c += 1.8 * tip_gap * 1000.0
        c += 7.0 * max(0.0, -pen) * 1000.0
        c += 0.35 * float((xc[3] - xc[4]) ** 2)
        c += 0.15 * float((xc[1] / RAD(20.0)) ** 2)
        c += 0.08 * float(max(0.0, xc[0] - RAD(38.0)) ** 2)
        c += 0.10 * float((xc[5] - RAD(75.0)) ** 2)
        c += 12.0 * float(np.sum(np.abs(x - xc)))
        return c

    # Stage 1: coarse grid over diverse wrap poses
    grid = []
    for l0 in (24.0, 36.0, 46.0):
        for z0 in (16.0, 32.0, 46.0):
            for b0, ax0 in ((35.0, 75.0), (52.0, 55.0)):
                cand = np.radians([l0, 0.0, z0, b0, b0, ax0])
                grid.append((cost_sub(cand), cand))
    grid.sort(key=lambda t: t[0])

    # Stage 2: refine top 2 seeds with short Nelder-Mead on subsampled skin
    best, fb = None, 1e18
    for _, s in grid[:2]:
        x, fx = _nelder_mead(cost_sub, s, np.radians([10, 8, 12, 14, 14, 15]), 75)
        if fx < fb:
            best, fb = x, fx
    x = np.clip(best, lo, hi)

    # Stage 3: smart full-vertex backoff + distal contact polish
    if free_full(x) < 0:
        lifted = x.copy()
        lifted[0] = hi[0]
        lifted[3] = min(x[3], RAD(15.0))
        lifted[4] = min(x[4], RAD(15.0))
        if free_full(lifted) >= 0:
            a, b = 0.0, 1.0
            for _ in range(14):
                m = (a + b) / 2
                if free_full(lifted + (x - lifted) * m) >= 0:
                    a = m
                else:
                    b = m
            x = lifted + (x - lifted) * a
        elif free_full(open_x) >= 0:
            a, b = 0.0, 1.0
            for _ in range(14):
                m = (a + b) / 2
                if free_full(open_x + (x - open_x) * m) >= 0:
                    a = m
                else:
                    b = m
            x = open_x + (x - open_x) * a
        else:
            x = open_x.copy()

    _, d_od, d_ot, d_cd, d_ct, _ = eval_full(x)
    tip_gap = min(d_ot - margin, d_ct)
    if tip_gap > 0.0004:
        for idx, step_deg in ((3, 2.5), (4, 2.5), (2, 2.5), (0, -2.5), (1, -2.5), (1, 2.5)):
            for _ in range(20):
                xn = x.copy()
                xn[idx] = np.clip(xn[idx] + RAD(step_deg), lo[idx], hi[idx])
                if abs(xn[idx] - x[idx]) < 1e-6:
                    break
                _, d_odn, d_otn, d_cdn, d_ctn, d_osn = eval_full(xn)
                fn = min(d_odn - margin, d_cdn, d_osn + soft_tol)
                gn = min(d_otn - margin, d_ctn)
                if fn < 0:
                    a, b = 0.0, 1.0
                    for _ in range(10):
                        m = (a + b) / 2
                        xm = x + (xn - x) * m
                        if free_full(xm) >= 0:
                            a = m
                        else:
                            b = m
                    xm = x + (xn - x) * a
                    _, _, d_otm, _, d_ctm, _ = eval_full(xm)
                    gm = min(d_otm - margin, d_ctm)
                    if gm < tip_gap:
                        x, tip_gap = xm, gm
                    break
                if gn < tip_gap - 1e-5:
                    x, tip_gap = xn, gn
                else:
                    break
            if tip_gap <= 0.0004:
                break

    put(x)
    M = h.fk()
    _, d_od, d_ot, d_cd, d_ct, _ = eval_full(x)
    return {
        "deg": [round(math.degrees(a), 1) for a in x[:5]],
        "axis_deg": round(math.degrees(x[5]), 1),
        "touched": bool(min(d_ot - margin, d_ct) <= 0.0015),
        "tip_to_obj_mm": round(d_ot * 1000, 2),
        "tip_to_fingers_mm": round(d_ct * 1000, 2),
        "pad_to_target_mm": round((thumb_pad(h, M) - Vector(target)).length * 1000, 1),
    }


def solve_thumb(h, col, target, others=FINGERS, margin=0.0, iters=300):
    """Precision-grip thumb: bring the pad to `target` (world) without entering the object or the
    other fingers. Solves lift, twist, swing, the two bends and which way the bends turn."""
    lo = np.append(np.radians(THUMB_LO), 0.0); hi = np.append(np.radians(THUMB_HI), math.pi / 2)
    caps = [(a, b, r * 0.85) for a, b, r in h.capsules(h.fk(), others)]
    ids = np.concatenate([h.seg[("Thumb", 2)][0][h.seg[("Thumb", 2)][1] > 0.3], h.seg[("Thumb", 3)][0]])
    soft_ids = h.thumb_root()
    tgt = np.array(target)

    def put(x):
        h.thumb_axis = (math.sin(x[5]), math.cos(x[5]))
        h.thumb_set(x[:5])

    def eval_sd(x):
        put(x)
        M = h.fk()
        X = h.skin(M, ids)
        d_obj = col.min_sd(X)
        d_cap = _caps_sd(X, caps) if caps else 1e9
        d_soft = col.min_sd(h.skin(M, soft_ids)) + SOFT if len(soft_ids) else 1e9
        return M, d_obj, d_cap, d_soft

    def free(x):
        _, d_obj, d_cap, d_soft = eval_sd(x)
        return min(d_obj - margin, d_cap, d_soft)

    def cost(x):
        xc = np.clip(x, lo, hi)
        M, d_obj, d_cap, d_soft = eval_sd(xc)
        pad = np.array(thumb_pad(h, M))
        pen = min(d_obj - margin, d_cap, d_soft)
        c = np.linalg.norm(pad - tgt) * 100.0                           # cm from target
        c += 0.35 * max(0.0, d_obj - margin) * 1000.0                   # encourage true surface touch
        c += 4.5 * max(0.0, -pen) * 1000.0                              # strong penalty per mm inside
        c += 0.15 * float(np.sum((xc[:5] / (hi[:5] - lo[:5])) ** 2))    # stay near relaxed thumb
        c += 0.25 * float((xc[3] - xc[4]) ** 2)                         # harmonious Thumb2/Thumb3 bend
        c += 10.0 * float(np.sum(np.abs(x - xc)))
        return c

    best, fb = None, 1e18
    seeds = ([28, 0, 22, 18, 18, 45], [40, 0, 36, 28, 28, 30], [18, 0, 12, 12, 12, 65],
             [42, 10, 18, 32, 32, 75])
    for seed in seeds:
        x, fx = _nelder_mead(cost, np.radians(seed), np.radians([10, 7, 10, 10, 10, 18]), min(iters, 200))
        if fx < fb:
            best, fb = x, fx
    x = np.clip(best, lo, hi)
    # 1. If penetrating, back off cleanly towards an open thumb via fine bisection
    if free(x) < 0:
        open_ = np.radians([46, 0, 0, 2, 2, 45])
        if free(open_) > 0:
            a, b = 0.0, 1.0
            for _ in range(16):
                m = (a + b) / 2
                if free(open_ + (x - open_) * m) >= 0:
                    a = m
                else:
                    b = m
            x = open_ + (x - open_) * a
    # 2. If there is a small remaining gap to the object, polish by closing gently until skin touches
    _, d_obj, _, _ = eval_sd(x)
    if d_obj > margin + 0.0002:
        for idx, step_deg in ((2, 1.5), (3, 1.5), (4, 1.5), (0, -1.5)):
            for _ in range(25):
                xn = x.copy()
                xn[idx] = np.clip(xn[idx] + RAD(step_deg), lo[idx], hi[idx])
                if abs(xn[idx] - x[idx]) < 1e-6:
                    break
                _, do_n, dc_n, ds_n = eval_sd(xn)
                if min(do_n - margin, dc_n, ds_n) < 0:
                    # bisect between x and xn for exact contact
                    a, b = 0.0, 1.0
                    for _ in range(10):
                        m = (a + b) / 2
                        xm = x + (xn - x) * m
                        if free(xm) >= 0:
                            a = m
                        else:
                            b = m
                    xm = x + (xn - x) * a
                    _, do_m, _, _ = eval_sd(xm)
                    if do_m < d_obj:
                        x, d_obj = xm, do_m
                    break
                if do_n < d_obj:
                    x, d_obj = xn, do_n
                else:
                    break
            if d_obj <= margin + 0.0002:
                break
    put(x)
    M = h.fk()
    pad = thumb_pad(h, M)
    return {"deg": [round(math.degrees(v), 1) for v in x[:5]], "bend_axis_deg": round(math.degrees(x[5]), 1),
            "pad_to_target_mm": round((pad - Vector(target)).length * 1000, 1),
            "gap_mm": round(max(0.0, col.min_sd(h.skin(M, ids))) * 1000, 2),
            "free_mm": round(free(x) * 1000, 2)}


# ------------------------------------------------------------------------------------------- grips

def _rest_on_palm(h, M, fr, p0, d, R, press=0.001, reach=0.08):
    """Lower a shaft (axis through p0 along d, radius R) onto the palm along -n until it rests on the
    palm skin. Returns the axis point. Call it with the thumb already lifted out of the way."""
    X = h.skin(M, h.palm)
    half = (fr["k"]["Pinky"] - fr["k"]["Index"]).length / 2 + 0.01
    X = X[np.abs((X - np.array(fr["K"])) @ np.array(fr["u"])) < half]
    n = np.array(fr["n"]); dd = np.array(d); p0 = np.array(p0)

    def clear(t):
        rel = X - (p0 + n * t)
        perp = rel - np.outer(rel @ dd, dd)
        return float(np.linalg.norm(perp, axis=1).min()) - R
    lo, hi = 0.0, reach                       # t = distance out of the knuckle plane
    if clear(hi) < 0:
        return Vector(p0 + n * hi)
    for _ in range(30):
        m = (lo + hi) / 2
        if clear(m) >= 0:
            hi = m
        else:
            lo = m
    return Vector(p0 + n * (hi - press))


def _grip_power(h, root, col_objs, at, axis, flip, roll, slant, margin, back=None, part=None, gather=0.0):
    """Handle across the palm under the knuckles, fingers wrapped round it, thumb over the fingers or handle."""
    spreads = {"Index": gather, "Middle": 0.25 * gather, "Ring": -0.25 * gather, "Pinky": -gather}
    for F in FINGERS:
        h.set_flex(F, (8, 8, 5), spreads[F])
    h.thumb_axis = (1.0, 0.0)                          # end joints hook towards the palm, over the handle
    h.thumb_set([RAD(48), 0.0, 0.0, RAD(6), RAD(6)])   # thumb lifted while the handle is laid in the palm
    M = h.fk()
    fr = h.frame(M)
    sh = shaft(root, at=at, axis=axis, part=part)
    R = sh["radius"]
    rf = float(np.mean([h.radius[(F, 1)] for F in FINGERS]))
    d = -fr["u"]                                       # the object's upper end goes to the thumb side
    if slant:
        d = Matrix.Rotation(RAD(slant) * h.sgn, 3, fr["n"]) @ d
    # Cap `back` so wide handles do not ride up onto the ball of the thumb (the palm is 2-4 cm thick there)
    back = back if back is not None else min(0.6 * (rf + R), 0.018)
    c = _rest_on_palm(h, M, fr, fr["K"] - fr["f"] * back, d, R)
    drop = (c - fr["K"]).dot(fr["n"]) - R
    d0 = -sh["d"] if flip else sh["d"]
    _move(root, sh["g"], d0, c, d, RAD(roll))
    col = Collider(col_objs)
    # When a guarded handle part is isolated (e.g. a sword hilt inside a knuckle bow), wrap the fingers
    # around the handle collider first so they curl INSIDE the guard instead of stopping on its outside,
    # then clear any contact with the full prop mesh.
    wrap_col = Collider(col_objs, part=part) if part is not None else col
    log = {}
    hard = np.concatenate([h.seg[(F, j)][0] for F in FINGERS for j in (1, 2, 3)])
    palm_and_root = np.unique(np.concatenate([h.palm, h.thumb_root(), h.seg[("Thumb", 1)][0]]))
    base_check = np.unique(np.concatenate([hard, palm_and_root]))
    for _ in range(6):
        for F in FINGERS:
            h.set_flex(F, (8, 8, 5), spreads[F])
            log[F] = close_finger(h, F, wrap_col, margin=margin)
        if wrap_col is not col:
            # Verify no finger penetrates the guard/knuckle bow; adjust flex and spread if needed
            for F in FINGERS:
                ids_f = np.concatenate([h.seg[(F, j)][0] for j in (1, 2, 3)])
                if col.min_sd(h.skin(h.fk(), ids_f)) < margin - 0.0004:
                    ch = h.chains[F]
                    q0 = [list(h.q[n]) for n in ch[:3]]
                    best_q = q0
                    best_sd = col.min_sd(h.skin(h.fk(), ids_f))
                    sp_sign = 1.0 if F in ("Index", "Middle") else -1.0
                    found_clean = False
                    for dsp in (0.0, 5.0 * sp_sign, 10.0 * sp_sign, 16.0 * sp_sign, -5.0 * sp_sign):
                        for d1 in (0, -8, -16, 8, 16, -24):
                            for d2 in (0, -10, -20, 10, 20, -32):
                                h.q[ch[0]][0] = np.clip(q0[0][0] + RAD(d1), RAD(FLEX_MIN[1]), RAD(FLEX_MAX[1]))
                                h.q[ch[0]][2] = np.clip(q0[0][2] + RAD(dsp) * h.sgn, RAD(-28), RAD(28))
                                h.q[ch[1]][0] = np.clip(q0[1][0] + RAD(d2), RAD(FLEX_MIN[2]), RAD(FLEX_MAX[2]))
                                h.q[ch[2]][0] = np.clip(q0[2][0] + RAD(0.6 * d2), RAD(FLEX_MIN[3]), RAD(FLEX_MAX[3]))
                                M_ = h.fk()
                                Xf = h.skin(M_, ids_f)
                                if wrap_col.min_sd(Xf) < margin - 0.0005:
                                    continue
                                sd_ = col.min_sd(Xf)
                                if sd_ > best_sd:
                                    best_sd = sd_
                                    best_q = [list(h.q[n]) for n in ch[:3]]
                                    if best_sd >= margin:
                                        found_clean = True
                                        break
                            if found_clean:
                                break
                        if found_clean:
                            break
                    for n, qv in zip(ch[:3], best_q):
                        h.q[n] = qv
        M_now = h.fk()
        inside = -wrap_col.min_sd(h.skin(M_now, base_check))
        if wrap_col is not col:
            inside = max(inside, -col.min_sd(h.skin(M_now, palm_and_root)))
        if inside < 0.0005:
            break
        col.shift += fr["n"] * inside
        if wrap_col is not col:
            wrap_col.shift += fr["n"] * inside
        root.matrix_world.translation += fr["n"] * inside
        c = c + fr["n"] * inside
    # Final per-finger polish if proximal phalanges still graze an irregular shaft
    for F in FINGERS:
        ids_f = np.concatenate([h.seg[(F, j)][0] for j in (1, 2, 3)])
        if col.min_sd(h.skin(h.fk(), ids_f)) < margin - 0.0004:
            ch = h.chains[F]
            for j_idx, min_deg in ((0, FLEX_MIN[1]), (1, FLEX_MIN[2])):
                if col.min_sd(h.skin(h.fk(), ids_f)) >= margin - 0.0003:
                    break
                n_b = ch[j_idx]
                cur = math.degrees(h.q[n_b][0])
                while cur > min_deg and col.min_sd(h.skin(h.fk(), ids_f)) < margin - 0.0003:
                    nxt = max(min_deg, cur - 1.0)
                    h.q[n_b][0] = RAD(nxt)
                    if col.min_sd(h.skin(h.fk(), ids_f)) >= margin - 0.0003:
                        lo_, hi_ = nxt, cur
                        for _ in range(8):
                            m = (lo_ + hi_) / 2
                            h.q[n_b][0] = RAD(m)
                            if col.min_sd(h.skin(h.fk(), ids_f)) >= margin - 0.0003:
                                lo_ = m
                            else:
                                hi_ = m
                        h.q[n_b][0] = RAD(lo_)
                        break
                    cur = nxt
    bpy.context.view_layer.update()
    # Thumb: wraps over Index/Middle on thin/medium shafts, or onto the thumb-facing side of wide handles
    M = h.fk()
    dists = [h.joint(M, h.chains[F][2]).lerp(h.joint(M, h.chains[F][3]), 0.45) for F in ("Index", "Middle")]
    dist_mid = dists[0].lerp(dists[1], 0.45)
    f_dir = (-fr["f"] * 0.65 + fr["n"] * 0.76).normalized()
    finger_pt = dist_mid + f_dir * (h.radius[("Index", 3)] + h.radius[("Thumb", 3)] * 0.65)
    u_mid = (h.joint(M, h.chains["Index"][0]) + h.joint(M, h.chains["Middle"][0])) / 2
    c_near = c + d * (u_mid - c).dot(d)
    h_dir = (-fr["f"] * 0.72 + fr["n"] * 0.69)
    h_dir = (h_dir - d * h_dir.dot(d)).normalized()
    handle_pt = c_near + h_dir * (R + h.radius[("Thumb", 3)] * 0.65)
    t_blend = min(1.0, max(0.0, ((dist_mid - c_near).dot(fr["f"]) - 0.008) / 0.022))
    target = finger_pt.lerp(handle_pt, t_blend)
    log["Thumb"] = wrap_thumb(h, col, target, margin=margin)
    return col, log, {"radius_mm": round(R * 1000, 1), "centre": c, "palm_drop_mm": round(drop * 1000, 1),
                      "thumb_blend": round(t_blend, 2),
                      "shaft": {k: (v if not isinstance(v, Vector) else [round(x, 4) for x in v]) for k, v in sh.items()}}


def _pad_dir(h, M, F, j=3):
    """World direction the pad (palm side) of phalanx j of finger F faces: bone local +Z."""
    return (h.A @ M[h.chains[F][j - 1]]).to_3x3().col[2].normalized()


def _phalanx_point(h, M, F, j=3, along=0.55):
    ch = h.chains[F]
    return h.joint(M, ch[j - 1]).lerp(h.joint(M, ch[j]), along)


def _fit_side_finger(h, F, col, base, scales=(0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3), spreads=(-10, -6, -3, 0, 4)):
    """A finger that supports the object with its side (the middle finger under a pen): try curl
    amounts and sideways angles, keep the pose that touches without entering."""
    ids = np.concatenate([h.seg[(F, j)][0] for j in (2, 3)])
    best = None
    for s in scales:
        for sp in spreads:
            h.set_flex(F, [min(FLEX_MAX[j + 1], a * s) for j, a in enumerate(base)], sp)
            d = col.min_sd(h.skin(h.fk(), ids))
            score = d if d >= 0 else 1.0 - d            # touching beats a gap beats being inside
            if best is None or score < best[0]:
                best = (score, s, sp, d)
    _, s, sp, d = best
    h.set_flex(F, [min(FLEX_MAX[j + 1], a * s) for j, a in enumerate(base)], sp)
    return {"curl": s, "spread_deg": sp, "gap_mm": round(d * 1000, 2)}


def reach_finger(h, F, target, col, start=(50, 60, 0.0), spread_lim=18.0, iters=200, along=0.65, bounds=None,
                 use_pad=False, margin=0.0, couple=0.58):
    """Pose finger F (knuckle bend, middle-joint bend with end joint coupled, sideways spread) so its
    distal phalanx reaches `target` and its actual skin touches `col` cleanly without penetrating."""
    ids = np.concatenate([h.seg[(F, j)][0] for j in (2, 3)])
    all_ids = np.concatenate([h.seg[(F, j)][0] for j in (1, 2, 3)])
    tgt = np.array(target)
    b = bounds or ((FLEX_MIN[1], FLEX_MAX[1]), (0.0, FLEX_MAX[2]))
    lo = np.array([b[0][0], b[1][0], -spread_lim]); hi = np.array([b[0][1], b[1][1], spread_lim])
    s0 = (start[0], start[1], start[2] if len(start) > 2 else 0.0)

    def put(x):
        h.set_flex(F, (x[0], x[1], min(FLEX_MAX[3], couple * x[1])), x[2])

    def pt(M):
        return np.array(finger_pad(h, M, F, along) if use_pad else _tip_point(h, M, F, along))

    def skin_sd(x):
        put(x)
        M = h.fk()
        return M, col.min_sd(h.skin(M, ids)), col.min_sd(h.skin(M, all_ids))

    def cost(x):
        xc = np.clip(x, lo, hi)
        M, sd, sd_all = skin_sd(xc)
        p = pt(M)
        c = np.linalg.norm(p - tgt) * 100.0
        c += 0.45 * max(0.0, sd - margin) * 1000.0                      # pull skin into actual contact
        c += 4.5 * max(0.0, margin - sd) * 1000.0                       # strong penalty for entering object
        c += 3.0 * max(0.0, margin - sd_all - 0.0005) * 1000.0          # guard proximal phalanx too
        c += 10.0 * float(np.abs(x - xc).sum()) + 0.002 * abs(xc[2])
        return c

    x, _ = _nelder_mead(cost, np.array(s0, float), np.array([10.0, 12.0, 6.0]), iters)
    x = np.clip(x, lo, hi)
    # 1. If penetrating, back off smoothly along PIP (then MCP / spread) with bisection
    _, sd, sd_all = skin_sd(x)
    if min(sd, sd_all) < margin:
        for idx, direction in ((1, -1.0), (0, -1.0), (2, -1.0 if x[2] >= 0 else 1.0)):
            if min(sd, sd_all) >= margin:
                break
            x_prev = x.copy()
            for _ in range(35):
                xn = x.copy()
                xn[idx] = np.clip(xn[idx] + direction * 1.5, lo[idx], hi[idx])
                if abs(xn[idx] - x[idx]) < 1e-6:
                    break
                _, sd_n, sda_n = skin_sd(xn)
                if min(sd_n, sda_n) >= margin:
                    # bisect between x (inside) and xn (clear) to sit right on the surface
                    a, b_ = 0.0, 1.0
                    for _ in range(10):
                        m = (a + b_) / 2
                        xm = x + (xn - x) * m
                        _, sdm, sdam = skin_sd(xm)
                        if min(sdm, sdam) >= margin:
                            b_ = m
                        else:
                            a = m
                    x = x + (xn - x) * b_
                    _, sd, sd_all = skin_sd(x)
                    break
                x, sd, sd_all = xn, sd_n, sda_n
            if min(sd, sd_all) < margin:
                x = x_prev
                _, sd, sd_all = skin_sd(x)
    # 2. If still slightly short of contact, close along whichever DOF reduces gap cleanly
    if sd > margin + 0.00025:
        for idx, step_deg in ((1, 1.5), (0, 1.5), (2, 1.5), (2, -1.5)):
            for _ in range(20):
                xn = x.copy()
                xn[idx] = np.clip(xn[idx] + step_deg, lo[idx], hi[idx])
                if abs(xn[idx] - x[idx]) < 1e-6:
                    break
                _, sd_n, sda_n = skin_sd(xn)
                if min(sd_n, sda_n) < margin:
                    a, b_ = 0.0, 1.0
                    for _ in range(10):
                        m = (a + b_) / 2
                        xm = x + (xn - x) * m
                        _, sdm, sdam = skin_sd(xm)
                        if min(sdm, sdam) >= margin:
                            a = m
                        else:
                            b_ = m
                    xm = x + (xn - x) * a
                    _, sdm, sdam = skin_sd(xm)
                    if sdm < sd:
                        x, sd, sd_all = xm, sdm, sdam
                    break
                if sd_n < sd - 1e-5:
                    x, sd, sd_all = xn, sd_n, sda_n
                else:
                    break
            if sd <= margin + 0.00025:
                break
    M, sd, _ = skin_sd(x)
    p = pt(M)
    return {"deg": [round(float(v), 1) for v in x], "to_target_mm": round(float(np.linalg.norm(p - tgt)) * 1000, 1),
            "gap_mm": round(sd * 1000, 2)}


def _grip_pen(h, root, col_objs, at, axis, flip, roll, slant, margin):
    """Writing (tripod) grip: the pen rests on the side of the curled middle finger, its upper barrel
    leans back into the thumb-index web, the index pad presses down on top, and the thumb pad closes
    the tripod from the opposite side. at = metres from the tip."""
    at = 0.032 if at is None else at
    # natural tripod posture: middle curled underneath supporting, index arched over top, ring/pinky tucked
    idx_base = (44.0, 50.0, 28.0)
    mid_base = (56.0, 62.0, 36.0)
    h.set_flex("Index", idx_base, 8.0)
    h.set_flex("Middle", mid_base, -18.0)
    h.set_flex("Ring", (68.0, 80.0, 44.0), -8.0)
    h.set_flex("Pinky", (74.0, 84.0, 48.0), -4.0)
    h.thumb_axis = (0.7, 0.7)
    h.thumb_set([RAD(45), 0.0, 0.0, 0.0, 0.0])
    M = h.fk()
    fr = h.frame(M)
    whole = shaft(root, at=0.5, axis=axis)
    L = whole["length"]
    frac = min(0.95, max(0.02, at / L))
    sh = shaft(root, at=(1 - frac) if flip else frac, axis=whole["d"])
    R = sh["radius"]
    d0 = -sh["d"] if flip else sh["d"]                    # tip -> back end
    r3, r1 = h.radius[("Index", 3)], h.radius[("Index", 1)]
    rm = h.radius[("Middle", 3)]
    # Place the grip point C1 resting directly on the radial/upper side of the middle finger,
    # positioned so the index pad sits naturally on top of the pen (not purely beside it).
    Pm = _tip_point(h, M, "Middle", 0.48)
    Pi = finger_pad(h, M, "Index", 0.70)
    dir_m = (Pi - Pm)
    # bias slightly toward the palm (+fr["n"]) so the index fingertip pad lands on top of the barrel
    dir_m = (dir_m + fr["n"] * (dir_m.length * 0.25)).normalized()
    C1 = Pm + dir_m * (rm + R)
    p1 = (h.joint(M, h.chains["Index"][1]) - fr["k"]["Index"]).normalized()
    side_out = -fr["u"]                                    # towards the thumb side of the hand
    # upper barrel rests in the thumb-index web, just dorsal to the index knuckle line
    C2 = fr["k"]["Index"] + p1 * 0.014 + side_out * (r1 + R + 0.002) - fr["n"] * 0.005
    soft = np.concatenate([h.palm, h.seg[("Index", 1)][0], h.thumb_root()])
    mid_ids = np.concatenate([h.seg[("Middle", j)][0] for j in (2, 3)])
    inv = root.matrix_world.inverted()
    g_loc = inv @ sh["g"]                                  # grip point and axis in the pen's own space
    d_loc = inv.to_3x3() @ d0
    col = None
    d1 = (C2 - C1).normalized()
    for it in range(6):
        d1 = (C2 - C1).normalized()
        mw = root.matrix_world
        _move(root, mw @ g_loc, (mw.to_3x3() @ d_loc).normalized(), C1, d1, RAD(roll) if it == 0 else 0.0)
        col = Collider(col_objs, cores=[(C1 - d1 * at * 0.6, C1 + d1 * 0.06, R * 0.8)])
        moved = False
        # seat C1 snugly against the middle finger's actual skin (neither floating nor penetrating)
        dm = col.min_sd(h.skin(M, mid_ids))
        if abs(dm - margin) > 0.0004:
            dir_perp = (dir_m - d1 * dir_m.dot(d1)).normalized()
            C1 = C1 - dir_perp * (dm - margin)
            moved = True
        # clear the web/palm/index-root soft tissue
        inside = -col.min_sd(h.skin(M, soft))
        if inside > 0.0005:
            out_v = (side_out - fr["n"] * 0.35).normalized()
            C2 = C2 + out_v * (inside - 0.0003)
            moved = True
        if not moved:
            break
    # Bring the index fingertip pad cleanly onto the top (dorsal-index side) of the pen
    idx_dir = (Pi - C1)
    idx_dir = (idx_dir - d1 * idx_dir.dot(d1)).normalized()
    log = {"Index": reach_finger(h, "Index", C1 + idx_dir * R, col, start=(idx_base[0], idx_base[1], 8.0),
                                 spread_lim=20.0, iters=150, along=0.70, bounds=((25, 74), (28, 76)),
                                 use_pad=True, margin=margin)}
    # Polish the middle finger onto the pen so it touches cleanly with zero penetration
    mid_dir = (Pm - C1)
    mid_dir = (mid_dir - d1 * mid_dir.dot(d1)).normalized()
    log["Middle"] = reach_finger(h, "Middle", C1 - d1 * 0.004 + mid_dir * (R + rm), col,
                                 start=(mid_base[0], mid_base[1], -18.0), spread_lim=22.0, iters=150, along=0.48,
                                 bounds=((35, 85), (38, 92)), use_pad=False, margin=margin)
    for F in ("Ring", "Pinky"):                            # tucked fingers must not enter the pen either
        ids_ = np.concatenate([h.seg[(F, j)][0] for j in (1, 2, 3)])
        k_ = 0
        while col.min_sd(h.skin(h.fk(), ids_)) < margin and k_ < 30:
            n1 = h.chains[F][0]
            h.q[n1][0] += RAD(2); k_ += 1
    M = h.fk()
    # Thumb closes the 3rd side of the tripod, opposing the midpoint of index and middle contacts
    Ct = C1 + d1 * 0.004
    pi_now = finger_pad(h, M, "Index", 0.70)
    pm_now = _tip_point(h, M, "Middle", 0.48)
    v_i = (pi_now - Ct); v_i = (v_i - d1 * v_i.dot(d1)).normalized()
    v_m = (pm_now - Ct); v_m = (v_m - d1 * v_m.dot(d1)).normalized()
    w = -(v_i + v_m)
    w = (w - d1 * w.dot(d1))
    if w.length < 1e-4:
        w = Vector(d1).cross(v_i)
    w.normalize()
    if w.dot(h.joint(M, h.chains["Thumb"][0]) - Ct) < 0:
        w = -w
    target = Ct + w * (R + margin)
    log["Thumb"] = solve_thumb(h, col, target, margin=margin)
    tip = C1 - d1 * at
    return col, log, {"radius_mm": round(R * 1000, 1), "tip": tip, "axis": d1, "grip_point": C1}


def _grip_pinch(h, root, col_objs, at, axis, flip, roll, slant, margin):
    """Small or flat thing (key, card, coin, flower stem) between the thumb pad and the index pad."""
    h.set_flex("Index", (42, 52, 26), -4)
    h.set_flex("Middle", (62, 74, 42), 4)
    h.set_flex("Ring", (70, 82, 46), 2)
    h.set_flex("Pinky", (74, 86, 50), 0)
    h.thumb_axis = (0.7, 0.7)
    h.thumb_set([RAD(45), 0.0, 0.0, 0.0, 0.0])
    M = h.fk()
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in col_objs:
        e = o.evaluated_get(dg); me = e.to_mesh()
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co); e.to_mesh_clear()
        mw = np.array(o.matrix_world)
        pts.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
    X = np.concatenate(pts)
    c0 = (X.min(0) + X.max(0)) / 2
    _, _, vt = np.linalg.svd(X - X.mean(0), full_matrices=False)
    thin = vt[2]; long_ = vt[0]
    half = float(((X - c0) @ thin).max() - ((X - c0) @ thin).min()) / 2
    reach = float(((X - c0) @ long_).max() - ((X - c0) @ long_).min()) / 2
    pd = _pad_dir(h, M, "Index", 3)
    pad_pt = finger_pad(h, M, "Index", 0.72)
    tipdir = (h.joint(M, h.chains["Index"][3]) - h.joint(M, h.chains["Index"][2])).normalized()
    # held by one end: the object sticks out beyond the fingertips (at = share of its length inside the pinch)
    inside_share = 0.35 if at is None else at
    centre = pad_pt + pd * (half + margin) + tipdir * reach * (1 - 2 * inside_share)
    q = Vector(thin).rotation_difference(pd)
    Rm = q.to_matrix().to_4x4()
    l2 = Rm.to_3x3() @ Vector(long_)
    l2p = (l2 - pd * l2.dot(pd))
    if l2p.length > 1e-6:                                  # turn the long side to point along the fingertip
        t2 = (tipdir - pd * tipdir.dot(pd)).normalized()
        ang = l2p.normalized().rotation_difference(t2 if not flip else -t2)
        Rm = ang.to_matrix().to_4x4() @ Rm
    if roll:
        Rm = Matrix.Rotation(RAD(roll), 4, pd) @ Rm
    root.matrix_world = Matrix.Translation(centre) @ Rm @ Matrix.Translation(-Vector(c0)) @ root.matrix_world
    bpy.context.view_layer.update()
    col = Collider(col_objs)
    log = {"Index": close_finger(h, "Index", col, margin=margin, joints=(2, 3), couple=0.5)}
    for F in ("Middle", "Ring", "Pinky"):                  # make sure curled idle fingers clear the pinched item
        ids_ = np.concatenate([h.seg[(F, j)][0] for j in (1, 2, 3)])
        k_ = 0
        while col.min_sd(h.skin(h.fk(), ids_)) < margin and k_ < 25:
            h.q[h.chains[F][0]][0] += RAD(2); k_ += 1
    M = h.fk()
    pd_now = _pad_dir(h, M, "Index", 3)
    grip_pt = finger_pad(h, M, "Index", 0.72) + pd_now * (2 * half + margin)
    log["Thumb"] = solve_thumb(h, col, grip_pt, margin=margin)
    return col, log, {"thickness_mm": round(half * 2000, 1), "centre": centre}


GRIPS = {"power": _grip_power, "pen": _grip_pen, "pinch": _grip_pinch}


def hold(obj, side="Right", grip="power", at=None, axis=None, flip=False, roll=0.0, slant=0.0, margin=0.0,
         parent=True, max_pen_mm=1.5, arm=None, body=None, **kw):
    """Put `obj` into the hand with the given grip, close the fingers on it and bone-parent it.

    grip: "power" (handle in the fist), "pen" (writing grip), "pinch" (between thumb and index pads).
    at: power - where along the object it is held, 0 = lower end .. 1 = upper end (default 0.35);
        pen - metres from the tip to the fingers (default 0.032); pinch - share of the object inside the pinch.
    flip: turn the object end for end. roll: degrees about its own axis. slant (power): degrees of tilt in the palm.
    Returns a report: finger angles, contacts, penetration check, and pass/fail (`ok`) against `max_pen_mm`."""
    root = _obj(obj)
    _unparent(root)
    h = Hand(side, arm, body)
    objs = _meshes(root)
    if grip == "power" and at is None:
        at = 0.35
    col, log, info = GRIPS[grip](h, root, objs, at=at, axis=axis, flip=flip, roll=roll, slant=slant, margin=margin, **kw)
    h.apply()
    if parent:
        _bone_parent(root, h.hand, h.arm)
    if col.cores:
        bpy.context.view_layer.update()
        check_col = Collider(objs)
    else:
        check_col = col
    rep = check(root, side, _hand=h, _col=check_col, max_pen_mm=max_pen_mm, require_touch=True)
    rep.update({"grip": grip, "side": side, "object": root.name, "closing": log,
                "info": {k: (v if not isinstance(v, Vector) else [round(x, 4) for x in v]) for k, v in info.items()}})
    return rep


def check(obj, side="Right", _hand=None, _col=None, touch_mm=1.5, max_pen_mm=1.5, require_touch=False, arm=None, body=None):
    """Measure the grip: how deep any hand skin is inside the object (mm), which fingers touch it,
    and whether it passes (`ok`) within `max_pen_mm`."""
    root = _obj(obj)
    h = _hand or Hand(side, arm, body)
    col = _col or Collider(_meshes(root))
    M = h.fk()
    out = {"penetration_mm": 0.0, "touching": [], "fingers": {}}
    worst = 0.0
    for F in ("Thumb",) + FINGERS:
        ids = np.concatenate([h.seg[(F, j)][0] for j in (1, 2, 3)])
        d = col.min_sd(h.skin(M, ids)) * 1000
        out["fingers"][F] = {"gap_mm": round(max(d, 0.0), 1) + 0.0, "inside_mm": round(max(-d, 0.0), 1) + 0.0}
        if d <= touch_mm:
            out["touching"].append(F)
        worst = max(worst, -d)
    d = col.min_sd(h.skin(M, h.palm)) * 1000
    out["palm"] = {"gap_mm": round(max(d, 0.0), 1) + 0.0, "inside_mm": round(max(-d, 0.0), 1) + 0.0}
    out["penetration_mm"] = round(max(worst, -d, 0.0), 1) + 0.0
    reasons = []
    if out["penetration_mm"] > max_pen_mm:
        reasons.append(f"penetration {out['penetration_mm']:.1f} mm > limit {max_pen_mm:.1f} mm")
    if require_touch and not out["touching"]:
        reasons.append("no finger touching object")
    out["ok"] = len(reasons) == 0
    out["max_penetration_mm"] = float(max_pen_mm)
    if reasons:
        out["fail_reasons"] = reasons
    return out


def release(obj):
    """Un-parent a held object where it is."""
    _unparent(_obj(obj))


def open_hand(side="Right", flex=(8, 10, 6), thumb=(0, 0, 0, 5, 5), arm=None, body=None):
    """Relaxed open hand."""
    h = Hand(side, arm, body)
    for F in FINGERS:
        h.set_flex(F, flex)
    h.thumb_set([RAD(a) for a in thumb])
    h.apply()
    return h.angles_deg()


def fist(side="Right", amount=1.0, arm=None, body=None):
    """A plain fist (no object): amount 0 = open, 1 = closed. Replaces pose.curl for held-nothing poses."""
    h = Hand(side, arm, body)
    for F in FINGERS:
        h.set_flex(F, (80 * amount, 100 * amount, 60 * amount))
    h.thumb_set([RAD(a * amount) for a in (30, 0, 25, 35, 45)])
    h.apply()
    return h.angles_deg()


def lbs_error(side="Right", arm=None, body=None):
    """Largest difference (mm) between this module's skinning and Blender's evaluated mesh for the hand."""
    h = Hand(side, arm, body)
    dg = bpy.context.evaluated_depsgraph_get()
    e = h.body.evaluated_get(dg); me = e.to_mesh()
    if len(me.vertices) < int(h.vidx.max()) + 1:
        e.to_mesh_clear()
        return None
    mw = h.body.matrix_world
    X = h.skin(h.fk())
    err = max((mw @ me.vertices[int(i)].co - Vector(X[k])).length for k, i in enumerate(h.vidx))
    e.to_mesh_clear()
    return round(err * 1000, 3)
