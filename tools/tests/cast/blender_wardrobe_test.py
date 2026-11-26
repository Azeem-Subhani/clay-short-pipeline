"""Inside-Blender tests of the Aj wardrobe: loading, shared textures, palette, skin tone, hide / recolor / wear, and what four dressed
characters cost in one scene.

    blender -b --factory-startup --python tools/tests/cast/blender_wardrobe_test.py -- [--four Name,Name,Name,Name]

A synthetic rigid add-on (a small cube 'crown' made here, saved to the scratchpad, registered only in memory) tests wear() without
touching the wardrobe registry. Prints one line per check and a JSON summary; exits 1 when a check fails.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import bpy

PIPE = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(PIPE))
sys.path.insert(0, str(PIPE / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import aj_wardrobe as W, cast  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--four", default="TeenBoyDarkHair,GirlPigtails,ElderManGreyHair,WomanLongStraight")
a = ap.parse_args(argv)
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def scene_stats():
    imgs = [i for i in bpy.data.images if i.type == "IMAGE" and i.size[0] > 0]
    tris = 0
    for o in bpy.data.objects:
        if o.type == "MESH" and not o.hide_render:
            tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
    return {"images": len(imgs), "megapixels": round(sum(i.size[0] * i.size[1] for i in imgs) / 1e6, 1), "triangles": tris,
            "materials": len(bpy.data.materials), "objects": len(bpy.data.objects)}


# ---- four dressed characters in one scene: time and weight
names = a.four.split(",")
shot = stagekit.begin("wtest", 2.0, "draft")
t0 = time.time()
acts, per = [], []
for i, n in enumerate(names):
    t1 = time.time()
    acts.append(cast.actor(f"c{i}", n, at=(i * 1.0, 0.0)))
    per.append(round(time.time() - t1, 2))
load_s = time.time() - t0
st4 = scene_stats()
print(f"4 dressed characters {names}: {load_s:.1f} s ({per}), {st4}", flush=True)
mem = sum(i.size[0] * i.size[1] * 4 for i in bpy.data.images if i.size[0] > 0) / 1e6
print(f"texture memory if all uncompressed 8-bit RGBA: {mem:.0f} MB (GPU holds them as it needs them)", flush=True)

# ---- the same outfit twice: textures shared, skin and materials separate, palette differs
shot = stagekit.begin("wtest2", 2.0, "draft")
x = cast.actor("x", "GirlPigtails", at=(0, 0))
n1 = scene_stats()
y = cast.actor("y", "GirlMessyRed", at=(1, 0))
n2 = scene_stats()
check("same outfit twice shares its textures", n2["images"] <= n1["images"] + 1, f"{n1['images']} -> {n2['images']} images")
check("two actors have two skin materials", x._skin_mat is not y._skin_mat and x._skin_mat.users == 1 and y._skin_mat.users == 1)
check("two faces", x.mesh.data.shape_keys is not y.mesh.data.shape_keys)


def base_color_of(act, role):
    ob = act.parts[role]
    m = ob.material_slots[0].material
    return tuple(round(c, 3) for c in m.node_tree.nodes["aj_tint"].inputs[0].default_value[:3]) if m.node_tree.nodes.get("aj_tint") else None


cx, cy = base_color_of(x, "polo"), base_color_of(y, "polo")
check("same outfit, different palette colours", cx != cy and cx is not None and cy is not None, f"{cx} vs {cy}")
check("garment materials are not shared", x.parts["polo"].material_slots[0].material is not y.parts["polo"].material_slots[0].material)

# ---- recolor
x.recolor(primary="#112233")
check("recolor primary", base_color_of(x, "polo") != cx)
x.recolor(polo="#445566", hair="#ffffff", skin="tan")
x.recolor(nonsense="#ffffff")
check("recolor of an unknown slot is a note, not a crash", any("no such palette slot" in n for n in shot.notes))
check("recolor hair", abs(x._wd["hair"]["mat"].node_tree.nodes["aj_hair_ramp"].color_ramp.elements[1].color[0] - 1.0) < 0.01)

# ---- hide
try:
    x.hide("polo")
    check("hiding the only top is refused", False, "no error")
except ValueError as e:
    check("hiding the only top is refused", "bare" in str(e), str(e)[:90])
check("the refused piece stays visible", not x.parts["polo"].hide_render)
x.hide("hair")
check("hide hair", x.parts["hair"].hide_render and x.parts["hair"].hide_viewport)
x.hide("nothing_here")
check("hide with no match is a note", any("matched no part" in n for n in shot.notes))

# ---- wear a synthetic rigid add-on, authored for the base head
tmp = Path(tempfile.mkdtemp()) / "crown.blend"
stagekit.begin("crownmaker", 1.0, "draft")                  # an empty scene: the add-on file holds the add-on and nothing else
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.10, depth=0.06, location=(0, -0.025, 1.76))
crown = bpy.context.active_object
crown.name = "Crown"
m = bpy.data.materials.new("gold")
m.use_nodes = True
crown.data.materials.append(m)
bpy.ops.wm.save_as_mainfile(filepath=str(tmp), copy=True)
shot = stagekit.begin("wtest3", 2.0, "draft")
idx = W.index()
idx.setdefault("addons", {})["crown"] = {"title": "test crown", "licence": "own", "era": ["any"], "kind": "rigid", "bone": "Head", "covers": [],
                                         "palette_slot": "accent", "file": str(tmp), "fits": {"Male_Teen": {"status": "pass", "review": "none", "file": None}}}
# the registry path is relative to the project: point the test file through an absolute path
orig_proj = W.core.PROJECT
t = cast.actor("t", "TeenBoyDarkHair", at=(0, 0), costume={"wear": [{"item": "crown", "color": "#D4AF37"}], "recolor": {"primary": "#334455"}})
check("add-on worn through the plan's costume", "crown" in t._wd["addons"] and "addon:crown" in t.parts)
cr = t._wd["addons"]["crown"]["objs"][0]
check("rigid add-on is bone-parented to the Head", cr.parent_type == "BONE" and cr.parent_bone == "mixamorig:Head", f"{cr.name} parent={cr.parent and cr.parent.name} type={cr.parent_type} bone={cr.parent_bone!r}")
t.hide("addon:crown")
check("hide addon:crown", cr.hide_render)
try:
    cast.actor("u", "GirlPigtails", at=(1, 0), costume={"wear": [{"item": "crown"}]})
    check("an add-on not fit-accepted on the body is refused", False, "no error")
except ValueError as e:
    check("an add-on not fit-accepted on the body is refused", "not fit-accepted" in str(e), str(e)[:80])
check("a character's own description", W.describe(t)["outfit"] == "jeans_shirt" and W.describe(t)["addons"] == ["crown"])

print(json.dumps({"four": {"seconds": round(load_s, 1), "per_character_s": per, **st4, "texture_mb_8bit": round(mem)}, "failed": FAILS}))
sys.exit(1 if FAILS else 0)
