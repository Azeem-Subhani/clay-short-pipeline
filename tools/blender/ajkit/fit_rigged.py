# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/dress_test/fit_rigged.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the folders come from ajkit.paths (bodies from 02_Age_Body_Variants,
# staging and the pass copy under output/_staging/wardrobe/<outfit>/<Sex>_<Age>/; tools/chars_aj/fit.py files a pass
# into library/wardrobe/fits) and garments, stage, sheetutil, fitcheck, fitreview are imported from ajkit. The fit
# method, its constants, the check and the pass rule are unchanged.
"""Fit a rigged outfit (garments + the body they were made on, Mixamo bone names) to an Aj variant, and check the fit.

    blender --background --python fit_rigged.py -- <Sex> <Age> <asset.blend> <outfit_name> [review]

The asset must be ready (prep_asset.py -- check). How to get one ready, what is checked and where results go:
scripts\\FITCHECK.md.

How: every garment vertex is described relative to the asset's own body: for each bone that moves it, where along
the bone it sits (t), in which direction round the bone (angle from the character's front), and how far it stands
off the asset body's surface in that direction (clearance). The vertex is rebuilt at the same t, angle and
clearance on OUR bone and OUR body surface, and the per-bone results are blended with the garment's own weights.
So the cloth follows our proportions and our chest. Then anything still inside the body is pushed out, the body's
skin weights are copied onto the garment, and it is bound to our armature.
Nothing here is typed in per garment or per variant. The variant file itself is never saved."""
import bpy, sys, os, math, json
import numpy as np
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # tools/blender, for ajkit
from ajkit import paths as _paths
a = sys.argv[sys.argv.index("--") + 1:]
SEX, AGE, ASSET, OUTFIT = a[0], a[1], a[2], a[3]
KEY = f"{SEX}_{AGE}"
# A fit that passes the check is written to FINAL. One that fails is never written there: it goes to STAGING with
# its report and renders, so it can be opened and inspected.
FINAL = str(_paths.STAGING / OUTFIT / KEY / "pass")      # tools/chars_aj/fit.py files a pass under library/wardrobe
OUTDIR = str(_paths.STAGING / OUTFIT / KEY)
os.makedirs(OUTDIR, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(_paths.BODIES / f"Aj_{KEY}.blend"))
from ajkit import garments as G
from ajkit import stage, sheetutil, fitcheck

arm = G.arm_obj(); body = G.body_obj()
P = "mixamorig:"
LOG = {"variant": KEY}
CLEAR = 0.006            # least cloth-to-skin distance, metres
T_LO, T_HI, T_N, A_N = -0.6, 1.6, 45, 72
BONES = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "LeftShoulder", "LeftArm", "LeftForeArm", "RightShoulder",
         "RightArm", "RightForeArm", "LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"]


CHAIN_NEXT = {"Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "LeftUpLeg": "LeftLeg",
              "RightUpLeg": "RightLeg", "LeftShoulder": "LeftArm", "RightShoulder": "RightArm",
              "LeftArm": "LeftForeArm", "RightArm": "RightForeArm"}
CHAIN_PREV = {v: k for k, v in CHAIN_NEXT.items()}
ORIG_W = {}
ASSET_CLEAR = {}
VALID = {}
VARIATION = {}
KEEP_SHARE = 0.0        # a bone carrying less than this share of a garment's weight in the asset does not move it here


def short(n):
    return n.split(":")[-1]


def rest_mesh(ob, armature, rest=True):
    """World coordinates and triangles of a mesh, its armature in rest pose (or as posed), modifiers applied."""
    armature.data.pose_position = 'REST' if rest else 'POSE'
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    oe = ob.evaluated_get(dg); me = oe.data
    me.calc_loop_triangles()
    co = np.array([oe.matrix_world @ v.co for v in me.vertices])
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    return co, tris


def bone_axes(armature, leg_to_ankle=None):
    ax = {}
    bones = {short(b.name): b for b in armature.data.bones}
    for n in BONES:
        b = bones.get(n)
        if b is None:
            continue
        h = np.array(armature.matrix_world @ b.head_local); e = np.array(armature.matrix_world @ b.tail_local)
        kids = [c for c in b.children if short(c.name) in bones]
        # the bone's working end is the joint it leads to, not Blender's display tail
        nxt = {"Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "LeftShoulder": "LeftArm",
               "LeftArm": "LeftForeArm", "LeftForeArm": "LeftHand", "RightShoulder": "RightArm", "RightArm": "RightForeArm",
               "RightForeArm": "RightHand", "LeftUpLeg": "LeftLeg", "RightUpLeg": "RightLeg", "LeftLeg": "LeftFoot",
               "RightLeg": "RightFoot", "Neck": "Head"}.get(n)
        if nxt in bones:
            e = np.array(armature.matrix_world @ bones[nxt].head_local)
        ax[n] = (h, e)
    return ax


def frame(h, e):
    w = e - h; L = np.linalg.norm(w); w = w / L
    ref = np.array((0.0, -1.0, 0.0))                      # the character's front
    if abs(w @ ref) > 0.9:
        ref = np.array((0.0, 0.0, 1.0))
    u = ref - w * (ref @ w); u /= np.linalg.norm(u)
    v = np.cross(w, u)
    return w, u, v, L


def core_axes(bvh, axes):
    """Move each bone's axis sideways to the middle of the body round it. A skeleton's shoulder bone can run along
    the very top of the shoulder; cloth lying there is then next to the axis, and "which direction round the bone"
    means nothing. With the axis in the middle of the flesh, cloth is always well away from it."""
    out = {}
    for n, (h, e) in axes.items():
        w, u, v, L = frame(h, e)
        o = h + (e - h) * 0.5
        pts = []
        for j in range(72):
            th = 2 * math.pi * j / 72
            d = Vector(u * math.cos(th) + v * math.sin(th))
            hit = bvh.ray_cast(Vector(o) + d * 0.25, -d, 0.5)
            if hit[0] is not None and hit[1].dot(d) > 0.0:
                pts.append(np.array(hit[0]))
        sh = np.zeros(3)
        if len(pts) >= 12:
            c = np.mean(pts, axis=0) - o
            sh = c - w * (c @ w)
            ln = np.linalg.norm(sh)
            if ln > 0.08:
                sh *= 0.08 / ln
        out[n] = (h + sh, e + sh)
    return out


def taut_ring(r, angs):
    """The outline a taut band would take round a ring of the body: its convex hull, as a radius per direction."""
    pts = np.c_[r * np.cos(angs), r * np.sin(angs)]
    P_ = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h
    H = np.array(half(P_)[:-1] + half(P_[::-1])[:-1])
    if len(H) < 3:
        return r
    E = np.roll(H, -1, axis=0) - H
    d = np.c_[np.cos(angs), np.sin(angs)]
    cdE = d[:, None, 0] * E[None, :, 1] - d[:, None, 1] * E[None, :, 0]
    cHE = (H[:, 0] * E[:, 1] - H[:, 1] * E[:, 0])[None, :]
    cHd = H[None, :, 0] * d[:, None, 1] - H[None, :, 1] * d[:, None, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        s = cHE / cdE; u = cHd / cdE
    ok = (np.abs(cdE) > 1e-12) & (s > 0) & (u >= -1e-9) & (u <= 1 + 1e-9)
    best = np.where(ok, s, -np.inf).max(axis=1)
    return np.where(np.isfinite(best), np.maximum(best, r), r)


def radius_table(bvh, h, e):
    """Distance from the bone axis to the body surface, on a grid of (position along the bone, angle round it)."""
    w, u, v, L = frame(h, e)
    ts = np.linspace(T_LO, T_HI, T_N); angs = np.linspace(-math.pi, math.pi, A_N, endpoint=False)
    R = np.full((T_N, A_N), np.nan)
    for i, t in enumerate(ts):
        o = Vector(h + (e - h) * t)
        for j, th in enumerate(angs):
            d = Vector(u * math.cos(th) + v * math.sin(th))
            hit = bvh.ray_cast(o, d)
            if hit[0] is not None and hit[1].dot(d) > 0.0:        # leaving the body: the axis point was inside
                R[i, j] = hit[3]
                continue
            # the axis runs just outside the skin here (a shoulder bone along the top of the shoulder): look
            # back at the body from a little way out and take the surface that faces us
            far = 0.15
            hit = bvh.ray_cast(o + d * far, -d, far + 0.06)
            if hit[0] is not None and hit[1].dot(d) > 0.0:
                R[i, j] = far - hit[3]                            # may be slightly negative: skin behind the axis
    ok = ~np.isnan(R)
    if ok.any():
        med = np.nanmedian(R)
        R[ok & (R > 2.5 * med)] = np.nan                         # a ray that ran along a limb
    measured = ~np.isnan(R)
    for _ in range(200):                                          # fill gaps from their neighbours
        bad = np.isnan(R)
        if not bad.any():
            break
        nb = np.stack([np.roll(R, 1, 1), np.roll(R, -1, 1), np.vstack([R[:1], R[:-1]]), np.vstack([R[1:], R[-1:]])])
        cnt = (~np.isnan(nb)).sum(0)
        fill = np.where(cnt > 0, np.nansum(nb, 0) / np.maximum(cnt, 1), np.nan)
        R[bad] = fill[bad]
    R = np.nan_to_num(R, nan=0.05)
    for _ in range(2):                                            # the body meshes are coarse: soften the table
        R = (2 * R + np.roll(R, 1, 1) + np.roll(R, -1, 1)) / 4
        R[1:-1] = (2 * R[1:-1] + R[:-2] + R[2:]) / 4
    # cloth does not dip into a hollow of the body (between the breasts, down the spine, between the buttocks):
    # it bridges it. Where a whole ring round the bone was measured, use the outline a taut band would take.
    for i in np.nonzero(measured.all(axis=1))[0]:
        R[i] = taut_ring(np.maximum(R[i], 0.004), angs)
    VALID[id(R)] = measured.astype(float)                        # where the table is a real measurement
    # how much the radius jumps round each cell: across a jump (shoulder top seen from the spine: neck one side,
    # the whole arm the other) a small difference between two bodies moves cloth a long way
    nbs = [np.roll(np.roll(R, a, 1), b, 0) for a in (-1, 0, 1) for b in (-1, 0, 1)]
    for k in range(len(nbs)):
        nbs[k][0] = R[0]; nbs[k][-1] = R[-1]
    VARIATION[id(R)] = np.max(nbs, 0) - np.min(nbs, 0)
    return R


def hull2d(q):
    """Convex hull of 2D points, counter-clockwise."""
    P_ = q[np.lexsort((q[:, 1], q[:, 0]))]

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h
    return np.array(half(P_)[:-1] + half(P_[::-1])[:-1])


def hull_table(co, tris, h, e):
    """Like radius_table, for an axis that runs OUTSIDE the body: straight down between the legs. A skirt goes round
    both legs together, so what it lies on is the outline a band would take round the whole body at each height (the
    convex hull of the body's cross-section there). Returns that outline as a distance from the axis, on the same
    grid of (position along the axis, direction round it)."""
    w, u, v, L = frame(h, e)
    ts = np.linspace(T_LO, T_HI, T_N); angs = np.linspace(-math.pi, math.pi, A_N, endpoint=False)
    R = np.full((T_N, A_N), np.nan)
    T3 = np.array(tris)
    E = np.unique(np.sort(np.vstack([T3[:, [0, 1]], T3[:, [1, 2]], T3[:, [2, 0]]]), axis=1), axis=0)
    P0, P1 = co[E[:, 0]], co[E[:, 1]]
    s0 = (P0 - h) @ w; s1 = (P1 - h) @ w
    D = np.c_[np.cos(angs), np.sin(angs)]
    for i, t in enumerate(ts):
        if t < -0.35:
            continue                                               # above the hip joints: the spine's business
        a = t * L
        m = (s0 < a) != (s1 < a)
        if m.sum() < 8:
            continue
        f = ((a - s0[m]) / (s1[m] - s0[m]))[:, None]
        X = P0[m] + f * (P1[m] - P0[m]) - h
        Hc = hull2d(np.c_[X @ u, X @ v])
        if len(Hc) < 3:
            continue
        Ed = np.roll(Hc, -1, axis=0) - Hc
        N = np.c_[Ed[:, 1], -Ed[:, 0]]
        N /= np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]
        c = (N * Hc).sum(1)
        if (c <= 1e-6).any():
            continue                                               # the axis is not inside the outline here
        nd = D @ N.T
        with np.errstate(divide="ignore"):
            R[i] = np.where(nd > 1e-9, c[None, :] / nd, np.inf).min(1)
    measured = ~np.isnan(R)
    rows = np.nonzero(measured.all(axis=1))[0]
    if not len(rows):
        return None
    for i in range(T_N):                                           # heights where nothing was cut: the nearest that was
        if not measured[i].all():
            R[i] = R[rows[np.argmin(np.abs(rows - i))]]
    R[1:-1] = (2 * R[1:-1] + R[:-2] + R[2:]) / 4
    VALID[id(R)] = measured.astype(float)
    nbs = [np.roll(np.roll(R, a_, 1), b_, 0) for a_ in (-1, 0, 1) for b_ in (-1, 0, 1)]
    for k in range(len(nbs)):
        nbs[k][0] = R[0]; nbs[k][-1] = R[-1]
    VARIATION[id(R)] = np.max(nbs, 0) - np.min(nbs, 0)
    return R


def lookup(R, t, th):
    ft = np.clip((t - T_LO) / (T_HI - T_LO) * (T_N - 1), 0, T_N - 1.001)
    fa = (th + math.pi) / (2 * math.pi) * A_N
    i0 = ft.astype(int); j0 = np.floor(fa).astype(int)
    dt = ft - i0; da = fa - j0
    j0 %= A_N; j1 = (j0 + 1) % A_N
    return (R[i0, j0] * (1 - dt) * (1 - da) + R[i0 + 1, j0] * dt * (1 - da) + R[i0, j1] * (1 - dt) * da + R[i0 + 1, j1] * dt * da)


# ------------------------------------------------------------------ our body
BCO, BTRI = rest_mesh(body, arm)
BVH_B = BVHTree.FromPolygons([Vector(p) for p in BCO], BTRI)
AXR_B = fitcheck.bone_axes(arm)                      # the skeleton's own joints
AX_B = core_axes(BVH_B, AXR_B)                      # the same bones, run through the middle of the body
BM_REST = fitcheck._eval(body)                      # for the skin-through relief pass (unmasked, rest)
BVH_B_TRI = fitcheck._bvh(BM_REST)                  # same triangles, indexed like BM_REST
TAB_B = {n: radius_table(BVH_B, *AX_B[n]) for n in AX_B}
LOG["height"] = round(float(BCO[:, 2].max()), 3)

# ------------------------------------------------------------------ the asset
col = G.collection("Dress")
with bpy.data.libraries.load(ASSET, link=False) as (src, dst):
    dst.objects = list(src.objects)
objs = [o for o in dst.objects if o is not None]


def asset_problems(objs):
    """Why this asset cannot be fitted, in words (empty when it can). The same rules as prep_asset.py -- check."""
    out = []
    arms_ = [o for o in objs if o.type == 'ARMATURE']
    meshes_ = [o for o in objs if o.type == 'MESH']
    if len(arms_) != 1:
        out.append(f"{len(arms_)} armatures (need exactly one)")
    else:
        have = {short(b.name) for b in arms_[0].data.bones}
        miss = [b for b in BONES if b not in have]
        if miss:
            out.append("the armature has no Mixamo-named bones " + ", ".join(miss)
                       + (" (it is a Rigify rig)" if any(b.name.startswith("DEF-") for b in arms_[0].data.bones) else ""))
    nb = [o for o in meshes_ if o.name.split(".")[0] == "Body"]
    if len(nb) != 1:
        out.append(f"{len(nb)} meshes named `Body` (need exactly one: the body the clothes were modelled on)")
    if len(meshes_) - len(nb) < 1:
        out.append("no garment mesh besides the body")
    if len(meshes_) - len(nb) > 8:
        out.append(f"{len(meshes_) - len(nb)} meshes besides the body: every one would be fitted as a garment")
    return out


_bad = asset_problems(objs)
if _bad:
    print("ASSET NOT READY", ASSET)
    for _p in _bad:
        print("  -", _p)
    print("Check and convert it first:  blender --background <asset.blend> --python work\\dress_test\\prep_asset.py -- check")
    print("(see scripts\\FITCHECK.md, \"Get an asset ready\")")
    sys.exit(2)
for o in objs:
    col.objects.link(o)
a_arm = next(o for o in objs if o.type == 'ARMATURE')
a_arm.animation_data_clear()
a_body = next(o for o in objs if o.type == 'MESH' and o.name.split(".")[0] == "Body")
garments = [o for o in objs if o.type == 'MESH' and o is not a_body]


def align_asset_pose():
    """Pose the asset like our rest pose (its arms are down, ours are out) and let its own skinning carry its body
    and its cloth there. After this, the same bone means the same direction on both, so cloth near a joint is not
    swung about by which bone happens to describe it."""
    a_arm.data.pose_position = 'POSE'
    for pb in a_arm.pose.bones:
        pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0); pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    tgt = fitcheck.bone_axes(arm)
    pbs = {short(pb.name): pb for pb in a_arm.pose.bones}
    turned = {}
    for n in ("LeftShoulder", "LeftArm", "LeftForeArm", "RightShoulder", "RightArm", "RightForeArm",
              "LeftUpLeg", "LeftLeg", "RightUpLeg", "RightLeg"):
        if n not in tgt or n not in pbs:
            continue
        cur = fitcheck.bone_axes(a_arm, posed=True)[n]
        d0 = Vector(cur[1] - cur[0]).normalized(); d1 = Vector(tgt[n][1] - tgt[n][0]).normalized()
        ang = d0.angle(d1)
        if ang < math.radians(2):
            continue
        q = d0.rotation_difference(d1)
        pb = pbs[n]
        Mw = a_arm.matrix_world @ pb.matrix
        head = Mw.translation.copy()
        pb.matrix = a_arm.matrix_world.inverted() @ (Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ Mw)
        bpy.context.view_layer.update()
        turned[n] = round(math.degrees(ang), 1)
    LOG["asset_pose_aligned_deg"] = turned


def spread_thighs(deg=15.0):
    """Pose the asset with each thigh turned outwards (about the front-back axis through its hip joint)."""
    a_arm.data.pose_position = 'POSE'
    for pb in a_arm.pose.bones:
        pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0); pb.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    pbs = {short(pb.name): pb for pb in a_arm.pose.bones}
    for n, sgn in (("LeftUpLeg", 1.0), ("RightUpLeg", -1.0)):
        if n not in pbs:
            continue
        pb = pbs[n]
        q = Quaternion((0.0, 1.0, 0.0), math.radians(-sgn * deg))
        Mw = a_arm.matrix_world @ pb.matrix
        head = Mw.translation.copy()
        pb.matrix = a_arm.matrix_world.inverted() @ (Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ Mw)
        bpy.context.view_layer.update()


# the crotch is measured on the asset twice, in its own rest pose and with its thighs spread, and the HIGHER is taken.
# Where inner thighs touch, a ray up the middle stops at the touching thighs and not at the fork: 9 cm too low once
# the asset's legs are turned to ours (below), and 8 cm too low on a stand-in body whose rest pose has its legs
# turned in to a standalone garment's trouser legs. Spreading the thighs shows the fork, but it also drags the skin
# there down a little (16 mm on the Carlo body), so where the rest pose already shows the fork, that is the truer one.
ACO0, _ = rest_mesh(a_body, a_arm, rest=True)
BVH_A0 = BVHTree.FromPolygons([Vector(p) for p in ACO0], _)
spread_thighs()
ACO0S, _ = rest_mesh(a_body, a_arm, rest=False)
BVH_A0S = BVHTree.FromPolygons([Vector(p) for p in ACO0S], _)
align_asset_pose()
ACO, ATRI = rest_mesh(a_body, a_arm, rest=False)
BVH_A = BVHTree.FromPolygons([Vector(p) for p in ACO], ATRI)
AXR_A = fitcheck.bone_axes(a_arm, posed=True)
AX_A = core_axes(BVH_A, AXR_A)
TAB_A = {n: radius_table(BVH_A, *AX_A[n]) for n in AX_A}
LOG["asset_body_height"] = round(float(ACO[:, 2].max()), 3)


def chain_shift_maps():
    """Each bone stretches the cloth along it by its own length ratio (thigh x0.83, shin x1.09...). Where cloth
    crosses a joint, that is a sudden change: a waistband lying across the hip/spine joint has its sides stretched
    more than its middle. Blend the stretch over 10 cm round each joint. Returns, per bone, how far to slide a
    point along the body compared with the bone-by-bone result."""
    maps = {}
    for names in fitcheck.CHAINS:
        names = [n for n in names if n in AX_A and n in AX_B]
        if len(names) < 2:
            continue
        LAs = np.array([frame(*AX_A[n])[3] for n in names]); LBs = np.array([frame(*AX_B[n])[3] for n in names])
        cumA = np.r_[0.0, np.cumsum(LAs)]; cumB = np.r_[0.0, np.cumsum(LBs)]
        grid = np.arange(-0.4, cumA[-1] + 0.4, 0.002)
        seg = np.clip(np.searchsorted(cumA, grid, side="right") - 1, 0, len(names) - 1)
        slope = (LBs / LAs)[seg]
        G = cumB[seg] + (grid - cumA[seg]) * slope
        k = 51                                                     # 10 cm of asset length
        sm = np.convolve(np.pad(slope, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
        F = np.cumsum(sm) * 0.002
        F += G[0] - F[0]
        for i, n in enumerate(names):
            maps[n] = (cumA[i], LAs[i], grid, F - G)
    return maps


CHAIN_SHIFT = chain_shift_maps()


def crotch_marks():
    """The crotch is a landmark both bodies have. Between the hip bone and the crotch, and between the crotch and
    the knee, the two bodies can be proportioned very differently (a child's thigh is half the asset's). Measure
    where the crotch is on each, so that cloth at the crotch stays at the crotch whichever bone describes it."""
    def cz(co, ax, bvh):
        """Height of the crotch: the roof of the fork between the thighs, found with vertical rays going up the middle
        of the body from below (the lowest point where one hits). It was the lowest body vertex within 12 mm of the
        middle plane: on a body whose inner thighs touch for a stretch (the asset's), those thigh vertices lie in that
        strip and put the crotch 7 cm too low, so the asset's crotch cloth was mapped 8 cm up into our pelvis."""
        cx, cy, hz = ax["Hips"][0][0], ax["Hips"][0][1], ax["Hips"][0][2]
        H = co[:, 2].max()
        zs = []
        for y in cy + np.linspace(-0.035 * H, 0.035 * H, 15):
            hit = bvh.ray_cast(Vector((cx, y, 0.2 * H)), Vector((0, 0, 1)))
            if hit[0] is not None and 0.25 * H < hit[0].z < hz:
                zs.append(float(hit[0].z))
        if zs:
            return min(zs)
        m = (np.abs(co[:, 0] - cx) < 0.012) & (co[:, 2] < hz) & (co[:, 2] > 0.25 * H)
        return float(co[m, 2].min()) if m.any() else None
    zA0, zAS = cz(ACO0, AX_A, BVH_A0), cz(ACO0S, AX_A, BVH_A0S)
    zA = max([z for z in (zA0, zAS) if z is not None], default=None)
    LOG["asset_crotch_rest_and_spread"] = [zA0, zAS]
    zB = cz(BCO, AX_B, BVH_B)
    if zA is None or zB is None or "Hips" not in AX_A:
        return None
    out = {"zA": zA, "zB": zB, "DA": max(AX_A["Hips"][0][2] - zA, 0.02), "DB": max(AX_B["Hips"][0][2] - zB, 0.02)}
    for n in ("LeftUpLeg", "RightUpLeg"):
        if n in AX_A and n in AX_B:
            wa, _, _, la = frame(*AX_A[n]); wb, _, _, lb = frame(*AX_B[n])
            ca = float(np.clip((zA - AX_A[n][0][2]) * wa[2] / la, 0.05, 0.8))
            cb = float(np.clip((zB - AX_B[n][0][2]) * wb[2] / lb, 0.05, 0.8))
            out[n] = (ca, cb)
    return out


CROTCH = crotch_marks()
LOG["crotch"] = {k: (round(float(v), 3) if np.ndim(v) == 0 else [round(float(x), 3) for x in v]) for k, v in (CROTCH or {}).items()}
LOG["bones_used"] = sorted(set(AX_A) & set(AX_B))


def skirt_setup():
    """A skirt (or the skirt of a dress) hangs round both legs together. It is described on its own axis: straight
    down from the crotch to the height of the ankles, midway between the hip joints. Along it the knee is a landmark
    (a knee-length skirt stays knee-length whatever the proportions of thigh and shin). Returns None when the bodies
    do not give the landmarks."""
    need = ("LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg")
    if not CROTCH or any(n not in AXR_A or n not in AXR_B for n in need):
        return None
    out = {}
    for tag, AXR, zc, co, tris in (("A", AXR_A, CROTCH["zA"], ACO, ATRI), ("B", AXR_B, CROTCH["zB"], BCO, BTRI)):
        c = 0.5 * (AXR["LeftUpLeg"][0] + AXR["RightUpLeg"][0])
        zk = 0.5 * (AXR["LeftLeg"][0][2] + AXR["RightLeg"][0][2]); za = 0.5 * (AXR["LeftLeg"][1][2] + AXR["RightLeg"][1][2])
        if not zc > zk > za:
            return None
        h = np.array((c[0], c[1], zc)); e = np.array((c[0], c[1], za))
        tab = hull_table(co, tris, h, e)
        if tab is None:
            return None
        out[tag] = (h, e, float((zc - zk) / (zc - za)), tab, float((AXR["Hips"][0][2] - zc) / (zc - za)) if "Hips" in AXR else 0.2)
    return out


SKIRT_AX = skirt_setup()
if SKIRT_AX:
    AX_A["Skirt"] = SKIRT_AX["A"][:2]; AX_B["Skirt"] = SKIRT_AX["B"][:2]
    TAB_A["Skirt"] = SKIRT_AX["A"][3]; TAB_B["Skirt"] = SKIRT_AX["B"][3]
    LOG["skirt_axis"] = {"knee_at_A": round(SKIRT_AX["A"][2], 3), "knee_at_B": round(SKIRT_AX["B"][2], 3)}


def skirt_like(o):
    """Does this garment have cloth below the crotch that goes round BOTH legs in one piece (a skirt, a dress)?
    Trousers do not: cut across below the crotch, each piece of cloth stays on one side. Decided by cutting the
    garment 10 cm and 18 cm below the asset's crotch and following each cut piece through the mesh."""
    if not SKIRT_AX:
        return False
    a_arm.data.pose_position = 'POSE'
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    oe = o.evaluated_get(dg); me = oe.data                        # with its modifiers (a mirrored half is whole here)
    co = np.array([oe.matrix_world @ v.co for v in me.vertices])
    cx = AX_A["Skirt"][0][0]
    E = np.empty(len(me.edges) * 2, int); me.edges.foreach_get("vertices", E); E = E.reshape(-1, 2)
    le = np.empty(len(me.loops), int); me.loops.foreach_get("edge_index", le)
    lp = np.repeat(np.arange(len(me.polygons)), [p.loop_total for p in me.polygons])
    for below in (0.10, 0.18):
        z = CROTCH["zA"] - below
        za, zb = co[E[:, 0], 2], co[E[:, 1], 2]
        cross = (za < z) != (zb < z)
        ce = np.nonzero(cross)[0]
        if len(ce) < 8:
            continue
        par = {int(i): int(i) for i in ce}

        def f(x):
            while par[x] != x:
                par[x] = par[par[x]]; x = par[x]
            return x
        m = cross[le]
        lpm, lem = lp[m], le[m]
        od = np.argsort(lpm, kind="stable"); lpm, lem = lpm[od], lem[od]
        for i in np.nonzero(lpm[1:] == lpm[:-1])[0]:
            par[f(int(lem[i]))] = f(int(lem[i + 1]))
        tt = ((z - za[ce]) / (zb[ce] - za[ce]))[:, None]
        px = (co[E[ce, 0]] + tt * (co[E[ce, 1]] - co[E[ce, 0]]))[:, 0]
        roots = np.array([f(int(i)) for i in ce])
        for r_ in np.unique(roots):
            x = px[roots == r_]
            if x.min() < cx - 0.03 and x.max() > cx + 0.03:
                return True
    return False


def fit(ob):
    # bake modifiers (subdivision) with the asset in rest pose, keep the weights
    a_arm.data.pose_position = 'POSE'                 # the aligned pose
    for m in ob.modifiers:
        if m.type == 'SUBSURF':
            m.levels = max(m.levels, 1)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    mw = ob.matrix_world.copy()
    newme = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    ob.data = newme; ob.parent = None
    ob.data.transform(mw); ob.matrix_world = Matrix.Identity(4)
    me = ob.data
    n = len(me.vertices)
    V = np.array([v.co[:] for v in me.vertices])
    # the fit record the check needs: where each vertex was on the asset and how far off the asset's body
    for nm, tp in (("fit_asset_co", "FLOAT_VECTOR"), ("fit_asset_clear", "FLOAT")):
        if me.attributes.get(nm):
            me.attributes.remove(me.attributes[nm])
        me.attributes.new(nm, tp, "POINT")
    me.attributes["fit_asset_co"].data.foreach_set("vector", V.astype(np.float32).ravel())
    CA = np.array([BVH_A.find_nearest(Vector(p))[3] for p in V])
    me.attributes["fit_asset_clear"].data.foreach_set("value", CA.astype(np.float32))
    ASSET_CLEAR[ob.name] = CA
    ch, s_along = fitcheck.chain_address(V, AXR_A)
    for nm, tp in (("fit_asset_chain", "INT"), ("fit_asset_s", "FLOAT")):
        if me.attributes.get(nm):
            me.attributes.remove(me.attributes[nm])
        me.attributes.new(nm, tp, "POINT")
    me.attributes["fit_asset_chain"].data.foreach_set("value", ch.astype(np.int32))
    me.attributes["fit_asset_s"].data.foreach_set("value", s_along.astype(np.float32))
    gname ={g.index: short(g.name) for g in ob.vertex_groups}
    use = [b for b in BONES if b in AX_A and b in AX_B]
    is_skirt = bool(SKIRT.get(ob.name)) and "Skirt" in AX_A and "Hips" in use
    if is_skirt:
        use.append("Skirt")                           # no asset weights of its own: it is given cloth by place, below
    W = np.zeros((n, len(use)))
    for v in me.vertices:
        for g in v.groups:
            nm = gname.get(g.group)
            if nm in use:
                W[v.index, use.index(nm)] += g.weight
    # a vertex weighted only to bones the asset rig does not have (hands, feet): give it the nearest limb bone
    lost = W.sum(1) < 1e-4
    if lost.any():
        for i in np.nonzero(lost)[0]:
            d = [np.linalg.norm(V[i] - (AX_A[b][0] + AX_A[b][1]) / 2) for b in use]
            W[i, int(np.argmin(d))] = 1.0
    share = W.sum(0) / W.sum()
    ORIG_W[ob.name] = (use, W.copy(), {b: float(s) for b, s in zip(use, share)})
    # one entry per (vertex, bone it is weighted to). A vertex that lies past the end of that bone is described
    # on the next bone of the chain instead (a waistband above the hip bone belongs to the spine), so that
    # the place along the body is always measured on the segment the cloth is actually at.
    vi, ki = np.nonzero(W > 1e-4)
    wi = W[vi, ki]
    ki = ki.copy()

    def along_chains(passes):
        for _ in range(passes):
            for k, b in enumerate(use):
                m = ki == k
                if not m.any():
                    continue
                hA, eA = AX_A[b]
                wA, uA, vA, LA = frame(hA, eA)
                t = ((V[vi[m]] - hA) @ wA) / LA
                idx = np.nonzero(m)[0]
                nx, pv = CHAIN_NEXT.get(b), CHAIN_PREV.get(b)
                if nx in use:
                    ki[idx[t > 1.0]] = use.index(nx)
                if pv in use:
                    ki[idx[t < 0.0]] = use.index(pv)

    along_chains(3)
    # the hip bone branches into the two legs. Above the crotch the cloth is described round the pelvis; below
    # it, round the thigh on its side; the change is gradual over the 7 cm below the crotch. This is decided by
    # where the cloth is, not by the asset's weights (thigh weights reach up to the waist on most assets, but a
    # thigh's axis says nothing sensible about cloth on the belly).
    if "Hips" in use:
        kh = use.index("Hips")
        cx = AX_A["Hips"][0][0]
        cen = (np.abs(ACO[:, 0] - cx) < 0.012) & (ACO[:, 2] < AX_A["Hips"][0][2]) & (ACO[:, 2] > 0.25 * ACO[:, 2].max())
        z_crotch = CROTCH["zA"] if CROTCH else (float(ACO[cen, 2].min()) if cen.any() else float(AX_A["Hips"][0][2] - 0.08))
        LOG.setdefault("asset_crotch_z", round(z_crotch, 3))
        s = np.clip((z_crotch - V[vi, 2]) / 0.07, 0.0, 1.0); s = s * s * (3 - 2 * s)
        # which thigh: by side, changing over gradually across the middle 6 cm so the centre seam is not torn
        wl = np.clip((V[vi, 0] - cx) / 0.06 + 0.5, 0.0, 1.0); wl = wl * wl * (3 - 2 * wl)
        has_l, has_r = "LeftUpLeg" in use, "RightUpLeg" in use
        if not has_r:
            wl = np.ones_like(wl)
        if not has_l:
            wl = np.zeros_like(wl)
        add_v, add_k, add_w = [], [], []
        if is_skirt:
            # a skirt goes round both legs in one piece. Described round one thigh or the other it is pulled in
            # between the legs and torn down the middle (the first dress: the print smeared down the centre and the
            # check failed on stretch there). Below the crotch it is described on the skirt axis instead, whatever
            # the asset's weights say (they name a thigh or a shin: the nearest skin); above it, round the pelvis.
            ks = use.index("Skirt")
            # the skirt axis takes over from the hip joints down (all of it by the crotch), not from the crotch: between
            # the two the pelvis bone's own table has run out (it ends 6 cm below the hip joint) and held the cloth in
            # while the body widened, which left a pinched waist and a ledge where the skirt axis began
            zh = float(AXR_A["Hips"][0][2])
            s = np.clip((zh - V[vi, 2]) / max(zh - z_crotch, 0.02), 0.0, 1.0); s = s * s * (3 - 2 * s)
            idx = np.nonzero((ki == kh) & (s > 0))[0]
            add_v.append(vi[idx]); add_k.append(np.full(len(idx), ks)); add_w.append(wi[idx] * s[idx])
            for lg in ("LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg"):
                if lg not in use:
                    continue
                j = np.nonzero(ki == use.index(lg))[0]
                add_v.append(vi[j]); add_k.append(np.full(len(j), ks)); add_w.append(wi[j] * s[j])
                add_v.append(vi[j]); add_k.append(np.full(len(j), kh)); add_w.append(wi[j] * (1 - s[j]))
                wi[j] = 0.0
            wi[idx] = wi[idx] * (1 - s[idx])
            idx = np.zeros(0, int)                                 # nothing is left for the trouser rule below
        else:
            idx = np.nonzero((ki == kh) & (s > 0) & (has_l or has_r))[0]    # pelvis entries: the part below the crotch goes to the thighs
        for up, sw in (("LeftUpLeg", wl), ("RightUpLeg", 1 - wl)):
            if up in use and not is_skirt:
                add_v.append(vi[idx]); add_k.append(np.full(len(idx), use.index(up))); add_w.append(wi[idx] * s[idx] * sw[idx])
        for up in ("LeftUpLeg", "RightUpLeg"):                     # thigh entries: the part above the crotch goes to the pelvis
            if up not in use or is_skirt:
                continue
            j = np.nonzero((ki == use.index(up)) & (s < 1))[0]
            add_v.append(vi[j]); add_k.append(np.full(len(j), kh)); add_w.append(wi[j] * (1 - s[j]))
            wi[j] = wi[j] * s[j]
        wi[idx] = wi[idx] * (1 - s[idx])
        vi = np.concatenate([vi] + add_v); ki = np.concatenate([ki] + add_k); wi = np.concatenate([wi] + add_w)
        keep = wi > 1e-5
        vi, ki, wi = vi[keep], ki[keep], wi[keep]
        along_chains(2)
    # the collarbones branch off the spine as the legs branch off the pelvis. Cloth inboard of where a collarbone
    # starts (over the breastbone, on the nape) and cloth round the neck above its base (a collar) is described
    # round the spine and the neck, not round a collarbone's axis carried on past its inner end. That axis says
    # where the SHOULDER is: on a body whose neck sits further forward of the shoulders than the asset's (the
    # seniors' stoop) it laid the collar back flat on the shoulders and pulled the neck opening down into a slot.
    # Decided by where the cloth is, not by the asset's weights, and changing over gradually.
    if "Spine2" in use:
        k2 = use.index("Spine2")
        add_v, add_k, add_w = [], [], []

        def sm(x):
            x = np.clip(x, 0.0, 1.0)
            return x * x * (3 - 2 * x)
        for sb in ("LeftShoulder", "RightShoulder"):
            if sb not in use:
                continue
            j = np.nonzero(ki == use.index(sb))[0]
            if not len(j):
                continue
            hA, eA = AX_A[sb]; wA = frame(hA, eA)[0]
            x = (V[vi[j]] - hA) @ wA                               # metres outboard of the collarbone's start
            f = 1 - sm((x + 0.03) / 0.06)                          # inboard of it: the spine's
            if "Neck" in AX_A:
                hN, eN = AX_A["Neck"]; wN = frame(hN, eN)[0]
                up = (V[vi[j]] - hN) @ wN                          # metres above the base of the neck
                f = np.maximum(f, sm((up + 0.04) / 0.04) * (1 - sm((x - 0.02) / 0.06)))    # round the neck: the neck's
            add_v.append(vi[j]); add_k.append(np.full(len(j), k2)); add_w.append(wi[j] * f)
            wi[j] = wi[j] * (1 - f)
        if add_v:
            LOG.setdefault("collarbone_to_spine_weight", {})[ob.name] = round(float(sum(w.sum() for w in add_w)), 1)
            vi = np.concatenate([vi] + add_v); ki = np.concatenate([ki] + add_k); wi = np.concatenate([wi] + add_w)
            keep = wi > 1e-5
            vi, ki, wi = vi[keep], ki[keep], wi[keep]
            along_chains(2)
    # near a joint, describe the cloth on BOTH bones and blend (half and half at the joint itself). Each bone's axis
    # runs through the middle of its own part of the body, so two neighbouring bones do not quite meet; a hard
    # switch from one to the other at the joint leaves a small ledge in the cloth there.
    add_v, add_k, add_w = [], [], []
    for k, b in enumerate(use):
        mm = np.nonzero(ki == k)[0]
        if not len(mm):
            continue
        hA, eA = AX_A[b]; wA, _, _, LA = frame(hA, eA)
        tt = ((V[vi[mm]] - hA) @ wA) / LA
        give = np.zeros(len(mm))
        for other, frac in ((CHAIN_NEXT.get(b), np.clip((tt - 0.75) / 0.5, 0, 1)), (CHAIN_PREV.get(b), np.clip((0.25 - tt) / 0.5, 0, 1))):
            if other not in use:
                continue
            fr = frac * frac * (3 - 2 * frac)
            sel = fr > 0
            if sel.any():
                add_v.append(vi[mm[sel]]); add_k.append(np.full(int(sel.sum()), use.index(other))); add_w.append(wi[mm[sel]] * fr[sel])
                give[sel] += fr[sel]
        wi[mm] = wi[mm] * (1 - np.clip(give, 0, 1))
    if add_v:
        vi = np.concatenate([vi] + add_v); ki = np.concatenate([ki] + add_k); wi = np.concatenate([wi] + add_w)
        keep = wi > 1e-5
        vi, ki, wi = vi[keep], ki[keep], wi[keep]
    out = np.zeros((n, 3)); wsum = np.zeros(n)
    out_r = np.zeros((n, 3)); wsum_r = np.zeros(n)
    rigid = np.zeros((n, 3)); rsum = np.zeros(n); stats = {}
    for k, b in enumerate(use):
        m = ki == k
        if not m.any():
            continue
        sel = vi[m]; wgt = wi[m]
        hA, eA = AX_A[b]; hB, eB = AX_B[b]
        wA, uA, vA, LA = frame(hA, eA); wB, uB, vB, LB = frame(hB, eB)
        rel = V[sel] - hA
        t = (rel @ wA) / LA
        rad = rel - np.outer(t * LA, wA)
        rho = np.linalg.norm(rad, axis=1)
        th = np.arctan2(rad @ vA, rad @ uA)
        # the same place along OUR bone: usually the same fraction t, but the crotch must land on the crotch
        tB = t.copy()
        if CROTCH and b == "Hips":
            low = t < 0
            tB[low] = -(-t[low] * LA) * (CROTCH["DB"] / CROTCH["DA"]) / LB
        elif CROTCH and b in CROTCH:
            ca, cb = CROTCH[b]
            tB = np.where(t <= ca, t * cb / ca, cb + (t - ca) * (1 - cb) / (1 - ca))
        elif b == "Skirt":                                         # the knee lands on the knee
            ca, cb = SKIRT_AX["A"][2], SKIRT_AX["B"][2]
            tB = np.where(t <= ca, t * cb / ca, cb + (t - ca) * (1 - cb) / (1 - ca))
            tB = np.where(t < 0, t * SKIRT_AX["B"][4] / max(SKIRT_AX["A"][4], 1e-3), tB)      # above the crotch: hip joint lands on hip joint
        ra = lookup(TAB_A[b], t, th); rb = lookup(TAB_B[b], tB, th)
        delta = rho - ra                                           # clearance off the asset body
        # assets often let their own body cut into the cloth where nobody sees it (tight waistbands). Do not copy
        # that: cloth is rebuilt at least the minimum clearance off OUR skin, instead of being pushed out afterwards,
        # which leaves a step.
        rho_new = rb + np.maximum(delta, CLEAR)
        pos = hB + np.outer(tB * LB, wB) + (np.outer(np.cos(th), uB) + np.outer(np.sin(th), vB)) * rho_new[:, None]
        if b in CHAIN_SHIFT:                                       # even out the stretch across joints
            a0, La, grid, dF = CHAIN_SHIFT[b]
            pos = pos + np.outer(np.interp(a0 + t * La, grid, dF), wB)
        # this bone describes the vertex well only if the cloth is at or outside the body along its ray
        good = (delta > -0.02) & (delta < 0.30)
        # ...and only where both bodies were really measured in that direction (a ray that ran along a limb, or an
        # axis point outside the body, gives a filled-in guess: not a description of anything)
        good &= (lookup(VALID[id(TAB_A[b])], t, th) > 0.75) & (lookup(VALID[id(TAB_B[b])], tB, th) > 0.75)
        wk = wgt * np.where(good, 1.0, 0.0)
        np.add.at(out, sel, pos * wk[:, None]); np.add.at(wsum, sel, wk)
        # trust a bone's description less where the body's radius jumps (on either body)
        jump = lookup(VARIATION[id(TAB_A[b])], t, th) + lookup(VARIATION[id(TAB_B[b])], tB, th)
        wr = wk * np.exp(-jump / 0.03)
        np.add.at(out_r, sel, pos * wr[:, None]); np.add.at(wsum_r, sel, wr)
        # fallback: the bone's plain stretch (length by bone length, girth by the ratio of mean body radii)
        s = float(np.mean(TAB_B[b][10:35]) / max(np.mean(TAB_A[b][10:35]), 1e-4))
        pr = hB + np.outer(tB * LB, wB) + (np.outer(np.cos(th), uB) + np.outer(np.sin(th), vB)) * (rho * s)[:, None]
        np.add.at(rigid, sel, pr * wgt[:, None]); np.add.at(rsum, sel, wgt)
        stats[b] = {"entries": int(m.sum()), "good": int(good.sum()), "weight_share": round(float(share[k]), 3),
                    "girth_ratio": round(s, 3), "length_ratio": round(LB / LA, 3)}
    rigid /= np.maximum(rsum, 1e-9)[:, None]
    okv = wsum > 1e-4
    new = np.where(okv[:, None], out / np.maximum(wsum, 1e-9)[:, None], rigid)
    rel = wsum_r > 0.02 * np.maximum(wsum, 1e-9)                  # enough trustworthy description: use only that
    new = np.where((okv & rel)[:, None], out_r / np.maximum(wsum_r, 1e-12)[:, None], new)
    LOG.setdefault("_tmp", {})[ob.name] = int((okv & ~rel).sum())
    LOG[ob.name] = {"verts": n, "fallback_verts": int((~okv).sum()), "low_trust_verts": LOG["_tmp"].pop(ob.name), "bones": stats}
    me.vertices.foreach_set("co", new.astype(np.float32).ravel()); me.update()
    return ob


def neighbours(me):
    nb = [[] for _ in me.vertices]
    for e in me.edges:
        i, j = e.vertices
        nb[i].append(j); nb[j].append(i)
    return nb


def settle(ob, clear=CLEAR, others=()):
    """Smooth the cloth lightly, then push anything too close to the body (or an inner garment) outwards."""
    me = ob.data
    A = np.array([v.co[:] for v in me.vertices])
    # vertices that share a position on the asset (split seams) are one point of cloth: smooth them as one,
    # or the seam opens
    aco = np.empty(len(A) * 3); me.attributes["fit_asset_co"].data.foreach_get("vector", aco)
    aco3 = aco.reshape(-1, 3)
    rep = fitcheck.weld_map(aco3)
    sets = [set() for _ in A]
    for ed in me.edges:
        i, j = rep[ed.vertices[0]], rep[ed.vertices[1]]
        if i != j:
            sets[i].add(j); sets[j].add(i)
    nb = [sorted(sets[rep[i]]) for i in range(len(A))]
    trees = [(BVH_B, clear)] + [(BVHTree.FromPolygons([Vector(v.co) for v in o.data.vertices],
                                                      [tuple(p.vertices) for p in o.data.polygons]), 0.004) for o in others]
    pushed = 0; worst = 0.0
    for it in range(6):
        if it < 4:
            # smooth the MOVE each vertex made from its place on the asset, not the positions themselves: smoothing
            # positions spreads vertices evenly, which widens narrow seam strips and flattens folds the asset has
            D = A - aco3
            S = np.array([D[j].mean(0) if len(j) else D[i] for i, j in enumerate(nb)])
            A = (aco3 + D + 0.5 * (S - D))[rep]
        for tree, off in trees:
            need = np.zeros(len(A)); N = np.zeros((len(A), 3))
            for i, p in enumerate(A):
                hit, nrm, fi, d = tree.find_nearest(Vector(p))
                if hit is None:
                    continue
                if tree is not BVH_B and d > 0.03:
                    continue          # another garment is an open surface: far from it the sign of "inside" means nothing
                                      # (a shirt's shoulders were pushed 6 cm by the trousers' waistband normal)
                sd = (Vector(p) - hit).dot(nrm)
                N[i] = nrm
                need[i] = min(0.06, max(0.0, off - sd))
            if it == 0 and tree is BVH_B:
                pushed = int((need > 1e-4).sum()); worst = float(need.max())
            if need.max() < 1e-4:
                continue
            kd = KDTree(len(A))
            for i, p in enumerate(A):
                kd.insert(p, i)
            kd.balance()
            disp = need.copy()
            for i in np.nonzero(need > 0)[0]:
                for (_, j, dist) in kd.find_range(A[i], 0.03):
                    f = need[i] * (1 - dist / 0.03) ** 0.5
                    if f > disp[j]:
                        disp[j] = f
            A = A + N * disp[:, None]
    me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
    # cloth that lay close on the asset must lie close here: pull back whatever stands off too far
    CA = ASSET_CLEAR.get(ob.name)
    if CA is not None and len(CA) == len(A):
        allow = np.maximum(0.010, 0.6 * CA)
        for it in range(5):
            cb = np.zeros(len(A)); to = np.zeros((len(A), 3))
            for i, p in enumerate(A):
                hit, nrm, fi, dist = BVH_B.find_nearest(Vector(p))
                cb[i] = dist; to[i] = (np.array(hit) - p) / max(dist, 1e-9)
            over = cb - np.maximum(CA + 0.4 * allow, clear + 0.001)
            m = over > 0
            if not m.any():
                break
            A[m] += to[m] * (over[m] * 0.9)[:, None]
            A = A[rep]
        me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
    # skin can still come through BETWEEN cloth vertices where the cloth's faces are large: test the body's surface
    # against the cloth's surface and lift the cloth there, until nothing crosses
    relief = 0
    for it in range(12):
        if it == 6:
            if not relief:
                break
            # the lift leaves a step at its edge: smooth the moves once, then lift again whatever that let through
            A = np.array([v.co[:] for v in me.vertices])
            for _ in range(2):
                D = A - aco3
                S = np.array([D[j].mean(0) if len(j) else D[i] for i, j in enumerate(nb)])
                A = (aco3 + D + 0.5 * (S - D))[rep]
            me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
        gm = fitcheck._eval(ob); gb = fitcheck._bvh(gm)
        d = fitcheck._skin_through(BM_REST, BVH_B, [(ob.name, gm, gb)])[ob.name]
        amt = np.where(d > 0, d + 0.004, 0.0)
        for bi in {i for i, _ in BVH_B_TRI.overlap(gb)}:
            amt[bi] = max(amt[bi], 0.004)
        idx = np.nonzero(amt > 0)[0]
        if not len(idx):
            if it < 6:
                continue
            break
        relief += len(idx)
        A = np.array([v.co[:] for v in me.vertices])
        kd = KDTree(len(A))
        for i, p in enumerate(A):
            kd.insert(p, i)
        kd.balance()
        best = np.zeros(len(A)); disp = np.zeros((len(A), 3))
        for bi in idx:
            p = BM_REST["cen"][bi]; nrm = BM_REST["nrm"][bi]
            for (_, j, dist) in kd.find_range(Vector(p), 0.045):
                f = amt[bi] * (1 - dist / 0.045) ** 0.5
                if f > best[j]:
                    best[j] = f; disp[j] = nrm * f
        A = (A + disp)
        A[:] = A[rep] if False else A
        me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
    LOG[ob.name]["relief_points"] = relief
    A = np.array([v.co[:] for v in me.vertices])
    # last: no vertex nearer the skin than half the usual clearance (the smoothing above can let one sink)
    for i, p in enumerate(A):
        hit, nrm, fi, dist = BVH_B.find_nearest(Vector(p))
        sd = (Vector(p) - hit).dot(nrm)
        if sd < clear * 0.5:
            A[i] = p + np.array(nrm) * (clear * 0.5 - sd + 0.0005)
    me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
    # what is left after settling
    sd = []
    for p in A:
        hit, nrm, fi, d = BVH_B.find_nearest(Vector(p))
        sd.append((Vector(p) - hit).dot(nrm))
    sd = np.array(sd)
    LOG[ob.name].update({"pushed_out_verts": pushed, "deepest_before_mm": round(worst * 1000, 1),
                         "min_clearance_after_mm": round(float(sd.min() * 1000), 2),
                         "verts_inside_after": int((sd < 0).sum())})


def rigid_details(ob, max_size=0.12):
    """Buttons, zip pulls, studs: small separate pieces of a garment keep their shape. Each is put back as a whole
    (turned, moved and scaled evenly) where the fit placed it, then lifted clear of the skin if it touches."""
    me = ob.data
    A = np.array([v.co[:] for v in me.vertices])
    aco = np.empty(len(A) * 3); me.attributes["fit_asset_co"].data.foreach_get("vector", aco); aco = aco.reshape(-1, 3)
    par = list(range(len(A)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    for ed in me.edges:
        a, b = find(ed.vertices[0]), find(ed.vertices[1])
        if a != b:
            par[a] = b
    groups = {}
    for i in range(len(A)):
        groups.setdefault(find(i), []).append(i)
    count = 0
    for idx in groups.values():
        if len(idx) < 4 or len(idx) > 0.5 * len(A):
            continue
        idx = np.array(idx)
        P0 = aco[idx]; P1 = A[idx]
        if np.linalg.norm(P0.max(0) - P0.min(0)) > max_size:
            continue
        c0, c1 = P0.mean(0), P1.mean(0)
        H = (P0 - c0).T @ (P1 - c1)
        U, S, Vt = np.linalg.svd(H)
        d = np.sign(np.linalg.det(Vt.T @ U.T))
        Rm = Vt.T @ np.diag([1, 1, d]) @ U.T
        sc = float(np.sqrt(((P1 - c1) ** 2).sum() / max(((P0 - c0) ** 2).sum(), 1e-12)))
        Q = (P0 - c0) @ Rm.T * sc + c1
        lift = 0.0; nsum = np.zeros(3)
        for p in Q:
            hit, nrm, fi, dist = BVH_B.find_nearest(Vector(p))
            sd = (Vector(p) - hit).dot(nrm)
            lift = max(lift, CLEAR * 0.5 - sd); nsum += np.array(nrm)
        if lift > 0:
            Q = Q + nsum / max(np.linalg.norm(nsum), 1e-9) * lift
        A[idx] = Q; count += 1
    me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
    LOG[ob.name]["rigid_details"] = count


def bind(ob, name):
    use, W0, share = ORIG_W[ob.name]
    ob.name = name
    G.refit_weights(ob)
    # the body's skin weights, limited to the bones that moved this garment in the asset: a strap top must not
    # follow the upper arm just because a strap lies near it
    allowed = {b for b in use if share[b] >= KEEP_SHARE}
    idx ={g.index: short(g.name) for g in ob.vertex_groups}
    by_name = {short(g.name): g for g in ob.vertex_groups}
    dropped = 0
    for v in (ob.data.vertices if KEEP_SHARE > 0 else ()):   # 0 = keep the body's weights as they are
        keep = [(g.group, g.weight) for g in v.groups if idx[g.group] in allowed]
        gone = [g.group for g in v.groups if idx[g.group] not in allowed and g.weight > 0]
        if not gone:
            continue
        dropped += 1
        tot = sum(w for _, w in keep)
        for gi in gone:
            ob.vertex_groups[gi].remove([v.index])
        if tot < 1e-4:
            cand = [b for b in use if b in allowed]
            b = cand[int(np.argmax([W0[v.index, use.index(c)] for c in cand]))]
            g = by_name.get(b) or ob.vertex_groups.new(name=P + b)
            g.add([v.index], 1.0, 'REPLACE')
        else:
            for gi, w in keep:
                ob.vertex_groups[gi].add([v.index], w / tot, 'REPLACE')
    LOG[name] = {"moved_by": sorted(allowed), "verts_reweighted": dropped}
    am = ob.modifiers.new("Armature", "ARMATURE")
    am.object = arm; am.use_deform_preserve_volume = True
    for p in ob.data.polygons:
        p.use_smooth = True


def lower_body(o):
    """A garment that covers the legs (pants, jeans, shorts, leggings). It is fitted first and the other garments are
    kept off it. Decided by the name where the name says so, otherwise by shape: it reaches below the crotch on both
    sides of the middle. (It used to be the word "pant" in the name only, so a garment called "jeans" was treated as
    a top: the shirt hem was not kept off the waistband and the jeans came through it.)"""
    if any(k in o.name.lower() for k in ("pant", "jean", "trouser", "short", "legging")):
        return True
    if not CROTCH or "Hips" not in AX_A:
        return False
    co, _ = rest_mesh(o, a_arm, rest=False)
    cx = AX_A["Hips"][0][0]
    below = co[co[:, 2] < CROTCH["zA"] - 0.05]
    return len(below) > 0.1 * len(co) and bool((below[:, 0] > cx + 0.02).any() and (below[:, 0] < cx - 0.02).any())


LOWER = {g.name: lower_body(g) for g in garments}
LOG["lower_body_garments"] = sorted(k for k, v in LOWER.items() if v)
SKIRT = {g.name: skirt_like(g) for g in garments}
LOG["skirt_like_garments"] = sorted(k for k, v in SKIRT.items() if v)
done = []; done_lower = []
for g in sorted(garments, key=lambda o: 0 if LOWER[o.name] else 1):
    is_low = LOWER[g.name]
    fit(g)
    settle(g, others=done_lower if not is_low else ())
    rigid_details(g)
    bind(g, "D_" + g.name.split(".")[0])
    done.append(g)
    if is_low:
        done_lower.append(g)
from ajkit import fitreview
fitreview.store_reference(ACO, ATRI, done)          # the asset's body and the cloth as it sat on it, kept hidden
bpy.data.objects.remove(a_body, do_unlink=True)
bpy.data.objects.remove(a_arm, do_unlink=True)

# ------------------------------------------------------------------ check, mask, poses (scripts/fitcheck.py)
from ajkit import fitcheck
rest = fitcheck.rest_check(arm, body, done)                 # 1. unmasked body, rest pose
mask = fitcheck.build_mask(arm, body, done)                 # 2. hide skin well inside the covered area
posed = fitcheck.pose_check(arm, body, done)                # 3. masked body, standard poses
PASS = bool(rest["pass"] and posed["pass"])
LOG["fit_check"] = {"pass": PASS, "rest": rest, "mask": mask, "posed": posed}
text = fitcheck.summary(rest, mask, posed)

# ------------------------------------------------------------------ renders (masked body, as it will be used)
stage.setup_stage()
for nme, en in (("Key", 70), ("Fill", 30), ("Rim", 50)):
    bpy.data.objects[nme].data.energy = en
sc = bpy.context.scene
H = LOG["height"]
fitcheck.set_mask(body, True)


def shots(tag):
    fs = []
    for ang in (0, 40, 90, 180):
        cam = sc.camera; cam.data.lens = 75
        r = math.radians(ang); dist = H * 3.4; tz = H * 0.5
        cam.location = (math.sin(r) * dist, -math.cos(r) * dist, tz + 0.1)
        stage.look_at(cam, (0, 0, tz))
        sc.render.resolution_x, sc.render.resolution_y = 600, 900
        sc.render.resolution_percentage = 100
        fs.append(stage.render(os.path.join(OUTDIR, f"{KEY}_{tag}_{ang}.png")))
    return fs


arm.data.pose_position = 'POSE'
files = shots("rest")
poses = fitcheck.standard_poses(arm)
for pn in ("arms_down", "sit"):
    fitcheck.apply_pose(arm, poses[pn])
    files += shots(pn)
fitcheck.apply_pose(arm, {})
sheetutil.sheet(files, os.path.join(OUTDIR, f"{KEY}.png"), cols=4)
json.dump(LOG, open(os.path.join(OUTDIR, f"{KEY}_fit_report.json"), "w"), indent=1, default=float)
open(os.path.join(OUTDIR, f"{KEY}_fit_report.md"), "w", encoding="utf-8").write(text)

# ------------------------------------------------------------------ review sheets: asset beside fitted
# The review (an agent looking at these with the checklist in FITCHECK.md) is for fits that PASS the measured
# check. For a failed fit the sheets are made only when asked for with the word "review", to help find the cause.
if PASS or "review" in a[4:]:
    LOG["review_sheets"] = fitreview.sheets(arm, body, done, os.path.join(OUTDIR, f"{KEY}_review"))
    json.dump(LOG, open(os.path.join(OUTDIR, f"{KEY}_fit_report.json"), "w"), indent=1, default=float)

# ------------------------------------------------------------------ output: final only when the check passes
stale = os.path.join(FINAL, f"Aj_{KEY}_{OUTFIT}.blend")
failed = os.path.join(OUTDIR, f"Aj_{KEY}_{OUTFIT}_FAILED.blend")
if PASS:
    os.makedirs(FINAL, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=stale, copy=True, compress=True)
    open(os.path.join(FINAL, f"Aj_{KEY}_{OUTFIT}_fit_report.md"), "w", encoding="utf-8").write(text)
    if os.path.exists(failed):
        os.remove(failed)
    print("FITCHECK PASS", stale)
else:
    bpy.ops.wm.save_as_mainfile(filepath=failed, copy=True, compress=True)
    print("FITCHECK FAIL", failed, "(nothing written to", FINAL + ")")
print(text)
print("DONE")