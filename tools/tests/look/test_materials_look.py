"""Tests of the material look: the clean ceiling tile, aspect-correct scans, graded scans, the warm-grey carpet, anti-tiling and wet ground.

    py -3 tools/tests/look/test_materials_look.py --plain          # the catalogue only, no Blender
    blender -b --factory-startup --python tools/tests/look/test_materials_look.py     # everything (go through the lock wrapper)

Inside Blender it builds materials, a big and a small room, and a wet pavement with puddles; no rendering.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.dont_write_bytecode = True
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def jpeg_size(p: Path):
    d = p.read_bytes()
    i = 2
    while i < len(d):
        if d[i] != 0xFF:
            i += 1
            continue
        m = d[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", d[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    return None


def plain():
    cat = json.loads((ROOT / "library" / "materials" / "catalog.json").read_text(encoding="utf-8"))["surfaces"]
    ct = cat["ceiling_tile"]
    check("ceiling_tile is its own procedural kind (not the stone blocks)", ct["procedural"]["kind"] == "ceiling", ct["procedural"]["kind"])
    check("ceiling_tile keeps its period tag", ct["era"] == ["modern"])
    check("painted_wall normal strength 0.3", cat["painted_wall"].get("grade", {}).get("normal") == 0.3)
    for n in ("plaster_clean", "carpet_grey"):
        g = cat[n].get("grade", {})
        check(f"{n} has a grade with normal and saturation", "normal" in g and "saturation" in g, json.dumps(g))
    check("carpet_grey carries the warm-grey tint", cat["carpet_grey"].get("tint", "").upper() == "#CFC8BD", str(cat["carpet_grey"].get("tint")))
    check("castle_stone grade untouched", cat["castle_stone"]["grade"]["normal"] == 0.7 and cat["castle_stone"]["grade"]["flatten"] == 0.5)
    # the scans on disk: list the non-square ones (mapping must follow them)
    lib = ROOT / "library" / "materials" / "ambientcg"
    odd = {}
    for d in sorted(lib.iterdir()) if lib.is_dir() else []:
        c = next(iter(d.glob("*_Color.jpg")), None)
        if c:
            s = jpeg_size(c)
            if s and s[0] != s[1]:
                odd[d.name] = s
    print("non-square scans:", odd)
    check("non-square scans are all 2:1 (the aspect fix expects it, any ratio works)", all(w == 2 * h for w, h in odd.values()))


def blender_part():
    sys.path.insert(0, str(ROOT / "tools" / "blender"))
    import bpy
    from stagekit import arch, core, dress, mat

    core.begin("t_mat", 1.0, "draft")

    def nodes(m, t):
        return [n for n in m.node_tree.nodes if n.type == t]

    # ---- 1 the ceiling tile
    m = mat.surface("ceiling_tile")
    check("ceiling tile source", m.get("sk_source") == "procedural:ceiling", str(m.get("sk_source")))
    check("ceiling tile has no stain or damp nodes", not nodes(m, "NEW_GEOMETRY") and not nodes(m, "SEPXYZ") and len(nodes(m, "TEX_NOISE")) == 1)
    br = nodes(m, "TEX_BRICK")
    check("ceiling tile is one 0.6 m grid", len(br) == 1 and abs(br[0].inputs["Brick Width"].default_value - 0.6) < 1e-6 and abs(br[0].inputs["Row Height"].default_value - 0.6) < 1e-6)
    lt, ls = br[0].inputs["Color1"].default_value, br[0].inputs["Mortar"].default_value
    check("seams are slightly darker, not dark", 0.6 < ls[0] / lt[0] < 0.85, f"{ls[0] / lt[0]:.2f}")
    # albedo: #E9E4DA at half, linear
    want = core.hex_rgba("#E9E4DA")
    check("tile colour is #E9E4DA at half albedo", all(abs(lt[i] - want[i] * 0.5) < 1e-4 for i in range(3)), str(tuple(round(v, 3) for v in lt[:3])))
    check("tile roughness 0.9", abs(next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Roughness"].default_value - 0.9) < 1e-6)

    # ---- 2 aspect
    wall = mat.surface("painted_wall")
    sc_ = nodes(wall, "MAPPING")[0].inputs["Scale"].default_value
    check("2:1 scan maps with a 2:1 tile (v scale doubled)", abs(sc_[0] - 0.5) < 1e-6 and abs(sc_[1] - 1.0) < 1e-6, str(tuple(sc_)))
    check("the material records the scan aspect", abs(wall.get("sk_aspect", 0) - 2.0) < 1e-6)
    car = mat.surface("carpet_grey")
    sc2 = nodes(car, "MAPPING")[0].inputs["Scale"].default_value
    check("a square scan keeps equal u and v scale", abs(sc2[0] - sc2[1]) < 1e-9 and abs(sc2[0] - 1.0) < 1e-6, str(tuple(sc2)))
    for name, aid in (("castle_stone", "Bricks100"), ("concrete", "Concrete034"), ("parquet", "WoodFloor043")):
        if mat.downloaded(aid):
            s3 = nodes(mat.surface(name), "MAPPING")[0].inputs["Scale"].default_value
            check(f"{name} ({aid}) maps 2:1", abs(s3[1] / s3[0] - 2.0) < 1e-6, str(tuple(s3)))

    # ---- 3 grade from the catalogue reaches the material
    nm = nodes(wall, "NORMAL_MAP")[0].inputs["Strength"].default_value
    hs = nodes(wall, "HUE_SAT")[0].inputs["Saturation"].default_value
    check("painted_wall normal strength 0.3 and saturation 0.9", abs(nm - 0.3) < 1e-6 and abs(hs - 0.9) < 1e-6, f"{nm} {hs}")
    pl = mat.surface("plaster_clean")
    check("plaster_clean normal 0.4", abs(nodes(pl, "NORMAL_MAP")[0].inputs["Strength"].default_value - 0.4) < 1e-6)
    check("carpet_grey normal 0.6", abs(nodes(car, "NORMAL_MAP")[0].inputs["Strength"].default_value - 0.6) < 1e-6)
    cs = mat.surface("castle_stone")
    check("castle_stone still graded as before", abs(nodes(cs, "NORMAL_MAP")[0].inputs["Strength"].default_value - 0.7) < 1e-6)

    # ---- 4 warm-grey carpet
    tint = [n for n in car.node_tree.nodes if n.type == "MIX" and n.blend_type == "MULTIPLY" and tuple(round(v, 3) for v in n.inputs[7].default_value[:3]) == tuple(round(v, 3) for v in core.hex_rgba("#CFC8BD")[:3])]
    check("carpet_grey multiplies by #CFC8BD", len(tint) == 1)
    cool = mat.surface("carpet_grey", tint="#C4CACF")
    check("a set's own floor_tint still wins", cool is not car)

    # ---- 5 anti-tiling
    big = arch.room((9.5, 8.0, 2.8), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", name="big")
    fm = big.floor.children[0].data.materials[0]
    check("a big floor carries the macro variation", fm.get("sk_anti_tile") == 1 and fm.get("sk_surface") == "carpet_grey", fm.name)
    check("... and keeps its surface name", big.floor.get("sk_surface") == "carpet_grey")
    small = arch.room((3.0, 3.0, 2.6), at=(30, 0), floor="carpet_grey", walls="painted_wall", ceiling="ceiling_tile", name="small")
    check("a small floor does not", not small.floor.children[0].data.materials[0].get("sk_anti_tile"))
    noise = [n for n in fm.node_tree.nodes if n.type == "TEX_NOISE"]
    check("the variation is one low-frequency noise at a few metres", len(noise) == 1 and noise[0].inputs["Scale"].default_value <= 0.5)
    amp = mat.ANTI_TILE
    check("the variation is a few percent", amp["value"] <= 0.06 and amp["rough"] <= 0.06, str(amp))
    wl = big.N.data.materials[0]
    check("a long wall (over 4 m) also gets it", wl.get("sk_anti_tile") == 1)

    # ---- 6 wet ground and puddles
    pav = arch.Parts("pave", "SET", "pavement", kind="shell")
    pav.box((18.0, 5.0, 0.3), (0, -3.0, -0.3), "paving_wet", bevel=0.0)
    pob = pav.build(at=(0, 0, 0), recentre=False)
    wm = mat.surface("paving_wet")
    check("paving_wet is made by wetten and has the puddle mask", wm.get("sk_wet") and wm.node_tree.nodes.get("sk_puddle_range") is not None)
    rng = wm.node_tree.nodes["sk_puddle_range"]
    a0 = rng.inputs["From Min"].default_value
    check("puddle_boost widens the patches", mat.puddle_boost(wm, 1.0) and rng.inputs["From Min"].default_value < a0 - 0.05)
    check("puddle_boost on a dry material says so", mat.puddle_boost(mat.surface("carpet_grey"), 1.0) is False)
    # the Dresser: a minimal one is awkward to make; use the theme entry the street uses
    D = _dresser(dress)
    if D is not None:
        got = D.floor_detail("puddles", 6, region=(-8.0, -5.0, 8.0, -1.0), name="t_wet")
        check("puddles on wet ground go into the ground's material, no discs", got is None and wm.get("sk_puddles", 0) > 0.5, str(wm.get("sk_puddles")))
        got2 = D.floor_detail("puddles", 4, region=(-4.0, 2.0, 4.0, 5.0), name="t_dry")
        check("puddles on dry ground are soft-edged decals", got2 is not None and got2.data.materials[0].name.startswith("SK_puddle_"), str(got2))
        if got2 is not None:
            check("... flat quads with 0..1 UVs, no icosphere discs", all(abs(v.co.z - got2.data.vertices[0].co.z) < 0.02 for v in got2.data.vertices) and len(got2.data.polygons) >= 1)


def _dresser(dress):
    """A Dresser on an empty open stage, the way an exterior theme gets one."""
    try:
        return dress.Dresser({"lo": (-10.0, -6.0), "hi": (10.0, 6.0)}, "probe", {}, 1.0, 7, 0.5, None, None)
    except Exception as e:                      # report, never hide
        check("could build a Dresser for the puddle tests", False, repr(e))
        return None


def main():
    plain()
    if "--plain" not in sys.argv:
        try:
            import bpy  # noqa: F401
        except ImportError:
            print("(no Blender: the in-Blender checks were skipped)")
        else:
            blender_part()
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
