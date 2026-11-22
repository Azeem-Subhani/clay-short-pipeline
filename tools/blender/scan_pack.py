"""Re-read part and colour names of every pack character into config/cast.json (after a new pack release).
Hand-written fields (looks, era, adapt, headwear_parts) are kept; new characters get era ["any"] and a note to fill them in.

    python tools/clip.py cast --rescan
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from stagekit import core  # noqa: E402

blend = core.pack_blend()
bpy.ops.wm.open_mainfile(filepath=str(blend))
cfg_path = core.PROJECT / "config" / "cast.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
old = cfg.get("characters", {})
out = {}
for root in sorted((o for o in bpy.data.objects if o.name.endswith("_Root") and "character" in o.keys()), key=lambda o: o.name):
    n = root.name[:-5]
    parts, cols, zs = set(), set(), []
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name.startswith(f"{n}_Front_") and "cl_part" in o.keys():
            parts.add(o["cl_part"])
            cols |= {m.name[3:] for m in o.data.materials if m and m.name != "CL_outline"}
            zs += [(o.matrix_world @ Vector(c)).z - root.location.z for c in o.bound_box]
    prev = old.get(n, {})
    out[n] = {"looks": prev.get("looks", "NEW in this pack: describe who this is"), "era": prev.get("era", ["any"]), "group": root.get("group", ""),
              "height_m": round(max(zs), 3) if zs else 1.7, "robe": bool(root.get("robe")), "colors": sorted(cols),
              "headwear_parts": prev.get("headwear_parts", []), "parts": sorted(parts), "adapt": prev.get("adapt", {})}
    if n not in old:
        print(f"new character: {n} - fill in looks/era in config/cast.json")
for n in old:
    if n not in out:
        print(f"gone from the pack: {n}")
cfg["characters"] = out
cfg_path.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"config/cast.json: {len(out)} characters from {blend.name}")
