"""Smoke test for stagekit.arch: a room with every kind of door and window, a vista, a cutaway, a free wall, a house front, an
exterior street kit; rendered at draft size.

    blender -b --factory-startup --python tools/tests/sets/test_arch.py -- --out <dir>

Prints what was hidden for each camera. Exit code 1 if anything failed to build.
"""
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "blender"))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import stagekit  # noqa: E402,F401
from stagekit import arch, core, lights  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = Path(argv[argv.index("--out") + 1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    core.begin("t", 1.0, "draft")
    t0 = time.perf_counter()
    R = arch.room((9, 7, 3.0), floor="wood_floor", walls="plaster_warm", ceiling="plaster_clean", name="r", openings=[
        dict(wall="N", kind="window", type="sash", w=1.2, h=1.5, sill=0.95, at=-2.5, id="w1"),
        dict(wall="N", kind="window", type="lattice", w=1.4, h=1.5, sill=0.95, at=0.0, id="w2", shutters=True),
        dict(wall="N", kind="window", type="arched", w=1.0, h=1.9, sill=0.9, at=2.5, id="w3"),
        dict(wall="S", kind="door", type="panel", w=1.0, h=2.1, at=-2.0, id="d1", open=70),
        dict(wall="S", kind="door", type="double", w=2.0, h=2.4, at=1.5, id="d2", open=40),
        dict(wall="E", kind="door", type="plank", w=1.1, h=2.1, at=-1.5, id="d3"),
        dict(wall="E", kind="door", type="arched", w=1.2, h=2.4, at=1.5, id="d4", arched=True, open=30),
        dict(wall="W", kind="window", type="office", w=2.4, h=1.5, sill=0.9, at=0.0, id="w4"),
        dict(wall="W", kind="door", type="glass", w=1.0, h=2.1, at=2.5, id="d5"),
    ])
    for W, k in (("N", "hills"), ("W", "city_day"), ("S", "garden"), ("E", "street")):
        arch.vista(R, W, k)
    lights.interior("office_day", key_from=R.openings["w2"], key_power=1500, fill=dict(at=(0, 0, 2.7), size=(7, 5), power=120))
    # a free wall, columns, stairs, a dais, a fireplace, a house front, a street kit
    fw = arch.wall((-4, -9), (0, -9), 2.6, 0.2, [dict(kind="door", type="panel", w=0.9, h=2.05, at=0.0, id="gate"), dict(kind="window", type="sash", w=0.8, h=1.0, at=1.4, id="peep")])
    arch.column("fluted", 3.0, 0.3, at=(1.5, -9, 0))
    arch.stairs(2.4, 1.0, 6, 1.4, at=(3.5, -10, 0), rail="dark_timber")
    arch.fireplace(at=(5, -9, 0))
    arch.house_front(2, "timber", at=(-8, -14, 0), awning="#B3322C")
    arch.house_front(3, "brick", at=(2, -14, 0))
    arch.street(30, 6, at=(0, -19, 0))
    arch.market_stall(at=(-5, -17, 0))
    arch.well(at=(6, -17, 0))
    arch.lamp_post(at=(8, -16, 0))
    arch.fence(at=(-10, -9, 0))
    arch.skyline(60, 30, at=(0, -22, 0))
    print("built in %.1fs" % (time.perf_counter() - t0), "objects", len(bpy.data.objects), "free wall openings", sorted(fw["openings"]))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    core.link(cam, "RIG")
    bpy.context.scene.camera = cam
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 540, 960, 100

    def shot(name, pos, aim, lens=22):
        cam.location = pos
        cam.data.lens = lens
        cam.rotation_euler = (Vector(aim) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
        hide = arch.cutaway(R, cam)
        sc.render.filepath = str(out / f"{name}.png")
        t1 = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(name, "hidden", sorted(hide), "render %.1fs" % (time.perf_counter() - t1))

    shot("a_from_s", (0.5, -3.1, 1.6), (0, 3, 1.4), 20)
    shot("b_from_n", (-0.5, 3.1, 1.6), (0, -3, 1.2), 20)
    shot("c_from_outside_s", (0, -12, 3.5), (0, 0, 1.2), 30)
    shot("d_street", (0, -12.5, 2.0), (0, -17, 2.5), 24)


main()
