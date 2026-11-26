"""ajkit.hairkit - the Aj hair library on a head: build the mesh, colour it, mount it on the Head bone.

Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/scripts/garments.py (hybrid_hair, library_hair_mat, bone_parent,
_skull_map) and variants.head_matrix. Changed against the pack copy: the library path comes from ajkit.paths, the
armature and the body are arguments (the pack read them by name from the open file), the module keeps no global
state of its own beyond a small skull-map cache keyed by the body mesh, and a hair colour can be changed afterwards
(set_color) because the same hair material is used for hair and for facial hair.

    ob = build("male_spiky", coll, "Hair")            # the mesh, in rest-pose world metres round the base head
    mat = material("cid.hair", (0.2, 0.1, 0.05))      # dark roots, lighter tips (the hair_g attribute)
    mount(ob, arm)                                    # onto this body's head, bone-parented to mixamorig:Head
"""
from __future__ import annotations

import json

import bpy
import bmesh
from mathutils import Matrix, Vector

from . import paths

P = "mixamorig:"
SKULL_C = Vector((0.0, -0.0246, 1.6112))   # centre of a sphere fitted to Aj's cranium (rest pose)
SKULL_R = 0.198                            # one "head radius" of the library models
HEADNECK = {"Head", "Neck"}
EAR = dict(y=-0.019, z=1.584, ry=0.030, rz=0.064, x=0.165)
WARNINGS: list[str] = []
_SKULL: dict = {}


def index() -> dict:
    return json.loads((paths.HAIR / "index.json").read_text(encoding="utf-8"))


def styles(kind: str = "hair") -> list[str]:
    """Names of the hairstyles ('hair') or the beards and moustaches ('facial') in the library."""
    return list(index().get(kind, {}))


def file_of(style: str) -> str:
    return str(paths.HAIR / f"{style}.npz")


def hex_rgb(h) -> tuple[float, float, float]:
    """'#rrggbb' (sRGB) -> linear floats; a 3-sequence is taken as already linear."""
    if not isinstance(h, str):
        return tuple(float(x) for x in h[:3])
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


# ------------------------------------------------------------------------------------------------ the skull map
def _skull_map(body, NE=48, NA=96):
    """Distance from SKULL_C to the head surface in every direction (ears left out), smoothed, so a hat can press the
    hair onto the skull. Built from the body mesh as it stands (rest pose)."""
    key = body.data.name
    if key in _SKULL:
        return _SKULL[key]
    import numpy as np
    from mathutils.bvhtree import BVHTree
    mw = body.matrix_world
    names = {g.index: g.name.replace(P, "") for g in body.vertex_groups}
    me = body.data

    def dom(v):
        w = {names[g.group]: g.weight for g in v.groups if g.weight > 0}
        return max(w, key=w.get) if w else None
    verts = [mw @ v.co for v in me.vertices]
    doms = [dom(v) for v in me.vertices]

    def ear(p):
        return abs(p.x) > EAR["x"] - 0.01 and ((p.y - EAR["y"]) / (EAR["ry"] + 0.012)) ** 2 + ((p.z - EAR["z"]) / (EAR["rz"] + 0.012)) ** 2 < 1.0
    keep = [all(doms[k] in HEADNECK and not ear(verts[k]) for k in poly.vertices) for poly in me.polygons]
    polys = [tuple(poly.vertices) for poly, k in zip(me.polygons, keep) if k]
    bvh = BVHTree.FromPolygons(verts, polys)
    R = np.full((NE, NA), np.nan)
    import math
    for i in range(NE):
        el = math.radians(-90 + 180 * (i + 0.5) / NE)
        for j in range(NA):
            az = math.radians(-180 + 360 * (j + 0.5) / NA)
            d = Vector((math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)))
            hit = bvh.ray_cast(SKULL_C, d, 0.5)
            if hit[0] is not None and el > math.radians(-75):
                R[i, j] = (hit[0] - SKULL_C).length
    for _ in range(200):
        miss = np.isnan(R)
        if not miss.any():
            break
        Pd = np.pad(R, ((1, 1), (0, 0)), mode="edge")
        nb = np.stack([Pd[:-2], Pd[2:], np.roll(R, 1, 1), np.roll(R, -1, 1)])
        fill = np.nanmean(np.where(np.isnan(nb), np.nan, nb), axis=0)
        R[miss] = fill[miss]
    R = np.nan_to_num(R, nan=SKULL_R)
    for _ in range(3):
        Pd = np.pad(R, ((1, 1), (0, 0)), mode="edge")
        R = (2 * R + Pd[:-2] + Pd[2:] + np.roll(R, 1, 1) + np.roll(R, -1, 1)) / 6.0
    _SKULL[key] = R
    return R


# ------------------------------------------------------------------------------------------------ the mesh
def build(style: str, coll, name: str, decimate: float = 0.35, press=None, floor: float = 0.002, body=None):
    """A hair (or beard) from the library as a mesh object in rest-pose world metres. press=(z0, z1): hat hair; above z0 the
    hair's stand-off from the skull is squashed (fully by z1), never closer than `floor` to the skin (needs `body`)."""
    import numpy as np
    d = np.load(file_of(style))
    W = d["v"].astype(float)
    F = d["f"].astype(np.int64)
    g = d["g"].astype(float)
    if press:
        if body is None:
            raise ValueError("press needs the body mesh")
        z0, z1 = press
        C0 = np.array(SKULL_C)[None, :]
        Rv = W - C0
        r = np.linalg.norm(Rv, axis=1)
        D = Rv / r[:, None]
        el = np.degrees(np.arcsin(np.clip(D[:, 2], -1, 1)))
        az = np.degrees(np.arctan2(D[:, 0], -D[:, 1]))
        Rm = _skull_map(body)
        NE, NA = Rm.shape
        fe = np.clip((el + 90) / 180 * NE - 0.5, 0, NE - 1.001)
        fa = (az + 180) / 360 * NA - 0.5
        y0, x0 = np.floor(fe).astype(int), np.floor(fa).astype(int)
        ty, tx = fe - y0, fa - x0

        def s(yy, xx):
            return Rm[np.clip(yy, 0, NE - 1), xx % NA]
        rs = (s(y0, x0) * (1 - tx) + s(y0, x0 + 1) * tx) * (1 - ty) + (s(y0 + 1, x0) * (1 - tx) + s(y0 + 1, x0 + 1) * tx) * ty
        t = np.clip((W[:, 2] - z0) / (z1 - z0), 0.0, 1.0)
        k = t * t * (3 - 2 * t)
        stand = r - rs
        new = np.where(stand > floor, floor + (stand - floor) * (1 - k * 0.92), stand)
        W = C0 + D * (rs + new)[:, None]
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(W))
    me.vertices.foreach_set("co", W.astype(np.float32).ravel())
    me.loops.add(F.size)
    me.loops.foreach_set("vertex_index", F.ravel().astype(np.int32))
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", (np.arange(len(F)) * 3).astype(np.int32))
    me.update(calc_edges=True)
    me.validate()
    at = me.attributes.new("hair_g", "FLOAT", "POINT")
    at.data.foreach_set("value", g.astype(np.float32))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if decimate and decimate < 1.0:
        md = ob.modifiers.new("thin", "DECIMATE")
        md.ratio = decimate
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        new_me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        if len(new_me.polygons) == 0:
            bpy.data.meshes.remove(new_me)
            WARNINGS.append(f"{name}: decimate gave an empty mesh, kept the full one")
        else:
            old = ob.data
            ob.data = new_me
            bpy.data.meshes.remove(old)
            new_me.name = name
        ob.modifiers.clear()
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


# ------------------------------------------------------------------------------------------------ the colour
def material(name: str, color, root: float = 0.55, roughness: float = 0.62, specular: float = 0.3):
    """Flat sculpted-hair material: darker at the roots, lighter toward the tips. color: '#rrggbb' or linear rgb."""
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    b.inputs["Roughness"].default_value = roughness
    b.inputs["Specular IOR Level"].default_value = specular
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "hair_g"
    at.attribute_type = "GEOMETRY"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.name = "aj_hair_ramp"
    ramp.color_ramp.elements[1].position = 0.7
    nt.links.new(at.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    m["aj_hair_root"] = root
    set_color(m, color)
    return m


def set_color(mat, color):
    """Change the colour of a hair material made by material()."""
    c = hex_rgb(color)
    root = float(mat.get("aj_hair_root", 0.55))
    ramp = mat.node_tree.nodes["aj_hair_ramp"]
    ramp.color_ramp.elements[0].color = (c[0] * root, c[1] * root, c[2] * root, 1)
    ramp.color_ramp.elements[1].color = (*c, 1)
    return mat


# ------------------------------------------------------------------------------------------------ the mount
def head_matrix(arm) -> Matrix:
    """World 4x4 taking the base's rest-pose head space to this variant's head (rigid, no scale)."""
    v = arm.get("aj_head_matrix")
    if not v:
        return Matrix.Identity(4)
    v = list(v)
    return Matrix([v[0:4], v[4:8], v[8:12], v[12:16]])


def bone_parent(ob, arm, bone: str, keep_world: bool = True):
    """Parent ob to one bone of arm (short name: 'Head'), keeping where it stands."""
    bpy.context.view_layer.update()
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = P + bone
    bpy.context.view_layer.update()
    if keep_world:
        ob.matrix_world = mw


def mount(ob, arm):
    """Hair onto this body's head: move it with the body's head matrix, then bone-parent it to the Head."""
    ob.matrix_world = head_matrix(arm) @ ob.matrix_world
    bone_parent(ob, arm, "Head")
    return ob


# ------------------------------------------------------------------------------------------------ the neck
def skin_probe(body):
    """A throw-away copy of the body with only its Armature modifier (the hide-under-clothes mask renumbers the evaluated
    mesh, so weights could not be read by index). Same vertices as body.data; delete it with drop_probe()."""
    pr = body.copy()
    pr.data = body.data.copy()
    pr.name = body.name + ".probe"
    for c in body.users_collection:
        c.objects.link(pr)
    for m in list(pr.modifiers):
        if m.type != "ARMATURE":
            pr.modifiers.remove(m)
    pr.parent = body.parent
    pr.matrix_parent_inverse = body.matrix_parent_inverse.copy()
    pr.hide_render = True
    bpy.context.view_layer.update()
    return pr


def drop_probe(pr):
    me = pr.data
    bpy.data.objects.remove(pr, do_unlink=True)
    bpy.data.meshes.remove(me)


def deform_matrices(arm) -> dict:
    """World-space deformation of every bone in the armature's current pose: evaluated position = D[bone] @ rest position."""
    bpy.context.view_layer.update()
    inv = arm.matrix_world.inverted()
    return {pb.name: arm.matrix_world @ pb.matrix @ pb.bone.matrix_local.inverted() @ inv for pb in arm.pose.bones}


def attach(ob, arm, body, ears, ear_r: float = 0.075, margin: float = 0.004, head_reach: float = 0.07, below_z: float | None = None,
           pose_fn=None, T=None) -> dict:
    """Hair onto this body, in the pose the figure stands in (pose_fn(arm) puts the armature there: the Aj's hanging-arms
    reference pose; the rest pose is a T). Steps:
      1. the hair is moved onto this body's head (head matrix);
      2. in that pose, hair that dips into the skin of the neck or shoulders is lifted out to `margin` above it (not near the
         ears: the hair is cut round them and meets their root);
      3. it is skinned to the armature. Vertices near the head skin carry the Head bone alone (rigid, as the pack mounts hair);
         vertices near the skin of the neck and shoulders copy that skin's bone weights, so a low nape or a long lock moves with
         the neck instead of cutting into it when the head turns. Vertices further than `head_reach` from any skin: Head,
         except those lower than `below_z` (the chin): long locks and pigtails hang from the head but lie on the chest, so they
         take the weights of the skin they are nearest to, however far, and the Head's share fades out within 10 cm below the chin.
    The bind coordinates are worked out so that the hair APPEARS exactly where steps 1-2 put it in that pose. Returns counts.
    T: the 4x4 from the native frame (what the library, `ears` and `below_z` are in) to the world as the armature stands now (the
    actor's scale and place); lengths are scaled by its scale. The pose is the one the armature is in when this is called."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.kdtree import KDTree
    me = ob.data
    ob.parent = None                                      # the mesh is in the library's frame: no parent, no transform, until the end
    me.transform(head_matrix(arm) @ ob.matrix_basis)
    ob.matrix_basis = Matrix.Identity(4)
    T = T if T is not None else Matrix.Identity(4)
    k = T.to_scale()[0]
    ears = [T @ e for e in ears]
    ear_r, margin, head_reach = ear_r * k, margin * k, head_reach * k
    nat_z = [v.co.z for v in me.vertices]                 # native heights, for the chin test
    me.transform(T)
    if pose_fn:
        pose_fn(arm)
    D = deform_matrices(arm)
    names = {g.index: g.name for g in body.vertex_groups}
    probe = skin_probe(body)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = probe.evaluated_get(dg)
    em = ev.to_mesh()
    mw = probe.matrix_world
    pts = [mw @ v.co for v in em.vertices]
    polys = [tuple(p.vertices) for p in em.polygons]
    ev.to_mesh_clear()
    wts, hw = [], []
    for v in probe.data.vertices:
        w = {names[g.group]: g.weight for g in v.groups if g.weight > 0}
        wts.append(w)
        tot = sum(w.values())
        hw.append((w.get(P + "Head", 0.0) + w.get(P + "HeadTop_End", 0.0)) / tot if tot > 0 else 1.0)
    drop_probe(probe)
    near_ear = {i for i, q in enumerate(pts) if any((q - e).length < ear_r for e in ears)}
    skip = {k for k, pl in enumerate(polys) if any(v in near_ear for v in pl)}
    bvh = BVHTree.FromPolygons(pts, polys)
    kd = KDTree(len(pts))
    for i, q in enumerate(pts):
        kd.insert(q, i)
    kd.balance()
    head_name = P + "Head"
    per = {}
    for v in me.vertices:                                  # 3. the weights
        p0 = Vector(v.co)
        zn = nat_z[v.index]
        loc, nor, fi, dist = bvh.find_nearest(p0, max(head_reach, 0.05 * k))
        low = below_z is not None and zn < below_z
        neck_skin = loc is not None and fi not in skip and sum(hw[q] for q in polys[fi]) / len(polys[fi]) <= 0.5
        if neck_skin or (loc is None and low):
            w = {}                                          # the skin's weights round here, nearer ones counting more
            for _co, i, dd in kd.find_n(p0, 6):
                for bn, x in wts[i].items():
                    w[bn] = w.get(bn, 0.0) + x / (dd + 0.01 * k)
            tot0 = sum(w.values())
            w = {bn: x / tot0 for bn, x in w.items()} if tot0 > 0 else {head_name: 1.0}
            if below_z is not None and head_name in w:
                f = max(0.0, min(1.0, (zn - (below_z - 0.10)) / 0.10))
                w[head_name] *= f * f * (3 - 2 * f)
            tot = sum(w.values())
            if tot < 1e-6:
                w, tot = {P + "Neck": 1.0}, 1.0
            per[v.index] = {kk: x / tot for kk, x in w.items() if x > 1e-4}
        else:
            per[v.index] = {head_name: 1.0}
    minv, fallback = [], 0
    for v in me.vertices:                                  # bind coordinates: the hair appears where it was put, in this pose
        p0 = Vector(v.co)
        M0 = Matrix.Identity(4) * 0.0
        for bn, x in per[v.index].items():
            M0 += D[bn] * x
        M = M0.inverted_safe()
        if (M0 @ (M @ p0) - p0).length > 1e-4 * max(1.0, k):          # weights that pull in opposite directions: not invertible
            per[v.index] = {head_name: 1.0}
            M = D[head_name].inverted_safe()
            fallback += 1
        minv.append(M)
        v.co = M @ p0
    me.update()
    groups = {}
    for vi, w in per.items():
        for kk, x in w.items():
            g = groups.get(kk) or groups.setdefault(kk, ob.vertex_groups.new(name=kk))
            g.add([vi], x, "REPLACE")
    ob.parent = arm
    ob.matrix_parent_inverse = arm.matrix_world.inverted()
    md = ob.modifiers.new("Armature", "ARMATURE")
    md.object = arm
    # 2. lift what sits in the skin of the neck and shoulders, judged on the hair AS EVALUATED in this pose (a few passes)
    moved, deepest = set(), 0.0
    for _pass in range(3):
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        eh = ob.evaluated_get(dg)
        hm = eh.to_mesh()
        cur = [eh.matrix_world @ q.co for q in hm.vertices]
        eh.to_mesh_clear()
        n = 0
        for v in me.vertices:
            q = cur[v.index]
            loc, nor, fi, dist = bvh.find_nearest(q, 0.05 * k)
            if loc is None or fi in skip or sum(hw[r] for r in polys[fi]) / len(polys[fi]) > 0.5:
                continue
            sd = (q - loc).dot(nor)
            if sd < margin - 1e-4:
                deepest = max(deepest, margin - sd)
                v.co = minv[v.index] @ (loc + nor * margin)
                moved.add(v.index)
                n += 1
        me.update()
        if not n:
            break
    nskin = sum(1 for w in per.values() if set(w) != {head_name})
    return {"moved": len(moved), "deepest_mm": round(deepest * 1000, 2), "skinned": nskin, "rigid": len(per) - nskin, "fallback_rigid": fallback}
