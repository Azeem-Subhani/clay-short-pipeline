"""Headless view lighting checks.

Run through the shared Blender lock:
    blender -b --factory-startup --python-exit-code 3 --python tools/tests/look/test_viewlight.py
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "blender"))
sys.dont_write_bytecode = True
from stagekit import camera, core, lights as stage_lights, review, viewlight


def wall(name, at, dimensions):
    bpy.ops.mesh.primitive_cube_add(size=1, location=at)
    ob = bpy.context.object
    ob.name, ob.scale = name, dimensions
    ob["sk_type"] = "wall"
    return ob


def head(shot, name, at, moments):
    ob = core.empty(name, at)
    ob["sk_type"] = "head"
    shot.subject(name, ob, moments=moments)
    return ob


def camera_view(cam, name, t, pos=(0, -3, 1.65), **kw):
    cam.view(name, t, pos=pos, aim=(0, 0, 1.45), lens=32, still=not kw, **kw)


def lights():
    return {o.name: o for o in bpy.context.scene.objects if o.type == "LIGHT" and o.get("vl_role")}


def main():
    shot = core.begin("viewlight_test", 4, quality="draft")
    declared = viewlight.source("window", (3, -0.8, 2), toward=(-2, 0, 0), kelvin=5800, name="east")
    assert viewlight.sources() == [declared]
    assert declared["toward"] == [-1, 0, 0]
    assert viewlight.source("practical", (-2, 3, 2.2))["toward"] is None

    wall("east wall", (3.1, 0, 1.5), (0.2, 8.2, 3))
    wall("west wall", (-3.1, 0, 1.5), (0.2, 8.2, 3))
    wall("south wall", (0, -4.1, 1.5), (6.2, 0.2, 3))
    wall("north wall", (0, 4.1, 1.5), (6.2, 0.2, 3))
    wall("ceiling", (0, 0, 3.1), (6.2, 8.2, 0.2))
    shot._viewlight_room = SimpleNamespace(lo=(-3, -4), hi=(3, 4))
    a = head(shot, "first", (0, 0, 1.45), ["one", "travel"])
    head(shot, "second", (0.4, 0.6, 1.45), ["one", "two"])
    cam = camera.Camera()
    camera_view(cam, "one", 0)
    camera_view(cam, "travel", 1, pos=(0.1, -2.8, 1.7), travel=0.3)
    camera_view(cam, "two", 2)
    report = viewlight.shape(shot, cam, meter=False, fit_shadows=False)
    assert shot.viewlight is report
    scene = bpy.context.scene
    rig, travel, reverse = report["views"]
    key = lights()["VL_one_key"]
    scene.frame_set(1)
    hero = a.matrix_world.translation
    angle = math.degrees((Vector((0, -3, 1.65)) - hero).angle(key.location - hero))
    assert rig["hero"] == "first" and rig["source"] == "east", rig
    assert 45 <= angle <= 60 and 45 <= rig["angle_off_lens"] <= 60, (angle, rig)
    assert 0 < key.location.x < 3 and -4 < key.location.y < 4 and hero.z < key.location.z < 3
    assert key.data.use_shadow and math.isclose(key.data.shadow_maximum_resolution, core.shadow_res(), rel_tol=1e-6)
    assert reverse["hero"] == "second" and travel["held_from"] == "one"
    assert not any(ob.get("vl_view") == "travel" for ob in lights().values())
    cut = shot.f(2)
    for frame in (0, 1, shot.f(1), cut - 1, cut, shot.frames, shot.frames + 1):
        scene.frame_set(frame)
        assert (key.data.energy > 0) == (1 <= frame < cut), frame
        assert (lights()["VL_two_key"].data.energy > 0) == (cut <= frame <= shot.frames), frame
    names = set(lights())
    assert report == viewlight.shape(shot, cam, meter=False, fit_shadows=False)
    assert set(lights()) == names
    print("PASS registry, placement, cut timing, continuous move and rebuild")

    shot = core.begin("viewlight_sun", 1, quality="draft")
    assert viewlight.sources() == []
    head(shot, "outdoors", (0, 0, 1.45), ["one"])
    cam = camera.Camera()
    camera_view(cam, "one", 0)
    sky = stage_lights.rig("day_clear", rim=0, look=False)
    sun = next(item for item in viewlight.sources() if item["kind"] == "sky")
    rig = viewlight.shape(shot, cam, edge=["outdoors"], meter=False, fit_shadows=False)["views"][0]
    assert sky.sun.data.type == "SUN" and rig["source"] == sun["name"], rig
    assert set(lights()) == {"VL_one_fill", "VL_one_front"}, set(lights())
    print("PASS new scene clears declarations, sun remains the only key")


def prop_insert():
    shot = core.begin("viewlight_insert", 1, quality="draft")
    head(shot, "out_of_frame", (5, 0, 1.5), ["insert"])
    bpy.ops.mesh.primitive_plane_add(size=0.75, location=(0, 0.1, 1.4), rotation=(math.pi / 2, 0, 0))
    monitor = bpy.context.object
    screen = bpy.data.materials.new("monitor")
    screen.use_nodes = True
    bsdf = next(node for node in screen.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Emission Color"].default_value = (0.6, 0.8, 1.0, 1)
    bsdf.inputs["Emission Strength"].default_value = 1
    monitor.data.materials.append(screen)
    shot.subject("monitor", monitor, moments=["insert"])
    cam = camera.Camera()
    cam.view("insert", 0, pos=(0, -3, 1.65), aim=(0, 0, 1.4), lens=32, size="insert", still=True)
    rig = viewlight.shape(shot, cam, meter=False, fit_shadows=False)["views"][0]
    # nobody to key and the subject glows (a monitor): it is its own key, so only a low narrow shaping key from above, no fills or bounce
    assert rig["hero"] is None and rig["subject"] == "monitor" and rig["subject_emits"] == "emissive", rig
    assert set(lights()) == {"VL_insert_key"}, set(lights())
    assert rig["key_role"] == "emitter_shape" and rig["key_power"] < 40, rig
    print("PASS off-camera character does not light a prop insert; a glowing subject gets only a low shaping key")


def build_set():
    fixture = bpy.data.lights.new("FILL_set_fixture", "POINT")
    core.link(bpy.data.objects.new(fixture.name, fixture), "LIGHTS")


def build_shot(shot):
    build_set()
    build_set_mood()
    head(shot, "subject", (0, 0, 1.45), ["one"])
    cam = camera.Camera()
    camera_view(cam, "one", 0)
    if shot.id == "viewlight_legacy":
        legacy = bpy.data.lights.new("handmade", "AREA")
        core.link(bpy.data.objects.new(legacy.name, legacy), "LIGHTS")
    elif shot.id == "viewlight_explicit":
        viewlight.shape(shot, cam, scale=0.5)
    elif shot.id == "viewlight_off":
        shot.viewlight = False


def runner():
    import run_shot

    for case in ("automatic", "legacy", "explicit", "off"):
        shot = run_shot.build_shot_scene(None, f"viewlight_{case}", "draft", seconds=2, script=__file__)
        report = shot.viewlight
        wb = bpy.context.scene.view_settings.use_white_balance
        if case == "off":
            assert report is False and not lights() and not wb
        elif case == "legacy":
            assert "handmade" in report["warnings"][0] and not lights()
            assert not wb, "a shot that keeps its hand-made rig keeps the view as it was"
        else:
            assert set(lights()) == {"VL_one_key", "VL_one_fill", "VL_one_front"}, report
            assert wb and report["white_balance"] == 5000, "the per-view step sets the mood's white balance"
            if case == "automatic":
                power = viewlight.view(report, "one")["key_power"]
            else:
                # scale is a multiplier on the metered key (the meter lands on its grid, so within a few percent)
                assert math.isclose(viewlight.view(report, "one")["key_power"], power * 0.5, rel_tol=0.06), (viewlight.view(report, "one")["key_power"], power)
            assert viewlight.hero_of(report, "one") == "subject"
    # the plan's hero and separate are the defaults; what the shot file sets wins, view by view
    plan = {"cast": ["a", "b"], "views": [{"id": "one", "hero": "a", "separate": ["b"]}, {"id": "two", "hero": "b"}]}
    merged = run_shot.merged_viewlight_options(plan, {"hero": {"two": "a"}, "scale": 0.5})
    assert merged == {"hero": {"one": "a", "two": "a"}, "edge": {"one": ["b"]}, "scale": 0.5}, merged
    assert run_shot.merged_viewlight_options(None, {"hero": "x"}) == {"hero": "x"}
    print("PASS run_shot hook, set fixtures, legacy warning, explicit rig, opt-out, white balance and plan options")


def build_set_mood():
    stage_lights.rig("office_day", look=False, rim=0.0)


def helpers():
    """hero_of reads a report or the options before shape ran; a later view of a run lends its options; mood levels; stand_in."""
    assert viewlight.hero_of({"views": [{"view": "a", "hero": "x"}, {"view": "b", "hero": "x", "held_from": "a"}]}, "b") == "x"
    assert viewlight.hero_of({"hero": {"b": "y"}}, "b") == "y" and viewlight.hero_of({"hero": "z"}, "q") == "z"
    assert viewlight.hero_of(None, "a") is None and viewlight.hero_of(False, "a") is None and viewlight.hero_of({"views": []}, "a") is None
    opts, taken = viewlight._run_options({"hero": {"b": "y"}, "scale": 2}, ["a", "b"])
    assert opts["hero"]["a"] == "y" and taken == {"hero": "b"} and opts["scale"] == 2
    day = viewlight.levels(stage_lights.mood_look("office_day"))
    night = viewlight.levels(stage_lights.mood_look("office_night"))
    rain = viewlight.levels(stage_lights.mood_look("rain_day"))
    assert math.isclose(day["key"], 1) and math.isclose(day["fill"], 1) and not day["pool"]
    assert night["key"] < 0.75 and night["fill"] / night["key"] < 1 and night["pool"]
    assert rain["fill"] / rain["key"] > 1.5 and rain["soft"]
    assert viewlight.levels({}) == viewlight.levels(stage_lights.mood_look("office_day"))
    print("PASS hero lookup, run options and mood levels")

    # night: a desk lamp near the hero motivates the key before a nearer window; a pool is closer and narrower than a day key
    shot = core.begin("viewlight_night", 1, quality="draft")
    stage_lights.rig("office_night", look=False, rim=0.0)
    for name, at, dims in (("e", (3.1, 0, 1.5), (0.2, 8.2, 3)), ("w", (-3.1, 0, 1.5), (0.2, 8.2, 3)), ("s", (0, -4.1, 1.5), (6.2, 0.2, 3)),
                           ("n", (0, 4.1, 1.5), (6.2, 0.2, 3)), ("c", (0, 0, 3.1), (6.2, 8.2, 0.2))):
        wall(name, at, dims)
    shot._viewlight_room = SimpleNamespace(lo=(-3, -4), hi=(3, 4))
    viewlight.source("window", (2.9, 0.3, 1.8), toward=(-1, 0, 0), kelvin=8000, name="window", strength=0.2)
    viewlight.source("practical", (-1.5, 1.2, 1.0), kelvin=3300, name="desk_lamp", strength=1.2)
    head(shot, "worker", (0, 0, 1.45), ["one"])
    cam = camera.Camera()
    camera_view(cam, "one", 0)
    rig = viewlight.view(viewlight.shape(shot, cam, meter=False, fit_shadows=False), "one")
    key = lights()["VL_one_key"]
    assert rig["source"] == "desk_lamp" and rig["key_role"] == "pool", rig
    assert rig["key_distance"] <= viewlight.POOL_THROW + 0.5 and math.isclose(math.degrees(key.data.spread), viewlight.POOL_SPREAD, abs_tol=0.01), rig
    assert bpy.context.scene.view_settings.use_white_balance and abs(bpy.context.scene.view_settings.white_balance_temperature - 4900) < 1
    print("PASS night key: pool from the practical, white balance")

    # stand_in: the same lights with no shot or cast, constant power, replaced by a second call, and the mood's white balance
    core.begin("viewlight_standin", 1, quality="draft")
    stage_lights.rig("office_day", look=False, rim=0.0)
    assert not bpy.context.scene.view_settings.use_white_balance
    cd = bpy.data.cameras.new("c")
    cob = bpy.data.objects.new("c", cd)
    bpy.context.scene.collection.objects.link(cob)
    cob.location = (0, -4, 1.6)
    cob.rotation_euler = (Vector((0, 0, 1.5)) - Vector(cob.location)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    rep = viewlight.stand_in(cob, (0, 0, 1.55), meter=False)
    got = {n for n in lights() if n.startswith("VL_standin_")}
    assert got == {"VL_standin_key", "VL_standin_fill", "VL_standin_front"}, got
    assert rep["white_balance"] == 5000 and bpy.context.scene.view_settings.use_white_balance
    assert 45 <= rep["angle_off_lens"] <= 60 and lights()["VL_standin_key"].data.energy > 0
    assert not (lights()["VL_standin_key"].data.animation_data and lights()["VL_standin_key"].data.animation_data.action)
    assert lights()["VL_standin_key"].get("sk_role") == "key" and lights()["VL_standin_fill"].get("sk_role") == "fill"
    night = viewlight.stand_in(cob, (0, 0, 1.55), mood="office_night", meter=False)
    assert {n for n in lights() if n.startswith("VL_standin_")} == got and night["key_power"] < rep["key_power"]
    n_obs = len(bpy.data.objects)
    metered = viewlight.stand_in(cob, (0, 0, 1.55))           # the default: a grey card at the head, like a view with nobody in it
    m = metered["meter"]
    assert m.get("kind") == "grey card" and m.get("key_scale") is not None, m
    assert math.isclose(metered["key_power"], metered["formula_key_power"] * m["key_scale"], rel_tol=5e-3), metered
    assert len(bpy.data.objects) == n_obs and not any(o.name.startswith("SK_meter") for o in bpy.data.objects)
    print(f"PASS stand_in is metered on a grey card at the head: {m.get('before')} -> {m.get('after')} x{m['key_scale']}")
    viewlight.clear()
    assert not lights()
    print("PASS stand_in")


def face_room(shot_id, set_light=0.0, blocker=False):
    """A small lit room with one synthetic cast member: a skin-coloured sphere head the look checks can measure, facing the camera."""
    shot = core.begin(shot_id, 1, quality="draft")
    stage_lights.rig("office_day", look=False, rim=0.0)
    for name, at, dims in (("e", (3.1, 0, 1.5), (0.2, 8.2, 3)), ("w", (-3.1, 0, 1.5), (0.2, 8.2, 3)), ("s", (0, -4.1, 1.5), (6.2, 0.2, 3)),
                           ("n", (0, 4.1, 1.5), (6.2, 0.2, 3)), ("c", (0, 0, 3.1), (6.2, 8.2, 0.2))):
        wall(name, at, dims)
    shot._viewlight_room = SimpleNamespace(lo=(-3, -4), hi=(3, 4))
    viewlight.source("window", (2.9, 0.3, 1.8), toward=(-1, 0, 0), kelvin=5800, name="window")
    coll = core.collection("CAST_face")
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(0, 0, 1.45), segments=48, ring_count=24)
    sphere = bpy.context.object
    for c in list(sphere.users_collection):
        c.objects.unlink(sphere)
    coll.objects.link(sphere)
    bpy.ops.object.shade_smooth()
    skin = bpy.data.materials.new("skin")
    skin.use_nodes = True
    next(n for n in skin.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (0.42, 0.28, 0.2, 1)
    sphere.data.materials.append(skin)
    sphere["sk_type"] = "head"
    stage = core.empty("face_stage", (0, 0, 0), "CAST")
    shot.actors["face"] = SimpleNamespace(head=sphere, head_r=0.2, scale=1.0, stage=stage, coll=coll,
                                         _billboard=lambda cam_ob: None)
    shot.subject("face", sphere, moments=["one"])
    if set_light:
        lamp = bpy.data.lights.new("PANEL_room", "AREA")
        lamp.energy, lamp.size = set_light, 1.5
        ob = bpy.data.objects.new(lamp.name, lamp)
        ob.location = (0, -1.0, 2.9)
        ob["sk_role"] = "practical"
        core.link(ob, "LIGHTS")
    if blocker:
        wall("pillar", (0, -1.5, 1.45), (0.6, 0.2, 0.6))
    cam = camera.Camera()
    cam.view("one", 0, pos=(0, -2.2, 1.5), aim=(0, 0, 1.45), lens=50, still=True)
    return shot, cam


def scene_state():
    sc = bpy.context.scene
    r = sc.render
    return {"frame": (sc.frame_current, sc.frame_subframe), "percent": r.resolution_percentage, "size": (r.resolution_x, r.resolution_y),
            "samples": sc.eevee.taa_render_samples, "filepath": r.filepath, "camera": sc.camera.name if sc.camera else None,
            "format": (r.image_settings.file_format, r.image_settings.color_depth), "stamp": r.use_stamp,
            "hidden": {o.name: o.hide_render for o in sc.objects}, "objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials), "wb": sc.view_settings.white_balance_temperature,
            "shadow_res": {o.name: o.data.shadow_maximum_resolution for o in sc.objects if o.type == "LIGHT"}}


def metering():
    """meter(): converges on a synthetic head, corrects a set that is brighter than the approved room, restores the scene, skips a hidden
    face, and meter=False keeps the formula's powers."""
    shot, cam = face_room("meter_plain")
    formula = viewlight.view(viewlight.shape(shot, cam, meter=False, scale=0.4), "one")
    assert viewlight.shape(shot, cam, meter=False, scale=0.4)["meter"] == {"enabled": False}
    before = scene_state()
    report = viewlight.shape(shot, cam, scale=0.4)
    after = scene_state()
    for k in before:
        if k != "shadow_res":
            assert before[k] == after[k], (k, before[k], after[k])
    assert before["shadow_res"] == after["shadow_res"]
    m = viewlight.view(report, "one")["meter"]
    lo, hi = m["target"]
    clo, chi = m["cheek_target"]
    # ratio first, then the level: the cheek in its range, the face in its range or (a compromise, said so) at most LEVEL_SLACK over it
    assert "after" in m and m["passes"] <= viewlight.METER_PASSES, m
    # the cheek in its range, or (the room's own light on the shadow side, set_share ~0.4 here) the step's fills taken off and said so
    assert clo - 0.03 <= m["after"]["cheek"] <= chi + 0.03 or (
        m["fill_scale"] <= 0.01 * m["key_scale"] + 1e-6 and any(n.startswith("the cheek ratio ends") for n in m["notes"])), m
    assert lo - 0.015 <= m["after"]["face"] <= hi + viewlight.LEVEL_SLACK + 0.02, m
    assert m["after"]["face"] <= hi + 0.015 or any(n.startswith("compromise") for n in m["notes"]), m
    assert m["target"] == viewlight.face_range(stage_lights.mood_look("office_day"))
    k = lights()["VL_one_key"]
    bpy.context.scene.frame_set(1)
    # scale=0.4 is a multiplier on what the meter arrived at (item 5): key = formula x key_scale x view_scale
    assert m.get("view_scale") == 0.4, m
    assert math.isclose(k.data.energy, formula["key_power"] * m["key_scale"] * 0.4, rel_tol=5e-3), (k.data.energy, formula["key_power"], m)
    assert math.isclose(viewlight.view(report, "one")["key_power"], k.data.energy, rel_tol=1e-4)
    print(f"PASS meter, ratio first: {m['before']} -> {m['after']} x{m['key_scale']} fill x{m['fill_scale']} in {m['passes']} passes, "
          f"{m['renders']} renders, {m['seconds']} s; the scene is restored; scale 0.4 applied on the result")

    report1 = viewlight.shape(shot, cam)
    k1 = lights()["VL_one_key"].data.energy
    report2 = viewlight.shape(shot, cam, scale=2.0)
    k2 = lights()["VL_one_key"].data.energy
    m2s = viewlight.view(report2, "one")["meter"]
    # the metered key (formula x key_scale) is multiplied by the view's scale after metering, and the report says so
    assert m2s["view_scale"] == 2.0 and math.isclose(k2, m2s["formula_key_power"] * m2s["key_scale"] * 2.0, rel_tol=5e-3), (k2, m2s)
    assert math.isclose(viewlight.view(report2, "one")["key_power"], k2, rel_tol=1e-4)
    print(f"PASS scale on a metered view multiplies the metered key: metered {m2s['formula_key_power'] * m2s['key_scale']:.1f} W, "
          f"scale 2 -> {k2:.1f} W (scale 1: {k1:.1f} W)")

    shot, cam = face_room("meter_bright", set_light=25.0)
    m2 = viewlight.view(viewlight.shape(shot, cam), "one")["meter"]
    assert m2["before"]["face"] > m2["target"][1] and m2["key_scale"] < 1 and m2["target"][0] - 0.015 <= m2["after"]["face"] <= m2["target"][1] + 0.015, m2
    print(f"PASS a set brighter than the approved room is metered down: {m2['before']} -> {m2['after']} x{m2['key_scale']}")

    shot, cam = face_room("meter_hidden", blocker=True)
    rig = viewlight.view(viewlight.shape(shot, cam), "one")
    assert "hidden" in rig["meter"].get("skipped", ""), rig["meter"]
    assert rig["meter"]["renders"] <= 1      # only the ceiling check reads the picture
    print("PASS a hidden face keeps the formula's key:", rig["meter"]["skipped"])

    # an insert with nobody in it: a grey card at the subject is metered to the object level, and the card is gone afterwards
    shot = core.begin("meter_insert", 1, quality="draft")
    stage_lights.rig("office_day", look=False, rim=0.0)
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(0, 0, 0.9))
    box = bpy.context.object
    shot.subject("box", box, moments=["insert"])
    cam = camera.Camera()
    cam.view("insert", 0, pos=(0, -1.6, 1.3), aim=(0, 0, 0.9), lens=40, size="insert", still=True)
    viewlight.shape(shot, cam, meter=False, fit_shadows=False)
    n = len(bpy.data.objects)
    rig = viewlight.view(viewlight.shape(shot, cam), "insert")
    mi = rig["meter"]
    assert rig["subject"] == "box" and mi["kind"] == "grey card" and "after" in mi, mi
    assert mi["target"][0] - 0.02 <= mi["after"]["card"] <= mi["target"][1] + 0.02, mi
    assert len(bpy.data.objects) == n and not any(o.name.startswith("SK_meter") for o in bpy.data.objects)
    print(f"PASS an insert is keyed and metered on a grey card: {mi['before']} -> {mi['after']} x{mi['key_scale']}")

    # a glowing subject (a screen) is its own key: a low narrow shaping key from above, no fills, never metered up
    shot = core.begin("meter_glow", 1, quality="draft")
    stage_lights.rig("office_night", look=False, rim=0.0)
    bpy.ops.mesh.primitive_cube_add(size=0.4, location=(0, 0, 0.9))
    screen = bpy.context.object
    glow = bpy.data.materials.new("screen_glow")
    glow.use_nodes = True
    em = glow.node_tree.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 4.0
    glow.node_tree.links.new(em.outputs[0], glow.node_tree.nodes["Material Output"].inputs["Surface"])
    screen.data.materials.append(glow)
    shot.subject("screen", screen, moments=["insert"])
    cam = camera.Camera()
    cam.view("insert", 0, pos=(0, -1.6, 1.3), aim=(0, 0, 0.9), lens=40, size="insert", still=True)
    plain = viewlight.view(viewlight.shape(shot, cam, meter=False, fit_shadows=False), "insert")
    rig = viewlight.view(viewlight.shape(shot, cam, fit_shadows=False), "insert")
    names = sorted(lights())
    assert plain["subject_emits"] == "emissive" and plain["key_role"] == "emitter_shape", plain
    assert names == ["VL_insert_key"] and not plain["fill_powers"], names
    k = lights()["VL_insert_key"]
    assert math.degrees(k.data.spot_size) <= viewlight.EMITTER_SPREAD + 0.1
    aim = k.matrix_world.to_3x3() @ Vector((0, 0, -1))
    assert aim.z < -0.7, aim                       # aimed down at the surface the subject stands on
    assert rig["key_power"] <= plain["key_power"] * 1.001, (rig["key_power"], plain["key_power"])
    print(f"PASS a glowing subject is its own key: one {plain['key_power']:.1f} W shaping key, spread "
          f"{math.degrees(k.data.spot_size):.0f}, aimed down, metered {rig['meter'].get('after') or rig['meter'].get('skipped')}")


def shadow_fit():
    """fit_shadows(): after the view keys are in, the pool holds at every lit run's frames, measured from EEVEE's own demand; the
    weakest practicals lose their shadows first, a view key never does, a key switched off at the current frame still counts, and the
    render settings are put back."""
    shot = core.begin("pool_fit", 20, quality="draft")
    bpy.ops.mesh.primitive_plane_add(size=16, location=(0, 0, 0))
    for i in range(6):
        bpy.ops.mesh.primitive_cube_add(size=0.6, location=((i % 3) * 1.6 - 1.6, (i // 3) * 1.6 - 0.8, 0.3))
    practicals = []
    for i in range(10):                     # equal distance from the stage centre, so their rank is their power
        a = i * math.tau / 10
        d = bpy.data.lights.new(f"PRAC_{i}", "POINT")
        d.energy, d.use_shadow, d.shadow_maximum_resolution = 20.0 + 10 * i, True, 0.002
        ob = bpy.data.objects.new(d.name, d)
        ob.location = (3.0 * math.cos(a), 3.0 * math.sin(a), 2.6)
        ob["sk_role"] = "practical"
        core.link(ob, "LIGHTS")
        practicals.append(ob)
    cam_ob = bpy.data.objects.new("pool_cam", bpy.data.cameras.new("pool_cam"))
    core.link(cam_ob, "CAMERAS")
    cam_ob.location, cam_ob.rotation_euler = (0, -6.5, 3.2), (math.radians(62), 0, 0)
    bpy.context.scene.camera = cam_ob
    key_a = viewlight._light("a", "key", 1, 10, Vector((2.5, -3, 2.4)), Vector((0, 0, 1)), 300, 4300, size=(1, 1), spread=60, shadow=True)
    key_b = viewlight._light("b", "key", 11, 20, Vector((-2.5, -3, 2.4)), Vector((0, 0, 1)), 300, 4300, size=(1, 1), spread=60, shadow=True)
    report = {"views": [{"view": "a", "frames": [1, 10]}, {"view": "b", "frames": [11, 20]}]}
    sc = bpy.context.scene
    sc.frame_set(5)                          # key b is dark here: limit_shadows alone would not count it
    assert key_b.data.energy == 0
    model = viewlight.fit_shadows(shot, report, measure=False)
    assert "measured" not in model["final"] and model["final"]["reserve_tiles"] > 0, model
    before = scene_state()
    out = viewlight.fit_shadows(shot, report, final_mb=128, pool_mb=64)   # a draft build: its own pool, and the final one
    after = scene_state()
    for k in before:
        assert before[k] == after[k], (k, before[k], after[k])
    fin, bld = out["final"], out["build"]
    print("  final fit:", fin["measured"], fin["dropped"], "| build fit:", bld["measured"], bld["dropped"])
    first = max(fin["rounds"][0]["demand"].values())
    assert key_a.data.use_shadow and key_b.data.use_shadow, "a view key lost its shadow"
    assert fin["fits"] and bld["fits"], out
    assert set(fin["measured"]) == {"1", "10", "11", "20"}, fin["measured"]
    stored = json.loads(sc["sk_shadow_fit"])
    final_off, build_off = set(stored["final"]), set(stored["build"])
    assert stored["quality"] == "draft" and final_off and final_off < build_off, stored      # a draft drops more than final
    for off in (final_off, build_off):                               # the weakest first, in both fits
        kept = [o.data.energy for o in practicals if o.name not in off]
        assert kept and max(o.data.energy for o in practicals if o.name in off) <= min(kept), (off, kept)
    assert {o.name for o in practicals if not o.data.use_shadow} == build_off        # the build's fit is the scene's
    with review.final_quality(shot):                                 # the look stills and the meter get the final fit
        assert {o.name for o in practicals if not o.data.use_shadow} == final_off
        assert key_a.data.use_shadow and key_b.data.use_shadow
    assert {o.name for o in practicals if not o.data.use_shadow} == build_off        # and back
    print(f"PASS shadow pool re-fit per quality: final demand {max(fin['measured'].values())} of {fin['target_tiles']} "
          f"({len(final_off)} practicals off), draft {max(bld['measured'].values())} of {bld['target_tiles']} ({len(build_off)} off); "
          f"final_quality swaps the final fit in and out; view keys kept; {fin['renders'] + bld['renders']} renders, settings restored")

    # a final build fits once, to the final pool, and final_quality has nothing to swap
    shot.quality = "final"
    for o in practicals:
        o.data.use_shadow = True
    one = viewlight.fit_shadows(shot, report, final_mb=128)
    assert "build" not in one and json.loads(sc["sk_shadow_fit"])["build"] == json.loads(sc["sk_shadow_fit"])["final"], one
    print("PASS a final build fits once:", one["final"]["dropped"])

    # Round 4: EEVEE fills at most viewlight.RENDER_TILE_CAP shadow tiles per render whatever the pool. Past it some shadows go missing
    # with no message, differently in each Blender process (sh08: the same rig's look still Y 95.9 to 114.5). A 2048 MB pool (8192 tiles)
    # is still fitted to the cap: a frame asking 1900 tiles loses practicals' shadows until it asks at most cap x POOL_TARGET.
    for o in practicals:
        o.data.use_shadow = True
    real = viewlight.pool_demand

    def fake(shot_, frames, final=True):
        off = sum(1 for o in practicals if not o.data.use_shadow)
        return {str(f): 1900 - 120 * off for f in frames}, 0.0
    viewlight.pool_demand = fake
    try:
        capped = viewlight.fit_shadows(shot, report, final_mb=2048)
    finally:
        viewlight.pool_demand = real
    cap = viewlight.RENDER_TILE_CAP * viewlight.POOL_TARGET
    fin = capped["final"]
    assert fin["target_tiles"] <= cap + 1 and max(fin["measured"].values()) <= cap and fin["dropped"], fin
    print(f"PASS the fit holds EEVEE's {viewlight.RENDER_TILE_CAP}-tile render cap under a 2048 MB pool: 1900 -> "
          f"{max(fin['measured'].values())} of {fin['target_tiles']} ({len(fin['dropped'])} practicals off)")


def repeatable():
    """Round 4: two fresh builds of the same small lit scene give the same final-quality picture (frame mean within 0.2 of 255, mean
    absolute pixel difference under 0.5 of 255: EEVEE's sampling is seeded, so a correct build repeats nearly exactly), with the fit's
    flags and the final shadow resolution in place for the look render."""
    import numpy as np
    from pathlib import Path as _P
    import tempfile
    pics = []
    for run in range(2):
        shot, cam = face_room(f"repeat_{run}")
        viewlight.shape(shot, cam, meter=False)
        stored = json.loads(bpy.context.scene.get("sk_shadow_fit") or "{}")
        path = _P(tempfile.gettempdir()) / f"sk_repeat_{run}.png"
        with review.final_quality(shot):
            final_off = set(stored.get("final", []))
            for o in bpy.context.scene.objects:
                if o.type == "LIGHT" and stored:
                    want = o.name not in final_off if o.name in final_off | set(stored.get("build", [])) else o.data.use_shadow
                    assert o.data.use_shadow == want, (o.name, o.data.use_shadow, stored)
            review.render_still(path, 1)
        pics.append(review._load_pixels(path))
    a, b = pics
    d_mean = abs(float(a.mean()) - float(b.mean())) * 255
    d_px = float(np.abs(a - b).mean()) * 255
    assert d_mean < 0.2 and d_px < 0.5, (d_mean, d_px)
    print(f"PASS two fresh builds render the same final picture: frame mean differs {d_mean:.3f}/255, pixels {d_px:.3f}/255")

def legacy_block():
    """A light the step does not know switches the automatic step off, and that is a blocking finding naming the light and the one way
    to make a story light (lights.practical); a light made that way is kept and does not switch it off."""
    shot, cam = face_room("legacy")
    lamp = bpy.data.lights.new("PHONE_glow", "POINT")
    lamp.energy = 2.0
    ob = bpy.data.objects.new("GLOW_phone", lamp)
    ob.location = (0.2, -0.3, 1.2)
    core.link(ob, "LIGHTS")
    shot._viewlight_set_lights = {o.name for o in bpy.context.scene.objects if o.type == "LIGHT" and o is not ob}
    report = viewlight.shape(shot, cam, _automatic=True, fit_shadows=False, meter=False)
    items = viewlight.findings(report)
    block = [i for i in items if i["code"] == "light_step_skipped"]
    assert report.get("skipped") and block and block[0]["level"] == "block" and block[0]["lights"] == ["GLOW_phone"], items
    assert "lights.practical(" in block[0]["text"] and "SCREEN_K" in block[0]["text"], block
    bpy.data.objects.remove(ob, do_unlink=True)
    story = stage_lights.practical("phone_glow", (0.2, -0.3, 1.2), color=stage_lights.SCREEN_K, power=2.0)
    report = viewlight.shape(shot, cam, _automatic=True, fit_shadows=False, meter=False)
    assert not report.get("skipped") and not any(i["code"] == "light_step_skipped" for i in viewlight.findings(report)), report
    assert story.name in bpy.data.objects and story.data.energy > 0
    json.dumps(viewlight.json_safe(report))
    print("PASS an unknown light blocks the skipped step by name; lights.practical(..., color=lights.SCREEN_K) is kept and the step runs")


if __name__ == "__main__":
    main()
    prop_insert()
    runner()
    helpers()
    metering()
    legacy_block()
    shadow_fit()
    repeatable()
