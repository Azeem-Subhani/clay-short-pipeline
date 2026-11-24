"""Every wardrobe piece on one character, three-quarter and front view (does the old wardrobe still fit old and new cast?).
blender -b --factory-startup --python wardrobe_sheet.py -- --char Farmer --out <abs dir> [--pack <blend>]"""
import argparse, os, sys
from pathlib import Path
import bpy
_W = Path(__file__).resolve().parents[2]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[3]
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True); ap.add_argument("--out", required=True); ap.add_argument("--pack", default=None)
ap.add_argument("--pipeline", default=str(_PIPE)); ap.add_argument("--px", type=int, default=360)
a = ap.parse_args(argv)
if a.pack:
    os.environ["CAST_PACK"] = a.pack
os.environ["SHORTS_PROJECT"] = a.pipeline
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit
from stagekit import cast, wardrobe
items = list(wardrobe.ITEMS)
out = Path(a.out).resolve() / a.char
out.mkdir(parents=True, exist_ok=True)
for it in items:
    shot = stagekit.begin("wardrobe", 2, "draft")
    sc = bpy.context.scene
    sc.render.resolution_x = sc.render.resolution_y = a.px; sc.render.resolution_percentage = 100; sc.eevee.taa_render_samples = 8
    w = bpy.data.worlds.new("W"); w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.87, 0.8, 1); sc.world = w
    sc.view_settings.view_transform = "Standard"
    cd = bpy.data.cameras.new("cam"); cd.type = "ORTHO"; cd.ortho_scale = 2.3
    cam = bpy.data.objects.new("cam", cd); sc.collection.objects.link(cam); cam.location = (0, -10, 0.97); cam.rotation_euler = (1.5707963, 0, 0); sc.camera = cam
    cast.look("#FFFFFF", lit=0.0)
    act = cast.actor("x", a.char, at=(0, 0), costume={"wear": [{"item": it}]})
    for v in ("3q", "front"):
        act.view(v)
        act.pose("wave" if v == "3q" else "rest", 0.0, 0.0)          # the wave brings a hand up to the hat: it must stay in front
        sc.frame_set(2)
        sc.render.filepath = str(out / f"{it}__{v}.png")
        bpy.ops.render.render(write_still=True)
print("WARDROBE_DONE", a.char, len(items))
