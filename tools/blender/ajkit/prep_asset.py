# Vendored from packs/aj_rebuild_v1/10_Pipeline_Scripts/dress_test/prep_asset.py (Aj pack, 2026-11-26).
# Changes against the pack copy, nothing else: the rig-kind label table in `check` gained its missing "arp" entry
# (check mode crashed with KeyError: 'arp' on Auto-Rig Pro files). Prepared files go to ajkit.paths.PREPARED by
# convention (tools/chars_aj/fit.py prep). No conversion rule or landmark fraction is changed.
"""Check a downloaded clothing asset, and make it ready for fit_rigged.py. The downloaded file is never changed.

fit_rigged.py needs ONE .blend that holds exactly this:
  * a mesh named `Body`: the body the clothes were modelled on;
  * the garments, each a separate mesh. Every mesh that is not `Body` is fitted as a garment;
  * one armature whose bones have Mixamo names (Hips, Spine, Spine1, Spine2, Neck, Head, LeftShoulder, LeftArm ...,
    with or without the `mixamorig:` prefix), and the meshes weighted to those bones.
Hardly any asset on BlenderKit comes like that: most are whole characters on a Rigify rig with hair, eyes, shoes and
props in the same file. This script says what a file holds, and converts it.

1. Look at what the file holds and what it still needs:

    blender --background <downloaded.blend> --python prep_asset.py -- check

2. Convert it (Rigify or Mixamo rig), naming the body mesh and the garment meshes to keep:

    blender --background <downloaded.blend> --python prep_asset.py -- <out.blend> <body_obj> <garment>[,<garment>...]

   Write <out.blend> to work\\dress_test\\library\\_prepared\\ and give that file to fit_rigged.py.
   A garment can be renamed on the way: <mesh>=<name> (a dressed Aj file as the asset: D_jeans=jeans,D_polo=polo).
   Modifiers that only hide faces (MASK, the fit mask HideUnderClothes) are not baked: the body stays whole.

What the conversion does:
  a. bakes the body and the garments in the rig's REST pose with every modifier except the Armature (subdivision,
     solidify ...), so the meshes are plain;
  b. Mixamo rig: keeps the armature and the weights as they are.
     Rigify rig: builds an armature with Mixamo names and merges the DEF weights into Mixamo groups (the two half-bones
     of a Rigify limb go to one Mixamo bone; face and finger bones go to Head / Hand);
  c. writes Body, the garments and the armature to <out.blend>. Nothing else.
No garment or body shape is changed.

WHERE THE JOINTS GO DECIDES THE FIT (Rigify rigs). The fitter describes cloth by "which bone, how far along it", so
the asset's skeleton must mark the same places on its body as ours marks on ours. Limb joints (shoulder, elbow,
wrist, hip, knee, ankle) are real pivots and are taken from the Rigify rig as they are. The torso joints and the
start of the collarbone have no counterpart in a Rigify rig: its spine bones are cut at other heights than Mixamo's.
They are therefore placed by landmarks, at the same fractions the Aj skeletons use (measured on all eight variants):
hip joint 0.195, Spine 0.32, Spine1 0.515, Spine2 0.70 of the way from the crotch to the base of the neck, and the
collarbone starting 0.42 of the way from the middle to the shoulder joint. Tested on 2026-11-26 with the Rigify
spine bones used as they are instead: the same outfit then fits visibly worse (seat and back pockets stretched, the
waistband high) and fails the check at 1.0 to 1.2 bone lengths. If Aj's skeleton is ever re-proportioned, measure
these fractions again."""
import bpy, sys, re
import numpy as np
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
P = "mixamorig:"
# the bones the fitter describes cloth on. Head, hands and feet are used when they are there (as the far end of the
# neck, forearm and shin) but a clothes rig often stops short of them.
NEEDED = ["Hips", "Spine", "Spine1", "Spine2", "Neck"] + [s + n for s in ("Left", "Right") for n in
          ("Shoulder", "Arm", "ForeArm", "UpLeg", "Leg")]


def short(n):
    return n.split(":")[-1]


def rig_kind(arm):
    names = {b.name for b in arm.data.bones}
    if all(n in {short(x) for x in names} for n in NEEDED):
        return "mixamo"
    if {"DEF-spine", "DEF-spine.004", "DEF-upper_arm.L", "DEF-thigh.L", "DEF-shin.L", "DEF-forearm.L"} <= names:
        return "rigify"
    if {"root.x", "spine_01.x", "neck.x", "head.x", "shoulder.l", "arm_stretch.l", "forearm_stretch.l",
            "thigh_stretch.l", "leg_stretch.l", "foot.l"} <= names:
        return "arp"                    # Auto-Rig Pro: converted like Rigify, through ARP_AS_RIGIFY below
    return "other"


# Auto-Rig Pro deform bones, named as the Rigify bones the converter reads joints from (added 2026-11-26 for the
# BlenderKit "Roman Warrior"). In ARP the upper arm is c_arm_twist_offset then arm_stretch, the thigh thigh_twist then
# thigh_stretch, the shin leg_stretch then leg_twist; spine root.x (hips, pointing down), spine_01..03, neck, head.
ARP_AS_RIGIFY = {"DEF-spine": "root.x", "DEF-spine.001": "spine_01.x", "DEF-spine.002": "spine_02.x",
                 "DEF-spine.003": "spine_03.x", "DEF-spine.004": "neck.x", "DEF-spine.006": "head.x"}
for _s in "LR":
    _a = _s.lower()
    ARP_AS_RIGIFY.update({f"DEF-upper_arm.{_s}": f"c_arm_twist_offset.{_a}", f"DEF-forearm.{_s}": f"forearm_stretch.{_a}",
                          f"DEF-hand.{_s}": f"hand.{_a}", f"DEF-thigh.{_s}": f"thigh_twist.{_a}",
                          f"DEF-shin.{_s}": f"leg_stretch.{_a}", f"DEF-foot.{_s}": f"foot.{_a}", f"DEF-toe.{_s}": f"toes_01.{_a}"})


def arp_to_mixamo(n):
    """Auto-Rig Pro deform bone name -> Mixamo short name (face and unknown bones -> Head)."""
    spine = {"root.x": "Hips", "spine_01.x": "Spine", "spine_02.x": "Spine1", "spine_03.x": "Spine2", "neck.x": "Neck",
             "head.x": "Head"}
    if n in spine:
        return spine[n]
    m = re.search(r"\.([lr])$", n)
    if not m:
        return "Head"
    s = {"l": "Left", "r": "Right"}[m.group(1)]
    b = n[:-2]
    for pre, mx in (("shoulder", "Shoulder"), ("c_arm_twist", "Arm"), ("arm_", "Arm"), ("forearm", "ForeArm"),
                    ("thigh", "UpLeg"), ("leg_", "Leg"), ("foot", "Foot"), ("toes", "ToeBase")):
        if b.startswith(pre):
            return s + mx
    if any(k in b for k in ("hand", "thumb", "index", "middle", "ring", "pinky")):
        return s + "Hand"
    return "Head"


def skinned_to(o, arm):
    return any(m.type == 'ARMATURE' and m.object is arm for m in o.modifiers) or (o.parent is arm and len(o.vertex_groups) > 0)


arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
meshes = [o for o in bpy.data.objects if o.type == 'MESH']

# ---------------------------------------------------------------------------------------------------- check
if a[0] == "check":
    print("ASSET CHECK", bpy.data.filepath)
    problems = []
    if len(arms) != 1:
        problems.append(f"{len(arms)} armatures (need exactly one): {[o.name for o in arms]}")
    arm = max(arms, key=lambda o: len(o.data.bones)) if arms else None
    kind = rig_kind(arm) if arm else "none"
    print("  rig:", repr(arm.name) if arm else None, "->", {"mixamo": "Mixamo bone names", "rigify": "Rigify (DEF- bones)",
          "arp": "Auto-Rig Pro (converted like Rigify)",
          "other": "neither Mixamo nor Rigify", "none": "no armature"}[kind])
    if kind == "other":
        have = {short(b.name) for b in arm.data.bones}
        problems.append("the rig is neither Mixamo nor Rigify; Mixamo bones missing: " + ", ".join(n for n in NEEDED if n not in have)
                        + ". This script cannot convert it.")
    if kind == "none":
        problems.append("no armature: a garment without the rig and body it was made on cannot go through fit_rigged.py")
    rows = sorted(meshes, key=lambda o: -len(o.data.vertices))
    print("  meshes (largest first):")
    for o in rows[:40]:
        print("    %-40s %7d verts  %s%s" % (repr(o.name), len(o.data.vertices),
              "skinned" if arm and skinned_to(o, arm) else "NOT skinned to the rig", "  hidden" if o.hide_render else ""))
    if len(rows) > 40:
        print("    ... and", len(rows) - 40, "more")
    body = [o for o in meshes if o.name.split(".")[0] == "Body"]
    others = [o for o in meshes if o not in body]
    if kind == "mixamo" and len(body) == 1 and 1 <= len(others) <= 8 and len(arms) == 1:
        unsk = [o.name for o in others + body if not skinned_to(o, arm)]
        if unsk:
            problems.append("not skinned to the rig: " + ", ".join(unsk))
        if not problems:
            print("  READY: usable by fit_rigged.py as it is. Garments:", [o.name for o in others])
    else:
        if not body:
            problems.append("no mesh named exactly `Body`: name the body mesh when converting")
        if len(others) > 8:
            problems.append(f"{len(others)} meshes besides the body: the fitter would fit every one as a garment. Keep only the garments when converting")
        if kind in ("rigify", "arp"):
            problems.append(("Rigify" if kind == "rigify" else "Auto-Rig Pro") + " rig: convert it")
    big = [(i.name, tuple(i.size)) for i in bpy.data.images if max(i.size[:]) > 4096]
    if big:
        print("  note: textures larger than 4K (each dressed file will be large):", big[:6])
    if problems:
        print("  NOT READY:")
        for p in problems:
            print("    -", p)
        if kind in ("mixamo", "rigify", "arp"):
            print("  convert with:  blender --background <this file> --python prep_asset.py -- <out.blend> <body_obj> <garment>[,<garment>...]")
    sys.exit(0)

# ---------------------------------------------------------------------------------------------------- convert
OUT, BODY, GARMENTS = a[0], a[1], a[2].split(",")
# a garment may be given as <mesh>=<new name>. A dressed Aj file used as the asset has garments named D_<name>; the
# fitter names its output "D_" + the asset garment's name, so keep them as <name> to get D_<name> again, not D_D_<name>.
RENAME = {g.split("=")[0]: (g.split("=")[1] if "=" in g else g.split("=")[0]) for g in GARMENTS}
GARMENTS = list(RENAME)
for n in [BODY] + GARMENTS:
    if n not in bpy.data.objects or bpy.data.objects[n].type != 'MESH':
        sys.exit(f"PREP FAILED: no mesh named {n!r} in this file (run with `check` to list them)")
if not arms:
    sys.exit("PREP FAILED: no armature in this file")
arm = max(arms, key=lambda o: len(o.data.bones))
KIND = rig_kind(arm)
if KIND == "other":
    sys.exit("PREP FAILED: the rig is neither Mixamo nor Rigify")
arm.data.pose_position = 'REST'
bpy.context.view_layer.update()
B = arm.data.bones


def side(n):
    m = re.search(r"\.([LR])(\.|$)", n)
    return {"L": "Left", "R": "Right"}[m.group(1)] if m else None


def to_mixamo(n):
    """Rigify deform bone name -> Mixamo short name (None for a bone that is not part of the body)."""
    if not n.startswith("DEF-"):
        return None
    s = side(n)
    base = n[4:]
    spine = {"spine": "Hips", "spine.001": "Spine", "spine.002": "Spine1", "spine.003": "Spine2", "spine.004": "Neck",
             "spine.005": "Neck", "spine.006": "Head"}
    if base in spine:
        return spine[base]
    if base.startswith("pelvis"):
        return "Hips"
    if base.startswith("breast"):
        return "Spine2"
    if s:
        if base.startswith("shoulder"):
            return s + "Shoulder"
        if base.startswith("upper_arm"):
            return s + "Arm"
        if base.startswith("forearm"):
            return s + "ForeArm"
        if base.startswith(("hand", "palm", "f_", "thumb")):
            return s + "Hand"
        if base.startswith("thigh"):
            return s + "UpLeg"
        if base.startswith("shin"):
            return s + "Leg"
        if base.startswith("foot"):
            return s + "Foot"
        if base.startswith("toe"):
            return s + "ToeBase"
    return "Head"                       # face: ears, eyes, lids, lips, jaw, chin, nose, tongue, teeth, brows


# ------------------------------------------------------------------ a. bake the meshes at rest
objs = {n: bpy.data.objects[n] for n in [BODY] + GARMENTS}
# modifiers that only HIDE faces are not baked: a dressed Aj file's body carries the fit mask (scripts\fitcheck.py
# MASK_MOD, a geometry-nodes modifier) that hides the skin under its clothes; baked, the asset body would have holes.
HIDE_ONLY = ("HideUnderClothes",)
for o in objs.values():
    for m in o.modifiers:
        if m.type in ('ARMATURE', 'PARTICLE_SYSTEM', 'MASK') or m.name in HIDE_ONLY:
            m.show_viewport = False
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get(); dg.update()
new = {}
for n, o in objs.items():
    o.name = n + "_src"                 # the new object takes the plain name
for n, o in objs.items():
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    me.transform(o.matrix_world)
    ob = bpy.data.objects.new("Body" if n == BODY else RENAME[n], me)
    for g in o.vertex_groups:           # same names in the same order: the baked mesh's weights refer to them by index
        ob.vertex_groups.new(name=g.name)
    new[n] = ob
    print("baked", n, "->", ob.name, len(me.vertices), "verts")

if KIND == "mixamo":
    # ---------------------------------------------------------------- b. Mixamo rig: keep armature and weights
    aob = arm
    aob.animation_data_clear()
    for n, ob in new.items():
        m = ob.modifiers.new("Armature", 'ARMATURE'); m.object = aob
        bpy.context.scene.collection.objects.link(ob)
        have = {short(g.name) for g in ob.vertex_groups}
        print(ob.name, "weight groups on Mixamo bones:", len(have & set(NEEDED)), "of", len(NEEDED))
else:
    # ---------------------------------------------------------------- b. Rigify rig: Mixamo armature, joint to joint
    from mathutils.bvhtree import BVHTree
    if KIND == "arp":
        MAP = {b.name: (arp_to_mixamo(b.name) if b.use_deform else None) for b in B}
    else:
        MAP = {b.name: to_mixamo(b.name) for b in B}
    used = sorted({v for v in MAP.values() if v})
    AL = ARP_AS_RIGIFY if KIND == "arp" else {}

    def head(n):
        return Vector(B[AL.get(n, n)].head_local)

    def tail(n):
        return Vector(B[AL.get(n, n)].tail_local)

    bme = new[BODY].data
    bvh = BVHTree.FromPolygons([v.co.copy() for v in bme.vertices], [tuple(p.vertices) for p in bme.polygons])
    Hh = max(v.co.z for v in bme.vertices)
    c0 = head("DEF-spine")
    roofs = []                           # the crotch: the roof of the fork between the thighs, by rays up the middle
    for y in c0.y + np.linspace(-0.035 * Hh, 0.035 * Hh, 15):
        hit = bvh.ray_cast(Vector((c0.x, y, 0.2 * Hh)), Vector((0, 0, 1)))
        if hit[0] is not None and 0.25 * Hh < hit[0].z < c0.z:
            roofs.append(hit[0].z)
    if not roofs:
        sys.exit("PREP FAILED: could not find the crotch of the body mesh (is it the right mesh, standing upright?)")
    z_crotch = min(roofs)
    z_neck = head("DEF-spine.004").z
    spine_pts = sorted([(head(n).z, head(n).y) for n in ("DEF-spine", "DEF-spine.001", "DEF-spine.002", "DEF-spine.003", "DEF-spine.004")])
    FRAC = {"Hips": 0.195, "Spine": 0.32, "Spine1": 0.515, "Spine2": 0.70, "Neck": 1.0}      # see the note at the top
    CLAVICLE = 0.42
    HEAD = {}
    for jn, fr in FRAC.items():
        z = z_crotch + fr * (z_neck - z_crotch)
        HEAD[jn] = Vector((c0.x, float(np.interp(z, [q[0] for q in spine_pts], [q[1] for q in spine_pts])), z))
    HEAD["Head"] = head("DEF-spine.006")
    print("crotch %.3f neck %.3f  hips %.3f spine %.3f spine1 %.3f spine2 %.3f" % (z_crotch, z_neck, HEAD["Hips"].z, HEAD["Spine"].z, HEAD["Spine1"].z, HEAD["Spine2"].z))
    NEXT = {"Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "Neck": "Head"}
    PARENT = {"Spine": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Neck": "Spine2", "Head": "Neck"}
    LAST_TAIL = {"Head": tail("DEF-spine.006")}
    for sd, s_ in (("Left", "L"), ("Right", "R")):
        arm_h = head(f"DEF-upper_arm.{s_}")
        sh = Vector((arm_h.x * CLAVICLE, arm_h.y, arm_h.z))
        HEAD[sd + "Shoulder"] = sh; HEAD[sd + "Arm"] = arm_h
        HEAD[sd + "ForeArm"] = head(f"DEF-forearm.{s_}"); HEAD[sd + "Hand"] = head(f"DEF-hand.{s_}")
        HEAD[sd + "UpLeg"] = head(f"DEF-thigh.{s_}"); HEAD[sd + "Leg"] = head(f"DEF-shin.{s_}")
        HEAD[sd + "Foot"] = head(f"DEF-foot.{s_}"); HEAD[sd + "ToeBase"] = head(f"DEF-toe.{s_}")
        NEXT.update({sd + "Shoulder": sd + "Arm", sd + "Arm": sd + "ForeArm", sd + "ForeArm": sd + "Hand", sd + "UpLeg": sd + "Leg",
                     sd + "Leg": sd + "Foot", sd + "Foot": sd + "ToeBase"})
        PARENT.update({sd + "Shoulder": "Spine2", sd + "Arm": sd + "Shoulder", sd + "ForeArm": sd + "Arm", sd + "Hand": sd + "ForeArm",
                       sd + "UpLeg": "Hips", sd + "Leg": sd + "UpLeg", sd + "Foot": sd + "Leg", sd + "ToeBase": sd + "Foot"})
        LAST_TAIL[sd + "Hand"] = tail(f"DEF-hand.{s_}"); LAST_TAIL[sd + "ToeBase"] = tail(f"DEF-toe.{s_}")

    adata = bpy.data.armatures.new("Asset_Mixamo_Rig")
    aob = bpy.data.objects.new("Asset_Mixamo_Rig", adata)
    bpy.context.scene.collection.objects.link(aob)
    bpy.context.view_layer.objects.active = aob
    aob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    for nme in HEAD:
        eb = adata.edit_bones.new(P + nme)
        eb.head = HEAD[nme]
        eb.tail = HEAD[NEXT[nme]] if nme in NEXT else LAST_TAIL[nme]
        if (eb.tail - eb.head).length < 0.01:
            eb.tail = eb.head + Vector((0, 0, 0.05))
    for nme, par in PARENT.items():
        adata.edit_bones[P + nme].parent = adata.edit_bones[P + par]
    bpy.ops.object.mode_set(mode='OBJECT')
    print("armature built:", len(adata.bones), "bones")

    # merge the DEF groups into Mixamo groups
    for n, ob in new.items():
        src = objs[n]
        gname = {g.index: g.name for g in src.vertex_groups}
        me = ob.data
        W = np.zeros((len(me.vertices), len(used)))
        for v in me.vertices:
            for g in v.groups:
                mx = MAP.get(gname.get(g.group))
                if mx:
                    W[v.index, used.index(mx)] += g.weight
        ob.vertex_groups.clear()
        tot = W.sum(1)
        nz = tot > 1e-6
        W[nz] /= tot[nz][:, None]
        if (~nz).any() and nz.any():                      # a vertex with no body weight takes its nearest weighted neighbour's
            from mathutils.kdtree import KDTree
            kd = KDTree(len(me.vertices))
            for i, v in enumerate(me.vertices):
                if nz[i]:
                    kd.insert(v.co, i)
            kd.balance()
            for i in np.nonzero(~nz)[0]:
                W[i] = W[kd.find(me.vertices[i].co)[1]]
            nz = np.ones(len(nz), bool)
        for k, mx in enumerate(used):
            vg = ob.vertex_groups.new(name=P + mx)
            idx = np.nonzero(W[:, k] > 1e-4)[0]
            for i in idx:
                vg.add([int(i)], float(W[i, k]), 'REPLACE')
        print(ob.name, "weighted verts", int(nz.sum()), "of", len(nz), "unweighted", int((~nz).sum()))
        m = ob.modifiers.new("Armature", 'ARMATURE'); m.object = aob
        bpy.context.scene.collection.objects.link(ob)

# ------------------------------------------------------------------ c. write
ids = {aob} | set(new.values())
bpy.data.libraries.write(OUT, ids, compress=True)
print("PREPARED", KIND, "->", OUT)
