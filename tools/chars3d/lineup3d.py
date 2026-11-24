"""lineup3d.py - build 3D characters side by side and render them (a lineup, or a few for a look).

    blender -b --factory-startup --python lineup3d.py -- --sheets <cast3d.json> --out <abs.png> [--names A,B,...] [--cols 12]
            [--yaw 0] [--width 3600] [--label] [--pipeline <root>] [--expr happy]
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--sheets", default="", help="default: config/cast3d.json of the project")
ap.add_argument("--out", required=True)
ap.add_argument("--names", default="")
ap.add_argument("--cols", type=int, default=12)
ap.add_argument("--yaw", type=float, default=0.0)
ap.add_argument("--width", type=int, default=3000)
ap.add_argument("--label", action="store_true")
_W = Path(__file__).resolve().parents[1]
ap.add_argument("--pipeline", default=str((_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[2]))
ap.add_argument("--expr", default="")
ap.add_argument("--dx", type=float, default=0.86)
ap.add_argument("--dz", type=float, default=2.25)
a = ap.parse_args(argv)
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
from stagekit import fig3d  # noqa: E402

sc = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
doc = json.loads(Path(a.sheets or (Path(a.pipeline) / "config" / "cast3d.json")).read_text(encoding="utf-8"))["characters"]
names = [n for n in a.names.split(",") if n] or list(doc)
rows = [names[i:i + a.cols] for i in range(0, len(names), a.cols)]
W = a.cols * a.dx
H = len(rows) * a.dz
for r, row in enumerate(rows):
    for c, n in enumerate(row):
        x = (c - (len(row) - 1) / 2) * a.dx
        z = -r * a.dz
        try:
            f = fig3d.Fig(doc[n], n)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            print("BUILD_FAILED", n, ex)
            continue
        f.J["root"].location = (x, 0.0, z)
        f.J["root"].rotation_euler = (0, 0, math.radians(a.yaw))
        for sfx, s in (("L", -1.0), ("R", 1.0)):
            f.J[f"sh.{sfx}"].rotation_quaternion = (math.cos(math.radians(7)), 0.0, s * math.sin(math.radians(7)), 0.0)
        if a.expr:
            f.ctrl[a.expr] = 1.0
        if a.label:
            cu = bpy.data.curves.new(n + "_lbl", "FONT")
            cu.body = doc[n].get("label", n)
            cu.align_x = "CENTER"
            cu.size = 0.085
            t = bpy.data.objects.new(n + "_lbl", cu)
            sc.collection.objects.link(t)
            t.location = (x, -0.5, z - 0.16)
            t.rotation_euler = (math.radians(90), 0, 0)
            m = bpy.data.materials.new("lbl")
            m.use_nodes = True
            m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.03, 0.03, 1)
            cu.materials.append(m)
        print("BUILT", n, flush=True)
# paper, light, camera
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0.9, -H / 2 + a.dz / 2 + 0.4))
bg = bpy.context.active_object
bg.scale = (W + 4, H + 4, 1)
bg.rotation_euler = (math.radians(90), 0, 0)
m = bpy.data.materials.new("paper")
m.use_nodes = True
b = m.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.955, 0.93, 0.87, 1)
b.inputs["Roughness"].default_value = 1.0
bg.data.materials.append(m)
bg.visible_shadow = False
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.2
sun.data.angle = math.radians(8)
sun.rotation_euler = (math.radians(58), math.radians(-12), math.radians(-28))
sc.collection.objects.link(sun)
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "SUN"))
fill.data.energy = 1.0
fill.rotation_euler = (math.radians(75), 0, math.radians(40))
fill.data.use_shadow = False
sc.collection.objects.link(fill)
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.9, 0.92, 1.0, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.75
sc.world = w
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(W + 0.3, (H + 0.2) * 1.0)
cam.location = (0, -12, -H / 2 + a.dz / 2 + 0.72)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam
sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in type(sc.render).bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
sc.render.resolution_x = a.width
sc.render.resolution_y = int(a.width * (H + 0.2) / (W + 0.3))
sc.render.resolution_percentage = 100
sc.view_settings.view_transform = "Standard"
sc.render.filepath = a.out
sc.render.image_settings.file_format = "PNG"
bpy.ops.render.render(write_still=True)
print("LINEUP_DONE", a.out)
