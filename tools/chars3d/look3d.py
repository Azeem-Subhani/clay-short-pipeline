"""look3d.py - look at ONE 3D character before using it: four turns and four faces on one sheet. Also the wardrobe sheet.

    blender -b --factory-startup --python look3d.py -- --char Beekeeper --out <abs.png> [--wear straw_hat,apron] [--pipeline <root>]
    blender -b --factory-startup --python look3d.py -- --wardrobe AdultMan,Queen,Boy --out <abs.png>

The first form builds the character eight times: seen from the front, three-quarter, side and back, then from the front
happy, surprised, angry and grinning. The second builds every wardrobe piece on each named character.
"""
import argparse
import math
import os
import sys
from pathlib import Path

import bpy

_W = Path(__file__).resolve().parents[1]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[2]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--char", default="")
ap.add_argument("--wardrobe", default="")
ap.add_argument("--out", required=True)
ap.add_argument("--wear", default="")
ap.add_argument("--width", type=int, default=2800)
ap.add_argument("--pipeline", default=str(_PIPE))
a = ap.parse_args(argv)
os.environ["SHORTS_PROJECT"] = a.pipeline
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit  # noqa: E402
from stagekit import cast3d, wardrobe  # noqa: E402

shot = stagekit.begin("look", 1.0, "draft")
sc = bpy.context.scene
DX, DZ = 0.95, 2.3
cells = []                    # (row, col, base, yaw, expr, wear, label)
if a.wardrobe:
    names = [n for n in a.wardrobe.split(",") if n]
    items = sorted(wardrobe.ITEMS)
    for r, n in enumerate(names):
        for c, it in enumerate(items):
            cells.append((r, c, n, 25.0, "", [it], it if r == 0 else ""))
    cols = len(items)
else:
    wear = [w for w in a.wear.split(",") if w]
    for c, (yaw, lab) in enumerate(((0, "front"), (42, "three-quarter"), (90, "side"), (180, "back"))):
        cells.append((0, c, a.char, yaw, "", wear, lab))
    for c, ex in enumerate(("happy", "surprised", "angry", "grin")):
        cells.append((1, c, a.char, 12, ex, wear, ex))
    cols = 4
rows = max(c[0] for c in cells) + 1
for i, (r, c, base, yaw, ex, wear, lab) in enumerate(cells):
    x, z = (c - (cols - 1) / 2) * DX, -r * DZ
    act = cast3d.actor(f"c{i}", base, at=(x, 0, z))
    act.heading(float(yaw))
    for w in wear:
        try:
            act.wear(w)
        except Exception as e_:
            print("WEAR_FAILED", base, w, e_)
    if ex:
        act.expr(ex, 0.0, 0.0)
    if lab:
        cu = bpy.data.curves.new(f"l{i}", "FONT")
        cu.body = lab
        cu.align_x = "CENTER"
        cu.size = 0.09
        t = bpy.data.objects.new(f"l{i}", cu)
        sc.collection.objects.link(t)
        t.location = (x, -0.6, z - 0.17)
        t.rotation_euler = (math.radians(90), 0, 0)
        m = bpy.data.materials.new("lbl")
        m.use_nodes = True
        m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.03, 0.03, 1)
        cu.materials.append(m)
W, H = cols * DX, rows * DZ
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 1.0, -H / 2 + DZ / 2 + 0.4))
bg = bpy.context.active_object
bg.scale = (W + 4, H + 4, 1)
bg.rotation_euler = (math.radians(90), 0, 0)
m = bpy.data.materials.new("paper")
m.use_nodes = True
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.90, 0.87, 0.80, 1)
m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
bg.data.materials.append(m)
bg.visible_shadow = False
for nm, e, rot, sh in (("sun", 2.6, (58, -12, -28), True), ("fill", 0.8, (75, 0, 40), False)):
    L = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "SUN"))
    L.data.energy = e
    L.data.use_shadow = sh
    L.rotation_euler = tuple(math.radians(v) for v in rot)
    sc.collection.objects.link(L)
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.92, 1.0, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
sc.world = w
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = W + 0.3
cam.location = (0, -12, -H / 2 + DZ / 2 + 0.72)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam
sc.render.resolution_x = a.width
sc.render.resolution_y = int(a.width * (H + 0.2) / (W + 0.3))
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sc.render.filepath = a.out
bpy.ops.render.render(write_still=True)
print("LOOK_DONE", a.out)
