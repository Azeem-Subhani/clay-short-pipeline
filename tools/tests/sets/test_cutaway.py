"""Prove arch.cutaway: one enclosed room (the throne room) seen from outside on all four sides, the wall nearest each camera hidden.

    blender -b --factory-startup --python tools/tests/sets/test_cutaway.py -- --out <dir> [--set examples/sets/set_throne_room.py]

Writes <out>/side_N.png ... side_W.png and sheet.png (2 x 2). Prints which parts were hidden for each camera. Also checks the
keyed form: arch.cutaway(room, cam, at_frame=(f0, f1)) hides at f0 and brings the walls back after f1 (printed as pass / fail).
"""
import importlib.util
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.dont_write_bytecode = True

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import set_preview as sp  # noqa: E402
import stagekit  # noqa: E402
from stagekit import arch, core  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = Path(argv[argv.index("--out") + 1]).resolve()
    setp = Path(argv[argv.index("--set") + 1]) if "--set" in argv else ROOT / "examples" / "sets" / "set_throne_room.py"
    out.mkdir(parents=True, exist_ok=True)
    stagekit.begin("cutaway", 4.0, "preview")
    sc = bpy.context.scene
    sc.render.resolution_percentage = 50
    mod = sp.load_set(setp)
    S = mod.build_set()
    R = S["room"]
    cam = sp.mk_camera()
    c = Vector((R.at[0], R.at[1], 1.5))
    w, d, h = R.size
    far = max(w, d) * 1.5
    views = {
        "N": (Vector((c.x + 2.0, c.y + d / 2 + far * 0.5, 5.0)), 22.0),
        "S": (Vector((c.x - 2.0, c.y - d / 2 - far * 0.5, 5.0)), 22.0),
        "E": (Vector((c.x + w / 2 + far * 0.5, c.y - 2.0, 5.5)), 22.0),
        "W": (Vector((c.x - w / 2 - far * 0.5, c.y + 2.0, 5.5)), 22.0),
    }
    imgs = []
    for k, (pos, lens) in views.items():
        sp.aim(cam, pos, c + Vector((0, 0, 1.0)), lens)
        hide = arch.cutaway(R, cam)
        sc.render.filepath = str(out / f"side_{k}.png")
        t0 = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(f"side {k}: camera ({pos.x:.0f}, {pos.y:.0f}, {pos.z:.0f}) hidden {sorted(hide)}  render {time.perf_counter() - t0:.1f}s")
        imgs.append(out / f"side_{k}.png")
    sp.tile(imgs, out / "sheet.png", cols=2)
    # keyed cutaway: hidden from frame 10 to 20, back from 21
    arch.cutaway(R, Vector((0, -40, 3)), at_frame=(10, 20))
    wall = R.S
    states = {}
    for f in (5, 10, 15, 20, 21, 30):
        sc.frame_set(f)
        states[f] = wall.hide_render
    ok = (not states[5]) and states[10] and states[15] and states[20] and (not states[21]) and (not states[30])
    print("keyed cutaway frames (S wall hide_render):", states, "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


main()
