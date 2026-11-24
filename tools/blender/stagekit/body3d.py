"""body3d - the skinned body of a 3D character: ONE continuous surface from the neck down (trunk, arms, hands with
fingers, legs, feet; a gown's skirt is part of it), bound to the figure's own joints, with the clothes made FROM that
surface. Nothing is laid over a hidden body, so nothing can poke through, and a sleeve is part of its garment.

    fig.body = body3d.Body(fig)     # the bare surface and its skin weights (fig3d.Fig does this when the sheet asks for it)
    fig.body.paint(part, "panel")   # every costume drawing of the sheet becomes a region of the surface
    fig.body.dress()                # cut the regions in, raise them by their layer, close the cloth edges, bind

How it is made
- The body parts are put together in a bind pose (arms out, so nothing touches) and fused into one skin.
- Each point of the skin follows the joints it belongs to: who owns it is decided by which body part's surface it lies
  on, with a soft change-over across shoulders and hips, and along a limb across the elbow, wrist, knee and ankle.
- A garment is a region: a stretch of a limb, a band round the body, or a flat front drawing (the sheet's own) wrapped
  round the trunk. The skin is cut exactly along the region's edge, the region is raised by its layer and the step is
  closed with a rim, which is the thickness of the cloth. Buttons and badges sit on the skin and move with it.
- An armature with one bone per joint copies the joints the actions already move, so no action changes.

Space: metres, the figure stands at the origin facing -Y, +X is its left hand, Z up (the same as fig3d).
"""
from __future__ import annotations

import fnmatch
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

BIND_ARM = math.radians(65.0)    # arms out in the bind pose
BALL = 1.20                      # the shoulder ball, in upper-arm radii
BIND_LEG = math.radians(4.0)     # legs a little apart
T_BASE = 0.0045                  # thickness of the first layer of cloth over the skin, metres
T_LAYER = 0.0040                 # each layer above it
SIGMA = 0.016                    # how soft the change-over between two body parts is, metres
FINGERS = (("f0", -0.52, -20.0), ("f1", 0.0, 0.0), ("f2", 0.52, 20.0))   # name, place across the palm (hand radii), fan in the bind pose
# finger curl in degrees per hand shape: relaxed (no shape), open, pinch, fist, point, grip
CURL = {"f0": (16, 0, 58, 98, 0, 72), "f1": (22, 0, 18, 102, 104, 76), "f2": (28, 0, 24, 104, 106, 78), "th": (8, 0, 34, 62, 58, 44)}


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _step(v, a, b):
    return _ss((v - a) / (b - a))


def _poly_sd(P, poly):
    """signed distance from points P (n, 2) to a closed outline (k, 2): positive inside"""
    A = np.asarray(poly, dtype=float)
    B = np.roll(A, -1, axis=0)
    d2 = np.full(len(P), 1e18)
    inside = np.zeros(len(P), dtype=bool)
    for (ax, az), (bx, bz) in zip(A, B):
        ex, ez = bx - ax, bz - az
        L2 = ex * ex + ez * ez
        if L2 < 1e-14:
            continue
        t = np.clip(((P[:, 0] - ax) * ex + (P[:, 1] - az) * ez) / L2, 0.0, 1.0)
        dx, dz = P[:, 0] - (ax + t * ex), P[:, 1] - (az + t * ez)
        d2 = np.minimum(d2, dx * dx + dz * dz)
        cr = ((az <= P[:, 1]) & (P[:, 1] < bz)) | ((bz <= P[:, 1]) & (P[:, 1] < az))
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = ax + (P[:, 1] - az) * ex / np.where(abs(ez) < 1e-14, 1.0, ez)
        inside ^= cr & (xi > P[:, 0])
    d = np.sqrt(d2)
    return np.where(inside, d, -d)


def _poly_halfwidth(z, poly):
    """the widest |x| of an outline at each height z (0 where the outline does not reach)"""
    A = np.asarray(poly, dtype=float)
    B = np.roll(A, -1, axis=0)
    w = np.zeros(len(z))
    for (ax, az), (bx, bz) in zip(A, B):
        if abs(bz - az) < 1e-12:
            continue
        cr = ((az <= z) & (z < bz)) | ((bz <= z) & (z < az))
        xi = np.abs(ax + (z - az) * (bx - ax) / (bz - az))
        w = np.where(cr, np.maximum(w, xi), w)
    return w


def _lathe(bm, profile, seg, syf, ripple=None):
    """spin (r, z) points round Z into a closed shape; syf(z): front-to-back squash at that height"""
    rows = []
    for k, (r, z) in enumerate(profile):
        row = []
        for i in range(seg):
            th = math.tau * i / seg
            rr = max(1e-4, r) * (ripple(th, z) if ripple else 1.0)
            row.append(bm.verts.new((rr * math.cos(th), rr * math.sin(th) * syf(z), z)))
        rows.append(row)
    for k in range(len(rows) - 1):
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((rows[k][i], rows[k][j], rows[k + 1][j], rows[k + 1][i]))
    bm.faces.new(rows[0])
    bm.faces.new(list(reversed(rows[-1])))


class Body:
    def __init__(self, fig):
        from . import fig3d
        self.f3 = fig3d
        self.fig = fig
        self.b = b = fig.b
        self.paints, self.studs, self.hidden = [], [], set()
        self.ready = False
        self.ob = self.rig = None
        self._mats, self._bmats = [], {}
        self.robe = fig.robe
        W = fig.W
        self.side = {"L": 1.0, "R": -1.0}
        self.L1, self.L2 = b["arm1"], b["arm2"]
        self.T1, self.T2 = b["leg_z"] - b["knee_z"], b["knee_z"] - b["ankle_z"]
        prof = sorted(([float(r), float(z)] for r, z in b["torso"]), key=lambda p: -p[1])
        self.ztop = b["neck_z"] + 0.045
        if self.robe:
            hem = prof[-1]
            b["hem_z"] = hem[1]
            self.prof = [(0.05, self.ztop)] + [tuple(p) for p in prof] + [(hem[0] * 0.95, hem[1] - 0.012)]
        else:
            self.prof = [(0.05, self.ztop)] + [tuple(p) for p in prof] + [(prof[-1][0] * 0.82, prof[-1][1] - 0.02)]
        self.tz0 = prof[-1][1]                               # the lower edge of the drawn torso
        self.zbot = self.prof[-1][1]
        pz = np.array([p[1] for p in self.prof][::-1])
        pr = np.array([p[0] for p in self.prof][::-1])
        self.rz = lambda z: np.interp(z, pz, pr)
        self.waist = fig.waist
        # bind pose: each limb is turned about its top joint
        self.A, self.Ai = {}, {}
        for sfx, s in self.side.items():
            for limb, top, ang in (("arm", f"sh.{sfx}", -s * BIND_ARM), ("leg", f"hip.{sfx}", -s * BIND_LEG)):
                M = Matrix.Translation(W[top]) @ Matrix.Rotation(ang, 4, "Y") @ Matrix.Translation(-W[top])
                self.A[limb, sfx], self.Ai[limb, sfx] = M, M.inverted()
        self.bones = [j for j in fig.J] + [f"{n}.{sfx}" for sfx in "LR" for n in ("f0", "f1", "f2", "th")]
        self.bi = {n: i for i, n in enumerate(self.bones)}
        self.surfs = [self._surface(legs=not self.robe, trunk=True)]
        if self.robe:
            self.surfs.append(self._surface(legs=True, trunk=False))
        self._rig()

    # ------------------------------------------------------------------ shapes
    def sy(self, z):
        if not self.robe:
            return np.full(np.shape(z), 0.76) if np.ndim(z) else 0.76
        return 0.86 - 0.10 * _step(z, self.waist - 0.06, self.waist + 0.06)

    def _knuckle(self, sfx, name):
        """where a finger starts and where it points, in the arm's rest space"""
        b, hr = self.b, self.b["hand_r"]
        wr = self.fig.W[f"wr.{sfx}"]
        hc = Vector((wr.x, 0.0, wr.z - hr * 0.95))
        if name == "th":
            s = self.side[sfx]
            return hc + Vector((-s * 0.10 * hr, -0.70 * hr, 0.16 * hr)), Vector((-s * 0.20, -0.74, -0.64)).normalized()
        _n, off, fan = next(q for q in FINGERS if q[0] == name)
        a = math.radians(fan)
        return hc + Vector((0.0, off * hr, -0.58 * hr)), Vector((0.0, math.sin(a), -math.cos(a)))

    def _prims(self, legs, trunk):
        f3, b, W = self.f3, self.b, self.fig.W
        parts = []
        if trunk:
            bm = bmesh.new()
            wz, hz = self.waist, b.get("hem_z", 0.1)
            rip = (lambda th, z: 1.0 + 0.04 * (max(0.0, min(1.0, (wz - z) / max(1e-6, wz - hz))) ** 1.5) * math.cos(14 * th)) if self.robe else None
            _lathe(bm, self.prof, 96 if self.robe else 64, lambda z: float(self.sy(z)), rip)
            f3._tube(bm, (0, 0, b["neck_z"] - 0.04), (0, 0, self.fig.hz - self.fig.R * 0.80), 0.052, 0.052, caps=False)
            parts.append((bm, None))
            hr = b["hand_r"]
            for sfx, s in self.side.items():
                sh, el, wr = W[f"sh.{sfx}"], W[f"el.{sfx}"], W[f"wr.{sfx}"]
                bm = bmesh.new()
                f3._sphere(bm, sh, b["r_sh"] * BALL, seg=32, rings=18)
                f3._tube(bm, sh, el, b["r_sh"], b["r_el"], seg=24)
                f3._tube(bm, el, wr, b["r_el"], b["r_wr"], seg=24)
                hc = Vector((wr.x, 0.0, wr.z - hr * 0.95))
                f3._sphere(bm, hc, hr, scale=(0.72, 0.98, 1.04), seg=28, rings=16)
                for name, _off, _fan in FINGERS:
                    k, d = self._knuckle(sfx, name)
                    f3._tube(bm, k - d * (0.10 * hr), k + d * (0.98 * hr), hr * 0.27, hr * 0.235, seg=14)
                k, d = self._knuckle(sfx, "th")
                f3._tube(bm, k - d * (0.25 * hr), k + d * (0.86 * hr), hr * 0.31, hr * 0.27, seg=14)
                parts.append((bm, self.A["arm", sfx]))
        if legs:
            ft = b["foot"]
            fl, fw = ft.get("len", 0.10), ft.get("w", 0.05)
            for sfx in "LR":
                hp, kn, an = W[f"hip.{sfx}"], W[f"kn.{sfx}"], W[f"an.{sfx}"]
                bm = bmesh.new()
                f3._tube(bm, hp, kn, b["r_hip"], b["r_kn"], seg=24)
                f3._tube(bm, kn, an, b["r_kn"], b["r_an"], seg=24)
                f3._sphere(bm, an + Vector((0, -fl * 0.40, -an.z + fw * 0.86)), fw * 1.08, scale=(1.0, fl / fw, 0.80), seg=24, rings=14)
                parts.append((bm, self.A["leg", sfx]))
        out = bmesh.new()
        for bm, M in parts:
            if M is not None:
                bm.transform(M)
            me = bpy.data.meshes.new("c3_tmp")
            bm.to_mesh(me)
            bm.free()
            out.from_mesh(me)
            bpy.data.meshes.remove(me)
        return out

    def _fuse(self, bm):
        """many closed shapes -> one smooth skin (points, triangles)"""
        me = bpy.data.meshes.new("c3_fuse")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("c3_fuse", me)
        bpy.context.scene.collection.objects.link(ob)
        voxel = 0.0046 * max(0.6, self.b.get("height", 1.6) / 1.6)
        m = ob.modifiers.new("fuse", "REMESH")
        m.mode, m.voxel_size, m.adaptivity = "VOXEL", voxel, 0.0
        s = ob.modifiers.new("smooth", "SMOOTH")
        s.factor, s.iterations = 0.5, 14
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        m2 = ev.to_mesh()
        m2.calc_loop_triangles()
        V = np.empty(len(m2.vertices) * 3)
        m2.vertices.foreach_get("co", V)
        F = np.empty(len(m2.loop_triangles) * 3, dtype=np.int64)
        m2.loop_triangles.foreach_get("vertices", F)
        ev.to_mesh_clear()
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(me)
        return V.reshape(-1, 3), F.reshape(-1, 3)

    # ------------------------------------------------------------------ who owns each point of the skin
    def _limb_space(self, V, limb, sfx):
        M = np.array(self.Ai[limb, sfx])
        return V @ M[:3, :3].T + M[:3, 3]

    def _surface(self, legs, trunk):
        b, W, fig = self.b, self.fig.W, self.fig
        V, F = self._fuse(self._prims(legs, trunk))
        n = len(V)
        hr = b["hand_r"]
        big = 9.0
        D = {}                                               # distance outside each body part's own surface
        co = {}
        if trunk:
            z = V[:, 2]
            rho = np.hypot(V[:, 0], V[:, 1] / self.sy(z))
            D["trunk"] = np.maximum(np.maximum((rho - self.rz(z)) * 0.8, z - self.ztop - 0.3), self.zbot - z)
            for sfx in "LR":
                P = self._limb_space(V, "arm", sfx)
                sh = W[f"sh.{sfx}"]
                s = sh.z - P[:, 2]
                r = np.hypot(P[:, 0] - sh.x, P[:, 1])
                La = self.L1 + self.L2
                rad = np.interp(s, [0.0, self.L1, La], [b["r_sh"], b["r_el"], b["r_wr"]])
                d = np.minimum(np.where(s < 0, np.hypot(r, s) - b["r_sh"], r - rad), np.hypot(r, s) - b["r_sh"] * BALL)
                d = np.where(s > La - b["r_wr"], np.maximum(np.maximum(0.0, r - 1.75 * hr), s - (La + 3.1 * hr)), d)   # the hand, fingers and all
                D[f"arm.{sfx}"] = d
                co[f"arm.{sfx}"] = (P, s, r)
        else:
            D["trunk"] = np.full(n, big)
        if legs:
            fw = b["foot"].get("w", 0.05)
            for sfx in "LR":
                P = self._limb_space(V, "leg", sfx)
                hp = W[f"hip.{sfx}"]
                s = hp.z - P[:, 2]
                r = np.hypot(P[:, 0] - hp.x, P[:, 1])
                Ll = self.T1 + self.T2
                rad = np.interp(s, [0.0, self.T1, Ll], [b["r_hip"], b["r_kn"], b["r_an"]])
                d = np.where(s < 0, np.hypot(r, s) - b["r_hip"], r - rad)
                d = np.where(s > Ll - b["r_an"], np.maximum(0.0, np.abs(P[:, 0] - hp.x) - fw * 1.25), d)
                D[f"leg.{sfx}"] = d
                co[f"leg.{sfx}"] = (P, s, r)
        names = list(D)
        if trunk:
            # A limb belongs to itself from where it stands clear of the trunk. A shoulder is a ball joint: the ball turns
            # about its own centre, so the line where it meets the trunk looks the same in every pose, and the narrow band
            # that changes over lies on the ball and stays on it.
            dt = D["trunk"]
            O = np.zeros((n, len(names)))
            for i, k in enumerate(names):
                if k != "trunk":
                    O[:, i] = np.exp(-np.maximum(D[k], 0.0) / 0.004) * _step(dt, 0.0015, 0.014)
            tot = O.sum(axis=1)
            O /= np.maximum(1.0, tot)[:, None]
            O[:, names.index("trunk")] = 1.0 - O.sum(axis=1)
        else:
            E = np.stack([np.exp(-np.maximum(D[k], 0.0) / (SIGMA * 0.5)) for k in names], axis=1) + 1e-12
            O = E / E.sum(axis=1, keepdims=True)
        own = {k: O[:, i] for i, k in enumerate(names)}
        Wt = np.zeros((n, len(self.bones)), dtype=np.float32)
        bi = self.bi
        rest = V.copy()
        for sfx in "LR":
            k = f"arm.{sfx}"
            if k in co:
                P, s, r = co[k]
                o = own[k]
                La = self.L1 + self.L2
                e = _step(s, self.L1 - 0.85 * b["r_el"], self.L1 + 0.85 * b["r_el"])
                h = _step(s, La - 0.55 * b["r_wr"], La + 0.35 * b["r_wr"])
                fs = []
                for name in ("f0", "f1", "f2", "th"):
                    kn, d = self._knuckle(sfx, name)
                    q = P - np.array(kn)
                    t = q @ np.array(d)
                    lat = np.linalg.norm(q - np.outer(t, np.array(d)), axis=1)
                    rf = hr * (0.30 if name == "th" else 0.27)
                    fs.append(_step(t, -0.12 * hr, 0.26 * hr) * (1.0 - _step(lat, 1.10 * rf, 1.75 * rf)))
                fs = np.stack(fs, axis=1)
                tot = fs.sum(axis=1, keepdims=True)
                fs = fs / np.maximum(1.0, tot)
                Wt[:, bi[f"sh.{sfx}"]] = o * (1 - e)
                Wt[:, bi[f"el.{sfx}"]] = o * e * (1 - h)
                Wt[:, bi[f"wr.{sfx}"]] = o * e * h * (1 - fs.sum(axis=1))
                for i, name in enumerate(("f0", "f1", "f2", "th")):
                    Wt[:, bi[f"{name}.{sfx}"]] = o * e * h * fs[:, i]
                rest += (P - V) * o[:, None]
            k = f"leg.{sfx}"
            if k in co:
                P, s, r = co[k]
                o = own[k]
                Ll = self.T1 + self.T2
                kk = _step(s, self.T1 - 0.85 * b["r_kn"], self.T1 + 0.85 * b["r_kn"])
                a = _step(s, Ll - 0.75 * b["r_an"], Ll + 0.30 * b["r_an"])
                Wt[:, bi[f"hip.{sfx}"]] = o * (1 - kk)
                Wt[:, bi[f"kn.{sfx}"]] = o * kk * (1 - a)
                Wt[:, bi[f"an.{sfx}"]] = o * kk * a
                rest += (P - V) * o[:, None]
        z = V[:, 2]
        skirt = np.zeros(n)
        if trunk:
            ot = own["trunk"]
            hd = _step(z, b["neck_z"] - 0.005, b["neck_z"] + 0.05)
            up = _step(z, self.waist - 0.035, self.waist + 0.035)
            Wt[:, bi["head"]] = ot * hd
            Wt[:, bi["torso"]] = ot * (1 - hd) * up
            low = ot * (1 - hd) * (1 - up)
            if self.robe:                                    # a gown: the skirt sways on its own joint and follows the legs a little
                lw = 0.50 * _step(b["leg_z"] + 0.05 - z, 0.0, 0.25)
                shin = _step(b["knee_z"] + 0.06 - z, 0.0, 0.16)
                left = _step(V[:, 0], -0.07, 0.07)
                for sfx, sd in (("L", left), ("R", 1 - left)):
                    Wt[:, bi[f"hip.{sfx}"]] += low * lw * sd * (1 - shin)
                    Wt[:, bi[f"kn.{sfx}"]] += low * lw * sd * shin
                Wt[:, bi["skirt"]] = low * (1 - lw)
                skirt = low
            else:
                Wt[:, bi["hips"]] = low
        Wt /= np.maximum(1e-9, Wt.sum(axis=1, keepdims=True))
        # flat coordinates of the trunk: the same wrap the 2D drawings were made for
        phi = np.arctan2(V[:, 0], -V[:, 1] / self.sy(z))
        phib = np.arctan2(V[:, 0], V[:, 1] / self.sy(z))
        rr = self.rz(np.clip(z, self.zbot, self.ztop))
        vert = dict(u=phi * rr / 1.08, ub=phib * rr / 1.08, z=z.copy(), rr=rr, rho=np.hypot(V[:, 0], V[:, 1] / self.sy(z)), skirt=skirt)
        for k in ("trunk", "arm.L", "arm.R", "leg.L", "leg.R"):
            vert["o_" + k] = own.get(k, np.zeros(n))
            if k in co:
                vert["s_" + k] = co[k][1]
            elif k != "trunk":
                vert["s_" + k] = np.zeros(n)
        tri = V[F]
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        N = np.zeros_like(V)
        for i in range(3):
            np.add.at(N, F[:, i], fn)
        N /= np.maximum(1e-12, np.linalg.norm(N, axis=1, keepdims=True))
        return dict(V=V, F=F, N=N, W=Wt, rest=rest, vert=vert, trunk=trunk, legs=legs)

    # ------------------------------------------------------------------ the armature
    def _rig(self):
        fig, W = self.fig, self.fig.W
        arm = bpy.data.armatures.new(f"{fig.name}_rig")
        ob = bpy.data.objects.new(f"{fig.name}.rig", arm)
        fig.coll.objects.link(ob)
        ob.parent = fig.J["root"]
        vl = bpy.context.view_layer
        prev = vl.objects.active
        vl.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        rest = {}
        for jn in fig.J:
            M = Matrix.Translation(W[jn])
            p = jn.split(".")
            if len(p) == 2 and p[0] in ("sh", "el", "wr"):
                M = self.A["arm", p[1]] @ M
            elif len(p) == 2 and p[0] in ("hip", "kn", "an"):
                M = self.A["leg", p[1]] @ M
            rest[jn] = M
        for sfx in "LR":
            for name in ("f0", "f1", "f2", "th"):
                k, _d = self._knuckle(sfx, name)
                rest[f"{name}.{sfx}"] = self.A["arm", sfx] @ Matrix.Translation(k)
        for bn in self.bones:
            eb = arm.edit_bones.new(bn)
            eb.head, eb.tail = (0, 0, 0), (0, 0.04, 0)
            eb.matrix = rest[bn]
        for sfx in "LR":
            for name in ("f0", "f1", "f2", "th"):
                arm.edit_bones[f"{name}.{sfx}"].parent = arm.edit_bones[f"wr.{sfx}"]
        bpy.ops.object.mode_set(mode="OBJECT")
        vl.objects.active = prev
        for jn in fig.J:
            c = ob.pose.bones[jn].constraints.new("COPY_TRANSFORMS")
            c.target = fig.J[jn]
        shapes = self.f3.HAND_SHAPES[1:]                     # open, pinch, fist, point, grip
        order = ("open", "pinch", "fist", "point", "grip")
        for sfx, s in self.side.items():
            for name in ("f0", "f1", "f2", "th"):
                pb = ob.pose.bones[f"{name}.{sfx}"]
                pb.rotation_mode = "XYZ"
                c = CURL[name]
                expr = f"{s:+.0f} * ((1.0 - min(1.0, o + p + f + t + g)) * {math.radians(c[0]):.4f} + " + " + ".join(
                    f"{v} * {math.radians(c[1 + i]):.4f}" for i, v in enumerate(("o", "p", "f", "t", "g"))) + ")"
                self._bone_driver(ob, pb, 1, expr, sfx, order, shapes)
                fan = next((q[2] for q in FINGERS if q[0] == name), 0.0)
                if fan:                                      # the fan of the bind pose closes unless the hand is open
                    self._bone_driver(ob, pb, 0, f"{-math.radians(fan):.4f} * (1.0 - 0.85 * min(1.0, o))", sfx, order, shapes)
        ob.hide_render = True
        self.rig = ob

    def _bone_driver(self, ob, pb, index, expr, sfx, order, shapes):
        fc = ob.driver_add(f'pose.bones["{pb.name}"].rotation_euler', index)
        d = fc.driver
        d.type = "SCRIPTED"
        for vn, shape in zip(("o", "p", "f", "t", "g"), order):
            v = d.variables.new()
            v.name = vn
            v.type = "SINGLE_PROP"
            v.targets[0].id_type = "OBJECT"
            v.targets[0].id = self.fig.ctrl
            v.targets[0].data_path = f'["hand_{sfx}_{shape}"]' if shape in shapes else '["blink"]'
        d.expression = expr

    # ------------------------------------------------------------------ garments
    def paint(self, p, how):
        """one costume drawing of the sheet becomes a region of the skin. how: decal | back | band | panel | limb | stud"""
        kind, c, key = self.fig._pk(p)
        q = dict(p, how=how, mkind=kind, color=c, key=key)
        if how == "stud":
            self.studs.append(q)
        else:
            self.paints.append(q)
        return []

    def hide(self, patterns):
        n = 0
        for q in self.paints + self.studs:
            if any(fnmatch.fnmatchcase(q["name"], pat) for pat in patterns) and q["name"] not in self.hidden:
                self.hidden.add(q["name"])
                n += 1
        if n and self.ready:
            self.dress()
        return n

    def recolor(self, colors):
        hit = False
        for q in self.paints + self.studs:
            if q.get("key") in colors:
                q["color"] = colors[q["key"]]
                hit = True
        for role, key in self.fig.keys.items():
            if key in colors:
                self.fig.col[role] = colors[key]
                hit = True
        if hit and self.ready:
            self.dress()

    def _mid(self, kind, color, key=None):
        k = (kind, color.upper())
        for i, m in enumerate(self._mats):
            if m[:2] == k:
                return i
        self._mats.append((kind, color.upper(), key))
        return len(self._mats) - 1

    def _cut(self, S, f, faces):
        """cut the skin exactly along f = 0 (through the given faces), carrying every per-point value onto the new points.
        Returns f for the grown point list, with the points the cut goes through at 0."""
        V, F = S["V"], S["F"]
        n = len(V)
        vm = np.zeros(n, dtype=bool)
        vm[F[faces].ravel()] = True
        f0 = f
        f = f.copy()
        a, b_ = F, F[:, [1, 2, 0]]
        ok = vm[a] & vm[b_]
        cut = ok & (f[a] * f[b_] < 0)
        if cut.any():
            fa, fb = np.abs(f[a][cut]), np.abs(f[b_][cut])   # a cut that would pass right beside a point goes through the point instead:
            ta = fa / (fa + fb)                              # no sliver triangles, which shade badly
            f[a[cut][ta < 0.16]] = 0.0
            f[b_[cut][ta > 0.84]] = 0.0
            cut = ok & (f[a] * f[b_] < 0)
        if not cut.any():
            return f, f0
        lo, hi = np.minimum(a, b_), np.maximum(a, b_)
        key = lo * n + hi
        uq, inv = np.unique(key[cut], return_inverse=True)
        ulo, uhi = uq // n, uq % n
        t = (f[ulo] / (f[ulo] - f[uhi]))[:, None]

        def mix(X):
            tt = t if X.ndim > 1 else t[:, 0]
            return np.concatenate([X, X[ulo] * (1 - tt) + X[uhi] * tt])
        for k in ("V", "N", "W", "rest"):
            S[k] = mix(S[k])
        S["N"] /= np.maximum(1e-12, np.linalg.norm(S["N"], axis=1, keepdims=True))
        for k in S["vert"]:
            S["vert"][k] = mix(S["vert"][k])
        f0 = mix(f0)
        f = np.concatenate([f, np.zeros(len(uq))])
        nid = np.full(F.shape, -1, dtype=np.int64)
        nid[cut] = n + inv
        nc = cut.sum(axis=1)
        keep = nc == 0
        newF, src = [F[keep]], [np.nonzero(keep)[0]]
        i1 = np.nonzero(nc == 1)[0]
        if len(i1):
            k = np.argmax(cut[i1], axis=1)
            va, vb, vc, p = F[i1, k], F[i1, (k + 1) % 3], F[i1, (k + 2) % 3], nid[i1, k]
            newF += [np.stack([va, p, vc], axis=1), np.stack([p, vb, vc], axis=1)]
            src += [i1, i1]
        i2 = np.nonzero(nc == 2)[0]
        if len(i2):
            u = np.argmin(cut[i2], axis=1)                   # the edge that is not cut
            vu, vn, w = F[i2, u], F[i2, (u + 1) % 3], F[i2, (u + 2) % 3]
            p, q = nid[i2, (u + 1) % 3], nid[i2, (u + 2) % 3]
            newF += [np.stack([p, w, q], axis=1), np.stack([vu, vn, p], axis=1), np.stack([vu, p, q], axis=1)]
            src += [i2, i2, i2]
        src = np.concatenate(src)
        S["F"] = np.concatenate(newF)
        for k in ("fm", "fl", "fc"):
            S[k] = S[k][src]
        return f, f0

    def _apply(self, S, f, charts, mat, level, chart=None):
        """paint the part of the given charts (None: everywhere) where f > 0. level: a number, "over" (one above what is
        there) or "same". chart: also make the painted faces this chart (0 trunk, 1 / 2 arm L / R, 3 / 4 leg L / R)."""
        mask = lambda: np.ones(len(S["F"]), dtype=bool) if charts is None else np.isin(S["fc"], charts)
        fs, f0 = self._cut(S, f, mask())
        F = S["F"]
        m = fs[F].mean(axis=1)
        m = np.where(np.abs(m) < 1e-12, f0[F].mean(axis=1), m)       # a face lying in the cut line: judged by the field as given
        sel = (m > 0) & mask()
        if not sel.any():
            return
        if level == "over":
            S["fl"][sel] += 1
        elif level != "same":
            S["fl"][sel] = int(level)
        S["fm"][sel] = mat
        if chart is not None:
            S["fc"][sel] = chart

    def _base(self, S):
        """the body's own colours: skin, top, sleeves, trousers, shoes"""
        fig, b, col, K = self.fig, self.b, self.fig.col, self.fig.keys
        v = S["vert"]
        skin = self._mid("skin", fig.skin, "skin")
        lv = lambda c: 0 if c.upper() == fig.skin.upper() else 1
        kd = lambda word, c: self.f3.kind_of(word, c, fig.skin)
        S["fm"] = np.full(len(S["F"]), skin, dtype=np.int64)
        S["fl"] = np.zeros(len(S["F"]), dtype=np.int64)
        S["fc"] = np.zeros(len(S["F"]), dtype=np.int64)
        if S["trunk"]:
            c = col["torso"]
            S["fm"][:] = self._mid(kd("torso", c), c, K.get("torso"))
            S["fl"][:] = lv(c)
            La = self.L1 + self.L2
            hand = La - 0.10 * b["hand_r"]
            for ci, sfx in ((1, "L"), (2, "R")):             # each region is painted inside the one before, so no gap is left between them
                for role, s0, word in (("sleeve_u", None, "sleeve"), ("sleeve_l", self.L1, "sleeve"), ("hand", hand, "hand")):
                    c = col.get(role, fig.skin)
                    kind = ("skin" if c.upper() == fig.skin.upper() else "leather") if role == "hand" else kd(word, c)
                    mat = self._mid(kind, c, K.get(role, "skin"))
                    if s0 is None:
                        self._apply(S, v[f"o_arm.{sfx}"] - 0.5, None, mat, lv(c), chart=ci)
                    else:
                        self._apply(S, v[f"s_arm.{sfx}"] - s0, (ci,), mat, lv(c))
        if S["legs"]:
            Ll = self.T1 + self.T2
            ft = b["foot"]
            top = ft.get("top", 0.0)
            shoe0 = Ll - 0.02 if not (top > b["ankle_z"] + 0.05) else (b["leg_z"] - top)
            for ci, sfx in ((3, "L"), (4, "R")):
                for role, s0, word in (("leg_u", None, "trouser"), ("leg_l", self.T1, "trouser"), ("shoe", shoe0, "shoe")):
                    c = col.get(role) or (col.get("leg_u") or fig.skin if s0 is None else None)
                    if not c:
                        continue
                    kind = "leather" if role == "shoe" else kd(word, c)
                    lvl = (1 if lv(col.get("leg_l", fig.skin)) == 0 else 2) if role == "shoe" else lv(c)
                    mat = self._mid(kind, c, K.get(role))
                    if s0 is None:
                        self._apply(S, v[f"o_leg.{sfx}"] - 0.5, None, mat, lvl, chart=ci)
                    else:
                        self._apply(S, v[f"s_leg.{sfx}"] - s0, (ci,), mat, lvl)
        if S["trunk"]:
            self._apply(S, np.minimum(0.064 - v["rho"], v["z"] - (b["neck_z"] - 0.02)), (0,), skin, 0)      # the neck
            if not self.robe:                                # under the top's lower edge the trunk is trousers
                c = col["leg_u"]
                self._apply(S, (self.tz0 + 0.004) - v["z"], (0,), self._mid(kd("trouser", c), c, K.get("leg_u")), lv(c))

    def _paint(self, S, q):
        fig, b = self.fig, self.b
        how = q["how"]
        v = S["vert"]
        mat = self._mid(q["mkind"], q["color"], q.get("key"))
        level = 0 if q["mkind"] == "skin" else "over"
        if how == "limb":
            bone, sfx = q["on"].split(".")
            limb = "arm" if bone.startswith("arm") else "leg"
            if (limb == "arm" and not S["trunk"]) or (limb == "leg" and not S["legs"]):
                return
            if q.get("s") is not None:
                s0, s1 = q["s"]
            else:
                a2, b2 = q.get("bone2d") or (None, None)
                if not a2:
                    return
                A, B = Vector(a2), Vector(b2)
                ax = B - A
                L2d = ax.length
                ax.normalize()
                ds = [(Vector(pt) - A).dot(ax) for pt in q["pts"]]
                d0, d1 = max(-0.01, min(ds)), min(L2d + 0.02, max(ds))
                if d1 - d0 < 0.004:
                    return
                seg = {"arm_upper": (0.0, self.L1), "arm_lower": (self.L1, self.L2), "leg_upper": (0.0, self.T1), "leg_lower": (self.T1, self.T2)}[bone]
                k = seg[1] / max(L2d, 1e-6)
                s0, s1 = seg[0] + d0 * k, seg[0] + d1 * k
                if bone.endswith("upper") and d0 * k < 0.02:
                    s0 = -9.0                                # it starts at the shoulder or the hip: it is joined to the body's garment
            s = v[f"s_{limb}.{sfx}"]
            ci = {"arm.L": 1, "arm.R": 2, "leg.L": 3, "leg.R": 4}[f"{limb}.{sfx}"]
            self._apply(S, np.minimum(s - s0, s1 - s), (ci,), mat, level)
            return
        if not S["trunk"]:
            return
        pts = [(float(x), float(z)) for x, z in q["pts"]]
        x0, z0 = min(p[0] for p in pts), min(p[1] for p in pts)
        x1, z1 = max(p[0] for p in pts), max(p[1] for p in pts)
        if q.get("z"):
            z0, z1 = q["z"]
        z = v["z"]
        if how == "band":
            self._apply(S, np.minimum(z - z0, z1 - z), (0,), mat, level)
            return
        if min(x1 - x0, z1 - z0) < 0.014 and level == "over":
            level = "same"                                   # a line (a seam, an edge, a stripe) is drawn on the cloth, not raised
        neck = z1 >= b["neck_z"] - 0.03 and how == "panel"   # a garment that reaches the neck covers the shoulders too
        zz = np.minimum(z, z1 - 0.003) if neck else z
        u = v["ub"] if how == "back" else v["u"]
        f = _poly_sd(np.stack([u, zz], axis=1), pts)
        if how == "panel":                                   # as wide as the body: it goes all the way round
            zc = np.clip(zz, z0 + 1e-4, z1 - 1e-4)
            xe = _poly_halfwidth(zc, pts)
            fb = np.minimum(np.minimum(np.abs(u) - xe + 0.004, xe - 0.80 * v["rr"]), np.minimum(zz - z0, z1 - zz + (9.0 if neck else 0.0)))
            f = np.maximum(f, fb)
        self._apply(S, f, (0,), mat, level)
        if how == "panel" and level == "over":               # sleeves in the garment's own colour are its sleeves: the same layer
            S["fl"][np.isin(S["fc"], (1, 2)) & (S["fm"] == mat)] += 1

    def _shell(self, S):
        """raise each region by its layer and close the steps between regions with rims"""
        V, F, N, fm, fl = S["V"], S["F"], S["N"], S["fm"], S["fl"]
        n = len(V)
        nm = len(self._mats) + 1
        key = F * nm + fm[:, None]
        uq, inv = np.unique(key.ravel(), return_inverse=True)
        Fn = inv.reshape(-1, 3)
        src = uq // nm
        lvl = np.zeros(len(uq))
        np.maximum.at(lvl, Fn.ravel(), np.repeat(fl, 3).astype(float))
        off = np.where(lvl > 0, T_BASE + T_LAYER * (lvl - 1), 0.0)
        P = V[src] + N[src] * off[:, None]
        # rims: every edge between two different materials
        a, b_ = F, F[:, [1, 2, 0]]
        lo, hi = np.minimum(a, b_), np.maximum(a, b_)
        ek = (lo * n + hi).ravel()
        order = np.argsort(ek, kind="stable")
        eks = ek[order]
        same = eks[:-1] == eks[1:]
        i0, i1 = order[:-1][same], order[1:][same]
        f0, c0, f1, c1 = i0 // 3, i0 % 3, i1 // 3, i1 % 3
        diff = fm[f0] != fm[f1]
        f0, c0, f1, c1 = f0[diff], c0[diff], f1[diff], c1[diff]
        ia, ja = Fn[f0, c0], Fn[f0, (c0 + 1) % 3]            # face 0 runs i -> j, face 1 runs j -> i
        jb, ib = Fn[f1, c1], Fn[f1, (c1 + 1) % 3]
        gap = (np.abs(off[ia] - off[ib]) + np.abs(off[ja] - off[jb])) > 1e-5
        ia, ja, ib, jb, f0, f1 = ia[gap], ja[gap], ib[gap], jb[gap], f0[gap], f1[gap]
        m = len(ia)
        base = len(P)
        Pr = np.concatenate([P[ja], P[ia], P[ib], P[jb]])
        rs = np.concatenate([src[ja], src[ia], src[ib], src[jb]])
        r = np.arange(m)
        Fr = np.concatenate([np.stack([base + r, base + m + r, base + 2 * m + r], axis=1), np.stack([base + r, base + 2 * m + r, base + 3 * m + r], axis=1)])
        upper = np.where(fl[f0] >= fl[f1], fm[f0], fm[f1])
        return dict(P=np.concatenate([P, Pr]), src=np.concatenate([src, rs]), F=np.concatenate([Fn, Fr]), fm=np.concatenate([fm, upper, upper]),
                    smooth=np.concatenate([np.ones(len(Fn), dtype=bool), np.zeros(2 * m, dtype=bool)]), n_skin=len(P))

    def _stud_mesh(self, S, out, q):
        """a button or badge: a small raised shape set on the finished surface, moving with the point it sits on"""
        v = S["vert"]
        pts = q["pts"]
        x0, z0 = min(p[0] for p in pts), min(p[1] for p in pts)
        x1, z1 = max(p[0] for p in pts), max(p[1] for p in pts)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        src = out["src"][:out["n_skin"]]
        ok = (v["o_trunk"][src] >= 0.5) & (np.abs(v["u"][src]) < 0.45)
        if not ok.any():
            return None
        d = np.where(ok, (v["u"][src] - cx) ** 2 + (v["z"][src] - cz) ** 2, 1e9)
        i = int(np.argmin(d))
        c, nrm = out["P"][i], S["N"][src[i]]
        up = np.array([0.0, 0.0, 1.0])
        t = up - nrm * (up @ nrm)
        t /= max(1e-9, np.linalg.norm(t))
        bt = np.cross(t, nrm)
        rr = max(0.008, min(x1 - x0, z1 - z0) / 2)
        sx, sz = max(1.0, (x1 - x0) / 2 / rr), max(1.0, (z1 - z0) / 2 / rr)
        seg, rings = 14, 8
        vs, fs = [], []
        for j in range(rings + 1):
            th = math.pi * j / rings
            for k in range(seg):
                ph = math.tau * k / seg
                e = (math.sin(th) * math.cos(ph) * rr * sx, math.cos(th) * rr * 0.55, math.sin(th) * math.sin(ph) * rr * sz)
                vs.append(c + bt * e[0] + nrm * e[1] + t * e[2])
        for j in range(rings):
            for k in range(seg):
                a_, b_, c_, d_ = j * seg + k, j * seg + (k + 1) % seg, (j + 1) * seg + (k + 1) % seg, (j + 1) * seg + k
                fs += [(a_, b_, c_), (a_, c_, d_)]
        return np.array(vs), np.array(fs, dtype=np.int64)[:, ::-1], int(src[i])

    # ------------------------------------------------------------------ the finished object
    def _material(self, kind, color):
        """the figure's own material, reading the rest position stored on the skin (so cloth texture does not swim when it moves)"""
        k = (kind, color)
        if k not in self._bmats:
            m = self.fig.mat(kind, color).copy()
            m.name = f"{self.fig.name}.body.{kind}.{color.lstrip('#')}"
            nt = m.node_tree
            at = nt.nodes.new("ShaderNodeAttribute")
            at.attribute_name = "c3_rest"
            for node in list(nt.nodes):
                if node.type == "TEX_COORD":
                    for lk in list(node.outputs["Object"].links):
                        nt.links.new(at.outputs["Vector"], lk.to_socket)
            self._bmats[k] = m
        return self._bmats[k]

    def dress(self):
        fig = self.fig
        Ps, Fs, Ms, Sm, Ws, Rs, Sk = [], [], [], [], [], [], []
        base = 0
        for S0 in self.surfs:
            S = dict(S0, vert=dict(S0["vert"]))
            self._base(S)
            for q in self.paints:
                if q["name"] not in self.hidden:
                    try:
                        self._paint(S, q)
                    except Exception as ex:                  # one odd drawing must not stop the character
                        print(f"[body3d] {fig.name}: part {q['name']} ({q['how']}) skipped: {ex}")
            out = self._shell(S)
            Ps.append(out["P"]); Fs.append(out["F"] + base); Ms.append(out["fm"]); Sm.append(out["smooth"])
            Ws.append(S["W"][out["src"]]); Rs.append(S["rest"][out["src"]]); Sk.append(S["vert"]["skirt"][out["src"]])
            base += len(out["P"])
            if S["trunk"]:
                for q in self.studs:
                    if q["name"] in self.hidden:
                        continue
                    st = self._stud_mesh(S, out, q)
                    if st is None:
                        continue
                    sv, sf, si = st
                    Ps.append(sv); Fs.append(sf + base); Ms.append(np.full(len(sf), self._mid(q["mkind"], q["color"], q.get("key"))))
                    Sm.append(np.ones(len(sf), dtype=bool))
                    Ws.append(np.repeat(S["W"][si][None, :], len(sv), axis=0)); Rs.append(np.repeat(S["rest"][si][None, :], len(sv), axis=0))
                    Sk.append(np.repeat(S["vert"]["skirt"][si], len(sv)))
                    base += len(sv)
        P, F, fm, sm = np.concatenate(Ps), np.concatenate(Fs), np.concatenate(Ms), np.concatenate(Sm)
        Wt, rest, skirt = np.concatenate(Ws), np.concatenate(Rs), np.concatenate(Sk)
        used = np.unique(fm)
        remap = np.zeros(len(self._mats) + 1, dtype=np.int64)
        remap[used] = np.arange(len(used))
        me = bpy.data.meshes.new(f"{fig.name}_Body")
        me.from_pydata(P.tolist(), [], F.tolist())
        me.polygons.foreach_set("material_index", remap[fm].astype(np.int32))
        me.polygons.foreach_set("use_smooth", sm)
        for i in used:
            kind, color, _key = self._mats[int(i)]
            me.materials.append(self._material(kind, color))
        me.attributes.new("c3_rest", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", rest.astype(np.float32).ravel())
        me.update()
        if self.ob is None:
            ob = bpy.data.objects.new(f"{fig.name}.Body", me)
            fig.coll.objects.link(ob)
            ob.parent = fig.J["root"]
            md = ob.modifiers.new("rig", "ARMATURE")
            md.object = self.rig
            md.use_deform_preserve_volume = True
            ob["c3_part"], ob["c3_kind"], ob["c3_color"], ob["c3_key"] = "Body", "cloth", "", ""
            fig.parts.setdefault("Body", []).append(ob)
            self.ob = ob
        else:
            ob = self.ob
            old = ob.data
            ob.data = me
            ob.vertex_groups.clear()
            bpy.data.meshes.remove(old)
        q = np.round(Wt * 40).astype(np.int32)               # weights in steps of 1/40: few calls per bone
        for bn, bi in self.bi.items():
            col = q[:, bi]
            if not col.any():
                continue
            vg = ob.vertex_groups.new(name=bn)
            for lv in np.unique(col[col > 0]):
                vg.add(np.nonzero(col == lv)[0].tolist(), float(lv) / 40.0, "REPLACE")
        if self.robe:
            self._cloth_keys(ob, P, skirt)
        self.ready = True
        return ob

    def _cloth_keys(self, ob, P, skirt):
        """a gown keeps its hem on the ground when the hips sink, and ripples and opens with the gait (the keys the actor plays)"""
        b = self.b
        hem = b.get("hem_z", 0.1)
        k = np.clip((self.waist - P[:, 2]) / max(1e-6, self.waist - hem), 0.0, 1.0) * (skirt > 0.02)
        w = np.clip(skirt * 1.4, 0.0, 1.0)
        ob.shape_key_add(name="Basis")
        r = np.maximum(1e-6, np.hypot(P[:, 0], P[:, 1]))
        th = np.arctan2(P[:, 1], P[:, 0])
        g = 1.0 + 0.30 * np.sin(np.pi * np.minimum(1.0, k * 0.9)) * 0.9 + 0.15 * k
        shapes = {"squat": np.stack([P[:, 0] * (1 + (g - 1) * w), P[:, 1] * (1 + (g - 1) * w), P[:, 2] + self.f3.SQUAT_MAX * k * w], axis=1)}
        for name in ("waveA", "waveB", "flare"):
            if name == "flare":
                d, dz = 0.055 * k ** 1.5, 0.022 * k ** 2
            else:
                d, dz = 0.034 * k ** 1.6 * (np.sin(5 * th) if name == "waveA" else np.cos(5 * th)), 0.0
            d = d * w
            shapes[name] = np.stack([P[:, 0] + P[:, 0] / r * d, P[:, 1] + P[:, 1] / r * d, P[:, 2] + dz * w], axis=1)
        for name, co in shapes.items():
            kb = ob.shape_key_add(name=name)
            kb.value = 0.0
            kb.data.foreach_set("co", co.astype(np.float32).ravel())
