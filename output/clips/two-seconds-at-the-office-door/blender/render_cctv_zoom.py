"""Render the lobby security camera's "digital zoom" on the doorway to assets/cctv_frame_zoom.png (1280 x 720): the same camera position,
height and footage card as render_cctv_frame.py (grey-green veil, scanlines, "LOBBY CAM 2   MON 08:47" bar, REC dot, all burned in), with a
long lens aimed at Maya holding the open right door leaf and the stranger walking in past her with his coffees, the two figures filling most of
the picture height. A small "ZOOM x4" tag sits under the REC dot and a thin red ring circles her hand on the door (a training-slide mark).
sh08 (training-room screen) and sh06 (guard's laptop) show this file with the screen look "clean".

    blender -b --factory-startup --python output/clips/two-seconds-at-the-office-door/blender/render_cctv_zoom.py -- [--out <png>]
        [--t 0.30] [--fill 0.80] [--percent 100] [--no-ring]
"""
import argparse
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIP = HERE.parent
ROOT = CLIP.parent.parent.parent
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import run_shot  # noqa: E402

ZOOM_TAG = "ZOOM x4"
T_ZOOM = 0.0           # sh03 time of the frame (the first frame of the shot: the door wide, Maya holding it)
# Fix round 2: at the security camera's angle her hand on the leaf edge sat exactly where his coffee carrier passes, so the still read as
# her taking a coffee. For this still only (a frame "from the clip", consistent in look and place with cctv_frame.png): he is a step further
# back, in the threshold, walking in; she stands a little further from the leaf with her arm out, her hand gripping the pull handle at
# shoulder height, clear of his cups. The red ring circles that hand.
ST_SHIFT = (0.0, -1.0)                  # the stranger, metres in x, y (back into the doorway)
MAYA_SHIFT = (0.22, 0.04)               # Maya, metres in x, y (away from the leaf, so her arm reaches out to it)
HANDLE = (-0.953, 0.09, 1.22)           # leaf-local: the right leaf's pull handle, on her face of the glass, at shoulder height


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(CLIP / "assets" / "cctv_frame_zoom.png"))
    ap.add_argument("--t", type=float, default=None, help="shot time of the frame (default sh03.T_FRAME)")
    ap.add_argument("--fill", type=float, default=0.74, help="share of the picture height the two figures fill")
    ap.add_argument("--aim_dz", type=float, default=0.10, help="shift of the aim point in z (m)")
    ap.add_argument("--percent", type=int, default=100)
    ap.add_argument("--no-ring", action="store_true")
    ap.add_argument("--quality", default="final")
    a = ap.parse_args(argv)
    shot = run_shot.build_shot_scene(CLIP, "sh03", a.quality)
    import sh03
    sh03.set_light_for_stills()
    from stagekit import core
    sc = bpy.context.scene
    t = T_ZOOM if a.t is None else a.t
    f = shot.f(t)
    maya, st = shot.actors["maya"], shot.actors["stranger"]
    from stagekit import furnish
    for actor, (dx, dy), nm in ((st, ST_SHIFT, "ZOOM_shift_st"), (maya, MAYA_SHIFT, "ZOOM_shift_maya")):
        e = bpy.data.objects.new(nm, None)
        sc.collection.objects.link(e)
        actor.stage.parent = e
        e.location = (dx, dy, 0.0)
    bpy.context.view_layer.update()
    doors = next(o for o in bpy.data.objects if o.get("sk_type") == "glass_doors" and o.parent is None)
    grip = sh03.leaf_point(furnish.part(doors, "leaf_R"), HANDLE, "ZOOM_handle")
    maya.hand("R", "grip", t, 0.0)
    maya.reach("R", grip, t, 0.0)
    maya.reach("R", grip, t + 0.3, 0.0)
    sc.frame_set(f)
    hand = maya.palm["R"].matrix_world.translation.copy()
    print(f"[cctv_zoom] handle at {tuple(round(c, 3) for c in grip.matrix_world.translation)}, palm at {tuple(round(c, 3) for c in hand)}, "
          f"gap {(grip.matrix_world.translation - hand).length:.3f} m")
    pts = [maya.top.point(), maya.feet.point(), st.top.point(),
           st.feet.point(), hand]
    pts = [Vector(p) for p in pts]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    aim = (lo + hi) / 2 + Vector((0, 0, a.aim_dz))
    pos = Vector(sh03.CCTV_POS)

    data = bpy.data.cameras.new("CCTV_ZOOM")
    data.sensor_fit = "AUTO"
    data.sensor_width = 36.0
    data.clip_start = 0.05
    ob = bpy.data.objects.new("CCTV_ZOOM", data)
    sc.collection.objects.link(ob)
    ob.location = pos
    ob.rotation_euler = (aim - pos).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1280, 720, a.percent
    sc.camera = ob
    # lens: the figures' extent across the view direction, at their distance, fills `fill` of the picture height (sensor height 20.25 mm)
    bpy.context.view_layer.update()
    inv = ob.matrix_world.inverted()
    loc = [inv @ p for p in pts]
    depth = -sum(p.z for p in loc) / len(loc)
    ext_y = max(p.y for p in loc) - min(p.y for p in loc)
    ext_x = max(p.x for p in loc) - min(p.x for p in loc)
    sh = 36.0 * 720 / 1280
    lens = min(depth * sh * a.fill / ext_y, depth * 36.0 * 0.9 / max(ext_x, 1e-3))
    data.lens = lens
    sh03.cctv_look(ob, lens, 1280, 720, frames=None, name="CCTV_LOOK_ZOOM")
    root = bpy.data.objects["CCTV_LOOK_ZOOM"]
    card = bpy.data.objects["CCTV_LOOK_ZOOM_card"]
    vs = [v.co for v in card.data.vertices]
    W = max(v.x for v in vs) - min(v.x for v in vs)
    H = max(v.y for v in vs) - min(v.y for v in vs)
    white = bpy.data.materials["CCTV_LOOK_ZOOM_white"]
    red = bpy.data.materials["CCTV_LOOK_ZOOM_red"]
    bar_h = 0.085
    th = bar_h * H * 0.55
    extra = []
    # "ZOOM x4" under the REC dot, right-aligned, on a small dark plate
    cu = bpy.data.curves.new("CCTV_ZOOM_tag", "FONT")
    cu.body = ZOOM_TAG
    cu.size = th * 0.85
    cu.align_x, cu.align_y = "RIGHT", "CENTER"
    cu.materials.append(white)
    tag = bpy.data.objects.new("CCTV_ZOOM_tag", cu)
    core.link(tag, "FX")
    tag.parent = root
    tag.location = (W / 2 - W * 0.03, H / 2 - H * bar_h * 1.75, 0.0004)
    extra.append(tag)
    if not a.no_ring:
        u, v, _ = world_to_camera_view(sc, ob, hand)
        r_out, r_in = H * 0.09, H * 0.09 - H * 0.014
        me = bpy.data.meshes.new("CCTV_ZOOM_ring")
        n = 64
        verts = [(math.cos(2 * math.pi * k / n) * r, math.sin(2 * math.pi * k / n) * r, 0) for r in (r_out, r_in) for k in range(n)]
        faces = [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
        me.from_pydata(verts, [], faces)
        me.materials.append(red)
        ring = bpy.data.objects.new("CCTV_ZOOM_ring", me)
        core.link(ring, "FX")
        ring.parent = root
        ring.location = ((u - 0.5) * W, (v - 0.5) * H, 0.0003)
        extra.append(ring)
        print(f"[cctv_zoom] hand at u={u:.3f} v={v:.3f}")
    for o in extra:
        o.hide_viewport = True
        try:
            o.visible_shadow = False
        except (AttributeError, TypeError):
            pass
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sc.render.use_stamp = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    print(f"[cctv_zoom] frame {f} (t={t}s) lens {lens:.1f} (x{lens / sh03.CCTV_LENS:.1f}) aim {tuple(round(c, 2) for c in aim)} -> {out}")


main()
