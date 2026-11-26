"""measure_bodies.py - measure the eight Aj bodies once and write the numbers the pipeline actor needs.

    blender -b --factory-startup --python tools/chars_aj/measure_bodies.py -- [--bodies Male_Teen,Female_Kid] [--out <dir>]

For each body in packs/aj_rebuild_v1/02_Age_Body_Variants (and its dressed twin in 03_Dressed_Variants, when there is one)
the armature and meshes are APPENDED into an empty scene (the pack file is never opened for writing, nothing is saved),
put in the hanging-arms reference pose of stagekit.aj_rig, and measured in the figure's model space (native metres,
front -Y, the figure's left +X, Z up):

  b          the body numbers fig3d actors use: height, head_z, R, neck_z, hip_z, sh_z, sh_x, arm1, arm2, hand_r, leg_z,
             hip_x, knee_z, ankle_z, r_kn, r_hip, foot {len, w}, torso [[half width, z] ...]
  legs       thigh and shin lengths in the side plane and their rest angles (seniors stand with bent knees)
  joints     every control pivot (the bone heads in the reference pose) and each bone's offset rotation (w, x, y, z)
  palm       per side: the palm point and palm normal, relative to the wrist pivot; the palm's thickness
  landmarks  points ON the skin (and on the clothes for the dressed twin) with their outward normal: chin, mouth, brow,
             forehead, ear, cheek, top, nape, chest, belly, heart, hip, pocket, belt, cross; side-dependent ones for the
             figure's left (mirror x for the right). Each says which joint it moves with (head or torso).

Writes library/characters/aj/bodies/<Sex>_<Age>.json.
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_HERE = Path(__file__).resolve()
PIPE = _HERE.parents[2]
sys.path.insert(0, str(PIPE / "tools" / "blender"))
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
from stagekit import aj_rig  # noqa: E402
from ajkit import paths  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--bodies", default="")
ap.add_argument("--out", default=str(paths.MEASURED))
a = ap.parse_args(argv)
ALL = [f"{s}_{g}" for s in ("Male", "Female") for g in ("Kid", "Teen", "Adult", "Senior")]
names = [n for n in a.bodies.split(",") if n] or ALL
out_dir = Path(a.out)
out_dir.mkdir(parents=True, exist_ok=True)
P = aj_rig.P
ARMISH = ("Arm", "ForeArm", "Hand", "Sleeve", "Thumb", "Index", "Middle", "Ring", "Pinky")


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images, bpy.data.actions, bpy.data.collections):
        for x in list(coll):
            if x.users == 0:
                coll.remove(x)


def append(path, want):
    """Append the named objects (and what they use) from a pack file. Returns {name: object}."""
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n in want or any(n.startswith(w[:-1]) for w in want if w.endswith("*"))]
    got = {}
    for ob in dst.objects:
        if ob is None:
            continue
        bpy.context.scene.collection.objects.link(ob)
        got[ob.name] = ob
    return got


def is_arm_group(name):
    if not name.startswith(P):
        return False
    n = name[len(P):]
    n = n.replace("Left", "").replace("Right", "")
    return n.startswith(ARMISH) and not n.startswith("Shoulder")


def eval_tris(obs, skip_arms=True):
    """World triangles of the evaluated meshes (posed), without the faces that belong to the arms and hands."""
    dg = bpy.context.evaluated_depsgraph_get()
    verts, tris = [], []
    for ob in obs:
        oe = ob.evaluated_get(dg)
        me = oe.to_mesh()
        M = oe.matrix_world
        armv = set()
        if skip_arms:
            gi = {g.index: g.name for g in ob.vertex_groups}
            for v in ob.data.vertices:
                best, bw = None, 0.0
                for g in v.groups:
                    if g.weight > bw:
                        best, bw = gi.get(g.group), g.weight
                if best and is_arm_group(best):
                    armv.add(v.index)
        base = len(verts)
        same = len(me.vertices) == len(ob.data.vertices)
        verts += [M @ v.co for v in me.vertices]
        me.calc_loop_triangles()
        for lt in me.loop_triangles:
            vs = lt.vertices
            if skip_arms and same and any(i in armv for i in vs):
                continue
            tris.append((base + vs[0], base + vs[1], base + vs[2]))
        oe.to_mesh_clear()
    return verts, tris


def ray(bvh, origin, direction):
    hit = bvh.ray_cast(Vector(origin), Vector(direction).normalized())
    if hit[0] is None:
        return None
    return hit[0], hit[1]


# Face heights relative to the eyes, in head radii, read off a front render of Male_Teen with markers (all eight bodies
# share the same head, R = 0.202). The UV rectangle of the mouth atlas was tried first: its centre sits 8 cm above the
# drawn mouth, because the atlas window is larger than the lips.
FACE_FROM_EYES = {"mouth": -0.565, "brow": 0.29, "forehead": 0.55, "cheek": -0.30}


def eye_height(body, dg):
    """Mean height of the eyeballs (the faces with the eye material)."""
    oe = body.evaluated_get(dg)
    me = oe.to_mesh()
    idx = [i for i, s in enumerate(body.material_slots) if s.material and s.material.name.startswith("Aj_Eye_MAT")]
    zs = [(oe.matrix_world @ me.vertices[v].co).z for p in me.polygons if p.material_index in idx for v in p.vertices]
    oe.to_mesh_clear()
    return sum(zs) / len(zs) if zs else None


def measure(name):
    sex, age = name.split("_")
    clear()
    t0 = time.time()
    bare = append(paths.BODIES / f"Aj_{sex}_{age}.blend", {"Armature", "Aj_Base_Body"})
    arm, body = bare["Armature"], bare["Aj_Base_Body"]
    arm.location = (0, 0, 0)
    ref = aj_rig.reference_pose(arm)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    W = {jn: ref[bn][0] for jn, (bn, _p, _g) in aj_rig.JOINTS.items()}
    hd = ref["HeadTop_End"][0]

    # all body vertices, posed
    oe = body.evaluated_get(dg)
    me = oe.to_mesh()
    V = [oe.matrix_world @ v.co for v in me.vertices]
    oe.to_mesh_clear()
    gi = {g.index: g.name for g in body.vertex_groups}

    def dom(v):
        best, bw = None, 0.0
        for g in v.groups:
            if g.weight > bw:
                best, bw = gi.get(g.group), g.weight
        return (best or "")[len(P):]

    owner = [dom(v) for v in body.data.vertices]
    height = max(v.z for v in V)
    ground = min(v.z for v in V)
    head = [V[i] for i, o in enumerate(owner) if o == "Head"]
    hx = [p.x for p in head]
    hy = [p.y for p in head]
    hz = [p.z for p in head]
    R = 0.5 * (max(hx) - min(hx))
    head_top = max(hz)
    head_c = Vector((0.0, 0.5 * (max(hy) + min(hy)), head_top - R))
    eye_z = eye_height(body, dg)
    # hands: the palm frame from the Hand bone (its local +Z is the palm normal, the grips solver's convention)
    palm = {}
    for s, side in (("L", "Left"), ("R", "Right")):
        wr = ref[f"{side}Hand"][0]
        m1 = ref[f"{side}HandMiddle1"][0]
        Rh = ref[f"{side}Hand"][1]
        n = (Rh @ Vector((0, 0, 1))).normalized()
        hv = [V[i] for i, o in enumerate(owner) if o.startswith(side) and (o.endswith("Hand") or "Hand" in o and "1" in o)]
        mid = wr.lerp(m1, 0.55)
        near = [p for p in hv if ((p - mid) - n * (p - mid).dot(n)).length < 0.022]      # a thin core through the palm
        if not near:
            near = hv
        along = [(p - mid).dot(n) for p in near]
        thick = max(along) - min(along) if along else 0.03
        surf = mid + n * max(along)                       # the palm's own skin, on the normal side
        palm[s] = {"point": list(surf - wr), "normal": list(n), "thickness": thick, "centre": list(mid - wr),
                   "middle_base": list(m1 - wr)}
    hand_r = (Vector(palm["L"]["centre"])).length
    # legs in the side plane
    legs = {}
    for s in "LR":
        hp, kn, an = W[f"hip.{s}"], W[f"kn.{s}"], W[f"an.{s}"]
        th = kn - hp
        sh = an - kn
        legs[s] = {"L1": math.hypot(th.y, th.z), "L2": math.hypot(sh.y, sh.z),
                   "a1": math.atan2(-th.y, -th.z), "a2": math.atan2(-sh.y, -sh.z),
                   "ankle_fwd": -(an.y - hp.y)}
    # foot
    fv = [V[i] for i, o in enumerate(owner) if o in ("LeftFoot", "LeftToeBase", "LeftToe_End")]
    foot = {"len": max(p.y for p in fv) - min(p.y for p in fv), "w": max(p.x for p in fv) - min(p.x for p in fv),
            "heel_y": max(p.y for p in fv), "toe_y": min(p.y for p in fv)} if fv else {"len": 0.2, "w": 0.08}
    # knee and hip radii (half the leg's depth there)
    def depth_at(z, sx=1.0, band=0.02):
        pts = [p for i, p in enumerate(V) if abs(p.z - z) < band and p.x * sx > 0 and "Leg" in owner[i]]
        return 0.5 * (max(p.y for p in pts) - min(p.y for p in pts)) if pts else 0.05
    r_kn = depth_at(W["kn.L"].z)
    # sitting on the floor: the hip joint rests at about the thigh's half depth above the ground
    r_hip = max(depth_at(W["hip.L"].z - 0.04), 0.05)
    # torso profile (no arms)
    tv = [p for i, p in enumerate(V) if owner[i] in ("Hips", "Spine", "Spine1", "Spine2", "Neck", "LeftShoulder", "RightShoulder")]
    prof = []
    z = W["hips"].z - 0.10
    while z <= W["neck"].z + 1e-6:
        sl = [p for p in tv if abs(p.z - z) < 0.015]
        if sl:
            prof.append([round(max(abs(p.x) for p in sl), 4), round(z, 4), round(0.5 * (max(p.y for p in sl) - min(p.y for p in sl)), 4)])
        z += 0.03
    b = {
        "height": height - ground, "ground": ground, "head_z": head_c.z, "head_y": head_c.y, "R": R, "head_top": head_top,
        "neck_z": W["neck"].z, "hip_z": W["hips"].z, "sh_z": W["sh.L"].z, "sh_x": W["sh.L"].x, "cl_x": W["cl.L"].x,
        "arm1": (W["el.L"] - W["sh.L"]).length, "arm2": (W["wr.L"] - W["el.L"]).length, "hand_r": hand_r,
        "leg_z": W["hip.L"].z, "hip_x": W["hip.L"].x, "knee_z": W["kn.L"].z, "ankle_z": W["an.L"].z,
        "r_kn": r_kn, "r_hip": r_hip, "foot": foot, "torso": [[p[0], p[1]] for p in prof], "torso_depth": [[p[2], p[1]] for p in prof],
    }
    joints = {jn: {"at": list(W[jn]), "bone": bn, "offset": list(ref[bn][1].to_quaternion())} for jn, (bn, _p, _g) in aj_rig.JOINTS.items()}
    res = {"body": name, "file": str(Path("02_Age_Body_Variants") / f"Aj_{sex}_{age}.blend"), "units": "native metres, model space",
           "b": b, "legs": legs, "joints": joints, "palm": palm, "head_top_end": list(hd)}

    def landmarks(obs, label):
        verts, tris = eval_tris(obs)
        bvh = BVHTree.FromPolygons(verts, tris)
        Rr, hz_, hy_ = R, head_c.z, head_c.y
        up = W["neck"].z - W["hips"].z
        hip_z = W["hips"].z
        out = {}

        def put(key, joint, hit, fallback=None):
            if hit is None:
                if fallback is None:
                    return
                hit = (Vector(fallback), Vector((0, -1, 0)))
            out[key] = {"at": [round(c, 5) for c in hit[0]], "n": [round(c, 4) for c in hit[1]], "joint": joint}

        F = -1.0                                           # rays come from the front (-Y) toward +Y
        ez = eye_z if eye_z is not None else hz_
        mz = ez + FACE_FROM_EYES["mouth"] * Rr
        put("mouth", "head", ray(bvh, (0.0, -2.0, mz), (0, 1, 0)))
        put("chin", "head", ray(bvh, (0.0, -2.0, mz - 0.08 * Rr), (0, 1, 0)))
        put("brow", "head", ray(bvh, (0.30 * Rr, -2.0, ez + FACE_FROM_EYES["brow"] * Rr), (0, 1, 0)))
        put("forehead", "head", ray(bvh, (0.0, -2.0, ez + FACE_FROM_EYES["forehead"] * Rr), (0, 1, 0)))
        put("cheek", "head", ray(bvh, (0.62 * Rr, -2.0, ez + FACE_FROM_EYES["cheek"] * Rr), (0, 1, 0)))
        put("ear", "head", ray(bvh, (2.0, hy_, hz_ - 0.05 * Rr), (-1, 0, 0)))
        put("top", "head", ray(bvh, (0.25 * Rr, hy_ - 0.15 * Rr, 4.0), (0, 0, -1)))
        put("nape", "head", ray(bvh, (0.22 * Rr, 2.0, W["head"].z + 0.04), (0, -1, 0)))
        put("chest", "torso", ray(bvh, (0.04, -2.0, hip_z + 0.72 * up), (0, 1, 0)))
        put("heart", "torso", ray(bvh, (0.07, -2.0, hip_z + 0.74 * up), (0, 1, 0)))
        put("cross", "torso", ray(bvh, (-0.07, -2.0, hip_z + 0.58 * up), (0, 1, 0)))
        put("belly", "torso", ray(bvh, (0.02, -2.0, hip_z + 0.30 * up), (0, 1, 0)))
        put("belt", "torso", ray(bvh, (0.04, -2.0, hip_z + 0.06), (0, 1, 0)))
        put("hip", "torso", ray(bvh, (2.0, W["hips"].y, hip_z - 0.01), (-1, 0, 0)))
        put("pocket", "torso", ray(bvh, (W["hip.L"].x, -2.0, hip_z - 0.06), (0, 1, 0)))
        res.setdefault("landmarks", {})[label] = out

    landmarks([body], "bare")
    dressed = paths.DRESSED / f"Aj_{sex}_{age}_dressed.blend"
    if dressed.exists():
        # the dressed twin: the same armature; its clothes and hair are measured as the outer surface
        clear()
        got = append(dressed, {"Armature", "Aj_Base_Body", "D_*"})
        arm, body = got["Armature"], got["Aj_Base_Body"]
        arm.location = (0, 0, 0)
        aj_rig.reference_pose(arm)
        bpy.context.view_layer.update()
        res["dressed_file"] = str(Path("03_Dressed_Variants") / dressed.name)
        res["dressed_parts"] = sorted(n for n in got if n.startswith("D_"))
        meshes = [o for o in got.values() if o.type == "MESH"]
        landmarks(meshes, "dressed")
        dv = []
        dge = bpy.context.evaluated_depsgraph_get()
        for o in meshes:
            oe2 = o.evaluated_get(dge)
            m2 = oe2.to_mesh()
            dv += [(oe2.matrix_world @ v.co).z for v in m2.vertices]
            oe2.to_mesh_clear()
        res["b_dressed"] = {"height": max(dv) - min(dv)}
    res["seconds"] = round(time.time() - t0, 2)
    p = out_dir / f"{name}.json"
    p.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"MEASURED {name} height={b['height']:.3f} R={R:.3f} arm={b['arm1']:.3f}+{b['arm2']:.3f}+{hand_r:.3f} "
          f"legs a1={math.degrees(legs['L']['a1']):.1f} a2={math.degrees(legs['L']['a2']):.1f} "
          f"palmN.L={tuple(round(c, 2) for c in palm['L']['normal'])} marks={len(res['landmarks'].get('dressed', res['landmarks']['bare']))} "
          f"-> {p} ({res['seconds']} s)", flush=True)


for n in names:
    measure(n)
print("MEASURE_DONE")
