"""Headless view lighting checks.

Run through the shared Blender lock:
    blender -b --factory-startup --python-exit-code 3 --python tools/tests/look/test_viewlight.py
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "blender"))
sys.dont_write_bytecode = True
from stagekit import camera, core, lights as stage_lights, viewlight


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
    report = viewlight.shape(shot, cam)
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
    assert report == viewlight.shape(shot, cam)
    assert set(lights()) == names
    print("PASS registry, placement, cut timing, continuous move and rebuild")

    shot = core.begin("viewlight_sun", 1, quality="draft")
    assert viewlight.sources() == []
    head(shot, "outdoors", (0, 0, 1.45), ["one"])
    cam = camera.Camera()
    camera_view(cam, "one", 0)
    sky = stage_lights.rig("day_clear", rim=0, look=False)
    sun = next(item for item in viewlight.sources() if item["kind"] == "sky")
    rig = viewlight.shape(shot, cam, edge=["outdoors"])["views"][0]
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
    rig = viewlight.shape(shot, cam)["views"][0]
    assert rig["hero"] is None and set(lights()) == {"VL_insert_bounce"}, rig
    print("PASS off-camera character does not light a prop insert")


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
                assert math.isclose(viewlight.view(report, "one")["key_power"], power * 0.5)
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
    rig = viewlight.view(viewlight.shape(shot, cam), "one")
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
    rep = viewlight.stand_in(cob, (0, 0, 1.55))
    got = {n for n in lights() if n.startswith("VL_standin_")}
    assert got == {"VL_standin_key", "VL_standin_fill", "VL_standin_front"}, got
    assert rep["white_balance"] == 5000 and bpy.context.scene.view_settings.use_white_balance
    assert 45 <= rep["angle_off_lens"] <= 60 and lights()["VL_standin_key"].data.energy > 0
    assert not (lights()["VL_standin_key"].data.animation_data and lights()["VL_standin_key"].data.animation_data.action)
    assert lights()["VL_standin_key"].get("sk_role") == "key" and lights()["VL_standin_fill"].get("sk_role") == "fill"
    night = viewlight.stand_in(cob, (0, 0, 1.55), mood="office_night")
    assert {n for n in lights() if n.startswith("VL_standin_")} == got and night["key_power"] < rep["key_power"]
    viewlight.clear()
    assert not lights()
    print("PASS stand_in")


if __name__ == "__main__":
    main()
    prop_insert()
    runner()
    helpers()
