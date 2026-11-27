"""Look test for canopy drips and rain splashes seen close to the lens, at final quality.

    blender -b --factory-startup --python tools/tests/kitfix/test_rain_drips.py -- --tag after [--fx-old <old fx.py>]

A canopy edge with fx.drips_edge 0.35 m in front of a 1.75 m stand-in figure and another 2.4 m behind him, fx.rain with splashes over a
ground plane, a camera 1.2 m from the figure at chest height looking through the drip line. Renders frames 5, 13 and 21 to
output/_staging/kitfix/drips/drips_<tag>_<frame>.png. --fx-old loads an older copy of fx.py (to make the "before" images).
"""
import argparse
import importlib.util
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("SHORTS_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.dont_write_bytecode = True
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stagekit  # noqa: E402
from stagekit import core, fx  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--tag", default="after")
ap.add_argument("--fx-old", default=None)
ap.add_argument("--frames", default="5,13,21")
a = ap.parse_args(argv)

if a.fx_old:
    spec = importlib.util.spec_from_file_location("stagekit._fx_old", a.fx_old)
    fx = importlib.util.module_from_spec(spec)
    sys.modules["stagekit._fx_old"] = fx
    spec.loader.exec_module(fx)

shot = stagekit.begin("rain_test", 1.0, "final")
sc = bpy.context.scene
sc.frame_end = 24

# world and light
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.38, 0.42, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(30))
core.link(sun, "Scene")

# ground and stand-in figure
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
g = bpy.context.object
gm = bpy.data.materials.new("ground")
gm.diffuse_color = (0.25, 0.25, 0.27, 1)
g.data.materials.append(gm)
bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.45, location=(0, 0, 0.725))
body = bpy.context.object
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.15, location=(0, 0, 1.6))
head = bpy.context.object
fm = bpy.data.materials.new("fig")
fm.diffuse_color = (0.55, 0.35, 0.3, 1)
for o in (body, head):
    o.data.materials.append(fm)

# canopy edges: 0.35 m in front of the figure (between camera and figure) and 2.4 m behind him; 3.0 m up
fx.drips_edge((-1.2, -0.35, 3.0), (1.2, -0.35, 3.0), n=16, fall=3.0, seed=5)
fx.drips_edge((-2.5, 2.4, 3.0), (2.5, 2.4, 3.0), n=22, fall=3.0, seed=6)
fx.rain(dict(lo=(-8, -6), hi=(8, 10)), intensity=1.5, wind=(0.14, 0.0), ground=0.0, near=(0.0, -1.0, 4.0))

# camera 1.2 m from the figure, chest height, looking through the drip line
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 35
core.link(cam, "Scene")
cam.location = (0.0, -1.2, 1.3)
cam.rotation_euler = (math.radians(90), 0, 0)
sc.camera = cam

out = ROOT / "output" / "_staging" / "kitfix" / "drips"
out.mkdir(parents=True, exist_ok=True)
for f in (int(x) for x in a.frames.split(",")):
    sc.frame_set(f)
    sc.render.filepath = str(out / f"drips_{a.tag}_{f:02d}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)
