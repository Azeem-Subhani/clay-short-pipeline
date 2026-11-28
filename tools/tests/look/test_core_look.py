"""Tests of the look settings in stagekit.core (style keys, shadow_res, white balance, render report, compositor grade).

    py -3 tools/tests/look/test_core_look.py --plain          # style keys only, no Blender
    blender -b --factory-startup --python tools/tests/look/test_core_look.py     # everything (go through the lock wrapper)

Inside Blender it also renders a small scene three ways (no compositor, a pass-through compositor group, the grade) at 25 percent
of a draft frame and checks that the pass-through picture is identical to the plain one and that the grade changes it.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.dont_write_bytecode = True
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def plain():
    st = json.loads((ROOT / "style" / "style.json").read_text(encoding="utf-8"))
    lk = st["look"]
    check("look keys", all(k in lk for k in ("white_balance_k", "grade", "shadow", "key", "fill", "practical", "cloth", "checks")))
    check("grade keys", set(lk["grade"]) >= {"enabled", "contrast_power", "bloom_threshold", "bloom_strength", "bloom_size"})
    check("shadow res per quality", lk["shadow"]["res_m"] == {"final": 0.004, "preview": 0.008, "draft": 0.016})
    pools = {q: st["eevee"]["quality"][q]["shadow_pool_mb"] for q in ("final", "preview", "draft")}
    check("shadow pools", pools == {"final": "2048", "preview": "1024", "draft": "512"}, str(pools))


def blender_part():
    sys.path.insert(0, str(ROOT / "tools" / "blender"))
    import bpy
    import numpy as np
    from mathutils import Vector
    from stagekit import core

    # look(): dotted keys, defaults
    check("look() reads a dotted key", core.look("cloth.sheen", 0.0) == 0.7)
    check("look() default for a missing key", core.look("cloth.nope", 123) == 123 and core.look("nope.deeper", None) is None)

    # shadow_res scales by quality and by `scale`
    core.begin("t_final", 1.0, "final")
    a = core.shadow_res()
    check("shadow_res final", abs(a - 0.004) < 1e-9 and abs(core.shadow_res(2.5) - 0.01) < 1e-9, str(a))
    core.begin("t_preview", 1.0, "preview")
    check("shadow_res preview", abs(core.shadow_res() - 0.008) < 1e-9)
    core.begin("t_draft", 1.0, "draft")
    check("shadow_res draft", abs(core.shadow_res() - 0.016) < 1e-9 and core.quality() == "draft")

    # render report lists every attempted setting, and the style pool size landed
    rep = core.RENDER_REPORT
    names = {x["name"] for x in rep["applied"]} | {x["name"] for x in rep["failed"]}
    wanted = {"eevee.taa_render_samples", "eevee.use_shadows", "eevee.shadow_ray_count", "eevee.shadow_step_count", "eevee.shadow_pool_size",
              "eevee.light_threshold", "eevee.use_raytracing", "eevee.ray_tracing_method", "eevee.use_fast_gi", "eevee.fast_gi_method",
              "eevee.fast_gi_distance", "eevee.fast_gi_quality", "eevee.use_bokeh_jittered", "eevee.bokeh_max_size", "eevee.bokeh_overblur",
              "eevee.use_overscan", "eevee.overscan_size", "eevee.volumetric_tile_size", "eevee.volumetric_samples", "eevee.use_volumetric_shadows",
              "view_settings.view_transform", "view_settings.look", "view_settings.use_white_balance"}
    check("report lists every setting", wanted <= names, str(sorted(wanted - names)))
    check("no setting failed", not rep["failed"], json.dumps(rep["failed"]))
    check("shadow pool landed", bpy.context.scene.eevee.shadow_pool_size == "512", bpy.context.scene.eevee.shadow_pool_size)
    core.begin("t_final2", 1.0, "final")
    check("final shadow pool 2048", bpy.context.scene.eevee.shadow_pool_size == "2048")

    # a bad setting is reported, not swallowed
    n = len(core.RENDER_REPORT["failed"])
    ok = core._put(bpy.context.scene.eevee, "no_such_property", 1, "eevee.no_such_property")
    check("a wrong name is reported", ok is False and len(core.RENDER_REPORT["failed"]) == n + 1)
    core.RENDER_REPORT["failed"].pop()

    # white balance sets and clears
    sc = bpy.context.scene
    vs = sc.view_settings
    check("default white balance is off", not vs.use_white_balance and core.RENDER_REPORT["white_balance_k"] is None)
    core.set_white_balance(5000)
    check("white balance sets", vs.use_white_balance and abs(vs.white_balance_temperature - 5000) < 1e-3 and sc["look_white_balance_k"] == 5000.0
          and core.RENDER_REPORT["white_balance_k"] == 5000.0)
    core.set_white_balance(6500)
    check("6500 clears", not vs.use_white_balance and core.RENDER_REPORT["white_balance_k"] is None and sc["look_white_balance_k"] == 0.0)
    core.set_white_balance(4200)
    core.set_white_balance(None)
    check("None clears", not vs.use_white_balance)

    # the grade builds, takes overrides, and switches off
    check("grade is on by default", sc.render.use_compositing and sc.compositing_node_group is not None and core.RENDER_REPORT["grade"])
    ng = sc.compositing_node_group
    kinds = sorted(n.bl_idname for n in ng.nodes)
    check("grade nodes", kinds == ["CompositorNodeColorBalance", "CompositorNodeGlare", "CompositorNodeRLayers", "NodeGroupOutput"], str(kinds))
    cb = next(n for n in ng.nodes if n.bl_idname == "CompositorNodeColorBalance")
    pw = next(i.default_value for i in cb.inputs if i.name == "Power" and hasattr(i.default_value, "__len__"))
    check("grade power 1.03", abs(pw[0] - 1.03) < 1e-6 and abs(pw[2] - 1.03) < 1e-6)
    core.grade(True, contrast_power=1.1, bloom_strength=0.0)
    ng = sc.compositing_node_group
    check("grade overrides", core.RENDER_REPORT["grade"]["contrast_power"] == 1.1 and not any(n.bl_idname == "CompositorNodeGlare" for n in ng.nodes))
    core.grade(False)
    check("grade off", sc.compositing_node_group is None and not sc.render.use_compositing and core.RENDER_REPORT["grade"] is None
          and bpy.data.node_groups.get("look_grade") is None)
    core.grade(True)
    check("grade back on", sc.render.use_compositing and sc.compositing_node_group is not None)

    # pixels: pass-through == no compositor, grade != pass-through
    def scene():
        core.begin("t_px", 1.0, "draft")
        s = bpy.context.scene
        s.render.resolution_percentage = 10
        s.eevee.taa_render_samples = 4
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 0, 0.5))
        bpy.ops.mesh.primitive_plane_add(size=6)
        ld = bpy.data.lights.new("L", "AREA"); ld.energy = 400; ld.size = 2
        lo = bpy.data.objects.new("L", ld); s.collection.objects.link(lo); lo.location = (1.5, -2, 3)
        lo.rotation_euler = (Vector((0, 0, 0.5)) - lo.location).to_track_quat("-Z", "Y").to_euler()
        cd = bpy.data.cameras.new("C"); co = bpy.data.objects.new("C", cd); s.collection.objects.link(co); s.camera = co
        co.location = (0, -3.5, 1.4); co.rotation_euler = (Vector((0, 0, 0.5)) - co.location).to_track_quat("-Z", "Y").to_euler()
        return s

    def shot_pixels(s, name):
        s.render.filepath = str(Path(tempfile.gettempdir()) / f"core_look_{name}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(s.render.filepath)
        px = np.array(img.pixels[:], dtype=np.float32)
        bpy.data.images.remove(img)
        return px

    s = scene(); core.grade(False)
    plain_px = shot_pixels(s, "plain")
    ng = bpy.data.node_groups.new("passthrough", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = ng.nodes.new("CompositorNodeRLayers"); out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], out.inputs["Image"])
    s.compositing_node_group = ng; s.render.use_compositing = True
    pass_px = shot_pixels(s, "pass")
    check("pass-through compositor is identical to none", np.array_equal(plain_px, pass_px), f"max diff {np.abs(plain_px - pass_px).max():.6f}")
    core.grade(True)
    grade_px = shot_pixels(s, "grade")
    d = np.abs(plain_px - grade_px).max()
    check("grade changes the picture", d > 0.005, f"max diff {d:.4f}")


def main():
    plain()
    if "--plain" not in sys.argv:
        try:
            import bpy  # noqa: F401
        except ImportError:
            print("SKIP Blender part (run it with blender -b --factory-startup --python)")
        else:
            blender_part()
    print("RESULT", "FAIL " + ", ".join(FAILS) if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
