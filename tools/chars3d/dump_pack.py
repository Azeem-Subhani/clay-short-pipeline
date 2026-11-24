"""dump_pack.py - read the 2D pack library and write, per character, what a 3D body needs: proportions, colours, part names.

    blender -b <character-library_v4.blend> --python dump_pack.py -- <out.json>
"""
import json
import sys

import bpy


def to_hex(c):
    def f(v):
        v = max(0.0, min(1.0, v))
        v = v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        return int(round(v * 255))
    return "#%02X%02X%02X" % (f(c[0]), f(c[1]), f(c[2]))


out = {}
roots = [o for o in bpy.data.objects if o.type == "EMPTY" and "character" in o.keys() and "view" in o.keys()]
for root in roots:
    name = root["character"]
    coll = next(c for c in bpy.data.collections if c.name == f"CH_{name}")
    obs = list(coll.all_objects)
    rig = next((o for o in obs if o.type == "ARMATURE" and o.get("view") == "Front"), None)
    if rig is None:
        continue
    B = {b.name: [round(b.head_local.x, 4), round(b.head_local.z, 4), round(b.tail_local.x, 4), round(b.tail_local.z, 4)] for b in rig.data.bones}
    parts = {}
    for o in obs:
        if o.type != "MESH" or o.get("cl_view") != "Front" or "cl_part" not in o.keys() or not len(o.data.vertices):
            continue
        xs = [o.location.x + v.co.x for v in o.data.vertices]
        zs = [o.location.z + v.co.z for v in o.data.vertices]
        m = o.data.materials[0] if o.data.materials else None
        key = m.name[3:].split(".")[0] if m is not None and m.name.startswith("CL_") else (m.name if m else "")
        parts[o["cl_part"]] = {"bone": o.parent_bone, "color": key, "hex": to_hex(m.diffuse_color) if m else "", "layer": round(-o.location.y / 0.03, 1),
                               "box": [round(min(xs), 3), round(min(zs), 3), round(max(xs), 3), round(max(zs), 3)],
                               "side": o.get("cl_side", ""), "wire": len(o.data.polygons) == 0,
                               "pts": [[round(o.location.x + v.co.x, 3), round(o.location.z + v.co.z, 3)] for v in o.data.vertices]}
    out[name] = {"label": root.get("label", name), "group": root.get("group", ""), "robe": bool(root.get("robe")), "legs": bool(root.get("legs", True)),
                 "order": int(root.get("order", 0)), "bones": B, "parts": parts}
argv = sys.argv[sys.argv.index("--") + 1:]
json.dump(out, open(argv[0], "w", encoding="utf-8"), indent=0)
print("DUMPED", len(out))
