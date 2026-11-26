"""Build every registered furniture piece on a grid in front of a wall, label it, and render contact sheets.

    blender -b --factory-startup --python tools/tests/sets/test_furnish.py -- --out <dir> [--only name,name] [--per 20]

Prints one line per piece: name, size (w x d x h m), mesh objects, triangles, build time. Exit code 1 if any piece fails to build,
has a zero size, or has no material on a mesh.
"""
import math
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "blender"))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stagekit  # noqa: E402,F401
from stagekit import arch, core, furnish, lights  # noqa: E402


def tri_count(root):
    dg = bpy.context.evaluated_depsgraph_get()
    n = 0
    objs = 0
    for o in [root, *root.children_recursive]:
        if o.type == "MESH":
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            n += sum(len(p.vertices) - 2 for p in me.polygons)
            ev.to_mesh_clear()
            objs += 1
    return objs, n


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = Path(argv[argv.index("--out") + 1]).resolve()
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    per = int(argv[argv.index("--per") + 1]) if "--per" in argv else 15
    out.mkdir(parents=True, exist_ok=True)
    names = [n for n in sorted(furnish.REGISTRY) if not only or n in only]
    bad = 0
    sheets = [names[i:i + per] for i in range(0, len(names), per)]
    for si, group in enumerate(sheets):
        core.begin("t", 1.0, "preview")
        sc = bpy.context.scene
        lights.rig("day_soft", sun_from=20, look=False, rim=0.3)
        cols = 5
        sp = 3.0
        rows = math.ceil(len(group) / cols)
        wall = arch.Parts("backwall", kind="shell")
        wall.box((cols * sp + 2, 0.1, 5), (0, 0.06, 0), "plaster_clean", bevel=0.0)
        wall.box((cols * sp + 6, rows * sp + 6, 0.1), (0, -rows * sp / 2 - 1, -0.1), "wood_floor", bevel=0.0)
        wall.build(at=(0, 0, 0), recentre=False)
        for i, n in enumerate(group):
            meta = furnish.REGISTRY[n]
            c, r = i % cols, i // cols
            x = (c - (cols - 1) / 2) * sp
            y = -r * sp
            z = meta["mount_z"] if meta["mount_z"] is not None else (3.6 if n == "chandelier" else 3.0 if n == "ceiling_light_panel" else 0.0)
            t0 = time.perf_counter()
            try:
                ob = furnish.make(n, at=(x, y, z))
            except Exception:
                traceback.print_exc()
                print(f"FAIL {n}")
                bad += 1
                continue
            dt = time.perf_counter() - t0
            bpy.context.view_layer.update()
            objs, tris = tri_count(ob)
            w, d, h = furnish.footprint(ob)
            flag = ""
            if min(w, h) <= 0.01:
                flag = "  <-- ZERO SIZE"
                bad += 1
            for o in [ob, *ob.children_recursive]:
                if o.type == "MESH" and not o.data.materials:
                    flag += f"  <-- NO MATERIAL on {o.name}"
                    bad += 1
            print(f"{n:22s} {w:5.2f} x {d:4.2f} x {h:4.2f} m  meshes {objs:3d}  tris {tris:6d}  {dt * 1000:5.0f} ms  tops {len(ob.get('sk_tops', []))}  lights {ob.get('sk_nlights', 0)}{flag}")
            lb = bpy.data.curves.new("lb", "FONT")
            lb.body = n
            lb.size = 0.16
            lb.align_x = "CENTER"
            lo = bpy.data.objects.new("lb", lb)
            core.link(lo, "FX")
            lo.location = (x, y - 0.9, 0.01)
            lo.rotation_euler = (0, 0, 0)
            lb.materials.append(__import__("stagekit").mat.solid("#101010", 0.9))
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        core.link(cam, "RIG")
        sc.camera = cam
        cam.data.lens = 50
        cam.data.clip_end = 200
        cx, cy = 0.0, -(rows - 1) * sp / 2
        cam.data.lens = 32
        pos = Vector((cx, cy - 11.0 - rows * 1.3, 7.0 + rows * 0.8))
        cam.location = pos
        cam.rotation_euler = (Vector((cx, cy + 0.2, 1.0)) - pos).to_track_quat("-Z", "Y").to_euler()
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 900, 100
        sc.render.filepath = str(out / f"pieces_{si + 1}.png")
        bpy.ops.render.render(write_still=True)
        print("sheet", si + 1, "->", sc.render.filepath)
    sys.exit(1 if bad else 0)


main()
