"""Render the lobby security camera's frame of sh03 to assets/cctv_frame.png (1280 x 720): the same camera pose, lens and footage card
(grey-green veil, scanlines, "LOBBY CAM 2   MON 08:47" bar, REC dot, all burned in) as sh03's cctv_pov view, at sh03.T_FRAME, when Maya holds
the glass door and the stranger steps in past her. sh06 (the guard's laptop) and sh08 (the training-room screen) show this file as it is
(screen look "clean": the footage look is already in the picture).

    blender -b --factory-startup --python output/clips/two-seconds-at-the-office-door/blender/render_cctv_frame.py -- [--out <png>] [--lens 18]
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIP = HERE.parent
ROOT = CLIP.parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import run_shot  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(CLIP / "assets" / "cctv_frame.png"))
    ap.add_argument("--lens", type=float, default=None)
    ap.add_argument("--quality", default="final")
    a = ap.parse_args(argv)
    shot = run_shot.build_shot_scene(CLIP, "sh03", a.quality)
    import sh03
    sh03.set_light_for_stills()
    sc = bpy.context.scene
    lens = a.lens or sh03.CCTV_LENS
    data = bpy.data.cameras.new("CCTV_16x9")
    data.lens = lens
    data.sensor_fit = "AUTO"
    data.sensor_width = 36.0
    data.clip_start = 0.05
    ob = bpy.data.objects.new("CCTV_16x9", data)
    sc.collection.objects.link(ob)
    ob.location = sh03.CCTV_POS
    ob.rotation_euler = (Vector(sh03.CCTV_AIM) - Vector(sh03.CCTV_POS)).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1280, 720, 100
    sh03.cctv_look(ob, lens, 1280, 720, frames=None, name="CCTV_LOOK_16x9")
    sc.camera = ob
    f = shot.f(sh03.T_FRAME)
    sc.frame_set(f)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sc.render.use_stamp = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    print(f"[cctv_frame] frame {f} (t={sh03.T_FRAME}s) lens {lens} -> {out}")


main()
