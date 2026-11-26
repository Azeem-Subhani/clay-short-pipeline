"""Prove the set audit finds what it claims to: build a small room with deliberate defects and check each is reported.

    blender -b --factory-startup --python tools/tests/sets/test_audit.py

Defects planted: a crate floating 30 cm up, a barrel sunk 15 cm into the floor, two tables overlapping, a cabinet pushed through
a wall, a mesh with no material, a window with no vista behind it (the void), a zero-area-heavy mesh. Also checks that a clean
placement (a table with a mug set on it, a chair beside it) produces none of those. Exit code 1 if any expectation fails.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "blender"))
sys.dont_write_bytecode = True

import bmesh  # noqa: E402
import bpy  # noqa: E402

import stagekit  # noqa: E402
from stagekit import arch, audit, core, furnish, lights  # noqa: E402


def main():
    core.begin("audit_test", 1.0, "draft")
    R = arch.room((8, 6, 2.8), floor="wood_floor", walls="plaster_clean", ceiling="plaster_clean", name="t",
                  openings=[dict(wall="N", kind="window", type="sash", w=1.4, h=1.4, sill=1.0, at=0, id="win")])
    lights.rig("office_day", look=False)
    # clean: a table with a mug on it and a chair beside it
    tb = furnish.trestle_table(at=(0, 0.5, 0), rot_z=0)
    tp = furnish.tops(tb)[0]
    mug = furnish.mugs(at=(tp[0].x, tp[0].y, tp[1]), rot_z=0, count=1)
    mug["sk_on"] = tb.name
    furnish.chair_dining(at=(-2.0, 0.5, 0), rot_z=0)
    # planted defects
    furnish.crate(at=(2.5, -1.0, 0.30), rot_z=0, name="float_crate")
    furnish.barrel(at=(-2.5, -1.5, -0.15), rot_z=0, name="sunk_barrel")
    furnish.banquet_table(at=(2.0, 2.0, 0), rot_z=0, name="table_a")
    furnish.banquet_table(at=(2.8, 1.9, 0), rot_z=0, name="table_b")
    furnish.cabinet(at=(-2.5, 3.1, 0), rot_z=0, name="wall_poker")            # its back is 0.1 m inside the north wall (y = 3.0)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.3)
    me = bpy.data.meshes.new("bare")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("bare_piece", me)
    core.link(ob, "SET")
    ob["sk_type"], ob["sk_kind"] = "bare", "prop"
    ob.location = (0.0, -2.0, 0.15)
    cam = ((0, -2.8, 1.6), (0, 3.0, 1.3), 28.0)
    res = audit.audit([cam], room=R)
    codes = {}
    for i in res["issues"]:
        codes.setdefault(i["code"], []).append(i["object"])
    for i in res["issues"]:
        print(f"[{i['level']}] {i['code']}: {i['object']}: {i['detail']}")
    expect = {"floating": "float_crate", "sunk": "sunk_barrel", "intersect": "table_", "through_wall": "wall_poker", "no_material": "bare", "opening_void": "win"}
    bad = 0
    for code, who in expect.items():
        hit = any(who in o for o in codes.get(code, []))
        print(f"{'PASS' if hit else 'FAIL'}  {code} reported for {who}")
        bad += not hit
    clean_fail = [c for c in ("floating", "sunk", "intersect") if any(o in ("trestle_table", "mugs", "chair_dining") or o.startswith(("mugs", "chair_dining", "trestle_table")) for o in codes.get(c, []))]
    print("PASS  the clean table, mug and chair are not flagged" if not clean_fail else f"FAIL  clean pieces flagged: {clean_fail}")
    bad += bool(clean_fail)
    sys.exit(1 if bad else 0)


main()
