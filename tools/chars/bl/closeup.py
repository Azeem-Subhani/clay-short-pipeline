"""Close-up stills of one character in given poses (ink inspection).
blender -b --factory-startup --python closeup.py -- --char X --pack <blend> --out <abs dir> --shots "pose:view:face,..." [--px 900] [--zoom 1.5] [--cz 0.95]"""
import argparse, os, sys
from pathlib import Path
import bpy
_W = Path(__file__).resolve().parents[2]
_PIPE = (_W / "clay-short-pipeline") if (_W / "clay-short-pipeline").exists() else Path(__file__).resolve().parents[3]
argv = sys.argv[sys.argv.index("--") + 1:]
ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True); ap.add_argument("--out", required=True); ap.add_argument("--shots", required=True)
ap.add_argument("--px", type=int, default=900); ap.add_argument("--zoom", type=float, default=1.5); ap.add_argument("--cz", type=float, default=0.95)
ap.add_argument("--pipeline", default=str(_PIPE)); ap.add_argument("--pack", default=None)
ap.add_argument("--scale", type=float, default=1.0); ap.add_argument("--tag", default="")
a = ap.parse_args(argv)
if a.pack:
    os.environ["CAST_PACK"] = a.pack
os.environ["SHORTS_PROJECT"] = a.pipeline
sys.path.insert(0, str(Path(a.pipeline) / "tools" / "blender"))
import stagekit
from stagekit import cast
shots = [x.split(":") for x in a.shots.split(",")]
shot = stagekit.begin("closeup", len(shots) * 0.5 + 1, "draft")
sc = bpy.context.scene
sc.render.resolution_x = sc.render.resolution_y = a.px; sc.render.resolution_percentage = 100
sc.eevee.taa_render_samples = 16
w = bpy.data.worlds.new("W"); w.use_nodes = True; w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.87, 0.8, 1); sc.world = w
sc.view_settings.view_transform = "Standard"
cd = bpy.data.cameras.new("cam"); cd.type = "ORTHO"; cd.ortho_scale = a.zoom
cam = bpy.data.objects.new("cam", cd); sc.collection.objects.link(cam); cam.location = (0, -10, a.cz * a.scale); cam.rotation_euler = (1.5707963, 0, 0); sc.camera = cam
cast.look("#FFFFFF", lit=0.0)
act = cast.actor("x", a.char, at=(0, 0), scale=a.scale)
out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
t = 0.0; jobs = []
for pose, view, face in shots:
    act.view(view, t); act.face(face, t); act.pose("rest", t, 0.0); act.lean(0, t, 0.0); act.tilt_head(0, t, 0.0); act.legs(0, 0, t, 0.0)
    if pose.startswith("arm="):          # arm=raise/bend[/plane]  for both arms
        v = pose[4:].split("/")
        for s_ in "LR":
            act.arm(s_, float(v[0]), float(v[1]), t, 0.0, **({"plane": v[2]} if len(v) > 2 else {}))
    else:
        act.pose(pose, t, 0.0)
    jobs.append((shot.f(t) + 2, out / f"{a.char}{a.tag}__{pose.replace('/', '_').replace('=', '')}__{view}_{face}.png")); t += 0.5
for fr, path in jobs:
    sc.frame_set(fr); sc.render.filepath = str(path); bpy.ops.render.render(write_still=True)
print("CLOSEUP_DONE", len(jobs))
