"""Tests of the room's side of the light in stagekit.lights and the fixtures in stagekit.furnish (mood colour identity, fixtures whose
light and glowing surface change together, shadow resolution per quality, the shadow pool budget, declared sources).

    blender -b --factory-startup --python tools/tests/look/test_lights_look.py     # (go through the lock wrapper)

Nothing is rendered; it builds small scenes and reads them. Exit code 1 if a check fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "blender"))
sys.dont_write_bytecode = True
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main():
    import bpy
    from stagekit import arch, core, furnish, lights, viewlight

    # 1. every mood carries its colour identity; office_day is the approved room
    want = {"wb", "key", "fill", "fill_low", "practical", "window", "window_w_m2", "world"}
    missing = [m for m in lights.MOODS if not want <= set(lights.MOODS[m].get("look", {}))]
    check("every mood has the look fields", not missing, str(missing))
    od = lights.mood_look("office_day")
    check("office_day is the approved room", (od["wb"], od["key"], od["fill"], od["fill_low"], od["practical"], od["window"]) == (5000, 4300, 6500, 4800, 3400, 5800), str(od))
    warm = [m for m in lights.MOODS if not (lights.MOODS[m]["look"]["practical"] < lights.MOODS[m]["look"]["key"] < lights.MOODS[m]["look"]["wb"] < lights.MOODS[m]["look"]["fill"])]
    check("practical < key < white balance < fill in every mood", not warm, str(warm))
    sys.path.insert(0, str(ROOT / "tools"))
    import plan
    check("tools/plan.py MOODS in step", set(plan.MOODS) == set(lights.MOODS), str(set(plan.MOODS) ^ set(lights.MOODS)))

    # 2. rig applies the white balance and the mood's practical temperature, also to fixtures built before it
    core.begin("t_final", 1.0, "final")
    pre = furnish.make("ceiling_light_panel", at=(0, 0, 3.0), size=(1.2, 0.6))
    lights.rig("office_night", look=False, rim=0.0)
    vs = bpy.context.scene.view_settings
    check("rig sets the mood's white balance", vs.use_white_balance and abs(vs.white_balance_temperature - 4900) < 1, f"{vs.white_balance_temperature}")
    pl = [c for c in pre.children_recursive if c.type == "LIGHT"][0]
    check("a fixture built before the rig takes its practical temperature", pl.data.use_temperature and abs(pl.data.temperature - 3300) < 1, f"{pl.data.temperature}")
    lights.rig("office_day", look=False, rim=0.0)
    check("and follows a later rig", abs(pl.data.temperature - 3400) < 1)

    # 3. the panel's defaults, and its light and surface dim together
    p2 = furnish.make("ceiling_light_panel", at=(3, 0, 3.0), size=(1.2, 0.6))
    l2 = [c for c in p2.children_recursive if c.type == "LIGHT"][0]
    mats = [s.material for c in p2.children_recursive if c.type == "MESH" for s in c.material_slots if s.material and s.material.get("sk_fixture")]
    import math
    check("panel default: about 8 W, spread 55, shadows on", abs(l2.data.energy - 8.0) < 0.1 and abs(math.degrees(l2.data.spread) - 55) < 0.1 and l2.data.use_shadow,
          f"{l2.data.energy:.2f} W {math.degrees(l2.data.spread):.0f} deg")
    em = lambda m: next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Emission Strength"].default_value  # noqa: E731
    check("panel diffuser emission 2.0", mats and abs(em(mats[0]) - 2.0) < 1e-6, str([em(m) for m in mats]))
    lights.practicals(scale=0.5, match="ceiling_light_panel")
    check("practicals(scale) dims light and surface", abs(l2.data.energy - 4.0) < 0.05 and abs(em(mats[0]) - 1.0) < 1e-6, f"{l2.data.energy} {em(mats[0])}")
    lights.practicals(scale=0.5, match="ceiling_light_panel")
    check("scale does not compound", abs(l2.data.energy - 4.0) < 0.05)
    lights.fixture(p2, kelvin=2700)
    mats2 = [s.material for c in p2.children_recursive if c.type == "MESH" for s in c.material_slots if s.material and s.material.get("sk_fixture")]
    check("fixture(kelvin) recolours one piece, light and surface", abs(l2.data.temperature - 2700) < 1 and abs(pl.data.temperature - 3400) < 1
          and mats2[0] is not mats[0] and abs(mats2[0]["sk_kelvin"] - 2700) < 1, f"{l2.data.temperature} {pl.data.temperature}")
    lights.practicals(scale=0.0)
    check("practicals(scale=0): every lamp off, surfaces unlit", all(o.data.energy == 0 for o in bpy.data.objects if o.type == "LIGHT" and o.get("sk_role") == "practical")
          and all(em(m) == 0 for m in bpy.data.materials if m.get("sk_fixture")))
    cand = furnish.make("table_candle", at=(5, 0, 0))
    cl = [c for c in cand.children_recursive if c.type == "LIGHT"][0]
    lights.practicals(kelvin=5000)
    check("period pieces keep their colour", not cl.data.use_temperature and cl.get("sk_fixture") is None)

    # 4. shadow resolution follows the quality
    for q, r in (("final", 0.004), ("preview", 0.008), ("draft", 0.016)):
        core.begin(f"t_{q}", 1.0, q)
        lights.rig("office_day", look=False, rim=0.0)
        p = furnish.make("ceiling_light_panel", at=(0, 0, 3.0), size=(1.2, 0.6))
        lt = [c for c in p.children_recursive if c.type == "LIGHT"][0]
        check(f"panel shadow resolution at {q}", abs(lt.data.shadow_maximum_resolution - r) < 1e-9 and lt.data.use_shadow_jitter == bool(core.look("shadow.jitter", True)),
              f"{lt.data.shadow_maximum_resolution}")

    # 5. the budget never exceeds the pool, with 30 fixtures, at every quality
    for q in ("final", "preview", "draft"):
        core.begin(f"b_{q}", 1.0, q)
        lights.rig("office_day", look=False, rim=0.0)
        for i in range(30):
            at = ((i % 6) * 1.5 - 4, (i // 6) * 1.5 - 3, 3.0)
            if i % 2:
                furnish.make("ceiling_light_panel", at=at, size=(1.2, 0.6))
            else:
                furnish.make("downlight", at=at)
        d = bpy.data.lights.new("hand", "SPOT")                      # a light made by hand at Blender's 1 mm default
        ho = bpy.data.objects.new("hand", d)
        bpy.context.scene.collection.objects.link(ho)
        lights.limit_shadows(quiet=True)
        b = lights.shadow_budget()
        rep = json.loads(bpy.context.scene["sk_shadow_budget"])
        check(f"budget fits the pool at {q}", b["estimate"] <= b["budget"] <= b["tiles"] and rep["estimate_tiles"] <= rep["budget_tiles"],
              f"{b['estimate']} of {b['budget']} ({b['tiles']} tiles), dropped {len(rep['dropped'])}")
        check(f"hand-made light held to the quality's resolution at {q}", d.shadow_maximum_resolution >= core.shadow_res() - 1e-9, f"{d.shadow_maximum_resolution}")
        kept = [o for o in bpy.data.objects if o.type == "LIGHT" and o.data.use_shadow]
        check(f"the budget drops the weakest first at {q}", all(o.data.energy >= max((x.data.energy for x in bpy.data.objects if x.type == "LIGHT" and x.get("sk_role") == "practical"
              and not x.data.use_shadow), default=0) - 1e-6 for o in kept if o.get("sk_role") == "practical"))

    # 6. sources are declared by window_key, window_sun and interior; old window keys still work
    core.begin("s", 1.0, "draft")
    R = arch.room((6, 5, 3.0), floor="wood_floor", walls="plaster_warm", ceiling="plaster_clean", name="r", openings=[
        dict(wall="E", kind="window", type="office", w=2.1, h=1.6, sill=0.9, at=-1.2, id="w1"),
        dict(wall="E", kind="window", type="office", w=2.1, h=1.6, sill=0.9, at=1.2, id="w2")])
    out = lights.interior("office_day", room=R)
    srcs = viewlight.sources()
    check("interior declares a window source per window", sum(1 for s in srcs if s["kind"] == "window") == 2, str([s["name"] for s in srcs]))
    k = out["key"]["light"]
    check("interior's window light is the weak cool sky light", abs(k.data.energy - 8.2 * 2.1 * 1.6) < 0.5 and abs(k.data.temperature - 5800) < 1 and k.data.use_shadow
          and k.get("sk_role") == "window", f"{k.data.energy:.1f} W")
    w = bpy.context.scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value
    check("interior's world is low", abs(w - 0.12) < 1e-6, str(w))
    n0 = len(viewlight.sources())
    lights.window_sun(R, "E", power=1.0)
    check("window_sun declares a source", len(viewlight.sources()) == n0 + 1)
    old = lights.window_key(R.openings["w1"], color="#F2F6FF", power=380, shaft=False, pitch=16, shadow=False, name="KEY_old")
    check("the old strong window key still works", abs(old["light"].data.energy - 380) < 1e-6 and not old["light"].data.use_shadow and old["light"].get("sk_role") == "key")
    leg = lights.interior("office_day", key_from=R.openings["w2"], key_power=1500, fill=dict(at=(0, 0, 2.7), size=(7, 5), power=120))
    check("interior's old arguments still give the strong key", abs(leg["key"]["light"].data.energy - 1500) < 1e-6 and leg["fill"] is not None)
    lamp = furnish.make("floor_lamp", at=(-2, 1, 0))
    nd = lights.declare_sources()
    check("declare_sources declares a strong lamp once", nd >= 1 and lights.declare_sources() == 0, str(nd))

    print("FAILED: " + ", ".join(FAILS) if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)


main()
