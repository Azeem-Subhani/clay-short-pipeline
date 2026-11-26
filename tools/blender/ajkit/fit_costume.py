# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/dress_test/fit_costume.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the folders come from ajkit.paths (as in ajkit/fit_rigged.py), the
# fit modules are imported from ajkit, and costume= mode finds showcase, pose and the costume scripts in the pack's
# script folder. The fit method, its constants, the check and the pass rule are unchanged.
"""Fit a finished Aj costume (Aj_King/Pirate/Soldier.blend) to an Aj variant: a copy of fit_rigged.py (2026-11-26)
with two additions for costumes, so fit_rigged.py itself is untouched.

    blender --background --python fit_costume.py -- <Sex> <Age> <prepared.blend> <outfit> costume=<Aj_X.blend> [review]

<prepared.blend> holds the costume's skinned cloth and boots (prep_asset.py convert of the costume file). The cloth is
fitted exactly as fit_rigged.py does. Added:
  * RIGID PARTS (carry_rigid): everything else under the costume's armature is read from the costume file (never
    saved) in the REST pose and carried over without changing its shape:
      - on the head (bone-parented to Head, or skinned to Head only: hair, crown, hats, shako, eye patch): moved by
        our Head bone against the costume's Head bone. Aj's head has the same shape on every variant (measured: 0.0 mm
        in head-bone space), so hair and hats stay exactly fitted to it;
      - on the body (bone-parented elsewhere: buckles, buttons, pistol, parrot): moved with the fitted cloth under it
        (best rotation + translation of the nearest cloth vertices, asset rest -> fitted rest; no scaling), then
        bone-parented to the same bone;
      - in the hand (bone-parented to a hand: scepter, cutlass, musket): put in the hand by the costume's own
        place_* rule, which calls grips.hold, in the costume's presentation pose (showcase.presentation).
  * The grip result is part of the gate: a fit passes only if the cloth check passes AND grips reports ok.

Original fit_rigged.py description:

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
sys.path.append(str(_paths.PACK_SCRIPTS))   # costume= mode only: showcase, pose and the costume modules stay pack scripts
a = sys.argv[sys.argv.index("--") + 1:]
SEX, AGE, ASSET, OUTFIT = a[0], a[1], a[2], a[3]
KEY = f"{SEX}_{AGE}"
# A fit that passes the check is written to FINAL. One that fails is never written there: it goes to STAGING with
# its report and renders, so it can be opened and inspected.
FINAL = str(_paths.STAGING / OUTFIT / KEY / "pass")      # tools/chars_aj/fit.py files a pass under library/wardrobe
if "regress" in a[4:]:       # a regression run of the fitter: everything stays in staging, the final folder is not touched
    FINAL = str(_paths.STAGING / OUTFIT / KEY / "would_pass")
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
    if len(meshes_) - len(nb) > (16 if any(x.startswith("costume=") for x in a[4:]) else 8):   # a costume has more pieces
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


MIN_CLEAR = 0.002        # fitcheck fails cloth nearer the skin than 1.5 mm: keep at least this


def asset_gap(key, other_key):
    """How far each vertex of garment `key` stood off garment `other_key` on the asset (both in the asset's rest
    pose), for vertices within 3 cm of it; inf elsewhere."""
    o = next((x for x in bpy.data.objects if x.type == 'MESH' and x.name.split(".")[0] in (other_key, "D_" + other_key)), None)
    if o is None or key not in REST0 or other_key not in REST0:
        return None
    tr = BVHTree.FromPolygons([Vector(v) for v in REST0[other_key]], [tuple(p.vertices) for p in o.data.polygons])
    out = np.full(len(REST0[key]), np.inf)
    for i, q in enumerate(REST0[key]):
        hit, nrm, fi, d = tr.find_nearest(Vector(q))
        if hit is not None and d < 0.03:
            out[i] = (Vector(q) - hit).dot(nrm)
    return out


def settle(ob, clear=CLEAR, others=()):
    """Smooth the cloth lightly, then push anything too close to the body (or an inner garment) outwards.
    fit_costume.py: the room asked for is per vertex and never more than the cloth had on the asset (at least
    MIN_CLEAR from the skin). A sash that lay 2 mm over the trousers on the asset was pushed to 4 mm, along the
    trousers' normal at the seat, which slides it UP the back: 11 mm on the asset's own body, 0.28 bone lengths;
    on the kids (pelvis bone 6.3 cm) the same push is 0.35-0.46 bone lengths and failed "cloth in the wrong place"."""
    me = ob.data
    A = np.array([v.co[:] for v in me.vertices])
    key = ob.name.split(".")[0]
    CA0 = ASSET_CLEAR.get(ob.name)
    # the body keeps the usual clearance: asking less (the asset's own) let the polo show skin on Female Adult in the
    # jeans_shirt regression (arms down, 7.5 mm), 2026-11-26. Only the room between garments follows the asset.
    body_off = np.full(len(A), clear)
    other_off = {}
    for o in others:
        gp = asset_gap(key, o.name[2:].split(".")[0] if o.name.startswith("D_") else o.name.split(".")[0])
        other_off[o.name] = np.full(len(A), 0.004) if gp is None or len(gp) != len(A) else np.clip(gp, 0.001, 0.004)
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
    trees = [(BVH_B, body_off)] + [(BVHTree.FromPolygons([Vector(v.co) for v in o.data.vertices],
                                                      [tuple(p.vertices) for p in o.data.polygons]), other_off[o.name]) for o in others]
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
                need[i] = min(0.06, max(0.0, off[i] - sd))
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
        lim = min(clear * 0.5, body_off[i])
        if sd < lim:
            A[i] = p + np.array(nrm) * (lim - sd + 0.0005)
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
STAGES = {}; LOG['stages'] = STAGES

# What kind of piece a garment is decides how it is fitted (fit_costume.py). Decided by the name where the name says
# so, otherwise by shape, never by per-asset numbers:
#   foot  - boots and shoes (name, or: reaches below the ankle AND forward of it over the toes). Leather and soles do
#           not stretch: placed RIGID.
#   plate - armour and stiff ornaments (cuirass, shoulder guard, epaulette, greave, bracer...). Placed RIGID under the
#           same rule as a belt (rigid RMS gap to the cloth fit <= BELT_RMS); the Roman cuirass, greaves, bracers and
#           shoulder guard (16-20 mm: a realistic body against a chibi one) measured far worse rigid, 2026-11-26.
#   belt  - a belt does not stretch along its length. Placed RIGID when a rigid placement matches the cloth fit
#           (RMS gap <= BELT_RMS); otherwise the body under it is too differently shaped (a waist against a
#           belly) and it is fitted as cloth. A strap across the body is not a belt (below).
#   strap - narrow straps lying ON the body (cross-belts, bandoliers, harness): the cloth fit, then put back on our
#           body's surface at the clearance it had on the asset (along the surface normal, not through the body),
#           so it runs over the bust instead of being pushed through it and torn.
#   cloth - everything else, as fit_rigged.py.
# RIGID = one similarity (rotation, translation, uniform scale) per bone the piece is weighted to on the asset,
# found from the cloth fit (so the scale follows our limb/torso size), blended with the asset's own weights; no
# per-vertex cloth deformation. Then each bone's part is scaled up about its centre in 1% steps (at most 12%) until
# no vertex is nearer the skin than MIN_CLEAR.
import re as _re
KIND_WORDS = [("strap", r"cross.?belt|bandol|baldric|harness|strap"),
              ("foot", r"boot|shoe|sandal|sabaton|clog"),
              ("plate", r"cuirass|breastplate|armou?r|pauldron|shoulder.?guard|epaulet|greave|bracer|vambrace|gorget|plate"),
              ("belt", r"belt|girdle|cingul")]
BELT_RMS = 0.006


def garment_kind(o):
    nm = o.name.split(".")[0].lower()
    for k, rx in KIND_WORDS:
        if _re.search(rx, nm):
            return k
    # shape: a foot garment reaches below the ankle and forward of it over the toes
    for side in ("Left", "Right"):
        if side + "Leg" in AXR_A:
            ank = AXR_A[side + "Leg"][1]
            co = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
            near = np.abs(co[:, 0] - ank[0]) < 0.08
            if (near & (co[:, 2] < ank[2] - 0.02) & (co[:, 1] < ank[1] - 0.06)).sum() > 20:
                return "foot"
    return "cloth"


KIND = {g.name: garment_kind(g) for g in garments}
LOG["garment_kinds"] = {k.split(".")[0]: v for k, v in KIND.items()}


def _sim_fit(X, Y, w):
    """Weighted similarity (Umeyama): Y ~ s R X + t."""
    w = w / max(w.sum(), 1e-12)
    mx = w @ X; my = w @ Y
    Xc = X - mx; Yc = Y - my
    C = (Yc * w[:, None]).T @ Xc
    U, S_, Vt = np.linalg.svd(C)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    var = float((w * (Xc ** 2).sum(1)).sum())
    sc = float(np.trace(np.diag(S_) @ D) / max(var, 1e-12))
    return sc, R, my - sc * R @ mx, my


def asset_signed_clear(ob):
    me = ob.data
    aco = np.empty(len(me.vertices) * 3); me.attributes["fit_asset_co"].data.foreach_get("vector", aco)
    out = np.empty(len(me.vertices))
    for i, q in enumerate(aco.reshape(-1, 3)):
        hit, nrm, fi, d = BVH_A.find_nearest(Vector(q))
        out[i] = (Vector(q) - hit).dot(nrm)
    return out


def _sd_body(A):
    sd = np.empty(len(A))
    for i, p in enumerate(A):
        hit, nrm, fi, d = BVH_B.find_nearest(Vector(p))
        sd[i] = (Vector(p) - hit).dot(nrm)
    return sd


def _rest_bone(armature, name):
    b = armature.data.bones.get(P + name) or armature.data.bones.get(name)
    return None if b is None else armature.matrix_world @ b.matrix_local


def _bone_len(armature, name):
    b = armature.data.bones.get(P + name) or armature.data.bones.get(name)
    return 0.0 if b is None else float((armature.matrix_world.to_3x3() @ (b.tail_local - b.head_local)).length)


BOOT_VG = "in_boot_verts"
FOOT_OK = 0.0015                 # covered: the boot at least this far from our foot (fitcheck's rest clearance)
FOOT_SPARE = 0.003               # boot to our foot: heel, toe, sides and top
FOOT_S = [None, None]                  # the current foot-part stretch, applied inside rigid_foot's place()


def _foot_verts(side):
    names = {g.index: short(g.name) for g in body.vertex_groups}
    want = {side + "Foot", side + "ToeBase", side + "Toe_End"}
    ix = [v.index for v in body.data.vertices
          if v.groups and names.get(max(v.groups, key=lambda x: x.weight).group) in want]
    return np.array(ix, dtype=int)


def boot_to_foot(side, m, X, Y0, ank_a, ob):
    """Find the stretch of the boot's foot part, in a level foot frame (forward, sideways, up), with separate scales
    for heel and toe, inner and outer side, and up from the sole, raised 1% at a time (at most 60%) until every
    vertex of our foot below the boot top is inside the boot with FOOT_SPARE to spare (a ray out along its normal
    meets the boot, at least FOOT_SPARE away, and no boot surface is nearer than that). Judged on our foot, not on
    the boot's vertices, so a boot lining does not count. Leaves the stretch in FOOT_S[0] for place(). Shaft untouched; the blend
    over 6 cm above the ankle joins the two."""
    fb = _rest_bone(arm, side + "Foot"); tb = _rest_bone(arm, side + "ToeBase")
    fwd = np.array((tb.translation - fb.translation)[:]) if tb is not None else np.array([0, -1.0, 0])
    fwd[2] = 0; fwd /= max(np.linalg.norm(fwd), 1e-9)
    up = np.array([0, 0, 1.0]); lat = np.cross(up, fwd)
    Rm = np.stack([fwd, lat, up])                                   # rows: frame axes
    low = X[m, 2] <= ank_a[2] + 0.03
    fv = _foot_verts(side)
    if not len(fv) or low.sum() < 10:
        return {"skipped": True}
    our_sole_z = float(BCO[fv][:, 2].min())
    ank_b_z = float(_rest_bone(arm, side + "Foot").translation.z)
    FP = BCO[fv] @ Rm.T
    BP = Y0[low] @ Rm.T
    anchor = np.array([(FP[:, 0].min() + FP[:, 0].max()) / 2, (FP[:, 1].min() + FP[:, 1].max()) / 2, BP[:, 2].min()])
    # centred on our foot; the scales below then set heel and toe (and the sides) to our foot + spare
    shift = np.array([anchor[0] - (BP[:, 0].min() + BP[:, 0].max()) / 2,
                      anchor[1] - (BP[:, 1].min() + BP[:, 1].max()) / 2, 0.0])
    sc = {"toe": 1.0, "heel": 1.0, "out": 1.0, "in": 1.0, "up": 1.0, "drop": 0.0}
    lat_sign = 1.0 if side == "Left" else -1.0

    def stretch(Yf):
        q = Yf @ Rm.T + shift - anchor
        q[:, 0] *= np.where(q[:, 0] > 0, sc["toe"], sc["heel"])
        q[:, 1] *= np.where(q[:, 1] * lat_sign > 0, sc["out"], sc["in"])
        q[:, 2] *= sc["up"]
        Yq = (q + anchor) @ Rm
        # sole height (2026-11-26): the asset's foot stood on the boot's insole, a platform sole above the boot's
        # bottom; our foot stands on the floor. The foot part goes down by sc["drop"] so the insole sits under our sole
        # (as on the asset, the platform then reaches below the floor)
        Yq[:, 2] -= sc["drop"]
        return Yq

    w = np.clip((X[m, 2] - ank_a[2]) / 0.06, 0.0, 1.0); w = w * w * (3 - 2 * w)
    idx = np.nonzero(m)[0]; loc = -np.ones(len(X), dtype=int); loc[idx] = np.arange(len(idx))
    ob.data.calc_loop_triangles()
    tris = [tuple(int(loc[i]) for i in lt.vertices) for lt in ob.data.loop_triangles if all(m[i] for i in lt.vertices)]
    top = float(Y0[:, 2].max()) - 0.025                               # the part of our foot the boot must hold
    fv = fv[BCO[fv][:, 2] < top]
    cv = fv                                                       # the shaft is fitted to the calf by rigid_foot
    NB = np.array([v.normal[:] for v in body.data.vertices])[cv]
    PB = BCO[cv]

    def uncovered(Yn):
        bv = BVHTree.FromPolygons([Vector(p) for p in Yn], tris)
        bad = np.zeros(len(cv), dtype=bool)
        for i, (p, n) in enumerate(zip(PB, NB)):
            p = Vector(p); n = Vector(n)
            h = bv.ray_cast(p + n * 1e-4, n, 0.3)
            if h[0] is None or h[3] < FOOT_OK or bv.find_nearest(p)[3] < FOOT_OK:
                bad[i] = True
                if len(DBG) < 40:
                    DBG.append([round(x, 3) for x in p] + [round(x, 2) for x in n] + [None if h[0] is None else round(h[3], 4), round(bv.find_nearest(p)[3], 4)])
        return bad
    it = 0
    DBG = []
    if os.environ.get("BOOT_NOSTRETCH"):
        return {"skipped": "BOOT_NOSTRETCH"}
    # heel, toe, inner and outer side: each scale from the extents, so the boot's end lies FOOT_SPARE + 4 mm (its
    # wall) past our foot's end in that direction
    Yn = Y0 + (1 - w)[:, None] * (stretch(Y0) - Y0)
    LOG.setdefault("boot_dbg", {})[side] = {"bad_at_start": int(uncovered(Yn).sum())}
    qb = Yn[low] @ Rm.T - anchor; qf = PB @ Rm.T - anchor
    gap = FOOT_SPARE + 0.004
    lat_b = qb[:, 1] * lat_sign; lat_f = qf[:, 1] * lat_sign
    for k_, bext, fext in (("toe", qb[:, 0].max(), qf[:, 0].max()), ("heel", -qb[:, 0].min(), -qf[:, 0].min()),
                           ("out", lat_b.max(), lat_f.max()), ("in", -lat_b.min(), -lat_f.min())):
        if bext > 1e-3:
            sc[k_] = float(np.clip((fext + gap) / bext, 0.7, 1.3))   # longer or shorter, to our foot
    # the drop: from each downward-facing vertex of our sole, the boot surface straight above it within 6 cm is the
    # insole our foot is sunk into; lower the boot until (90th percentile) it is FOOT_SPARE under our sole
    Yn = Y0 + (1 - w)[:, None] * (stretch(Y0) - Y0)
    bvd = BVHTree.FromPolygons([Vector(p) for p in Yn], tris)
    ups = []
    for p_, n_ in zip(PB, NB):
        if n_[2] < -0.5:
            h_ = bvd.ray_cast(Vector(p_) + Vector((0, 0, 1e-4)), Vector((0, 0, 1)), 0.06)
            if h_[0] is not None:
                ups.append(h_[3] + FOOT_SPARE)
    sc["drop"] = float(np.percentile(ups, 90)) if len(ups) >= 5 else 0.0
    it = 0
    Yn = Y0 + (1 - w)[:, None] * (stretch(Y0) - Y0)
    bad = uncovered(Yn)
    # where our foot still pokes out (a waisted sole round a block-shaped cartoon foot): push the boot out locally,
    # along the foot's normal, to FOOT_SPARE past it; a 1.2 cm Gaussian spreads the move so the boot stays smooth
    D = np.zeros_like(Yn)
    kdb = KDTree(len(Yn))
    for i_, p_ in enumerate(Yn):
        kdb.insert(p_, i_)
    kdb.balance()
    pushes = 0
    for rnd in range(10):
        Yc = Yn + D
        bad = uncovered(Yc)
        if not bad.any():
            break
        bv = BVHTree.FromPolygons([Vector(p) for p in Yc], tris)
        add = np.zeros_like(Yn)
        for i in np.nonzero(bad)[0]:
            p = Vector(PB[i]); n = Vector(NB[i])
            q, _, _, d = bv.find_nearest(p)
            h = bv.ray_cast(p + n * 1e-4, n, 0.3)
            if PB[i][2] > ank_b_z - 0.02:
                continue                                          # round the ankle the shaft fit decides
            need = (FOOT_SPARE - h[3]) if (h[0] is not None and h[3] < FOOT_OK) else (d + FOOT_SPARE)
            if h[0] is None or (Vector(q) - p).dot(n) < 0:
                need = d + FOOT_SPARE                              # the boot wall is behind the skin here
            need = min(need, 0.008)                               # at most 8 mm a round
            for co_, j, dd in kdb.find_range(q, 0.06):
                wgt = math.exp(-(dd * dd) / (2 * 0.02 ** 2)) * (1 - w[j])
                mv = np.array(n[:]) * need * wgt
                if np.linalg.norm(mv) > np.linalg.norm(add[j]):
                    add[j] = mv
            pushes += 1
        D += add
        nD = np.linalg.norm(D, axis=1)
        D *= np.minimum(1.0, 0.02 / np.maximum(nD, 1e-9))[:, None]   # at most 2 cm in all
        kdb = KDTree(len(Yn))
        for i_, p_ in enumerate(Yn + D):
            kdb.insert(p_, i_)
        kdb.balance()
    inner = 0
    FOOT_S[1] = D
    Yn = Yn + D
    bad = uncovered(Yn)
    FOOT_S[0] = stretch
    DBG.clear(); uncovered(Yn)
    LOG.setdefault("boot_dbg_end", {})[side] = {"bad": list(DBG), "bbox": [Yn.min(0).round(3).tolist(), Yn.max(0).round(3).tolist()]}
    BPn = Yn[low] @ Rm.T
    return {"scales": {k: round(v, 3) for k, v in sc.items()}, "iterations": it + 1,
            "boot_length_mm_before": round(float(BP[:, 0].max() - BP[:, 0].min()) * 1000, 1),
            "boot_length_mm_after": round(float(BPn[:, 0].max() - BPn[:, 0].min()) * 1000, 1),
            "our_foot_length_mm": round(float(FP[:, 0].max() - FP[:, 0].min()) * 1000, 1),
            "foot_verts_judged": int(len(cv)), "foot_verts_not_covered": int(bad.sum()),
            "local_push_mm_max": round(float(np.linalg.norm(D, axis=1).max()) * 1000, 1), "local_pushes": pushes, "drop_mm": round(sc["drop"] * 1000, 1)}


def hide_in_boots():
    """Mark and hide our foot below each boot's top edge (owner-approved 2026-11-26): vertex group and face attribute
    fitcheck.BOOT_ATTR, and a Mask modifier fitcheck.BOOT_MOD that leaves those faces out. Nothing is deleted."""
    boots = [o for o in done if o.name[2:].split(".")[0] in FOOT_KEYS]
    if not boots:
        return None
    names = {g.index: short(g.name) for g in body.vertex_groups}
    out = {}
    sel = np.zeros(len(body.data.vertices), dtype=bool)
    for side in ("Left", "Right"):
        ank = _rest_bone(arm, side + "Foot")
        if ank is None:
            continue
        ank = np.array(ank.translation)
        tops = []
        for b in boots:
            V = np.array([tuple(b.matrix_world @ v.co) for v in b.data.vertices])
            V = V[np.linalg.norm(V[:, :2] - ank[:2], axis=1) < 0.12]
            if len(V):
                tops.append(V[:, 2].max())
        if not tops:
            continue
        cut = max(tops) - 0.025
        want = {side + "Leg", side + "Foot", side + "ToeBase", side + "Toe_End"}
        n_ = 0
        for v in body.data.vertices:
            if v.groups and names.get(max(v.groups, key=lambda x: x.weight).group) in want and BCO[v.index][2] < cut:
                sel[v.index] = True; n_ += 1
        out[side] = {"cut_z_m": round(float(cut), 3), "boot_top_z_m": round(float(max(tops)), 3), "verts": n_}
    vg = body.vertex_groups.get(BOOT_VG) or body.vertex_groups.new(name=BOOT_VG)   # a group may not share the attribute's name
    vg.add([int(i) for i in np.nonzero(sel)[0]], 0.01, 'REPLACE')   # low weight: membership is what the Mask reads
    me = body.data
    fl = [bool(any(sel[i] for i in p.vertices)) for p in me.polygons]   # exactly the faces the Mask leaves out
    at = me.attributes.get(fitcheck.BOOT_ATTR)
    if at is not None:
        me.attributes.remove(at)
    at = me.attributes.new(fitcheck.BOOT_ATTR, "BOOLEAN", "FACE")
    at.data.foreach_set("value", fl)
    mk = body.modifiers.get(fitcheck.BOOT_MOD) or body.modifiers.new(fitcheck.BOOT_MOD, "MASK")
    mk.mode = 'VERTEX_GROUP'; mk.vertex_group = BOOT_VG; mk.invert_vertex_group = True; mk.threshold = 0.001
    mk.show_viewport = mk.show_render = True
    me.update()
    out["faces_hidden"] = int(sum(fl))
    LOG["hidden_in_boots"] = out
    return out


def rigid_foot(ob):
    """A boot or shoe: below the ankle it is carried by the foot (foot bone frame, uniform scale = our foot length
    over the asset's: Foot + ToeBase bones); above the ankle by the shin (shin bone frame anchored at the ankle,
    uniform scale from the cloth fit of the shaft, so it takes our calf's size). The two are blended over 6 cm
    above the ankle. Then each part is scaled up about the ankle in 1% steps (at most 12%) until it clears the
    skin by MIN_CLEAR. No per-vertex cloth deformation."""
    key = ob.name.split(".")[0]
    me = ob.data
    F = np.array([v.co[:] for v in me.vertices]); X = REST0[key]
    info = {"kind": "foot", "mode": "rigid (foot + shin)", "sides": {}}
    out = F.copy()
    SA = asset_signed_clear(ob)
    floor = np.clip(SA, MIN_CLEAR, CLEAR)
    judged = SA >= MIN_CLEAR                                       # it had room on the asset: it must have room here
    ankles = {sd_: _rest_bone(a_arm, sd_ + "Foot") for sd_ in ("Left", "Right")}
    if all(v_ is not None for v_ in ankles.values()):
        dl = np.linalg.norm(X - np.array(ankles["Left"].translation), axis=1)
        dr = np.linalg.norm(X - np.array(ankles["Right"].translation), axis=1)
        nearest_side = np.where(dl < dr, "Left", "Right")
    else:
        nearest_side = np.full(len(X), "Left")
    for side in ("Left", "Right"):
        fa, fb = _rest_bone(a_arm, side + "Foot"), _rest_bone(arm, side + "Foot")
        la, lb = _rest_bone(a_arm, side + "Leg"), _rest_bone(arm, side + "Leg")
        if fa is None or fb is None or la is None or lb is None:
            continue
        ank_a = np.array(fa.translation); ank_b = np.array(fb.translation)
        m = nearest_side == side                                    # this side's boot
        if not m.any():
            continue
        k_foot = (_bone_len(arm, side + "Foot") + _bone_len(arm, side + "ToeBase")) / max(
            _bone_len(a_arm, side + "Foot") + _bone_len(a_arm, side + "ToeBase"), 1e-9)
        shaft = m & (X[:, 2] > ank_a[2] + 0.06)
        k_leg = _sim_fit(X[shaft], F[shaft], np.ones(int(shaft.sum())))[0] if shaft.sum() > 10 else k_foot
        Ra = np.array(fa.to_3x3().normalized()); Rb = np.array(fb.to_3x3().normalized())
        Rla = np.array(la.to_3x3().normalized()); Rlb = np.array(lb.to_3x3().normalized())
        Rf = Rb @ Ra.T; Rl = Rlb @ Rla.T
        # the foot part stands on the floor: turn it about the vertical only (from the asset's foot direction to ours,
        # level), so a foot bone that slopes more or less than the asset's does not tip the boot into our foot; then
        # keep its sole at the asset's sole height (2026-11-26)
        def _lvl(R_, armature, sd_):
            fb_, tb_ = _rest_bone(armature, sd_ + "Foot"), _rest_bone(armature, sd_ + "ToeBase")
            v_ = np.array((tb_.translation - fb_.translation)[:]); v_[2] = 0
            return math.atan2(v_[1], v_[0])
        yaw = _lvl(None, arm, side) - _lvl(None, a_arm, side)
        Rf = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1.0]])
        lowa = X[m, 2] <= ank_a[2] + 0.03
        # level the sole: the asset's boot bottom slopes (toe lower than heel); fit a line to the lowest point of each
        # 1 cm slice along the foot and turn the foot part about the sideways axis through the ankle until it is flat
        fa_dir = np.array((_rest_bone(a_arm, side + "ToeBase").translation - fa.translation)[:]); fa_dir[2] = 0
        fa_dir /= max(np.linalg.norm(fa_dir), 1e-9)
        Xl = X[m][lowa]; sl = (Xl - ank_a) @ fa_dir
        bins = np.floor(sl / 0.01).astype(int); bx, bz = [], []
        for b_ in np.unique(bins):
            k_ = bins == b_
            if k_.sum() >= 3:
                bx.append(sl[k_].mean()); bz.append(Xl[k_, 2].min())
        slope = float(np.polyfit(bx, bz, 1)[0]) if len(bx) >= 4 else 0.0
        pitch = math.atan(slope)                                   # turn by -pitch about the sideways axis
        ax_ = np.cross(np.array([0, 0, 1.0]), fa_dir)
        K_ = np.array([[0, -ax_[2], ax_[1]], [ax_[2], 0, -ax_[0]], [-ax_[1], ax_[0], 0]])
        Rp = np.eye(3) + math.sin(pitch) * K_ + (1 - math.cos(pitch)) * K_ @ K_
        if np.dot(((Xl - ank_a) @ Rp.T) @ fa_dir, Xl[:, 2] * 0 + 1) is not None:
            tst = (Xl - ank_a) @ Rp.T
            if abs(np.polyfit(tst @ fa_dir, tst[:, 2], 1)[0]) > abs(slope) and len(bx) >= 4:
                Rp = Rp.T                                          # the other way round
        Rf = Rf @ Rp
        our_sole = float(BCO[_foot_verts(side)][:, 2].min()) if len(_foot_verts(side)) else 0.0
        info.setdefault("sole", {})[side] = {"asset_slope_deg": round(math.degrees(pitch), 1), "our_sole_z_mm": round(our_sole * 1000, 1)}

        def place(kf, kl):
            Yf = ank_b + kf * ((X[m] - ank_a) @ Rf.T)
            lowf = X[m, 2] <= ank_a[2] + 0.03
            Yf[:, 2] += (our_sole - FOOT_SPARE) - Yf[lowf, 2].min()       # sole just under our sole
            Yl = ank_b + kl * ((X[m] - ank_a) @ Rl.T)
            w = np.clip((X[m, 2] - ank_a[2]) / 0.06, 0.0, 1.0); w = w * w * (3 - 2 * w)
            Yb = (1 - w)[:, None] * Yf + w[:, None] * Yl
            if FOOT_S[0] is not None:                               # the foot-length stretch, faded out up the shaft
                Yb = Yb + (1 - w)[:, None] * (FOOT_S[0](Yb) - Yb)
                if FOOT_S[1] is not None:                           # and the local push-out round our foot
                    Yb = Yb + FOOT_S[1]
            return Yb
        ef = el = 1.0
        # --- length to our foot (owner-approved 2026-11-26): below the ankle the boot is stretched (heel and toe,
        # inner and outer side, and up from the sole, each on its own) until it clears our foot by FOOT_SPARE
        FOOT_S[0] = None; FOOT_S[1] = None
        fl = boot_to_foot(side, m, X, place(k_foot, k_leg), ank_a, ob)
        info.setdefault("foot_length_fit", {})[side] = fl
        Y = place(k_foot * ef, k_leg * el)
        for it in range(12):
            sd = _sd_body(Y); bad = (sd < floor[m]) & judged[m] & (X[m, 2] > ank_a[2] + 0.03)
            if not bad.any():
                break
            hi = X[m, 2] > ank_a[2] + 0.03
            # the foot part is not scaled up: the costume's body had its foot faces culled inside the boots, so the
            # asset gives no clearance to keep there (a boot sole is not judged against the foot it was built round)
            if (bad & hi).any():
                el *= 1.01
            Y = place(k_foot * ef, k_leg * el)
        # last: any boot vertex still inside or within FOOT_OK of our skin (an insole, the inside of the rim) goes
        # out to the skin + MIN_CLEAR along the skin normal; these lie inside the boot where nobody sees them
        sd = _sd_body(Y); moved = 0
        for j in np.nonzero(sd < FOOT_OK)[0]:
            h_, n_, _, _ = BVH_B.find_nearest(Vector(Y[j]))
            Y[j] = np.array((h_ + n_ * MIN_CLEAR)[:]); moved += 1
        info.setdefault("last_move_out", {})[side] = moved
        sd = _sd_body(Y)
        out[m] = Y
        FOOT_S[0] = None; FOOT_S[1] = None
        info["sides"][side] = {"verts_inside_on_asset": int((~judged[m]).sum()), "foot_scale": round(k_foot, 3), "shin_scale": round(float(k_leg), 3),
                               "extra": [round(ef, 3), round(el, 3)], "verts_too_close_after": int((sd < MIN_CLEAR).sum()),
                               "min_clearance_after_mm": round(float(sd.min()) * 1000, 2)}
    info["rms_vs_cloth_fit_mm"] = round(float(np.sqrt(((out - F) ** 2).sum(1).mean())) * 1000, 1)
    LOG.setdefault("rigid_fit", {})[key] = info
    me.vertices.foreach_set("co", out.astype(np.float32).ravel()); me.update()
    return True


def rigidify(ob, kind):
    """Replace the cloth fit of `ob` by rigid pieces (see the comment on KIND). Returns False when a belt should stay
    cloth."""
    key = ob.name.split(".")[0]
    me = ob.data
    F = np.array([v.co[:] for v in me.vertices])                 # the cloth fit (world = object space here)
    X = REST0[key]
    use, W0, share = ORIG_W[ob.name]
    W = W0 / np.maximum(W0.sum(1, keepdims=True), 1e-12)
    bones = [k for k in range(len(use)) if W[:, k].sum() > 1e-3 * len(W)]
    sims = {}
    for k in bones:
        sims[k] = list(_sim_fit(X, F, W[:, k]))
    def place(scales):
        out = np.zeros_like(F)
        for k in bones:
            sc, R, t, c = sims[k]
            Y = sc * (X @ R.T) + t
            Y = c + (Y - c) * scales[k]
            out += W[:, [k]] * Y
        tot = W[:, bones].sum(1, keepdims=True)
        return out / np.maximum(tot, 1e-12)
    scales = {k: 1.0 for k in bones}
    A = place(scales)
    rms = float(np.sqrt(((A - F) ** 2).sum(1).mean()))
    info = {"kind": kind, "rms_vs_cloth_fit_mm": round(rms * 1000, 1),
            "scale": {use[k]: round(sims[k][0], 3) for k in bones}}
    if kind in ("belt", "plate") and rms > BELT_RMS:
        info["mode"] = "cloth (rigid did not match the body: rms over %.0f mm)" % (BELT_RMS * 1000)
        LOG.setdefault("rigid_fit", {})[key] = info
        return False
    SA = asset_signed_clear(ob)
    floor = np.clip(SA, MIN_CLEAR, CLEAR); judged = SA >= MIN_CLEAR
    steps = 0
    for it in range(12):
        sd = _sd_body(A)
        bad = (sd < floor) & judged
        if not bad.any():
            break
        hit_b = [k for k in bones if W[bad, k].sum() > 1e-3]
        if not hit_b:
            break
        for k in hit_b:
            scales[k] *= 1.01
        A = place(scales); steps += 1
    sd = _sd_body(A)
    info.update({"mode": "rigid", "extra_scale": {use[k]: round(scales[k], 3) for k in bones},
                 "verts_too_close_after": int((sd < MIN_CLEAR).sum()), "min_clearance_after_mm": round(float(sd.min()) * 1000, 2)})
    LOG.setdefault("rigid_fit", {})[key] = info
    me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
    return True


def refine(o, maxlen=0.015):
    """Cut a strap's long faces (up to 9 cm along the strap) finer before fitting, shape unchanged (straight cuts,
    weights interpolated): a long face is a straight chord, and on a curved body it runs through the skin between
    its corners whatever is done to the corners."""
    import bmesh
    sc = float(np.mean(o.matrix_world.to_scale()))
    bm = bmesh.new(); bm.from_mesh(o.data)
    n0 = len(bm.verts)
    for _ in range(4):
        long_ = [e for e in bm.edges if e.calc_length() * sc > maxlen]
        if not long_:
            break
        bmesh.ops.subdivide_edges(bm, edges=long_, cuts=1, use_grid_fill=True)
    bm.to_mesh(o.data); o.data.update(); bm.free()
    LOG.setdefault("refined", {})[o.name.split(".")[0]] = [n0, len(o.data.vertices)]


def drop_hidden_pieces(ob, inner_faces=False):
    """Delete separate pieces lying wholly inside the asset's body. inner_faces (boots, 2026-11-26): also every
    vertex more than 2 mm inside the asset's body (the cap closing the shaft, an insole): faces nobody can see."""
    import bmesh
    SA = asset_signed_clear(ob)
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    seen = set(); kill = []
    if inner_faces:
        zz = np.array([tuple(ob.matrix_world @ v.co) for v in me.vertices])[:, 2]
        ank_z = min(_rest_bone(a_arm, s_ + "Foot").translation.z for s_ in ("Left", "Right"))
        ins = (SA < -0.002) & (np.array([tuple(v) for v in REST0[ob.name.split(".")[0]]])[:, 2] > ank_z + 0.03)   # up the shaft only: below, the asset's foot was cut away, so inside/outside means nothing
        LOG.setdefault("inner_faces_z", {})[ob.name.split(".")[0]] = np.histogram(zz[ins], bins=6)[0].tolist() + [round(float(zz[ins].min()), 3) if ins.any() else None, round(float(zz[ins].max()), 3) if ins.any() else None]
        kill = [bm.verts[i] for i in np.nonzero(ins)[0]]
        seen = {v.index for v in kill}
    for v in bm.verts:
        if v.index in seen:
            continue
        isl = []; st = [v]; seen.add(v.index)
        while st:
            x = st.pop(); isl.append(x)
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index); st.append(y)
        if all(SA[x.index] < 0 for x in isl):
            kill += isl
    n = len(kill)
    if n:
        # vertex attributes and weights are indexed: keep W/ORIG_W and REST0 in step with the mesh
        keep = np.ones(len(me.vertices), bool); keep[[x.index for x in kill]] = False
        bmesh.ops.delete(bm, geom=kill, context='VERTS')
        bm.to_mesh(me); me.update()
        key = ob.name.split(".")[0]
        REST0[key] = REST0[key][keep]
        use, W0, share = ORIG_W[ob.name]; ORIG_W[ob.name] = (use, W0[keep], share)
        if ob.name in ASSET_CLEAR:
            ASSET_CLEAR[ob.name] = ASSET_CLEAR[ob.name][keep]
    bm.free()
    LOG.setdefault("hidden_pieces_dropped", {})[ob.name.split(".")[0]] = n
    return n


def strap_to_surface(ob):
    """A strap lying on the body: from the cloth fit, put each vertex on our body's surface at the clearance it had
    on the asset (at least MIN_CLEAR), along the surface normal at the nearest point, then smooth the MOVES so the
    strap keeps its width and straight edges."""
    me = ob.data
    A = np.array([v.co[:] for v in me.vertices])
    CA0 = ASSET_CLEAR.get(ob.name)
    c = np.clip(CA0, MIN_CLEAR, 0.03) if CA0 is not None else np.full(len(A), CLEAR)
    T = A.copy()
    for i, p in enumerate(A):
        hit, nrm, fi, d = BVH_B.find_nearest(Vector(p))
        T[i] = np.array(hit) + np.array(nrm) * c[i]
    aco = np.empty(len(A) * 3); me.attributes["fit_asset_co"].data.foreach_get("vector", aco)
    rep_ = fitcheck.weld_map(aco.reshape(-1, 3))
    sets = [set() for _ in A]
    for ed in me.edges:
        i, j = rep_[ed.vertices[0]], rep_[ed.vertices[1]]
        if i != j:
            sets[i].add(j); sets[j].add(i)
    nb = [sorted(sets[rep_[i]]) for i in range(len(A))]
    D = T - A
    for _ in range(4):
        S_ = np.array([D[j].mean(0) if len(j) else D[i] for i, j in enumerate(nb)])
        D = (D + 0.5 * (S_ - D))[rep_]
    A = A + D
    # smoothing halves the move of a vertex whose neighbours did not move: one that was inside the body stays
    # inside. Those are put exactly on their surface target.
    for _ in range(3):
        sd = _sd_body(A); inside = sd < MIN_CLEAR
        if not inside.any():
            break
        A[inside] = T[inside]
        A = A[rep_]
    sd = _sd_body(A)
    LOG.setdefault("rigid_fit", {})[ob.name.split(".")[0]] = {"kind": "strap", "mode": "on the surface",
        "move_p95_mm": round(float(np.percentile(np.linalg.norm(D, axis=1), 95)) * 1000, 1),
        "min_clearance_after_mm": round(float(sd.min()) * 1000, 2)}
    me.vertices.foreach_set("co", A.astype(np.float32).ravel()); me.update()
# ------------------------------------------------------------------ cross-belts as generated ribbons (owner-approved 2026-11-26)
RIB_LIFT = 0.002                 # inner face of the ribbon above the carrier garment
RIB_THICK = 0.004                # ribbon thickness (the asset's Solidify was 4 mm)
RIB_STEP = 0.015                 # face length along the ribbon
RIB_UNDER = 0.010                # each strap end is cut at the first section wholly this far under the belt's top edge
RIB_TUCK = 0.015                 # the lower turn goes this far under the waist belt's top edge
RIBBONS = []                     # ribbons laid so far: (fitted verts, asset verts)


def _strap_centreline(key):
    """The strap's centreline and width on the asset, from the costume file's own (unmodified) cage: a closed ribbon
    with two boundary loops, one per edge. Returns (points of a closed loop, width, loop sizes) or None."""
    cpath = next((x.split("=", 1)[1] for x in a[4:] if x.startswith("costume=")), None)
    if not cpath:
        return None
    with bpy.data.libraries.load(cpath, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n == key][:1]
    ob = next((o for o in dst.objects if o is not None), None)
    if ob is None:
        return None
    me = ob.data
    M = np.array(ob.matrix_world)
    co = np.array([v.co[:] for v in me.vertices]) @ M[:3, :3].T + M[:3, 3]
    cnt = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            cnt[ek] = cnt.get(ek, 0) + 1
    nb = {}
    for (i, j), c in cnt.items():
        if c == 1:
            nb.setdefault(i, []).append(j); nb.setdefault(j, []).append(i)
    loops, seen = [], set()
    for s0 in nb:
        if s0 in seen:
            continue
        lp = [s0]; seen.add(s0); cur = s0
        while True:
            nx = [x for x in nb[cur] if x not in seen]
            if not nx:
                break
            cur = nx[0]; lp.append(cur); seen.add(cur)
        loops.append(lp)
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    loops = sorted(loops, key=len, reverse=True)[:2]
    if len(loops) < 2:
        return None

    def gap(lp):
        P_ = co[lp]
        return float(np.linalg.norm(np.diff(np.vstack([P_, P_[:1]]), axis=0), axis=1).max())
    # walk the cleaner edge (the other edge of the Soldier's cage has a stray 15 cm jump); pair each of its vertices
    # with the nearest vertex of the other edge
    loops = sorted(loops, key=gap)
    A = co[loops[0]]; B = co[loops[1]]
    kd = KDTree(len(B))
    for i, p in enumerate(B):
        kd.insert(p, i)
    kd.balance()
    Bm = np.array([B[kd.find(Vector(p))[1]] for p in A])
    C = (A + Bm) / 2
    w = float(np.median(np.linalg.norm(A - Bm, axis=1)))
    return C, w, len(loops[0]), len(loops[1])


def _resample_loop(C, step):
    P = np.vstack([C, C[:1]])
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    n = max(int(round(s[-1] / step)), 8)
    t = np.linspace(0, s[-1], n, endpoint=False)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1), float(s[-1])


def _tri_mesh(V, me):
    me.calc_loop_triangles()
    T = np.array([lt.vertices[:] for lt in me.loop_triangles])
    return T, BVHTree.FromPolygons([Vector(p) for p in V], [tuple(int(x) for x in t) for t in T])


def _bary(p, a_, b_, c_):
    v0, v1, v2 = b_ - a_, c_ - a_, p - a_
    d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-14:
        return np.array([1.0, 0.0, 0.0])
    v = (d11 * d20 - d01 * d21) / den; w = (d00 * d21 - d01 * d20) / den
    b = np.clip(np.array([1 - v - w, v, w]), 0, 1)
    return b / max(b.sum(), 1e-9)


def _ribbon_on(C, width, bvh, belt=None, info=None):  # noqa
    """Lay an even ribbon along the closed centreline C on the surface in bvh: 3 vertices across, inner layer
    RIB_LIFT above the surface, outer layer RIB_THICK above that. Returns verts (n*6, 3) and the centre points.
    belt: the waist belt's vertices; the lower turn of the loop is taken down until it lies RIB_TUCK under the
    belt's top edge there (tucked between carrier and belt). The width direction is parallel-transported from the
    top of the loop both ways round, so it never flips (no twist); the two transports meet at the bottom, under
    the belt."""
    P = np.array([bvh.find_nearest(Vector(p))[0][:] for p in C])
    for _ in range(3):                                            # even out, keep on the surface
        P = 0.5 * P + 0.25 * (np.roll(P, 1, 0) + np.roll(P, -1, 0))
        P = np.array([bvh.find_nearest(Vector(p))[0][:] for p in P])
    n = len(P)
    if belt is not None and len(belt):
        # the whole lower part of the loop (where it runs round the hip from front to back) goes under the waist
        # belt: every point lower than 8 cm above the belt's top edge near it is brought down, fading out up there,
        # until the part that was at or below 1 cm above the edge lies RIB_TUCK under it
        def btop(p_):
            nr_ = belt[np.linalg.norm(belt[:, :2] - p_[:2], axis=1) < 0.06]
            return float(nr_[:, 2].max()) if len(nr_) else float(belt[:, 2].max())

        def bbot(p_):
            nr_ = belt[np.linalg.norm(belt[:, :2] - p_[:2], axis=1) < 0.06]
            return float(nr_[:, 2].min()) if len(nr_) else float(belt[:, 2].min())
        z0 = P[:, 2].copy(); moved = 0.0
        for _ in range(5):
            tops = np.array([btop(p_) for p_ in P])
            tgt = tops - RIB_TUCK - 0.5 * width                 # the ribbon's upper edge, not just its middle
            w_ = np.clip(1.0 - (z0 - (tops + 0.01 + 0.5 * width)) / 0.07, 0.0, 1.0)
            dz = np.maximum(0.0, P[:, 2] - tgt) * w_
            P[:, 2] -= dz / 2
            P = np.array([bvh.find_nearest(Vector(p))[0][:] for p in P])
            P = 0.6 * P + 0.2 * (np.roll(P, 1, 0) + np.roll(P, -1, 0))
            P = np.array([bvh.find_nearest(Vector(p))[0][:] for p in P])
        tops = np.array([btop(p_) for p_ in P])
        low = z0 < tops + 0.01 + 0.5 * width
        if info is not None:
            info.update({"points_tucked": int(low.sum()),
                         "upper_edge_under_belt_top_mm_min": round(float((tops - P[:, 2] - 0.5 * width)[low].min()) * 1000, 1) if low.any() else None,
                         "lower_edge_above_belt_bottom_mm_min": round(float((P[:, 2] - 0.5 * width - np.array([bbot(p_) for p_ in P]))[low].min()) * 1000, 1) if low.any() else None,
                         "max_drop_mm": round(float((z0 - P[:, 2]).max()) * 1000, 1)})
    N = np.array([bvh.find_nearest(Vector(p))[1][:] for p in P])
    N = 0.5 * N + 0.25 * (np.roll(N, 1, 0) + np.roll(N, -1, 0)); N /= np.linalg.norm(N, axis=1)[:, None]
    T = np.roll(P, -1, 0) - np.roll(P, 1, 0); T /= np.maximum(np.linalg.norm(T, axis=1), 1e-9)[:, None]
    # parallel transport of the width direction from the highest point, both ways round
    S = np.zeros_like(P)
    top_i = int(np.argmax(P[:, 2]))
    s0 = np.cross(N[top_i], T[top_i]); S[top_i] = s0 / max(np.linalg.norm(s0), 1e-9)
    flips = 0
    lo_i = int(np.argmin(P[:, 2]))                                # the two transports meet here, under the belt
    fwd_len = (lo_i - top_i) % n
    for step in (1, -1):
        prev = S[top_i]
        for k_ in range(1, (fwd_len + 1) if step == 1 else (n - fwd_len)):
            i = (top_i + step * k_) % n
            s = prev - N[i] * (prev @ N[i]); s -= T[i] * (s @ T[i])   # into the tangent plane, across the line
            if np.linalg.norm(s) < 1e-6:
                s = np.cross(N[i], T[i]) * np.sign(np.cross(N[i], T[i]) @ prev or 1.0)
            s /= np.linalg.norm(s)
            if s @ prev < 0:
                s = -s; flips += 1
            S[i] = s; prev = s
    if info is not None:
        info["frame_flips_prevented"] = flips
        bot = lo_i
        info["seam_angle_deg"] = round(float(np.degrees(np.arccos(np.clip(abs(S[bot] @ S[(bot + 1) % n]), -1, 1)))), 1)
    V = np.zeros((len(C), 6, 3))
    for k, u in enumerate((-0.5, 0.0, 0.5)):
        Q = P + S * (u * width)
        H = []; Hn = []
        for q in Q:
            h, nr, _, _ = bvh.find_nearest(Vector(q)); H.append(h[:]); Hn.append(nr[:])
        H = np.array(H); Hn = np.array(Hn)
        Hn = np.where((Hn * N).sum(1)[:, None] < 0, -Hn, Hn)      # a thin shell: keep the outward side
        V[:, k] = H + Hn * RIB_LIFT
        V[:, 3 + k] = H + Hn * (RIB_LIFT + RIB_THICK)
    return V.reshape(-1, 3), P


def ribbon_strap(g):
    """Replace a cross-belt by a clean ribbon laid on the fitted carrier garment (the fitted garment it lay on in the
    asset). Centreline landmarks keep their place on the carrier (same triangle, same barycentrics). Bound by the
    carrier's weights; held on it in every pose by two Shrinkwrap modifiers (Outside Surface), one per layer."""
    key = g.name.split(".")[0]
    cl = _strap_centreline(key)
    if cl is None or not done:
        return False
    C0, width, la, lb = cl
    best = None
    for o in done:
        k_ = o.name[2:].split(".")[0]
        Ta, bva = _tri_mesh(REST0[k_], o.data)
        d = float(np.median([bva.find_nearest(Vector(p))[3] for p in C0]))
        if best is None or d < best[0]:
            best = (d, o, k_, Ta, bva)
    d0, car, ck, Ta, bva = best
    Vf = np.array([tuple(car.matrix_world @ v.co) for v in car.data.vertices])
    Tf, bvf = _tri_mesh(Vf, car.data)
    C, L_ = _resample_loop(C0, RIB_STEP)
    Cf = []
    for p in C:
        h, _, fi, _ = bva.find_nearest(Vector(p))
        t = Ta[fi]
        Cf.append(_bary(np.array(h[:]), *REST0[ck][t]) @ Vf[t])
    Cf = np.array(Cf)
    bo = next((o for o in done if KIND.get(o.name[2:].split(".")[0], KIND.get(o.name[2:])) == "belt"
               or o.name[2:].split(".")[0].lower().endswith("belt")), None)
    bA = REST0[bo.name[2:].split(".")[0]] if bo is not None else None
    bF = np.array([tuple(bo.matrix_world @ v.co) for v in bo.data.vertices]) if bo is not None else None
    ia, iff = {}, {}
    VA, _ = _ribbon_on(C, width, bva, bA, ia)                     # the same ribbon on the asset: the fit record
    VF, PF = _ribbon_on(Cf, width, bvf, bF, iff)
    n = len(C)
    # where it crosses a ribbon already laid, it goes over it: lifted by that ribbon's thickness + 1 mm, and the
    # Shrinkwrap lets go there (its weight fades to 0), so it rides on the other belt instead of through it
    lift_w = np.zeros(len(VF))
    for VF_o, VA_o in RIBBONS:
        for V_, Vo in ((VF, VF_o), (VA, VA_o)):
            kd_ = KDTree(len(Vo))
            for i_, p_ in enumerate(Vo):
                kd_.insert(p_, i_)
            kd_.balance()
            dist = np.array([kd_.find(Vector(p_))[2] for p_ in V_])
            f_ = np.clip(1.0 - (dist - 0.5 * width) / 0.03, 0.0, 1.0)
            f_ = f_.reshape(n, 6).max(1).repeat(6)                # whole cross-section together
            nr = (V_.reshape(n, 6, 3)[:, 3:] - V_.reshape(n, 6, 3)[:, :3]).mean(1)
            nr /= np.maximum(np.linalg.norm(nr, axis=1), 1e-9)[:, None]
            V_ += np.repeat(nr, 6, axis=0) * (f_ * (RIB_THICK + 0.001))[:, None]
            if V_ is VF:
                lift_w = np.maximum(lift_w, f_)
    RIBBONS.append((VF.copy(), VA.copy()))
    # the turn round the hip is cut away under the waist belt: the waist belt is narrower than the ribbon is wide,
    # so the turn cannot hide under it. Cross-sections that would show below the belt's bottom edge are dropped and
    # the ribbon becomes a strip with both ends inside the belt band (open ends, hidden by the belt)
    # per end (2026-11-26): walk down each side of the loop from its top (over the shoulder) and cut at the first
    # cross-section lying wholly RIB_UNDER under the waist belt's top edge there; everything past both cuts (the
    # turn round the hip) goes. If a side never gets that low, it is extended down the carrier until it does.
    cs = VF.reshape(n, 6, 3).copy(); ca = VA.reshape(n, 6, 3).copy(); lw = lift_w.reshape(n, 6).copy()

    def btop_at(p_, belt_):
        nr_ = belt_[np.linalg.norm(belt_[:, :2] - p_[:2], axis=1) < 0.06]
        return float(nr_[:, 2].max()) if len(nr_) else float(belt_[:, 2].max())

    def bbot_at(p_, belt_):
        nr_ = belt_[np.linalg.norm(belt_[:, :2] - p_[:2], axis=1) < 0.06]
        return float(nr_[:, 2].min()) if len(nr_) else float(belt_[:, 2].min())

    top_i = int(np.argmax(cs[:, 1, 2]))
    ends = {}
    # each end is cut along a level line z_c inside the waist-belt band: at least RIB_UNDER under the belt's top
    # edge and 3 mm above its bottom edge (the middle of what is left if the band is narrower than that). Every
    # lengthwise edge of the strip (6: inner and outer layer, 3 across) is followed down from the shoulder and ends
    # exactly where it crosses z_c, so a slanting strap gets a level end that lies wholly inside the band. The same
    # cut, by the same fractions along the same edges, is made on the asset copy (the fit record).
    extra = {1: ([], []), -1: ([], [])}
    ends = {}
    cutinfo = {}
    for step in (1, -1):
        order_ = [(top_i + step * k_) % n for k_ in range(n)]
        if bF is None:
            ends[step] = (order_[:n // 2], None); continue
        # where this side first reaches the band: its centre below the belt's top edge
        hit = next((j for j in range(1, n) if cs[order_[j], 1, 2] < btop_at(cs[order_[j], 1], bF)), None)
        if hit is None:
            ends[step] = (order_[:n // 2], None); cutinfo[step] = "never reaches the belt"; continue
        tp = btop_at(cs[order_[hit], 1], bF); bt = bbot_at(cs[order_[hit], 1], bF)
        # as deep in the band as it goes (3 mm above the belt's bottom edge): at the back the belt stands ~35 mm off
        # the tunic and an end only 10 mm under its top edge shows over it from a camera a little above (seen)
        zc = bt + 0.003 if bt + 0.003 <= tp - RIB_UNDER else 0.5 * ((tp - RIB_UNDER) + (bt + 0.003))
        kept = [j for j in range(n) if cs[order_[j], :, 2].min() >= zc]
        last = 0
        while last + 1 < n and cs[order_[last + 1], :, 2].min() >= zc:
            last += 1
        # the rows after the last whole one: the strip's own next rows, at most 4, so an edge cannot be followed
        # round the turn; if not every edge gets below z_c in them, the strip is instead carried on straight down the
        # carrier from the last whole row (15 mm steps) until it does
        nxtF = [cs[order_[j]] for j in range(last, min(last + 5, n))]
        nxtA = [ca[order_[j]] for j in range(last, min(last + 5, n))]
        if not all((np.array([r_[k, 2] for r_ in nxtF]) < zc).any() for k in range(6)):
            nxtF = [cs[order_[last]]]; nxtA = [ca[order_[last]]]
            lF = cs[order_[last]].copy(); lA = ca[order_[last]].copy()
            for _ in range(10):
                nf = []
                for v_ in lF:
                    h_, nr_, _, d_ = bvf.find_nearest(Vector(v_)); nr_ = np.array(nr_[:])
                    dn = np.array([0, 0, -1.0]) + nr_ * nr_[2]; dn /= max(np.linalg.norm(dn), 1e-9)
                    h2, n2, _, _ = bvf.find_nearest(Vector(v_ + dn * RIB_STEP))
                    nf.append(np.array(h2[:]) + np.array(n2[:]) * d_)
                nf = np.array(nf); lA = lA + (nf - lF); lF = nf
                nxtF.append(lF.copy()); nxtA.append(lA.copy())
                if (lF[:, 2] < zc).all():
                    break
            cutinfo.setdefault("extended", []).append(step)
        rowF = np.zeros((6, 3)); rowA = np.zeros((6, 3)); ok = True
        for k in range(6):
            pt = None
            for j in range(len(nxtF) - 1):
                a_, b_ = nxtF[j][k], nxtF[j + 1][k]
                if a_[2] >= zc > b_[2]:
                    tt = (a_[2] - zc) / (a_[2] - b_[2])
                    pt = (a_ + tt * (b_ - a_), nxtA[j][k] + tt * (nxtA[j + 1][k] - nxtA[j][k])); break
            if pt is None:
                ok = False; break
            rowF[k], rowA[k] = pt
        if ok and len(nxtF) > 2 and "extended" in cutinfo and step in cutinfo["extended"]:
            # keep the carried-on rows that are wholly above the cut, then the level end
            for r_F, r_A in zip(nxtF[1:], nxtA[1:]):
                if r_F[:, 2].min() >= zc:
                    extra[step][0].append(r_F); extra[step][1].append(r_A)
        if not ok:
            ends[step] = (order_[:last + 1], None); cutinfo[step] = "an edge never crosses the cut line"; continue
        ends[step] = (order_[:last + 1], True)
        extra[step][0].append(rowF); extra[step][1].append(rowA)
        cutinfo[step] = {"cut_z_m": round(float(zc), 3), "belt_top_z_m": round(tp, 3), "belt_bottom_z_m": round(bt, 3),
                         "under_top_mm": round((tp - zc) * 1000, 1), "above_bottom_mm": round((zc - bt) * 1000, 1)}
    seq_f, cut_f = ends[1]; seq_b, cut_b = ends[-1]
    order = [("o", i) for i in reversed(seq_b[1:])][::1]
    rows_F = [ext for ext in reversed(extra[-1][0])] + [cs[i] for i in reversed(seq_b[1:])] + [cs[top_i]] +              [cs[i] for i in seq_f[1:]] + list(extra[1][0])
    rows_A = [ext for ext in reversed(extra[-1][1])] + [ca[i] for i in reversed(seq_b[1:])] + [ca[top_i]] +              [ca[i] for i in seq_f[1:]] + list(extra[1][1])
    rows_W = [np.zeros(6)] * len(extra[-1][0]) + [lw[i] for i in reversed(seq_b[1:])] + [lw[top_i]] +              [lw[i] for i in seq_f[1:]] + [np.zeros(6)] * len(extra[1][0])
    dup = len(set(seq_f[1:]) & set(seq_b[1:]))
    LOG.setdefault("ribbon_cut", {})[key] = {
        "sections_before": int(n), "sections_after": len(rows_F), "overlap_sections": dup,
        "ends": {"side_a": cutinfo.get(1), "side_b": cutinfo.get(-1)},
        "end_under_belt_top_mm": [round((btop_at(r_[1], bF) - r_[:, 2].max()) * 1000, 1) for r_ in (rows_F[0], rows_F[-1])] if bF is not None else None,
        "end_above_belt_bottom_mm": [round((r_[:, 2].min() - bbot_at(r_[1], bF)) * 1000, 1) for r_ in (rows_F[0], rows_F[-1])] if bF is not None else None}
    VF = np.concatenate(rows_F); VA = np.concatenate(rows_A); lift_w = np.concatenate(rows_W)
    n0 = n; n = len(rows_F)
    faces = []
    for i in range(n - 1):                                          # one open strip: no wrap, no islands
        j = i + 1
        for k0, k1 in ((0, 1), (1, 2), (4, 3), (5, 4), (3, 0), (2, 5)):   # inner (faces the carrier), outer, edge walls
            faces.append((i * 6 + k0, i * 6 + k1, j * 6 + k1, j * 6 + k0))
    me = bpy.data.meshes.new("D_" + key)
    me.from_pydata([tuple(p) for p in VF], [], faces); me.update()
    for m_ in g.data.materials:
        me.materials.append(m_)
    uv = me.uv_layers.new(name="UVMap")
    rep = L_ / max(width, 1e-3) / 8.0                              # texture repeats along the length
    for p in me.polygons:
        for li in p.loop_indices:
            vi = me.loops[li].vertex_index; r, k = divmod(vi, 6)
            uv.data[li].uv = ((k % 3) / 2.0, r / n0 * rep)
    for p in me.polygons:
        p.use_smooth = True
    old = g.data
    g.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    g.name = "D_" + key
    g.parent = None
    g.matrix_world = Matrix.Identity(4)
    for nm, tp in (("fit_asset_co", "FLOAT_VECTOR"), ("fit_asset_clear", "FLOAT")):
        me.attributes.new(nm, tp, "POINT")
    me.attributes["fit_asset_co"].data.foreach_set("vector", VA.astype(np.float32).ravel())
    me.attributes["fit_asset_clear"].data.foreach_set("value", np.array([BVH_A.find_nearest(Vector(p))[3] for p in VA], np.float32))
    REST0[key] = VA
    for vg in list(g.vertex_groups):
        g.vertex_groups.remove(vg)
    cw = [{car.vertex_groups[x.group].name: x.weight for x in v.groups if x.weight > 0} for v in car.data.vertices]
    for i, p in enumerate(VF):
        h, _, fi, _ = bvf.find_nearest(Vector(p))
        t = Tf[fi]; b = _bary(np.array(h[:]), *Vf[t])
        acc = {}
        for bi, vi in zip(b, t):
            for nm, w in cw[int(vi)].items():
                acc[nm] = acc.get(nm, 0) + bi * w
        top = sorted(acc.items(), key=lambda x: -x[1])[:4]; tot = sum(w for _, w in top) or 1.0
        for nm, w in top:
            vg = g.vertex_groups.get(nm) or g.vertex_groups.new(name=nm)
            vg.add([i], w / tot, 'REPLACE')
    gi = g.vertex_groups.new(name="ribbon_inner"); go = g.vertex_groups.new(name="ribbon_outer")
    for r in range(n):
        for k in range(6):
            (gi if k < 3 else go).add([r * 6 + k], float(1.0 - lift_w[r * 6 + k]), 'REPLACE')
    for m_ in list(g.modifiers):
        g.modifiers.remove(m_)
    am = g.modifiers.new("Armature", "ARMATURE"); am.object = arm; am.use_deform_preserve_volume = True
    for nm, vg, off in (("WrapInner", "ribbon_inner", RIB_LIFT), ("WrapOuter", "ribbon_outer", RIB_LIFT + RIB_THICK)):
        sw = g.modifiers.new(nm, "SHRINKWRAP")
        sw.target = car; sw.wrap_method = 'NEAREST_SURFACEPOINT'; sw.wrap_mode = 'OUTSIDE_SURFACE'
        sw.offset = off; sw.vertex_group = vg
    seg = np.linalg.norm(np.roll(PF, -1, 0) - PF, axis=1)
    sd = _sd_body(VF)
    LOG.setdefault("rigid_fit", {})[key] = {"kind": "strap", "mode": "generated ribbon on " + car.name,
        "cage_loops": [la, lb], "width_mm": round(width * 1000, 1), "thick_mm": RIB_THICK * 1000,
        "segments": n, "seg_mm": [round(float(seg.min()) * 1000, 1), round(float(seg.max()) * 1000, 1)],
        "length_asset_m": round(L_, 3), "length_fitted_m": round(float(seg.sum()), 3),
        "carrier_asset_dist_mm": round(d0 * 1000, 1), "lower_turn_fitted": iff, "lower_turn_asset": ia,
        "belt_object": bo.name if bo is not None else None, "min_body_clearance_mm": round(float(sd.min()) * 1000, 2)}
    LOG["D_" + key] = {"moved_by": sorted({vg.name for vg in g.vertex_groups} - {"ribbon_inner", "ribbon_outer"})}
    return True


REST0 = {}                       # asset rest-pose position of every cloth vertex, before fitting (for carry_rigid)
for g in sorted(garments, key=lambda o: (KIND[o.name] == "strap", 0 if LOWER[o.name] else 1)):   # straps last: they lie on the fitted carrier and tuck under the fitted belt
    is_low = LOWER[g.name]
    # refine(g) for straps was tried (2026-11-26) and made the cross-belts worse (uneven stretch 9-10%), kept unused
    REST0[g.name.split(".")[0]] = np.array([tuple(g.matrix_world @ v.co) for v in g.data.vertices])
    if KIND[g.name] == "strap" and ribbon_strap(g):       # generated ribbon on the fitted carrier (owner-approved 2026-11-26)
        done.append(g)
        continue
    fit(g)
    _k = g.name.split(".")[0]
    _st = {"fit": np.array([tuple(g.matrix_world @ v.co) for v in g.data.vertices])}
    kind = KIND[g.name]
    if kind == "foot":
        drop_hidden_pieces(g, inner_faces=True)   # faces inside the asset's leg (shaft cap, insole): never seen
    if kind == "foot" and rigid_foot(g):
        pass
    elif kind in ("plate", "belt") and rigidify(g, kind):
        pass                                                    # rigid: no cloth settling
    else:
        if kind == "strap":
            drop_hidden_pieces(g)
            strap_to_surface(g)          # straps are not settled: the skin-relief lift (4.5 cm kernels) spread them into sheets
        else:
            settle(g, others=done_lower if not is_low else ())
    _st["settle"] = np.array([tuple(g.matrix_world @ v.co) for v in g.data.vertices])
    STAGES[_k] = {k_: {"dz_median_mm": round(float(np.median(v_[:, 2] - REST0[_k][:, 2])) * 1000, 1),
                       "move_p95_mm": round(float(np.percentile(np.linalg.norm(v_ - REST0[_k], axis=1), 95)) * 1000, 1)}
                  for k_, v_ in _st.items() if len(v_) == len(REST0[_k])}
    if KIND[g.name] != "strap":            # a strap's small pieces were put on the surface with it
        rigid_details(g)
    bind(g, "D_" + g.name.split(".")[0])
    done.append(g)
    if is_low:
        done_lower.append(g)



# ------------------------------------------------------------------ waist belt onto the tunic (owner-approved 2026-11-26)
# The rigid belt was placed against the body, so where the tunic is thin it stood off it (~38 mm at the back) and where
# the tunic is full it cut into it (kids). Here the belt is moved radially, per angle round its own centre, so its inner
# face sits BELT_GAP outside whatever lies under it (tunic, and the cross-belt ribbons where they pass under it). The
# radial move is a smooth function of the angle only (Fourier, order BELT_ORDER): the belt keeps its band shape and its
# thickness, no wobble; the buckle keeps its angle (front centre).
BELT_GAP = 0.002
BELT_ORDER = 6
BELT_BINS = 72
ARM_WORDS = ("Arm", "Hand", "Shoulder")
def belt_to_tunic():
    """Radial move dr(theta, t) = (1-t) dB(theta) + t dT(theta), t = 0 at the belt's bottom edge, 1 at its top: the
    belt may follow the cloth's slope (a cone) but stays a smooth band. dB, dT are Fourier series of order
    BELT_ORDER, fitted to the room needed in each 5 deg bin, top and bottom half of the band, then raised until no
    bin is short of BELT_GAP."""
    belts = [o for o in done if KIND.get(o.name[2:].split(".")[0]) == "belt"]
    out = {}
    def basis(t):
        cols = [np.ones_like(t)]
        for j in range(1, BELT_ORDER + 1):
            cols += [np.cos(j * t), np.sin(j * t)]
        return np.stack(cols, 1)
    nb = 2 * BELT_ORDER + 1
    for bo in belts:
        key = bo.name[2:].split(".")[0]
        B = np.array([tuple(bo.matrix_world @ v.co) for v in bo.data.vertices])
        zlo, zhi = B[:, 2].min(), B[:, 2].max(); H = max(zhi - zlo, 1e-6); zmid = 0.5 * (zlo + zhi)
        c = B[:, :2].mean(0)
        def polar(V):
            d = V[:, :2] - c
            a_ = np.arctan2(d[:, 1], d[:, 0])
            return a_, np.linalg.norm(d, axis=1), ((a_ + np.pi) / (2 * np.pi) * BELT_BINS).astype(int) % BELT_BINS
        under, names = [], []
        for o in done:
            if o is bo or KIND.get(o.name[2:].split(".")[0]) in ("belt", "foot", "plate"):
                continue
            V = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
            gn = {g.index: g.name for g in o.vertex_groups}
            armw = np.array([sum(x.weight for x in v.groups if any(w in gn[x.group] for w in ARM_WORDS)) for v in o.data.vertices])
            m = (V[:, 2] > zlo - 0.004) & (V[:, 2] < zhi + 0.004) & (armw < 0.3)
            if m.any():
                under.append(V[m]); names.append(o.name)
        if not under:
            continue
        U = np.concatenate(under)
        ab, rb, ib = polar(B); hb = B[:, 2] >= zmid
        au, ru, iu = polar(U); hu = U[:, 2] >= zmid
        rows, rhs, cells = [], [], []
        for k in range(BELT_BINS):
            for h in (0, 1):
                mb = (ib == k) & (hb == h); mu = (iu == k) & (hu == h)
                if not mb.any() or not mu.any():
                    continue
                j = int(np.argmax(ru[mu])); rp = ru[mu][j]; tp = float(np.clip((U[mu][j, 2] - zlo) / H, 0, 1))
                inner = rb[mb].min()
                th = (k + 0.5) / BELT_BINS * 2 * np.pi - np.pi
                bs = basis(np.array([th]))[0]
                rows.append(np.concatenate([(1 - tp) * bs, tp * bs])); rhs.append(rp + BELT_GAP - inner)
                cells.append((k, h, inner, rp, tp))
        Am = np.array(rows); bv = np.array(rhs)
        coef = np.linalg.lstsq(Am, bv, rcond=None)[0]
        shortf = bv - Am @ coef
        lift = max(0.0, float(shortf.max())); coef[0] += lift; coef[nb] += lift
        tb = np.clip((B[:, 2] - zlo) / H, 0, 1)
        Bs = basis(ab)
        dr = (1 - tb) * (Bs @ coef[:nb]) + tb * (Bs @ coef[nb:])
        f = (rb + dr) / np.maximum(rb, 1e-9)
        Bn = B.copy(); Bn[:, :2] = c + (B[:, :2] - c) * f[:, None]
        inv = bo.matrix_world.inverted()
        for v, p_ in zip(bo.data.vertices, Bn):
            v.co = inv @ Vector(p_)
        bo.data.update()
        # measured after the move: per bin and half, the belt's inner face against the outermost cloth there
        _, rn, ibn = polar(Bn)
        g_after, g_before = [], []
        for k, h, inner, rp, tp in cells:
            mb = (ibn == k) & (hb == h)
            g_after.append(rn[mb].min() - rp); g_before.append(inner - rp)
        g_after = np.array(g_after); g_before = np.array(g_before)
        if g_after.min() < BELT_GAP:              # interpolation between halves left a cell short: open the whole band evenly
            e_ = BELT_GAP - float(g_after.min()); fe = (rn + e_) / np.maximum(rn, 1e-9)
            Bn[:, :2] = c + (Bn[:, :2] - c) * fe[:, None]; dr = dr + e_; g_after = g_after + e_
            for v, p_ in zip(bo.data.vertices, Bn):
                v.co = inv @ Vector(p_)
            bo.data.update()
        back = np.array([abs(((k + 0.5) / BELT_BINS * 360 - 180) - 90) <= 30 for k, *_ in cells])
        out[key] = {"belt_to_cloth_gap_mm_min": round(float(g_after.min()) * 1000, 1),
                    "belt_to_cloth_gap_mm_max": round(float(g_after.max()) * 1000, 1),
                    "back_gap_mm": [round(float(g_after[back].min()) * 1000, 1), round(float(g_after[back].max()) * 1000, 1)] if back.any() else None,
                    "gap_before_mm": [round(float(g_before.min()) * 1000, 1), round(float(g_before.max()) * 1000, 1)],
                    "back_gap_before_mm": [round(float(g_before[back].min()) * 1000, 1), round(float(g_before[back].max()) * 1000, 1)] if back.any() else None,
                    "radial_move_mm": [round(float(dr.min()) * 1000, 1), round(float(dr.max()) * 1000, 1)],
                    "under": names, "cells_used": len(cells)}
    LOG["belt_to_tunic"] = out


belt_to_tunic()

FOOT_KEYS = {k.split(".")[0] for k, v in KIND.items() if v == "foot"}
hide_in_boots()


# ------------------------------------------------------------------ rigid parts of the costume (fit_costume.py)
COSTUME = next((x.split("=", 1)[1] for x in a[4:] if x.startswith("costume=")), None)
CNAME = os.path.splitext(os.path.basename(COSTUME))[0].split("_", 1)[1] if COSTUME else None   # King / Pirate / Soldier
PROPS = []


def _bone_world(armature, b):
    return armature.matrix_world @ armature.data.bones[P + b].matrix_local


def _reparent(ob, armature, bone=None):
    bpy.context.view_layer.update()
    mw = ob.matrix_world.copy()
    ob.parent = armature
    if bone:
        ob.parent_type = 'BONE'; ob.parent_bone = P + bone
    else:
        ob.parent_type = 'OBJECT'
    bpy.context.view_layer.update()
    ob.matrix_world = mw
    bpy.context.view_layer.update()


def carry_rigid():
    out = {}
    with bpy.data.libraries.load(COSTUME, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if not n.startswith("WGT-")]
    loaded = [o for o in dst.objects if o is not None]
    c_arm = next(o for o in loaded if o.type == 'ARMATURE' and o.name.startswith("Armature"))
    keep = set(c_arm.children_recursive)
    fitted = set(REST0)
    rcol = bpy.data.collections.new(CNAME + "_Rigid"); bpy.context.scene.collection.children.link(rcol)
    for o in loaded:
        if o in keep and o.name.split(".")[0] not in fitted and o.name.split(".")[0] != "Aj_Base_Body":
            rcol.objects.link(o)
    bpy.context.scene.collection.objects.link(c_arm)
    c_arm.data.pose_position = 'REST'; arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    # fitted cloth, rest pose: vertex i of the fitted garment is vertex i of the asset garment
    fit_co = {}
    for g in done:
        fit_co[g.name[2:].split(".")[0]] = np.array([tuple(g.matrix_world @ v.co) for v in g.data.vertices])
    A_all = np.concatenate([REST0[k] for k in fit_co]); F_all = np.concatenate([fit_co[k] for k in fit_co])
    kd = KDTree(len(A_all))
    for i, p in enumerate(A_all):
        kd.insert(p, i)
    kd.balance()
    T_head = _bone_world(arm, "Head") @ _bone_world(c_arm, "Head").inverted()
    roots = [o for o in c_arm.children if o.name.split(".")[0] not in fitted and o.name.split(".")[0] != "Aj_Base_Body"]
    for o in roots:
        mw = o.matrix_world.copy()
        am = next((m for m in o.modifiers if m.type == 'ARMATURE' and m.object is c_arm), None)
        if am is not None:                                     # skinned: only accepted when it is all on the head
            used = {short(o.vertex_groups[g.group].name) for v in o.data.vertices for g in v.groups if g.weight > 1e-4}
            if used != {"Head"}:
                out[o.name] = {"kind": "UNHANDLED skinned", "bones": sorted(used)}
                continue
            o.data.transform(T_head @ mw, shape_keys=True)   # shape keys too, or the Basis key keeps the old place
            o.parent = arm; o.parent_type = 'OBJECT'
            o.matrix_parent_inverse = arm.matrix_world.inverted(); o.matrix_basis = Matrix.Identity(4)
            am.object = arm
            out[o.name] = {"kind": "head (skinned to Head)"}
            continue
        bone = short(o.parent_bone) if o.parent_type == 'BONE' else None
        if bone == "Head":
            o.parent = None; o.matrix_world = T_head @ mw
            _reparent(o, arm, "Head")
            out[o.name] = {"kind": "head"}
        elif bone in ("RightHand", "LeftHand"):
            o.parent = None; o.matrix_world = mw
            _reparent(o, arm, bone)
            PROPS.append(o.name)
            out[o.name] = {"kind": "hand prop (grips.hold)"}
        else:
            # follow the fitted cloth under it: best rigid move of the cloth vertices nearest the item's near side
            dg = bpy.context.evaluated_depsgraph_get()
            pts = []
            for m in [o] + list(o.children_recursive):
                if m.type == 'MESH':
                    e = m.evaluated_get(dg); me_ = e.to_mesh()
                    pts += [tuple(m.matrix_world @ v.co) for v in me_.vertices]
                    e.to_mesh_clear()
            pts = np.array(pts) if pts else np.array([tuple(mw.translation)])
            dn = np.array([kd.find(p)[2] for p in pts])
            c = pts[dn <= dn.min() + 0.01].mean(0)
            idx = [h[1] for h in kd.find_n(c, 80)]
            P0 = A_all[idx]; P1 = F_all[idx]
            c0, c1 = P0.mean(0), P1.mean(0)
            Hm = (P0 - c0).T @ (P1 - c1)
            U, S_, Vt = np.linalg.svd(Hm)
            dd = np.sign(np.linalg.det(Vt.T @ U.T))
            Rm = Vt.T @ np.diag([1, 1, dd]) @ U.T
            M = Matrix.Identity(4)
            for i in range(3):
                for j in range(3):
                    M[i][j] = float(Rm[i, j])
            t = c1 - Rm @ c0
            M.translation = Vector(t)
            o.parent = None; o.matrix_world = M @ mw
            _reparent(o, arm, bone)
            out[o.name] = {"kind": f"on the body ({bone}), follows the cloth",
                           "moved_mm": round(float(np.linalg.norm((Rm @ c + t) - c)) * 1000, 1),
                           "turned_deg": round(math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(Rm) - 1) / 2)))), 2)}
    rigid_set = set(rcol.all_objects[:])
    for o in list(c_arm.children):
        if o in rigid_set:
            out.setdefault(o.name, {"kind": "UNHANDLED (left behind)"})
    for o in loaded:
        if o is not c_arm and o not in rigid_set and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.objects.remove(c_arm, do_unlink=True)
    bpy.context.view_layer.update()
    return out


if COSTUME:
    LOG["rigid"] = carry_rigid()
    print("RIGID", json.dumps(LOG["rigid"]))

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
fitcheck._boot_mod(body, True)                              # our foot hidden inside the boots, as it will be used


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

# ------------------------------------------------------------------ hand prop: presentation pose + grips.hold
if COSTUME and PROPS:
    import importlib, showcase, pose as _pose
    mod = importlib.import_module(CNAME.lower())
    place = {"King": "place_scepter", "Pirate": "place_cutlass", "Soldier": "place_musket"}[CNAME]
    showcase.presentation(CNAME, keep_right_grip=False)
    from ajkit import grips as _grips
    # the asset body's height (the costume was made for it) against ours: long props are scaled by it
    H_ASSET = float(ACO[:, 2].max())
    BODY_SCALE = LOG["height"] / H_ASSET
    LOG["prop_body_scale"] = round(BODY_SCALE, 3)

    def place_musket_scaled(length, at_shift=0.0):
        """soldier.place_musket with the musket's length scaled to the body (1.22 m on the teen asset)."""
        mu = bpy.data.objects["S_Musket"]
        _grips.release(mu)
        d0 = mu.matrix_world.to_3x3().col[0].normalized()
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for o in _grips._meshes(mu):
            e = o.evaluated_get(dg); me_ = e.to_mesh(); mw_ = o.matrix_world
            pts.extend(mw_ @ v.co for v in me_.vertices); e.to_mesh_clear()
        sv = np.array([p_.dot(d0) for p_ in pts]); s0, s1 = float(sv.min()), float(sv.max()); L_ = s1 - s0

        def span(mask):
            Pm = np.array([tuple(pts[i]) for i in np.where(mask)[0]])
            perp = Pm - np.outer(Pm @ np.array(d0), np.array(d0))
            return float(np.linalg.norm(perp.max(0) - perp.min(0)))
        if span(sv > s1 - 0.20 * L_) > span(sv < s0 + 0.20 * L_):
            d0 = -d0
        mu.scale *= (length / L_)
        bpy.context.view_layer.update()
        h = _grips.Hand("Right"); fr = h.frame()
        at_m = min(0.92, max(0.55, (fr["K"].z - 0.005) / length)) + at_shift
        ref0 = mu.matrix_world.to_3x3().col[1].normalized()
        roll = _grips.roll_to_align(d0, ref0, -fr["u"], -fr["f"])
        return _grips.hold(mu, "Right", "power", at=at_m, axis=d0, roll=roll)

    def place_cutlass_v(at=0.46, slant=12.0, gather=12.0):
        """pirate.place_cutlass with the grip point and slant as parameters (the defaults are pirate.py's)."""
        cut = bpy.data.objects["P_Cutlass"]
        _grips.release(cut)
        d0 = cut.matrix_world.to_3x3().col[1].normalized()
        sh = _grips.shaft(cut, at=0.5, axis=d0)
        cut.scale *= (0.90 / sh["length"])
        bpy.context.view_layer.update()
        h = _grips.Hand("Right"); fr = h.frame()
        d1 = Matrix.Rotation(math.radians(slant), 3, fr["n"]) @ (-fr["u"])
        ref0 = cut.matrix_world.to_3x3().col[0].normalized()
        roll = _grips.roll_to_align(d0, ref0, d1, fr["f"])
        return _grips.hold(cut, "Right", "power", at=at, axis=d0, roll=roll, slant=slant, part="hold", gather=gather)

    # the first try is the costume's own rule; if grips reports a fail, a few nearby grips are tried in a fixed order
    # and the first that passes is kept (the grip limit itself is not touched)
    if CNAME == "Soldier":
        tries = [lambda: place_musket_scaled(1.22 * BODY_SCALE)] + \
                [(lambda d: (lambda: place_musket_scaled(1.22 * BODY_SCALE, d)))(d) for d in (0.02, -0.02, 0.04, -0.04)]
    elif CNAME == "Pirate":
        tries = [lambda: place_cutlass_v()] + [(lambda a_, s_: (lambda: place_cutlass_v(a_, s_)))(a_, s_)
                                                for a_, s_ in ((0.44, 12.0), (0.48, 12.0), (0.46, 8.0), (0.46, 16.0), (0.42, 12.0), (0.50, 12.0))]
    else:
        tries = [lambda: getattr(mod, place)()]
    LOG["grip_tries"] = []
    grep_ = {"ok": False}
    for ti, fn in enumerate(tries):
        _grips.fist("Right", 0.9); _pose.update()
        try:
            grep_ = fn()
        except Exception as ex:                                   # reported, never hidden
            import traceback; traceback.print_exc()
            grep_ = {"ok": False, "fail_reasons": [f"{type(ex).__name__}: {ex}"]}
        LOG["grip_tries"].append({"try": ti, "ok": grep_.get("ok"), "penetration_mm": grep_.get("penetration_mm")})
        if grep_.get("ok"):
            break
    if CNAME == "Pirate" and "Stylized Parrot" in bpy.data.objects:
        coat = bpy.data.objects.get("D_P_Coat")
        if coat:
            coat.name = "P_Coat"
            try:
                mod.reperch()
            finally:
                coat.name = "D_P_Coat"
    _pose.update()
    LOG["grip"] = {k: grep_.get(k) for k in ("ok", "penetration_mm", "touching", "fail_reasons", "palm")}
    text += (f"\n## Hand prop ({place}, grips.hold)\n\n- ok: {grep_.get('ok')}, penetration {grep_.get('penetration_mm')} mm "
             f"(limit {grep_.get('max_penetration_mm')}), touching {grep_.get('touching')} {grep_.get('fail_reasons', '')}\n")
    PASS = bool(PASS and grep_.get("ok"))
    files = shots("presentation")
    for ang in (20, 160):                                         # head close-ups: hair and hat/crown on the head
        r = math.radians(ang); hz = float(_bone_world(arm, "Head").translation.z) + 0.15
        sc.camera.data.lens = 75
        sc.camera.location = (math.sin(r) * 2.2, -math.cos(r) * 2.2, hz + 0.05)
        stage.look_at(sc.camera, (0, 0, hz))
        sc.render.resolution_x, sc.render.resolution_y = 700, 700
        files.append(stage.render(os.path.join(OUTDIR, f"{KEY}_head_{ang}.png")))
    sheetutil.sheet(files, os.path.join(OUTDIR, f"{KEY}_presentation.png"), cols=3)
    LOG["fit_check"]["pass_with_grip"] = PASS
    json.dump(LOG, open(os.path.join(OUTDIR, f"{KEY}_fit_report.json"), "w"), indent=1, default=float)
    open(os.path.join(OUTDIR, f"{KEY}_fit_report.md"), "w", encoding="utf-8").write(text)

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