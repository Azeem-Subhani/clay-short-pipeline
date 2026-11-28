"""Inside-Blender test of the cloth look that stagekit.aj_wardrobe puts on every character at load (style/style.json > look.cloth).

    blender -b --factory-startup --python tools/tests/look/test_cloth_look.py

Checks, on loaded characters: cloth materials carry the style values (specular, sheen, sheen roughness, a roughness floor placed after
the roughness texture); leather, rubber and metal are untouched; the Solidify exists on garments with the chosen visibility (render
only, after the Armature) and not on shoes; the viewport evaluation (what the physical sweep, the QA and the review checks read) has
the same vertex count with and without it while a real render sees the shell; the colour graph of every garment is the same with
and without the look (nothing that feeds Base Color changes); a pack-made outfit (jeans_shirt) gets the response on its cloth.
Prints one line per check; exits 1 when one fails.
"""
import copy
import os
import sys
from pathlib import Path

import bpy
import numpy as np

PIPE = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
sys.path.insert(0, str(PIPE / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import aj_wardrobe as W, cast, cast_aj, core  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


SPEC, SHEEN, SHEEN_R, FLOOR = (core.look("cloth.specular", 0.15), core.look("cloth.sheen", 0.7),
                               core.look("cloth.sheen_roughness", 0.5), core.look("cloth.roughness_floor", 0.8))
MM = core.look("cloth.thickness_mm", 2.5)


def mats_of(actor):
    out = []
    for role, ob in actor.parts.items():
        for s in ob.material_slots:
            if s.material is not None and s.material.get("fabric_kind"):
                out.append((role, ob, s.material))
    return out


def colour_signature(mat):
    """Everything that decides the base colour: the nodes upstream of Base Color with their settings, and the links among them.
    The response nodes (roughness, specular, sheen) are left out; they do not feed Base Color."""
    nt = mat.node_tree
    b = W._principled(mat)
    seen, stack = set(), [b.inputs["Base Color"].links[0].from_node] if b.inputs["Base Color"].is_linked else []
    while stack:
        n = stack.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        for i in n.inputs:
            for lk in i.links:
                stack.append(lk.from_node)
    sig = [("base", round(b.inputs["Base Color"].default_value[0], 4), b.inputs["Base Color"].is_linked)]
    for name in sorted(seen):
        n = nt.nodes[name]
        vals = []
        for i in n.inputs:
            if hasattr(i, "default_value") and not i.is_linked:
                v = i.default_value
                vals.append(tuple(round(x, 4) for x in v) if hasattr(v, "__len__") else round(float(v), 4))
        sig.append((name, n.bl_idname, tuple(vals), tuple(sorted((i.name, lk.from_node.name) for i in n.inputs for lk in i.links))))
    return sig


def tint_of(mat):
    """The colour the material multiplies its texture by (the aj_tint node, else the Palette)."""
    nt = mat.node_tree
    t = nt.nodes.get("aj_tint")
    if t is not None:
        return tuple(round(x, 4) for x in t.inputs[0].default_value[:3])
    p = nt.nodes.get("Palette")
    return tuple(round(x, 4) for x in p.outputs[0].default_value[:3]) if p else None


# ---- load a character with cloth, find the materials
stagekit.begin("cloth_a", 2.0, "draft")
A = cast.actor("a", "OfficeWomanCardigan", at=(0, 0))
M = mats_of(A)
cloth = [(r, o, m) for r, o, m in M if m["fabric_kind"] in W.CLOTH_KINDS]
other = [(r, o, m) for r, o, m in M if m["fabric_kind"] not in W.CLOTH_KINDS]
check("the character wears cloth and non-cloth kinds", bool(cloth) and bool(other),
      f"cloth {sorted({m['fabric_kind'] for _, _, m in cloth})}, other {sorted({m['fabric_kind'] for _, _, m in other})}")

for role, ob, m in cloth:
    b = W._principled(m)
    r = b.inputs["Roughness"]
    ok = (abs(b.inputs["Specular IOR Level"].default_value - SPEC) < 1e-6 and abs(b.inputs["Sheen Weight"].default_value - SHEEN) < 1e-6
          and abs(b.inputs["Sheen Roughness"].default_value - SHEEN_R) < 1e-6)
    check(f"{m.name} ({role}): specular {SPEC}, sheen {SHEEN} / {SHEEN_R}", ok)
    if r.is_linked:
        fl = r.links[0].from_node
        check(f"{m.name}: roughness floor {FLOOR} after the roughness texture",
              fl.name.startswith(W.FLOOR_NAME) and fl.operation == "MAXIMUM" and abs(fl.inputs[1].default_value - FLOOR) < 1e-6
              and fl.inputs[0].is_linked and fl.inputs[0].links[0].from_node.type != "MATH")
    else:
        check(f"{m.name}: roughness at least {FLOOR}", r.default_value >= FLOOR - 1e-6)

for role, ob, m in other:
    b = W._principled(m)
    check(f"{m.name} ({m['fabric_kind']}) is left alone",
          abs(b.inputs["Specular IOR Level"].default_value - 0.5) < 1e-6 and b.inputs["Sheen Weight"].default_value == 0.0
          and not m.get("aj_cloth") and m.node_tree.nodes.get(W.FLOOR_NAME) is None)

# ---- the metal watch and the hair
B = cast.actor("b", "ManagerBlazer", at=(2, 0))
steel = [m for _, _, m in mats_of(B) if m["fabric_kind"] == "steel"]
check("a steel material is untouched", bool(steel) and all(abs(W._principled(m).inputs["Roughness"].default_value - 0.28) < 1e-6
                                                           and not m.get("aj_cloth") for m in steel))
hair = B.parts["hair"].material_slots[0].material
hb = W._principled(hair)
check("hair is a little more matte", abs(hb.inputs["Roughness"].default_value - core.look("hair.roughness", 0.45)) < 1e-6
      and abs(hb.inputs["Specular IOR Level"].default_value - core.look("hair.specular", 0.5)) < 1e-6)

# ---- thickness
gar = {r: o for r, o, _ in cloth}
for role in ("trousers", "blouse", "addon:cardigan"):
    ob = gar.get(role)
    md = ob.modifiers.get(W.THICK_NAME) if ob else None
    kinds = [m.type for m in ob.modifiers] if ob else []
    ok = (md is not None and md.type == "SOLIDIFY" and abs(md.thickness - MM / 1000) < 1e-9 and md.offset == 1.0
          and md.show_render and not md.show_viewport and kinds.index("SOLIDIFY") > kinds.index("ARMATURE"))
    check(f"{role}: Solidify {MM} mm, outward, render only, after the Armature", ok)
shoes = A.parts.get("shoes")
check("shoes get no thickness", shoes is not None and shoes.modifiers.get(W.THICK_NAME) is None)
check("the body gets no thickness", A.mesh.modifiers.get(W.THICK_NAME) is None)

# the viewport evaluation (physical sweep, QA) is unchanged; a render sees the shell
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
bpy.context.scene.collection.objects.link(cam)
cam.location = (0, -4, 1.0)
cam.rotation_euler = (1.5708, 0, 0)
bpy.context.scene.camera = cam
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
tr = gar["trousers"]
ev = tr.evaluated_get(dg)
n_view = len(ev.to_mesh().vertices)
ev.to_mesh_clear()
n_base = len(tr.data.vertices)
sc = bpy.context.scene


def silhouette_pixels(show_shell: bool) -> int:
    """Render the trousers alone, side on, orthographic and transparent, and count the covered pixels."""
    tr.modifiers[W.THICK_NAME].show_render = show_shell
    out = Path(os.environ.get("TEMP", ".")) / f"cloth_test_{int(show_shell)}.png"
    sc.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(str(out))
    buf = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
    im.pixels.foreach_get(buf)
    px = buf.reshape(-1, 4)[:, :3]
    n = int((np.abs(px - px[0]).max(axis=1) > 0.02).sum())              # pixels that differ from the background (corner pixel)
    bpy.data.images.remove(im)
    return n


for o in bpy.data.objects:
    if o is not tr and o.type in ("MESH", "LIGHT"):
        o.hide_render = True
cam.data.type = "ORTHO"
cam.data.ortho_scale = 1.2
cam.location = (tr.evaluated_get(dg).matrix_world.translation.x, -4.0, 0.55)
sc.render.engine = "BLENDER_EEVEE"
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 6.0
sun.rotation_euler = (1.2, 0.0, 0.0)
bpy.context.scene.collection.objects.link(sun)
if bpy.context.scene.world is None:
    bpy.context.scene.world = bpy.data.worlds.new("w")
bpy.context.scene.world.use_nodes = True
for n in bpy.context.scene.world.node_tree.nodes:
    if n.type == "BACKGROUND":
        n.inputs["Strength"].default_value = 0.0
sc.render.resolution_x = sc.render.resolution_y = 512
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
n_off, n_on = silhouette_pixels(False), silhouette_pixels(True)
tr.modifiers[W.THICK_NAME].show_render = True
check("viewport evaluation has the fitted vertex count (checks read it)", n_view == n_base, f"{n_view} == {n_base}")
check("a render shows the shell (more pixels covered)", n_on > n_off > 0, f"{n_off} -> {n_on} px")

SIG = {m.name: (colour_signature(m), tint_of(m)) for _, _, m in M}      # taken now: beginning the next shot clears the scene

# ---- colour: the same character with the look switched off has the same colour graph and tint
W.CLOTH = False
stagekit.begin("cloth_b", 2.0, "draft")
A0 = cast.actor("a", "OfficeWomanCardigan", at=(0, 0))
W.CLOTH = True
M0 = {m.name: m for _, _, m in mats_of(A0)}
check("with the look off nothing is changed (no thickness, no floor)", all(not m.get("aj_cloth") for m in M0.values())
      and all(o.modifiers.get(W.THICK_NAME) is None for o in A0.parts.values()))
same = True
for name, (sig, tint) in SIG.items():
    m0 = M0.get(name)
    if m0 is None or sig != colour_signature(m0) or tint != tint_of(m0):
        same = False
        print("   colour differs on", name)
check("every garment's colour graph and tint are identical with and without the look", same and len(SIG) == len(M0), f"{len(SIG)} materials")

# a per-shot recolour after loading still takes
stagekit.begin("cloth_c", 2.0, "draft")
C = cast.actor("c", "OfficeWomanCardigan", at=(0, 0))
C.recolor(primary="#2F6FB0")
blouse_m = next(m for r, _, m in mats_of(C) if r == "blouse" and m["fabric_kind"] == "cotton")
check("recolor still sets the tint on a cloth material",
      tint_of(blouse_m) == tuple(round(x, 4) for x in core.hex_rgba("#2F6FB0")[:3]) and blouse_m.get("aj_cloth") is True)

# ---- the pack's own outfit
stagekit.begin("cloth_d", 2.0, "draft")
ent = copy.deepcopy(cast_aj.entry("TeenBoyDarkHair"))
ent.pop("name", None)
ent["outfit"] = "jeans_shirt"
ent["addons"] = []
cast_aj.cast_data()["characters"]["PackJeans"] = ent
P = cast.actor("p", "PackJeans", at=(0, 0))
pm = {r: o.material_slots[0].material for r, o in P.parts.items() if r in ("polo", "jeans")}
good = bool(pm)
for r, m in pm.items():
    b = W._principled(m)
    good &= m.get("aj_cloth") is True and abs(b.inputs["Specular IOR Level"].default_value - SPEC) < 1e-6 and \
        b.inputs["Roughness"].links[0].from_node.name.startswith(W.FLOOR_NAME)
check("jeans_shirt: the pack's polo and jeans get the cloth response", good, str({r: bool(m.get("aj_cloth")) for r, m in pm.items()}))
check("jeans_shirt: its pieces get the thickness", all(P.parts[r].modifiers.get(W.THICK_NAME) is not None for r in pm))

print("FAILED: " + ", ".join(FAILS) if FAILS else "all cloth look checks passed")
sys.exit(1 if FAILS else 0)
