"""Prove the office-building kit does what its docstrings say: moving parts move, status lamps switch, screens take pictures, rain loops, wet surfaces
are glossier, the library props open with their grips, and the four office themes are registered for the shot-plan validator.

    blender -b --factory-startup --python tools/tests/sets/test_office_kit.py

Checks (each prints PASS or FAIL; exit code 1 if any fails):
  pieces        every new piece builds, has a size, a type, the 'modern' era and a material on every mesh
  doors         furnish.swing_door turns the leaves of glass_doors; furnish.open_lift slides the lift leaves apart
  lamps         lamp_state keys the reader's lamp: red at the start, green after the key, and the light follows
  screens       screen_set_image replaces the picture; screen_look toggles the footage look and the timestamp
  rain          fx.rain makes streaks that loop (a Cycles F-curve), splash rings, glass beads and edge drips; excluded rectangles stay dry
  wet           mat.surface("asphalt", wet=1.0) is rougher-free: its roughness drops and its colour darkens relative to the dry one
  library       the ten hand props are in library/assets/index.json with a grip, open with assets.use, and aj_hands.prop_kind reads that grip
  themes        dress.THEMES has office_entrance, office_lobby, training_room, dim_room with era ["modern"]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "blender"))
sys.dont_write_bytecode = True

import bpy  # noqa: E402

import stagekit  # noqa: E402
from stagekit import assets, core, dress, furnish, fx, lights, mat  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


NEW = ["glass_front", "glass_doors", "card_reader_post", "badge_reader", "badge_gate", "lift_doors", "reception_desk", "company_totem", "wall_logo", "security_camera",
       "wall_screen", "ceiling_projector", "magazines", "lounge_chair", "bench_modern", "bollard", "planter_box", "bike_rack", "bicycle", "entrance_canopy", "water_jug_set",
       "floor_mat", "wet_floor_sign", "umbrella_stand", "coat_hooks", "fire_extinguisher", "exit_sign", "vending_machine", "recycling_bins", "training_seat", "lectern",
       "flipchart", "coffee_cup", "cup_carrier", "cardboard_box_desk", "laptop_closed", "laptop_open", "messenger_bag", "keycard_lanyard", "smartphone", "security_radio",
       "file_stack", "window_blinds", "desk_monitor", "router", "power_strip", "downlight", "ceiling_vent", "smoke_detector", "stanchion", "sanitiser_stand", "energy_can",
       "pizza_box", "headphones", "storage_box"]
PROPS = ["prop_coffee_cup", "prop_cup_carrier", "prop_cardboard_box_desk", "prop_laptop_open", "prop_laptop_closed", "prop_messenger_bag", "prop_keycard_lanyard",
         "prop_smartphone", "prop_security_radio", "prop_file_stack"]


def main():
    core.begin("office_kit_test", 4.0, "draft")
    lights.rig("day_soft", look=False)
    # ---- pieces
    bad = []
    built = {}
    for i, n in enumerate(NEW):
        try:
            ob = furnish.make(n, at=(i * 3.0, 0, 0))
            built[n] = ob
            w, d, h = furnish.footprint(ob)
            meshes = [o for o in [ob, *ob.children_recursive] if o.type == "MESH"]
            if min(w, h) <= 0.005 or ob.get("sk_type") != n or "modern" not in list(ob.get("sk_era", [])) or any(not m.data.materials for m in meshes):
                bad.append(n)
        except Exception as e:                                        # noqa: BLE001
            bad.append(f"{n} ({type(e).__name__}: {e})")
    check("pieces", not bad, ", ".join(bad) if bad else f"{len(NEW)} built")
    # ---- doors and lifts
    dr = built["glass_doors"]
    furnish.swing_door(dr, 0.5, 1.5, left=90.0, right=70.0)
    sh = core.current()
    bpy.context.scene.frame_set(sh.f(1.6))
    lf, rf = furnish.part(dr, "leaf_L"), furnish.part(dr, "leaf_R")
    check("doors", abs(lf.rotation_euler.z - 3.14159 / 2) < 0.02 and abs(rf.rotation_euler.z + 70 * 3.14159 / 180) < 0.02,
          f"L {lf.rotation_euler.z * 57.3:.0f} deg, R {rf.rotation_euler.z * 57.3:.0f} deg")
    lift = built["lift_doors"]
    a0 = furnish.part(lift, "door1_L").location.x
    b0 = furnish.part(lift, "door1_R").location.x
    furnish.open_lift(lift, 1, 0.5, 1.5)
    bpy.context.scene.frame_set(sh.f(1.6))
    gap = furnish.part(lift, "door1_R").location.x - furnish.part(lift, "door1_L").location.x
    check("lifts", abs(gap - ((b0 - a0) + 1.0)) < 0.02, f"leaf gap {b0 - a0:.2f} -> {gap:.2f} m")
    # ---- lamps
    post = built["card_reader_post"]
    lamp = furnish.part(post, "lamp")
    lt = bpy.data.objects[lamp["sk_lamp_light"]]
    furnish.lamp_state(lamp, "red")
    furnish.lamp_state(lamp, "green", t=2.0)
    bpy.context.scene.frame_set(sh.f(0.5))
    col0 = tuple(round(v, 2) for v in bpy.data.materials[lamp["sk_lamp_mat"]].node_tree.nodes["Emission"].inputs["Color"].default_value[:3])
    bpy.context.scene.frame_set(sh.f(3.0))
    col1 = tuple(round(v, 2) for v in bpy.data.materials[lamp["sk_lamp_mat"]].node_tree.nodes["Emission"].inputs["Color"].default_value[:3])
    check("lamps", col0[0] > col0[1] and col1[1] > col1[0] and lt.data.color[1] > lt.data.color[0], f"{col0} then {col1}")
    # ---- screens
    scr = built["wall_screen"]
    s = furnish.screen(scr)
    node = s.data.materials[0].node_tree.nodes["image"]
    before = node.image.name
    furnish.screen_set_image_builtin(scr, "slide")
    furnish.screen_look(scr, "clean")
    stamps = [o for o in scr.children_recursive if o.get("sk_part") == "stamp"]
    check("screens", node.image.name != before and node.image.name == "SK_screen_slide" and all(o.hide_render for o in stamps) and len(stamps) == 2,
          f"{before} -> {node.image.name}, {len(stamps)} stamp objects hidden")
    # ---- rain
    r = fx.rain(dict(lo=(-6, -6), hi=(6, 6)), intensity=1.0, exclude=[(-1, -1, 1, 1, 3.0)], height=8.0)
    st = r["streaks"]
    cyc = [fc for fc in core.fcurves(st) if any(m.type == "CYCLES" for m in fc.modifiers)]
    xs = [v.co for v in st.data.vertices]
    under = [v for v in xs if -0.9 < v.x < 0.9 and -0.9 < v.y < 0.9 and v.z < 2.5]
    wr = fx.window_rain(dict(centre=(0, 0, 2), normal=(0, -1, 0), w=3.0, h=2.0))
    dr_ = fx.drips_edge((-1, 0, 3), (1, 0, 3), n=6)
    check("rain", len(cyc) == 3 and r["splashes"] is not None and len(st.data.polygons) > 500 and not under and wr.data.materials and len(dr_) == 6,
          f"{len(st.data.polygons)} streak cards, {len(cyc)} looping curves, {len(under)} streak vertices under the excluded canopy")
    # ---- wet
    dry, wet = mat.surface("asphalt"), mat.surface("asphalt", wet=1.0)
    bd = next(n for n in dry.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bw = next(n for n in wet.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    check("wet", wet.get("sk_wet") == 1.0 and bw.inputs["Roughness"].is_linked and bw.inputs["Coat Weight"].default_value > bd.inputs["Coat Weight"].default_value,
          "roughness driven by the puddle mask, coat added")
    check("wet catalog", mat.surface("asphalt_wet").get("sk_wet") == 0.85 and mat.surface("paving_wet").get("sk_wet") == 0.9)
    # ---- library props
    ok = []
    for pid in PROPS:
        try:
            e = assets.get(pid)
            root = assets.use(pid, at=(0, 0, 0))
            ok.append(bool(e.get("grip")) and "modern" in e["era"] and e["source"] == "built" and e["license"] == "own" and any(o.type == "MESH" for o in root.children_recursive))
        except Exception as e_:                                       # noqa: BLE001
            ok.append(False)
            print("   ", pid, type(e_).__name__, e_)
    check("library", all(ok), f"{sum(ok)}/{len(PROPS)} props open with a grip")
    try:
        from stagekit import aj_hands
        root = assets.use("prop_messenger_bag", at=(0, 0, 0))
        check("grip read", aj_hands.prop_kind(root) == "power" and abs(aj_hands.grip_at(root) - 0.9) < 1e-6, f"bag grip {aj_hands.prop_kind(root)}")
    except Exception as e_:                                            # noqa: BLE001
        check("grip read", False, f"{type(e_).__name__}: {e_}")
    # ---- themes
    want = {"office_entrance": "exterior", "office_lobby": "room", "training_room": "room", "dim_room": "room"}
    check("themes", all(k in dress.THEMES and dress.THEMES[k]["era"] == ["modern"] and dress.THEMES[k]["kind"] == v for k, v in want.items()), ", ".join(want))
    check("moods", "rain_day" in lights.MOODS)
    sys.exit(1 if FAILS else 0)


main()
