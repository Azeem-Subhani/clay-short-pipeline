"""Build one reusable asset in Blender, render a preview, and file it in library/assets.

    python tools/clip.py asset <script.py> [--no-save] [--quality draft|preview]

The script defines:
    ASSET = dict(id="prop_wire_cutters", name="Wire cutters", kind="prop", tags=["tool", "cutters"], notes="...")
    def build_asset():        # build at the world origin, resting on z = 0, front toward -Y; return the root object
        ...
The preview is rendered on a neutral stage from a 3/4 view: look at it before trusting the asset in a shot.
"""
import argparse
import importlib.util
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import bpy  # noqa: E402

import stagekit  # noqa: E402
from stagekit import assets, build, camera, core, lights  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser(prog="run_asset")
    ap.add_argument("script")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--quality", default="preview", choices=("draft", "preview", "final"))
    a = ap.parse_args(argv)
    script = Path(a.script).resolve()
    shot = stagekit.begin("asset_preview", 1.0, a.quality)
    spec = importlib.util.spec_from_file_location("asset_script", script)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script.parent))
    try:
        spec.loader.exec_module(mod)
        meta = dict(mod.ASSET)
        root = mod.build_asset()
    except Exception:
        traceback.print_exc()
        print("[run_asset] BUILD FAILED")
        sys.exit(3)
    if root.parent is not None or not hasattr(root, "children_recursive"):
        print("[run_asset] build_asset() must return the root object of the asset")
        sys.exit(3)
    sx, sy, sz = assets.measure(root)
    lo, hi = core.world_bbox([o for o in [root, *root.children_recursive] if o.type == "MESH"])
    if abs(lo.z) > 0.01:
        print(f"[run_asset] warning: the asset does not rest on z = 0 (lowest point {lo.z:.3f} m)")
    entry = None
    if not a.no_save:
        prev_rel = f"previews/{meta['id']}.png"
        entry = assets.save(root, meta.pop("id"), meta.pop("name"), meta.pop("kind", "prop"), meta.pop("tags", ()), preview=prev_rel, **meta)
        out = assets.LIB / prev_rel
    else:
        out = script.with_suffix(".preview.png")
    # neutral preview stage: a plain floor, soft daylight, a three-quarter view
    size = max(sx, sy, sz, 0.05)
    c = (lo + hi) / 2
    build.ground("preview_floor", size * 16, "#8E8A84", relief=0.0, coll="PREVIEW")
    lights.rig("day_soft", sun_from=35)
    cam = camera.Camera()
    d = size * 2.3 + 0.2
    cam.view("preview", 0.0, pos=(c.x - d * 0.55, c.y - d * 0.8, c.z + d * 0.42), aim=tuple(c), lens=60)
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 960, 960
    sc.render.filepath = str(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print(f"[run_asset] size {sx} x {sy} x {sz} m; preview {out}")
    if entry:
        print(f"[run_asset] saved {entry['id']} -> {assets.LIB / entry['file']}")
    print("[run_asset] OK")


if __name__ == "__main__":
    main()
